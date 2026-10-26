"""Tests for domain errors."""

from app.domain.errors import TransitionError


def test_transition_error_is_exception():
    err = TransitionError("bad transition")
    assert isinstance(err, Exception)
    assert str(err) == "bad transition"
