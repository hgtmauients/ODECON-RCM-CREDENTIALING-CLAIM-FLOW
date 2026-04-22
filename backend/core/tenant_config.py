"""
ClaimFlow - Tenant configuration resolver.
Reads settings from Tenant.settings JSONB first, falls back to environment variables.
Sensitive values are stored encrypted and transparently decrypted on read.
"""

import os
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = frozenset({
    "api_cert_key",
    "caqh_password",
    "smtp_pass",
    "webhook_secret",
})

ENV_VAR_MAP: Dict[str, str] = {
    "api_cert_key": "API_CERT_KEY",
    "caqh_org_id": "CAQH_ORG_ID",
    "caqh_username": "CAQH_USERNAME",
    "caqh_password": "CAQH_PASSWORD",
    "smtp_host": "SMTP_HOST",
    "smtp_port": "SMTP_PORT",
    "smtp_user": "SMTP_USER",
    "smtp_pass": "SMTP_PASS",
    "from_email": "FROM_EMAIL",
    "webhook_secret": "WEBHOOK_SECRET",
}

ALL_SETTING_KEYS: List[str] = list(ENV_VAR_MAP.keys())


def _storage_key(key: str) -> str:
    """Return the JSONB key used for storage (sensitive keys get _encrypted suffix)."""
    if key in SENSITIVE_KEYS:
        return f"{key}_encrypted"
    return key


async def get_tenant_setting(
    db: AsyncSession,
    tenant_id: str,
    key: str,
    default: Any = None,
) -> Any:
    """
    Resolve a single tenant setting.
    Priority: tenant DB value → environment variable → default.
    Encrypted values are transparently decrypted.
    """
    from models.tenant import Tenant

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()

    if tenant and tenant.settings:
        storage = _storage_key(key)
        value = tenant.settings.get(storage)
        if value is not None and value != "":
            if key in SENSITIVE_KEYS:
                try:
                    from services.encryption import decrypt_credential
                    return await decrypt_credential(value)
                except Exception as e:
                    logger.warning(f"Failed to decrypt tenant setting {key}: {e}")
            else:
                return value

    env_name = ENV_VAR_MAP.get(key, key.upper())
    env_val = os.getenv(env_name)
    if env_val is not None and env_val != "":
        return env_val

    return default


async def get_all_tenant_settings(db: AsyncSession, tenant_id: str) -> Dict[str, Any]:
    """
    Return all tenant-configurable settings as a flat dict.
    Sensitive values are decrypted. Missing keys fall back to env vars.
    """
    settings: Dict[str, Any] = {}
    for key in ALL_SETTING_KEYS:
        settings[key] = await get_tenant_setting(db, tenant_id, key, default="")
    return settings


async def get_masked_tenant_settings(db: AsyncSession, tenant_id: str) -> Dict[str, Any]:
    """
    Return all tenant-configurable settings with sensitive values masked.
    Shows '***' + last 4 chars for non-empty sensitive fields.
    """
    from models.tenant import Tenant

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    db_settings = (tenant.settings or {}) if tenant else {}

    masked: Dict[str, Any] = {}
    for key in ALL_SETTING_KEYS:
        storage = _storage_key(key)
        db_val = db_settings.get(storage)
        has_db_value = db_val is not None and db_val != ""

        env_name = ENV_VAR_MAP.get(key, key.upper())
        env_val = os.getenv(env_name, "")
        has_env_value = bool(env_val)

        if key in SENSITIVE_KEYS:
            if has_db_value:
                try:
                    from services.encryption import decrypt_credential
                    plain = await decrypt_credential(db_val)
                    masked[key] = _mask(plain)
                except Exception:
                    masked[key] = "***error***"
                masked[f"{key}_source"] = "db"
            elif has_env_value:
                masked[key] = _mask(env_val)
                masked[f"{key}_source"] = "env"
            else:
                masked[key] = ""
                masked[f"{key}_source"] = "none"
        else:
            if has_db_value:
                masked[key] = db_val
                masked[f"{key}_source"] = "db"
            elif has_env_value:
                masked[key] = env_val
                masked[f"{key}_source"] = "env"
            else:
                masked[key] = ""
                masked[f"{key}_source"] = "none"

    return masked


async def save_tenant_settings(
    db: AsyncSession,
    tenant_id: str,
    incoming: Dict[str, Any],
) -> None:
    """
    Persist tenant settings into the Tenant.settings JSONB column.
    Sensitive values are encrypted before storage.
    Empty strings for sensitive keys are treated as "clear the value".
    """
    from models.tenant import Tenant
    from services.encryption import encrypt_credential

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise ValueError(f"Tenant {tenant_id} not found")

    current: Dict[str, Any] = dict(tenant.settings or {})

    for key in ALL_SETTING_KEYS:
        if key not in incoming:
            continue

        raw_value = incoming[key]
        storage = _storage_key(key)

        if key in SENSITIVE_KEYS:
            # Skip masked placeholder values (no actual change)
            if isinstance(raw_value, str) and raw_value.startswith("***"):
                continue
            if raw_value == "" or raw_value is None:
                current.pop(storage, None)
            else:
                current[storage] = await encrypt_credential(str(raw_value))
        else:
            if raw_value == "" or raw_value is None:
                current.pop(storage, None)
            else:
                current[storage] = raw_value

    tenant.settings = current
    await db.commit()


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "***"
    return "***" + value[-4:]
