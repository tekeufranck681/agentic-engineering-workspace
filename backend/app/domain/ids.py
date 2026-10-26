"""ENG-004 readable IDs and parsing."""

import re
from typing import Annotated
from pydantic import Field

READABLE_ID_PATTERN = re.compile(r"^[A-Z]{2,5}-\d{3,}$")


def format_id(kind: str, n: int) -> str:
    """Return a readable ID like `REQ-001` (3+ digits, zero-padded)."""
    return f"{kind.upper()}-{n:03d}"


def parse_id(s: str) -> tuple[str, int]:
    """Split a readable ID into `(prefix, number)`.

    Raises `ValueError` if the ID does not match the pattern.
    """
    match = READABLE_ID_PATTERN.match(s)
    if not match:
        raise ValueError(f"Invalid readable ID: {s!r}")
    prefix, num_str = s.split("-", 1)
    return prefix, int(num_str)


ReadableId = Annotated[str, Field(pattern=READABLE_ID_PATTERN.pattern)]
