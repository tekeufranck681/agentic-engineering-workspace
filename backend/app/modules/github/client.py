"""Scoped GitHub repository adapter (ENG-010, transport part).

Every method acts on the configured demo-target repository only: there is no
repo argument, so the adapter cannot be pointed at the product repo. Writes
are further limited to branches under ``agent_branch_prefix`` (default
``aew/``); the default branch is never written, nothing is force-pushed, and
CI workflow files and ``.git`` paths are refused. Scope violations raise
``GitHubScopeError`` before any request is sent.

Commits are created through the Git Data API (blobs, tree, commit, ref
update), so the push happens from the backend with the token, and no token
ever enters the sandbox.

The agent-facing tool schema on top of this adapter waits for ENG-004 (M4).
"""

import base64
import posixpath
import re
from typing import Any

import httpx
from pydantic import BaseModel

from app.modules.github.config import GitHubSettings

_BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
_FORBIDDEN_PREFIXES = (".git/", ".github/workflows/")


class GitHubError(Exception):
    """Base error for the adapter."""


class GitHubScopeError(GitHubError):
    """Refused locally: the request is outside the agent's scope. Nothing was sent."""


class GitHubAPIError(GitHubError):
    def __init__(self, action: str, status_code: int, message: str = ""):
        self.action, self.status_code = action, status_code
        super().__init__(f"{action} failed: HTTP {status_code}{f' ({message})' if message else ''}")


class RepoInfo(BaseModel):
    full_name: str
    default_branch: str
    private: bool
    html_url: str


class FileContent(BaseModel):
    path: str
    ref: str
    blob_sha: str
    text: str


class CommitResult(BaseModel):
    branch: str
    commit_sha: str
    parent_sha: str
    changed_paths: list[str]
    html_url: str


class PullRequest(BaseModel):
    number: int
    html_url: str
    state: str
    head_branch: str
    head_sha: str
    base_branch: str
    draft: bool


def _check_path(path: str) -> str:
    """Normalize a repo-relative path and refuse anything outside the repo or sensitive."""
    if not path or path.startswith("/") or "\\" in path or "\x00" in path:
        raise GitHubScopeError(f"path must be repo-relative: {path!r}")
    normalized = posixpath.normpath(path)
    if normalized.startswith("..") or normalized in (".", ".git"):
        raise GitHubScopeError(f"path escapes the repository: {path!r}")
    if any(normalized.startswith(prefix) for prefix in _FORBIDDEN_PREFIXES):
        raise GitHubScopeError(f"path is protected: {path!r}")
    return normalized


