"""ENG-020 ToolGateway: typed, scoped and recorded calls. No network."""

from uuid import uuid4

import pytest
from pydantic import BaseModel

from app.domain.enums import TaskSize
from app.domain.task import Task
from app.modules.github.client import FileContent, GitHubScopeError
from app.modules.tools.builtin import READ_ONLY_TOOLS, register_builtin_tools
from app.modules.tools.gateway import ToolContext, ToolGateway, ToolScope, ToolSpec
from app.modules.zetaris.client import QueryResult

BASE = "c" * 40


def make_task(paths=("src/payment.py", "tests/")) -> Task:
    return Task(id="TASK-001", project_id=uuid4(), title="Fix activation", description="d",
                size=TaskSize.s, target_paths=list(paths))


class FakeGitHub:
    def __init__(self):
        self.calls = []

    def list_files(self, ref):
        self.calls.append(("list", ref))
        return ["README.md", "src/payment.py", "tests/test_payment.py"]

    def get_file(self, path, ref):
        self.calls.append(("read", path, ref))
        if path.startswith(".git"):
            raise GitHubScopeError(f"path is protected: {path!r}")
        return FileContent(path=path, ref=ref, blob_sha="b" * 40, text="def activate(): ...\n")


class FakeZetaris:
    def run_sql(self, statement, row_limit):
        return QueryResult(rows=[["REQ-014", "locked"]], row_count=1, statement=statement, limit=row_limit or 100,
                           query_id="q-1", request_id="r-1", org_id="1", endpoint="http://z/api/v1.0/query",
                           duration_ms=12)


class WriteInput(BaseModel):
    path: str
    text: str


class WriteOutput(BaseModel):
    path: str


def write_handler(ctx, data):
    ctx.dep("written").append(data.path)
    return WriteOutput(path=data.path)


WRITE_SPEC = ToolSpec(name="test.write", description="test-only write tool", input_model=WriteInput,
                      output_model=WriteOutput, handler=write_handler, writes=True,
                      write_paths=lambda d: [d.path])


@pytest.fixture()
def gateway():
    gw = register_builtin_tools(ToolGateway())
    gw.register(WRITE_SPEC)
    return gw


def ctx_for(scope=None, **deps):
    scope = scope or ToolScope.for_task("RUN-001", make_task(), set(READ_ONLY_TOOLS) | {"test.write"})
    base = {"github": FakeGitHub(), "base_ref": BASE, "zetaris": FakeZetaris(), "written": []}
    return ToolContext(scope, **{**base, **deps})


def test_read_tools_use_the_pinned_base_commit(gateway):
    ctx = ctx_for()
    listed = gateway.call(ctx, "repo.list_files", {"prefix": "src/"})
    assert listed.ok and listed.output == {"ref": BASE, "paths": ["src/payment.py"]}
    read = gateway.call(ctx, "repo.read_file", {"path": "src/payment.py"})
    assert read.ok and read.output["ref"] == BASE
    assert ctx.dep("github").calls[-1] == ("read", "src/payment.py", BASE)


def test_zetaris_tool_is_registered_unchanged_with_evidence(gateway):
    result = gateway.call(ctx_for(), "zetaris.run_sql", {"statement": "SELECT id, status FROM aew_pg.requirements"})
    assert result.ok
    assert result.output["evidence"]["query_id"] == "q-1"
    record = gateway.recorder.records[-1]
    assert record.output["evidence"]["statement_sha256"]


def test_every_call_is_recorded_including_rejections(gateway):
    ctx = ctx_for()
    gateway.call(ctx, "repo.list_files", {})
    gateway.call(ctx, "nope.tool", {})
    gateway.call(ctx, "repo.read_file", {})
    statuses = [(r.tool, r.status, r.run_id, r.task_id) for r in gateway.recorder.records]
    assert statuses == [
        ("repo.list_files", "ok", "RUN-001", "TASK-001"),
        ("nope.tool", "rejected", "RUN-001", "TASK-001"),
        ("repo.read_file", "rejected", "RUN-001", "TASK-001"),
    ]


