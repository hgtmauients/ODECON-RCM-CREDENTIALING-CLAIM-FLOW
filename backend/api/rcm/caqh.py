"""
ClaimFlow - CAQH ProView API endpoints.
Pull provider credentialing data from CAQH, search by NPI, manage roster.
Uses per-tenant credentials resolved via tenant_config.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Dict, Any, Optional
import logging

from core.database import get_db
from api.auth import get_current_user, Principal
from models.credentialing import ProviderCredentialing

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rcm/caqh", tags=["RCM - CAQH ProView"])


async def _get_client(db: AsyncSession, tenant_id: str):
    from services.caqh_proview import get_tenant_client
    return await get_tenant_client(db, tenant_id)


async def _require_configured(db: AsyncSession, tenant_id: str):
    from services.caqh_proview import is_configured_for_tenant
    if not await is_configured_for_tenant(db, tenant_id):
        raise HTTPException(
            status_code=503,
            detail="CAQH ProView not configured — set credentials in Settings",
        )


@router.get("/status")
async def caqh_integration_status(
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Check if CAQH ProView integration is configured for the current tenant."""
    current_user.require_role("admin")
    from services.caqh_proview import is_configured_for_tenant
    configured = await is_configured_for_tenant(db, current_user.tenant_id)
    return {
        "configured": configured,
        "message": "CAQH ProView is active" if configured else "Configure CAQH credentials in Settings to enable",
    }


@router.get("/search/{npi}")
async def search_caqh_by_npi(
    npi: str,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Search CAQH ProView for a provider by NPI."""
    current_user.require_role("admin")
    await _require_configured(db, current_user.tenant_id)
    client = await _get_client(db, current_user.tenant_id)
    result = await client.search_by_npi(npi)
    return {"success": True, "data": result}


@router.get("/provider/{caqh_id}/status")
async def get_caqh_provider_status(
    caqh_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Get CAQH attestation status for a provider."""
    current_user.require_role("admin")
    await _require_configured(db, current_user.tenant_id)
    client = await _get_client(db, current_user.tenant_id)
    result = await client.get_provider_status(caqh_id)
    return {"success": True, "data": result}


@router.get("/provider/{caqh_id}/data")
async def pull_caqh_provider_data(
    caqh_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """
    Pull full credentialing profile from CAQH ProView.
    Returns licenses, certifications, malpractice, education, DEA, privileges.
    """
    current_user.require_role("admin")
    await _require_configured(db, current_user.tenant_id)
    client = await _get_client(db, current_user.tenant_id)
    result = await client.get_provider_data(caqh_id)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "Failed to pull CAQH data"))

    return {"success": True, "data": result}


@router.post("/provider/{caqh_id}/import")
async def import_caqh_to_credentialing(
    caqh_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """
    Pull CAQH data and create/update a ProviderCredentialing record.
    Automatically populates verification fields from CAQH.
    """
    current_user.require_role("admin")
    await _require_configured(db, current_user.tenant_id)
    client = await _get_client(db, current_user.tenant_id)
    caqh_data = await client.get_provider_data(caqh_id)
    if not caqh_data.get("success"):
        raise HTTPException(status_code=502, detail=caqh_data.get("error", "CAQH pull failed"))

    demo = caqh_data.get("demographics", {})
    npi = demo.get("npi", "")
    provider_id = f"CAQH_{npi}_{caqh_id}" if npi else f"CAQH_{caqh_id}"

    existing = await db.execute(
        select(ProviderCredentialing).where(and_(
            ProviderCredentialing.provider_id == provider_id,
            ProviderCredentialing.tenant_id == current_user.tenant_id,
        ))
    )
    credentialing = existing.scalar_one_or_none()

    licenses = caqh_data.get("licenses", [])
    active_licenses = [l for l in licenses if l.get("status", "").upper() in ("ACTIVE", "CURRENT", "")]
    license_verified = len(active_licenses) > 0

    if credentialing:
        credentialing.signup_data = {
            **demo,
            "caqh_provider_id": caqh_id,
            "source": "caqh_proview",
        }
        credentialing.npi_verification = {"verified": bool(npi), "npi": npi, "source": "caqh"}
        credentialing.state_license_verification = {
            "verified": license_verified,
            "licenses": active_licenses,
            "source": "caqh",
        }
    else:
        from datetime import datetime
        credentialing = ProviderCredentialing(
            tenant_id=current_user.tenant_id,
            provider_id=provider_id,
            signup_data={
                "first_name": demo.get("first_name", ""),
                "last_name": demo.get("last_name", ""),
                "email": demo.get("email", ""),
                "npi": npi,
                "state_code": active_licenses[0]["state"] if active_licenses else "",
                "license_number": active_licenses[0]["license_number"] if active_licenses else "",
                "specialty": caqh_data.get("board_certifications", [{}])[0].get("specialty", "") if caqh_data.get("board_certifications") else "",
                "caqh_provider_id": caqh_id,
                "source": "caqh_proview",
            },
            npi_verification={"verified": bool(npi), "npi": npi, "source": "caqh"},
            state_license_verification={
                "verified": license_verified,
                "licenses": active_licenses,
                "source": "caqh",
            },
            background_check=None,
            oig_check=None,
            sam_check=None,
            credentialing_status="pending",
        )
        db.add(credentialing)

    await db.commit()

    return {
        "success": True,
        "provider_id": provider_id,
        "data": {
            "licenses_found": len(licenses),
            "active_licenses": len(active_licenses),
            "certifications": len(caqh_data.get("board_certifications", [])),
            "malpractice_policies": len(caqh_data.get("malpractice_insurance", [])),
            "education_records": len(caqh_data.get("education", [])),
            "dea_certificates": len(caqh_data.get("dea_certificates", [])),
            "hospital_privileges": len(caqh_data.get("hospital_privileges", [])),
        },
    }


@router.post("/roster/add")
async def add_provider_to_caqh_roster(
    body: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Add a provider to your CAQH organization roster."""
    current_user.require_role("admin")
    await _require_configured(db, current_user.tenant_id)
    client = await _get_client(db, current_user.tenant_id)
    result = await client.add_to_roster(body)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "Roster add failed"))

    return {"success": True, "data": result}