class GitHubRepoClient:
    """Adapter bound to ``settings.demo_repo``. Use as a context manager."""

    def __init__(self, settings: GitHubSettings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.repo = settings.demo_repo
        self._http = httpx.Client(
            base_url=settings.api_url,
            headers={
                "Authorization": f"Bearer {settings.bearer_token()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "agentic-engineering-workspace",
            },
            timeout=settings.timeout_seconds,
            transport=transport,
        )
        self._repo_path = f"/repos/{settings.demo_repo}"
        self._default_branch: str | None = None

    def __enter__(self) -> "GitHubRepoClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # -- low level ------------------------------------------------------
    def _request(self, action: str, method: str, url: str, expected: tuple[int, ...], **kw: Any) -> Any:
        try:
            response = self._http.request(method, self._repo_path + url, **kw)
        except httpx.HTTPError as exc:
            raise GitHubError(f"{action} failed: {type(exc).__name__}") from exc
        if response.status_code not in expected:
            message = ""
            try:
                message = str(response.json().get("message", ""))[:200]
            except ValueError:
                pass
            raise GitHubAPIError(action, response.status_code, message)
        return response.json() if response.content else None

    def _check_agent_branch(self, branch: str) -> str:
        if not _BRANCH_PATTERN.fullmatch(branch) or ".." in branch or branch.endswith("/"):
            raise GitHubScopeError(f"invalid branch name {branch!r}")
        if not branch.startswith(self.settings.agent_branch_prefix):
            raise GitHubScopeError(
                f"branch {branch!r} is outside the agent namespace {self.settings.agent_branch_prefix!r}"
            )
        if branch == self.default_branch():
            raise GitHubScopeError("the default branch is never written by the agent")
        return branch

    # -- reads ----------------------------------------------------------
    def get_repo(self) -> RepoInfo:
        data = self._request("get repo", "GET", "", (200,))
        self._default_branch = data["default_branch"]
        return RepoInfo(
            full_name=data["full_name"],
            default_branch=data["default_branch"],
            private=bool(data.get("private")),
            html_url=data["html_url"],
        )

    def default_branch(self) -> str:
        if self._default_branch is None:
            self.get_repo()
        assert self._default_branch is not None
        return self._default_branch

    def get_branch_sha(self, branch: str) -> str:
        data = self._request(f"read branch {branch}", "GET", f"/git/ref/heads/{branch}", (200,))
        return data["object"]["sha"]

    def list_files(self, ref: str) -> list[str]:
        """All file paths at ``ref`` (recursive tree)."""
        data = self._request(f"list files at {ref}", "GET", f"/git/trees/{ref}", (200,), params={"recursive": "1"})
        if data.get("truncated"):
            raise GitHubError("repository tree too large for one listing")
        return sorted(item["path"] for item in data.get("tree", []) if item.get("type") == "blob")

    def get_file(self, path: str, ref: str) -> FileContent:
        path = _check_path(path)
        data = self._request(f"read {path}", "GET", f"/contents/{path}", (200,), params={"ref": ref})
        if not isinstance(data, dict) or data.get("type") != "file":
            raise GitHubError(f"{path} is not a file")
        if int(data.get("size", 0)) > self.settings.max_file_bytes:
            raise GitHubScopeError(f"{path} is larger than {self.settings.max_file_bytes} bytes")
        raw = base64.b64decode(data.get("content", ""))
        return FileContent(path=path, ref=ref, blob_sha=data["sha"], text=raw.decode("utf-8", errors="replace"))

    # -- writes (agent namespace only) ----------------------------------
    def create_branch(self, branch: str, from_sha: str) -> str:
        self._check_agent_branch(branch)
        self._request(
            f"create branch {branch}", "POST", "/git/refs", (201,),
            json={"ref": f"refs/heads/{branch}", "sha": from_sha},
        )
        return branch

    def commit_files(
        self,
        branch: str,
        message: str,
        files: dict[str, str],
        deletions: tuple[str, ...] | list[str] = (),
    ) -> CommitResult:
        """Commit file contents (and deletions) on top of ``branch``; fast-forward only."""
        self._check_agent_branch(branch)
        if not files and not deletions:
            raise GitHubScopeError("nothing to commit")
        if not message.strip():
            raise GitHubScopeError("commit message is empty")
        checked = {_check_path(p): text for p, text in files.items()}
        removed = [_check_path(p) for p in deletions]
        for path, text in checked.items():
            if len(text.encode()) > self.settings.max_file_bytes:
                raise GitHubScopeError(f"{path} is larger than {self.settings.max_file_bytes} bytes")

        parent_sha = self.get_branch_sha(branch)
        parent = self._request("read parent commit", "GET", f"/git/commits/{parent_sha}", (200,))
        entries: list[dict[str, Any]] = []
        for path, text in checked.items():
            blob = self._request(f"upload {path}", "POST", "/git/blobs", (201,), json={"content": text, "encoding": "utf-8"})
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        entries += [{"path": path, "mode": "100644", "type": "blob", "sha": None} for path in removed]
        tree = self._request(
            "create tree", "POST", "/git/trees", (201,),
            json={"base_tree": parent["tree"]["sha"], "tree": entries},
        )
        commit = self._request(
            "create commit", "POST", "/git/commits", (201,),
            json={"message": message, "tree": tree["sha"], "parents": [parent_sha]},
        )
        self._request(
            f"update branch {branch}", "PATCH", f"/git/refs/heads/{branch}", (200,),
            json={"sha": commit["sha"], "force": False},
        )
        return CommitResult(
            branch=branch,
            commit_sha=commit["sha"],
            parent_sha=parent_sha,
            changed_paths=sorted([*checked, *removed]),
            html_url=commit.get("html_url", ""),
        )

    def open_pull_request(self, branch: str, title: str, body: str, draft: bool = False) -> PullRequest:
        self._check_agent_branch(branch)
        data = self._request(
            f"open PR from {branch}", "POST", "/pulls", (201,),
            json={"title": title, "body": body, "head": branch, "base": self.default_branch(), "draft": draft},
        )
        return self._pull(data)

    def get_pull_request(self, number: int) -> PullRequest:
        return self._pull(self._request(f"read PR #{number}", "GET", f"/pulls/{number}", (200,)))

    def close_pull_request(self, number: int) -> PullRequest:
        pr = self.get_pull_request(number)
        self._check_agent_branch(pr.head_branch)
        return self._pull(self._request(f"close PR #{number}", "PATCH", f"/pulls/{number}", (200,), json={"state": "closed"}))

    def delete_branch(self, branch: str) -> None:
        self._check_agent_branch(branch)
        self._request(f"delete branch {branch}", "DELETE", f"/git/refs/heads/{branch}", (204,))

    @staticmethod
    def _pull(data: dict) -> PullRequest:
        return PullRequest(
            number=data["number"],
            html_url=data["html_url"],
            state=data["state"],
            head_branch=data["head"]["ref"],
            head_sha=data["head"]["sha"],
            base_branch=data["base"]["ref"],
            draft=bool(data.get("draft")),
        )