def test_tool_not_in_scope_is_rejected_and_handler_not_called(gateway):
    scope = ToolScope.for_task("RUN-002", make_task(), {"repo.list_files"})
    ctx = ctx_for(scope)
    result = gateway.call(ctx, "repo.read_file", {"path": "src/payment.py"})
    assert result.status == "rejected" and "not allowed" in result.error
    assert ctx.dep("github").calls == []


def test_invalid_input_is_rejected(gateway):
    result = gateway.call(ctx_for(), "zetaris.run_sql", {"statement": "", "row_limit": -3})
    assert result.status == "rejected" and result.error.startswith("invalid input")


def test_call_budget(gateway):
    scope = ToolScope.for_task("RUN-003", make_task(), set(READ_ONLY_TOOLS), max_calls=2)
    ctx = ctx_for(scope)
    assert gateway.call(ctx, "repo.list_files", {}).ok
    assert gateway.call(ctx, "repo.list_files", {}).ok
    third = gateway.call(ctx, "repo.list_files", {})
    assert third.status == "rejected" and "budget" in third.error


@pytest.mark.parametrize("path,allowed", [
    ("src/payment.py", True),
    ("tests/test_payment.py", True),
    ("tests/sub/x.py", True),
    ("src/other.py", False),
    ("src/payment.py.bak", False),
    ("tests/../src/other.py", False),
    ("testsX/x.py", False),
    ("README.md", False),
])
def test_write_tools_are_limited_to_task_target_paths(gateway, path, allowed):
    ctx = ctx_for()
    result = gateway.call(ctx, "test.write", {"path": path, "text": "x"})
    assert result.ok is allowed
    assert (path in ctx.dep("written")) is allowed
    if not allowed:
        assert "outside the task scope" in result.error


def test_adapter_errors_become_error_results(gateway):
    result = gateway.call(ctx_for(), "repo.read_file", {"path": ".git/config"})
    assert result.status == "error" and "GitHubScopeError" in result.error


def test_missing_dependency_is_an_error_result(gateway):
    result = gateway.call(ctx_for(zetaris=None), "zetaris.run_sql", {"statement": "SELECT 1 FROM a.b"})
    assert result.status == "error" and "zetaris is not available" in result.error


def test_invalid_handler_output_is_caught():
    gw = ToolGateway()
    gw.register(ToolSpec(name="bad", description="", input_model=WriteInput, output_model=WriteOutput,
                         handler=lambda ctx, d: {"wrong": 1}))
    scope = ToolScope(run_id="RUN-001", task_id="TASK-001", allowed_tools=frozenset({"bad"}))
    result = gw.call(ToolContext(scope), "bad", {"path": "a", "text": "b"})
    assert result.status == "error" and "invalid output" in result.error


def test_large_outputs_are_bounded_in_records(gateway):
    big = FakeGitHub()
    big.get_file = lambda path, ref: FileContent(path=path, ref=ref, blob_sha="b" * 40, text="x" * 50_000)
    result = gateway.call(ctx_for(github=big), "repo.read_file", {"path": "src/payment.py"})
    assert result.ok and len(result.output["text"]) == 50_000  # model sees the full file
    assert gateway.recorder.records[-1].output["_truncated"] is True  # record stays small


def test_registration_rules():
    gw = register_builtin_tools(ToolGateway())
    with pytest.raises(ValueError):
        register_builtin_tools(gw)
    with pytest.raises(ValueError):
        gw.register(ToolSpec(name="w", description="", input_model=WriteInput, output_model=WriteOutput,
                             handler=write_handler, writes=True))


def test_model_only_sees_schemas_of_allowed_tools(gateway):
    scope = ToolScope.for_task("RUN-004", make_task(), {"repo.read_file"})
    schemas = gateway.schemas_for(scope)
    assert [s["name"] for s in schemas] == ["repo.read_file"]
    assert schemas[0]["parameters"]["required"] == ["path"]


def test_scope_ids_follow_eng004_format():
    with pytest.raises(ValueError):
        ToolScope(run_id="run-1", task_id="TASK-001", allowed_tools=frozenset())
