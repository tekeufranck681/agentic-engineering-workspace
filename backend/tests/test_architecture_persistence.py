"""ENG-024/029 persistence tests — architecture, ADR, contract and task tables.

Pins the real behavior: every ENG-004 artifact kind now round-trips through
the RepositoryPort to PostgreSQL-shaped tables (SQLite in tests), versions
append without overwrite, enums store lowercase values, the 0005 migration
chain applies/reverts, and the architecture API runs its full
generate → record-decision → accept flow against the database.
"""

import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from alembic import command
from alembic.script import ScriptDirectory
from alembic.config import Config

from app.core.db import get_session
from app.domain.adr import ArchitectureDecision
from app.domain.architecture import ArchitectureDoc, Component
from app.domain.contract import ApiContractContent, ApiEndpoint, EngineeringContract
from app.domain.enums import ArtifactKind, ArtifactStatus, TaskSize, TaskStatus
from app.domain.fakes import FakeLLM
from app.domain.ids import ReadableId
from app.domain.task import Task
from app.main import create_app
from app.modules.architecture.router import get_service as architecture_service_dep
from app.modules.architecture.service import (
    ArchitectureService,
    LLMADRGeneration,
    LLMArchitectureAnalysis,
    LLMComponentSpec,
    LLMContractGeneration,
)
from app.modules.capabilities.api import requirements_capability
from app.modules.persistence.models import Project
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.requirements.service import (
    LLMRequirementSpec,
    LLMRequirementsAnalysis,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
NIL_PROJECT = uuid.UUID(int=0)
NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)


@pytest.fixture()
def project(session: Session):
    project = Project(name="arch-test", description=None)
    session.add(project)
    session.commit()
    return project


@pytest.fixture()
def repo(session: Session):
    return SqlAlchemyArtifactRepository(session)


# ------------------------------------------------------------- repository


async def test_all_four_kinds_roundtrip_through_the_port(repo, project):
    pid = project.id

    arch = ArchitectureDoc(
        id=ReadableId("ARCH-001"),
        project_id=pid,
        summary="Auth service + gateway",
        components=[Component(name="auth", responsibility="login")],
        decision_ids=["ADR-001"],
        created_at=NOW,
    )
    adr = ArchitectureDecision(
        id=ReadableId("ADR-001"), project_id=pid, title="JWT", context="c",
        decision="d", alternatives=["sessions"], consequences=["stateless"],
        created_at=NOW,
    )
    contract = EngineeringContract(
        id=ReadableId("CON-001"),
        project_id=pid,
        content=ApiContractContent(
            endpoints=[ApiEndpoint(method="POST", path="/login", summary="Login")]
        ),
        created_at=NOW,
    )
    # Allocate the task id through the port the way services do — the
    # counter is the allocator, hand-written ids don't move it.
    task_id = await repo.next_id(pid, ArtifactKind.task)
    assert str(task_id) == "TASK-001"
    task = Task(
        id=task_id,
        project_id=pid,
        title="Implement login",
        description="Wire the endpoint",
        target_paths=["src/auth.py"],
        size=TaskSize.s,
        depends_on=[],
        created_at=NOW,
    )
    for artifact in (arch, adr, contract, task):
        artifact.seal()
        await repo.save_artifact(artifact)

    for kind, rid, cls in (
        (ArtifactKind.architecture, "ARCH-001", ArchitectureDoc),
        (ArtifactKind.adr, "ADR-001", ArchitectureDecision),
        (ArtifactKind.contract, "CON-001", EngineeringContract),
        (ArtifactKind.task, "TASK-001", Task),
    ):
        loaded = await repo.get_artifact(pid, ReadableId(rid))
        assert type(loaded) is cls
        assert loaded.status in (ArtifactStatus.draft, TaskStatus.pending)

    # Contract content is lossless through the JSON blob.
    loaded_contract = await repo.get_artifact(pid, ReadableId("CON-001"))
    assert loaded_contract.content.kind == "api"
    assert loaded_contract.content.endpoints[0].path == "/login"

    # Task readable-id allocation keeps advancing through the shared counters.
    assert str(await repo.next_id(pid, ArtifactKind.task)) == "TASK-002"


