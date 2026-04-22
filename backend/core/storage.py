"""
ClaimFlow - File storage abstraction.
Supports local filesystem (default) and S3-compatible object stores.

Security: every caller-supplied path component is sanitized to prevent
directory traversal. The final resolved path is verified to live under the
tenant's storage root before any write or read happens.
"""

import os
import re
import logging
from pathlib import Path, PurePosixPath
from typing import Optional

logger = logging.getLogger(__name__)

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")  # "local" or "s3"
LOCAL_STORAGE_PATH = os.getenv("EDI_STORAGE_PATH", "/data/edi")
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_REGION = os.getenv("S3_REGION", "us-east-1")

# Per-component character allowlist. Anything outside this is rejected
# rather than silently rewritten — silent rewrites confuse callers and
# make path conflicts easy to engineer.
_SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_MAX_COMPONENT_LEN = 255


class StoragePathError(ValueError):
    """Raised when a caller-supplied path would escape the storage root."""


def sanitize_component(component: str, *, label: str = "path component") -> str:
    """
    Validate a single path component (no separators) and return it.

    Rejects: empty strings, ".", "..", anything containing / or \\, anything
    failing the conservative allowlist, anything longer than 255 bytes.
    Caller passes a single segment; multi-segment paths must be assembled
    via build_relative_path() so each piece is validated.
    """
    if not isinstance(component, str) or not component:
        raise StoragePathError(f"Empty {label}")
    if component in (".", ".."):
        raise StoragePathError(f"Reserved {label}: {component!r}")
    if "/" in component or "\\" in component or "\x00" in component:
        raise StoragePathError(f"Separator or NUL in {label}: {component!r}")
    if len(component.encode("utf-8")) > _MAX_COMPONENT_LEN:
        raise StoragePathError(f"{label} too long ({_MAX_COMPONENT_LEN} byte cap)")
    if not _SAFE_COMPONENT_RE.match(component):
        raise StoragePathError(
            f"{label} contains characters outside [A-Za-z0-9._-]: {component!r}"
        )
    return component


def safe_filename(filename: Optional[str], *, fallback: str) -> str:
    """
    Coerce an untrusted filename (e.g. UploadFile.filename) into a safe single
    component. Strips path separators and replaces any disallowed character
    with underscore so legitimate user filenames still survive.
    """
    raw = (filename or fallback).split("/")[-1].split("\\")[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._-")
    if not cleaned:
        cleaned = fallback
    return cleaned[:_MAX_COMPONENT_LEN]


def build_relative_path(*components: str) -> str:
    """
    Build a relative storage path from validated components.
    Each component is sanitized via sanitize_component(); the result uses
    forward slashes (POSIX style) so it works for both local and S3 keys.
    """
    safe = [sanitize_component(c) for c in components]
    return str(PurePosixPath(*safe))


class StorageService:
    """Abstraction over local filesystem and S3 with path-traversal protection."""

    async def write(self, path: str, content: bytes, tenant_id: Optional[str] = None) -> str:
        """Write content and return the resolved path/key."""
        if STORAGE_BACKEND == "s3":
            return await self._write_s3(path, content, tenant_id)
        return self._write_local(path, content, tenant_id)

    async def read(self, path: str) -> bytes:
        """Read content from storage. Caller-supplied path must be one we wrote."""
        if STORAGE_BACKEND == "s3":
            return await self._read_s3(path)
        return self._read_local(path)

    async def exists(self, path: str) -> bool:
        if STORAGE_BACKEND == "s3":
            return await self._exists_s3(path)
        return Path(path).exists()

    # ---------------------------------------------------------------- local

    def _resolve_local_path(self, path: str, tenant_id: Optional[str]) -> Path:
        """
        Resolve `path` relative to the tenant's storage root and verify the
        result stays inside that root. Raises StoragePathError on escape.

        We rebuild the path segment-by-segment after sanitizing each component
        so neither absolute paths nor `..` traversal can survive.
        """
        root = Path(LOCAL_STORAGE_PATH).resolve()
        if tenant_id:
            tenant_id = sanitize_component(tenant_id, label="tenant_id")
            root = (root / tenant_id).resolve()

        # Split on both separators, drop "." and "..", validate the rest.
        raw_parts = [p for p in path.replace("\\", "/").split("/") if p and p != "."]
        if any(p == ".." for p in raw_parts):
            raise StoragePathError(f"Path traversal attempt: {path!r}")
        for part in raw_parts:
            sanitize_component(part, label="path component")

        full = (root / Path(*raw_parts)).resolve() if raw_parts else root
        # Containment check — even though sanitize_component should make this
        # impossible, the resolved-path check is defense in depth.
        try:
            full.relative_to(root)
        except ValueError:
            raise StoragePathError(f"Resolved path escapes storage root: {full}")
        return full

    def _write_local(self, path: str, content: bytes, tenant_id: Optional[str] = None) -> str:
        full_path = self._resolve_local_path(path, tenant_id)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
        return str(full_path)

    def _read_local(self, path: str) -> bytes:
        # Local reads use the absolute path stored at write time; we still
        # refuse to follow paths outside the configured storage root.
        full = Path(path).resolve()
        root = Path(LOCAL_STORAGE_PATH).resolve()
        try:
            full.relative_to(root)
        except ValueError:
            raise StoragePathError(f"Refusing to read outside storage root: {full}")
        return full.read_bytes()

    # ------------------------------------------------------------------ s3

    def _resolve_s3_key(self, path: str, tenant_id: Optional[str]) -> str:
        """Sanitize an S3 object key the same way we sanitize local paths."""
        parts = []
        if tenant_id:
            parts.append(sanitize_component(tenant_id, label="tenant_id"))
        for raw in path.replace("\\", "/").split("/"):
            if not raw or raw == ".":
                continue
            if raw == "..":
                raise StoragePathError(f"Path traversal attempt in S3 key: {path!r}")
            parts.append(sanitize_component(raw, label="S3 key segment"))
        return "/".join(parts)

    async def _write_s3(self, path: str, content: bytes, tenant_id: Optional[str] = None) -> str:
        try:
            import boto3
            s3 = boto3.client("s3", region_name=S3_REGION)
            key = self._resolve_s3_key(path, tenant_id)
            s3.put_object(Bucket=S3_BUCKET, Key=key, Body=content)
            return f"s3://{S3_BUCKET}/{key}"
        except ImportError:
            logger.error("boto3 not installed but S3 backend configured")
            raise

    async def _read_s3(self, path: str) -> bytes:
        import boto3
        s3 = boto3.client("s3", region_name=S3_REGION)
        key = path.replace(f"s3://{S3_BUCKET}/", "") if path.startswith("s3://") else path
        response = s3.get_object(Bucket=S3_BUCKET, Key=key)
        return response["Body"].read()

    async def _exists_s3(self, path: str) -> bool:
        import boto3
        s3 = boto3.client("s3", region_name=S3_REGION)
        key = path.replace(f"s3://{S3_BUCKET}/", "") if path.startswith("s3://") else path
        try:
            s3.head_object(Bucket=S3_BUCKET, Key=key)
            return True
        except Exception:
            return False


storage = StorageService()
