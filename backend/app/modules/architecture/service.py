"""Business logic for architecture generation, ADRs, and engineering contracts (ENG-024)."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.architecture import ArchitectureDoc, Component
from app.domain.base import TraceLinks
from app.domain.adr import ArchitectureDecision
from app.domain.contract import (
    ApiContractContent,
    DbSchemaContractContent,
    EngineeringContract,
    UmlContractContent,
)
from app.domain.enums import (
    ArtifactKind,
    ArtifactStatus,
    assert_transition,
)
from app.domain.errors import TransitionError
from app.domain.ids import ReadableId
from app.domain.ports import LLMPort, RepositoryPort
from app.domain.requirements import Requirement
from app.domain.requirements_set import RequirementsSet


# ---------------------------------------------------------------------------
# Intermediate LLM response schemas
# ---------------------------------------------------------------------------

class LLMComponentSpec(BaseModel):
    name: str
    responsibility: str
    depends_on: list[str] = Field(default_factory=list)
    requirement_ids: list[str] = Field(default_factory=list)


class LLMArchitectureAnalysis(BaseModel):
    summary: str
    components: list[LLMComponentSpec]
    decision_summaries: list[str] = Field(default_factory=list)


class LLMADRGeneration(BaseModel):
    title: str
    context: str
    decision: str
    alternatives: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)


class LLMContractGeneration(BaseModel):
    kind: Literal["api", "db_schema", "uml"]
    endpoints: list[dict] = Field(default_factory=list)
    tables: list[dict] = Field(default_factory=list)
    diagram_type: str = ""
    source: str = ""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ArchitectureService:
    """Coordinates architecture generation, ADR recording, and contract generation.

    Uses an injected LLMPort for model calls and a RepositoryPort for ID
    allocation and artifact persistence.
    """

    @staticmethod
    def _bump_and_seal(artifact) -> None:
        """Advance `version` and re-seal before saving a mutation.

        Persistence is append-only versioned (unique on project+id+version):
        a mutation must land as a NEW version row, never an overwrite of the
        same version (the in-memory fake allowed overwriting; the database
        rejects it).
        """
        artifact.version += 1
        artifact.seal()

    def __init__(self, llm: LLMPort, repo: RepositoryPort) -> None:
        self._llm = llm
        self._repo = repo

    # -- architecture generation ------------------------------------------------

    async def generate_architecture(
        self,
        project_id: uuid.UUID,
        requirements_set_id: ReadableId,
        context: str = "",
    ) -> tuple[ArchitectureDoc, list[ArchitectureDecision]]:
        """Generate an architecture document (with initial ADRs) from locked requirements."""
        rset = await self._repo.get_artifact(project_id, requirements_set_id)
        if not isinstance(rset, RequirementsSet):
            raise ValueError(f"RequirementsSet {requirements_set_id} not found")
        if rset.status != "locked":
            raise ValueError(
                f"RequirementsSet {requirements_set_id} must be locked before "
                f"architecture generation (current: {rset.status})"
            )

        # Load member requirements for context
        req_titles = []
        for ref in rset.members:
            req = await self._repo.get_artifact(project_id, ref.id)
            if isinstance(req, Requirement):
                req_titles.append(f"- {req.title}: {req.description}")
        req_text = "\n".join(req_titles)

        prompt = (
            "You are a software architect. Given the approved requirements below, "
            "design a high-level architecture: components with responsibilities, "
            "their dependencies, which requirements each component satisfies, "
            "and a short list of architecture decisions that should be recorded as ADRs.\n\n"
            f"Requirements:\n{req_text}\n\nContext:\n{context}"
        )
        gen: LLMArchitectureAnalysis = await self._llm.generate_structured(
            prompt, LLMArchitectureAnalysis
        )

        components = [
            Component(
                name=c.name,
                responsibility=c.responsibility,
                depends_on=c.depends_on,
                requirement_ids=c.requirement_ids,
            )
            for c in gen.components
        ]

        # Create the architecture document
        arch_id = await self._repo.next_id(project_id, ArtifactKind.architecture)
        doc = ArchitectureDoc(
            id=arch_id,
            project_id=project_id,
            summary=gen.summary,
            components=components,
            decision_ids=[],
            status=ArtifactStatus.draft,
            trace=TraceLinks(requirement_ids=[ref.id for ref in rset.members]),
        )

        # Create ADRs from decision summaries and link them
        decisions: list[ArchitectureDecision] = []
        for summary in gen.decision_summaries:
            adr_prompt = (
                "Write a full architecture decision record (ADR) for the following "
                "decision summary. Include title, context, the decision itself, "
                "alternatives considered, and consequences.\n\n"
                f"Summary: {summary}"
            )
            adr_gen: LLMADRGeneration = await self._llm.generate_structured(
                adr_prompt, LLMADRGeneration
            )
            adr_id = await self._repo.next_id(project_id, ArtifactKind.adr)
            adr = ArchitectureDecision(
                id=adr_id,
                project_id=project_id,
                title=adr_gen.title,
                context=adr_gen.context,
                decision=adr_gen.decision,
                alternatives=adr_gen.alternatives,
                consequences=adr_gen.consequences,
                status=ArtifactStatus.draft,
            )
            adr.seal()
            await self._repo.save_artifact(adr)
            decisions.append(adr)
            doc.decision_ids.append(adr_id)

        doc.seal()
        await self._repo.save_artifact(doc)
        return doc, decisions

    # -- ADR recording ----------------------------------------------------------

    async def record_decision(
        self, project_id: uuid.UUID, architecture_id: ReadableId, context: str
    ) -> ArchitectureDecision:
        """Record a single ADR and link it to the parent architecture."""
        doc = await self._repo.get_artifact(project_id, architecture_id)
        if not isinstance(doc, ArchitectureDoc):
            raise ValueError(f"ArchitectureDoc {architecture_id} not found")

        prompt = (
            "Write a full architecture decision record (ADR). Include title, context, "
            "the decision itself, alternatives considered, and consequences.\n\n"
            f"Context:\n{context}"
        )
        adr_gen: LLMADRGeneration = await self._llm.generate_structured(
            prompt, LLMADRGeneration
        )

        adr_id = await self._repo.next_id(project_id, ArtifactKind.adr)
        adr = ArchitectureDecision(
            id=adr_id,
            project_id=project_id,
            title=adr_gen.title,
            context=adr_gen.context,
            decision=adr_gen.decision,
            alternatives=adr_gen.alternatives,
            consequences=adr_gen.consequences,
            status=ArtifactStatus.draft,
        )
        adr.seal()
        await self._repo.save_artifact(adr)

        # Link into parent doc — as a new version row (append-only).
        doc.decision_ids.append(adr_id)
        self._bump_and_seal(doc)
        await self._repo.save_artifact(doc)
        return adr

    # -- engineering contracts ----------------------------------------------------

    async def generate_engineering_contract(
        self,
        project_id: uuid.UUID,
        kind: str,
        context: str = "",
    ) -> EngineeringContract:
        """Generate an engineering contract of the given kind (api | db_schema | uml)."""
        if kind not in ("api", "db_schema", "uml"):
            raise ValueError(f"Unknown contract kind: {kind}")

        prompt = (
            f"Produce an engineering contract of kind '{kind}'. "
            "Return the structured content for that kind.\n\n"
            f"Context:\n{context}"
        )
        gen: LLMContractGeneration = await self._llm.generate_structured(
            prompt, LLMContractGeneration
        )

        if gen.kind == "api":
            content = ApiContractContent(endpoints=gen.endpoints)
        elif gen.kind == "db_schema":
            content = DbSchemaContractContent(tables=gen.tables)
        else:
            content = UmlContractContent(
                diagram_type=gen.diagram_type, source=gen.source
            )

        con_id = await self._repo.next_id(project_id, ArtifactKind.contract)
        contract = EngineeringContract(
            id=con_id,
            project_id=project_id,
            content=content,
            status=ArtifactStatus.draft,
        )
        contract.seal()
        await self._repo.save_artifact(contract)
        return contract

    # -- lifecycle ---------------------------------------------------------------

    async def accept_architecture(
        self, project_id: uuid.UUID, architecture_id: ReadableId
    ) -> ArchitectureDoc:
        """Move an architecture document from draft to accepted."""
        doc = await self._repo.get_artifact(project_id, architecture_id)
        if not isinstance(doc, ArchitectureDoc):
            raise ValueError(f"ArchitectureDoc {architecture_id} not found")
        assert_transition(doc.status, ArtifactStatus.accepted, ARCH_TRANSITIONS)
        doc.status = ArtifactStatus.accepted
        self._bump_and_seal(doc)
        await self._repo.save_artifact(doc)
        return doc

    # -- read helpers --------------------------------------------------------------

    async def get_architecture(
        self, project_id: uuid.UUID, architecture_id: ReadableId
    ) -> tuple[ArchitectureDoc, list[ArchitectureDecision]]:
        """Retrieve an architecture document and its linked ADRs."""
        doc = await self._repo.get_artifact(project_id, architecture_id)
        if not isinstance(doc, ArchitectureDoc):
            raise ValueError(f"ArchitectureDoc {architecture_id} not found")
        decisions: list[ArchitectureDecision] = []
        for adr_id in doc.decision_ids:
            adr = await self._repo.get_artifact(project_id, adr_id)
            if isinstance(adr, ArchitectureDecision):
                decisions.append(adr)
        return doc, decisions


# ArtifactStatus transition map (draft -> accepted, no self-transitions)
ARCH_TRANSITIONS = {
    ArtifactStatus.draft: frozenset({ArtifactStatus.accepted, ArtifactStatus.superseded}),
    ArtifactStatus.accepted: frozenset({ArtifactStatus.superseded}),
    ArtifactStatus.superseded: frozenset(),
}
