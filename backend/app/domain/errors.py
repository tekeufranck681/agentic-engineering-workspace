"""Errors raised by the ENG-004 domain layer."""


class TransitionError(Exception):
    """Raised when an artifact state transition is not allowed."""
