"""GitHub prerequisite check for ENG-005. Run it on the backend host.

    python -m app.modules.github.preflight
    python -m app.modules.github.preflight --write-probe --evidence-out ../docs/evidence/github-preflight-<date>.md

Read-only by default. It proves, in order:

1. the token authenticates, and what kind it is (fine-grained is required:
   a classic token with ``repo`` scope can write every repo the user owns);
2. the demo-target repo exists, is not archived, and the token can push to it;
3. the token cannot push to (or administer) the product repo;
4. whether the demo default branch is protected, and the remaining API quota.

``--write-probe`` additionally creates and deletes a throwaway branch ref in
the demo repo to prove contents write. PR creation is proven in ENG-040.

Exit code 0 when no check failed, 1 for configuration problems, 2 otherwise.
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.modules.github.config import GitHubConfigError, GitHubSettings

Status = Literal["pass", "warn", "fail", "skip"]


class Check(BaseModel):
    name: str
    status: Status
    detail: str


class GitHubPreflightReport(BaseModel):
    demo_repo: str
    product_repo: str
    checks: list[Check] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def passed(self) -> bool:
        return not any(check.status == "fail" for check in self.checks)

    def add(self, name: str, status: Status, detail: str) -> None:
        self.checks.append(Check(name=name, status=status, detail=detail))


def _token_kind(token: str) -> str:
    if token.startswith("github_pat_"):
        return "fine-grained"
    if token.startswith("ghp_"):
        return "classic"
    return "other"


def _client(settings: GitHubSettings, transport: httpx.BaseTransport | None) -> httpx.Client:
    return httpx.Client(
        base_url=settings.api_url,
        headers={
            "Authorization": f"Bearer {settings.bearer_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "agentic-engineering-workspace-preflight",
        },
        timeout=settings.timeout_seconds,
        transport=transport,
    )


def run_preflight(
    settings: GitHubSettings,
    write_probe: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> GitHubPreflightReport:
    report = GitHubPreflightReport(demo_repo=settings.demo_repo, product_repo=settings.product_repo)
    kind = _token_kind(settings.bearer_token())

    with _client(settings, transport) as gh:
        # 1. authentication and token kind
        try:
            user = gh.get("/user")
        except httpx.HTTPError as exc:
            report.add("authenticate", "fail", f"cannot reach {settings.api_url}: {type(exc).__name__}")
            return report
        if user.status_code != 200:
            report.add("authenticate", "fail", f"GET /user returned HTTP {user.status_code}")
            return report
        report.add("authenticate", "pass", f"token belongs to {user.json().get('login')}")

        scopes = [s.strip() for s in user.headers.get("x-oauth-scopes", "").split(",") if s.strip()]
        if kind == "fine-grained":
            report.add("token kind", "pass", "fine-grained token (access limited to selected repos)")
        elif "repo" in scopes or "public_repo" in scopes:
            report.add(
                "token kind",
                "fail",
                f"{kind} token with scopes {scopes}: it can write every repo of the account; "
                "use a fine-grained token limited to the demo repo",
            )
        else:
            report.add("token kind", "warn", f"{kind} token, scopes {scopes or 'none reported'}")

        # 2. demo repo reachable and writable
        demo = gh.get(f"/repos/{settings.demo_repo}")
        if demo.status_code != 200:
            report.add("demo repo", "fail", f"GET /repos/{settings.demo_repo} returned HTTP {demo.status_code}")
            demo_data: dict = {}
        else:
            demo_data = demo.json()
            perms = demo_data.get("permissions") or {}
            visibility = "private" if demo_data.get("private") else "public"
            if demo_data.get("archived"):
                report.add("demo repo", "fail", "demo repo is archived")
            elif not perms.get("push"):
                report.add("demo repo", "fail", f"{visibility}, token has no push permission")
            else:
                report.add(
                    "demo repo",
                    "pass",
                    f"{visibility}, default branch {demo_data.get('default_branch')}, push allowed",
                )
            if perms.get("admin"):
                report.add("demo admin", "warn", "token has admin on the demo repo; push is enough")

        # 3. product repo must not be writable
        product = gh.get(f"/repos/{settings.product_repo}")
        if product.status_code in (403, 404):
            report.add("product repo isolation", "pass", f"token cannot see it (HTTP {product.status_code})")
        elif product.status_code == 200:
            perms = product.json().get("permissions") or {}
            if perms.get("push") or perms.get("admin"):
                report.add("product repo isolation", "fail", "token can write the product repo")
            else:
                report.add("product repo isolation", "pass", "visible but read-only for this token")
        else:
            report.add("product repo isolation", "fail", f"unexpected HTTP {product.status_code}")

        # 4. default branch protection and quota
        default_branch = demo_data.get("default_branch")
        if default_branch:
            branch = gh.get(f"/repos/{settings.demo_repo}/branches/{default_branch}")
            if branch.status_code == 200 and branch.json().get("protected"):
                report.add("demo default branch", "pass", f"{default_branch} is protected")
            elif branch.status_code == 200:
                report.add(
                    "demo default branch",
                    "warn",
                    f"{default_branch} is not protected; the agent must only push feature branches",
                )
            else:
                report.add("demo default branch", "warn", f"branch lookup HTTP {branch.status_code}")

        rate = gh.get("/rate_limit")
        if rate.status_code == 200:
            core = rate.json().get("resources", {}).get("core", {})
            remaining, limit = core.get("remaining"), core.get("limit")
            status: Status = "pass" if remaining is not None and remaining >= 100 else "warn"
            report.add("api quota", status, f"{remaining}/{limit} core requests left this hour")
        else:
            report.add("api quota", "warn", f"rate limit lookup HTTP {rate.status_code}")

        # 5. optional write probe: create then delete a branch ref
        if not write_probe:
            report.add("contents write", "skip", "run with --write-probe to prove it")
        elif not default_branch or any(c.name == "demo repo" and c.status == "fail" for c in report.checks):
            report.add("contents write", "skip", "demo repo check failed")
        else:
            report.add("contents write", *_write_probe(gh, settings.demo_repo, default_branch))

    return report


def _write_probe(gh: httpx.Client, repo: str, default_branch: str) -> tuple[Status, str]:
    head = gh.get(f"/repos/{repo}/git/ref/heads/{default_branch}")
    if head.status_code != 200:
        return "fail", f"cannot read {default_branch} ref (HTTP {head.status_code})"
    sha = head.json()["object"]["sha"]
    ref = f"aew-preflight/{int(time.time())}"
    created = gh.post(f"/repos/{repo}/git/refs", json={"ref": f"refs/heads/{ref}", "sha": sha})
    if created.status_code != 201:
        return "fail", f"creating branch {ref} returned HTTP {created.status_code}"
    deleted = gh.delete(f"/repos/{repo}/git/refs/heads/{ref}")
    if deleted.status_code != 204:
        return "warn", f"created {ref} but delete returned HTTP {deleted.status_code}; remove it by hand"
    return "pass", f"created and deleted branch {ref} at {sha[:7]}"


def render_markdown(report: GitHubPreflightReport) -> str:
    lines = [
        "# GITHUB_PREFLIGHT evidence: GitHub prerequisites (ENG-005)",
        "",
        f"* **Generated (UTC):** {report.generated_at.isoformat(timespec='seconds')}",
        "* **Command:** `python -m app.modules.github.preflight`",
        f"* **Demo-target repo:** `{report.demo_repo}`",
        f"* **Product repo (must stay read-only):** `{report.product_repo}`",
        "* **Sanitization:** the token is never written; the file is checked for it before saving.",
        f"* **Verdict:** {'PASS' if report.passed else 'FAIL'}",
        "",
        "| Check | Status | Detail |",
        "|---|---|---|",
    ]
    lines += [f"| {c.name} | {c.status} | {c.detail} |" for c in report.checks]
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GitHub prerequisite check (ENG-005)")
    parser.add_argument("--write-probe", action="store_true", help="create and delete a branch in the demo repo")
    parser.add_argument("--evidence-out", type=Path, help="write evidence markdown here")
    args = parser.parse_args(argv)

    try:
        settings = GitHubSettings.from_env()
    except GitHubConfigError as exc:
        print(f"CONFIG: {exc}")
        return 1

    report = run_preflight(settings, write_probe=args.write_probe)
    for check in report.checks:
        print(f"{check.status.upper():4} {check.name}: {check.detail}")

    if args.evidence_out is not None:
        text = render_markdown(report)
        if settings.bearer_token() in text:
            print("REFUSED: evidence text contains the token; nothing written")
            return 2
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(text, encoding="utf-8")
        print(f"evidence written: {args.evidence_out}")

    print("GITHUB PREFLIGHT OK" if report.passed else "GITHUB PREFLIGHT FAILED")
    return 0 if report.passed else 2


if __name__ == "__main__":
    sys.exit(main())
