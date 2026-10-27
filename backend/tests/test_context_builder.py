"""Context Builder tests (ENG-023) without live services.

The demo task's context: its locked requirement and criteria with exact
versions, the accepted architecture's tracing component and decision, the
contract, the dependency task, relevant files and tests at a pinned commit
(read through the ToolGateway's repo tools), Zetaris facts with query
evidence (through ``zetaris.run_sql``) and the project's H-MEM lesson as a
supplemental prior memory. Then the safety cases: a requirement changed after
lock, an unlocked requirement, a criterion changed since planning (all block),
Zetaris or the repository unavailable (explicitly degraded, or blocking when
facts are required), the size budget, and H-MEM down (fails closed).
"""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.acceptance_criterion import AcceptanceCriterion, Verification
from app.domain.adr import ArchitectureDecision
from app.domain.architecture import ArchitectureDoc, Component
from app.domain.base import ArtifactRef, TraceLinks
from app.domain.contract import ApiContractContent, ApiEndpoint, EngineeringContract
from app.domain.enums import ArtifactKind
from app.domain.fakes import InMemoryRepository
from app.domain.requirements import Requirement
from app.domain.requirements_set import RequirementsSet
from app.domain.task import Task
from app.main import create_app
from app.modules.context import api as context_api
from app.modules.context.builder import ContextBuilder, ContextSettings, FactQuery
from app.modules.context.errors import ContextBlockedError, ContextNotFoundError, ContextSourceUnavailableError
from app.modules.github.client import FileContent, RepoInfo
from app.modules.memory.api import get_memory_provider
from app.modules.memory.errors import MemoryUnavailableError
from app.modules.persistence.models import Project
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.tools.builtin import register_builtin_tools
from app.modules.tools.gateway import ToolGateway
from app.modules.zetaris.client import QueryResult
from app.modules.zetaris.errors import ZetarisUnavailableError
from tests.memory_fakes import LESSON, FakeMemory, make_record

PROJECT = uuid.UUID("3f2c1a9e-0000-4000-8000-0000000000c1")
HEAD = "4c1d2e3f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d"
FILES = {
    "app/billing/service.py": "class BillingService:\n    def activate(self, subscription):\n        ...\n",
    "app/billing/models.py": "class Subscription:\n    status = 'PENDING'\n",
    "app/billing/webhooks.py": "def on_payment_confirmed(event):\n    ...\n",
    "app/reporting/export.py": "def export_csv():\n    ...\n",
    "tests/test_service.py": "def test_activate():\n    ...\n",
    "tests/test_export.py": "def test_export():\n    ...\n",
    "README.md": "# demo\n",
}


class FakeGitHub:
    def __init__(self, files: dict[str, str] = FILES):
        self.files = files

    def get_repo(self) -> RepoInfo:
        return RepoInfo(full_name="acme/billing-demo", default_branch="main", private=True, html_url="https://x")

    def get_branch_sha(self, branch: str) -> str:
        assert branch == "main"
        return HEAD

    def list_files(self, ref: str) -> list[str]:
        assert ref == HEAD
        return list(self.files)

    def get_file(self, path: str, ref: str) -> FileContent:
        return FileContent(path=path, ref=ref, blob_sha=f"blob-{len(path)}", text=self.files[path])


class FakeZetaris:
    def __init__(self, error: Exception | None = None, base_sha: str = HEAD):
        self.error = error
        self.base_sha = base_sha
        self.statements: list[str] = []

    def run_sql(self, statement: str, row_limit: int | None = None) -> QueryResult:
        self.statements.append(statement)
        if self.error is not None:
            raise self.error
        if "aew_repository_bindings" in statement:
            rows = [["acme/billing-demo", "main", self.base_sha, "active", "2026-10-26T10:00:00"]]
        elif "aew_projects" in statement:
            rows = [["Billing demo", "active"]]
        else:
            rows = [["42"]]
        return QueryResult(
            rows=rows, row_count=len(rows), truncated=False, statement=statement, limit=row_limit or 20,
            query_id=f"q-{len(self.statements)}", request_id=f"r-{len(self.statements)}", org_id="7",
            endpoint="http://zetaris.test/api/v1.0/query", duration_ms=12,
        )


