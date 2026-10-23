"""Statement governance: what the tool is allowed to send to Zetaris.

Rules (from the Zetaris documentation and our own safety contract):

* one Lightning SQL statement per request — no semicolons, no batches;
* read-only by default — only SELECT-family and introspection keywords are
  accepted; anything that creates, alters, drops, grants or writes needs an
  explicit non-default flag, which the agent-facing tool never sets;
* a statement length cap keeps runaway model output out of the engine.
"""

from app.modules.zetaris.errors import StatementRejectedError

MAX_STATEMENT_LENGTH = 10_000

READ_ONLY_KEYWORDS = ("SELECT", "WITH", "SHOW", "DESCRIBE", "DESC", "EXPLAIN")


def validate_statement(statement: str, *, allow_writes: bool = False) -> str:
    """Validate and normalize one statement, or raise StatementRejectedError.

    Returns the stripped statement on success.
    """
    text = statement.strip()
    if not text:
        raise StatementRejectedError("empty statement")
    if len(text) > MAX_STATEMENT_LENGTH:
        raise StatementRejectedError(
            f"statement exceeds {MAX_STATEMENT_LENGTH} characters"
        )
    if ";" in text:
        raise StatementRejectedError(
            "exactly one statement per request: semicolons are not allowed"
        )
    keyword = text.split(None, 1)[0].upper()
    if not allow_writes and keyword not in READ_ONLY_KEYWORDS:
        raise StatementRejectedError(
            f"statement is not read-only (starts with {keyword!r}); "
            "write or administrative statements need human approval"
        )
    return text


def clamp_row_limit(requested: int | None, *, default: int, maximum: int) -> int:
    """Resolve the effective row limit within [1, maximum]."""
    if requested is None:
        return min(default, maximum)
    return max(1, min(requested, maximum))
