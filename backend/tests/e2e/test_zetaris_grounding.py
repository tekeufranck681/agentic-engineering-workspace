"""ENG-047 end-to-end Zetaris grounding across the agent workflow.

The acceptance chain the sponsor judge walks is::

    product record (Postgres)
        -> governed Zetaris views (publisher --check proves freshness)
        -> zetaris.run_sql tool calls with real SQL and results
        -> EngineeringFact + FactProvenance in the context manifest
        -> the rendered agent prompt that actually reaches the model
        -> the context.built event of a full agent run

Two layers live in this one file:

* deterministic chain tests (always collected, no network): a real product
  database row through the SQLAlchemy models (SQLite in tests, Postgres in
  production against the same metadata), the real read-model publisher in
  --check mode over a mocked Zetaris REST API, the real context builder
  driving ``zetaris.run_sql`` through the tool gateway, and a full
  ``AgentRun`` graph. Also covers the two safety semantics ENG-047 requires:
  honest fail-closed behaviour (no fabricated fallback rows) and stale read
  model reporting.
* one live, read-only test gated on ``ZETARIS_LIVE=1``. It runs on the
  operator host where the Postgres-backed read model and the Zetaris
  instance exist; the build sandbox cannot reach that network. When
  ``ZETARIS_GROUNDING_OUT`` is set it writes a sanitized evidence JSON
  (identifiers and counts, never rows, credentials or tokens).
"""

import json
import os
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from pydantic import SecretStr

from app.domain.enums import RunStatus
from app.modules.context.errors import ContextBlockedError
from app.modules.persistence.models import BindingStatus, Project, RepositoryBinding
from app.modules.persistence.repository import bind_repository, create_project
from app.modules.persistence.run_models import RunEventRow
from app.modules.persistence.schemas import ProjectCreate, RepositoryBindingCreate
from app.modules.tools.builtin import ZETARIS_TOOL
from app.modules.zetaris.client import QueryResult, ZetarisClient, ZetarisSettings
from app.modules.zetaris.errors import ZetarisError, ZetarisUnavailableError
from app.modules.zetaris.publisher import publish

from tests.test_context_builder import PROJECT, FakeZetaris as ContextFakeZetaris, builder, seeded
from tests.test_implementation_capability import workspace  # noqa: F401  (fixture)
from tests.test_run_graph import RIGHT, agent, make_delivery, prepare
from tests.test_zetaris_publisher import TARGET, FakeZetaris as HttpFakeZetaris, make_client

# The governed, read-only statements the builder issues (kept in lockstep with
# app.modules.context.builder._read_facts; the chain test asserts the builder
# emits exactly these strings, so drift on either side fails that test).
BINDING_SQL = (
    "SELECT full_name, default_branch, base_sha, status, bound_at "
    "FROM aew_pg.aew_repository_bindings "
    "WHERE project_id = '{project_id}' AND status = 'active'"
)
PROJECT_SQL = "SELECT name, status FROM aew_pg.aew_projects WHERE id = '{project_id}'"

# Distinct from the workspace base commit on purpose: it proves the value the
# agent is grounded on came from the governed view, not from the GitHub client.
GROUNDED_SHA = "0123456789abcdef0123456789abcdef01234567"
ORG_ID = "7"


class PersistedRowZetaris(ContextFakeZetaris):
    """Context-level fake serving rows that mirror the persisted product row.

    The test reads the real SQLite row back and passes its values in, so the
    grounding assertions compare what the product stored with what the agent
    would read through Zetaris rather than against hard-coded fixtures.
    """

    def __init__(self, *, project_name: str, full_name: str, branch: str, base_sha: str) -> None:
        super().__init__(base_sha=base_sha)
        self._project_name = project_name
        self._full_name = full_name
        self._branch = branch

    def run_sql(self, statement: str, row_limit: int | None = None) -> QueryResult:
        self.statements.append(statement)
        if self.error is not None:
            raise self.error
        if "aew_repository_bindings" in statement:
            rows = [[self._full_name, self._branch, self.base_sha, "active", "2026-10-27T09:00:00"]]
        elif "aew_projects" in statement:
            rows = [[self._project_name, "active"]]
        else:
            rows = []
        return QueryResult(
            rows=rows, row_count=len(rows), truncated=False, statement=statement,
            limit=row_limit or 20, query_id=f"q-{len(self.statements)}",
            request_id=f"r-{len(self.statements)}", org_id=ORG_ID,
            endpoint="http://zetaris.test/api/v1.0/query", duration_ms=11,
        )


def _seed_product_record(session) -> tuple[Project, RepositoryBinding]:
    """Stage 1 of the chain: the real engineering record in the product store."""
    project = create_project(session, ProjectCreate(name="ENG-047 grounding demo",
                                                    description="Zetaris grounding e2e"))
    binding = bind_repository(session, project.id, RepositoryBindingCreate(
        owner="zetaris-e2e", name="grounding-chain", default_branch="main",
        base_sha=GROUNDED_SHA, html_url="https://github.example/zetaris-e2e/grounding-chain",
    ))
    assert binding.status == BindingStatus.ACTIVE
    return project, binding


