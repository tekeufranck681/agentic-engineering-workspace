"""POST /runs/{id}/execute guards: unknown runs 404, non-queued runs 409 (no external calls)."""

from app.domain.enums import RunStatus
from app.domain.ids import ReadableId
from app.domain.run import Run
from app.modules.persistence.models import Project
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository


async def test_execute_rejects_unknown_and_non_queued_runs(client, session):
    project = Project(name="exec-test", description=None)
    session.add(project)
    session.commit()
    pid = str(project.id)
    assert client.post("/runs/RUN-404/execute", json={"project_id": pid}).status_code == 404
    run = Run(id=ReadableId("RUN-001"), project_id=project.id, task_id="TASK-001", status=RunStatus.succeeded)
    run.seal()
    await SqlAlchemyArtifactRepository(session).save_artifact(run)
    response = client.post("/runs/RUN-001/execute", json={"project_id": pid})
    assert response.status_code == 409 and "not queued" in response.json()["detail"]
