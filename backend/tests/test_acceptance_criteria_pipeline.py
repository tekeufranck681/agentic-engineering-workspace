"""Set-level acceptance criteria feed planning, so tasks carry ac_ids a run can evaluate."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.architecture import ArchitectureDoc, Component
from app.domain.fakes import FakeLLM
from app.domain.ids import ReadableId
from app.main import create_app
from app.modules.capabilities.api import planning_capability, requirements_capability
from app.modules.persistence.models import Project
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.planning.service import LLMTaskDecomposition, LLMTaskSpec
from app.modules.requirements.service import LLMACGeneration, LLMACSpec
from tests.test_requirements_api_persistence import ANALYSIS_RESPONSE

AC = {"LLMACGeneration": LLMACGeneration(acceptance_criteria=[
    LLMACSpec(title="Only the selected month", given=["invoices in two months"], when=["export March"], then=["only March rows"]),
])}
PLAN = {"LLMTaskDecomposition": LLMTaskDecomposition(tasks=[
    LLMTaskSpec(title="Query by month", description="d", size="s", requirement_ids=["REQ-001"]),
    LLMTaskSpec(title="Invented trace", description="d", size="s", ac_ids=["AC-999"]),
])}


@pytest.fixture()
def api(session: Session) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: (yield session)
    app.dependency_overrides[requirements_capability] = lambda: FakeLLM(responses={**ANALYSIS_RESPONSE, **AC})
    app.dependency_overrides[planning_capability] = lambda: FakeLLM(responses=PLAN)
    with TestClient(app) as client:
        yield client


async def test_criteria_are_generated_listed_and_inherited_by_tasks(api, session):
    project = Project(name="ac-pipeline", description=None)
    session.add(project)
    session.commit()
    pid = str(project.id)
    set_id = api.post("/requirements/analyze", json={"project_id": pid, "brief": "Billing"}).json()["set"]["id"]

    generated = api.post(f"/requirements/set/{set_id}/acceptance-criteria", json={"project_id": pid})
    assert generated.status_code == 200, generated.text
    ac_ids = [a["id"] for a in generated.json()["acceptance_criteria"]]
    assert ac_ids and all(a["requirement_id"] == "REQ-001" for a in generated.json()["acceptance_criteria"])
    listed = api.get(f"/requirements/set/{set_id}/acceptance-criteria", params={"project_id": pid})
    assert [a["id"] for a in listed.json()["acceptance_criteria"]] == ac_ids

    arch = ArchitectureDoc(id=ReadableId("ARCH-001"), project_id=project.id, summary="s", components=[Component(name="api", responsibility="r")])
    arch.seal()
    await SqlAlchemyArtifactRepository(session).save_artifact(arch)
    tasks = api.post("/planning/decompose", json={"project_id": pid, "architecture_id": "ARCH-001"}).json()["tasks"]
    assert tasks[0]["trace"]["ac_ids"] == ac_ids  # inherited from REQ-001
    assert tasks[1]["trace"]["ac_ids"] == []  # invented AC-999 dropped
