"""The ContextManifest: what one task's run is given, and where each part came from.

Architecture refs: HG/v1.0/07 §20 (minimum sufficient context, record exact
artifact versions and the repository commit), HG/v1.0/08 §7.2 (manifest
contents), HG/v1.0/06 §7 (context.build contract), HG/v1.0/10 §23 (P0 sources).
Every artifact appears as ``id@version`` with its content hash in ``pins``;
external reads keep their provenance (tool call ids, Zetaris query evidence,
H-MEM memory ids and scores). ``unknowns`` says what is missing and why.
"""

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ArtifactPin(BaseModel):
    """One artifact version the context used."""

    kind: str
    id: str
    version: int
    status: str
    content_hash: str | None = None

    @property
    def ref(self) -> str:
        return f"{self.id}@v{self.version}"


class RequirementContext(BaseModel):
    pin: ArtifactPin
    title: str
    description: str
    type: str
    priority: str
    locked_in: str = Field(description="The locked requirements set that pins this version, e.g. RSET-001@v4")


class AcceptanceCriterionContext(BaseModel):
    pin: ArtifactPin
    requirement_id: str
    title: str
    given: list[str]
    when: list[str]
    then: list[str]
    verification: str | None = None
    priority: str


class ComponentContext(BaseModel):
    name: str
    responsibility: str
    depends_on: list[str] = Field(default_factory=list)
    requirement_ids: list[str] = Field(default_factory=list)


class ArchitectureContext(BaseModel):
    pin: ArtifactPin
    summary: str
    components: list[ComponentContext] = Field(description="Only components that trace to the task's requirements")


class DecisionContext(BaseModel):
    pin: ArtifactPin
    title: str
    decision: str
    consequences: list[str] = Field(default_factory=list)


class ContractContext(BaseModel):
    pin: ArtifactPin
    kind: str
    content: dict[str, Any]


class TaskContext(BaseModel):
    pin: ArtifactPin
    title: str
    description: str
    target_paths: list[str] = Field(default_factory=list)
    size: str | None = None


class DependencyTaskContext(BaseModel):
    pin: ArtifactPin
    title: str


class RepositoryContext(BaseModel):
    full_name: str | None = None
    default_branch: str | None = None
    base_commit: str | None = Field(default=None, description="The commit every file was read at")
    binding_base_sha: str | None = Field(default=None, description="base_sha of the project's binding (Zetaris)")


class RelevantFile(BaseModel):
    path: str
    reason: str = Field(description="Why it was picked: target path, test of a target, or matched terms")
    blob_sha: str | None = None
    excerpt: str = ""
    truncated: bool = False
    tool_call_id: str | None = None


class FactProvenance(BaseModel):
    """Where a Zetaris fact came from (the tool's QueryEvidence plus the tool call)."""

    tool_call_id: str
    query_id: str
    request_id: str
    statement_sha256: str
    org_id: str
    executed_at: datetime
    truncated: bool


class EngineeringFact(BaseModel):
    name: str
    statement: str
    columns: list[str] = Field(default_factory=list, description="Known when the builder wrote the statement")
    rows: list[list[str]] = Field(default_factory=list)
    provenance: FactProvenance


class PriorMemory(BaseModel):
    """A lesson from an earlier run (H-MEM): supplemental, never authoritative."""

    memory_id: str
    content: str
    relevance: float
    source: str
    refs: list[str] = Field(default_factory=list)


class ContextSource(BaseModel):
    name: Literal["project_state", "repository", "zetaris", "memory"]
    status: Literal["ok", "degraded", "unavailable", "not_configured", "skipped"]
    detail: str = ""


