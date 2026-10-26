"""ENG-005 GitHub preflight: mocked GitHub API, no network."""

import httpx
import pytest

from app.modules.github.config import GitHubConfigError, GitHubSettings
from app.modules.github.preflight import render_markdown, run_preflight

DEMO = "team/demo-target"
PRODUCT = "team/product"
FINE = "github_pat_" + "x" * 40


def make_settings(token: str = FINE, **kw) -> GitHubSettings:
    return GitHubSettings(token=token, demo_repo=DEMO, product_repo=PRODUCT, **kw)


def make_handler(
    *,
    scopes: str | None = None,
    demo_status: int = 200,
    demo_perms: dict | None = None,
    product_status: int = 404,
    product_perms: dict | None = None,
    protected: bool = True,
    calls: list | None = None,
):
    demo_perms = {"push": True, "admin": False} if demo_perms is None else demo_perms

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append((request.method, request.url.path))
        assert request.headers["Authorization"].startswith("Bearer ")
        path = request.url.path
        if path == "/user":
            headers = {"x-oauth-scopes": scopes} if scopes is not None else {}
            return httpx.Response(200, json={"login": "m5-bot"}, headers=headers)
        if path == f"/repos/{DEMO}":
            return httpx.Response(
                demo_status,
                json={"private": False, "archived": False, "default_branch": "main", "permissions": demo_perms},
            )
        if path == f"/repos/{PRODUCT}":
            return httpx.Response(product_status, json={"permissions": product_perms or {}})
        if path == f"/repos/{DEMO}/branches/main":
            return httpx.Response(200, json={"protected": protected})
        if path == "/rate_limit":
            return httpx.Response(200, json={"resources": {"core": {"remaining": 4990, "limit": 5000}}})
        if path == f"/repos/{DEMO}/git/ref/heads/main":
            return httpx.Response(200, json={"object": {"sha": "a" * 40}})
        if path == f"/repos/{DEMO}/git/refs" and request.method == "POST":
            return httpx.Response(201, json={})
        if path.startswith(f"/repos/{DEMO}/git/refs/heads/aew-preflight/") and request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(500, json={"unexpected": path})

    return handler


def statuses(report) -> dict[str, str]:
    return {c.name: c.status for c in report.checks}


def test_happy_path_is_read_only_by_default():
    calls: list = []
    report = run_preflight(make_settings(), transport=httpx.MockTransport(make_handler(calls=calls)))
    assert report.passed
    s = statuses(report)
    assert s["token kind"] == "pass"
    assert s["demo repo"] == "pass"
    assert s["product repo isolation"] == "pass"
    assert s["contents write"] == "skip"
    assert all(method == "GET" for method, _ in calls)


def test_write_probe_creates_and_deletes_a_branch():
    calls: list = []
    report = run_preflight(
        make_settings(), write_probe=True, transport=httpx.MockTransport(make_handler(calls=calls))
    )
    assert statuses(report)["contents write"] == "pass"
    methods = [m for m, _ in calls]
    assert methods.count("POST") == 1 and methods.count("DELETE") == 1


def test_classic_token_with_repo_scope_fails():
    report = run_preflight(
        make_settings(token="ghp_" + "y" * 36),
        transport=httpx.MockTransport(make_handler(scopes="repo, workflow")),
    )
    assert not report.passed
    assert statuses(report)["token kind"] == "fail"


def test_writable_product_repo_fails():
    handler = make_handler(product_status=200, product_perms={"push": True})
    report = run_preflight(make_settings(), transport=httpx.MockTransport(handler))
    assert not report.passed
    assert statuses(report)["product repo isolation"] == "fail"


def test_demo_repo_without_push_fails():
    handler = make_handler(demo_perms={"push": False})
    report = run_preflight(make_settings(), transport=httpx.MockTransport(handler))
    assert statuses(report)["demo repo"] == "fail"


def test_missing_demo_repo_fails_and_skips_write_probe():
    handler = make_handler(demo_status=404)
    report = run_preflight(make_settings(), write_probe=True, transport=httpx.MockTransport(handler))
    s = statuses(report)
    assert s["demo repo"] == "fail"
    assert s["contents write"] == "skip"


def test_unprotected_default_branch_is_a_warning():
    report = run_preflight(make_settings(), transport=httpx.MockTransport(make_handler(protected=False)))
    assert report.passed
    assert statuses(report)["demo default branch"] == "warn"


def test_demo_equal_to_product_is_rejected():
    with pytest.raises(Exception):
        GitHubSettings(token=FINE, demo_repo=PRODUCT, product_repo=PRODUCT)


def test_from_env_requires_token_and_demo(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_DEMO_REPO", DEMO)
    monkeypatch.setattr(GitHubSettings, "model_config", {**GitHubSettings.model_config, "env_file": None})
    with pytest.raises(GitHubConfigError):
        GitHubSettings.from_env()


def test_evidence_never_contains_token():
    settings = make_settings()
    report = run_preflight(settings, transport=httpx.MockTransport(make_handler()))
    assert settings.bearer_token() not in render_markdown(report)
