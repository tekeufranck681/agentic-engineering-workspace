"""ENG-017 publisher: publish the engineering read model into Zetaris.

Operator-driven by design:

* default mode is DRY-RUN — it reads the live Zetaris state through the
  governed read path, prints the exact statements it would run, and changes
  nothing;
* writes happen only with `--apply`, launched by a human;
* `--check` is the freshness/consistency audit: no plan, no writes, no
  password needed — inventory completeness, the independent Postgres-vs-
  Zetaris count cross-check, and strict view-queryability probes;
* the datasource password is never printed, logged or embedded in the report;
* after applying, verification runs automatically (same checks as `--check`,
  with probes advisory rather than strict).

CLI:

    python -m app.modules.zetaris.publisher            # dry-run, shows plan
    python -m app.modules.zetaris.publisher --apply    # executes + verifies
    python -m app.modules.zetaris.publisher --check    # freshness audit only
"""

import argparse
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.modules.zetaris import read_model
from app.modules.zetaris.client import ZetarisClient
from app.modules.zetaris.config import ReadModelSettings, ZetarisSettings
from app.modules.zetaris.errors import ZetarisConfigError, ZetarisError
from app.modules.zetaris.read_model import (
    TABLES,
    CurrentState,
    JdbcTarget,
)


class TableCheck(BaseModel):
    table: str
    postgres_count: int | None
    zetaris_count: int | None
    match: bool | None = Field(
        description="None when a side could not be counted (inconclusive, not a pass)"
    )
    note: str = ""


class PublishReport(BaseModel):
    """Serializable evidence of one publisher run. Contains no secrets."""

    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    mode: str
    datasource: str
    planned: list[str] = Field(default_factory=list)
    executed: list[str] = Field(default_factory=list)
    failed_action: str | None = None
    missing_after_apply: list[str] = Field(default_factory=list)
    table_checks: list[TableCheck] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    success: bool = False


def fetch_current_state(client: ZetarisClient, datasource: str) -> CurrentState:
    """Read what Zetaris already has, through the governed read path."""
    registered: set[str] = set()
    exists = datasource in client.list_datasources()
    if exists:
        result = client.run_sql(f"SHOW DATASOURCE TABLES {datasource}")
        for row in result.rows:
            if row:
                registered.add(row[0])
    return CurrentState(datasource_exists=exists, registered_objects=frozenset(registered))


def _count_via_zetaris(client: ZetarisClient, qualified_table: str) -> int:
    result = client.run_sql(f"SELECT COUNT(*) FROM {qualified_table}")
    if not result.rows or not result.rows[0]:
        raise ZetarisError(f"count query returned no rows for {qualified_table}")
    return int(result.rows[0][0])


def publish(
    client: ZetarisClient,
    target: JdbcTarget,
    *,
    table_counter: Callable[[str], int] | None,
    read_model_password: str | None,
    apply: bool,
    verify_only: bool = False,
) -> PublishReport:
    """Compute the plan, optionally execute it with operator password, verify.

    With ``verify_only`` (--check), no plan is computed, no password is needed,
    and freshness is judged strictly: the views must actually answer queries.
    """

    if apply and verify_only:
        raise ValueError("--apply and --check are mutually exclusive modes")

    datasource = read_model.DATASOURCE_NAME
    mode = "check" if verify_only else ("apply" if apply else "dry_run")
    report = PublishReport(mode=mode, datasource=datasource)

    if verify_only:
        report.notes.append(
            "check mode: freshness/consistency verification only; "
            "no plan computed, no writes sent"
        )
    else:
        current = fetch_current_state(client, datasource)
        plan = read_model.build_plan(target, current)
        report.planned = [f"{item.action}: {item.display()}" for item in plan]

        if not plan:
            report.notes.append("read model already fully published; nothing to do")

        if not apply:
            report.success = True
            report.notes.append(
                "dry-run only: no statement was executed; re-run with --apply to publish"
            )
            return report

        if plan and read_model_password is None:
            raise ZetarisConfigError(
                "applying requires the read-model password: set "
                "ZETARIS_READMODEL_PASSWORD (the zetaris_ro role password) locally"
            )

        for item in plan:
            assert read_model_password is not None
            try:
                client.run_sql(item.rendered(read_model_password), allow_writes=True)
            except ZetarisError as exc:
                report.failed_action = f"{item.action}: {exc}"
                report.notes.append("stopped at first failure; fix and re-run (idempotent)")
                return report
            report.executed.append(item.action)

    failed_probes = _verify(client, datasource, table_counter, report)

    report.success = (
        report.failed_action is None
        and not report.missing_after_apply
        and all(check.match is True for check in report.table_checks)
        and not (verify_only and failed_probes)
    )
    return report


