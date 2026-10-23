"""Live integration check for the Zetaris client (run on the Zetaris host).

Usage (after filling the ZETARIS_* values in the local .env):

    python -m app.modules.zetaris.smoke

What it proves, read-only and in order:

1. the direct REST API answers and this account can list datasources;
2. the Lightning engine inventories respond (SHOW LIGHTNING DATABASES);
3. a REAL query against the bundled NY_TAXI sample data returns rows —
   the actual ENG-007-style evidence, not a SELECT 1.

Exit code is 0 only when all three pass; failures print the typed error and
an exit code of 1 (config) or 2 (runtime). Nothing is written to the
instance.
"""

import sys

from app.modules.zetaris.client import ZetarisClient
from app.modules.zetaris.config import ZetarisSettings
from app.modules.zetaris.errors import ZetarisConfigError, ZetarisError
from app.modules.zetaris.tool import RunSqlInput, run_sql_tool

SAMPLE_QUERY = "SELECT * FROM NY_TAXI.customers LIMIT 5"


def main() -> int:
    try:
        settings = ZetarisSettings.from_env()
    except ZetarisConfigError as exc:
        print(f"CONFIG: {exc}")
        return 1

    with ZetarisClient(settings) as client:
        try:
            datasources = client.list_datasources()
        except ZetarisError as exc:
            print(f"FAIL datasources: {exc}")
            return 2
        print(f"OK   datasources: {len(datasources)} visible: "
              f"{', '.join(datasources) if datasources else 'none registered yet'}")

        for label, statement in (
            ("lightning databases", "SHOW LIGHTNING DATABASES"),
            ("NY_TAXI sample query", SAMPLE_QUERY),
        ):
            try:
                output = run_sql_tool(RunSqlInput(statement=statement), client)
            except ZetarisError as exc:
                print(f"FAIL {label}: {exc}")
                return 2
            print(f"OK   {label}: {output.row_count} row(s)"
                  f"{' (truncated)' if output.truncated else ''}")
            for row in output.rows[:3]:
                print(f"     {row}")
            evidence = output.evidence
            print(f"     evidence: sha256={evidence.statement_sha256[:12]}… "
                  f"query_id={evidence.query_id} request_id={evidence.request_id} "
                  f"duration_ms={evidence.duration_ms}")

    print("SMOKE OK: zetaris client works against the live instance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