def ref(kind: ArtifactKind, artifact_id: str, version: int = 1) -> ArtifactRef:
    return ArtifactRef(kind=kind, id=artifact_id, version=version)


def sealed(artifact):
    artifact.seal()
    return artifact


def demo_artifacts(project: uuid.UUID = PROJECT, *, locked: bool = True) -> list:
    return [
        sealed(Requirement(id="REQ-001", project_id=project, title="Activate only after payment confirmation",
                           description="A subscription becomes ACTIVE only after the payment is confirmed.",
                           type="functional", priority="must")),
        sealed(RequirementsSet(id="RSET-001", project_id=project, summary="Subscription billing",
                               members=[ref(ArtifactKind.requirement, "REQ-001")],
                               status="locked" if locked else "approved")),
        sealed(AcceptanceCriterion(id="AC-001", project_id=project, requirement_id="REQ-001",
                                   title="Unconfirmed payment does not activate",
                                   given=["a PENDING subscription"], when=["the payment fails or is unconfirmed"],
                                   then=["the subscription stays PENDING"], priority="must",
                                   verification=Verification(kind="integration", hint="webhook replay"))),
        sealed(AcceptanceCriterion(id="AC-002", project_id=project, requirement_id="REQ-001",
                                   title="Confirmed payment activates", given=["a PENDING subscription"],
                                   when=["the payment is confirmed"], then=["the subscription is ACTIVE"],
                                   priority="must")),
        sealed(ArchitectureDoc(id="ARCH-001", project_id=project, summary="Billing service gated on confirmation",
                               components=[
                                   Component(name="BillingService", responsibility="Activates on confirmed payment",
                                             requirement_ids=["REQ-001"]),
                                   Component(name="Reporting", responsibility="Exports", requirement_ids=["REQ-009"]),
                               ],
                               decision_ids=["ADR-001"], status="accepted")),
        sealed(ArchitectureDecision(id="ADR-001", project_id=project, title="Activate on the confirmed webhook",
                                    context="Confirmation is asynchronous",
                                    decision="Activate only in the payment-confirmed webhook handler",
                                    consequences=["webhook endpoint needed"], status="accepted")),
        sealed(EngineeringContract(id="CON-001", project_id=project, content=ApiContractContent(
            endpoints=[ApiEndpoint(method="POST", path="/webhooks/payments", summary="Payment confirmation")]))),
        sealed(Task(id="TASK-001", project_id=project, title="Subscription model", description="PENDING status",
                    size="s", target_paths=["app/billing/models.py"], status="done")),
        sealed(Task(id="TASK-002", project_id=project, title="Activate subscriptions on payment confirmation",
                    description="Change BillingService so a subscription activates only on the payment-confirmed "
                                "webhook.",
                    size="m", target_paths=["app/billing/service.py"], depends_on=["TASK-001"],
                    trace=TraceLinks(requirement_ids=["REQ-001"], ac_ids=["AC-001"], contract_ids=["CON-001"]),
                    derived_from=[ref(ArtifactKind.requirement, "REQ-001"),
                                  ref(ArtifactKind.acceptance_criterion, "AC-001")])),
    ]


async def seeded(*, locked: bool = True) -> InMemoryRepository:
    repo = InMemoryRepository()
    for artifact in demo_artifacts(locked=locked):
        await repo.save_artifact(artifact)
    return repo


