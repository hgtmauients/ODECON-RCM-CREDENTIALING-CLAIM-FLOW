"""
Clearinghouse Transport Layer
Handles SFTP/API file transmission to/from clearinghouses
Sends 837P files, downloads 277/835 files
"""

import logging
import asyncio
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import paramiko
import httpx
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from models.rcm import TradingPartnerConnection, PayerProfile
from models.claims import EDIFile
from services.encryption import decrypt_credential
from core.audit import log_credential_access
from core.http_client import request_with_retry
from core.outbound_guard import assert_safe_http_url, assert_safe_sftp_host
from core.storage import sanitize_component, safe_filename

logger = logging.getLogger(__name__)


class SFTPTransport:
    """
    SFTP file transport for EDI files
    Handles connection, upload, download with error handling
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _resolve_connection_tenant_id(self, connection: TradingPartnerConnection) -> str:
        """Resolve and cache tenant id for this connection."""
        tenant_id = getattr(connection, "_resolved_tenant_id", None)
        if tenant_id is None:
            tenant_result = await self.db.execute(
                select(PayerProfile.tenant_id).where(PayerProfile.id == connection.payer_id)
            )
            tenant_id = tenant_result.scalar_one_or_none()
            if tenant_id is None:
                raise ValueError(f"Unable to resolve tenant for payer_id={connection.payer_id}")
            setattr(connection, "_resolved_tenant_id", tenant_id)
        return str(tenant_id)

    @staticmethod
    def _safe_download_root(tenant_id: str) -> Path:
        """
        Build a tenant-scoped local download root and enforce containment.
        """
        base_root = Path(os.getenv("EDI_DOWNLOAD_PATH", "/tmp/edi_downloads")).resolve()
        tenant_segment = sanitize_component(tenant_id, label="tenant_id")
        tenant_root = (base_root / tenant_segment).resolve()
        try:
            tenant_root.relative_to(base_root)
        except ValueError as exc:
            raise ValueError(f"Resolved tenant download path escapes base root: {tenant_root}") from exc
        tenant_root.mkdir(parents=True, exist_ok=True)
        return tenant_root

    @staticmethod
    def _build_ssh_client() -> paramiko.SSHClient:
        """
        Build SSH client with host-key verification enabled by default.
        Set SFTP_ALLOW_UNKNOWN_HOST_KEYS=true only for local/dev troubleshooting.
        """
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        allow_unknown = os.getenv("SFTP_ALLOW_UNKNOWN_HOST_KEYS", "false").lower() == "true"
        if allow_unknown:
            logger.warning("SFTP_ALLOW_UNKNOWN_HOST_KEYS=true: accepting unknown host keys")
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        else:
            ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
        return ssh

    async def _decrypt_with_audit(
        self,
        *,
        encrypted_value: str,
        connection: TradingPartnerConnection,
        credential_type: str,
        reason: str,
    ) -> str:
        plaintext = await decrypt_credential(encrypted_value)
        tenant_id = await self._resolve_connection_tenant_id(connection)
        await log_credential_access(
            self.db,
            tenant_id=tenant_id,
            payer_id=connection.payer_id,
            credential_type=credential_type,
            action="viewed",
            reason=reason,
        )
        return plaintext
    
    async def upload_file(
        self,
        local_file_path: str,
        remote_file_path: str,
        connection: TradingPartnerConnection
    ) -> Dict[str, Any]:
        """
        Upload file to clearinghouse SFTP
        
        Args:
            local_file_path: Path to local 837P file
            remote_file_path: Where to put it on SFTP server
            connection: TradingPartnerConnection with SFTP details
        
        Returns:
            Success/failure with details
        """
        try:
            # Decrypt SFTP password
            password = None
            if connection.sftp_password_encrypted:
                password = await self._decrypt_with_audit(
                    encrypted_value=connection.sftp_password_encrypted,
                    connection=connection,
                    credential_type="sftp_password",
                    reason="sftp_upload",
                )
            
            # Create SSH client
            ssh = self._build_ssh_client()
            
            # Connect
            logger.info(f"Connecting to SFTP: {connection.sftp_host}:{connection.sftp_port}")
            assert_safe_sftp_host(connection.sftp_host, field_name="sftp_host")
            
            connect_kwargs = {
                "hostname": connection.sftp_host,
                "port": connection.sftp_port or 22,
                "username": connection.sftp_username
            }
            
            if password:
                connect_kwargs["password"] = password
            elif connection.sftp_private_key_encrypted:
                # Use SSH key authentication
                private_key = await self._decrypt_with_audit(
                    encrypted_value=connection.sftp_private_key_encrypted,
                    connection=connection,
                    credential_type="sftp_private_key",
                    reason="sftp_upload",
                )
                from io import StringIO
                key = paramiko.RSAKey.from_private_key(StringIO(private_key))
                connect_kwargs["pkey"] = key
            
            ssh.connect(**connect_kwargs, timeout=30)
            
            # Open SFTP session
            sftp = ssh.open_sftp()
            
            # Upload file
            remote_full_path = f"{connection.sftp_outbound_path}/{remote_file_path}".replace("//", "/")
            
            logger.info(f"Uploading {local_file_path} to {remote_full_path}")
            sftp.put(local_file_path, remote_full_path)
            
            # Verify upload
            file_stat = sftp.stat(remote_full_path)
            
            sftp.close()
            ssh.close()
            
            logger.info(f"File uploaded successfully: {remote_file_path} ({file_stat.st_size} bytes)")
            
            return {
                "success": True,
                "remote_path": remote_full_path,
                "file_size": file_stat.st_size,
                "uploaded_at": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"SFTP upload failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def download_files(
        self,
        connection: TradingPartnerConnection,
        file_pattern: str = "*.835"
    ) -> List[Dict[str, Any]]:
        """
        Download files from clearinghouse SFTP
        Used for polling 277/835 files
        
        Args:
            connection: TradingPartnerConnection with SFTP details
            file_pattern: Pattern to match (e.g., "*.835", "*.277")
        
        Returns:
            List of downloaded files with metadata
        """
        try:
            # Decrypt password
            password = None
            if connection.sftp_password_encrypted:
                password = await self._decrypt_with_audit(
                    encrypted_value=connection.sftp_password_encrypted,
                    connection=connection,
                    credential_type="sftp_password",
                    reason="sftp_download",
                )
            
            # Connect
            ssh = self._build_ssh_client()
            assert_safe_sftp_host(connection.sftp_host, field_name="sftp_host")
            
            connect_kwargs = {
                "hostname": connection.sftp_host,
                "port": connection.sftp_port or 22,
                "username": connection.sftp_username
            }
            
            if password:
                connect_kwargs["password"] = password
            
            ssh.connect(**connect_kwargs, timeout=30)
            sftp = ssh.open_sftp()
            
            # List files in inbound directory
            inbound_path = connection.sftp_inbound_path or "/inbound"
            
            logger.info(f"Polling SFTP directory: {inbound_path} for pattern {file_pattern}")
            
            files = sftp.listdir(inbound_path)
            tenant_id = await self._resolve_connection_tenant_id(connection)
            download_root = self._safe_download_root(tenant_id)
            
            downloaded_files = []
            
            for filename in files:
                if file_pattern.replace("*", "") in filename:
                    raw_name = str(filename)
                    if raw_name in {".", ".."} or "/" in raw_name or "\\" in raw_name:
                        logger.warning("Skipping suspicious remote filename from SFTP listing: %r", raw_name)
                        continue

                    remote_name = safe_filename(raw_name, fallback="downloaded.edi")
                    if remote_name != raw_name:
                        # Fail closed for unexpected names rather than trying to
                        # translate a remote name and potentially reading the wrong file.
                        logger.warning(
                            "Skipping non-canonical remote filename from SFTP listing: raw=%r safe=%r",
                            raw_name,
                            remote_name,
                        )
                        continue

                    # Download file
                    remote_path = f"{inbound_path}/{remote_name}"
                    local_name = safe_filename(remote_name, fallback="downloaded.edi")
                    local_path = (download_root / local_name).resolve()
                    try:
                        local_path.relative_to(download_root)
                    except ValueError as exc:
                        raise ValueError(f"Refusing to write outside download root: {local_path}") from exc
                    
                    logger.info(f"Downloading {filename}...")
                    sftp.get(remote_path, str(local_path))
                    
                    downloaded_files.append({
                        "filename": filename,
                        "local_path": str(local_path),
                        "remote_path": remote_path,
                        "downloaded_at": datetime.now(timezone.utc).isoformat()
                    })
            
            sftp.close()
            ssh.close()
            
            logger.info(f"Downloaded {len(downloaded_files)} files from SFTP")
            
            return downloaded_files
            
        except Exception as e:
            logger.error(f"SFTP download failed: {e}")
            return []
    
    async def test_connection(self, connection: TradingPartnerConnection) -> Dict[str, Any]:
        """
        Test SFTP connection
        Used by connection test button in payer editor
        """
        try:
            password = None
            if connection.sftp_password_encrypted:
                password = await self._decrypt_with_audit(
                    encrypted_value=connection.sftp_password_encrypted,
                    connection=connection,
                    credential_type="sftp_password",
                    reason="sftp_test_connection",
                )
            
            ssh = self._build_ssh_client()
            assert_safe_sftp_host(connection.sftp_host, field_name="sftp_host")
            
            ssh.connect(
                hostname=connection.sftp_host,
                port=connection.sftp_port or 22,
                username=connection.sftp_username,
                password=password,
                timeout=10
            )
            
            sftp = ssh.open_sftp()
            
            # Try to list directory
            inbound_path = connection.sftp_inbound_path or "/"
            files = sftp.listdir(inbound_path)
            
            sftp.close()
            ssh.close()
            
            return {
                "success": True,
                "message": f"Connected successfully. Found {len(files)} files in {inbound_path}",
                "file_count": len(files)
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Connection failed: {str(e)}",
                "error": str(e)
            }


class APITransport:
    """
    API-based transport for clearinghouses with REST APIs
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.http_timeout_seconds = float(os.getenv("CLEARINGHOUSE_API_TIMEOUT_SECONDS", "60"))
        self.http_max_retries = max(0, int(os.getenv("CLEARINGHOUSE_API_MAX_RETRIES", "2")))
        self.http_retry_backoff_seconds = float(os.getenv("CLEARINGHOUSE_API_RETRY_BACKOFF_SECONDS", "0.2"))

    @staticmethod
    def _validated_endpoint(connection: TradingPartnerConnection) -> str:
        endpoint = str(connection.api_endpoint or "").strip()
        assert_safe_http_url(endpoint, field_name="api_endpoint")
        return endpoint.rstrip("/")

    async def _decrypt_with_audit(
        self,
        *,
        encrypted_value: str,
        connection: TradingPartnerConnection,
        credential_type: str,
        reason: str,
    ) -> str:
        plaintext = await decrypt_credential(encrypted_value)
        tenant_id = getattr(connection, "_resolved_tenant_id", None)
        if tenant_id is None:
            tenant_result = await self.db.execute(
                select(PayerProfile.tenant_id).where(PayerProfile.id == connection.payer_id)
            )
            tenant_id = tenant_result.scalar_one_or_none()
            if tenant_id is None:
                raise ValueError(f"Unable to resolve tenant for payer_id={connection.payer_id}")
            setattr(connection, "_resolved_tenant_id", tenant_id)
        await log_credential_access(
            self.db,
            tenant_id=tenant_id,
            payer_id=connection.payer_id,
            credential_type=credential_type,
            action="viewed",
            reason=reason,
        )
        return plaintext
    
    async def submit_837_via_api(
        self,
        edi_content: str,
        connection: TradingPartnerConnection
    ) -> Dict[str, Any]:
        """
        Submit 837 via clearinghouse API
        """
        try:
            # Decrypt API credentials
            api_key = (
                await self._decrypt_with_audit(
                    encrypted_value=connection.api_key_encrypted,
                    connection=connection,
                    credential_type="api_key",
                    reason="api_submit_837",
                )
                if connection.api_key_encrypted else None
            )
            api_secret = (
                await self._decrypt_with_audit(
                    encrypted_value=connection.api_secret_encrypted,
                    connection=connection,
                    credential_type="api_secret",
                    reason="api_submit_837",
                )
                if connection.api_secret_encrypted else None
            )
            
            # Authentication
            headers: Dict[str, str] = {}
            if connection.api_auth_method == "bearer" and api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            elif connection.api_auth_method == "basic" and api_key and api_secret:
                import base64
                credentials = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
                headers["Authorization"] = f"Basic {credentials}"
            
            headers["Content-Type"] = "application/x12"
            
            endpoint = self._validated_endpoint(connection)
            response = await request_with_retry(
                method="POST",
                url=f"{endpoint}/submit",
                content=edi_content,
                headers=headers,
                timeout_seconds=self.http_timeout_seconds,
                max_retries=self.http_max_retries,
                retry_backoff_seconds=self.http_retry_backoff_seconds,
                retry_on_statuses=(429, 500, 502, 503, 504),
                client_factory=httpx.AsyncClient,
            )
            
            if response.status_code in (200, 201):
                data = response.json()
                return {
                    "success": True,
                    "submission_id": data.get("submission_id"),
                    "tracking_number": data.get("tracking_number"),
                    "message": "Claim submitted successfully via API"
                }
            return {
                "success": False,
                "error": f"API returned {response.status_code}: {response.text}"
            }
                    
        except Exception as e:
            logger.error(f"API submission failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def test_connection(self, connection: TradingPartnerConnection) -> Dict[str, Any]:
        """
        Test API connection
        """
        try:
            api_key = (
                await self._decrypt_with_audit(
                    encrypted_value=connection.api_key_encrypted,
                    connection=connection,
                    credential_type="api_key",
                    reason="api_test_connection",
                )
                if connection.api_key_encrypted else None
            )
            
            headers: Dict[str, str] = {}
            if connection.api_auth_method == "bearer" and api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            
            # Ping endpoint
            endpoint = self._validated_endpoint(connection)
            response = await request_with_retry(
                method="GET",
                url=f"{endpoint}/ping",
                headers=headers,
                timeout_seconds=min(10.0, self.http_timeout_seconds),
                max_retries=self.http_max_retries,
                retry_backoff_seconds=self.http_retry_backoff_seconds,
                retry_on_statuses=(429, 500, 502, 503, 504),
                client_factory=httpx.AsyncClient,
            )
            
            if response.status_code == 200:
                return {
                    "success": True,
                    "message": "API connection successful."
                }
            return {
                "success": False,
                "message": f"API returned {response.status_code}"
            }
                    
        except Exception as e:
            return {
                "success": False,
                "message": f"Connection failed: {str(e)}"
            }


class ClearinghouseService:
    """
    High-level service for clearinghouse operations
    Abstracts SFTP/API details
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.sftp = SFTPTransport(db)
        self.api = APITransport(db)
    
    async def submit_837_file(
        self,
        local_file_path: str,
        payer_id: int,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """
        Submit 837 file using configured method for payer
        """
        try:
            # Get payer
            payer_result = await self.db.execute(
                select(PayerProfile).where(and_(
                    PayerProfile.id == payer_id,
                    PayerProfile.tenant_id == tenant_id,
                ))
            )
            payer = payer_result.scalar_one_or_none()
            
            if not payer:
                return {"success": False, "error": "Payer not found"}
            
            # Get connection
            conn_result = await self.db.execute(
                select(TradingPartnerConnection)
                .join(PayerProfile, TradingPartnerConnection.payer_id == PayerProfile.id)
                .where(and_(
                    TradingPartnerConnection.payer_id == payer_id,
                    PayerProfile.tenant_id == tenant_id,
                ))
                .limit(1)
            )
            connection = conn_result.scalar_one_or_none()
            
            if not connection:
                return {"success": False, "error": "No connection configured for payer"}
            
            # Route based on connection type
            if connection.connection_type == "sftp":
                filename = Path(local_file_path).name
                result = await self.sftp.upload_file(
                    local_file_path=local_file_path,
                    remote_file_path=filename,
                    connection=connection
                )
                return result
                
            elif connection.connection_type == "api":
                # Read file content
                with open(local_file_path, 'r') as f:
                    edi_content = f.read()
                
                result = await self.api.submit_837_via_api(
                    edi_content=edi_content,
                    connection=connection
                )
                return result
                
            else:
                return {
                    "success": False,
                    "error": f"Connection type '{connection.connection_type}' not yet supported. Use SFTP or API."
                }
                
        except Exception as e:
            logger.error(f"Error submitting 837: {e}")
            return {"success": False, "error": str(e)}
    
    async def poll_for_835_files(self, payer_id: int, tenant_id: str) -> List[str]:
        """
        Poll clearinghouse for new 835 remittance files
        Run this as a scheduled job (every hour)
        """
        try:
            # Get connection
            conn_result = await self.db.execute(
                select(TradingPartnerConnection)
                .join(PayerProfile, TradingPartnerConnection.payer_id == PayerProfile.id)
                .where(and_(
                    TradingPartnerConnection.payer_id == payer_id,
                    PayerProfile.tenant_id == tenant_id,
                ))
                .limit(1)
            )
            connection = conn_result.scalar_one_or_none()
            
            if not connection:
                logger.warning(f"No connection for payer {payer_id}")
                return []
            
            if connection.connection_type == "sftp":
                files = await self.sftp.download_files(connection, file_pattern="*.835")
                return [f["local_path"] for f in files]
            else:
                logger.warning(f"835 polling not supported for connection type: {connection.connection_type}")
                return []
                
        except Exception as e:
            logger.error(f"Error polling for 835 files: {e}")
            return []

    async def poll_for_277_files(self, payer_id: int, tenant_id: str) -> List[str]:
        """
        Poll clearinghouse for new 277/277CA acknowledgment files.
        Run this as a scheduled job (every hour).
        """
        try:
            # Get connection
            conn_result = await self.db.execute(
                select(TradingPartnerConnection)
                .join(PayerProfile, TradingPartnerConnection.payer_id == PayerProfile.id)
                .where(and_(
                    TradingPartnerConnection.payer_id == payer_id,
                    PayerProfile.tenant_id == tenant_id,
                ))
                .limit(1)
            )
            connection = conn_result.scalar_one_or_none()

            if not connection:
                logger.warning(f"No connection for payer {payer_id}")
                return []

            if connection.connection_type == "sftp":
                files = await self.sftp.download_files(connection, file_pattern="*.277")
                return [f["local_path"] for f in files]
            else:
                logger.warning(f"277 polling not supported for connection type: {connection.connection_type}")
                return []

        except Exception as e:
            logger.error(f"Error polling for 277 files: {e}")
            return []

