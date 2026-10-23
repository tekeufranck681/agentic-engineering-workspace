"""Domain errors of the persistence module.

Kept free of HTTP concerns; the router translates them to status codes.
"""


class PersistenceError(Exception):
    """Base class for persistence-module failures."""


class ProjectNotFoundError(PersistenceError):
    """Raised when a project id does not exist."""


class DuplicateProjectNameError(PersistenceError):
    """Raised when creating a project whose name is already taken."""


class BindingNotFoundError(PersistenceError):
    """Raised when a project has no (active) repository binding."""
