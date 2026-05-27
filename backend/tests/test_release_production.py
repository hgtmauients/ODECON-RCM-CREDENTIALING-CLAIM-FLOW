import json
import subprocess
import sys
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


def test_run_public_cors_preflight_guard_detects_missing_header(monkeypatch):
    class _Resp:
        status = 204
        headers = {
            "Access-Control-Allow-Origin": "https://www.noodledoc.com",
            "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Tenant-ID",
        }

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(rp.urllib.request, "urlopen", lambda *_args, **_kwargs: _Resp())
    out = rp._run_public_cors_preflight_guard(
        api_base_url="https://api.noodledoc.com",
        web_origin="https://www.noodledoc.com",
        path="/api/credentialing/manual",
        required_headers=["content-type", "authorization", "x-csrf-token"],
    )
    assert out["ok"] is False
    assert "x-csrf-token" in out["missing_headers"]


def test_run_public_cors_preflight_guard_passes_with_required_headers(monkeypatch):
    class _Resp:
        status = 204
        headers = {
            "Access-Control-Allow-Origin": "https://www.noodledoc.com",
            "Access-Control-Allow-Headers": "Authorization, Content-Type, X-CSRF-Token, X-Tenant-ID",
        }

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(rp.urllib.request, "urlopen", lambda *_args, **_kwargs: _Resp())
    out = rp._run_public_cors_preflight_guard(
        api_base_url="https://api.noodledoc.com",
        web_origin="https://www.noodledoc.com",
        path="/api/credentialing/manual",
        required_headers=["content-type", "authorization", "x-csrf-token"],
    )
    assert out["ok"] is True
    assert out["missing_headers"] == []


def test_run_security_gate_raises_on_failure(monkeypatch):
    def fake_run(cmd, *, cwd=None, capture_output=False):
        return _cp(1, stderr="failed")

    monkeypatch.setattr(rp, "_run", fake_run)
    try:
        rp._run_security_gate(Path("C:/tmp"))
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "predeploy security gate failed" in str(exc)


def test_run_security_gate_includes_hardening_regression_suites(monkeypatch):
    seen = {}

    def fake_run(cmd, *, cwd=None, capture_output=False):
        seen["cmd"] = cmd
        return _cp(0, stdout="ok")

    monkeypatch.setattr(rp, "_run", fake_run)
    rp._run_security_gate(Path("C:/tmp"))
    cmd = " ".join(seen["cmd"])
    assert "test_auth_revalidation.py" in cmd
    assert "test_csrf_cookie_guard.py" in cmd
    assert "test_outbound_guard.py" in cmd
    assert "test_payer_role_gates.py" in cmd
    assert "test_audit_helper.py" in cmd
    assert "test_cors_runtime_policy.py" in cmd
    assert "test_tenant_isolation_http.py" in cmd
    assert "test_tenant_escape_vectors.py" in cmd
    assert "test_rate_limit_keying.py" in cmd
    assert "test_verify_production_canary.py" in cmd
    assert "test_change_password_tenant_scope.py" in cmd
    assert "test_secondary_service_tenant_scope.py" in cmd
    assert "test_rules_engine_tenant_scope.py" in cmd


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


def test_ensure_release_ref_integrity_rejects_non_main_branch(monkeypatch):
    def fake_run(cmd, *, cwd=None, capture_output=False):
        if cmd[:4] == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return _cp(0, stdout="feature/tenant-fix\n")
        return _cp(0, stdout="abc123\n")

    monkeypatch.setattr(rp, "_run", fake_run)
    try:
        rp._ensure_release_ref_integrity(Path("C:/tmp"))
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "local main" in str(exc)


def test_ensure_release_ref_integrity_rejects_head_mismatch(monkeypatch):
    def fake_run(cmd, *, cwd=None, capture_output=False):
        if cmd[:4] == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return _cp(0, stdout="main\n")
        if cmd == ["git", "rev-parse", "HEAD"]:
            return _cp(0, stdout="111\n")
        if cmd == ["git", "rev-parse", "main"]:
            return _cp(0, stdout="222\n")
        return _cp(1, stderr="unexpected command")

    monkeypatch.setattr(rp, "_run", fake_run)
    try:
        rp._ensure_release_ref_integrity(Path("C:/tmp"))
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "does not match local main" in str(exc)


