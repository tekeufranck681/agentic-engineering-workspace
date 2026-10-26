"""ENG-004 content hashing for artifacts."""

import hashlib
import json
from collections.abc import Iterable
from typing import Any


def canonical_json(payload: dict) -> str:
    """Serialize `payload` to deterministic JSON.

    Keys are sorted, whitespace is minimal, and non-ASCII is preserved.
    UUIDs and other non-standard types are converted via str().
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def content_hash(payload: dict) -> str:
    """Return `sha256:` prefixed digest of the canonical JSON."""
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def hash_model(model: Any, exclude: Iterable[str] = ()) -> str:
    """Hash a Pydantic model's field values.

    Always excludes `content_hash`, `created_at`, and `status`. Additional
    field names may be passed via `exclude`.
    """
    default_exclude = {"content_hash", "created_at", "status"}
    full_exclude = default_exclude | set(exclude)
    data = model.model_dump(exclude=full_exclude)
    return content_hash(data)
