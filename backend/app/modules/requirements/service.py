"""Business logic for requirements analysis and acceptance criteria (ENG-014/019)."""

import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.domain.base import ArtifactRef, TraceLinks
from app.domain.enums import (
    ArtifactKind,
    ArtifactStatus,
    Priority,
    RequirementStatus,
    RequirementType,
    VerificationKind,
    assert_transition,
    REQUIREMENT_TRANSITIONS,
)
from app.domain.errors import TransitionError
from app.domain.ids import ReadableId
from app.domain.ports import LLMPort, RepositoryPort
from app.domain.requirements import Requirement
from app.domain.requirements_set import RequirementsSet
from app.domain.user_story import UserStory
from app.domain.acceptance_criterion import AcceptanceCriterion, Verification


# ---------------------------------------------------------------------------
# Intermediate LLM response schemas (what the model returns)
# ---------------------------------------------------------------------------

# Enum-typed fields put the allowed values into the JSON schema the model sees.
class LLMRequirementSpec(BaseModel):
    title: str
    description: str
    type: RequirementType
    priority: Priority


class LLMRequirementsAnalysis(BaseModel):
    summary: str
    requirements: list[LLMRequirementSpec]
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class LLMUserStorySpec(BaseModel):
    as_a: str
    i_want: str
    so_that: str


class LLMUserStoryGeneration(BaseModel):
    stories: list[LLMUserStorySpec]


class LLMACSpec(BaseModel):
    title: str
    given: list[str]
    when: list[str]
    then: list[str]
    verification_kind: VerificationKind = VerificationKind.unit
    verification_hint: str | None = None
    priority: Priority = Priority.must