def builder(repo, *, github=FakeGitHub(), zetaris=None, memory=None, settings=None) -> tuple[ContextBuilder, ToolGateway]:
    tools = register_builtin_tools(ToolGateway())
    zetaris = FakeZetaris() if zetaris is None else zetaris
    memory = FakeMemory(make_record()) if memory is None else memory
    return ContextBuilder(repo, tools=tools, github=github, zetaris=zetaris or None, memory=memory,
                          settings=settings), tools


# ----------------------------------------------------------------- the demo


async def test_the_demo_task_gets_locked_criteria_files_and_facts_with_provenance():
    context_builder, tools = builder(await seeded())

    manifest = await context_builder.build(PROJECT, "TASK-002", run_id="RUN-001")

    assert [(r.pin.ref, r.locked_in) for r in manifest.requirements] == [("REQ-001@v1", "RSET-001@v1")]
    assert [c.pin.ref for c in manifest.acceptance_criteria] == ["AC-001@v1", "AC-002@v1"]
    assert manifest.acceptance_criteria[0].then == ["the subscription stays PENDING"]
    assert manifest.acceptance_criteria[0].verification == "integration: webhook replay"
    assert [c.name for c in manifest.architecture.components] == ["BillingService"]  # only what traces to REQ-001
    assert [d.pin.ref for d in manifest.decisions] == ["ADR-001@v1"]
    assert (manifest.contracts[0].pin.ref, manifest.contracts[0].kind) == ("CON-001@v1", "api")
    assert [(t.pin.ref, t.pin.status) for t in manifest.dependency_tasks] == [("TASK-001@v1", "done")]
    assert manifest.constraints == ["write scope: only app/billing/service.py"]

    assert (manifest.repository.full_name, manifest.repository.base_commit) == ("acme/billing-demo", HEAD)
    assert [(f.path, f.reason) for f in manifest.relevant_files] == [
        ("app/billing/service.py", "target path"),
        ("app/billing/webhooks.py", "path matches webhook"),
    ]
    assert [(t.path, t.reason) for t in manifest.relevant_tests] == [("tests/test_service.py", "test of a target")]
    assert manifest.relevant_files[0].excerpt.startswith("class BillingService") and manifest.relevant_files[0].tool_call_id

    binding = manifest.facts[0]
    assert (binding.name, binding.rows[0][0], binding.provenance.query_id) == ("repository binding", "acme/billing-demo", "q-1")
    assert binding.columns[2] == "base_sha" and manifest.repository.binding_base_sha == HEAD
    assert binding.provenance.tool_call_id and len(binding.provenance.statement_sha256) == 64

    assert [(m.memory_id, m.relevance, m.source) for m in manifest.prior_memories] == [("mem-1", 0.44, "run:RUN-0001")]
    assert manifest.memory_evidence["status"] == "recalled"
    assert manifest.unknowns == [] and not manifest.degraded
    assert {s.name: s.status for s in manifest.sources} == {
        "project_state": "ok", "zetaris": "ok", "repository": "ok", "memory": "ok"
    }
    assert {p.ref for p in manifest.pins} == {
        "REQ-001@v1", "AC-001@v1", "AC-002@v1", "ARCH-001@v1", "ADR-001@v1", "CON-001@v1", "TASK-001@v1", "TASK-002@v1"
    }

    calls = [(r.tool, r.status, r.run_id) for r in tools.recorder.records]
    assert calls.count(("zetaris.run_sql", "ok", "RUN-001")) == 2 and ("repo.list_files", "ok", "RUN-001") in calls
    text = manifest.render()
    assert "AC-001@v1 (REQ-001) Unconfirmed payment does not activate" in text
    assert text.rindex("Relevant lessons from earlier runs") > text.index("Relevant files:")  # lessons come last
    assert LESSON in text and manifest.chars == len(text) <= manifest.char_budget


async def test_the_same_inputs_give_the_same_fingerprint():
    repo = await seeded()
    first = await builder(repo)[0].build(PROJECT, "TASK-002")
    second = await builder(repo)[0].build(PROJECT, "TASK-002")
    assert first.fingerprint() == second.fingerprint() and first.manifest_id != second.manifest_id


