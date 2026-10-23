"""Minimal, faithful client for the Zetaris direct REST API.

Request mechanics follow the official getting-started material:

* every request carries ``Authorization: Bearer <api key>``, ``X-Org-ID`` and
  a fresh UUID ``X-Request-ID``;
* queries are ``POST {base}/sql-editor/sqls/run`` with a body of
  ``queryId`` / ``sql`` / ``source`` / ``limit``;
* rows come back under the ``data`` key with all values as strings;
* datasource inventory is ``GET {base}/datasource/datasources``.

The client never logs or stores the API key, validates statements through the
governance layer before any network call, and maps failures to typed errors
so upper layers can distinguish refusal, auth, bad requests and outages.
"""

import time
import uuid

import httpx
from pydantic import BaseModel, Field

from app.modules.zetaris import governance
from app.modules.zetaris.config import ZetarisSettings
from app.modules.zetaris.errors import (
    ZetarisAuthError,
    ZetarisRequestError,
    ZetarisUnavailableError,
)

DATASOURCES_PATH = "/datasource/datasources"
RUN_SQL_PATH = "/sql-editor/sqls/run"
QUERY_SOURCE = "SqlEditor"
MAX_ERROR_BODY = 200


class QueryResult(BaseModel):
    """One executed query: rows plus the identifiers needed for evidence."""

    rows: list[list[str]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    statement: str
    limit: int
    query_id: str
    request_id: str
    org_id: str
    endpoint: str
    duration_ms: int


class ZetarisClient:
    """Synchronous client for the direct Zetaris REST API (/api/v1.0)."""

    def __init__(
        self,
        settings: ZetarisSettings,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        settings.require_credentials()
        self._settings = settings
        self._base = settings.rest_url.removesuffix("/")
        self._http = httpx.Client(
            base_url=self._base,
            timeout=httpx.Timeout(settings.query_timeout_seconds),
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "ZetarisClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------ HTTP

    def _request(
        self, method: str, path: str, json_body: dict | None = None
    ) -> tuple[object, str]:
        """One authenticated request. Returns (decoded JSON, request_id)."""
        request_id = str(uuid.uuid4())
        headers = {
            "Authorization": f"Bearer {self._settings.bearer_token()}",
            "X-Org-ID": self._settings.org_id or "",
            "X-Request-ID": request_id,
            "Content-Type": "application/json",
        }
        try:
            response = self._http.request(method, path, headers=headers, json=json_body)
        except httpx.TimeoutException as exc:
            raise ZetarisUnavailableError(
                f"zetaris did not answer within {self._settings.query_timeout_seconds}s"
            ) from exc
        except httpx.TransportError as exc:
            raise ZetarisUnavailableError(
                f"cannot reach zetaris at {self._base}: {exc}"
            ) from exc

        if response.status_code in (401, 403):
            raise ZetarisAuthError(
                f"zetaris refused the API key (HTTP {response.status_code}); "
                "create a fresh key under Management -> API Tokens"
            )
        if response.status_code == 400:
            raise ZetarisRequestError(
                "zetaris rejected the request (HTTP 400): check the numeric "
                f"org id and the statement. Body: {response.text[:MAX_ERROR_BODY]}"
            )
        if response.status_code != 200:
            raise ZetarisRequestError(
                f"zetaris returned HTTP {response.status_code}: "
                f"{response.text[:MAX_ERROR_BODY]}"
            )
        try:
            return response.json(), request_id
        except ValueError as exc:
            raise ZetarisRequestError("zetaris returned a non-JSON response") from exc

    # ------------------------------------------------------------------- API

    def list_datasources(self) -> list[str]:
        """Names of the datasources visible to this account (health signal)."""
        payload, _ = self._request("GET", DATASOURCES_PATH)
        if isinstance(payload, list):
            entries = payload
        elif isinstance(payload, dict):
            data = payload.get("data", [])
            entries = data if isinstance(data, list) else []
        else:
            entries = []
        names = []
        for entry in entries:
            if isinstance(entry, dict) and "name" in entry:
                names.append(str(entry["name"]))
            elif isinstance(entry, str):
                names.append(entry)
        return names

    def run_sql(
        self,
        statement: str,
        row_limit: int | None = None,
        *,
        allow_writes: bool = False,
    ) -> QueryResult:
        """Validate and execute one statement, returning rows and identifiers.

        All values come back as strings, exactly as the API returns them; any
        conversion is the caller's responsibility.
        """
        text = governance.validate_statement(statement, allow_writes=allow_writes)
        limit = governance.clamp_row_limit(
            row_limit,
            default=self._settings.default_row_limit,
            maximum=self._settings.max_row_limit,
        )
        query_id = str(uuid.uuid4())
        body = {
            "queryId": query_id,
            "sql": text,
            "source": QUERY_SOURCE,
            "limit": limit,
        }
        started = time.monotonic()
        payload, request_id = self._request("POST", RUN_SQL_PATH, json_body=body)
        duration_ms = int((time.monotonic() - started) * 1000)

        rows: list[list[str]] = []
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                for row in data:
                    if isinstance(row, list):
                        rows.append(["" if value is None else str(value) for value in row])

        return QueryResult(
            rows=rows,
            row_count=len(rows),
            truncated=limit > 0 and len(rows) == limit,
            statement=text,
            limit=limit,
            query_id=query_id,
            request_id=request_id,
            org_id=self._settings.org_id or "",
            endpoint=f"{self._base}{RUN_SQL_PATH}",
            duration_ms=duration_ms,
        )
