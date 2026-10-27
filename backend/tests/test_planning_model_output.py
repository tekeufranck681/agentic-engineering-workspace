"""Planning tolerates unambiguous model-output variants (sizes, dependency titles)."""

import pytest

from app.domain.enums import TaskSize
from app.modules.planning.service import LLMTaskDecomposition, LLMTaskSpec, normalize_size, resolve_dependency
from tests.modules.planning.test_service import make_plan_setup, make_service


@pytest.mark.parametrize("raw,expected", [("M", TaskSize.m), (" small ", TaskSize.s), ("Large", TaskSize.m), ("xs", TaskSize.xs), ("Extra-Small", TaskSize.xs)])
def test_sizes_normalize(raw, expected):
    assert normalize_size(raw) == expected


def test_unknown_size_is_still_rejected():
    with pytest.raises(ValueError):
        normalize_size("huge-ish")


def test_dependencies_resolve_by_loose_title_or_id():
    ids = {"Create users table": "TASK-001", "Add login API": "TASK-002"}
    assert resolve_dependency("create users table.", ids) == "TASK-001"
    assert resolve_dependency("task-002", ids) == "TASK-002"
    assert resolve_dependency("Something else", ids) is None


async def test_decompose_accepts_variant_output_and_drops_self_and_duplicate_deps():
    pid, arch_id, repo = await make_plan_setup()
    response = {"LLMTaskDecomposition": LLMTaskDecomposition(tasks=[
        LLMTaskSpec(title="Create users table", description="d", size="Medium"),
        LLMTaskSpec(title="Add login API", description="d", size="L",
                    depends_on_titles=["create users table", "Create Users Table", "Add login API"]),
    ])}
    tasks = await make_service(response, repo).decompose(pid, arch_id)
    assert [t.size for t in tasks] == [TaskSize.m, TaskSize.m]
    assert tasks[1].depends_on == [tasks[0].id]
