"""Planning and runs routers persist through the real repository.

Regression: both routers built an InMemoryRepository per request, so a plan
decomposed in one request could never be read, checked or run in the next.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.architecture import ArchitectureDoc, Component
from app.domain.fakes import FakeLLM
from app.domain.ids import ReadableId
from app.main import create_app
from app.modules.capabilities.api import planning_capability
from app.modules.persistence.models import Project
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.planning.service import LLMTaskDecomposition, LLMTaskSpec

DECOMPOSITION = {
    "LLMTaskDecomposition": LLMTaskDecomposition(
        tasks=[
            LLMTaskSpec(title="Store schema", description="Create tables", size="s",
                        target_paths=["app/store.py"], ac_ids=["AC-001"]),
            LLMTaskSpec(title="REST endpoints", description="Expose API", size="m",
                        depends_on_titles=["Store schema"], ac_ids=["AC-002"]),
        ]
    )
}


@pytest.fixture()
def project(session: Session) -> Project:
    project = Project(name="plan-test", description=None)
    session.add(project)
    session.commit()
    return project


@pytest.fixture()
def api(session: Session) -> Iterator[TestClient]:
    app = create_app()

    def override_get_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[planning_capability] = lambda: FakeLLM(responses=DECOMPOSITION)
    with TestClient(app) as client:
        yield client


async def test_plan_readiness_and_runs_survive_across_requests(api, project, session):
    pid = str(project.id)
    arch = ArchitectureDoc(id=ReadableId("ARCH-001"), project_id=project.id, summary="API + store",
                           components=[Component(name="api", responsibility="serve")])
    arch.seal()
    await SqlAlchemyArtifactRepository(session).save_artifact(arch)

    decomposed = api.post("/planning/decompose", json={"project_id": pid, "architecture_id": "ARCH-001"})
    assert decomposed.status_code == 200, decomposed.text
    assert [t["id"] for t in decomposed.json()["tasks"]] == ["TASK-001", "TASK-002"]
    assert session.execute(text("SELECT count(*) FROM tasks")).scalar_one() >= 2

    plan = api.get("/planning/ARCH-001", params={"project_id": pid})
    assert plan.status_code == 200, plan.text
    assert plan.json()["dependencies"] == [{"task_id": "TASK-002", "depends_on_id": "TASK-001"}]

    blocked = api.post("/planning/tasks/TASK-002/readiness", json={"project_id": pid})
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["readiness"] == "blocked"
    assert "TASK-001" in blocked.json()["blocking_reasons"][0]

    ready = api.post("/planning/tasks/TASK-001/status", json={"project_id": pid, "target_status": "ready"})
    assert ready.status_code == 200, ready.text

    started = api.post("/runs/start", json={"project_id": pid, "task_id": "TASK-001"})
    assert started.status_code == 200, started.text
    run_id = started.json()["run"]["id"]

    listed = api.get("/runs", params={"project_id": pid})
    assert listed.status_code == 200
    assert [r["id"] for r in listed.json()["runs"]] == [run_id]
    assert api.get(f"/runs/{run_id}", params={"project_id": pid}).json()["run"]["task_id"] == "TASK-001"
