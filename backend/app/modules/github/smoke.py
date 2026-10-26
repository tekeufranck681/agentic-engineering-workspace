"""Live check of the GitHub adapter (ENG-010). Run it on the backend host.

    python -m app.modules.github.smoke                      # read-only
    python -m app.modules.github.smoke --write --evidence-out ../docs/evidence/github-adapter-<date>.md

Read-only mode reads the demo repo, its default-branch head, the file list
and one file. ``--write`` then runs the full delivery path on the demo repo:
create an ``aew/`` branch, commit a file, open a draft PR, and finally close
the PR and delete the branch (``--keep`` leaves them for inspection).
Exit code 0 on success, 1 for configuration problems, 2 otherwise.
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from app.modules.github.client import GitHubError, GitHubRepoClient
from app.modules.github.config import GitHubConfigError, GitHubSettings


def run(client: GitHubRepoClient, write: bool, keep: bool) -> list[tuple[str, str]]:
    steps: list[tuple[str, str]] = []
    repo = client.get_repo()
    steps.append(("read repo", f"{repo.full_name}, default branch {repo.default_branch}"))
    head = client.get_branch_sha(repo.default_branch)
    steps.append(("read head", f"{repo.default_branch} at {head[:7]}"))
    files = client.list_files(head)
    steps.append(("list files", f"{len(files)} file(s)"))
    if files:
        first = client.get_file(files[0], head)
        steps.append(("read file", f"{first.path}, {len(first.text)} chars"))
    if not write:
        return steps

    branch = f"{client.settings.agent_branch_prefix}smoke-{int(time.time())}"
    client.create_branch(branch, head)
    steps.append(("create branch", branch))
    commit = client.commit_files(
        branch, "chore: adapter smoke check", {f"aew-smoke/{branch.rsplit('-', 1)[-1]}.md": "adapter smoke check\n"}
    )
    steps.append(("commit", f"{commit.commit_sha[:7]} on {branch}, parent {commit.parent_sha[:7]}"))
    pr = client.open_pull_request(branch, "[smoke] adapter check", "Automated ENG-010 smoke check.", draft=True)
    steps.append(("open PR", f"#{pr.number} {pr.html_url} (draft={pr.draft})"))
    if keep:
        steps.append(("cleanup", "skipped (--keep)"))
    else:
        client.close_pull_request(pr.number)
        client.delete_branch(branch)
        steps.append(("cleanup", f"closed #{pr.number}, deleted {branch}"))
    return steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GitHub adapter live check (ENG-010)")
    parser.add_argument("--write", action="store_true", help="run branch, commit and PR on the demo repo")
    parser.add_argument("--keep", action="store_true", help="leave the smoke PR and branch in place")
    parser.add_argument("--evidence-out", type=Path)
    args = parser.parse_args(argv)

    try:
        settings = GitHubSettings.from_env()
    except GitHubConfigError as exc:
        print(f"CONFIG: {exc}")
        return 1

    error = None
    steps: list[tuple[str, str]] = []
    with GitHubRepoClient(settings) as client:
        try:
            steps = run(client, args.write, args.keep)
        except GitHubError as exc:
            error = str(exc)
    for name, detail in steps:
        print(f"OK   {name}: {detail}")
    if error:
        print(f"FAIL {error}")

    if args.evidence_out is not None:
        lines = [
            "# GITHUB_ADAPTER evidence: scoped repository adapter (ENG-010)",
            "",
            f"* **Generated (UTC):** {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            f"* **Command:** `python -m app.modules.github.smoke{' --write' if args.write else ''}`",
            f"* **Demo-target repo:** `{settings.demo_repo}`",
            f"* **Verdict:** {'FAIL' if error else 'PASS'}",
            "",
            "| Step | Result |",
            "|---|---|",
            *[f"| {name} | {detail} |" for name, detail in steps],
        ]
        if error:
            lines.append(f"| error | {error} |")
        text = "\n".join(lines) + "\n"
        if settings.bearer_token() in text:
            print("REFUSED: evidence text contains the token; nothing written")
            return 2
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(text, encoding="utf-8")
        print(f"evidence written: {args.evidence_out}")

    print("GITHUB ADAPTER SMOKE FAILED" if error else "GITHUB ADAPTER SMOKE OK")
    return 2 if error else 0


if __name__ == "__main__":
    sys.exit(main())
