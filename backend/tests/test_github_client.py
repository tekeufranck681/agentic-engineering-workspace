"""ENG-010 GitHub adapter: an in-memory fake of the GitHub REST API."""

import base64
import json

import httpx
import pytest

from app.modules.github.client import GitHubAPIError, GitHubRepoClient, GitHubScopeError
from app.modules.github.config import GitHubSettings

DEMO = "team/demo-target"
BASE = f"/repos/{DEMO}"
MAIN_SHA = "a" * 40


class FakeGitHub:
    """Just enough of the GitHub API to exercise every adapter path."""

    def __init__(self):
        self.refs = {"main": MAIN_SHA}
        self.files = {"README.md": "# demo\n", "src/app.py": "print('hi')\n"}
        self.pulls: dict[int, dict] = {}
        self.requests: list[tuple[str, str, dict | None]] = []
        self.counter = 0

    def _sha(self) -> str:
        self.counter += 1
        return f"{self.counter:040x}"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        method, path = request.method, request.url.path
        self.requests.append((method, path, body))
        assert path.startswith(BASE), f"request left the demo repo: {path}"
        sub = path[len(BASE):]

        if method == "GET" and sub == "":
            return httpx.Response(200, json={"full_name": DEMO, "default_branch": "main", "private": False,
                                             "html_url": f"https://github.com/{DEMO}"})
        if method == "GET" and sub.startswith("/git/ref/heads/"):
            name = sub[len("/git/ref/heads/"):]
            if name not in self.refs:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"object": {"sha": self.refs[name]}})
        if method == "GET" and sub.startswith("/git/trees/"):
            return httpx.Response(200, json={"truncated": False, "tree": [
                *({"path": p, "type": "blob"} for p in self.files), {"path": "src", "type": "tree"}]})
        if method == "GET" and sub.startswith("/contents/"):
            p = sub[len("/contents/"):]
            if p not in self.files:
                return httpx.Response(404, json={"message": "Not Found"})
            raw = self.files[p].encode()
            return httpx.Response(200, json={"type": "file", "size": len(raw), "sha": "b" * 40,
                                             "content": base64.b64encode(raw).decode()})
        if method == "POST" and sub == "/git/refs":
            name = body["ref"].removeprefix("refs/heads/")
            if name in self.refs:
                return httpx.Response(422, json={"message": "Reference already exists"})
            self.refs[name] = body["sha"]
            return httpx.Response(201, json={})
        if method == "GET" and sub.startswith("/git/commits/"):
            return httpx.Response(200, json={"tree": {"sha": "t" * 40}})
        if method == "POST" and sub == "/git/blobs":
            return httpx.Response(201, json={"sha": self._sha()})
        if method == "POST" and sub == "/git/trees":
            return httpx.Response(201, json={"sha": self._sha()})
        if method == "POST" and sub == "/git/commits":
            return httpx.Response(201, json={"sha": self._sha(), "html_url": "https://github.com/x/commit"})
        if method == "PATCH" and sub.startswith("/git/refs/heads/"):
            assert body["force"] is False
            self.refs[sub[len("/git/refs/heads/"):]] = body["sha"]
            return httpx.Response(200, json={})
        if method == "DELETE" and sub.startswith("/git/refs/heads/"):
            self.refs.pop(sub[len("/git/refs/heads/"):])
            return httpx.Response(204)
        if method == "POST" and sub == "/pulls":
            number = len(self.pulls) + 1
            self.pulls[number] = {"number": number, "html_url": f"https://github.com/{DEMO}/pull/{number}",
                                  "state": "open", "draft": body["draft"],
                                  "head": {"ref": body["head"], "sha": self.refs[body["head"]]},
                                  "base": {"ref": body["base"]}}
            return httpx.Response(201, json=self.pulls[number])
        if method == "GET" and sub.startswith("/pulls/"):
            return httpx.Response(200, json=self.pulls[int(sub.rsplit("/", 1)[1])])
        if method == "PATCH" and sub.startswith("/pulls/"):
            pr = self.pulls[int(sub.rsplit("/", 1)[1])]
            pr["state"] = body["state"]
            return httpx.Response(200, json=pr)
        return httpx.Response(500, json={"message": f"unhandled {method} {sub}"})

    def writes(self) -> list[tuple[str, str]]:
        return [(m, p[len(BASE):]) for m, p, _ in self.requests if m != "GET"]


@pytest.fixture()
def gh():
    return FakeGitHub()


@pytest.fixture()
def client(gh):
    settings = GitHubSettings(token="github_pat_" + "x" * 40, demo_repo=DEMO, product_repo="team/product")
    with GitHubRepoClient(settings, transport=httpx.MockTransport(gh)) as c:
        yield c