def test_lower_case_enum_storage_and_version_append(repo, project, session):
    task = Task(
        id=ReadableId("TASK-001"), project_id=project.id, title="t", description="d",
        size=TaskSize.m, target_paths=[], depends_on=[], created_at=NOW,
    )
    task.seal()
    import asyncio

    asyncio.run(repo.save_artifact(task))
    assert session.execute(text("SELECT status FROM tasks")).scalar_one() == "pending"

    v2 = task.model_copy(update={"version": 2, "status": TaskStatus.ready})
    v2.seal()
    asyncio.run(repo.save_artifact(v2))
    latest = asyncio.run(repo.get_artifact(project.id, ReadableId("TASK-001")))
    assert latest.status == TaskStatus.ready
    v1 = asyncio.run(repo.get_artifact(project.id, ReadableId("TASK-001"), version=1))
    assert v1.status == TaskStatus.pending


def test_alembic_0005_chain_and_tables(tmp_path, monkeypatch):
    db_path = tmp_path / "chain.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{db_path}")
    tables = set(inspect(engine).get_table_names())
    assert {"architectures", "adrs", "engineering_contracts", "tasks"} <= tables
    head = engine.connect().execute(
        text("SELECT version_num FROM alembic_version")
    ).scalar_one()
    assert head == ScriptDirectory.from_config(config).get_current_head()  # newest migration, whatever it is

    command.downgrade(config, "base")
    assert not {"architectures", "adrs", "engineering_contracts", "tasks"} & set(
        inspect(engine).get_table_names()
    )
    command.upgrade(config, "head")
    engine.dispose()


# ------------------------------------------------------------------ HTTP flow

ARCH_LLM_RESPONSES = {
    "LLMRequirementsAnalysis": LLMRequirementsAnalysis(
        summary="Billing slice",
        requirements=[
            LLMRequirementSpec(
                title="Activate only after payment confirmation",
                description="Subscription activates after confirmed payment.",
                type="functional",
                priority="must",
            )
        ],
        assumptions=[],
        open_questions=[],
    ),
    "LLMArchitectureAnalysis": LLMArchitectureAnalysis(
        summary="Billing service + gateway",
        components=[
            LLMComponentSpec(
                name="billing-service",
                responsibility="manage subscriptions",
                depends_on=["db"],
                requirement_ids=["REQ-001"],
            )
        ],
        decision_summaries=["Use Stripe webhooks"],
    ),
    "LLMADRGeneration": LLMADRGeneration(
        title="Use Stripe webhooks",
        context="Payment confirmation must be trustworthy",
        decision="Listen to payment_intent.succeeded",
        alternatives=["poll Stripe"],
        consequences=["webhook endpoint needed"],
    ),
    "LLMContractGeneration": LLMContractGeneration(
        kind="api",
        endpoints=[{"method": "POST", "path": "/webhooks/stripe", "summary": "Stripe"}],
    ),
}


@pytest.fixture()
def full_client(session: Session) -> Iterator[TestClient]:
    session.add(Project(id=NIL_PROJECT, name="nil-arch", description=None))
    session.commit()
    app = create_app()

    def override_get_session() -> Iterator[Session]:
        yield session

    def arch_service() -> ArchitectureService:
        return ArchitectureService(
            llm=FakeLLM(responses=ARCH_LLM_RESPONSES),
            repo=SqlAlchemyArtifactRepository(session),
        )

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[architecture_service_dep] = arch_service
    app.dependency_overrides[requirements_capability] = lambda: FakeLLM(
        responses=ARCH_LLM_RESPONSES
    )
    with TestClient(app) as test_client:
        yield test_client


