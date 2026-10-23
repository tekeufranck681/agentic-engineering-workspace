"""Zetaris client tests against a mocked HTTP transport — no live instance.

Faithfulness checks: exact request path, headers, and JSON body as documented
in the Zetaris getting-started material, plus typed error mapping and the
grounded evidence produced by the tool layer.
"""

import json
import uuid
import hashlib

import httpx
import pytest
from pydantic import SecretStr

from app.modules.zetaris.client import ZetarisClient
from app.modules.zetaris.config import ZetarisSettings
from app.modules.zetaris.errors import (
    StatementRejectedError,
    ZetarisAuthError,
    ZetarisConfigError,
    ZetarisRequestError,
    ZetarisUnavailableError,
)
from app.modules.zetaris.tool import RunSqlInput, run_sql_tool

ORG_ID = "42"
API_KEY = "test-key"


def make_settings(**overrides) -> ZetarisSettings:
    values = {
        "rest_url": "http://zetaris.test:8888/api/v1.0",
        "org_id": ORG_ID,
        "api_key": SecretStr(API_KEY),
    }
    values.update(overrides)
    return ZetarisSettings(**values)


def make_client(handler, **settings_overrides) -> ZetarisClient:
    transport = httpx.MockTransport(handler)
    return ZetarisClient(make_settings(**settings_overrides), transport=transport)


def ok_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/v1.0/datasource/datasources":
        return httpx.Response(200, json=[{"name": "NY_TAXI"}, {"name": "TPCDS_DB"}])
    if request.url.path == "/api/v1.0/sql-editor/sqls/run":
        body = json.loads(request.content.decode())
        assert body["source"] == "SqlEditor"
        assert body["limit"] == 5
        uuid.UUID(body["queryId"])  # must be a real UUID
        return httpx.Response(
            200, json={"data": [["1", "Alice"], ["2", "Bob"]]}
        )
    return httpx.Response(404, json={"detail": "unknown path"})


def test_run_sql_sends_documented_request_and_parses_rows():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content.decode())
        return ok_handler(request)

    with make_client(handler) as client:
        result = client.run_sql("SELECT * FROM NY_TAXI.customers", row_limit=5)

    assert captured["headers"]["authorization"] == f"Bearer {API_KEY}"
    assert captured["headers"]["x-org-id"] == ORG_ID
    uuid.UUID(captured["headers"]["x-request-id"])
    assert captured["body"]["sql"] == "SELECT * FROM NY_TAXI.customers"

    assert result.rows == [["1", "Alice"], ["2", "Bob"]]
    assert result.row_count == 2
    assert result.truncated is False
    assert result.org_id == ORG_ID
    assert result.endpoint == "http://zetaris.test:8888/api/v1.0/sql-editor/sqls/run"
    assert result.duration_ms >= 0


def test_run_sql_returns_empty_rows_on_dict_without_data():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": "statement executed"})

    with make_client(handler) as client:
        result = client.run_sql("SHOW LIGHTNING DATABASES")
    assert result.rows == [] and result.row_count == 0


def test_run_sql_marks_truncated_when_limit_hit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [["1"], ["2"]]})

    with make_client(handler) as client:
        result = client.run_sql("SELECT 1", row_limit=2)
    assert result.truncated is True


def test_governance_rejects_writes_before_network():
    def handler(request: httpx.Request) -> httpx.Response:  # must never be hit
        raise AssertionError("network must not be called for rejected statements")

    with make_client(handler) as client:
        with pytest.raises(StatementRejectedError):
            client.run_sql("DROP LIGHTNING DATABASE x")


def test_401_maps_to_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "bad key"})

    with make_client(handler) as client:
        with pytest.raises(ZetarisAuthError):
            client.run_sql("SELECT 1")


def test_400_maps_to_request_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad org")

    with make_client(handler) as client:
        with pytest.raises(ZetarisRequestError):
            client.run_sql("SELECT 1")


def test_timeout_maps_to_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("boom", request=request)

    with make_client(handler) as client:
        with pytest.raises(ZetarisUnavailableError):
            client.run_sql("SELECT 1")


def test_list_datasources_supports_list_and_dict_payloads():
    with make_client(ok_handler) as client:
        assert client.list_datasources() == ["NY_TAXI", "TPCDS_DB"]

    def dict_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"name": "crm_pg"}]})

    with make_client(dict_handler) as client:
        assert client.list_datasources() == ["crm_pg"]


def test_settings_require_numeric_org_and_key():
    with pytest.raises(Exception):
        make_settings(org_id="abc")
    with pytest.raises(ZetarisConfigError):
        make_settings(org_id=None).require_credentials()
    with pytest.raises(ZetarisConfigError):
        make_settings(api_key=None).require_credentials()


def test_api_key_never_appears_in_repr():
    settings = make_settings()
    assert API_KEY not in repr(settings)
    assert API_KEY not in str(settings)


def test_tool_executes_and_attaches_grounded_evidence():
    with make_client(ok_handler) as client:
        output = run_sql_tool(
            RunSqlInput(statement="SELECT * FROM NY_TAXI.customers", row_limit=5), client
        )

    assert output.rows == [["1", "Alice"], ["2", "Bob"]]
    assert output.row_count == 2

    evidence = output.evidence
    assert evidence.org_id == ORG_ID
    assert evidence.statement == "SELECT * FROM NY_TAXI.customers"
    assert evidence.statement_sha256 == hashlib.sha256(
        b"SELECT * FROM NY_TAXI.customers"
    ).hexdigest()
    uuid.UUID(evidence.query_id)
    uuid.UUID(evidence.request_id)
    assert evidence.endpoint.endswith("/api/v1.0/sql-editor/sqls/run")
    assert evidence.row_count == 2 and evidence.truncated is False
    assert evidence.duration_ms >= 0
    assert API_KEY not in evidence.model_dump_json()
