"""Sandbox tools on the ToolGateway (ENG-025).

* ``sandbox.read_file``  read a file from the run's workspace (current state);
* ``sandbox.write_file`` write a file; only paths inside the task's
  ``target_paths`` pass the gateway (write tool);
* ``sandbox.run_tests``  run pytest in the sandbox and return an objective result
  (outcome, counts, failing test ids, output tail);
* ``sandbox.diff``       every change since the base commit.

Context dependency: ``workspace`` (an open ``Workspace`` from the SandboxProvider).
"""

from pydantic import BaseModel, Field

from app.modules.sandbox.provider import ChangeSet, TestRunResult
from app.modules.tools.gateway import ToolContext, ToolGateway, ToolSpec

SANDBOX_READ_FILE = "sandbox.read_file"
SANDBOX_WRITE_FILE = "sandbox.write_file"
SANDBOX_RUN_TESTS = "sandbox.run_tests"
SANDBOX_DIFF = "sandbox.diff"
SANDBOX_TOOLS = frozenset({SANDBOX_READ_FILE, SANDBOX_WRITE_FILE, SANDBOX_RUN_TESTS, SANDBOX_DIFF})


class PathInput(BaseModel):
    path: str = Field(min_length=1, description="Repo-relative file path")


class FileText(BaseModel):
    path: str
    text: str


class WriteFileInput(BaseModel):
    path: str = Field(min_length=1, description="Repo-relative file path inside the task scope")
    text: str = Field(description="Full new file content (the file is replaced)")


class WrittenFile(BaseModel):
    path: str
    bytes: int


class RunTestsInput(BaseModel):
    selector: str | None = Field(
        default=None, description="Optional pytest target, e.g. tests/test_payment.py::test_activation"
    )


class NoInput(BaseModel):
    pass


def _read(ctx: ToolContext, data: PathInput) -> FileText:
    workspace = ctx.dep("workspace")
    return FileText(path=data.path, text=workspace.read_file(data.path))


def _write(ctx: ToolContext, data: WriteFileInput) -> WrittenFile:
    path = ctx.dep("workspace").write_file(data.path, data.text)
    return WrittenFile(path=path, bytes=len(data.text.encode()))


def _run_tests(ctx: ToolContext, data: RunTestsInput) -> TestRunResult:
    return ctx.dep("workspace").run_tests(data.selector)


def _diff(ctx: ToolContext, data: NoInput) -> ChangeSet:
    return ctx.dep("workspace").diff()


def register_sandbox_tools(gateway: ToolGateway) -> ToolGateway:
    gateway.register(ToolSpec(
        name=SANDBOX_READ_FILE, description="Read a file from the run's sandbox workspace",
        input_model=PathInput, output_model=FileText, handler=_read,
    ))
    gateway.register(ToolSpec(
        name=SANDBOX_WRITE_FILE,
        description="Replace a file in the sandbox workspace; only files in the task scope are allowed",
        input_model=WriteFileInput, output_model=WrittenFile, handler=_write,
        writes=True, write_paths=lambda d: [d.path],
    ))
    gateway.register(ToolSpec(
        name=SANDBOX_RUN_TESTS,
        description="Run pytest in the sandbox and return outcome, counts and failing test ids",
        input_model=RunTestsInput, output_model=TestRunResult, handler=_run_tests,
    ))
    gateway.register(ToolSpec(
        name=SANDBOX_DIFF, description="Show every change in the workspace since the run's base commit",
        input_model=NoInput, output_model=ChangeSet, handler=_diff,
    ))
    return gateway
