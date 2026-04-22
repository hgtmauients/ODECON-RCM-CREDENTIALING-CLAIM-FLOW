"""
ClaimFlow - File storage abstraction.
Supports local filesystem (default) and S3-compatible object stores.
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")  # "local" or "s3"
LOCAL_STORAGE_PATH = os.getenv("EDI_STORAGE_PATH", "/data/claimflow/edi")
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_REGION = os.getenv("S3_REGION", "us-east-1")


class StorageService:
    """Abstraction over local filesystem and S3."""

    async def write(self, path: str, content: bytes, tenant_id: Optional[str] = None) -> str:
        """Write content and return the resolved path/key."""
        if STORAGE_BACKEND == "s3":
            return await self._write_s3(path, content, tenant_id)
        return self._write_local(path, content, tenant_id)

    async def read(self, path: str) -> bytes:
        """Read content from storage."""
        if STORAGE_BACKEND == "s3":
            return await self._read_s3(path)
        return self._read_local(path)

    async def exists(self, path: str) -> bool:
        if STORAGE_BACKEND == "s3":
            return await self._exists_s3(path)
        return Path(path).exists()

    def _write_local(self, path: str, content: bytes, tenant_id: Optional[str] = None) -> str:
        full_path = Path(LOCAL_STORAGE_PATH)
        if tenant_id:
            full_path = full_path / tenant_id
        full_path = full_path / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
        return str(full_path)

    def _read_local(self, path: str) -> bytes:
        return Path(path).read_bytes()

    async def _write_s3(self, path: str, content: bytes, tenant_id: Optional[str] = None) -> str:
        try:
            import boto3
            s3 = boto3.client("s3", region_name=S3_REGION)
            key = f"{tenant_id}/{path}" if tenant_id else path
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
