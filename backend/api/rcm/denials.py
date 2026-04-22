"""
Denial Management API
Work denial cases, generate appeals, track outcomes.

Access control: list/get + appeal generation require billing role (which
expands via the role hierarchy to admin / super_admin). Appeal generation
is audit-logged.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from typing import Optional
import logging

from core.database import get_db
from core.audit import log_audit_event
from models.denials import DenialCase, DenialPlaybook
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
    """List denial cases with filters - scoped to tenant. Returns full filtered total."""
    current_user.require_role("billing")
    try:
        filters = [DenialCase.tenant_id == current_user.tenant_id]
        if category:
            filters.append(DenialCase.denial_category == category)
        if priority:
            filters.append(DenialCase.priority == priority)
        if status:
            filters.append(DenialCase.status == status)

        data_query = (
            select(DenialCase).where(and_(*filters))
            .order_by(desc(DenialCase.created_at)).limit(limit).offset(offset)
        )
        count_query = select(func.count(DenialCase.id)).where(and_(*filters))

        result = await db.execute(data_query)
        denials = result.scalars().all()
        total = (await db.execute(count_query)).scalar() or 0

        # Single batched join to avoid N+1 lookups for claim_number.
        claim_ids = [d.claim_id for d in denials if d.claim_id]
        claim_numbers: dict = {}
        if claim_ids:
            claim_rows = await db.execute(
                select(Claim.id, Claim.claim_number).where(and_(
                    Claim.id.in_(claim_ids),
                    Claim.tenant_id == current_user.tenant_id,
                ))
            )
            claim_numbers = {row[0]: row[1] for row in claim_rows.all()}

        cases_with_claims = [{
            "id": denial.id,
            "claim_id": denial.claim_id,
            "claim_number": claim_numbers.get(denial.claim_id, "Unknown"),
            "carc_code": denial.carc_code,
            "rarc_code": denial.rarc_code,
            "denial_description": denial.denial_description,
            "denial_category": denial.denial_category,
            "denied_amount": float(denial.denied_amount) if denial.denied_amount else 0.0,
            "status": denial.status,
            "priority": denial.priority,
            "appeal_due_date": denial.appeal_due_date.isoformat() if denial.appeal_due_date else None,
            "days_until_due": denial.days_until_due,
            "assigned_to": denial.assigned_to,
            "created_at": denial.created_at.isoformat() if denial.created_at else None,
        } for denial in denials]

        return {
            "success": True,
            "data": cases_with_claims,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception:
        logger.exception("Error listing denial cases")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/cases/{denial_id}")
async def get_denial_case(
    denial_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Get denial case details with playbook - scoped to tenant"""
    current_user.require_role("billing")
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/cases/{denial_id}/generate-appeal")
async def generate_appeal_letter(
    denial_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Generate appeal letter from template - scoped to tenant; mutation audited."""
    current_user.require_role("billing")
    check = await db.execute(
        select(DenialCase.id).where(and_(
            DenialCase.id == denial_id,
            DenialCase.tenant_id == current_user.tenant_id,
        ))
    )
    if not check.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Denial case not found")

    try:
        denial_manager = DenialManager(db)
        result = await denial_manager.generate_appeal(denial_id, tenant_id=current_user.tenant_id)
        await log_audit_event(
            db, current_user, action="appeal_generated", resource_type="denial",
            resource_id=str(denial_id), request=request,
        )
        await db.commit()
        return {"success": True, "data": result}
    except Exception:
        logger.exception("Error generating appeal")
        raise HTTPException(status_code=500, detail="Internal server error")
