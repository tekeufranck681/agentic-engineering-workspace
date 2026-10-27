"""What the independent review (``evaluation.evaluate``) is asked, and its answer.

The contract (versioned instructions, tools, evidence) is registered with the
other §25 capabilities in ``capabilities/registry.py``. It is not the
implementer's prompt: the reviewer sees only criteria whose executable check
already passed, the test code of those checks and the diff, and answers keep,
fail or unverified per criterion. Failed and missing checks never reach it.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.acceptance_criterion import AcceptanceCriterion
from app.domain.task import Task
from app.modules.sandbox.provider import ChangeSet

MAX_DIFF_CHARS = 12_000
MAX_TEST_CODE_CHARS = 12_000


class ReviewFinding(BaseModel):
    acceptance_criterion_id: str
    action: Literal["keep", "fail", "unverified"] = Field(
        description="keep: the change implements the criterion and the check exercises it; "
        "fail: the diff clearly contradicts the criterion; unverified: the check does not "
        "really exercise the criterion, or you cannot tell"
    )
    reason: str = Field(min_length=1, max_length=600, description="One or two sentences; quote the line for fail")


class EvaluationReview(BaseModel):
    # At least one finding: an empty answer is unusable, so the runtime's
    # repair loop asks again instead of every criterion staying UNVERIFIED.
    findings: list[ReviewFinding] = Field(min_length=1)


def _bounded(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n[... truncated ...]"


def build_review_prompt(task: Task, passed: list[tuple[AcceptanceCriterion, list[str]]],
                        test_code: dict[str, str], diff: ChangeSet) -> str:
    """``passed``: each criterion with the selectors whose check passed in the sandbox."""
    lines = [f"Task {task.id} v{task.version}: {task.title}", task.description, "",
             "Acceptance criteria whose executable check passed in the sandbox:"]
    for ac, selectors in passed:
        lines += [f"- {ac.id} v{ac.version}: {ac.title}",
                  f"  Given: {'; '.join(ac.given)}",
                  f"  When: {'; '.join(ac.when)}",
                  f"  Then: {'; '.join(ac.then)}",
                  f"  Check (passed): {', '.join(selectors)}"]
    if test_code:
        lines += ["", "Test code of these checks:"]
        for path, text in test_code.items():
            lines += [f"--- {path} ---", text]
    base = (diff.base_sha or "unknown")[:12]
    lines += ["", f"Change under evaluation (git diff against base commit {base}):",
              _bounded(diff.patch, MAX_DIFF_CHARS) if diff.patch.strip() else "(no change)",
              "", "Return one finding per criterion listed above. Use the bare criterion id "
              "(for example AC-001) as acceptance_criterion_id."]
    return "\n".join(lines)