async def test_caller_fact_queries_come_back_with_their_evidence():
    zetaris = FakeZetaris()
    context_builder, _ = builder(await seeded(), zetaris=zetaris)
    extra = FactQuery(name="open incidents", statement="SELECT COUNT(*) FROM ops.incidents", columns=["count"])

    manifest = await context_builder.build(PROJECT, "TASK-002", fact_queries=[extra])

    assert [(f.name, f.rows) for f in manifest.facts][-1] == ("open incidents", [["42"]])
    assert zetaris.statements[-1] == "SELECT COUNT(*) FROM ops.incidents"


async def test_an_unknown_task_is_not_found():
    with pytest.raises(ContextNotFoundError):
        await builder(await seeded())[0].build(PROJECT, "TASK-999")


# ------------------------------------------------------------- safe blocking


async def test_a_requirement_changed_after_lock_blocks():
    repo = await seeded()
    changed = (await repo.get_artifact(PROJECT, "REQ-001")).model_copy(
        update={"version": 2, "description": "A subscription becomes ACTIVE when the customer pays."}
    )
    await repo.save_artifact(sealed(changed))

    with pytest.raises(ContextBlockedError) as caught:
        await builder(repo)[0].build(PROJECT, "TASK-002")

    assert caught.value.reasons == [
        "REQ-001 changed since TASK-002 was planned (v1 then, v2 now): re-plan",
        "REQ-001 changed after it was locked (REQ-001@v1 locked in RSET-001@v1, v2 draft now): re-lock and re-plan",
    ]


async def test_an_unlocked_requirement_blocks():
    with pytest.raises(ContextBlockedError) as caught:
        await builder(await seeded(locked=False))[0].build(PROJECT, "TASK-002")
    assert caught.value.reasons == ["REQ-001 is not in a locked requirements set"]


async def test_a_criterion_changed_since_planning_blocks():
    repo = await seeded()
    changed = (await repo.get_artifact(PROJECT, "AC-001")).model_copy(update={"version": 2, "then": ["it activates"]})
    await repo.save_artifact(sealed(changed))

    with pytest.raises(ContextBlockedError, match="AC-001 changed since TASK-002 was planned \\(v1 then, v2 now\\)"):
        await builder(repo)[0].build(PROJECT, "TASK-002")


# ------------------------------------------------------------ degraded mode


async def test_zetaris_down_is_an_explicitly_degraded_context():
    zetaris = FakeZetaris(error=ZetarisUnavailableError("cannot reach zetaris at http://zetaris.test"))
    context_builder, _ = builder(await seeded(), zetaris=zetaris)

    manifest = await context_builder.build(PROJECT, "TASK-002")

    assert manifest.facts == [] and manifest.degraded
    zetaris_source = next(s for s in manifest.sources if s.name == "zetaris")
    assert zetaris_source.status == "unavailable" and "ZetarisUnavailableError" in zetaris_source.detail
    assert any(u.startswith("governed engineering facts missing: repository binding:") for u in manifest.unknowns)
    assert [c.pin.ref for c in manifest.acceptance_criteria] == ["AC-001@v1", "AC-002@v1"]  # the rest still holds


async def test_zetaris_down_blocks_when_facts_are_required():
    zetaris = FakeZetaris(error=ZetarisUnavailableError("cannot reach zetaris"))
    with pytest.raises(ContextBlockedError, match="facts are required and Zetaris failed"):
        await builder(await seeded(), zetaris=zetaris)[0].build(PROJECT, "TASK-002", require_facts=True)


async def test_without_repository_or_zetaris_the_manifest_says_so():
    context_builder = ContextBuilder(await seeded(), tools=register_builtin_tools(ToolGateway()),
                                     memory=FakeMemory(make_record()))

    manifest = await context_builder.build(PROJECT, "TASK-002")

    assert {s.name: s.status for s in manifest.sources}["repository"] == "not_configured"
    assert {s.name: s.status for s in manifest.sources}["zetaris"] == "not_configured"
    assert manifest.relevant_files == [] and manifest.facts == [] and manifest.degraded
    assert len(manifest.unknowns) == 2


