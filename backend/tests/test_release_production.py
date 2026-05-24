import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts import release_production as rp


def _cp(returncode: int, *, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["cmd"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_canary_parses_embedded_json(monkeypatch):
    payload = {"go": True, "run_id": "abc123"}
    stdout = f"noise before\n{json.dumps(payload)}\nnoise after"

    def fake_run(cmd, *, cwd=None, capture_output=False):
        return _cp(0, stdout=stdout)

    monkeypatch.setattr(rp, "_run", fake_run)
    out = rp._run_canary(server="root@host", tenant="tenant-1")
    assert out["go"] is True
    assert out["run_id"] == "abc123"


def test_run_error_rate_guard_passes_below_threshold(monkeypatch):
    def fake_run(cmd, *, cwd=None, capture_output=False):
        return _cp(0, stdout="3\n")

    monkeypatch.setattr(rp, "_run", fake_run)
    out = rp._run_error_rate_guard("root@host", window_minutes=10, max_error_lines=5)
    assert out["ok"] is True
    assert out["error_lines"] == 3


def test_run_error_rate_guard_fails_above_threshold(monkeypatch):
    def fake_run(cmd, *, cwd=None, capture_output=False):
        return _cp(0, stdout="42\n")

    monkeypatch.setattr(rp, "_run", fake_run)
    out = rp._run_error_rate_guard("root@host", window_minutes=10, max_error_lines=5)
    assert out["ok"] is False
    assert out["error_lines"] == 42


def test_run_route_smoke_parses_json_payload(monkeypatch):
    payload = {"ok": True, "checks": [{"url": "/health", "expected": 200, "actual": 200}]}

    def fake_run(cmd, *, cwd=None, capture_output=False):
        return _cp(0, stdout=json.dumps(payload))

    monkeypatch.setattr(rp, "_run", fake_run)
    out = rp._run_route_smoke("root@host")
    assert out["ok"] is True
    assert out["checks"][0]["actual"] == 200


def test_run_security_gate_raises_on_failure(monkeypatch):
    def fake_run(cmd, *, cwd=None, capture_output=False):
        return _cp(1, stderr="failed")

    monkeypatch.setattr(rp, "_run", fake_run)
    try:
        rp._run_security_gate(Path("C:/tmp"))
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "predeploy security gate failed" in str(exc)


def test_slo_review_gate_passes_with_fresh_attestation(tmp_path):
    reviewed_at = datetime.now(timezone.utc).isoformat()
    attestation = tmp_path / "slo-review-attestation.json"
    attestation.write_text(
        json.dumps(
            {
                "reviewed_at_utc": reviewed_at,
                "reviewer": "platform-oncall@noodledoc.com",
                "summary": "SLO dashboard reviewed; error budget healthy.",
            }
        ),
        encoding="utf-8",
    )
    out = rp._run_slo_review_gate(
        tmp_path,
        attestation_path="slo-review-attestation.json",
        max_age_days=14,
    )
    assert out["ok"] is True


def test_slo_review_gate_fails_when_attestation_is_stale(tmp_path):
    reviewed_at = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    attestation = tmp_path / "slo-review-attestation.json"
    attestation.write_text(
        json.dumps(
            {
                "reviewed_at_utc": reviewed_at,
                "reviewer": "platform-oncall@noodledoc.com",
                "summary": "Old review",
            }
        ),
        encoding="utf-8",
    )
    out = rp._run_slo_review_gate(
        tmp_path,
        attestation_path="slo-review-attestation.json",
        max_age_days=14,
    )
    assert out["ok"] is False
