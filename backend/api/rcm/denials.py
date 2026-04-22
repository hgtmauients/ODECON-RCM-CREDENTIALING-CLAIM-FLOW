"""
Denial Management API
Work denial cases, generate appeals, track outcomes
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from core.database import get_db
from models.denials import DenialCase, DenialPlaybook, AppealTemplate
from models.claims import Claim
from api.auth import get_current_user, Principal
from services.denial_manager import DenialManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rcm/denials", tags=["RCM - Denials"])


@router.get("/cases")
async def list_denial_cases(
    category: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List denial cases with filters - scoped to tenant"""
    try:
        query = select(DenialCase).where(DenialCase.tenant_id == current_user.tenant_id)

        if category:
            query = query.where(DenialCase.denial_category == category)
        if priority:
            query = query.where(DenialCase.priority == priority)
        if status:
            query = query.where(DenialCase.status == status)

        query = query.order_by(desc(DenialCase.created_at)).limit(limit).offset(offset)

        result = await db.execute(query)
        denials = result.scalars().all()

        cases_with_claims = []
        for denial in denials:
            claim_result = await db.execute(
                select(Claim).where(and_(Claim.id == denial.claim_id, Claim.tenant_id == current_user.tenant_id))
            )
            claim = claim_result.scalar_one_or_none()

            cases_with_claims.append({
                "id": denial.id,
                "claim_id": denial.claim_id,
                "claim_number": claim.claim_number if claim else "Unknown",
                "carc_code": denial.carc_code,
                "rarc_code": denial.rarc_code,
                "denial_description": denial.denial_description,
                "denial_category": denial.denial_category,
                "denied_amount": float(denial.denied_amount),
                "status": denial.status,
                "priority": denial.priority,
                "appeal_due_date": denial.appeal_due_date.isoformat() if denial.appeal_due_date else None,
                "days_until_due": denial.days_until_due,
                "assigned_to": denial.assigned_to,
                "created_at": denial.created_at.isoformat() if denial.created_at else None,
            })

        return {"success": True, "data": cases_with_claims}
    except Exception as e:
        logger.error(f"Error listing denial cases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cases/{denial_id}")
async def get_denial_case(
    denial_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Get denial case details with playbook - scoped to tenant"""
    try:
        result = await db.execute(
            select(DenialCase).where(
                and_(DenialCase.id == denial_id, DenialCase.tenant_id == current_user.tenant_id)
            )
        )
        denial = result.scalar_one_or_none()

        if not denial:
            raise HTTPException(status_code=404, detail="Denial case not found")

        playbook = None
        if denial.playbook_id:
            playbook_result = await db.execute(
                select(DenialPlaybook).where(and_(
                    DenialPlaybook.id == denial.playbook_id,
                    DenialPlaybook.tenant_id == current_user.tenant_id,
                ))
            )
            playbook = playbook_result.scalar_one_or_none()

        claim_result = await db.execute(
            select(Claim).where(and_(Claim.id == denial.claim_id, Claim.tenant_id == current_user.tenant_id))
        )
        claim = claim_result.scalar_one_or_none()

        return {
            "success": True,
            "data": {
                "denial": {
                    "id": denial.id,
                    "claim_number": claim.claim_number if claim else None,
                    "carc_code": denial.carc_code,
                    "rarc_code": denial.rarc_code,
                    "denial_description": denial.denial_description,
                    "denial_category": denial.denial_category,
                    "denied_amount": float(denial.denied_amount),
                    "status": denial.status,
                    "priority": denial.priority,
                    "appeal_due_date": denial.appeal_due_date.isoformat() if denial.appeal_due_date else None,
                    "days_until_due": denial.days_until_due,
                },
                "playbook": {
                    "name": playbook.playbook_name,
                    "instructions": playbook.staff_instructions,
                    "required_attachments": playbook.required_attachments,
                    "submission_method": playbook.submission_method,
                    "typical_turnaround_days": playbook.typical_turnaround_days,
                    "success_rate": float(playbook.success_rate) if playbook.success_rate else None,
                } if playbook else None,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting denial case: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cases/{denial_id}/generate-appeal")
async def generate_appeal_letter(
    denial_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Generate appeal letter from template - scoped to tenant"""
    # Verify ownership
    check = await db.execute(
        select(DenialCase.id).where(
            and_(DenialCase.id == denial_id, DenialCase.tenant_id == current_user.tenant_id)
        )
    )
    if not check.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Denial case not found")

    try:
        denial_manager = DenialManager(db)
        result = await denial_manager.generate_appeal(denial_id, tenant_id=current_user.tenant_id)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Error generating appeal: {e}")
        raise HTTPException(status_code=500, detail=str(e))
