"""ContextBuilder (ENG-023): one task's minimum sufficient context, with provenance.

Retrieval order follows HG/v1.0/07 §20: explicit artifact relations, then
dependency traversal with lifecycle filtering, then repository structural
search, with H-MEM lessons last and supplemental. External reads go through
the ToolGateway (``repo.list_files``, ``repo.read_file``, ``zetaris.run_sql``)
under a read-only scope for the run, so each one is a recorded tool call.
"""

import asyncio
import logging
import re
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.domain.acceptance_criterion import AcceptanceCriterion
from app.domain.adr import ArchitectureDecision
from app.domain.architecture import ArchitectureDoc
from app.domain.base import Artifact
from app.domain.contract import EngineeringContract
from app.domain.enums import ArtifactKind, ArtifactStatus, RequirementStatus
from app.domain.ports import RepositoryPort
from app.domain.requirements import Requirement
from app.domain.requirements_set import RequirementsSet
from app.domain.task import Task
from app.modules.context.errors import ContextBlockedError, ContextNotFoundError, ContextSourceUnavailableError
from app.modules.context.manifest import (
    AcceptanceCriterionContext,
    ArchitectureContext,
    ArtifactPin,
    ComponentContext,
    ContextManifest,
    ContextSource,
    ContractContext,
    DecisionContext,
    DependencyTaskContext,
    EngineeringFact,
    FactProvenance,
    PriorMemory,
    RelevantFile,
    RepositoryContext,
    RequirementContext,
    TaskContext,
)
from app.modules.memory.errors import AgentMemoryError
from app.modules.memory.models import MemoryRecallEvidence
from app.modules.memory.provider import AgentMemoryProvider
from app.modules.tools.builtin import REPO_LIST_FILES, REPO_READ_FILE
from app.modules.tools.gateway import ToolContext, ToolGateway, ToolScope
from app.modules.zetaris.tool import TOOL_NAME as ZETARIS_TOOL

logger = logging.getLogger(__name__)

DEFAULT_CAPABILITY = "engineering.implement"
_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in into is it its of on or that the this to was were will with "
    "only after before when then must should can not no all any each per via".split()
)
_TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]+$|_test\.[a-z]+$|\.(test|spec)\.[a-z]+$")


class ContextSettings(BaseModel):
    char_budget: int = Field(default=40_000, ge=2_000, description="Rendered context, about 10k tokens")
    max_files: int = Field(default=8, ge=0)
    max_tests: int = Field(default=4, ge=0)
    excerpt_chars: int = Field(default=4_000, ge=200)
    fact_row_limit: int = Field(default=20, ge=1)
    max_tool_calls: int = Field(default=40, ge=1)
    memory_top_n: int = Field(default=5, ge=1)
    memory_threshold: float = Field(default=0.35, ge=0, le=1)


class FactQuery(BaseModel):
    """A governed read the caller wants in the context; read-only by the tool's governance."""

    name: str
    statement: str
    columns: list[str] = Field(default_factory=list)