def _pg_counter(session):
    def count(table: str) -> int:
        model = Project if table == "projects" else RepositoryBinding
        return session.query(model).count()

    return count


# ------------------------------------------- deterministic, always-collected


async def test_product_record_to_agent_prompt_full_grounding_chain(session):
    project, binding = _seed_product_record(session)
    # Read the product row back: the governed view must answer with these values.
    persisted = session.get(RepositoryBinding, binding.id)
    project_row = session.get(Project, project.id)

    # Stage 2: publisher --check over a mocked Zetaris REST API proves the
    # governed views exist and are fresh, using the real Postgres-side counts.
    http_fake = HttpFakeZetaris(datasource_exists=True, count_rows=1)
    with make_client(http_fake) as client:
        report = publish(client, TARGET, table_counter=_pg_counter(session),
                         read_model_password=None, apply=False, verify_only=True)
    assert report.mode == "check" and report.success is True
    assert report.planned == [] and all(check.match is True for check in report.table_checks)
    assert "api_key" not in report.model_dump_json()  # reports are secret-free

    # Stages 3-5: builder -> zetaris.run_sql gateway calls -> manifest -> prompt.
    zetaris = PersistedRowZetaris(
        project_name=project_row.name, full_name=persisted.full_name,
        branch=persisted.default_branch, base_sha=persisted.base_sha,
    )
    context_builder, gateway = builder(await seeded(), zetaris=zetaris)
    manifest = await context_builder.build(PROJECT, "TASK-002", run_id="RUN-0471")

    # The exact SQL the tool ran: governed, qualified, read-only, project scoped.
    assert zetaris.statements == [
        BINDING_SQL.format(project_id=PROJECT),
        PROJECT_SQL.format(project_id=PROJECT),
    ]
    assert all(sql.startswith("SELECT ") and "aew_pg.aew_" in sql for sql in zetaris.statements)

    facts = {fact.name: fact for fact in manifest.facts}
    assert set(facts) == {"repository binding", "project"}

    binding_fact = facts["repository binding"]
    assert binding_fact.rows[0][0] == persisted.full_name
    assert binding_fact.rows[0][2] == GROUNDED_SHA
    project_fact = facts["project"]
    assert project_fact.rows[0][0] == project_row.name

    # Every fact carries full sponsor provenance, including a real statement hash.
    for fact in manifest.facts:
        provenance = fact.provenance
        uuid.UUID(provenance.tool_call_id)
        assert provenance.query_id.startswith("q-") and provenance.request_id.startswith("r-")
        assert len(provenance.statement_sha256) == 64
        assert provenance.org_id == ORG_ID and provenance.executed_at and provenance.truncated is False

    # The tool gateway recorded both Zetaris calls against this run, status ok
    # (the same gateway also carries the GitHub file tools, hence the filter).
    records = [r for r in gateway.recorder.records
               if r.run_id == "RUN-0471" and r.tool == ZETARIS_TOOL]
    assert len(records) == 2
    assert all(r.status == "ok" for r in records)
    assert all(r.input["statement"].startswith("SELECT ") for r in records)

    # The rendered prompt the model actually receives carries the fact and its
    # query id, so agent output is traceable back to the governed SQL.
    rendered = manifest.render()
    assert "Governed engineering facts (Zetaris):" in rendered
    assert persisted.full_name in rendered and GROUNDED_SHA in rendered
    assert f"(query {binding_fact.provenance.query_id})" in rendered

    # The builder refreshes repository.full_name from the live GitHub client,
    # but the governed pin survives as binding_base_sha and inside the fact row:
    # that sha is what keeps file reads anchored to the branch Zetaris recorded.
    assert manifest.repository.binding_base_sha == GROUNDED_SHA
    assert binding_fact.rows[0][0] == persisted.full_name
    source = next(s for s in manifest.sources if s.name == "zetaris")
    assert source.status == "ok" and not manifest.degraded
    # The deliberately distinct grounded sha honestly surfaces as a drift
    # unknown (a grounding signal, not a failure) — never a missing-facts one.
    assert len(manifest.unknowns) == 1 and "binding records base" in manifest.unknowns[0]
    assert not any("governed engineering facts missing" in u for u in manifest.unknowns)


async def test_agent_run_carries_zetaris_grounding_into_context_event(
    session, workspace, tmp_path
):
    repo, runs, run, context_builder, implementer, store, _provider = await prepare(
        session, workspace, RIGHT
    )
    delivery, _api = make_delivery(session, tmp_path)
    run_agent = agent(repo, runs, run, context_builder, implementer, store, workspace,
                      delivery=delivery)

    outcome = await run_agent.execute()

    assert outcome.status == RunStatus.succeeded
    facts = run_agent.manifest.facts
    assert {fact.name for fact in facts} == {"repository binding", "project"}
    assert all(fact.provenance.query_id and fact.provenance.tool_call_id for fact in facts)
    assert "acme/billing-demo" in run_agent.manifest.render()

    event = (
        session.query(RunEventRow)
        .filter_by(run_id=run.id, event_type="context.built")
        .one()
    )
    assert event.payload["degraded"] is False
    assert event.payload["manifest_id"] == run_agent.manifest.manifest_id
    # This harness's workspace commit intentionally differs from the seeded
    # binding sha, so the builder honestly records that one drift unknown; what
    # must not happen is a missing-facts unknown or a degraded Zetaris source.
    assert not any("governed engineering facts missing" in u for u in event.payload["unknowns"])


