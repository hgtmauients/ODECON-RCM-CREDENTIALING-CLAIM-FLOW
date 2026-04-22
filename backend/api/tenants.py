"""
ClaimFlow - Tenant management API.
Provides CRUD for tenant onboarding and metadata lookup,
plus per-tenant settings management with encrypted credential storage.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, Optional
from datetime import datetime
import logging

from core.database import get_db
from api.auth import get_current_user, Principal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.post("")
async def create_tenant(
    tenant_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Create a new tenant (super-admin only)."""
    current_user.require_role("super_admin")

    from models.tenant import Tenant

    tenant = Tenant(
        name=tenant_data["name"],
        slug=tenant_data.get("slug", tenant_data["name"].lower().replace(" ", "-")),
        settings=tenant_data.get("settings", {}),
        created_by=current_user.email,
    )
    db.add(tenant)
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

    return {
        "success": True,
        "data": {
            "id": str(tenant.id),
            "name": tenant.name,
            "slug": tenant.slug,
            "is_active": tenant.is_active,
            "settings": tenant.settings,
            "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
        },
    }


@router.put("/{tenant_id}")
async def update_tenant(
    tenant_id: str,
    updates: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Update tenant metadata. Admin or super-admin only."""
    from models.tenant import Tenant

    if current_user.tenant_id != tenant_id and not current_user.has_role("super_admin"):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")
    current_user.require_role("admin")

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    allowed_fields = {"name", "npi", "tax_id", "address_line_1", "address_line_2", "city", "state", "zip_code", "phone", "billing_contact_email", "settings"}
    for key, value in updates.items():
        if key in allowed_fields and hasattr(tenant, key):
            setattr(tenant, key, value)

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
    settings: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Save tenant-configurable settings. Sensitive values encrypted before storage."""
    if current_user.tenant_id != tenant_id and not current_user.has_role("super_admin"):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")
    current_user.require_role("admin")

    from core.tenant_config import save_tenant_settings

    try:
        await save_tenant_settings(db, tenant_id, settings)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to save tenant settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to save settings")

    return {"success": True, "message": "Settings saved"}


@router.post("/{tenant_id}/settings/test-smtp")
async def test_smtp_settings(
    tenant_id: str,
    body: Dict[str, Any],
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

    smtp_port = int(await get_tenant_setting(db, tenant_id, "smtp_port", "587"))
    smtp_user = await get_tenant_setting(db, tenant_id, "smtp_user", "")
    smtp_pass = await get_tenant_setting(db, tenant_id, "smtp_pass", "")
    from_email = await get_tenant_setting(db, tenant_id, "from_email", "noreply@claimflow.io")
    to_email = body.get("to", current_user.email)

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
        logger.warning(f"SMTP test failed for tenant {tenant_id}: {e}")
        return {"success": False, "error": str(e)}


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
    import httpx

    api_key = await get_tenant_setting(db, tenant_id, "api_cert_key")
    if not api_key:
        return {"success": False, "error": "API-Cert key not configured"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.api-cert.com/v1/usage",
                headers={"X-API-Key": api_key},
            )
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"API-Cert returned {resp.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


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
    import httpx

    org_id = await get_tenant_setting(db, tenant_id, "caqh_org_id")
    username = await get_tenant_setting(db, tenant_id, "caqh_username")
    password = await get_tenant_setting(db, tenant_id, "caqh_password")

    if not (org_id and username and password):
        return {"success": False, "error": "CAQH credentials not fully configured"}

    try:
        base_url = "https://proview-demo.caqh.org/RosterAPI/api"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{base_url}/Roster",
                params={"organizationId": org_id},
                auth=(username, password),
            )
            if resp.status_code in (200, 401, 403):
                connected = resp.status_code == 200
                return {
                    "success": connected,
                    "message": "Connected to CAQH" if connected else f"CAQH returned {resp.status_code}",
                }
            return {"success": False, "error": f"CAQH returned {resp.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