class ContextManifest(BaseModel):
    """Minimum sufficient context for one task, reconstructible from its pins."""

    manifest_id: str
    project_id: str
    run_id: str
    capability: str
    objective: str
    task: TaskContext
    requirements: list[RequirementContext] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterionContext] = Field(default_factory=list)
    architecture: ArchitectureContext | None = None
    decisions: list[DecisionContext] = Field(default_factory=list)
    contracts: list[ContractContext] = Field(default_factory=list)
    dependency_tasks: list[DependencyTaskContext] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    repository: RepositoryContext = Field(default_factory=RepositoryContext)
    relevant_files: list[RelevantFile] = Field(default_factory=list)
    relevant_tests: list[RelevantFile] = Field(default_factory=list)
    facts: list[EngineeringFact] = Field(default_factory=list)
    prior_memories: list[PriorMemory] = Field(default_factory=list)
    memory_evidence: dict[str, Any] | None = Field(default=None, description="H-MEM recall evidence (ids, scores, why)")
    unknowns: list[str] = Field(default_factory=list)
    sources: list[ContextSource] = Field(default_factory=list)
    pins: list[ArtifactPin] = Field(default_factory=list)
    chars: int = Field(default=0, description="Characters of rendered context")
    char_budget: int
    built_at: datetime

    @property
    def degraded(self) -> bool:
        """True when any source is missing or partial; the unknowns say which and why."""
        return any(source.status not in ("ok", "skipped") for source in self.sources)

    def fingerprint(self) -> str:
        """SHA-256 over the pinned artifact versions and the base commit: same inputs, same fingerprint."""
        basis = {
            "pins": sorted((pin.id, pin.version, pin.content_hash or "") for pin in self.pins),
            "base_commit": self.repository.base_commit,
        }
        return hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()

    def render(self) -> str:
        """The context as prompt text: locked state first, supplemental lessons last and labelled."""
        lines = [f"Objective: {self.objective}", "", f"Task {self.task.pin.ref}: {self.task.title}", self.task.description]
        if self.task.target_paths:
            lines.append(f"May change only: {', '.join(self.task.target_paths)}")
        if self.requirements:
            lines += ["", "Locked requirements:"]
            lines += [f"- {r.pin.ref} {r.title}: {r.description}" for r in self.requirements]
        if self.acceptance_criteria:
            lines += ["", "Acceptance criteria (each must hold):"]
            for ac in self.acceptance_criteria:
                lines.append(
                    f"- {ac.pin.ref} ({ac.requirement_id}) {ac.title}: GIVEN {'; '.join(ac.given)} "
                    f"WHEN {'; '.join(ac.when)} THEN {'; '.join(ac.then)}"
                )
        if self.architecture:
            lines += ["", f"Architecture {self.architecture.pin.ref}: {self.architecture.summary}"]
            lines += [f"- {c.name}: {c.responsibility}" for c in self.architecture.components]
        if self.decisions:
            lines += ["", "Decisions:"] + [f"- {d.pin.ref} {d.title}: {d.decision}" for d in self.decisions]
        if self.contracts:
            lines += ["", "Contracts:"]
            lines += [f"- {c.pin.ref} ({c.kind}): {json.dumps(c.content, sort_keys=True)}" for c in self.contracts]
        if self.dependency_tasks:
            lines += ["", "Depends on:"] + [f"- {t.pin.ref} {t.title} ({t.pin.status})" for t in self.dependency_tasks]
        if self.constraints:
            lines += ["", "Constraints:"] + [f"- {c}" for c in self.constraints]
        if self.facts:
            lines += ["", "Governed engineering facts (Zetaris):"]
            for fact in self.facts:
                header = ", ".join(fact.columns) if fact.columns else "rows"
                lines.append(f"- {fact.name} [{header}] = {fact.rows} (query {fact.provenance.query_id})")
        if self.repository.base_commit:
            lines += ["", f"Repository {self.repository.full_name} at {self.repository.base_commit}"]
        for title, files in (("Relevant files:", self.relevant_files), ("Relevant tests:", self.relevant_tests)):
            if files:
                lines += ["", title]
                for file in files:
                    lines.append(f"--- {file.path} ({file.reason}){' [truncated]' if file.truncated else ''}")
                    lines.append(file.excerpt)
        if self.unknowns:
            lines += ["", "Unknowns:"] + [f"- {u}" for u in self.unknowns]
        if self.prior_memories:
            lines += [
                "",
                "Relevant lessons from earlier runs (Meterless H-MEM, supplemental and never authoritative; "
                "the locked state above wins):",
            ]
            lines += [f"- {m.content} <{m.memory_id}, {m.source}>" for m in self.prior_memories]
        return "\n".join(lines)
