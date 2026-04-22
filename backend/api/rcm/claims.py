"""
Claims API Endpoints
Create, validate, submit, and track claims through full lifecycle
"""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, date
import logging

from core.database import get_db
from models.claims import Claim, ClaimLine, ClaimDiagnosis, ClaimEvent, EDIFile, ClaimQueue
from models.rcm import PayerProfile
from api.auth import get_current_user, Principal
from services.rules_engine import RulesEngine
from services.edi_processor import EDIProcessor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rcm/claims", tags=["RCM - Claims"])


@router.get("")
async def list_claims(
    state: Optional[str] = None,
    queue: Optional[str] = None,
    payer_id: Optional[int] = None,
    provider_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List claims with filters - scoped to tenant"""
    try:
        query = select(Claim).where(Claim.tenant_id == current_user.tenant_id)

        if state:
            query = query.where(Claim.state == state)
        if queue:
            query = query.where(Claim.current_queue == queue)
        if payer_id:
            query = query.where(Claim.payer_id == payer_id)
        if provider_id:
            query = query.where(Claim.provider_id == provider_id)
        if date_from:
            query = query.where(Claim.service_date_from >= date_from)
        if date_to:
            query = query.where(Claim.service_date_from <= date_to)

        query = query.order_by(desc(Claim.created_date)).limit(limit).offset(offset)

        result = await db.execute(query)
        claims = result.scalars().all()

        return {
            "success": True,
            "data": [{
                "id": c.id,
                "claim_number": c.claim_number,
                "payer_claim_id": c.payer_claim_id,
                "payer_id": c.payer_id,
                "state": c.state,
                "current_queue": c.current_queue,
                "service_date_from": c.service_date_from.isoformat() if c.service_date_from else None,
                "total_charges": float(c.total_charges) if c.total_charges else 0,
                "total_paid": float(c.total_paid) if c.total_paid else None,
                "created_date": c.created_date.isoformat() if c.created_date else None,
                "submitted_date": c.submitted_date.isoformat() if c.submitted_date else None,
            } for c in claims],
            "total": len(claims),
        }
    except Exception as e:
        logger.error(f"Error listing claims: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{claim_id}")
async def get_claim_detail(
    claim_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Get single claim detail - scoped to tenant"""
    result = await db.execute(
        select(Claim).where(and_(Claim.id == claim_id, Claim.tenant_id == current_user.tenant_id))
    )
    claim = result.scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    lines_result = await db.execute(select(ClaimLine).where(ClaimLine.claim_id == claim.id))
    lines = lines_result.scalars().all()

    dx_result = await db.execute(select(ClaimDiagnosis).where(ClaimDiagnosis.claim_id == claim.id))
    diagnoses = dx_result.scalars().all()

    return {
        "success": True,
        "data": {
            "id": claim.id,
            "claim_number": claim.claim_number,
            "payer_claim_id": claim.payer_claim_id,
            "payer_id": claim.payer_id,
            "patient_id": claim.patient_id,
            "provider_id": claim.provider_id,
            "state": claim.state,
            "current_queue": claim.current_queue,
            "service_date_from": claim.service_date_from.isoformat() if claim.service_date_from else None,
            "service_date_to": claim.service_date_to.isoformat() if claim.service_date_to else None,
            "total_charges": float(claim.total_charges) if claim.total_charges else 0,
            "total_allowed": float(claim.total_allowed) if claim.total_allowed else None,
            "total_paid": float(claim.total_paid) if claim.total_paid else None,
            "patient_responsibility": float(claim.patient_responsibility) if claim.patient_responsibility else None,
            "claim_type": claim.claim_type,
            "billing_provider_npi": claim.billing_provider_npi,
            "rendering_provider_npi": claim.rendering_provider_npi,
            "prior_auth_number": claim.prior_auth_number,
            "filing_deadline": claim.filing_deadline.isoformat() if claim.filing_deadline else None,
            "denial_reason": claim.denial_reason,
            "denial_category": claim.denial_category,
            "created_date": claim.created_date.isoformat() if claim.created_date else None,
            "submitted_date": claim.submitted_date.isoformat() if claim.submitted_date else None,
            "lines": [{
                "id": l.id,
                "line_number": l.line_number,
                "cpt_code": l.cpt_code,
                "cpt_description": l.cpt_description,
                "modifiers": l.modifiers,
                "units": l.units,
                "charge_amount": float(l.charge_amount) if l.charge_amount else 0,
                "paid_amount": float(l.paid_amount) if l.paid_amount else None,
                "is_denied": l.is_denied,
                "carc_code": l.carc_code,
            } for l in lines],
            "diagnoses": [{
                "icd10_code": d.icd10_code,
                "icd10_description": d.icd10_description,
                "is_primary": d.is_primary,
            } for d in diagnoses],
        },
    }


@router.post("")
async def create_claim(
    claim_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Create new claim - scoped to tenant"""
    try:
        import uuid
        short_id = uuid.uuid4().hex[:8].upper()
        claim_number = f"CLM-{datetime.now().strftime('%Y%m%d')}-{short_id}"

        # Parse date fields from strings
        safe_data = {}
        date_fields = {'service_date_from', 'service_date_to', 'filing_deadline', 'appeal_due_date'}
        for k, v in claim_data.items():
            if k in ('id', 'lines', 'diagnoses'):
                continue
            if k in date_fields and isinstance(v, str):
                safe_data[k] = date.fromisoformat(v)
            else:
                safe_data[k] = v

        new_claim = Claim(
            tenant_id=current_user.tenant_id,
            claim_number=claim_number,
            **safe_data,
            created_by=current_user.email,
            state="draft",
        )

        db.add(new_claim)
        await db.flush()

        if 'lines' in claim_data:
            for line_data in claim_data['lines']:
                ld = {**line_data}
                if 'service_date' in ld and isinstance(ld['service_date'], str):
                    ld['service_date'] = date.fromisoformat(ld['service_date'])
                line = ClaimLine(claim_id=new_claim.id, **ld)
                db.add(line)

        if 'diagnoses' in claim_data:
            for dx_data in claim_data['diagnoses']:
                dx = ClaimDiagnosis(claim_id=new_claim.id, **dx_data)
                db.add(dx)

        await db.commit()
        await db.refresh(new_claim)

        logger.info(f"Created claim {claim_number} for tenant {current_user.tenant_id}")

        return {
            "success": True,
            "message": "Claim created successfully",
            "data": {"id": new_claim.id, "claim_number": claim_number},
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating claim: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{claim_id}/validate")
async def validate_claim(
    claim_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Validate claim against payer rules - scoped to tenant"""
    try:
        claim_result = await db.execute(
            select(Claim).where(and_(Claim.id == claim_id, Claim.tenant_id == current_user.tenant_id))
        )
        claim = claim_result.scalar_one_or_none()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        rules_engine = RulesEngine(db)
        results = await rules_engine.validate_claim(claim_id)

        if results["passed"]:
            claim.state = "validated"
            claim.validated_date = datetime.utcnow()
            claim.current_queue = "ready_to_submit"
            await db.commit()

        return {"success": True, "data": results}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating claim {claim_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch/submit")
async def submit_claim_batch(
    batch: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Submit batch of claims - scoped to tenant"""
    current_user.require_role("billing")
    claim_ids: List[int] = batch.get("claim_ids", [])
    payer_id: int = batch.get("payer_id", 0)
    if not claim_ids or not payer_id:
        raise HTTPException(status_code=422, detail="claim_ids and payer_id are required")
    try:
        # Verify all claims belong to this tenant
        for cid in claim_ids:
            check = await db.execute(
                select(Claim.id).where(and_(Claim.id == cid, Claim.tenant_id == current_user.tenant_id))
            )
            if not check.scalar_one_or_none():
                raise HTTPException(status_code=404, detail=f"Claim {cid} not found")

        # Verify payer belongs to this tenant
        from models.rcm import PayerProfile
        payer_check = await db.execute(
            select(PayerProfile.id).where(and_(PayerProfile.id == payer_id, PayerProfile.tenant_id == current_user.tenant_id))
        )
        if not payer_check.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Payer not found")

        edi_processor = EDIProcessor(db)
        result = await edi_processor.generate_837(claim_ids, payer_id)

        try:
            from services.clearinghouse_transport import ClearinghouseService

            transport = ClearinghouseService(db)
            send_result = await transport.submit_837_file(
                local_file_path=result["file_path"],
                payer_id=payer_id,
            )

            edi_file_result = await db.execute(select(EDIFile).where(EDIFile.id == result["file_id"]))
            edi_file = edi_file_result.scalar_one_or_none()

            if edi_file:
                if send_result["success"]:
                    edi_file.status = "transmitted"
                    edi_file.processed_at = datetime.utcnow()

                    for cid in claim_ids:
                        claim_result = await db.execute(select(Claim).where(Claim.id == cid))
                        claim = claim_result.scalar_one_or_none()
                        if claim:
                            claim.state = "submitted"
                            claim.submitted_date = datetime.utcnow()
                            event = ClaimEvent(
                                claim_id=claim.id,
                                event_type="submitted_to_clearinghouse",
                                from_state="ready_to_submit",
                                to_state="submitted",
                                data=send_result,
                                message=f"Claim submitted via {send_result.get('method', 'clearinghouse')}",
                            )
                            db.add(event)

                    await db.commit()
                    return {
                        "success": True,
                        "message": f"Batch submitted and transmitted: {result['claim_count']} claims",
                        "data": {**result, "transmission": send_result},
                    }
                else:
                    edi_file.status = "transmission_failed"
                    edi_file.error_message = send_result.get("error")
                    await db.commit()
                    return {
                        "success": False,
                        "message": f"837P generated but transmission failed: {send_result.get('error')}",
                        "data": {**result, "transmission": send_result},
                    }
        except ImportError:
            return {
                "success": True,
                "message": "837P file generated. Manual upload required.",
                "data": {**result, "manual_upload_required": True},
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting batch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{claim_id}/events")
async def get_claim_events(
    claim_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Get event timeline for claim - scoped to tenant"""
    # Verify claim belongs to tenant
    claim_check = await db.execute(
        select(Claim.id).where(and_(Claim.id == claim_id, Claim.tenant_id == current_user.tenant_id))
    )
    if not claim_check.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Claim not found")

    result = await db.execute(
        select(ClaimEvent).where(ClaimEvent.claim_id == claim_id).order_by(ClaimEvent.timestamp)
    )
    events = result.scalars().all()

    return {
        "success": True,
        "data": [{
            "id": e.id,
            "event_type": e.event_type,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "from_state": e.from_state,
            "to_state": e.to_state,
            "message": e.message,
            "data": e.data,
        } for e in events],
    }


@router.get("/queues/list")
async def list_queues(
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List all claim queues with counts - scoped to tenant"""
    try:
        result = await db.execute(
            select(ClaimQueue).where(
                and_(ClaimQueue.is_active == True, ClaimQueue.tenant_id == current_user.tenant_id)
            )
        )
        queues = result.scalars().all()

        queue_data = []
        for queue in queues:
            count_result = await db.execute(
                select(func.count(Claim.id)).where(
                    and_(Claim.current_queue == queue.name, Claim.tenant_id == current_user.tenant_id)
                )
            )
            count = count_result.scalar() or 0

            queue_data.append({
                "id": queue.id,
                "name": queue.name,
                "display_name": queue.display_name,
                "description": queue.description,
                "count": count,
                "color": queue.color,
                "icon": queue.icon,
            })

        return {"success": True, "data": queue_data}
    except Exception as e:
        logger.error(f"Error listing queues: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import/csv")
async def import_claims_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """
    Import claims from CSV file.
    Expected columns: patient_id, provider_id, payer_id, service_date_from,
    total_charges, claim_type, cpt_code, units, charge_amount, icd10_code
    """
    import csv
    import io

    content = await file.read()
    csv_file = io.StringIO(content.decode("utf-8"))
    reader = csv.DictReader(csv_file)

    created_claims = []
    errors = []

    for row_num, row in enumerate(reader, start=2):
        try:
            import uuid as _uuid
            short_id = _uuid.uuid4().hex[:8].upper()
            claim_number = f"CLM-{datetime.now().strftime('%Y%m%d')}-{short_id}"
            new_claim = Claim(
                tenant_id=current_user.tenant_id,
                claim_number=claim_number,
                patient_id=int(row.get("patient_id", 0)) if row.get("patient_id") else None,
                provider_id=int(row.get("provider_id", 0)) if row.get("provider_id") else None,
                payer_id=int(row.get("payer_id", 0)) if row.get("payer_id") else None,
                service_date_from=datetime.strptime(row["service_date_from"], "%Y-%m-%d").date() if row.get("service_date_from") else datetime.utcnow().date(),
                total_charges=float(row.get("total_charges", 0)),
                claim_type=row.get("claim_type", "professional"),
                billing_provider_npi=row.get("billing_provider_npi"),
                state="draft",
                created_by=current_user.email,
            )
            db.add(new_claim)
            await db.flush()

            if row.get("cpt_code"):
                line = ClaimLine(
                    claim_id=new_claim.id,
                    line_number=1,
                    cpt_code=row["cpt_code"],
                    units=int(row.get("units", 1)),
                    charge_amount=float(row.get("charge_amount", row.get("total_charges", 0))),
                )
                db.add(line)

            if row.get("icd10_code"):
                dx = ClaimDiagnosis(
                    claim_id=new_claim.id,
                    diagnosis_pointer=1,
                    icd10_code=row["icd10_code"],
                    is_primary=True,
                )
                db.add(dx)

            created_claims.append(claim_number)
        except Exception as e:
            errors.append({"row": row_num, "error": str(e)})

    await db.commit()

    return {
        "success": True,
        "message": f"Imported {len(created_claims)} claims",
        "data": {
            "claims_created": len(created_claims),
            "errors": errors,
        },
    }


@router.delete("/{claim_id}")
async def delete_claim(
    claim_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Delete a claim - scoped to tenant. Only draft/rejected claims can be deleted."""
    result = await db.execute(
        select(Claim).where(and_(Claim.id == claim_id, Claim.tenant_id == current_user.tenant_id))
    )
    claim = result.scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.state not in ("draft", "rejected", "void"):
        raise HTTPException(status_code=400, detail=f"Cannot delete claim in '{claim.state}' state. Void it first.")
    await db.delete(claim)
    await db.commit()
    return {"success": True, "message": "Claim deleted"}


@router.post("/batch/delete")
async def batch_delete_claims(
    body: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Delete multiple claims. Only draft/rejected/void claims can be deleted."""
    claim_ids = body.get("claim_ids", [])
    if not claim_ids:
        raise HTTPException(status_code=422, detail="claim_ids required")

    deleted = 0
    errors = []
    for cid in claim_ids:
        result = await db.execute(
            select(Claim).where(and_(Claim.id == cid, Claim.tenant_id == current_user.tenant_id))
        )
        claim = result.scalar_one_or_none()
        if not claim:
            errors.append(f"Claim {cid} not found")
        elif claim.state not in ("draft", "rejected", "void"):
            errors.append(f"Claim {cid} in '{claim.state}' state cannot be deleted")
        else:
            await db.delete(claim)
            deleted += 1

    await db.commit()
    return {"success": True, "data": {"deleted": deleted, "errors": errors}}


@router.post("/{claim_id}/void")
async def void_claim(
    claim_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Void a claim (soft-delete, keeps record for audit)."""
    result = await db.execute(
        select(Claim).where(and_(Claim.id == claim_id, Claim.tenant_id == current_user.tenant_id))
    )
    claim = result.scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    claim.previous_state = claim.state
    claim.state = "void"
    event = ClaimEvent(
        claim_id=claim.id,
        event_type="voided",
        from_state=claim.previous_state,
        to_state="void",
        message=f"Claim voided by {current_user.email}",
    )
    db.add(event)
    await db.commit()
    return {"success": True, "message": "Claim voided"}
