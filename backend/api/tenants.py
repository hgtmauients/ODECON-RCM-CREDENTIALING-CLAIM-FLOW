"""
ClaimFlow - Tenant management API.
Provides CRUD for tenant onboarding and metadata lookup,
plus per-tenant settings management with encrypted credential storage.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import logging

from core.database import get_db
from core.audit import log_audit_event
from api.auth import get_current_user, Principal
from api.schemas import TenantCreate, TenantUpdate, TenantSettingsUpdate, TestSmtpRequest
from core.http_client import request_with_retry
from core.outbound_guard import assert_safe_smtp_host

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tenants", tags=["Tenants"])

# Fields the bulk update path must NEVER touch — settings has its own
# dedicated /settings endpoint that handles encryption; bypassing that path
# stomps on encrypted secrets (closes NEW-M3).
_PROTECTED_TENANT_FIELDS = frozenset({"id", "settings", "is_active", "created_at", "created_by"})


def _integration_test_error_message() -> str:
    # Keep responses stable and non-sensitive; detailed errors stay in server logs.
    return "Integration test failed. Check server logs for details."


@router.post("")
async def create_tenant(
    payload: TenantCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Create a new tenant (super-admin only). Validated via TenantCreate."""
    current_user.require_role("super_admin")

    from models.tenant import Tenant

    name = payload.name.strip()
    slug = (payload.slug or name).lower().replace(" ", "-")
    tenant = Tenant(
        name=name,
        slug=slug,
        settings={},  # Use /settings endpoint for any non-trivial config.
        created_by=current_user.email,
    )
    db.add(tenant)
    await db.flush()

    await log_audit_event(
        db, current_user, action="tenant_created", resource_type="tenant",
        resource_id=str(tenant.id), request=request,
        metadata={"name": name, "slug": slug},
    )
    await db.commit()
    await db.refresh(tenant)

    return {"success": True, "data": {"id": str(tenant.id), "name": tenant.name, "slug": tenant.slug}}


@router.get("/{tenant_id}")
async def get_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Get tenant metadata. Accessible by members of the tenant or super-admins."""
    from models.tenant import Tenant

    if current_user.tenant_id != tenant_id and not current_user.has_role("super_admin"):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Strip out encrypted ciphertext from raw settings; only return non-sensitive keys.
    raw_settings = tenant.settings or {}
    safe_settings = {k: v for k, v in raw_settings.items() if not k.endswith("_encrypted")}

    return {
        "success": True,
        "data": {
            "id": str(tenant.id),
            "name": tenant.name,
            "slug": tenant.slug,
            "is_active": tenant.is_active,
            "settings": safe_settings,
            "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
        },
    }


@router.put("/{tenant_id}")
async def update_tenant(
    tenant_id: str,
    updates: TenantUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Update tenant metadata. Admin or super-admin only.

    `settings` is intentionally rejected here — use PUT /tenants/{id}/settings
    so encryption is applied. (Closes NEW-M3.)
    """
    from models.tenant import Tenant

    if current_user.tenant_id != tenant_id and not current_user.has_role("super_admin"):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")
    current_user.require_role("admin")

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    applied = []
    for key, value in updates.model_dump(exclude_unset=True).items():
        if key in _PROTECTED_TENANT_FIELDS:
            continue
        if hasattr(tenant, key):
            setattr(tenant, key, value)
            applied.append(key)

    await log_audit_event(
        db, current_user, action="tenant_updated", resource_type="tenant",
        resource_id=tenant_id, request=request,
        changes={"updated_fields": sorted(applied)},
    )
    await db.commit()
    return {"success": True, "message": "Tenant updated"}


@router.get("")
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List all tenants (super-admin only)."""
    current_user.require_role("super_admin")
    from models.tenant import Tenant

    result = await db.execute(select(Tenant).order_by(Tenant.name))
    tenants = result.scalars().all()

    return {
        "success": True,
        "data": [{
            "id": str(t.id),
            "name": t.name,
            "slug": t.slug,
            "is_active": t.is_active,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        } for t in tenants],
    }


# ── Per-tenant settings (configurable via UI) ──────────────────────────


@router.get("/{tenant_id}/settings")
async def get_tenant_settings(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Return tenant-configurable settings with sensitive values masked."""
    if current_user.tenant_id != tenant_id and not current_user.has_role("super_admin"):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")
    current_user.require_role("admin")

    from core.tenant_config import get_masked_tenant_settings

    masked = await get_masked_tenant_settings(db, tenant_id)
    return {"success": True, "data": masked}


