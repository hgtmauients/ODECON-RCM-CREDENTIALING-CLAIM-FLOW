"""
Canonical production release orchestrator for ClaimFlow.

Runs, in order:
  1) (optional) git push to origin/main
  2) (optional) Vercel frontend deploy
  3) Hetzner backend sync (tarball upload/extract), rebuild/restart
  4) Alembic upgrade head on Hetzner backend container
  5) Production canary verifier with strict GO/NO-GO

Designed to run from a developer workstation (not inside containers).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_SERVER = (os.getenv("CLAIMFLOW_DEPLOY_SERVER", "") or "root@5.161.209.46").strip()
DEFAULT_REMOTE_DIR = (os.getenv("CLAIMFLOW_DEPLOY_REMOTE_DIR", "") or "/opt/noodledoc").strip()
DEFAULT_TENANT = "00000000-0000-0000-0000-000000000001"
CRITICAL_SKIP_FLAGS = (
    "skip_security_gate",
    "skip_post_smoke",
    "skip_route_smoke",
    "skip_error_rate_guard",
    "skip_canary",
    "skip_slo_review_gate",
    "skip_frontend_gate",
)


def _run(cmd: List[str], *, cwd: Path | None = None, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=capture_output,
        check=False,
    )


def _run_security_gate(repo_root: Path) -> None:
    gate = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "backend/tests/test_tenant_isolation_http.py",
            "backend/tests/test_tenant_escape_vectors.py",
            "backend/tests/test_startup_checks.py",
            "backend/tests/test_csv_export.py",
            "backend/tests/test_auth_error_messages.py",
            "backend/tests/test_csrf_cookie_guard.py",
            "backend/tests/test_auth_revalidation.py",
            "backend/tests/test_security_signal_logging.py",
            "backend/tests/test_rate_limit_keying.py",
            "backend/tests/test_rate_limit_security_signal_flow.py",
            "backend/tests/test_provider_adapter.py",
            "backend/tests/test_outbound_guard.py",
            "backend/tests/test_payer_role_gates.py",
            "backend/tests/test_audit_helper.py",
            "backend/tests/test_cors_runtime_policy.py",
            "backend/tests/test_verify_production_canary.py",
            "backend/tests/test_change_password_tenant_scope.py",
            "backend/tests/test_secondary_service_tenant_scope.py",
            "backend/tests/test_rules_engine_tenant_scope.py",
            "-v",
            "-W",
            "error::RuntimeWarning",
        ],
        cwd=repo_root,
    )
    if gate.returncode != 0:
        raise RuntimeError("predeploy security gate failed")


def _run_frontend_quality_gate(repo_root: Path) -> None:
    webapp_dir = repo_root / "webapp"
    npm_bin = shutil.which("npm") or shutil.which("npm.cmd") or "npm"
    commands = [
        [npm_bin, "ci"],
        [npm_bin, "run", "typecheck"],
        [npm_bin, "run", "test:coverage"],
        [npm_bin, "run", "test:coverage:all"],
        [npm_bin, "run", "e2e:smoke"],
        [npm_bin, "run", "e2e:visual"],
        [npm_bin, "run", "build"],
        [npm_bin, "run", "check:bundle-budget"],
    ]
    for cmd in commands:
        result = _run(cmd, cwd=webapp_dir)
        if result.returncode != 0:
            raise RuntimeError(f"frontend quality gate failed at: {' '.join(cmd)}")


def _run_remote_env_contract_gate(server: str, *, remote_dir: str, required_keys: List[str]) -> Dict[str, Any]:
    remote_script = f"""
import json
import pathlib
import subprocess

remote_dir = {json.dumps(remote_dir)}
required_keys = {json.dumps(required_keys)}
env_file = pathlib.Path(remote_dir) / ".env"
payload = {{"ok": False, "missing_keys": [], "compose_ok": False, "compose_error": ""}}