class ContextBuilder:
    """Builds a ContextManifest for a task from project state, the repository, Zetaris and H-MEM."""

    def __init__(
        self,
        artifacts: RepositoryPort,
        *,
        tools: ToolGateway | None = None,
        github=None,
        zetaris=None,
        memory: AgentMemoryProvider | None = None,
        settings: ContextSettings | None = None,
    ) -> None:
        self._artifacts = artifacts
        self._tools = tools
        self._github = github
        self._zetaris = zetaris
        self._memory = memory
        self._settings = settings or ContextSettings()

    async def build(
        self,
        project_id: uuid.UUID,
        task_id: str,
        *,
        run_id: str | None = None,
        objective: str | None = None,
        capability: str = DEFAULT_CAPABILITY,
        base_commit: str | None = None,
        fact_queries: Sequence[FactQuery] = (),
        require_facts: bool = False,
    ) -> ContextManifest:
        task = await self._artifacts.get_artifact(project_id, task_id)
        if not isinstance(task, Task):
            raise ContextNotFoundError(f"no task {task_id} in project {project_id}")
        run_id = run_id or f"CTX-{uuid.uuid4().int % 10**6:06d}"
        pins: dict[str, ArtifactPin] = {}
        unknowns: list[str] = []
        sources: list[ContextSource] = []

        blocked = await self._planned_versions_changed(project_id, task)
        requirements, locked_reasons = await self._locked_requirements(project_id, task, pins)
        blocked += locked_reasons
        if blocked:
            raise ContextBlockedError(blocked)
        sources.append(ContextSource(name="project_state", status="ok", detail="artifact links and versions"))

        requirement_ids = [r.pin.id for r in requirements]
        criteria = await self._criteria(project_id, task, requirement_ids, pins)
        if not criteria:
            unknowns.append(f"no acceptance criteria trace to {', '.join(requirement_ids) or task.id}")
        architecture, decisions = await self._architecture(project_id, requirement_ids, pins, unknowns)
        contracts = await self._contracts(project_id, task, pins, unknowns)
        dependencies = await self._dependencies(project_id, task, pins, unknowns)
        constraints = self._constraints(task, requirements, dependencies)

        manifest = ContextManifest(
            manifest_id=str(uuid.uuid4()),
            project_id=str(project_id),
            run_id=run_id,
            capability=capability,
            objective=objective or f"Implement and validate {task.id}: {task.title}",
            task=TaskContext(
                pin=_pin(task, pins),
                title=task.title,
                description=task.description,
                target_paths=list(task.target_paths),
                size=str(task.size),
            ),
            requirements=requirements,
            acceptance_criteria=criteria,
            architecture=architecture,
            decisions=decisions,
            contracts=contracts,
            dependency_tasks=dependencies,
            constraints=constraints,
            char_budget=self._settings.char_budget,
            built_at=datetime.now(timezone.utc),
        )

        scope = ToolScope(
            run_id=run_id,
            task_id=task.id,
            allowed_tools=frozenset({REPO_LIST_FILES, REPO_READ_FILE, ZETARIS_TOOL}),
            writable_paths=(),
            max_calls=self._settings.max_tool_calls,
        )
        self._read_facts(manifest, scope, project_id, fact_queries, require_facts, sources, unknowns)
        self._read_repository(manifest, scope, task, base_commit, sources, unknowns)
        await self._recall(manifest, project_id, task, sources)

        manifest.unknowns = unknowns
        manifest.sources = sources
        manifest.pins = list(pins.values())
        self._fit(manifest)
        manifest.chars = len(manifest.render())
        logger.info(
            "context %s for %s %s (project %s): %d requirements, %d criteria, %d files, %d tests, %d facts, "
            "%d prior memories, %d unknowns, sources %s, fingerprint %s",
            manifest.manifest_id,
            capability,
            task.id,
            project_id,
            len(manifest.requirements),
            len(manifest.acceptance_criteria),
            len(manifest.relevant_files),
            len(manifest.relevant_tests),
            len(manifest.facts),
            len(manifest.prior_memories),
            len(unknowns),
            ",".join(f"{s.name}={s.status}" for s in sources),
            manifest.fingerprint()[:12],
        )
        return manifest

    @staticmethod
    def _fit(manifest: ContextManifest) -> None:
        """Trim file excerpts, lowest-ranked first, until the rendered context fits its budget."""
        overflow = len(manifest.render()) - manifest.char_budget
        if overflow <= 0:
            return
        manifest.unknowns.append("file excerpts trimmed to fit the context budget")
        overflow = len(manifest.render()) - manifest.char_budget
        for bucket in (manifest.relevant_tests, manifest.relevant_files):
            for file in reversed(bucket):
                if overflow <= 0:
                    return
                cut = min(overflow, len(file.excerpt))
                file.excerpt = file.excerpt[: len(file.excerpt) - cut]
                file.truncated = True
                overflow -= cut

    # ------------------------------------------------------------ project state

    async def _planned_versions_changed(self, project_id: uuid.UUID, task: Task) -> list[str]:
        """Artifacts the task was planned against that moved since: the plan is stale."""
        reasons = []
        for ref in task.derived_from:
            latest = await self._artifacts.get_artifact(project_id, ref.id)
            if latest is None:
                reasons.append(f"{ref.id}@v{ref.version}, which {task.id} was planned against, no longer exists")
            elif latest.version != ref.version:
                reasons.append(
                    f"{ref.id} changed since {task.id} was planned (v{ref.version} then, v{latest.version} now): re-plan"
                )
        return reasons

    async def _locked_requirements(
        self, project_id: uuid.UUID, task: Task, pins: dict[str, ArtifactPin]
    ) -> tuple[list[RequirementContext], list[str]]:
        ids = _unique(
            [*task.trace.requirement_ids, *(r.id for r in task.derived_from if r.kind == ArtifactKind.requirement)]
        )
        if not ids:
            return [], [f"{task.id} traces to no requirement, so there is nothing locked to build against"]
        sets = [
            s
            for s in await self._artifacts.list_artifacts(project_id, ArtifactKind.requirements_set)
            if isinstance(s, RequirementsSet) and s.status == RequirementStatus.locked
        ]
        locked: dict[str, tuple[int, str]] = {}
        for requirements_set in sorted(sets, key=lambda s: (s.created_at, s.version)):
            for member in requirements_set.members:
                if member.kind == ArtifactKind.requirement:
                    locked[member.id] = (member.version, f"{requirements_set.id}@v{requirements_set.version}")

        contexts, reasons = [], []
        for requirement_id in ids:
            latest = await self._artifacts.get_artifact(project_id, requirement_id)
            if not isinstance(latest, Requirement):
                reasons.append(f"{requirement_id} does not exist")
                continue
            if requirement_id not in locked:
                reasons.append(f"{requirement_id} is not in a locked requirements set")
                continue
            version, locked_in = locked[requirement_id]
            if latest.version != version or latest.status == RequirementStatus.superseded:
                reasons.append(
                    f"{requirement_id} changed after it was locked ({requirement_id}@v{version} locked in "
                    f"{locked_in}, v{latest.version} {latest.status} now): re-lock and re-plan"
                )
                continue
            contexts.append(
                RequirementContext(
                    pin=_pin(latest, pins, status="locked"),
                    title=latest.title,
                    description=latest.description,
                    type=str(latest.type),
                    priority=str(latest.priority),
                    locked_in=locked_in,
                )
            )
        return contexts, reasons

    async def _criteria(
        self, project_id: uuid.UUID, task: Task, requirement_ids: list[str], pins: dict[str, ArtifactPin]
    ) -> list[AcceptanceCriterionContext]:
        wanted = set(task.trace.ac_ids) | {r.id for r in task.derived_from if r.kind == ArtifactKind.acceptance_criterion}
        found: dict[str, AcceptanceCriterion] = {}
        for criterion in await self._artifacts.list_artifacts(project_id, ArtifactKind.acceptance_criterion):
            if not isinstance(criterion, AcceptanceCriterion) or criterion.status == ArtifactStatus.superseded:
                continue
            if criterion.id in wanted or criterion.requirement_id in requirement_ids:
                found[criterion.id] = criterion
        return [
            AcceptanceCriterionContext(
                pin=_pin(criterion, pins),
                requirement_id=criterion.requirement_id,
                title=criterion.title,
                given=list(criterion.given),
                when=list(criterion.when),
                then=list(criterion.then),
                verification=(
                    f"{criterion.verification.kind}: {criterion.verification.hint or ''}".rstrip(": ")
                    if criterion.verification
                    else None
                ),
                priority=str(criterion.priority),
            )
            for criterion in sorted(found.values(), key=lambda c: c.id)
        ]

    async def _architecture(
        self, project_id: uuid.UUID, requirement_ids: list[str], pins: dict[str, ArtifactPin], unknowns: list[str]
    ) -> tuple[ArchitectureContext | None, list[DecisionContext]]:
        wanted = set(requirement_ids)
        docs = [d for d in await self._artifacts.list_artifacts(project_id, ArtifactKind.architecture)
                if isinstance(d, ArchitectureDoc)]
        covering = [
            d for d in docs
            if any(wanted & set(c.requirement_ids) for c in d.components) or wanted & set(d.trace.requirement_ids)
        ]
        accepted = [d for d in covering if d.status == ArtifactStatus.accepted]
        if not accepted:
            drafts = ", ".join(f"{d.id}@v{d.version} ({d.status})" for d in covering)
            unknowns.append(
                "no accepted architecture traces to " + ", ".join(requirement_ids)
                + (f"; not accepted yet: {drafts}" if drafts else "")
            )
            return None, []
        doc = max(accepted, key=lambda d: (d.created_at, d.version))
        components = [c for c in doc.components if wanted & set(c.requirement_ids)] or list(doc.components)
        architecture = ArchitectureContext(
            pin=_pin(doc, pins),
            summary=doc.summary,
            components=[ComponentContext(**c.model_dump()) for c in components],
        )
        decisions = []
        for decision_id in doc.decision_ids:
            adr = await self._artifacts.get_artifact(project_id, decision_id)
            if not isinstance(adr, ArchitectureDecision):
                unknowns.append(f"{doc.id} links {decision_id}, which does not exist")
            elif adr.status != ArtifactStatus.superseded:
                decisions.append(
                    DecisionContext(pin=_pin(adr, pins), title=adr.title, decision=adr.decision,
                                    consequences=list(adr.consequences))
                )
        return architecture, decisions

    async def _contracts(
        self, project_id: uuid.UUID, task: Task, pins: dict[str, ArtifactPin], unknowns: list[str]
    ) -> list[ContractContext]:
        ids = _unique([*task.trace.contract_ids, *(r.id for r in task.derived_from if r.kind == ArtifactKind.contract)])
        contracts = []
        for contract_id in ids:
            contract = await self._artifacts.get_artifact(project_id, contract_id)
            if not isinstance(contract, EngineeringContract):
                unknowns.append(f"{task.id} references contract {contract_id}, which does not exist")
                continue
            content = contract.content.model_dump(mode="json")
            contracts.append(ContractContext(pin=_pin(contract, pins), kind=content.pop("kind"), content=content))
        return contracts

    async def _dependencies(
        self, project_id: uuid.UUID, task: Task, pins: dict[str, ArtifactPin], unknowns: list[str]
    ) -> list[DependencyTaskContext]:
        dependencies = []
        for dependency_id in _unique(task.depends_on):
            dependency = await self._artifacts.get_artifact(project_id, dependency_id)
            if not isinstance(dependency, Task):
                unknowns.append(f"{task.id} depends on {dependency_id}, which does not exist")
                continue
            dependencies.append(DependencyTaskContext(pin=_pin(dependency, pins), title=dependency.title))
        return dependencies

    @staticmethod
    def _constraints(
        task: Task, requirements: list[RequirementContext], dependencies: list[DependencyTaskContext]
    ) -> list[str]:
        constraints = []
        if task.target_paths:
            constraints.append(f"write scope: only {', '.join(task.target_paths)}")
        constraints += [f"{r.pin.id} ({r.type}): {r.description}" for r in requirements if r.type == "non_functional"]
        constraints += [
            f"{d.pin.id} is {d.pin.status}; {task.id} builds on it" for d in dependencies if d.pin.status != "done"
        ]
        return constraints

    # ------------------------------------------------------------ external reads

    def _read_facts(
        self,
        manifest: ContextManifest,
        scope: ToolScope,
        project_id: uuid.UUID,
        extra: Sequence[FactQuery],
        require_facts: bool,
        sources: list[ContextSource],
        unknowns: list[str],
    ) -> None:
        if self._tools is None or self._zetaris is None:
            detail = "Zetaris is not configured for this backend (ZETARIS_* settings)"
            sources.append(ContextSource(name="zetaris", status="not_configured", detail=detail))
            unknowns.append(f"governed engineering facts: {detail}")
            if require_facts:
                raise ContextBlockedError([f"facts are required and {detail}"])
            return
        queries = [
            FactQuery(
                name="repository binding",
                statement=(
                    "SELECT full_name, default_branch, base_sha, status, bound_at FROM aew_pg.aew_repository_bindings "
                    f"WHERE project_id = '{project_id}' AND status = 'active'"
                ),
                columns=["full_name", "default_branch", "base_sha", "status", "bound_at"],
            ),
            FactQuery(
                name="project",
                statement=f"SELECT name, status FROM aew_pg.aew_projects WHERE id = '{project_id}'",
                columns=["name", "status"],
            ),
            *extra,
        ]
        context = ToolContext(scope, zetaris=self._zetaris)
        failures = []
        for query in queries:
            result = self._tools.call(
                context, ZETARIS_TOOL, {"statement": query.statement, "row_limit": self._settings.fact_row_limit}
            )
            if not result.ok:
                failures.append(f"{query.name}: {result.error}")
                continue
            evidence = result.output["evidence"]
            manifest.facts.append(
                EngineeringFact(
                    name=query.name,
                    statement=query.statement,
                    columns=query.columns,
                    rows=result.output["rows"],
                    provenance=FactProvenance(
                        tool_call_id=str(result.call_id),
                        query_id=evidence["query_id"],
                        request_id=evidence["request_id"],
                        statement_sha256=evidence["statement_sha256"],
                        org_id=evidence["org_id"],
                        executed_at=evidence["executed_at"],
                        truncated=evidence["truncated"],
                    ),
                )
            )
        binding = next((f for f in manifest.facts if f.name == "repository binding" and f.rows), None)
        if binding is not None:
            row = binding.rows[0]
            manifest.repository.full_name, manifest.repository.default_branch = row[0], row[1]
            manifest.repository.binding_base_sha = row[2] or None
        elif not failures:
            unknowns.append("Zetaris holds no active repository binding for this project")
        if failures:
            status = "unavailable" if not manifest.facts else "degraded"
            sources.append(ContextSource(name="zetaris", status=status, detail="; ".join(failures)))
            unknowns.append("governed engineering facts missing: " + "; ".join(failures))
            if require_facts:
                raise ContextBlockedError([f"facts are required and Zetaris failed: {'; '.join(failures)}"])
        else:
            sources.append(ContextSource(name="zetaris", status="ok", detail=f"{len(manifest.facts)} governed queries"))

    def _read_repository(
        self,
        manifest: ContextManifest,
        scope: ToolScope,
        task: Task,
        base_commit: str | None,
        sources: list[ContextSource],
        unknowns: list[str],
    ) -> None:
        if self._tools is None or self._github is None:
            detail = "the repository adapter is not configured (GITHUB_* settings)"
            sources.append(ContextSource(name="repository", status="not_configured", detail=detail))
            unknowns.append(f"relevant files and tests: {detail}")
            return
        try:
            repo = self._github.get_repo()
            manifest.repository.full_name = repo.full_name
            manifest.repository.default_branch = repo.default_branch
            base_commit = base_commit or self._github.get_branch_sha(repo.default_branch)
        except Exception as exc:  # the adapter's typed errors carry no secrets
            detail = f"repository unavailable: {type(exc).__name__}: {str(exc)[:200]}"
            sources.append(ContextSource(name="repository", status="unavailable", detail=detail))
            unknowns.append(f"relevant files and tests: {detail}")
            return
        manifest.repository.base_commit = base_commit
        if manifest.repository.binding_base_sha and manifest.repository.binding_base_sha != base_commit:
            unknowns.append(
                f"the project's binding records base {manifest.repository.binding_base_sha[:12]}, the branch is at "
                f"{base_commit[:12]}; files are read at {base_commit[:12]}"
            )
        context = ToolContext(scope, github=self._github, base_ref=base_commit)
        listed = self._tools.call(context, REPO_LIST_FILES, {"prefix": ""})
        if not listed.ok:
            sources.append(ContextSource(name="repository", status="unavailable", detail=listed.error or ""))
            unknowns.append(f"relevant files and tests: listing failed: {listed.error}")
            return

        terms = _terms(task.title, task.description, *(r.title for r in manifest.requirements),
                       *(c.title for c in manifest.acceptance_criteria))
        files, tests = _rank(listed.output["paths"], task.target_paths, terms)
        budget = self._settings.char_budget - len(manifest.render())
        omitted, failures = [], []
        for bucket, picked, limit in ((manifest.relevant_files, files, self._settings.max_files),
                                      (manifest.relevant_tests, tests, self._settings.max_tests)):
            for path, reason in picked[:limit]:
                if budget <= 0:
                    omitted.append(path)
                    continue
                read = self._tools.call(context, REPO_READ_FILE, {"path": path})
                if not read.ok:
                    failures.append(f"{path}: {read.error}")
                    continue
                text = read.output["text"]
                excerpt = text[: min(self._settings.excerpt_chars, max(budget, 0))]
                budget -= len(excerpt) + len(path) + 40
                bucket.append(
                    RelevantFile(path=path, reason=reason, excerpt=excerpt, truncated=len(excerpt) < len(text),
                                 tool_call_id=str(read.call_id))
                )
            omitted += [path for path, _ in picked[limit:]]
        for target in task.target_paths:
            if not target.endswith("/") and target not in listed.output["paths"]:
                unknowns.append(f"target path {target} does not exist at {base_commit[:12]} (new file?)")
        if omitted:
            unknowns.append(f"{len(omitted)} more matching files left out (limits or budget): {', '.join(omitted[:10])}")
        status = "degraded" if failures else "ok"
        detail = "; ".join(failures) if failures else f"{len(listed.output['paths'])} files at {base_commit[:12]}"
        sources.append(ContextSource(name="repository", status=status, detail=detail))
        if failures:
            unknowns.append("files that could not be read: " + "; ".join(failures))

    async def _recall(
        self, manifest: ContextManifest, project_id: uuid.UUID, task: Task, sources: list[ContextSource]
    ) -> None:
        if self._memory is None:
            sources.append(ContextSource(name="memory", status="not_configured", detail="no H-MEM provider"))
            return
        query = " ".join(
            [task.title, *(f"{c.title}: {' '.join(c.then)}" for c in manifest.acceptance_criteria),
             *(c.name for c in (manifest.architecture.components if manifest.architecture else []))]
        )[:4000]
        try:
            retrieval = await asyncio.to_thread(
                self._memory.query,
                str(project_id),
                query,
                top_n=self._settings.memory_top_n,
                threshold=self._settings.memory_threshold,
            )
        except AgentMemoryError as exc:
            raise ContextSourceUnavailableError(
                f"project memory (H-MEM) did not answer, so the context is not built without it: {exc}"
            ) from exc
        manifest.prior_memories = [
            PriorMemory(
                memory_id=item.memory.id,
                content=item.memory.content,
                relevance=round(item.relevance, 4),
                source=item.memory.source,
                refs=list(item.memory.provenance.refs),
            )
            for item in retrieval.memories
        ]
        manifest.memory_evidence = MemoryRecallEvidence.from_retrieval(retrieval, query_source="context").model_dump(
            mode="json"
        )
        sources.append(
            ContextSource(name="memory", status="ok", detail=f"{len(manifest.prior_memories)} lessons above the threshold")
        )