@router.put("/{tenant_id}/settings")
async def update_tenant_settings(
    tenant_id: str,
    settings: TenantSettingsUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Save tenant-configurable settings. Sensitive values encrypted before storage."""
    if current_user.tenant_id != tenant_id and not current_user.has_role("super_admin"):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")
    current_user.require_role("admin")

    from core.tenant_config import save_tenant_settings

    incoming = settings.model_dump(exclude_unset=True)
    try:
        await save_tenant_settings(db, tenant_id, incoming)
    except ValueError:
        logger.info("save_tenant_settings: tenant %s not found", tenant_id)
        raise HTTPException(status_code=404, detail="Tenant not found")
    except Exception:
        logger.exception("Failed to save tenant settings for %s", tenant_id)
        raise HTTPException(status_code=500, detail="Failed to save settings")

    # Audit logs the FIELD NAMES touched, not the values (which include
    # secrets). The secrets themselves are encrypted in the DB.
    await log_audit_event(
        db, current_user, action="tenant_settings_updated", resource_type="tenant",
        resource_id=tenant_id, request=request,
        changes={"updated_fields": sorted(incoming.keys())},
    )
    await db.commit()

    return {"success": True, "message": "Settings saved"}


@router.post("/{tenant_id}/webhook/regenerate-secret")
async def regenerate_webhook_secret(
    tenant_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Generate a fresh per-tenant webhook secret + return it once.

    The plaintext is returned ONLY in this response. Subsequent reads via
    /tenants/{id}/settings come back masked.
    """
    if current_user.tenant_id != tenant_id and not current_user.has_role("super_admin"):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")
    current_user.require_role("admin")

    import secrets as _secrets
    from core.tenant_config import save_tenant_settings

    new_secret = _secrets.token_hex(32)  # 64-char hex, ~256 bits
    try:
        await save_tenant_settings(db, tenant_id, {"webhook_secret": new_secret})
    except ValueError:
        raise HTTPException(status_code=404, detail="Tenant not found")

    await log_audit_event(
        db, current_user, action="webhook_secret_rotated", resource_type="tenant",
        resource_id=tenant_id, request=request,
        metadata={"length": len(new_secret)},
    )
    await db.commit()

    return {
        "success": True,
        "data": {
            "webhook_secret": new_secret,
            "warning": "This value is shown ONCE. Store it now — subsequent reads return only a masked preview.",
        },
    }


@router.post("/{tenant_id}/settings/test-smtp")
async def test_smtp_settings(
    tenant_id: str,
    body: Optional[TestSmtpRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Send a test email using the tenant's saved SMTP settings."""
    if current_user.tenant_id != tenant_id and not current_user.has_role("super_admin"):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")
    current_user.require_role("admin")

    from core.tenant_config import get_tenant_setting

    smtp_host = await get_tenant_setting(db, tenant_id, "smtp_host")
    if not smtp_host:
        raise HTTPException(status_code=400, detail="SMTP not configured — save SMTP settings first")
    assert_safe_smtp_host(smtp_host, field_name="smtp_host")

    smtp_port = int(await get_tenant_setting(db, tenant_id, "smtp_port", "587"))
    smtp_user = await get_tenant_setting(db, tenant_id, "smtp_user", "")
    smtp_pass = await get_tenant_setting(db, tenant_id, "smtp_pass", "")
    from_email = await get_tenant_setting(db, tenant_id, "from_email", "noreply@claimflow.io")
    # Test emails always go to the authenticated operator to prevent abuse
    # as an open relay via arbitrary recipients.
    to_email = current_user.email

    try:
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText("This is a test email from ClaimFlow settings.")
        msg["Subject"] = "ClaimFlow SMTP Test"
        msg["From"] = from_email
        msg["To"] = to_email

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, [to_email], msg.as_string())

        return {"success": True, "message": f"Test email sent to {to_email}"}
    except Exception as e:
        logger.warning("SMTP test failed for tenant %s: %s", tenant_id, e)
        return {"success": False, "error": _integration_test_error_message()}


@router.post("/{tenant_id}/settings/test-api-cert")
async def test_api_cert_settings(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Check API-Cert key validity and quota usage for this tenant."""
    if current_user.tenant_id != tenant_id and not current_user.has_role("super_admin"):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")
    current_user.require_role("admin")

    from core.tenant_config import get_tenant_setting

    api_key = await get_tenant_setting(db, tenant_id, "api_cert_key")
    if not api_key:
        return {"success": False, "error": "API-Cert key not configured"}

    try:
        resp = await request_with_retry(
            method="GET",
            url="https://api.api-cert.com/v1/usage",
            headers={"X-API-Key": api_key},
            timeout_seconds=10.0,
            max_retries=2,
            retry_backoff_seconds=0.2,
            retry_on_statuses=(429, 500, 502, 503, 504),
        )
        if resp.status_code == 200:
            return {"success": True, "data": resp.json()}
        return {"success": False, "error": f"API-Cert returned {resp.status_code}"}
    except Exception as e:
        logger.warning("API-Cert test failed for tenant %s: %s", tenant_id, e)
        return {"success": False, "error": _integration_test_error_message()}


@router.post("/{tenant_id}/settings/test-caqh")
async def test_caqh_settings(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Test CAQH ProView credentials for this tenant."""
    if current_user.tenant_id != tenant_id and not current_user.has_role("super_admin"):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")
    current_user.require_role("admin")

    from core.tenant_config import get_tenant_setting

    org_id = await get_tenant_setting(db, tenant_id, "caqh_org_id")
    username = await get_tenant_setting(db, tenant_id, "caqh_username")
    password = await get_tenant_setting(db, tenant_id, "caqh_password")

    if not (org_id and username and password):
        return {"success": False, "error": "CAQH credentials not fully configured"}

    try:
        base_url = "https://proview-demo.caqh.org/RosterAPI/api"
        resp = await request_with_retry(
            method="GET",
            url=f"{base_url}/Roster",
            params={"organizationId": org_id},
            auth=(username, password),
            timeout_seconds=15.0,
            max_retries=2,
            retry_backoff_seconds=0.2,
            retry_on_statuses=(429, 500, 502, 503, 504),
        )
        if resp.status_code in (200, 401, 403):
            connected = resp.status_code == 200
            return {
                "success": connected,
                "message": "Connected to CAQH" if connected else f"CAQH returned {resp.status_code}",
            }
        return {"success": False, "error": f"CAQH returned {resp.status_code}"}
    except Exception as e:
        logger.warning("CAQH test failed for tenant %s: %s", tenant_id, e)
        return {"success": False, "error": _integration_test_error_message()}