if not env_file.exists():
    payload["error"] = "missing .env"
    print(json.dumps(payload))
    raise SystemExit(0)

values = {{}}
for raw in env_file.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip()

missing = [k for k in required_keys if not values.get(k, "").strip()]
payload["missing_keys"] = missing

compose = subprocess.run(
    ["docker", "compose", "-f", "docker-compose.prod.yml", "config"],
    cwd=remote_dir,
    text=True,
    capture_output=True,
    check=False,
)
payload["compose_ok"] = compose.returncode == 0
payload["compose_error"] = (compose.stderr or "").strip()
payload["ok"] = payload["compose_ok"] and not missing
print(json.dumps(payload))
"""
    remote_cmd = f"python3 -c {shlex.quote(remote_script)}"
    result = _run(["ssh", server, remote_cmd], capture_output=True)
    payload: Dict[str, Any] = {
        "ok": False,
        "stdout": (result.stdout or "").strip(),
        "stderr": (result.stderr or "").strip(),
        "required_keys": required_keys,
    }
    if result.returncode != 0:
        return payload
    try:
        parsed = json.loads(payload["stdout"] or "{}")
        payload.update(parsed)
        payload["ok"] = bool(parsed.get("ok"))
        return payload
    except json.JSONDecodeError:
        return payload


def _run_post_deploy_smoke(server: str) -> Dict[str, Any]:
    smoke = _run(
        [
            "ssh",
            server,
            "docker exec noodledoc-backend-1 python -c \"import httpx; r=httpx.get('http://127.0.0.1:8000/health', timeout=5.0); print(r.status_code); raise SystemExit(0 if r.status_code==200 else 1)\"",
        ],
        capture_output=True,
    )
    return {
        "ok": smoke.returncode == 0,
        "stdout": (smoke.stdout or "").strip(),
        "stderr": (smoke.stderr or "").strip(),
    }


def _run_route_smoke(server: str) -> Dict[str, Any]:
    script = (
        "import json, httpx; checks=["
        "('http://127.0.0.1:8000/health', 200),"
        "('http://127.0.0.1:8000/api/auth/me', 401),"
        "('http://127.0.0.1:8000/api/rcm/payers', 401)"
        "]; results=[{'url':u,'expected':e,'actual':httpx.get(u, timeout=5.0).status_code} for (u,e) in checks]; "
        "ok=all(item['actual']==item['expected'] for item in results); "
        "print(json.dumps({'ok':ok,'checks':results}))"
    )
    route_check = _run(
        ["ssh", server, f"docker exec noodledoc-backend-1 python -c \"{script}\""],
        capture_output=True,
    )
    payload: Dict[str, Any] = {
        "ok": False,
        "stdout": (route_check.stdout or "").strip(),
        "stderr": (route_check.stderr or "").strip(),
    }
    if route_check.returncode != 0:
        return payload
    try:
        parsed = json.loads(payload["stdout"] or "{}")
        return {
            "ok": bool(parsed.get("ok")),
            "checks": parsed.get("checks", []),
            "stdout": payload["stdout"],
            "stderr": payload["stderr"],
        }
    except json.JSONDecodeError:
        return payload


def _run_error_rate_guard(server: str, *, window_minutes: int, max_error_lines: int) -> Dict[str, Any]:
    logs = _run(
        [
            "ssh",
            server,
            f"bash -lc \"docker logs --since {window_minutes}m noodledoc-backend-1 2>&1 | egrep -i 'ERROR|Traceback|Exception' | wc -l\"",
        ],
        capture_output=True,
    )
    raw = (logs.stdout or "").strip()
    try:
        error_lines = int(raw.splitlines()[-1]) if raw else -1
    except Exception:
        error_lines = -1
    ok = logs.returncode == 0 and error_lines >= 0 and error_lines <= max_error_lines
    return {
        "ok": ok,
        "window_minutes": window_minutes,
        "max_error_lines": max_error_lines,
        "error_lines": error_lines,
        "stdout": raw,
        "stderr": (logs.stderr or "").strip(),
    }


def _run_slo_review_gate(repo_root: Path, *, attestation_path: str, max_age_days: int) -> Dict[str, Any]:
    attestation_file = (repo_root / attestation_path).resolve()
    if not attestation_file.exists():
        return {
            "ok": False,
            "error": f"SLO attestation file missing: {attestation_path}",
        }

    try:
        payload = json.loads(attestation_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Failed to parse SLO attestation JSON: {exc}",
        }

    reviewed_at_raw = str(payload.get("reviewed_at_utc", "")).strip()
    reviewer = str(payload.get("reviewer", "")).strip()
    summary = str(payload.get("summary", "")).strip()
    if not reviewed_at_raw or not reviewer or not summary:
        return {
            "ok": False,
            "error": "SLO attestation requires reviewed_at_utc, reviewer, and summary",
        }

    try:
        reviewed_at = datetime.fromisoformat(reviewed_at_raw.replace("Z", "+00:00"))
        if reviewed_at.tzinfo is None:
            reviewed_at = reviewed_at.replace(tzinfo=timezone.utc)
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Invalid reviewed_at_utc format: {exc}",
        }

    age_days = (datetime.now(timezone.utc) - reviewed_at.astimezone(timezone.utc)).total_seconds() / 86400.0
    ok = age_days <= float(max_age_days)
    return {
        "ok": ok,
        "reviewed_at_utc": reviewed_at.astimezone(timezone.utc).isoformat(),
        "reviewer": reviewer,
        "summary": summary,
        "age_days": round(age_days, 3),
        "max_age_days": max_age_days,
    }


def _ensure_git_clean(repo_root: Path) -> None:
    status = _run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True)
    if status.returncode != 0:
        raise RuntimeError(f"git status failed:\n{status.stderr}")
    if status.stdout.strip():
        raise RuntimeError("Working tree is dirty. Commit/stash changes or use --allow-dirty.")


def _ensure_release_ref_integrity(repo_root: Path) -> None:
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root, capture_output=True)
    if branch.returncode != 0:
        raise RuntimeError(f"git rev-parse --abbrev-ref failed:\n{branch.stderr}")
    current_branch = (branch.stdout or "").strip()
    if current_branch != "main":
        raise RuntimeError(
            f"Releases must run from local main; current branch is '{current_branch}'."
        )

    head = _run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True)
    main = _run(["git", "rev-parse", "main"], cwd=repo_root, capture_output=True)
    if head.returncode != 0 or main.returncode != 0:
        raise RuntimeError("Unable to resolve git refs for release integrity check")

    head_sha = (head.stdout or "").strip()
    main_sha = (main.stdout or "").strip()
    if not head_sha or not main_sha or head_sha != main_sha:
        raise RuntimeError(
            "Release ref integrity failed: HEAD does not match local main. "
            "Checkout/update main before releasing."
        )


def _git_push(repo_root: Path) -> None:
    push = _run(["git", "push", "origin", "main"], cwd=repo_root)
    if push.returncode != 0:
        raise RuntimeError("git push failed")


def _vercel_deploy(webapp_dir: Path) -> str:
    vercel_bin = shutil.which("vercel") or shutil.which("vercel.cmd") or "vercel"
    deploy = _run([vercel_bin, "--prod", "--yes"], cwd=webapp_dir, capture_output=True)
    if deploy.returncode != 0:
        raise RuntimeError(f"vercel deploy failed:\n{deploy.stdout}\n{deploy.stderr}")
    output = deploy.stdout or ""
    match = re.search(r"(https://[a-zA-Z0-9.-]+\.vercel\.app)", output)
    return match.group(1) if match else ""


def _create_deploy_archive(repo_root: Path) -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix="claimflow_deploy_"))
    archive = tmp_dir / "deploy_bundle.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(repo_root / "backend", arcname="backend")
        tar.add(repo_root / "docker-compose.prod.yml", arcname="docker-compose.prod.yml")
    return archive


def _upload_and_extract_archive(archive: Path, *, server: str, remote_dir: str) -> None:
    remote_archive = f"/tmp/{archive.name}"
    scp = _run(["scp", str(archive), f"{server}:{remote_archive}"])
    if scp.returncode != 0:
        raise RuntimeError("scp upload failed")

    extract_cmd = (
        f"set -euo pipefail; "
        f"mkdir -p {remote_dir}; "
        f"tar -xzf {remote_archive} -C {remote_dir}; "
        f"for f in docker-entrypoint.sh backup-runner.sh; do "
        f"  tr -d '\\r' < {remote_dir}/backend/\\$f > /tmp/\\$f && "
        f"  mv /tmp/\\$f {remote_dir}/backend/\\$f && "
        f"  chmod +x {remote_dir}/backend/\\$f; "
        f"done; "
        f"rm -f {remote_archive}"
    )
    ssh = _run(["ssh", server, f"bash -lc \"{extract_cmd}\""])
    if ssh.returncode != 0:
        raise RuntimeError("remote extract/normalize failed")


def _deploy_backend(*, server: str, remote_dir: str) -> None:
    db_role_cmd = (
        f"set -euo pipefail; "
        f"cd {remote_dir}; "
        f"set -a; source .env; set +a; "
        f"APP_DB_USER=${{APP_DB_USER:-claimflow_app}}; "
        f"APP_DB_PASSWORD=${{APP_DB_PASSWORD:-$POSTGRES_PASSWORD}}; "
        f"APP_DB_NAME=${{POSTGRES_DB:-noodledoc}}; "
        f"docker compose -f docker-compose.prod.yml up -d postgres redis; "
        f"docker exec -i noodledoc-postgres-1 psql -U \"$POSTGRES_USER\" -d \"$APP_DB_NAME\" -v ON_ERROR_STOP=1 <<'SQL' "
        f"DO $$ "
        f"BEGIN "
        f"  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$APP_DB_USER') THEN "
        f"    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE INHERIT', '$APP_DB_USER', '$APP_DB_PASSWORD'); "
        f"  ELSE "
        f"    EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE INHERIT', '$APP_DB_USER', '$APP_DB_PASSWORD'); "
        f"  END IF; "
        f"END "
        f"$$; "
        f"GRANT CONNECT ON DATABASE \"$APP_DB_NAME\" TO \"$APP_DB_USER\"; "
        f"GRANT USAGE ON SCHEMA public TO \"$APP_DB_USER\"; "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO \"$APP_DB_USER\"; "
        f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO \"$APP_DB_USER\"; "
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO \"$APP_DB_USER\"; "
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO \"$APP_DB_USER\"; "
        f"SQL"
    )
    db_role_ssh = _run(["ssh", server, f"bash -lc \"{db_role_cmd}\""])
    if db_role_ssh.returncode != 0:
        raise RuntimeError("database app-role hardening failed")

    deploy_cmd = (
        f"set -euo pipefail; "
        f"cd {remote_dir}; "
        f"docker compose -f docker-compose.prod.yml up -d --build backend; "
        f"docker exec noodledoc-backend-1 alembic upgrade head"
    )
    ssh = _run(["ssh", server, f"bash -lc \"{deploy_cmd}\""])
    if ssh.returncode != 0:
        raise RuntimeError("backend rebuild/migration failed")


def _run_canary(*, server: str, tenant: str) -> Dict[str, Any]:
    canary_cmd = (
        "docker exec noodledoc-backend-1 "
        "python -m scripts.verify_production_canary "
        f"--tenant {tenant}"
    )
    result = _run(["ssh", server, canary_cmd], capture_output=True)
    if result.returncode not in (0, 10):
        raise RuntimeError(f"canary command failed:\n{result.stdout}\n{result.stderr}")

    raw = result.stdout.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError(f"Unable to parse canary JSON:\n{raw}")
    payload = json.loads(raw[start : end + 1])
    return payload


def _validate_release_contract(report: Dict[str, Any], args: argparse.Namespace) -> None:
    required = [
        "security_gate",
        "frontend_gate",
        "slo_review_gate",
        "git_push",
        "vercel_url",
        "hetzner_deploy",
        "env_contract_gate",
        "post_deploy_smoke",
        "route_smoke",
        "error_rate_guard",
        "canary",
    ]
    for key in required:
        if key not in report or report[key] is None:
            raise RuntimeError(f"release contract missing required field: {key}")

    if args.skip_security_gate:
        if report["security_gate"] != "skipped":
            raise RuntimeError("release contract violation: security_gate skip mismatch")
    elif report["security_gate"] != "ok":
        raise RuntimeError("release contract violation: security_gate must be ok")

    if args.skip_frontend_gate:
        if report["frontend_gate"] != "skipped":
            raise RuntimeError("release contract violation: frontend_gate skip mismatch")
    elif report["frontend_gate"] != "ok":
        raise RuntimeError("release contract violation: frontend_gate must be ok")

    if args.skip_slo_review_gate:
        if report["slo_review_gate"] != "skipped":
            raise RuntimeError("release contract violation: slo_review_gate skip mismatch")
    else:
        slo = report["slo_review_gate"]
        if not isinstance(slo, dict) or not slo.get("ok"):
            raise RuntimeError("release contract violation: slo_review_gate must be ok dict")

    if args.skip_git_push:
        if report["git_push"] != "skipped":
            raise RuntimeError("release contract violation: git_push skip mismatch")
    elif report["git_push"] != "ok":
        raise RuntimeError("release contract violation: git_push must be ok")

    if args.skip_vercel:
        if report["vercel_url"] != "skipped":
            raise RuntimeError("release contract violation: vercel skip mismatch")
    elif not isinstance(report["vercel_url"], str) or not report["vercel_url"].startswith("https://"):
        raise RuntimeError("release contract violation: vercel_url must be https URL")

    if args.skip_hetzner:
        if report["hetzner_deploy"] != "skipped":
            raise RuntimeError("release contract violation: hetzner skip mismatch")
        if report["env_contract_gate"] != "skipped":
            raise RuntimeError("release contract violation: env contract skip mismatch")
    else:
        if report["hetzner_deploy"] != "ok":
            raise RuntimeError("release contract violation: hetzner_deploy must be ok")
        env_gate = report["env_contract_gate"]
        if not isinstance(env_gate, dict) or not env_gate.get("ok"):
            raise RuntimeError("release contract violation: env_contract_gate must be ok dict")

    if args.skip_post_smoke:
        if report["post_deploy_smoke"] != "skipped":
            raise RuntimeError("release contract violation: post smoke skip mismatch")
    else:
        smoke = report["post_deploy_smoke"]
        if not isinstance(smoke, dict) or not smoke.get("ok"):
            raise RuntimeError("release contract violation: post_deploy_smoke must be ok dict")

    if args.skip_route_smoke:
        if report["route_smoke"] != "skipped":
            raise RuntimeError("release contract violation: route smoke skip mismatch")
    else:
        route = report["route_smoke"]
        if not isinstance(route, dict) or not route.get("ok"):
            raise RuntimeError("release contract violation: route_smoke must be ok dict")
        checks = route.get("checks", [])
        if not isinstance(checks, list) or len(checks) == 0:
            raise RuntimeError("release contract violation: route_smoke checks required")

    if args.skip_error_rate_guard:
        if report["error_rate_guard"] != "skipped":
            raise RuntimeError("release contract violation: error rate guard skip mismatch")
    else:
        guard = report["error_rate_guard"]
        if not isinstance(guard, dict) or not guard.get("ok"):
            raise RuntimeError("release contract violation: error_rate_guard must be ok dict")
        if not isinstance(guard.get("error_lines"), int) or guard["error_lines"] < 0:
            raise RuntimeError("release contract violation: error_rate_guard error_lines invalid")

    if args.skip_canary:
        if report["canary"] != "skipped":
            raise RuntimeError("release contract violation: canary skip mismatch")
        if report.get("partial") is not True or report.get("go") is not False:
            raise RuntimeError("release contract violation: skip-canary must be partial true and go false")
    else:
        canary = report["canary"]
        if not isinstance(canary, dict):
            raise RuntimeError("release contract violation: canary must be dict")
        if canary.get("go") is not True:
            raise RuntimeError("release contract violation: canary go must be true")
        if report.get("partial") is not False:
            raise RuntimeError("release contract violation: full release cannot be partial")


def _repo_root_from_script() -> Path:
    # backend/scripts/release_production.py -> repo root is two levels up
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonical ClaimFlow production release")
    parser.add_argument("--tenant", default=DEFAULT_TENANT, help="Tenant UUID for post-deploy canary")
    parser.add_argument("--server", default=DEFAULT_SERVER, help="Hetzner SSH target")
    parser.add_argument("--remote-dir", default=DEFAULT_REMOTE_DIR, help="Remote deploy directory")
    parser.add_argument("--skip-git-push", action="store_true", help="Skip git push origin/main")
    parser.add_argument("--skip-vercel", action="store_true", help="Skip Vercel frontend deploy")
    parser.add_argument("--skip-hetzner", action="store_true", help="Skip Hetzner backend deploy")
    parser.add_argument("--skip-canary", action="store_true", help="Skip production canary run")
    parser.add_argument("--skip-security-gate", action="store_true", help="Skip local predeploy security gate tests")
    parser.add_argument("--skip-frontend-gate", action="store_true", help="Skip local frontend quality gate")
    parser.add_argument("--skip-post-smoke", action="store_true", help="Skip post-deploy backend smoke check")
    parser.add_argument("--skip-route-smoke", action="store_true", help="Skip critical route smoke checks")
    parser.add_argument("--skip-error-rate-guard", action="store_true", help="Skip post-deploy error-rate guard")
    parser.add_argument("--skip-slo-review-gate", action="store_true", help="Skip SLO review attestation gate")
    parser.add_argument("--slo-attestation-path", default="docs/slo-review-attestation.json", help="Path to SLO review attestation JSON")
    parser.add_argument("--slo-max-age-days", type=int, default=14, help="Maximum allowed age for SLO review attestation")
    parser.add_argument("--error-window-minutes", type=int, default=10, help="Lookback window for error-rate guard")
    parser.add_argument("--max-error-lines", type=int, default=20, help="Maximum ERROR/Exception lines allowed in guard window")
    parser.add_argument("--allow-dirty", action="store_true", help="Allow running with local uncommitted changes")
    parser.add_argument("--break-glass-ticket", default="", help="Required ticket/reference when using critical skip flags")
    args = parser.parse_args()

    repo_root = _repo_root_from_script()
    webapp_dir = repo_root / "webapp"

    report: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "git_push": None,
        "vercel_url": None,
        "hetzner_deploy": None,
        "security_gate": None,
        "frontend_gate": None,
        "env_contract_gate": None,
        "post_deploy_smoke": None,
        "route_smoke": None,
        "error_rate_guard": None,
        "slo_review_gate": None,
        "canary": None,
        "partial": False,
        "go": False,
    }

    try:
        critical_skips_used = [flag for flag in CRITICAL_SKIP_FLAGS if getattr(args, flag, False)]
        if critical_skips_used and not str(args.break_glass_ticket or "").strip():
            raise RuntimeError(
                "Critical skip flags require --break-glass-ticket. "
                f"Used: {', '.join(critical_skips_used)}"
            )

        if args.allow_dirty and not args.skip_hetzner:
            raise RuntimeError(
                "--allow-dirty cannot be used when deploying backend. "
                "Commit or stash local changes first."
            )
        if not args.allow_dirty:
            _ensure_git_clean(repo_root)
        if not args.skip_git_push or not args.skip_hetzner:
            _ensure_release_ref_integrity(repo_root)

        if not args.skip_security_gate:
            _run_security_gate(repo_root)
            report["security_gate"] = "ok"
        else:
            report["security_gate"] = "skipped"

        if not args.skip_frontend_gate:
            _run_frontend_quality_gate(repo_root)
            report["frontend_gate"] = "ok"
        else:
            report["frontend_gate"] = "skipped"

        if not args.skip_slo_review_gate:
            slo_gate = _run_slo_review_gate(
                repo_root,
                attestation_path=args.slo_attestation_path,
                max_age_days=max(1, args.slo_max_age_days),
            )
            report["slo_review_gate"] = slo_gate
            if not slo_gate.get("ok"):
                raise RuntimeError("SLO review gate failed")
        else:
            report["slo_review_gate"] = "skipped"

        if not args.skip_git_push:
            _git_push(repo_root)
            report["git_push"] = "ok"
        else:
            report["git_push"] = "skipped"

        if not args.skip_vercel:
            report["vercel_url"] = _vercel_deploy(webapp_dir)
        else:
            report["vercel_url"] = "skipped"

        if not args.skip_hetzner:
            archive = _create_deploy_archive(repo_root)
            _upload_and_extract_archive(archive, server=args.server, remote_dir=args.remote_dir)
            env_gate = _run_remote_env_contract_gate(
                args.server,
                remote_dir=args.remote_dir,
                required_keys=["POSTGRES_PASSWORD", "REDIS_PASSWORD", "CLAIMFLOW_ENCRYPTION_KEY"],
            )
            report["env_contract_gate"] = env_gate
            if not env_gate.get("ok"):
                raise RuntimeError("remote env contract gate failed")
            _deploy_backend(server=args.server, remote_dir=args.remote_dir)
            report["hetzner_deploy"] = "ok"
        else:
            report["hetzner_deploy"] = "skipped"
            report["env_contract_gate"] = "skipped"

        if not args.skip_post_smoke:
            smoke = _run_post_deploy_smoke(args.server)
            report["post_deploy_smoke"] = smoke
            if not smoke.get("ok"):
                raise RuntimeError("post-deploy smoke check failed")
        else:
            report["post_deploy_smoke"] = "skipped"

        if not args.skip_route_smoke:
            route_smoke = _run_route_smoke(args.server)
            report["route_smoke"] = route_smoke
            if not route_smoke.get("ok"):
                raise RuntimeError("critical route smoke checks failed")
        else:
            report["route_smoke"] = "skipped"

        if not args.skip_error_rate_guard:
            guard = _run_error_rate_guard(
                args.server,
                window_minutes=max(1, args.error_window_minutes),
                max_error_lines=max(0, args.max_error_lines),
            )
            report["error_rate_guard"] = guard
            if not guard.get("ok"):
                raise RuntimeError("post-deploy error-rate guard failed")
        else:
            report["error_rate_guard"] = "skipped"

        if not args.skip_canary:
            canary_json = _run_canary(server=args.server, tenant=args.tenant)
            report["canary"] = canary_json
            report["partial"] = False
            report["go"] = bool(canary_json.get("go") is True)
        else:
            report["canary"] = "skipped"
            report["partial"] = True
            report["go"] = False

        _validate_release_contract(report, args)

    except Exception as exc:
        report["error"] = str(exc)
        report["go"] = False

    print(json.dumps(report, indent=2))
    return 0 if report.get("go") else 10


if __name__ == "__main__":
    raise SystemExit(main())
