"""Tests for readable IDs and content hashing."""

from pydantic import BaseModel, ValidationError

from app.domain.ids import format_id, parse_id, ReadableId
from app.domain.hashing import canonical_json, content_hash, hash_model


def test_format_id_zero_padded():
    assert format_id("REQ", 1) == "REQ-001"
    assert format_id("TASK", 42) == "TASK-042"
    assert format_id("ARCH", 999) == "ARCH-999"
    assert format_id("CON", 1000) == "CON-1000"


def test_parse_id_round_trip():
    assert parse_id("REQ-001") == ("REQ", 1)
    assert parse_id("TASK-042") == ("TASK", 42)
    assert parse_id("ARCH-999") == ("ARCH", 999)
    assert parse_id("CON-1000") == ("CON", 1000)


def test_parse_id_rejects_bad_ids():
    for bad in ["REQ-1", "req-001", "REQ-00", "REQ-abc", "REQ"]:
        try:
            parse_id(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected ValueError for {bad!r}")


def test_readable_id_accepts_valid():
    m = _ModelWithReadableId(id="REQ-001")
    assert m.id == "REQ-001"


def test_readable_id_rejects_invalid():
    for bad in ["REQ-1", "req-001", "REQ-00"]:
        try:
            _ModelWithReadableId(id=bad)
        except ValidationError:
            pass
        else:
            raise AssertionError(f"Expected ValidationError for {bad!r}")


def test_canonical_json_sort_keys():
    a = canonical_json({"b": 2, "a": 1})
    b = canonical_json({"a": 1, "b": 2})
    assert a == b
    assert a == '{"a":1,"b":2}'


def test_canonical_json_separators():
    out = canonical_json({"a": [1, 2], "b": {"x": 1}})
    assert " " not in out


def test_content_hash_deterministic():
    h1 = content_hash({"a": 1, "b": 2})
    h2 = content_hash({"b": 2, "a": 1})
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_content_hash_changes_with_content():
    h1 = content_hash({"a": 1})
    h2 = content_hash({"a": 2})
    assert h1 != h2


def test_hash_model_excludes_default_fields():
    class M(BaseModel):
        name: str
        status: str = "draft"
        content_hash: str | None = None
        created_at: str = "2026-01-01T00:00:00Z"

    m1 = M(name="x", status="draft", content_hash="old", created_at="2026-01-01T00:00:00Z")
    m2 = M(name="x", status="locked", content_hash="new", created_at="2026-01-02T00:00:00Z")
    assert hash_model(m1) == hash_model(m2)


def test_hash_model_changes_with_content():
    class M(BaseModel):
        name: str
        value: int

    m1 = M(name="x", value=1)
    m2 = M(name="x", value=2)
    assert hash_model(m1) != hash_model(m2)


def test_hash_model_excludes_extra_fields():
    class M(BaseModel):
        name: str
        readiness: str | None = None
        blocking_reasons: list[str] = []

    m1 = M(name="x", readiness="ready", blocking_reasons=["a"])
    m2 = M(name="x", readiness="blocked", blocking_reasons=["b"])
    assert hash_model(m1, exclude={"readiness", "blocking_reasons"}) == hash_model(
        m2, exclude={"readiness", "blocking_reasons"}
    )


class _ModelWithReadableId(BaseModel):
    id: ReadableId
