"""Scoped git commit, push and GitHub PR delivery (ENG-040).

``DeliveryService.deliver`` turns a run's sandbox workspace into a pull request
on the demo-target repo, and refuses unless every gate holds:

1. **test gate**: the full test suite runs in the sandbox right now and passes
   (no tests collected is a refusal, not a pass);
2. **change gate**: the workspace has changes since the base commit;
3. **scope gate**: every changed path is inside the task's ``target_paths``,
   the same rule the ToolGateway applies to writes.

Then it commits on a fresh ``aew/`` branch created at the run's exact base
commit, pushes through the GitHub adapter from the backend (the token never
enters the sandbox) and opens a PR whose body traces requirement, ACs, task
and run. The diff, the test report and the PR record go to M2's write-once
evidence store (ENG-037); each step is a run event and each GitHub write a
tool execution in M2's run store (ENG-027), linked to its evidence.

The agent never merges: a human reviews the PR.
"""

import hashlib
import json

from pydantic import BaseModel

from app.domain.task import Task
from app.modules.github.client import GitHubError, GitHubRepoClient
from app.modules.persistence.evidence_store import EvidenceStore
from app.modules.persistence.run_store import RunStore
from app.modules.sandbox.provider import ChangeSet, TestRunResult, Workspace
from app.modules.tools.gateway import ToolScope


class DeliveryRefused(Exception):
    """A gate did not hold; nothing was pushed."""


class EvidenceRef(BaseModel):
    kind: str
    id: str


class Delivery(BaseModel):
    run_id: str
    task_id: str
    branch: str
    base_sha: str
    commit_sha: str
    changed_paths: list[str]
    pr_number: int
    pr_url: str
    tests_passed: int
    evidence: list[EvidenceRef]