class LLMACGeneration(BaseModel):
    acceptance_criteria: list[LLMACSpec]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class RequirementsService:
    """Coordinates requirements analysis, user-story generation, and AC generation.

    Uses an injected LLMPort for model calls and a RepositoryPort for ID
    allocation and artifact persistence.
    """

    def __init__(self, llm: LLMPort, repo: RepositoryPort) -> None:
        self._llm = llm
        self._repo = repo

    # -- requirements analysis ------------------------------------------------

    async def analyze_project(
        self, project_id: uuid.UUID, brief: str
    ) -> tuple[RequirementsSet, list[Requirement]]:
        """Analyze a project brief and produce a draft RequirementsSet + Requirements."""
        prompt = (
            "You are a senior requirements analyst. Analyze the following project brief "
            "and produce structured requirements (functional and non-functional), a summary, "
            "assumptions, and open questions.\n\n"
            f"Brief:\n{brief}"
        )
        analysis: LLMRequirementsAnalysis = await self._llm.generate_structured(
            prompt, LLMRequirementsAnalysis
        )

        # Create requirements with allocated IDs
        requirements: list[Requirement] = []
        for spec in analysis.requirements:
            req_id = await self._repo.next_id(project_id, ArtifactKind.requirement)
            req = Requirement(
                id=req_id,
                project_id=project_id,
                title=spec.title,
                description=spec.description,
                type=RequirementType(spec.type),
                priority=Priority(spec.priority),
                status=RequirementStatus.draft,
            )
            req.seal()
            await self._repo.save_artifact(req)
            requirements.append(req)

        # Create the RequirementsSet container
        set_id = await self._repo.next_id(project_id, ArtifactKind.requirements_set)
        members = [req.ref() for req in requirements]
        rset = RequirementsSet(
            id=set_id,
            project_id=project_id,
            summary=analysis.summary,
            members=members,
            assumptions=analysis.assumptions,
            open_questions=analysis.open_questions,
            status=RequirementStatus.draft,
        )
        rset.seal()
        await self._repo.save_artifact(rset)
        return rset, requirements

    # -- user story generation ------------------------------------------------

    async def generate_user_stories(
        self,
        project_id: uuid.UUID,
        requirements_set_id: ReadableId,
        context: str = "",
    ) -> list[UserStory]:
        """Generate user stories from the requirements in a given set."""
        rset = await self._repo.get_artifact(project_id, requirements_set_id)
        if not isinstance(rset, RequirementsSet):
            raise ValueError(f"RequirementsSet {requirements_set_id} not found")

        req_ids = [ref.id for ref in rset.members]
        requirements: list[Requirement] = []
        for rid in req_ids:
            req = await self._repo.get_artifact(project_id, rid)
            if isinstance(req, Requirement):
                requirements.append(req)

        req_titles = "\n".join(f"- {r.title}: {r.description}" for r in requirements)
        prompt = (
            "You are a product owner. For the requirements below, generate user stories "
            "in As / I want / So that format. Each story should trace back to one requirement.\n\n"
            f"Requirements:\n{req_titles}\n\nContext:\n{context}"
        )
        gen: LLMUserStoryGeneration = await self._llm.generate_structured(
            prompt, LLMUserStoryGeneration
        )

        stories: list[UserStory] = []
        for spec in gen.stories:
            story_id = await self._repo.next_id(project_id, ArtifactKind.user_story)
            # Link story back to the first requirement (simple traceability)
            trace = TraceLinks(requirement_ids=[requirements[0].id] if requirements else [])
            story = UserStory(
                id=story_id,
                project_id=project_id,
                as_a=spec.as_a,
                i_want=spec.i_want,
                so_that=spec.so_that,
                status=ArtifactStatus.draft,
                trace=trace,
            )
            story.seal()
            await self._repo.save_artifact(story)
            stories.append(story)
        return stories

    # -- acceptance criteria generation ----------------------------------------

    async def generate_acceptance_criteria(
        self,
        project_id: uuid.UUID,
        user_story_id: ReadableId,
        requirement_id: str = "",
        context: str = "",
    ) -> list[AcceptanceCriterion]:
        """Generate testable acceptance criteria from a user story."""
        story = await self._repo.get_artifact(project_id, user_story_id)
        if not isinstance(story, UserStory):
            raise ValueError(f"UserStory {user_story_id} not found")

        prompt = (
            "You are a QA engineer. For the user story below, generate testable "
            "acceptance criteria in Given/When/Then format. Include a verification kind.\n\n"
            f"Story: As a {story.as_a}, I want {story.i_want}, so that {story.so_that}\n\n"
            f"Context:\n{context}"
        )
        gen: LLMACGeneration = await self._llm.generate_structured(prompt, LLMACGeneration)

        criteria: list[AcceptanceCriterion] = []
        for spec in gen.acceptance_criteria:
            ac_id = await self._repo.next_id(project_id, ArtifactKind.acceptance_criterion)
            trace = TraceLinks(
                requirement_ids=[requirement_id] if requirement_id else [],
                ac_ids=[],
            )
            verification = Verification(
                kind=VerificationKind(spec.verification_kind),
                hint=spec.verification_hint,
            )
            ac = AcceptanceCriterion(
                id=ac_id,
                project_id=project_id,
                requirement_id=requirement_id,
                title=spec.title,
                given=spec.given,
                when=spec.when,
                then=spec.then,
                verification=verification,
                priority=Priority(spec.priority),
                status=ArtifactStatus.draft,
                trace=trace,
            )
            ac.seal()
            await self._repo.save_artifact(ac)
            criteria.append(ac)
        return criteria

    # -- requirements set lifecycle ----------------------------------------------

    async def approve_requirements_set(
        self, project_id: uuid.UUID, requirements_set_id: ReadableId
    ) -> RequirementsSet:
        """Move a requirements set from draft to approved via in_review."""
        rset = await self._repo.get_artifact(project_id, requirements_set_id)
        if not isinstance(rset, RequirementsSet):
            raise ValueError(f"RequirementsSet {requirements_set_id} not found")
        if rset.status == RequirementStatus.draft:
            assert_transition(
                rset.status, RequirementStatus.in_review, REQUIREMENT_TRANSITIONS
            )
            rset.status = RequirementStatus.in_review
            await self._repo.save_artifact(rset)
        assert_transition(
            rset.status, RequirementStatus.approved, REQUIREMENT_TRANSITIONS
        )
        rset.status = RequirementStatus.approved
        await self._repo.save_artifact(rset)
        return rset

    async def lock_requirements_set(
        self, project_id: uuid.UUID, requirements_set_id: ReadableId
    ) -> RequirementsSet:
        """Move a requirements set from approved to locked (immutable snapshot)."""
        rset = await self._repo.get_artifact(project_id, requirements_set_id)
        if not isinstance(rset, RequirementsSet):
            raise ValueError(f"RequirementsSet {requirements_set_id} not found")
        assert_transition(
            rset.status, RequirementStatus.locked, REQUIREMENT_TRANSITIONS
        )
        rset.status = RequirementStatus.locked
        await self._repo.save_artifact(rset)
        return rset

    # -- read helpers ---------------------------------------------------------------

    async def get_requirements_set(
        self, project_id: uuid.UUID, requirements_set_id: ReadableId
    ) -> tuple[RequirementsSet, list[Requirement]]:
        """Retrieve a requirements set and all its member requirements."""
        rset = await self._repo.get_artifact(project_id, requirements_set_id)
        if not isinstance(rset, RequirementsSet):
            raise ValueError(f"RequirementsSet {requirements_set_id} not found")
        requirements: list[Requirement] = []
        for ref in rset.members:
            req = await self._repo.get_artifact(project_id, ref.id)
            if isinstance(req, Requirement):
                requirements.append(req)
        return rset, requirements
