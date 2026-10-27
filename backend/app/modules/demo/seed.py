"""Seed the demo scenario into the configured product database (ENG-050).

    python -m app.modules.demo.seed --repo owner/aew-demo-target

Run once, on the operator host, after ``alembic upgrade head``. It creates the
project "Subscription billing demo" bound to the demo repo, with REQ-001 locked,
AC-001/AC-002, the accepted design and TASK-002 ready to run. It refuses if the
project already exists (``--project-name`` to seed another copy).
Exit 0 on success, 1 for configuration or duplicate problems.
"""

import argparse
import asyncio
import sys

from app.core.config import get_settings
from app.core.db import get_engine, make_session_factory
from app.modules.demo.scenario import PROJECT_NAME, seed
from app.modules.persistence.errors import DuplicateProjectNameError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the ENG-050 demo scenario")
    parser.add_argument("--repo", required=True, help="owner/name of the demo-target repo")
    parser.add_argument("--base-sha", help="commit of the demo repo to bind (optional)")
    parser.add_argument("--project-name", default=PROJECT_NAME)
    args = parser.parse_args(argv)
    if "/" not in args.repo or args.repo.startswith("http"):
        print("CONFIG: --repo must be owner/name")
        return 1

    url = get_settings().database_url
    with make_session_factory(get_engine(url))() as session:
        try:
            scenario = asyncio.run(seed(session, args.repo, base_sha=args.base_sha, project_name=args.project_name))
        except DuplicateProjectNameError:
            print(f"EXISTS: a project named {args.project_name!r} is already seeded; nothing changed")
            return 1
    print(f"OK   database: {url.split('@')[-1]}")
    print(f"OK   project {scenario.project_id} bound to {scenario.repository}")
    print(f"     artifacts: {', '.join(scenario.artifacts)}")
    print(f"     ready to run: {scenario.task_id} (ACs {', '.join(scenario.acceptance_criteria)})")
    print("DEMO SCENARIO SEEDED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
