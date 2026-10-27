"""Business logic for task decomposition, dependencies, and readiness (ENG-029/034/039)."""

import uuid

from pydantic import BaseModel, Field

from app.domain.architecture import ArchitectureDoc
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

class PlanningService:
    """Decomposes architecture into executable tasks with dependencies and readiness.

    Uses an injected LLMPort for decomposition and a RepositoryPort for ID
    allocation and artifact persistence.
    """

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
        prompt = (
            "You are a tech lead. Break the architecture below into concrete, "
            "executable engineering tasks. For each task provide: title, description, "
            "target file paths, size (xs/s/m), which other task titles it depends on, "
            "and which requirement IDs it satisfies.\n\n"
            f"Architecture: {doc.summary}\nComponents:\n{comp_text}\n\nContext:\n{context}"
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
            trace = TraceLinks(
                requirement_ids=spec.requirement_ids,
                ac_ids=spec.ac_ids,
            )
            task = Task(
                id=task_id,
                project_id=project_id,
                title=spec.title,
                description=spec.description,
                target_paths=spec.target_paths,
                size=TaskSize(spec.size),
                depends_on=[],  # filled in pass 2
                status=TaskStatus.pending,
                trace=trace,
            )
            tasks.append(task)

        # Pass 2: resolve title-based dependencies to IDs and validate
        for task, spec in zip(tasks, gen.tasks):
            deps: list[str] = []
            for dep_title in spec.depends_on_titles:
                dep_id = title_to_id.get(dep_title)
                if dep_id is None:
                    raise ValueError(
                        f"Task {task.title!r} depends on unknown task title {dep_title!r}"
                    )
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

        readiness = "ready" if not blocking else "blocked"
        task.readiness = readiness
        task.blocking_reasons = blocking
        await self._repo.save_artifact(task)
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
