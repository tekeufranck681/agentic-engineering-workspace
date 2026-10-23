"""Grounded query evidence (ENG-022).

Every governed query produces one of these records: enough to prove later —
in run evidence (M2 ENG-037) and sponsor proof (ENG-057) — that a specific
statement ran against the real instance, under a specific organisation, at a
specific time, and returned a specific number of rows. Secrets are never part
of the record.
"""

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class QueryEvidence(BaseModel):
    """Auditable record of one executed governed query."""

    statement: str = Field(description="The exact statement that was executed")
    statement_sha256: str = Field(description="SHA-256 of the statement text")
    query_id: str = Field(description="queryId sent with the request")
    request_id: str = Field(description="X-Request-ID sent with the request")
    org_id: str = Field(description="Zetaris organisation the query ran under")
    endpoint: str = Field(description="Absolute URL of the query endpoint used")
    row_count: int = Field(ge=0)
    truncated: bool = Field(
        description="True when the result hit the row limit and may be partial"
    )
    duration_ms: int = Field(ge=0)
    executed_at: datetime

    @classmethod
    def build(
        cls,
        *,
        statement: str,
        query_id: str,
        request_id: str,
        org_id: str,
        endpoint: str,
        row_count: int,
        truncated: bool,
        duration_ms: int,
    ) -> "QueryEvidence":
        return cls(
            statement=statement,
            statement_sha256=hashlib.sha256(statement.encode("utf-8")).hexdigest(),
            query_id=query_id,
            request_id=request_id,
            org_id=org_id,
            endpoint=endpoint,
            row_count=row_count,
            truncated=truncated,
            duration_ms=duration_ms,
            executed_at=datetime.now(timezone.utc),
        )
