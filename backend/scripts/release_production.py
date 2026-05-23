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
        "canary": None,
        "go": False,
    }

    try:
        if not args.allow_dirty:
            _ensure_git_clean(repo_root)

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
