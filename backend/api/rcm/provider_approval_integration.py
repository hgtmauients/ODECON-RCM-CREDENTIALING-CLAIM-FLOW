"""
Provider Approval -> Payer Enrollment Integration
Hook that connects Stage 1 (verification) to Stage 2 (payer enrollment)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Dict, Any
import logging

from core.database import get_db
from api.auth import get_current_user, Principal
from models.credentialing import ProviderCredentialing
from services.smart_payer_enrollment import create_smart_payer_enrollment_cases, get_provider_eligible_payers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rcm/integration", tags=["RCM - Integration"])


@router.post("/provider/{provider_id}/create-payer-cases")
async def trigger_payer_case_creation(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Manually trigger payer enrollment case creation - scoped to tenant"""
    try:
        cred_result = await db.execute(
            select(ProviderCredentialing).where(and_(
                ProviderCredentialing.provider_id == provider_id,
                ProviderCredentialing.tenant_id == current_user.tenant_id,
            ))
        )
        provider_cred = cred_result.scalar_one_or_none()

        if not provider_cred:
            raise HTTPException(status_code=404, detail="Provider not found")

        if provider_cred.credentialing_status != "passed":
            raise HTTPException(
                status_code=400,
                detail=f"Provider must be approved first (current status: {provider_cred.credentialing_status})",
            )

        result = await create_smart_payer_enrollment_cases(
            provider_id=provider_id,
            db=db,
            provider_verification_data=provider_cred.signup_data or {},
            tenant_id=current_user.tenant_id,
        )

        return {"success": True, "data": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering payer case creation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/provider/{provider_id}/eligible-payers")
async def get_eligible_payers_for_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Get list of payers provider is eligible for - scoped to tenant"""
    try:
        result = await get_provider_eligible_payers(provider_id, db, tenant_id=current_user.tenant_id)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error getting eligible payers: {e}")
        raise HTTPException(status_code=500, detail=str(e))