def _digest(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def build_pr_body(run_id: str, task: Task, base_sha: str, summary: str, tests: TestRunResult,
                  changed: list[str], evidence: list[EvidenceRef]) -> str:
    trace = task.trace
    lines = [
        f"Automated change by the Agentic Engineering Workspace for **{task.id}: {task.title}**.",
        "",
        summary,
        "",
        "## Traceability",
        "",
        f"- **Requirements:** {', '.join(trace.requirement_ids) or 'none linked'}",
        f"- **Acceptance criteria:** {', '.join(trace.ac_ids) or 'none linked'}",
        f"- **Task:** {task.id}",
        f"- **Run:** {run_id}",
        f"- **Base commit:** `{base_sha}`",
        "",
        "## Tests (sandbox, at delivery time)",
        "",
        f"- **Outcome:** {tests.outcome}, {tests.passed} passed, {tests.failed} failed, {tests.errors} errors",
        f"- **Duration:** {tests.duration_ms} ms",
        "",
        "## Changed files",
        "",
        *[f"- `{path}`" for path in changed],
        "",
        "## Evidence",
        "",
        "| Kind | Evidence id (sha256) |",
        "|---|---|",
        *[f"| {ref.kind} | `{ref.id}` |" for ref in evidence],
        "",
        "Review before merging: the agent never merges its own changes.",
    ]
    return "\n".join(lines)


class DeliveryService:
    def __init__(self, github: GitHubRepoClient, run_store: RunStore, evidence: EvidenceStore):
        self.github = github
        self.run_store = run_store
        self.evidence = evidence

    def _refuse(self, run_id: str, reason: str, **details) -> DeliveryRefused:
        self.run_store.append_event(run_id, "delivery.refused", {"reason": reason, **details})
        return DeliveryRefused(reason)

    def _github_write(self, run_id: str, tool: str, request: dict, action, evidence_ref: str | None = None):
        """Run one GitHub write and record it as a tool execution, whatever the outcome."""
        try:
            result = action()
        except GitHubError:
            self.run_store.record_tool_execution(run_id, tool, _digest(request), status="error")
            raise
        self.run_store.record_tool_execution(run_id, tool, _digest(request), status="ok", evidence_ref=evidence_ref)
        return result

    def deliver(self, run_id: str, task: Task, workspace: Workspace, summary: str) -> Delivery:
        self.run_store.append_event(run_id, "delivery.started", {"task_id": task.id, "base_sha": workspace.base_sha})
        if not workspace.base_sha:
            raise self._refuse(run_id, "workspace has no base commit")

        tests = workspace.run_tests()
        if tests.outcome != "passed":
            raise self._refuse(run_id, f"test gate: suite {tests.outcome}", passed=tests.passed,
                               failed=tests.failed, failing_tests=tests.failing_tests)

        change_set: ChangeSet = workspace.diff()
        if not change_set.changes:
            raise self._refuse(run_id, "change gate: the workspace has no changes")
        scope = ToolScope(run_id=run_id, task_id=task.id, allowed_tools=frozenset(),
                          writable_paths=tuple(task.target_paths))
        outside = [c.path for c in change_set.changes if not scope.allows_write(c.path)]
        if outside:
            raise self._refuse(run_id, "scope gate: changes outside the task's target paths", paths=outside)

        diff_row = self.evidence.put(change_set.patch.encode(), kind="diff", media_type="text/x-diff",
                                     run_id=run_id, produced_by="sandbox.diff")
        test_row = self.evidence.put(tests.model_dump_json(indent=2).encode(), kind="test_output",
                                     media_type="application/json", run_id=run_id, produced_by="sandbox.run_tests")
        refs = [EvidenceRef(kind="diff", id=diff_row.id), EvidenceRef(kind="test_output", id=test_row.id)]
        self.run_store.append_event(run_id, "delivery.gates_passed", {
            "tests_passed": tests.passed, "changed_paths": [c.path for c in change_set.changes],
            "evidence": [r.model_dump() for r in refs],
        })

        files, deletions = workspace.collect_changes()
        branch = f"{self.github.settings.agent_branch_prefix}{run_id.lower()}-{task.id.lower()}"
        base_sha = workspace.base_sha
        self._github_write(run_id, "github.create_branch", {"branch": branch, "sha": base_sha},
                           lambda: self.github.create_branch(branch, base_sha))
        message = f"{task.id}: {task.title}\n\n{summary}\n\nRun: {run_id}"
        commit = self._github_write(
            run_id, "github.commit_files",
            {"branch": branch, "paths": sorted(files), "deletions": sorted(deletions)},
            lambda: self.github.commit_files(branch, message, files, deletions), evidence_ref=diff_row.id,
        )
        body = build_pr_body(run_id, task, base_sha, summary, tests, commit.changed_paths, refs)
        pr = self._github_write(
            run_id, "github.open_pull_request", {"branch": branch, "title": task.title},
            lambda: self.github.open_pull_request(branch, f"[{task.id}] {task.title}", body),
        )

        pr_record = {"number": pr.number, "url": pr.html_url, "branch": branch, "base_sha": base_sha,
                     "commit_sha": commit.commit_sha, "changed_paths": commit.changed_paths,
                     "task_id": task.id, "run_id": run_id, "body": body}
        pr_row = self.evidence.put(json.dumps(pr_record, sort_keys=True).encode(), kind="pull_request",
                                   media_type="application/json", run_id=run_id, produced_by="github.open_pull_request")
        refs.append(EvidenceRef(kind="pull_request", id=pr_row.id))
        self.run_store.append_event(run_id, "delivery.pr_opened", {
            "pr_number": pr.number, "pr_url": pr.html_url, "branch": branch, "commit_sha": commit.commit_sha,
            "evidence": [r.model_dump() for r in refs],
        })
        return Delivery(run_id=run_id, task_id=task.id, branch=branch, base_sha=base_sha,
                        commit_sha=commit.commit_sha, changed_paths=commit.changed_paths, pr_number=pr.number,
                        pr_url=pr.html_url, tests_passed=tests.passed, evidence=refs)
