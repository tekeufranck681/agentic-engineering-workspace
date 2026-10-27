"""ENG-042 smoke CLI tests: exit codes, evidence writing and the leak guard.

The CLI itself is the live operator entry point; here its service is replaced
with mocked reports so no network is involved.
"""

import json

from app.modules.integrations import smoke
from app.modules.integrations.schemas import (
    METERLESS_ENGINE,
    NIGHTSHIFT,
    ZETARIS,
    HealthStatus,
    SponsorHealthCheck,
    SponsorHealthReport,
)
from datetime import datetime, timezone


def _report(status: HealthStatus) -> SponsorHealthReport:
    return SponsorHealthReport(
        generated_at=datetime(2026, 10, 27, tzinfo=timezone.utc),
        overall=status,
        checks=[
            SponsorHealthCheck.build(ZETARIS, status, detail="d1"),
            SponsorHealthCheck.build(NIGHTSHIFT, status, detail="d2"),
            SponsorHealthCheck.build(METERLESS_ENGINE, status, detail="d3"),
            SponsorHealthCheck.build("cursor", HealthStatus.NOT_CHECKED, detail="build provenance"),
        ],
    )


def _patch_service(monkeypatch, report) -> None:
    class _FakeService:
        def run_all(self, *, include_chat: bool = False) -> SponsorHealthReport:
            return report

    monkeypatch.setattr(smoke.SponsorHealthService, "default", staticmethod(lambda: _FakeService()))


def test_smoke_exits_zero_when_all_runtime_sponsors_verified(monkeypatch, capsys):
    _patch_service(monkeypatch, _report(HealthStatus.VERIFIED))
    code = smoke.main([])
    out = capsys.readouterr().out
    assert code == 0
    assert "SMOKE OK" in out
    assert "verified" in out


def test_smoke_exits_one_when_not_configured(monkeypatch):
    _patch_service(monkeypatch, _report(HealthStatus.NOT_CHECKED))
    assert smoke.main([]) == 1


def test_smoke_exits_two_when_unavailable(monkeypatch):
    _patch_service(monkeypatch, _report(HealthStatus.UNAVAILABLE))
    assert smoke.main([]) == 2


def test_smoke_writes_sanitized_markdown_evidence(monkeypatch, tmp_path, capsys):
    report = _report(HealthStatus.VERIFIED)
    _patch_service(monkeypatch, report)
    target = tmp_path / "sponsor-health.md"
    code = smoke.main(["--evidence-out", str(target)])
    assert code == 0
    text = target.read_text(encoding="utf-8")
    assert "SPONSOR_READY evidence" in text
    assert "`verified`" in text
    assert "not_checked" in text  # cursor row documented honestly
    captured = capsys.readouterr()
    assert "evidence written" in captured.err


def test_smoke_json_flag_emits_machine_readable_report(monkeypatch, capsys):
    _patch_service(monkeypatch, _report(HealthStatus.VERIFIED))
    code = smoke.main(["--json"])
    assert code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)  # pure JSON, no trailing human lines
    assert payload["overall"] == "verified"
    assert len(payload["checks"]) == 4
    assert "SMOKE OK" not in captured.out


def test_evidence_leak_guard_refuses_to_write(monkeypatch, tmp_path):
    secret = "rt-leaking-secret"
    report = _report(HealthStatus.VERIFIED)
    report.checks[0].detail = f"failure mentioning {secret}"
    _patch_service(monkeypatch, report)
    monkeypatch.setenv("NIGHTSHIFT_TOKEN", secret)
    target = tmp_path / "must-not-exist.md"
    code = smoke.main(["--evidence-out", str(target)])
    assert code == 2
    assert not target.exists()
