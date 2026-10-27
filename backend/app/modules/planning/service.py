"""Business logic for task decomposition, dependencies, and readiness (ENG-029/034/039)."""

import uuid

from pydantic import BaseModel, Field

from app.domain.acceptance_criterion import AcceptanceCriterion
from app.domain.architecture import ArchitectureDoc
from app.domain.requirements import Requirement
from app.domain.base import TraceLinks
from app.domain.enums import (
    ArtifactKind,
    TaskSize,
    TaskStatus,
    assert_transition,
    TASK_TRANSITIONS,
)
from app.domain.ids import ReadableId
from app.domain.ports import LLMPort, RepositoryPort
from app.domain.requirements_set import RequirementsSet
from app.domain.task import Task, TaskDependency


# ---------------------------------------------------------------------------
# Intermediate LLM response schema
# ---------------------------------------------------------------------------

class LLMTaskSpec(BaseModel):
    title: str
    description: str
    target_paths: list[str] = Field(default_factory=list)
    size: str = "m"  # xs | s | m
    depends_on_titles: list[str] = Field(default_factory=list)
    requirement_ids: list[str] = Field(default_factory=list)
    ac_ids: list[str] = Field(default_factory=list)


class LLMTaskDecomposition(BaseModel):
    tasks: list[LLMTaskSpec]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

# Model output tolerance: sizes and dependency titles come back from the LLM in
# varied forms. Normalize what is unambiguous; still reject what is not.
_SIZE_ALIASES = {
    "xs": TaskSize.xs, "extra small": TaskSize.xs, "extra-small": TaskSize.xs, "tiny": TaskSize.xs,
    "s": TaskSize.s, "small": TaskSize.s,
    "m": TaskSize.m, "medium": TaskSize.m,
    # Larger estimates are capped at the largest atomic size the plan allows.
    "l": TaskSize.m, "large": TaskSize.m, "xl": TaskSize.m,
}


def normalize_size(value: str) -> TaskSize:
    """Map a model-reported size onto xs/s/m, or raise ValueError."""
    size = _SIZE_ALIASES.get(" ".join(str(value).lower().split()))
    if size is None:
        raise ValueError(f"task size {value!r} is not one of xs, s, m")
    return size


def _title_key(title: str) -> str:
    return " ".join("".join(c if c.isalnum() else " " for c in title.lower()).split())


def resolve_dependency(title: str, title_to_id: dict[str, ReadableId]) -> ReadableId | None:
    """Exact title, then case/punctuation-insensitive title, then a task id."""
    if title in title_to_id:
        return title_to_id[title]
    key = _title_key(title)
    matches = [tid for t, tid in title_to_id.items() if _title_key(t) == key]
    if len(matches) == 1:
        return matches[0]
    ids = {str(tid): tid for tid in title_to_id.values()}
    return ids.get(title.strip().upper())