async def test_a_binding_behind_the_branch_is_reported():
    context_builder, _ = builder(await seeded(), zetaris=FakeZetaris(base_sha="0" * 40))
    manifest = await context_builder.build(PROJECT, "TASK-002")
    assert manifest.unknowns == [
        f"the project's binding records base {'0' * 12}, the branch is at {HEAD[:12]}; files are read at {HEAD[:12]}"
    ]


async def test_the_context_stays_within_its_budget():
    files = {f"app/billing/payment_{i}.py": "x = 1\n" * 2_000 for i in range(12)}
    files["app/billing/service.py"] = "class BillingService: ...\n"
    context_builder, _ = builder(
        await seeded(), github=FakeGitHub(files), settings=ContextSettings(char_budget=6_000, excerpt_chars=2_000)
    )

    manifest = await context_builder.build(PROJECT, "TASK-002")

    assert manifest.chars <= manifest.char_budget
    assert manifest.relevant_files[0].path == "app/billing/service.py"  # the target is kept whole
    assert not manifest.relevant_files[0].truncated and any(f.truncated for f in manifest.relevant_files)
    assert any("more matching files left out" in u for u in manifest.unknowns)


async def test_h_mem_down_fails_closed():
    memory = FakeMemory(error=MemoryUnavailableError("cannot reach hmem-service"))
    with pytest.raises(ContextSourceUnavailableError, match="project memory \\(H-MEM\\) did not answer"):
        await builder(await seeded(), memory=memory)[0].build(PROJECT, "TASK-002")


# ----------------------------------------------------------------------- API


@pytest.fixture()
def api(session: Session) -> Iterator[TestClient]:
    session.add(Project(id=PROJECT, name="context-api", description=None))
    session.commit()
    app = create_app()

    def override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[context_api.get_github] = lambda: FakeGitHub()
    app.dependency_overrides[context_api.get_zetaris] = lambda: FakeZetaris()
    app.dependency_overrides[get_memory_provider] = lambda: FakeMemory(make_record())
    with TestClient(app) as client:
        yield client


async def seed_rows(session: Session, *artifacts) -> None:
    repo = SqlAlchemyArtifactRepository(session)
    for artifact in artifacts:
        await repo.save_artifact(artifact)


async def test_the_api_builds_the_demo_context_from_the_database(api, session):
    await seed_rows(session, *demo_artifacts())

    response = api.post(f"/projects/{PROJECT}/context", json={"task_id": "TASK-002", "run_id": "RUN-001"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert [c["pin"]["id"] for c in body["acceptance_criteria"]] == ["AC-001", "AC-002"]
    assert body["facts"][0]["provenance"]["query_id"] == "q-1"
    assert body["repository"]["base_commit"] == HEAD and body["prior_memories"][0]["memory_id"] == "mem-1"


async def test_the_api_answers_404_and_409_with_reasons(api, session):
    artifacts = demo_artifacts()
    changed = artifacts[0].model_copy(update={"version": 2, "description": "changed"})
    await seed_rows(session, *artifacts, sealed(changed))

    missing = api.post(f"/projects/{PROJECT}/context", json={"task_id": "TASK-999"})
    blocked = api.post(f"/projects/{PROJECT}/context", json={"task_id": "TASK-002"})
    no_project = api.post(f"/projects/{uuid.uuid4()}/context", json={"task_id": "TASK-002"})

    assert (missing.status_code, missing.json()["error"]["kind"]) == (404, "context_task_not_found")
    assert blocked.status_code == 409 and blocked.json()["error"]["reasons"][0].startswith("REQ-001 changed")
    assert no_project.status_code == 404
