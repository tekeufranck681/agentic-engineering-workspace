"""Governance rules: the front door of the governed run_sql tool."""

import pytest

from app.modules.zetaris.errors import StatementRejectedError
from app.modules.zetaris.governance import clamp_row_limit, validate_statement


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT 1",
        "  SELECT * FROM NY_TAXI.customers LIMIT 10  ",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "SHOW LIGHTNING DATABASES",
        "SHOW DATASOURCES",
        "DESCRIBE DATASOURCE TABLE db.t",
        "EXPLAIN QUERY SELECT 1",
    ],
)
def test_read_only_statements_are_accepted(statement):
    assert validate_statement(statement) == statement.strip()


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE DATASOURCE x OPTIONS (k 'v')",
        "DROP LIGHTNING DATABASE db",
        "INSERT INTO t VALUES (1)",
        "GRANT SELECT ON t TO r",
        "UPDATE t SET a = 1",
        "DELETE FROM t",
    ],
)
def test_write_statements_are_rejected_by_default(statement):
    with pytest.raises(StatementRejectedError):
        validate_statement(statement)


def test_write_statements_need_explicit_flag():
    statement = "CREATE DATASOURCE x OPTIONS (k 'v')"
    assert validate_statement(statement, allow_writes=True) == statement


def test_empty_statement_rejected():
    with pytest.raises(StatementRejectedError):
        validate_statement("   ")


def test_semicolons_rejected_even_single_trailing():
    with pytest.raises(StatementRejectedError):
        validate_statement("SELECT 1;")
    with pytest.raises(StatementRejectedError):
        validate_statement("SELECT 1; SELECT 2")


def test_oversized_statement_rejected():
    with pytest.raises(StatementRejectedError):
        validate_statement("SELECT " + "x" * 20_000)


def test_clamp_row_limit():
    assert clamp_row_limit(None, default=100, maximum=1000) == 100
    assert clamp_row_limit(5, default=100, maximum=1000) == 5
    assert clamp_row_limit(10_000, default=100, maximum=1000) == 1000
    assert clamp_row_limit(0, default=100, maximum=1000) == 1
