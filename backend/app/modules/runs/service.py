"""Business logic for run lifecycle management (ENG-044).

No LLM involvement: runs are pure lifecycle state. M5's orchestration attaches
here by driving transitions and consuming the start payload.
"""

import uuid

from app.domain.acceptance_criterion import AcceptanceCriterion
from app.domain.contract import EngineeringContract
from app.domain.enums import (
    ArtifactKind,
    RunStatus,
    TaskStatus,
    assert_transition,
    RUN_TRANSITIONS,
)
from app.domain.ids import ReadableId
from app.domain.ports import RepositoryPort
from app.domain.run import Run, RunStartPayload
from app.domain.task import Task


class RunsService:
    """Creates and drives run lifecycle; hands M5 an execution package."""

    @staticmethod
    def _bump_and_seal(artifact) -> None:
        """Advance `version` and re-seal before saving a mutation.

        Persistence is append-only versioned (unique on project+id+version), so
        a mutation must land as a NEW version row, as in the architecture and
        requirements services.
        """
        artifact.version += 1
        artifact.seal()

    def __init__(self, repo: RepositoryPort) -> None:
        self._repo = repo

    # -- start -----------------------------------------------------------------

    async def start_run(
        self, project_id: uuid.UUID, task_id: ReadableId
    ) -> Run:
        """Create a queued run for a task that is execution-ready."""
        task = await self._repo.get_artifact(project_id, task_id)
        if not isinstance(task, Task):
            raise ValueError(f"Task {task_id} not found")
        if task.status != TaskStatus.ready:
            raise ValueError(
                f"Task {task_id} must be ready to start a run "
                f"(current: {task.status})"
            )

        run_id = await self._repo.next_id(project_id, ArtifactKind.run)
        run = Run(
            id=run_id,
            project_id=project_id,
            task_id=str(task.id),
            attempt=1,
            status=RunStatus.queued,
        )
        run.seal()
        await self._repo.save_artifact(run)
        return run

    # -- transitions ------------------------------------------------------------

    async def transition(
        self,
        project_id: uuid.UUID,
        run_id: ReadableId,
        target_status: str,
        error: str | None = None,
    ) -> Run:
        """Move a run through its state machine with validation."""
        run = await self._repo.get_artifact(project_id, run_id)
        if not isinstance(run, Run):
            raise ValueError(f"Run {run_id} not found")
        target = RunStatus(target_status)
        assert_transition(run.status, target, RUN_TRANSITIONS)
        run.status = target
        if target == RunStatus.failed:
            run.error = error
        self._bump_and_seal(run)
        await self._repo.save_artifact(run)
        return run

    # -- reads -----------------------------------------------------------------

    async def get_run(
        self, project_id: uuid.UUID, run_id: ReadableId
    ) -> tuple[Run, Task | None]:
        """Return a run and its task (if present)."""
        run = await self._repo.get_artifact(project_id, run_id)
        if not isinstance(run, Run):
            raise ValueError(f"Run {run_id} not found")
        task = await self._repo.get_artifact(project_id, run.task_id)
        return run, task if isinstance(task, Task) else None

    async def list_runs(
        self, project_id: uuid.UUID, task_id: str | None = None
    ) -> list[Run]:
        """List runs, optionally filtered by task."""
        runs = await self._repo.list_artifacts(project_id, ArtifactKind.run)
        run_list = [r for r in runs if isinstance(r, Run)]
        if task_id is not None:
            run_list = [r for r in run_list if r.task_id == task_id]
        return run_list

    # -- M5 attach point ---------------------------------------------------------

    async def get_start_payload(
        self, project_id: uuid.UUID, run_id: ReadableId
    ) -> RunStartPayload:
        """Build the execution package for M5's orchestration.

        Contains the run id, its task, and the contracts + acceptance criteria
        linked through the task's trace links.
        """
        run = await self._repo.get_artifact(project_id, run_id)
        if not isinstance(run, Run):
            raise ValueError(f"Run {run_id} not found")
        task = await self._repo.get_artifact(project_id, run.task_id)
        if not isinstance(task, Task):
            raise ValueError(f"Task {run.task_id} for run {run_id} not found")

        contracts: list[EngineeringContract] = []
        for con_id in task.trace.contract_ids:
            con = await self._repo.get_artifact(project_id, con_id)
            if isinstance(con, EngineeringContract):
                contracts.append(con)

        criteria: list[AcceptanceCriterion] = []
        for ac_id in task.trace.ac_ids:
            ac = await self._repo.get_artifact(project_id, ac_id)
            if isinstance(ac, AcceptanceCriterion):
                criteria.append(ac)

        return RunStartPayload(
            run_id=str(run.id),
            task=task,
            contracts=contracts,
            acceptance_criteria=criteria,
        )