async def test_zetaris_outage_is_degraded_without_fabricated_facts():
    broken = ContextFakeZetaris(error=ZetarisUnavailableError("connection refused"))
    context_builder, gateway = builder(await seeded(), zetaris=broken)

    manifest = await context_builder.build(PROJECT, "TASK-002", run_id="RUN-0472")

    # No fallback rows are invented: the agent is told explicitly what it lacks.
    assert manifest.facts == []
    source = next(s for s in manifest.sources if s.name == "zetaris")
    assert source.status == "unavailable"
    assert manifest.degraded and manifest.unknowns
    assert "Governed engineering facts" not in manifest.render()
    failed_calls = [r for r in gateway.recorder.records
                    if r.run_id == "RUN-0472" and r.tool == ZETARIS_TOOL]
    assert len(failed_calls) == 2 and all(r.status == "error" for r in failed_calls)

    # When facts are mandatory the run must block rather than proceed ungrounded.
    with pytest.raises(ContextBlockedError):
        await context_builder.build(PROJECT, "TASK-002", run_id="RUN-0473",
                                    require_facts=True)


def test_stale_read_model_mismatch_is_reported_not_claimed_fresh(session):
    _seed_product_record(session)
    # Zetaris answers but its view counts disagree with the product database.
    http_fake = HttpFakeZetaris(datasource_exists=True, count_rows=5)
    with make_client(http_fake) as client:
        report = publish(client, TARGET, table_counter=_pg_counter(session),
                         read_model_password=None, apply=False, verify_only=True)

    assert report.mode == "check" and report.success is False
    assert report.planned == []  # a check never plans or writes
    assert report.table_checks and all(check.match is False for check in report.table_checks)
    for check in report.table_checks:
        assert check.postgres_count != check.zetaris_count


def test_zetaris_http_failure_is_honest_and_keeps_secrets_out_of_reports():
    secret = "eng047-secret-token-must-never-appear"
    settings = ZetarisSettings(
        rest_url="http://zetaris.test:8888/api/v1.0", org_id="1", api_key=SecretStr(secret),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="Bad Gateway")

    # A dead instance raises (the publisher never reports success it did not
    # observe); the error text must not carry the bearer credential.
    with (
        ZetarisClient(settings, transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ZetarisError) as exc_info,
    ):
        publish(client, TARGET, table_counter=lambda table: 1,
                read_model_password=None, apply=False, verify_only=True)

    assert secret not in str(exc_info.value)
    assert settings.api_key.get_secret_value() not in str(exc_info.value)


# ------------------------------------------------------------- live, gated


LIVE_SKIP = pytest.mark.skipif(
    os.environ.get("ZETARIS_LIVE") != "1",
    reason="operator host only: real Zetaris REST API and published read model (ZETARIS_LIVE=1)",
)


@LIVE_SKIP
def test_live_zetaris_grounds_a_real_project_record():
    """Read-only live proof. Prerequisites (see docs/evidence/zetaris-agent-proof-2026-10-27.md):

    * ZETARIS_REST_URL / ZETARIS_ORG_ID / ZETARIS_API_KEY point at a reachable
      instance on which the read-model publisher has run successfully;
    * ZETARIS_TEST_PROJECT_ID is a project that has an ACTIVE repository
      binding in the product database and a row in the governed views.
    """
    settings = ZetarisSettings.from_env()
    project_id = os.environ.get("ZETARIS_TEST_PROJECT_ID")
    if not project_id:
        pytest.skip("set ZETARIS_TEST_PROJECT_ID to a project with a published active binding")

    queries = (
        ("repository binding", BINDING_SQL.format(project_id=project_id),
         ["full_name", "default_branch", "base_sha", "status", "bound_at"]),
        ("project", PROJECT_SQL.format(project_id=project_id), ["name", "status"]),
    )
    summary = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "rest_url": settings.rest_url,
        "org_id": settings.org_id,
        "queries": [],
    }
    with ZetarisClient(settings) as client:
        for name, statement, columns in queries:
            result = client.run_sql(statement)
            assert result.row_count >= 1, f"{name}: governed view returned no rows"
            assert result.query_id and result.request_id
            assert result.org_id == settings.org_id
            summary["queries"].append({
                "name": name,
                "statement": statement,
                "columns": columns,
                "query_id": result.query_id,
                "request_id": result.request_id,
                "row_count": result.row_count,
                "truncated": result.truncated,
                "duration_ms": result.duration_ms,
            })

    out_path = os.environ.get("ZETARIS_GROUNDING_OUT")
    if out_path:
        with open(out_path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)
    assert len(summary["queries"]) == 2
