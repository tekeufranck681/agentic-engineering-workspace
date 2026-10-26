"""Tests for the requirements service (ENG-014/019)."""

import pytest
from uuid import uuid4

from app.domain.enums import (
    ArtifactKind,
    ArtifactStatus,
    RequirementStatus,
    RequirementType,
    Priority,
    TransitionError,
)
from app.domain.fakes import InMemoryRepository, FakeLLM
from app.modules.requirements.service import (
    RequirementsService,
    LLMRequirementsAnalysis,
    LLMRequirementSpec,
    LLMUserStoryGeneration,
    LLMUserStorySpec,
    LLMACGeneration,
    LLMACSpec,
)


def make_service(responses: dict) -> tuple[RequirementsService, InMemoryRepository, FakeLLM]:
    llm = FakeLLM(responses=responses)
    repo = InMemoryRepository()
    svc = RequirementsService(llm=llm, repo=repo)
    return svc, repo, llm


ANALYSIS_RESPONSE = {
    "LLMRequirementsAnalysis": LLMRequirementsAnalysis(
        summary="Login feature",
        requirements=[
            LLMRequirementSpec(
                title="User login",
                description="User can log in with email and password",
                type="functional",
                priority="must",
            ),
            LLMRequirementSpec(
                title="Password strength",
                description="System must enforce strong passwords",
                type="non_functional",
                priority="should",
            ),
        ],
        assumptions=["Users have valid email addresses"],
        open_questions=["Do we need social login?"],
    )
}

USER_STORY_RESPONSE = {
    "LLMUserStoryGeneration": LLMUserStoryGeneration(
        stories=[
            LLMUserStorySpec(
                as_a="registered user",
                i_want="log in with my email and password",
                so_that="I can access my account",
            ),
        ]
    )
}

AC_RESPONSE = {
    "LLMACGeneration": LLMACGeneration(
        acceptance_criteria=[
            LLMACSpec(
                title="Successful login",
                given=["I am on the login page"],
                when=["I enter valid credentials and submit"],
                then=["I am redirected to the dashboard"],
                verification_kind="integration",
                verification_hint="test_login_success",
                priority="must",
            ),
        ]
    )
}


@pytest.mark.asyncio
async def test_analyze_project_creates_requirements_set():
    svc, repo, llm = make_service(ANALYSIS_RESPONSE)
    pid = uuid4()
    rset, requirements = await svc.analyze_project(pid, "Build a login system")
    assert rset.id.startswith("RSET-")
    assert rset.status == RequirementStatus.draft
    assert len(requirements) == 2
    assert requirements[0].id.startswith("REQ-")
    assert requirements[0].type == RequirementType.functional
    assert requirements[0].priority == Priority.must
    assert rset.members[0].id == requirements[0].id


@pytest.mark.asyncio
async def test_analyze_project_requirements_have_correct_types():
    svc, repo, llm = make_service(ANALYSIS_RESPONSE)
    pid = uuid4()
    _, requirements = await svc.analyze_project(pid, "Build a login system")
    assert requirements[0].type == RequirementType.functional
    assert requirements[1].type == RequirementType.non_functional


@pytest.mark.asyncio
async def test_generate_user_stories():
    svc, repo, llm = make_service({**ANALYSIS_RESPONSE, **USER_STORY_RESPONSE})
    pid = uuid4()
    rset, _ = await svc.analyze_project(pid, "brief")
    stories = await svc.generate_user_stories(pid, rset.id)
    assert len(stories) == 1
    assert stories[0].id.startswith("US-")
    assert stories[0].as_a == "registered user"
    assert stories[0].trace.requirement_ids == ["REQ-001"]


@pytest.mark.asyncio
async def test_generate_acceptance_criteria():
    responses = {**ANALYSIS_RESPONSE, **USER_STORY_RESPONSE, **AC_RESPONSE}
    svc, repo, llm = make_service(responses)
    pid = uuid4()
    rset, _ = await svc.analyze_project(pid, "brief")
    stories = await svc.generate_user_stories(pid, rset.id)
    acs = await svc.generate_acceptance_criteria(pid, stories[0].id, requirement_id="REQ-001")
    assert len(acs) == 1
    assert acs[0].id.startswith("AC-")
    assert len(acs[0].given) == 1
    assert len(acs[0].when) == 1
    assert len(acs[0].then) == 1
    assert acs[0].verification.kind == "integration"


@pytest.mark.asyncio
async def test_generate_ac_rejects_empty_when_then():
    """Domain validation: AC must have non-empty when/then."""
    bad_ac = LLMACSpec(
        title="Bad", given=["g"], when=[], then=[], priority="must"
    )
    responses = {
        **ANALYSIS_RESPONSE,
        **USER_STORY_RESPONSE,
        "LLMACGeneration": LLMACGeneration(acceptance_criteria=[bad_ac]),
    }
    svc, repo, llm = make_service(responses)
    pid = uuid4()
    rset, _ = await svc.analyze_project(pid, "brief")
    stories = await svc.generate_user_stories(pid, rset.id)
    with pytest.raises(ValueError):
        await svc.generate_acceptance_criteria(pid, stories[0].id)


@pytest.mark.asyncio
async def test_approve_requirements_set():
    svc, repo, llm = make_service(ANALYSIS_RESPONSE)
    pid = uuid4()
    rset, _ = await svc.analyze_project(pid, "brief")
    approved = await svc.approve_requirements_set(pid, rset.id)
    assert approved.status == RequirementStatus.approved


@pytest.mark.asyncio
async def test_lock_requirements_set():
    svc, repo, llm = make_service(ANALYSIS_RESPONSE)
    pid = uuid4()
    rset, _ = await svc.analyze_project(pid, "brief")
    await svc.approve_requirements_set(pid, rset.id)
    locked = await svc.lock_requirements_set(pid, rset.id)
    assert locked.status == RequirementStatus.locked


@pytest.mark.asyncio
async def test_lock_before_approve_fails():
    svc, repo, llm = make_service(ANALYSIS_RESPONSE)
    pid = uuid4()
    rset, _ = await svc.analyze_project(pid, "brief")
    with pytest.raises(TransitionError):
        await svc.lock_requirements_set(pid, rset.id)


@pytest.mark.asyncio
async def test_get_requirements_set():
    svc, repo, llm = make_service(ANALYSIS_RESPONSE)
    pid = uuid4()
    rset, _ = await svc.analyze_project(pid, "brief")
    fetched_set, fetched_reqs = await svc.get_requirements_set(pid, rset.id)
    assert fetched_set.id == rset.id
    assert len(fetched_reqs) == 2


@pytest.mark.asyncio
async def test_analyze_project_seals_artifacts():
    svc, repo, llm = make_service(ANALYSIS_RESPONSE)
    pid = uuid4()
    rset, requirements = await svc.analyze_project(pid, "brief")
    assert rset.content_hash is not None
    assert requirements[0].content_hash is not None