class PlanningService:
    """Decomposes architecture into executable tasks with dependencies and readiness.

    Uses an injected LLMPort for decomposition and a RepositoryPort for ID
    allocation and artifact persistence.
    """

    @staticmethod
    def _bump_and_seal(artifact) -> None:
        """Advance `version` and re-seal before saving a mutation.

        Persistence is append-only versioned (unique on project+id+version), so
        a mutation must land as a NEW version row, as in the architecture and
        requirements services.
        """
        artifact.version += 1
        artifact.seal()

    def __init__(self, llm: LLMPort, repo: RepositoryPort) -> None:
        self._llm = llm
        self._repo = repo

    # -- decomposition ------------------------------------------------------------

    async def decompose(
        self,
        project_id: uuid.UUID,
        architecture_id: ReadableId,
        requirements_set_id: ReadableId = "",
        context: str = "",
    ) -> list[Task]:
        """Break an architecture document into executable tasks.

        Dependency references arrive as task *titles* from the LLM and are
        resolved to readable IDs after all tasks are allocated.
        """
        doc = await self._repo.get_artifact(project_id, architecture_id)
        if not isinstance(doc, ArchitectureDoc):
            raise ValueError(f"ArchitectureDoc {architecture_id} not found")

        comp_text = "\n".join(
            f"- {c.name}: {c.responsibility} (deps: {', '.join(c.depends_on) or 'none'})"
            for c in doc.components
        )
        # Requirements and their acceptance criteria, so every task can name the
        # criteria evaluation will check it against.
        requirements = [r for r in await self._repo.list_artifacts(project_id, ArtifactKind.requirement) if isinstance(r, Requirement)]
        criteria = [a for a in await self._repo.list_artifacts(project_id, ArtifactKind.acceptance_criterion) if isinstance(a, AcceptanceCriterion)]
        ac_by_req: dict[str, list[str]] = {}
        for ac in criteria:
            ac_by_req.setdefault(ac.requirement_id, []).append(str(ac.id))
        req_text = "\n".join(
            f"- {r.id}: {r.title} (acceptance criteria: "
            + ("; ".join(f"{a.id} {a.title}" for a in criteria if a.requirement_id == str(r.id)) or "none")
            + ")"
            for r in requirements
        )
        prompt = (
            "You are a tech lead. Break the architecture below into concrete, "
            "executable engineering tasks. For each task provide: title, description, "
            "target file paths, size (xs/s/m), which other task titles it depends on, "
            "which requirement IDs it satisfies, and which acceptance criterion IDs "
            "(from the list below) verify it. Every task should cover at least one "
            "acceptance criterion.\n\n"
            f"Architecture: {doc.summary}\nComponents:\n{comp_text}\n\n"
            f"Requirements:\n{req_text or '- none'}\n\nContext:\n{context}"
        )
        gen: LLMTaskDecomposition = await self._llm.generate_structured(
            prompt, LLMTaskDecomposition
        )

        # Pass 1: allocate IDs and create tasks without dependencies
        title_to_id: dict[str, ReadableId] = {}
        tasks: list[Task] = []
        for spec in gen.tasks:
            task_id = await self._repo.next_id(project_id, ArtifactKind.task)
            title_to_id[spec.title] = task_id
            # Validate IDs only against registries that exist for the project.
            known_reqs = {str(r.id) for r in requirements}
            known_acs = {a for ids in ac_by_req.values() for a in ids}
            req_ids = [r for r in spec.requirement_ids if r in known_reqs] if known_reqs else list(spec.requirement_ids)
            ac_ids = [a for a in spec.ac_ids if a in known_acs] if known_acs else list(spec.ac_ids)
            if not ac_ids:  # inherit the criteria of the requirements it serves
                ac_ids = [a for r in req_ids for a in ac_by_req.get(r, [])]
            trace = TraceLinks(requirement_ids=req_ids, ac_ids=ac_ids)
            task = Task(
                id=task_id,
                project_id=project_id,
                title=spec.title,
                description=spec.description,
                target_paths=spec.target_paths,
                size=normalize_size(spec.size),
                depends_on=[],  # filled in pass 2
                status=TaskStatus.pending,
                trace=trace,
            )
            tasks.append(task)

        # Pass 2: resolve title-based dependencies to IDs and validate
        for task, spec in zip(tasks, gen.tasks):
            deps: list[str] = []
            for dep_title in spec.depends_on_titles:
                dep_id = resolve_dependency(dep_title, title_to_id)
                if dep_id is None:
                    raise ValueError(
                        f"Task {task.title!r} depends on unknown task title {dep_title!r}"
                    )
                # Models sometimes list a task as its own dependency or repeat
                # one; both carry no ordering information, so drop them.
                if dep_id != task.id and dep_id not in deps:
                    deps.append(dep_id)
            task.depends_on = deps
            task.seal()
            await self._repo.save_artifact(task)

        return tasks

    # -- dependencies (derived) ------------------------------------------------------

    def derive_dependencies(self, tasks: list[Task]) -> list[TaskDependency]:
        """Derive dependency edges from tasks' depends_on lists (derived view only)."""
        edges: list[TaskDependency] = []
        for task in tasks:
            for dep_id in task.depends_on:
                edges.append(
                    TaskDependency(task_id=str(task.id), depends_on_id=dep_id)
                )
        return edges

    # -- readiness -----------------------------------------------------------------

    async def check_readiness(
        self, project_id: uuid.UUID, task_id: ReadableId
    ) -> tuple[str, list[str]]:
        """Compute execution readiness: a task is ready when all dependencies are done.

        Returns (readiness, blocking_reasons). readiness is "ready" or "blocked".
        """
        task = await self._repo.get_artifact(project_id, task_id)
        if not isinstance(task, Task):
            raise ValueError(f"Task {task_id} not found")

        blocking: list[str] = []
        for dep_id in task.depends_on:
            dep = await self._repo.get_artifact(project_id, dep_id)
            if dep is None:
                blocking.append(f"dependency {dep_id} not found")
            elif isinstance(dep, Task) and dep.status != TaskStatus.done:
                blocking.append(
                    f"dependency {dep_id} ({dep.title}) is {dep.status}"
                )

        # Readiness is derived on demand and excluded from the content hash, so
        # it is returned rather than persisted as a new task version.
        readiness = "ready" if not blocking else "blocked"
        return readiness, blocking

    # -- status transitions -----------------------------------------------------------

    async def update_task_status(
        self, project_id: uuid.UUID, task_id: ReadableId, target_status: str
    ) -> Task:
        """Move a task through its status state machine with validation."""
        task = await self._repo.get_artifact(project_id, task_id)
        if not isinstance(task, Task):
            raise ValueError(f"Task {task_id} not found")
        target = TaskStatus(target_status)
        assert_transition(task.status, target, TASK_TRANSITIONS)
        task.status = target
        self._bump_and_seal(task)
        await self._repo.save_artifact(task)
        return task

    # -- read helpers ----------------------------------------------------------------

    async def get_plan(
        self, project_id: uuid.UUID, architecture_id: ReadableId
    ) -> tuple[list[Task], list[TaskDependency]]:
        """Return all tasks derived from an architecture, plus dependency edges."""
        doc = await self._repo.get_artifact(project_id, architecture_id)
        if not isinstance(doc, ArchitectureDoc):
            raise ValueError(f"ArchitectureDoc {architecture_id} not found")
        tasks = await self._repo.list_artifacts(project_id, ArtifactKind.task)
        task_list = [t for t in tasks if isinstance(t, Task)]
        return task_list, self.derive_dependencies(task_list)