def _pin(artifact: Artifact, pins: dict[str, ArtifactPin], status: str | None = None) -> ArtifactPin:
    pin = ArtifactPin(
        kind=str(type(artifact).ARTIFACT_KIND),
        id=str(artifact.id),
        version=artifact.version,
        status=status or str(artifact.status),
        content_hash=artifact.content_hash,
    )
    pins[pin.id] = pin
    return pin


def _unique(values) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values))


def _terms(*texts: str) -> set[str]:
    words = set()
    for text in texts:
        for word in _WORD.findall(text.lower()):
            if len(word) >= 4 and word not in _STOPWORDS:
                words.add(word)
                if word.endswith("s"):
                    words.add(word[:-1])
    return words


def _rank(paths: list[str], targets: list[str], terms: set[str]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(files, tests), best first, each with the reason it was picked."""
    stems = {_stem(t) for t in targets if not t.endswith("/")}
    files, tests = [], []
    for path in paths:
        is_test = bool(_TEST_PATH.search(path))
        if any(path == t or (t.endswith("/") and path.startswith(t)) for t in targets):
            score, reason = 100, "target path"
        elif is_test and any(stem and stem in _stem(path) for stem in stems):
            score, reason = 50, "test of a target"
        else:
            words = set(_WORD.findall(path.lower()))
            matched = sorted(terms & (words | {w[:-1] for w in words if w.endswith("s")}))
            score, reason = len(matched), f"path matches {', '.join(matched)}"
        if score > 0:
            (tests if is_test else files).append((score, path, reason))
    order = lambda item: (-item[0], item[1])  # noqa: E731
    return ([(p, r) for _, p, r in sorted(files, key=order)], [(p, r) for _, p, r in sorted(tests, key=order)])


def _stem(path: str) -> str:
    name = path.rsplit("/", 1)[-1].split(".", 1)[0]
    return re.sub(r"^test_|_test$|_spec$", "", name.lower())
