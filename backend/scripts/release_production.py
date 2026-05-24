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
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_SERVER = "root@5.161.209.46"
DEFAULT_REMOTE_DIR = "/opt/noodledoc"
DEFAULT_TENANT = "00000000-0000-0000-0000-000000000001"


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
            "py",
            "-3",
            "-m",
            "pytest",
            "backend/tests/test_startup_checks.py",
            "backend/tests/test_csv_export.py",
            "backend/tests/test_auth_error_messages.py",
            "backend/tests/test_provider_adapter.py",
            "-v",
        ],
        cwd=repo_root,
    )
    if gate.returncode != 0:
        raise RuntimeError("predeploy security gate failed")


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


def _ensure_git_clean(repo_root: Path) -> None:
    status = _run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True)
    if status.returncode != 0:
        raise RuntimeError(f"git status failed:\n{status.stderr}")
    if status.stdout.strip():
        raise RuntimeError("Working tree is dirty. Commit/stash changes or use --allow-dirty.")


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
    parser.add_argument("--skip-post-smoke", action="store_true", help="Skip post-deploy backend smoke check")
    parser.add_argument("--skip-route-smoke", action="store_true", help="Skip critical route smoke checks")
    parser.add_argument("--skip-error-rate-guard", action="store_true", help="Skip post-deploy error-rate guard")
    parser.add_argument("--error-window-minutes", type=int, default=10, help="Lookback window for error-rate guard")
    parser.add_argument("--max-error-lines", type=int, default=20, help="Maximum ERROR/Exception lines allowed in guard window")
    parser.add_argument("--allow-dirty", action="store_true", help="Allow running with local uncommitted changes")
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
        "post_deploy_smoke": None,
        "route_smoke": None,
        "error_rate_guard": None,
        "canary": None,
        "go": False,
    }

    try:
        if not args.allow_dirty:
            _ensure_git_clean(repo_root)

        if not args.skip_security_gate:
            _run_security_gate(repo_root)
            report["security_gate"] = "ok"
        else:
            report["security_gate"] = "skipped"

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
            _deploy_backend(server=args.server, remote_dir=args.remote_dir)
            report["hetzner_deploy"] = "ok"
        else:
            report["hetzner_deploy"] = "skipped"

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
            report["go"] = bool(canary_json.get("go") is True)
        else:
            report["canary"] = "skipped"
            report["go"] = True

    except Exception as exc:
        report["error"] = str(exc)
        report["go"] = False

    print(json.dumps(report, indent=2))
    return 0 if report.get("go") else 10


if __name__ == "__main__":
    raise SystemExit(main())
