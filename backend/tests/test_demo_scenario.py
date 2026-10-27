"""ENG-050 demo scenario: deterministic repo and seeded engineering state.

The demo repo's own tests run for real (pytest in a copy of demo/aew-demo-target);
the seed is written to the test database through M2's persistence and read back
through M4's planning/runs services and M3's ContextBuilder.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.domain.enums import ArtifactKind, RunStatus
from app.modules.context.builder import ContextBuilder
from app.modules.demo.scenario import (
    AC_001_TEST,
    AC_002_TEST,
    EXPECTED_FAILURE,
    REFERENCE_FIX,
    TARGET_FILE,
    seed,
)
from app.modules.github.client import FileContent, RepoInfo
from app.modules.persistence.errors import DuplicateProjectNameError
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.planning.service import PlanningService
from app.modules.runs.service import RunsService
from app.modules.tools.builtin import register_builtin_tools
from app.modules.tools.gateway import ToolGateway

DEMO = Path(__file__).resolve().parents[2] / "demo" / "aew-demo-target"
REPO = "rickrick3/aew-demo-target"


def pytest_in(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-rf", "-p", "no:cacheprovider", *args],
                          cwd=root, capture_output=True, text=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


@pytest.fixture()
def demo_copy(tmp_path) -> Path:
    target = tmp_path / "aew-demo-target"
    shutil.copytree(DEMO, target, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    return target


def test_before_the_fix_exactly_the_ac_001_pending_case_fails(demo_copy):
    result = pytest_in(demo_copy)
    assert result.returncode == 1, result.stdout
    failed = [line.split(" ", 1)[1].split(" - ")[0] for line in result.stdout.splitlines() if line.startswith("FAILED ")]
    assert failed == [EXPECTED_FAILURE]
    assert "1 failed, 6 passed" in result.stdout


def test_the_reference_fix_makes_every_test_pass(demo_copy):
    target = demo_copy / TARGET_FILE
    old, new = REFERENCE_FIX
    source = target.read_text(encoding="utf-8")
    assert source.count(old) == 1
    target.write_text(source.replace(old, new), encoding="utf-8", newline="")
    result = pytest_in(demo_copy)
    assert result.returncode == 0 and "7 passed" in result.stdout, result.stdout


@pytest.mark.parametrize("selector", [AC_001_TEST, AC_002_TEST])
def test_every_ac_names_a_test_that_exists(demo_copy, selector):
    result = pytest_in(demo_copy, "--collect-only", selector)
    assert result.returncode == 0 and selector.split("::")[1] in result.stdout


class DemoGitHub:
    """The demo repo served from the versioned folder, as the GitHub adapter would."""

    def __init__(self, root: Path = DEMO):
        self.files = {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
                      for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}

    def get_repo(self):
        return RepoInfo(full_name=REPO, default_branch="main", private=False, html_url=f"https://github.com/{REPO}")

    def get_branch_sha(self, branch):
        return "a" * 40

    def list_files(self, ref):
        return list(self.files)

    def get_file(self, path, ref):
        return FileContent(path=path, ref=ref, blob_sha="b" * 40, text=self.files[path])


async def test_seed_gives_a_runnable_task_with_context(session):
    scenario = await seed(session, REPO)
    repo = SqlAlchemyArtifactRepository(session)
    pid = scenario.project_id
    assert scenario.task_id == "TASK-002" and scenario.acceptance_criteria == ["AC-001", "AC-002"]

    # ENG-044: a run starts and its payload carries both ACs with their tests
    runs = RunsService(repo)
    run = await runs.start_run(pid, "TASK-002")
    assert (run.id, run.status) == ("RUN-001", RunStatus.queued)
    payload = await runs.get_start_payload(pid, run.id)
    assert [(ac.id, ac.verification.hint) for ac in payload.acceptance_criteria] == [
        ("AC-001", AC_001_TEST), ("AC-002", AC_002_TEST)]
    assert [c.id for c in payload.contracts] == ["CON-001"]

    # ENG-023: the context builder accepts the locked state and finds the target and its tests
    builder = ContextBuilder(repo, tools=register_builtin_tools(ToolGateway()), github=DemoGitHub())
    manifest = await builder.build(pid, "TASK-002", run_id=run.id)
    assert [r.pin.id for r in manifest.requirements] == ["REQ-001"]
    assert [c.pin.id for c in manifest.acceptance_criteria] == ["AC-001", "AC-002"]
    assert manifest.relevant_files[0].path == TARGET_FILE
    assert "tests/test_service.py" in [t.path for t in manifest.relevant_tests]

    # counters continue after the seeded ids
    assert await repo.next_id(pid, ArtifactKind.task) == "TASK-003"


async def test_seeding_twice_is_refused(session):
    await seed(session, REPO)
    with pytest.raises(DuplicateProjectNameError):
        await seed(session, REPO)


async def test_status_changes_work_on_the_real_sql_repository(session):
    scenario = await seed(session, REPO)
    repo = SqlAlchemyArtifactRepository(session)
    pid = scenario.project_id
    assert await PlanningService(llm=None, repo=repo).check_readiness(pid, "TASK-002") == ("ready", [])
    run = await RunsService(repo).start_run(pid, "TASK-002")
    await RunsService(repo).transition(pid, run.id, "running")
    await PlanningService(llm=None, repo=repo).update_task_status(pid, "TASK-002", "running")
