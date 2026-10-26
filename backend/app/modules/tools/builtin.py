"""First tools registered on the ToolGateway (ENG-020).

Read-only for now:

* ``repo.list_files`` / ``repo.read_file`` read the demo-target repo through
  the scoped GitHub adapter (ENG-010) at the run's pinned base commit;
* ``zetaris.run_sql`` is M2's governed query tool (ENG-022), registered
  unchanged, with its QueryEvidence kept in the call record.

Context dependencies: ``github`` (GitHubRepoClient), ``base_ref`` (commit sha
the run started from), ``zetaris`` (ZetarisClient).
"""

from pydantic import BaseModel, Field

from app.modules.tools.gateway import ToolContext, ToolGateway, ToolSpec
from app.modules.zetaris.tool import (
    TOOL_DESCRIPTION as ZETARIS_DESCRIPTION,
    TOOL_NAME as ZETARIS_TOOL,
    RunSqlInput,
    RunSqlOutput,
    run_sql_tool,
)

REPO_LIST_FILES = "repo.list_files"
REPO_READ_FILE = "repo.read_file"
READ_ONLY_TOOLS = frozenset({REPO_LIST_FILES, REPO_READ_FILE, ZETARIS_TOOL})


class ListFilesInput(BaseModel):
    prefix: str = Field(default="", description="Only return paths starting with this prefix")


class ListFilesOutput(BaseModel):
    ref: str
    paths: list[str]


class ReadFileInput(BaseModel):
    path: str = Field(min_length=1, description="Repo-relative file path")


class ReadFileOutput(BaseModel):
    path: str
    ref: str
    text: str


def _list_files(ctx: ToolContext, data: ListFilesInput) -> ListFilesOutput:
    ref = ctx.dep("base_ref")
    paths = [p for p in ctx.dep("github").list_files(ref) if p.startswith(data.prefix)]
    return ListFilesOutput(ref=ref, paths=paths)


def _read_file(ctx: ToolContext, data: ReadFileInput) -> ReadFileOutput:
    ref = ctx.dep("base_ref")
    file = ctx.dep("github").get_file(data.path, ref)
    return ReadFileOutput(path=file.path, ref=ref, text=file.text)


def _run_sql(ctx: ToolContext, data: RunSqlInput) -> RunSqlOutput:
    return run_sql_tool(data, ctx.dep("zetaris"))


def register_builtin_tools(gateway: ToolGateway) -> ToolGateway:
    gateway.register(ToolSpec(
        name=REPO_LIST_FILES,
        description="List file paths in the demo-target repository at the run's base commit",
        input_model=ListFilesInput, output_model=ListFilesOutput, handler=_list_files,
    ))
    gateway.register(ToolSpec(
        name=REPO_READ_FILE,
        description="Read one text file from the demo-target repository at the run's base commit",
        input_model=ReadFileInput, output_model=ReadFileOutput, handler=_read_file,
    ))
    gateway.register(ToolSpec(
        name=ZETARIS_TOOL, description=ZETARIS_DESCRIPTION,
        input_model=RunSqlInput, output_model=RunSqlOutput, handler=_run_sql,
    ))
    return gateway
