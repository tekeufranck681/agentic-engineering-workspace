"""ENG-017 publisher tests — pure planning plus mocked-HTTP execution.

Guarantees under test: plans are exact and idempotent, the datasource
password never appears in any display/report output, dry-run performs zero
write statements, and verification honestly distinguishes match / mismatch /
inconclusive.
"""

import json
import re

import httpx
import pytest
from pydantic import SecretStr

from app.modules.zetaris import read_model
from app.modules.zetaris.client import ZetarisClient
from app.modules.zetaris.config import ReadModelSettings, ZetarisSettings
from app.modules.zetaris.errors import ZetarisConfigError
from app.modules.zetaris.publisher import fetch_current_state, publish
from app.modules.zetaris.read_model import (
    TABLES,
    CurrentState,
    JdbcTarget,
)

TARGET = JdbcTarget(host="host.docker.internal", port=5433, database="aew", user="zetaris_ro")
SECRET = "super-secret-readmodel-password"


# ------------------------------------------------------------ pure planning

def test_create_datasource_template_shape_and_placeholder():
    statement = read_model.create_datasource_template(TARGET)
    assert statement.startswith("CREATE DATASOURCE aew_pg")
    assert '"org.postgresql.Driver"' in statement
    assert "jdbc:postgresql://host.docker.internal:5433/aew" in statement
    assert 'username "zetaris_ro"' in statement
    assert read_model.PASSWORD_PLACEHOLDER in statement
    assert SECRET not in statement
    assert ";" not in statement


def test_display_never_leaks_password():
    plan = read_model.build_plan(TARGET, CurrentState(datasource_exists=False))
    rendered_all = "\n".join(item.display() for item in plan)
    assert read_model.PASSWORD_PLACEHOLDER not in rendered_all
    assert "<redacted>" in rendered_all
    for item in plan:
        assert SECRET not in item.display()
        assert SECRET not in repr(item)


def test_plan_from_empty_state_is_full_and_ordered():
    plan = read_model.build_plan(TARGET, CurrentState(datasource_exists=False))
    actions = [item.action for item in plan]
    assert actions == [
        "create datasource aew_pg",
        "register table projects",
        "register table repository_bindings",
        "create governed view aew_projects",
        "create governed view aew_repository_bindings",
    ]


def test_plan_is_empty_when_everything_exists():
    current = CurrentState(
        datasource_exists=True,
        registered_objects=frozenset(
            {"projects", "repository_bindings", "aew_projects", "aew_repository_bindings"}
        ),
    )
    assert read_model.build_plan(TARGET, current) == []


def test_plan_only_adds_missing_objects():
    current = CurrentState(
        datasource_exists=True, registered_objects=frozenset({"projects"})
    )
    actions = [item.action for item in read_model.build_plan(TARGET, current)]
    assert "create datasource aew_pg" not in actions
    assert "register table projects" not in actions
    assert actions == [
        "register table repository_bindings",
        "create governed view aew_projects",
        "create governed view aew_repository_bindings",
    ]


# ------------------------------------------------------- mocked HTTP client

class FakeZetaris:
    """Stateful fake: remembers whether CREATE DATASOURCE has 'run'."""

    def __init__(self, *, count_rows: int = 3, datasource_exists: bool = False) -> None:
        self.datasource_exists = datasource_exists
        self.count_rows = count_rows
        self.sent_sql: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1.0/datasource/datasources":
            names = [{"name": "aew_pg"}] if self.datasource_exists else []
            return httpx.Response(200, json=names)
        if request.url.path == "/api/v1.0/sql-editor/sqls/run":
            sql = json.loads(request.content.decode())["sql"]
            self.sent_sql.append(sql)
            if sql.startswith("SHOW DATASOURCE TABLES"):
                objects = (
                    [["projects"], ["repository_bindings"], ["aew_projects"], ["aew_repository_bindings"]]
                    if self.datasource_exists
                    else []
                )
                return httpx.Response(200, json={"data": objects})
            if sql.startswith("COUNT_PROBE_FAIL"):
                return httpx.Response(400, text="no such object")
            if sql.startswith("SELECT COUNT(*)"):
                return httpx.Response(200, json={"data": [[str(self.count_rows)]]})
            if sql.startswith("CREATE DATASOURCE"):
                self.datasource_exists = True
                return httpx.Response(200, json={"data": []})
            if sql.startswith(("REGISTER DATASOURCE TABLE", "CREATE DATASOURCE VIEW")):
                return httpx.Response(200, json={"data": []})
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404, json={"detail": "unknown"})


def make_client(fake: FakeZetaris) -> ZetarisClient:
    settings = ZetarisSettings(
        rest_url="http://zetaris.test:8888/api/v1.0",
        org_id="1",
        api_key=SecretStr("k"),
    )
    return ZetarisClient(settings, transport=httpx.MockTransport(fake.handler))


def writes_sent(fake: FakeZetaris) -> list[str]:
    write_keywords = re.compile(r"^(CREATE|REGISTER|DROP|ALTER|INSERT|UPDATE|GRANT|DELETE)")
    return [sql for sql in fake.sent_sql if write_keywords.match(sql)]


def test_fetch_current_state_parses_inventory():
    fake = FakeZetaris(datasource_exists=True)
    with make_client(fake) as client:
        current = fetch_current_state(client, "aew_pg")
    assert current.datasource_exists is True
    assert current.registered_objects == frozenset(
        {"projects", "repository_bindings", "aew_projects", "aew_repository_bindings"}
    )