def test_main_runs_slo_gate_before_deploy(monkeypatch, tmp_path):
    order: list[str] = []
    monkeypatch.setattr(rp, "_repo_root_from_script", lambda: tmp_path)
    (tmp_path / "webapp").mkdir()
    monkeypatch.setattr(rp, "_ensure_git_clean", lambda _repo: order.append("clean"))
    monkeypatch.setattr(rp, "_ensure_release_ref_integrity", lambda _repo: order.append("ref"))
    monkeypatch.setattr(rp, "_run_security_gate", lambda _repo: order.append("security"))
    monkeypatch.setattr(
        rp,
        "_run_slo_review_gate",
        lambda *_args, **_kwargs: (order.append("slo"), {"ok": True})[1],
    )
    monkeypatch.setattr(rp, "_create_deploy_archive", lambda _repo: (order.append("archive"), tmp_path / "bundle.tar.gz")[1])
    monkeypatch.setattr(rp, "_upload_and_extract_archive", lambda *_args, **_kwargs: order.append("upload"))
    monkeypatch.setattr(rp, "_run_remote_env_contract_gate", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(rp, "_deploy_backend", lambda **_kwargs: order.append("deploy"))
    monkeypatch.setattr(rp, "_run_post_deploy_smoke", lambda _server: {"ok": True})
    monkeypatch.setattr(
        rp,
        "_run_route_smoke",
        lambda _server: {"ok": True, "checks": [{"url": "http://127.0.0.1:8000/health", "expected": 200, "actual": 200}]},
    )
    monkeypatch.setattr(
        rp,
        "_run_public_cors_preflight_guard",
        lambda **_kwargs: {"ok": True, "missing_headers": []},
    )
    monkeypatch.setattr(rp, "_run_error_rate_guard", lambda *_args, **_kwargs: {"ok": True, "error_lines": 0})
    monkeypatch.setattr(rp, "_run_canary", lambda **_kwargs: {"go": True})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_production.py",
            "--skip-git-push",
            "--skip-vercel",
            "--skip-frontend-gate",
            "--break-glass-ticket",
            "TEST-123",
        ],
    )

    rc = rp.main()
    assert rc == 0
    assert order.index("slo") < order.index("deploy")


def test_main_skip_canary_marks_partial_and_returns_no_go(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(rp, "_repo_root_from_script", lambda: tmp_path)
    (tmp_path / "webapp").mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_production.py",
            "--allow-dirty",
            "--skip-git-push",
            "--skip-vercel",
            "--skip-hetzner",
            "--skip-security-gate",
            "--skip-frontend-gate",
            "--skip-post-smoke",
            "--skip-route-smoke",
            "--skip-cors-preflight-guard",
            "--skip-error-rate-guard",
            "--skip-slo-review-gate",
            "--skip-canary",
            "--break-glass-ticket",
            "TEST-123",
        ],
    )

    rc = rp.main()
    payload = json.loads(capsys.readouterr().out)
    assert rc == 10
    assert payload["partial"] is True
    assert payload["go"] is False


def test_remote_env_contract_gate_parses_missing_values(monkeypatch):
    def fake_run(cmd, *, cwd=None, capture_output=False):
        return _cp(
            0,
            stdout=json.dumps({"ok": False, "missing_keys": ["REDIS_PASSWORD"], "compose_ok": False}),
        )

    monkeypatch.setattr(rp, "_run", fake_run)
    out = rp._run_remote_env_contract_gate(
        "root@host",
        remote_dir="/opt/noodledoc",
        required_keys=["POSTGRES_PASSWORD", "REDIS_PASSWORD"],
    )
    assert out["ok"] is False
    assert out["missing_keys"] == ["REDIS_PASSWORD"]


def test_validate_release_contract_rejects_missing_route_checks():
    class _Args:
        skip_security_gate = False
        skip_frontend_gate = False
        skip_slo_review_gate = False
        skip_git_push = False
        skip_vercel = False
        skip_hetzner = False
        skip_post_smoke = False
        skip_route_smoke = False
        skip_cors_preflight_guard = False
        skip_error_rate_guard = False
        skip_canary = False

    payload = {
        "security_gate": "ok",
        "frontend_gate": "ok",
        "slo_review_gate": {"ok": True},
        "git_push": "ok",
        "vercel_url": "https://example.vercel.app",
        "hetzner_deploy": "ok",
        "env_contract_gate": {"ok": True},
        "post_deploy_smoke": {"ok": True},
        "route_smoke": {"ok": True, "checks": []},
        "cors_preflight_guard": {"ok": True},
        "error_rate_guard": {"ok": True, "error_lines": 0},
        "canary": {"go": True},
        "partial": False,
        "go": True,
    }
    try:
        rp._validate_release_contract(payload, _Args())
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "route_smoke checks required" in str(exc)


def test_main_rejects_allow_dirty_when_backend_deploy_enabled(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(rp, "_repo_root_from_script", lambda: tmp_path)
    (tmp_path / "webapp").mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_production.py",
            "--allow-dirty",
            "--skip-git-push",
            "--skip-vercel",
        ],
    )

    rc = rp.main()
    payload = json.loads(capsys.readouterr().out)
    assert rc == 10
    assert "allow-dirty" in payload["error"]