def test_reads(client):
    repo = client.get_repo()
    assert repo.default_branch == "main"
    assert client.get_branch_sha("main") == MAIN_SHA
    assert client.list_files(MAIN_SHA) == ["README.md", "src/app.py"]
    assert client.get_file("src/app.py", MAIN_SHA).text == "print('hi')\n"


def test_full_delivery_path(client, gh):
    client.create_branch("aew/fix-1", MAIN_SHA)
    commit = client.commit_files("aew/fix-1", "fix: thing", {"src/app.py": "print('fixed')\n"}, deletions=["README.md"])
    assert commit.parent_sha == MAIN_SHA
    assert commit.changed_paths == ["README.md", "src/app.py"]
    assert gh.refs["aew/fix-1"] == commit.commit_sha
    tree_body = next(b for m, p, b in gh.requests if m == "POST" and p.endswith("/git/trees"))
    assert tree_body["base_tree"] == "t" * 40
    assert {"path": "README.md", "mode": "100644", "type": "blob", "sha": None} in tree_body["tree"]

    pr = client.open_pull_request("aew/fix-1", "Fix", "body", draft=True)
    assert pr.base_branch == "main" and pr.head_sha == commit.commit_sha and pr.draft
    assert client.close_pull_request(pr.number).state == "closed"
    client.delete_branch("aew/fix-1")
    assert "aew/fix-1" not in gh.refs


@pytest.mark.parametrize("branch", ["main", "feature/x", "aew/../main", "aew/", "aew/x y", "-aew/x"])
def test_writes_outside_agent_namespace_are_refused_before_sending(client, gh, branch):
    for action in (
        lambda: client.create_branch(branch, MAIN_SHA),
        lambda: client.commit_files(branch, "m", {"a.txt": "x"}),
        lambda: client.open_pull_request(branch, "t", "b"),
        lambda: client.delete_branch(branch),
    ):
        with pytest.raises(GitHubScopeError):
            action()
    assert gh.writes() == []


def test_custom_prefix_equal_to_default_branch_is_still_refused(gh):
    gh.refs["aew/main"] = MAIN_SHA
    settings = GitHubSettings(token="github_pat_" + "x" * 40, demo_repo=DEMO, product_repo="team/product")
    with GitHubRepoClient(settings, transport=httpx.MockTransport(gh)) as c:
        c._default_branch = "aew/main"  # pathological repo whose default branch sits in the namespace
        with pytest.raises(GitHubScopeError, match="default branch"):
            c.commit_files("aew/main", "m", {"a.txt": "x"})


@pytest.mark.parametrize(
    "path", ["/etc/passwd", "../outside.txt", "src/../../x", ".git/config", ".github/workflows/ci.yml", "a\\b", ""]
)
def test_unsafe_paths_are_refused(client, gh, path):
    client.create_branch("aew/fix-2", MAIN_SHA)
    before = gh.writes()
    with pytest.raises(GitHubScopeError):
        client.commit_files("aew/fix-2", "m", {path: "x"})
    with pytest.raises(GitHubScopeError):
        client.get_file(path, MAIN_SHA)
    assert gh.writes() == before


def test_oversized_file_is_refused(gh):
    settings = GitHubSettings(token="github_pat_" + "x" * 40, demo_repo=DEMO, product_repo="team/product",
                              max_file_bytes=1000)
    with GitHubRepoClient(settings, transport=httpx.MockTransport(gh)) as c:
        c.create_branch("aew/big", MAIN_SHA)
        with pytest.raises(GitHubScopeError, match="larger"):
            c.commit_files("aew/big", "m", {"big.txt": "x" * 2000})


def test_empty_commit_and_message_are_refused(client):
    client.create_branch("aew/fix-3", MAIN_SHA)
    with pytest.raises(GitHubScopeError):
        client.commit_files("aew/fix-3", "m", {})
    with pytest.raises(GitHubScopeError):
        client.commit_files("aew/fix-3", "  ", {"a.txt": "x"})


def test_api_errors_are_typed_and_carry_no_token(client):
    with pytest.raises(GitHubAPIError) as info:
        client.get_branch_sha("does-not-exist")
    assert info.value.status_code == 404
    assert "github_pat_" not in str(info.value)
    client.create_branch("aew/dup", MAIN_SHA)
    with pytest.raises(GitHubAPIError) as dup:
        client.create_branch("aew/dup", MAIN_SHA)
    assert dup.value.status_code == 422


def test_bad_prefix_setting_is_rejected():
    with pytest.raises(Exception):
        GitHubSettings(token="t", demo_repo=DEMO, agent_branch_prefix="")
    with pytest.raises(Exception):
        GitHubSettings(token="t", demo_repo=DEMO, agent_branch_prefix="main")
