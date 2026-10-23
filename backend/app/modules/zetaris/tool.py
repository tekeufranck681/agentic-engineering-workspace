"""The governed ``run_sql`` tool (ENG-022).

This is the exact surface M5's ToolGateway will register: schema-validated
input, schema-validated output, read-only always, and a grounded
QueryEvidence record attached to every execution. The tool layer never
enables writes; administrative operations stay behind human approval by
design (pack stop-conditions).
"""

from pydantic import BaseModel, Field

from app.modules.zetaris.client import QueryResult, ZetarisClient
from app.modules.zetaris.evidence import QueryEvidence

TOOL_NAME = "zetaris.run_sql"
TOOL_DESCRIPTION = (
    "Run one read-only governed SQL statement against the Zetaris data "
    "virtualization layer and return rows plus auditable evidence"
)


class RunSqlInput(BaseModel):
    """Gateway-visible input schema for the tool."""

    statement: str = Field(
        min_length=1,
        description="One Lightning SQL statement; read-only, no semicolons, "
        "fully qualified <source>.<table> names",
    )
    row_limit: int | None = Field(
        default=None, ge=1, description="Optional row cap; server clamps it"
    )


class RunSqlOutput(BaseModel):
    """Gateway-visible output schema: data plus grounded evidence."""

    rows: list[list[str]]
    row_count: int
    truncated: bool
    evidence: QueryEvidence


def run_sql_tool(data: RunSqlInput, client: ZetarisClient) -> RunSqlOutput:
    """Execute one governed read query and attach its evidence record.

    Raises the typed Zetaris errors from :mod:`client` / :mod:`governance`;
    it is the gateway's job to translate them into tool-call failures.
    """
    result: QueryResult = client.run_sql(data.statement, data.row_limit)
    evidence = QueryEvidence.build(
        statement=result.statement,
        query_id=result.query_id,
        request_id=result.request_id,
        org_id=result.org_id,
        endpoint=result.endpoint,
        row_count=result.row_count,
        truncated=result.truncated,
        duration_ms=result.duration_ms,
    )
    return RunSqlOutput(
        rows=result.rows,
        row_count=result.row_count,
        truncated=result.truncated,
        evidence=evidence,
    )
