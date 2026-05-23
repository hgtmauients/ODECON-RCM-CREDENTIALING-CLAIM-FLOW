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

from core.audit import log_credential_access

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


# Settings whose env-var fallback represents a CROSS-TENANT secret. For these
# we deliberately refuse the env fallback so one tenant cannot inherit
# another tenant\'s integration secret simply by leaving its own slot blank.
# webhook_secret is the canonical example: it gates an unauthenticated
# webhook, and the env-var has historically been shared across tenants.
TENANT_SCOPED_KEYS = frozenset({"webhook_secret"})


async def get_tenant_setting(
    db: AsyncSession,
    tenant_id: str,
    key: str,
    default: Any = None,
    *,
    allow_env_fallback: Optional[bool] = None,
) -> Any:
    """
    Resolve a single tenant setting.
    Priority: tenant DB value → environment variable → default.
    Encrypted values are transparently decrypted.

    For TENANT_SCOPED_KEYS the env fallback is disabled by default to prevent
    cross-tenant secret inheritance. Pass allow_env_fallback=True to override
    (only legitimate when the caller is explicitly an admin tooling path).
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
                    plain = await decrypt_credential(value)
                    await log_credential_access(
                        db,
                        tenant_id=tenant_id,
                        credential_type=key,
                        action="viewed",
                        reason="tenant_setting_read_db",
                    )
                    return plain
                except Exception as e:
                    logger.warning(f"Failed to decrypt tenant setting {key}: {e}")
            else:
                return value

    if allow_env_fallback is None:
        allow_env_fallback = key not in TENANT_SCOPED_KEYS
    if allow_env_fallback:
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
                    await log_credential_access(
                        db,
                        tenant_id=tenant_id,
                        credential_type=key,
                        action="viewed",
                        reason="tenant_setting_masked_read",
                    )
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
