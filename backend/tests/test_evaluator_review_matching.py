"""Review findings match criteria however the model echoes their ids; empty reviews are rejected."""

import pytest
from pydantic import ValidationError

from app.modules.evaluation.capability import EvaluationReview, ReviewFinding
from app.modules.evaluation.evaluator import index_findings


def _f(ac_id: str, action: str = "keep") -> ReviewFinding:
    return ReviewFinding(acceptance_criterion_id=ac_id, action=action, reason="r")


def test_ids_are_normalized():
    found = index_findings([_f("AC-001 v1"), _f("ac-002@v2", "fail"), _f("criterion AC-003")], ["AC-001", "AC-002", "AC-003"])
    assert {k: v.action for k, v in found.items()} == {"AC-001": "keep", "AC-002": "fail", "AC-003": "keep"}


def test_unknown_ids_and_duplicates_are_ignored():
    found = index_findings([_f("AC-009"), _f("AC-001"), _f("AC-001", "fail")], ["AC-001"])
    assert list(found) == ["AC-001"] and found["AC-001"].action == "keep"


def test_an_empty_review_is_invalid_so_the_runtime_repairs_it():
    with pytest.raises(ValidationError):
        EvaluationReview.model_validate({})
    with pytest.raises(ValidationError):
        EvaluationReview.model_validate({"findings": []})