def test_full_architecture_flow_persists_end_to_end(full_client, session: Session):
    nil = str(NIL_PROJECT)
    # Requirements: analyze -> approve -> lock (real tables, ENG-014/019 seam).
    assert full_client.post(
        "/requirements/analyze", json={"project_id": nil, "brief": "Billing"}
    ).status_code == 200
    assert full_client.post(
        "/requirements/set/RSET-001/approve", json={"approved_by": "m2"}
    ).status_code == 200
    assert full_client.post(
        "/requirements/set/RSET-001/lock", json={"locked_by": "m2"}
    ).status_code == 200

    # Architecture from the locked set.
    gen = full_client.post(
        "/architecture/generate",
        json={"project_id": nil, "requirements_set_id": "RSET-001"},
    )
    assert gen.status_code == 200, gen.text
    arch_id = gen.json()["architecture"]["id"]
    assert arch_id.startswith("ARCH-")
    assert gen.json()["decisions"][0]["title"] == "Use Stripe webhooks"

    # Independent ADR recording — bumps the parent doc to a NEW version.
    rec = full_client.post(
        f"/architecture/{arch_id}/decision",
        json={"project_id": nil, "architecture_id": arch_id, "context": "retry policy"},
    )
    assert rec.status_code == 200, rec.text

    # Contract generation persists a CON row.
    con = full_client.post(
        "/architecture/contract",
        json={"project_id": nil, "kind": "api", "context": "stripe webhook"},
    )
    assert con.status_code == 200, con.text
    assert con.json()["contract"]["content"]["kind"] == "api"

    # Accept the architecture — another NEW version row.
    acc = full_client.post(
        f"/architecture/{arch_id}/accept", json={"accepted_by": "m2"}
    )
    assert acc.status_code == 200, acc.text
    assert acc.json()["architecture"]["status"] == "accepted"

    # Database truth check.
    versions = session.execute(
        text("SELECT version, status FROM architectures ORDER BY version")
    ).all()
    assert [(v.version, v.status) for v in versions] == [
        (1, "draft"),
        (2, "draft"),
        (3, "accepted"),
    ]
    assert session.execute(text("SELECT count(*) FROM adrs")).scalar_one() == 2
    assert session.execute(text("SELECT count(*) FROM engineering_contracts")).scalar_one() == 1

    # Read-back is served from the database, with both ADRs linked.
    got = full_client.get(f"/architecture/{arch_id}")
    assert got.status_code == 200
    assert len(got.json()["decisions"]) == 2


def test_every_content_hash_column_fits_a_domain_hash():
    """Regression: VARCHAR(64) rejected the 71-char "sha256:<hex>" hash on PostgreSQL.

    SQLite does not enforce VARCHAR lengths, so check the declared length directly.
    """
    from app.core.db import Base
    from app.domain.hashing import content_hash

    needed = len(content_hash({"any": "payload"}))
    columns = [t.c.content_hash for t in Base.metadata.tables.values() if "content_hash" in t.c]
    assert len(columns) >= 9
    for column in columns:
        assert column.type.length >= needed, f"{column.table.name}.content_hash is VARCHAR({column.type.length})"


def test_read_and_accept_are_scoped_to_the_real_project(full_client, session: Session):
    """Regression: GET/accept resolved every id against the nil project (404)."""
    project = Project(name="real-arch", description=None)
    session.add(project)
    session.commit()
    pid = str(project.id)
    assert full_client.post("/requirements/analyze", json={"project_id": pid, "brief": "Billing"}).status_code == 200
    assert full_client.post("/requirements/set/RSET-001/approve", json={"approved_by": "m1", "project_id": pid}).status_code == 200
    assert full_client.post("/requirements/set/RSET-001/lock", json={"locked_by": "m1", "project_id": pid}).status_code == 200
    gen = full_client.post("/architecture/generate", json={"project_id": pid, "requirements_set_id": "RSET-001"})
    assert gen.status_code == 200, gen.text
    arch_id = gen.json()["architecture"]["id"]

    got = full_client.get(f"/architecture/{arch_id}", params={"project_id": pid})
    assert got.status_code == 200, got.text
    assert got.json()["architecture"]["project_id"] == pid

    acc = full_client.post(f"/architecture/{arch_id}/accept", json={"accepted_by": "m1", "project_id": pid})
    assert acc.status_code == 200, acc.text
    assert acc.json()["architecture"]["status"] == "accepted"