def test_dry_run_sends_no_write_statements():
    fake = FakeZetaris(datasource_exists=False)
    with make_client(fake) as client:
        report = publish(
            client, TARGET, table_counter=None, read_model_password=None, apply=False
        )
    assert report.mode == "dry_run"
    assert report.success is True
    assert len(report.planned) == 5
    assert writes_sent(fake) == []
    assert SECRET not in report.model_dump_json()


def test_apply_executes_in_order_and_verifies_counts():
    fake = FakeZetaris(datasource_exists=False, count_rows=3)
    with make_client(fake) as client:
        report = publish(
            client,
            TARGET,
            table_counter=lambda table: 3,
            read_model_password=SECRET,
            apply=True,
        )
    sent_writes = writes_sent(fake)
    assert sent_writes[0].startswith("CREATE DATASOURCE")
    assert len(sent_writes) == 5
    assert SECRET not in report.model_dump_json()
    assert report.failed_action is None
    assert report.missing_after_apply == []
    assert all(check.match is True for check in report.table_checks)
    assert report.success is True


def test_apply_requires_password():
    fake = FakeZetaris(datasource_exists=False)
    with make_client(fake) as client:
        with pytest.raises(ZetarisConfigError):
            publish(client, TARGET, table_counter=None, read_model_password=None, apply=True)
    assert writes_sent(fake) == []


def test_apply_reports_count_mismatch_honestly():
    fake = FakeZetaris(datasource_exists=True, count_rows=5)
    with make_client(fake) as client:
        report = publish(
            client,
            TARGET,
            table_counter=lambda table: 2,  # postgres says 2, zetaris says 5
            read_model_password=SECRET,
            apply=True,
        )
    assert report.success is False
    assert all(check.match is False for check in report.table_checks)


def test_apply_idempotent_when_nothing_missing():
    fake = FakeZetaris(datasource_exists=True, count_rows=0)
    with make_client(fake) as client:
        report = publish(
            client,
            TARGET,
            table_counter=lambda table: 0,
            read_model_password=SECRET,
            apply=True,
        )
    assert report.planned == []
    assert writes_sent(fake) == []
    assert report.success is True


def test_apply_stops_at_first_failed_statement():
    class FailingFake(FakeZetaris):
        def handler(self, request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1.0/sql-editor/sqls/run":
                sql = json.loads(request.content.decode())["sql"]
                if sql.startswith("CREATE DATASOURCE"):
                    return httpx.Response(400, text="connection test failed")
            return super().handler(request)

    fake = FailingFake(datasource_exists=False)
    with make_client(fake) as client:
        report = publish(
            client, TARGET, table_counter=None, read_model_password=SECRET, apply=True
        )
    assert report.success is False
    assert report.failed_action is not None
    assert "create datasource" in report.failed_action
    assert len(report.executed) == 0


# ------------------------------------------------------------- check mode

def test_check_passes_when_published_and_consistent():
    fake = FakeZetaris(datasource_exists=True, count_rows=3)
    with make_client(fake) as client:
        report = publish(
            client, TARGET, table_counter=lambda table: 3,
            read_model_password=None, apply=False, verify_only=True,
        )
    assert report.mode == "check"
    assert report.planned == []  # a check computes no plan
    assert report.success is True
    assert all(check.match is True for check in report.table_checks)
    assert writes_sent(fake) == []
    assert SECRET not in report.model_dump_json()


def test_check_needs_no_password_and_no_writes():
    fake = FakeZetaris(datasource_exists=True, count_rows=1)
    with make_client(fake) as client:
        report = publish(
            client, TARGET, table_counter=lambda table: 1,
            read_model_password=None, apply=False, verify_only=True,
        )
    assert report.success is True
    assert writes_sent(fake) == []


def test_check_flags_count_mismatch_as_stale():
    fake = FakeZetaris(datasource_exists=True, count_rows=5)
    with make_client(fake) as client:
        report = publish(
            client, TARGET, table_counter=lambda table: 2,
            read_model_password=None, apply=False, verify_only=True,
        )
    assert report.success is False
    assert all(check.match is False for check in report.table_checks)


def test_check_flags_missing_objects_as_stale():
    fake = FakeZetaris(datasource_exists=False, count_rows=0)
    with make_client(fake) as client:
        report = publish(
            client, TARGET, table_counter=lambda table: 0,
            read_model_password=None, apply=False, verify_only=True,
        )
    assert len(report.missing_after_apply) == 4
    assert report.success is False


def test_check_strict_on_unqueryable_views():
    class BlindViewsFake(FakeZetaris):
        def handler(self, request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1.0/sql-editor/sqls/run":
                sql = json.loads(request.content.decode())["sql"]
                if sql == "SELECT COUNT(*) FROM aew_pg.aew_projects":
                    return httpx.Response(400, text="no such object")
            return super().handler(request)

    fake = BlindViewsFake(datasource_exists=True, count_rows=3)
    with make_client(fake) as client:
        report = publish(
            client, TARGET, table_counter=lambda table: 3,
            read_model_password=None, apply=False, verify_only=True,
        )
    assert "view aew_projects: probe inconclusive" in report.notes
    assert report.success is False  # strict: advisory only in --apply mode


def test_check_and_apply_are_mutually_exclusive():
    fake = FakeZetaris(datasource_exists=True)
    with make_client(fake) as client:
        with pytest.raises(ValueError):
            publish(
                client, TARGET, table_counter=None,
                read_model_password=None, apply=True, verify_only=True,
            )


# --------------------------------------------------------------- settings

def test_read_model_settings_defaults_and_secret():
    settings = ReadModelSettings(password=SecretStr(SECRET))
    assert settings.host == "host.docker.internal"
    assert settings.port == 5433
    assert settings.database == "aew"
    assert settings.user == "zetaris_ro"
    assert SECRET not in repr(settings)