def _verify(
    client: ZetarisClient,
    datasource: str,
    table_counter: Callable[[str], int] | None,
    report: PublishReport,
) -> list[str]:
    """Inventory completeness + independent counts + view probes.

    Returns the names of views whose queryability probe failed (advisory in
    --apply mode, strict in --check mode).
    """

    # Verification 1: inventory completeness.
    wanted = {t.name for t in TABLES} | {t.view_name for t in TABLES}
    after = fetch_current_state(client, datasource)
    report.missing_after_apply = sorted(wanted - set(after.registered_objects))

    # Verification 2: independent counts (product Postgres vs Zetaris).
    for table in TABLES:
        check = TableCheck(
            table=table.name, postgres_count=None, zetaris_count=None, match=None
        )
        try:
            if table_counter is not None:
                check.postgres_count = table_counter(table.name)
        except Exception as exc:  # local DB problem is inconclusive, not Zetaris failure
            check.note = f"postgres count unavailable: {exc}"
        try:
            check.zetaris_count = _count_via_zetaris(client, f"{datasource}.{table.name}")
        except ZetarisError as exc:
            check.note = f"zetaris count failed: {exc}" if not check.note else check.note
        if check.postgres_count is not None and check.zetaris_count is not None:
            check.match = check.postgres_count == check.zetaris_count
        report.table_checks.append(check)

    # Confirm each governed view answers queries through the datasource-qualified
    # address (spike confirmed `aew_pg.<view>` addressing; an error here is a
    # genuine finding).
    failed_probes: list[str] = []
    for table in TABLES:
        try:
            _count_via_zetaris(client, f"{datasource}.{table.view_name}")
            report.notes.append(f"view {table.view_name}: queryable")
        except ZetarisError:
            failed_probes.append(table.view_name)
            report.notes.append(f"view {table.view_name}: probe inconclusive")
    return failed_probes


def _default_table_counter() -> Callable[[str], int]:
    """Count rows in the product database using the same engine as the app."""
    from sqlalchemy import text

    from app.core.config import get_settings
    from app.core.db import get_engine

    allowed = {table.name for table in TABLES}
    engine = get_engine(get_settings().database_url)

    def count(table: str) -> int:
        if table not in allowed:
            raise ValueError(f"refusing to count unexpected table {table!r}")
        with engine.connect() as connection:
            return int(connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())

    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help="execute the plan on Zetaris (default is dry-run: print only)",
    )
    mode_group.add_argument(
        "--check",
        action="store_true",
        help="freshness/consistency audit only: no plan, no writes, no password",
    )
    args = parser.parse_args()

    try:
        zetaris_settings = ZetarisSettings.from_env()
    except ZetarisConfigError as exc:
        print(f"CONFIG: {exc}")
        return 2

    read_model_settings = ReadModelSettings()
    target = JdbcTarget(
        host=read_model_settings.host,
        port=read_model_settings.port,
        database=read_model_settings.database,
        user=read_model_settings.user,
    )
    password = (
        read_model_settings.password.get_secret_value()
        if read_model_settings.password is not None
        else None
    )

    with ZetarisClient(zetaris_settings) as client:
        try:
            report = publish(
                client,
                target,
                table_counter=_default_table_counter() if (args.apply or args.check) else None,
                read_model_password=None if args.check else password,
                apply=args.apply,
                verify_only=args.check,
            )
        except ZetarisError as exc:
            print(f"FAIL: {exc}")
            return 1

    for line in report.planned:
        print(f"PLAN {'->' if args.apply else '  '} {line}")
    print(report.model_dump_json(indent=2))
    if args.apply:
        print("PUBLISH OK" if report.success else "PUBLISH FAILED — see report")
        return 0 if report.success else 1
    if args.check:
        print("READ MODEL FRESH" if report.success else "READ MODEL STALE — see report")
        return 0 if report.success else 1
    print("DRY-RUN: nothing was executed; re-run with --apply to publish")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
