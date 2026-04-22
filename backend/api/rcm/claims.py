"""
Claims API Endpoints
Create, validate, submit, and track claims through full lifecycle.

Access control: every route requires billing role (which expands to
admin / super_admin via the role hierarchy). Mutations are audit-logged.
"""

import os
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, date
import logging

from core.database import get_db
from core.audit import log_audit_event
from core.csv_export import csv_response
from models.claims import Claim, ClaimLine, ClaimDiagnosis, ClaimEvent, EDIFile, ClaimQueue
from models.rcm import PayerProfile
from api.auth import get_current_user, Principal
from services.rules_engine import RulesEngine
from services.edi_processor import EDIProcessor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rcm/claims", tags=["RCM - Claims"])

MAX_CLAIMS_CSV_BYTES = int(os.getenv("MAX_CLAIMS_CSV_BYTES", str(20 * 1024 * 1024)))  # 20 MB


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
    """List claims with filters - scoped to tenant. Returns full filtered total."""
    current_user.require_role("billing")
    try:
        filters = [Claim.tenant_id == current_user.tenant_id]
        if state:
            filters.append(Claim.state == state)
        if queue:
            filters.append(Claim.current_queue == queue)
        if payer_id:
            filters.append(Claim.payer_id == payer_id)
        if provider_id:
            filters.append(Claim.provider_id == provider_id)
        if date_from:
            filters.append(Claim.service_date_from >= date_from)
        if date_to:
            filters.append(Claim.service_date_from <= date_to)

        data_query = (
            select(Claim)
            .where(and_(*filters))
            .order_by(desc(Claim.created_date))
            .limit(limit)
            .offset(offset)
        )
        count_query = select(func.count(Claim.id)).where(and_(*filters))

        data_result = await db.execute(data_query)
        claims = data_result.scalars().all()

        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

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
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.exception("Error listing claims")
        raise HTTPException(status_code=500, detail="Failed to list claims")


@router.get("/export.csv")
async def export_claims_csv(
    request: Request,
    state: Optional[str] = None,
    queue: Optional[str] = None,
    payer_id: Optional[int] = None,
    provider_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(10000, ge=1, le=50000),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Stream filtered claims as CSV. Same filters as GET /rcm/claims."""
    current_user.require_role("billing")

    filters = [Claim.tenant_id == current_user.tenant_id]
    if state:
        filters.append(Claim.state == state)
    if queue:
        filters.append(Claim.current_queue == queue)
    if payer_id:
        filters.append(Claim.payer_id == payer_id)
    if provider_id:
        filters.append(Claim.provider_id == provider_id)
    if date_from:
        filters.append(Claim.service_date_from >= date_from)
    if date_to:
        filters.append(Claim.service_date_from <= date_to)

    query = (
        select(Claim).where(and_(*filters))
        .order_by(desc(Claim.created_date)).limit(limit)
    )
    rows = (await db.execute(query)).scalars().all()

    await log_audit_event(
        db, current_user, action="claims_csv_exported", resource_type="claim",
        resource_id="batch", request=request,
        metadata={"row_count": len(rows), "filters": {"state": state, "payer_id": payer_id}},
    )
    await db.commit()

    fieldnames = [
        "id", "claim_number", "payer_claim_id", "payer_id", "patient_id",
        "provider_id", "state", "current_queue",
        "service_date_from", "service_date_to",
        "total_charges", "total_allowed", "total_paid",
        "billing_provider_npi", "rendering_provider_npi",
        "claim_type", "denial_reason", "denial_category",
        "created_date", "submitted_date",
    ]
    return csv_response(
        filename=f"claims_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        rows=rows,
        fieldnames=fieldnames,
        row_to_dict=lambda c: {
            "id": c.id,
            "claim_number": c.claim_number,
            "payer_claim_id": c.payer_claim_id,
            "payer_id": c.payer_id,
            "patient_id": c.patient_id,
            "provider_id": c.provider_id,
            "state": c.state,
            "current_queue": c.current_queue,
            "service_date_from": c.service_date_from,
            "service_date_to": c.service_date_to,
            "total_charges": float(c.total_charges) if c.total_charges else 0,
            "total_allowed": float(c.total_allowed) if c.total_allowed else None,
            "total_paid": float(c.total_paid) if c.total_paid else None,
            "billing_provider_npi": c.billing_provider_npi,
            "rendering_provider_npi": c.rendering_provider_npi,
            "claim_type": c.claim_type,
            "denial_reason": c.denial_reason,
            "denial_category": c.denial_category,
            "created_date": c.created_date,
            "submitted_date": c.submitted_date,
        },
    )


@router.get("/{claim_id}")
async def get_claim_detail(
    claim_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Get single claim detail - scoped to tenant"""
    current_user.require_role("billing")
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
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Create new claim - scoped to tenant; mutation audited."""
    current_user.require_role("billing")
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

        await log_audit_event(
            db, current_user, action="claim_created", resource_type="claim",
            resource_id=str(new_claim.id), request=request,
            metadata={"claim_number": claim_number, "payer_id": new_claim.payer_id},
        )
        await db.commit()
        await db.refresh(new_claim)

        logger.info(f"Created claim {claim_number} for tenant {current_user.tenant_id}")

        return {
            "success": True,
            "message": "Claim created successfully",
            "data": {"id": new_claim.id, "claim_number": claim_number},
        }
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Error creating claim")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{claim_id}")
async def update_draft_claim(
    claim_id: int,
    updates: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Edit a draft claim. Only allowed when state == 'draft' to keep submitted
    claims immutable for audit + EDI integrity. Mutation audited."""
    current_user.require_role("billing")
    try:
        result = await db.execute(
            select(Claim)
            .where(and_(Claim.id == claim_id, Claim.tenant_id == current_user.tenant_id))
            .with_for_update()
        )
        claim = result.scalar_one_or_none()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")
        if claim.state != "draft":
            raise HTTPException(
                status_code=409,
                detail=f"Cannot edit claim in state '{claim.state}' — only draft claims are editable. Use the corrected-claim flow instead.",
            )

        # total_charges is derived from line items, not user-set, so it's
        # excluded from the editable set (closes v9-M4: desync risk).
        editable = {
            "patient_id", "provider_id", "payer_id",
            "service_date_from", "service_date_to",
            "claim_type", "billing_provider_npi", "rendering_provider_npi",
            "prior_auth_number",
        }
        date_fields = {"service_date_from", "service_date_to"}
        applied = []
        for key, value in (updates or {}).items():
            if key not in editable or not hasattr(claim, key):
                continue
            if key in date_fields and isinstance(value, str):
                value = date.fromisoformat(value)
            setattr(claim, key, value)
            applied.append(key)

        await log_audit_event(
            db, current_user, action="claim_updated", resource_type="claim",
            resource_id=str(claim_id), request=request,
            changes={"updated_fields": sorted(applied)},
        )
        await db.commit()
        return {"success": True, "message": "Claim updated"}
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Error updating claim %s", claim_id)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{claim_id}/validate")
async def validate_claim(
    claim_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Validate claim against payer rules - scoped to tenant"""
    current_user.require_role("billing")
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/batch/submit")
async def submit_claim_batch(
    batch: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Submit batch of claims - scoped to tenant; submission audited."""
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
        result = await edi_processor.generate_837(claim_ids, payer_id, tenant_id=current_user.tenant_id)

        try:
            from services.clearinghouse_transport import ClearinghouseService

            transport = ClearinghouseService(db)
            send_result = await transport.submit_837_file(
                local_file_path=result["file_path"],
                payer_id=payer_id,
            )

            edi_file_result = await db.execute(
                select(EDIFile).where(and_(
                    EDIFile.id == result["file_id"],
                    EDIFile.tenant_id == current_user.tenant_id,
                ))
            )
            edi_file = edi_file_result.scalar_one_or_none()

            if edi_file:
                if send_result["success"]:
                    edi_file.status = "transmitted"
                    edi_file.processed_at = datetime.utcnow()

                    for cid in claim_ids:
                        claim_result = await db.execute(
                            select(Claim).where(and_(
                                Claim.id == cid,
                                Claim.tenant_id == current_user.tenant_id,
                            ))
                        )
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

                    await log_audit_event(
                        db, current_user, action="claim_batch_submitted", resource_type="claim",
                        resource_id="batch", request=request,
                        metadata={
                            "claim_ids": claim_ids, "payer_id": payer_id,
                            "transmission_method": send_result.get("method"),
                            "edi_file_id": result.get("file_id"),
                        },
                    )
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{claim_id}/events")
async def get_claim_events(
    claim_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Get event timeline for claim - scoped to tenant"""
    current_user.require_role("billing")
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
    current_user.require_role("billing")
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/import/csv")
async def import_claims_csv(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Import claims from CSV. Billing role; size-capped; per-row rollback.

    Expected columns: patient_id, provider_id, payer_id, service_date_from,
    total_charges, claim_type, cpt_code, units, charge_amount, icd10_code

    Hardening (closes v9-M5/M6/M7):
      - billing role gate
      - 20 MB size cap, .csv extension check
      - per-row commit so a bad row does NOT cascade-fail subsequent rows
      - audit log at end with batch counts
    """
    current_user.require_role("billing")
    import csv
    import io
    import uuid as _uuid
    from models.patient import Patient

    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    content = await file.read(MAX_CLAIMS_CSV_BYTES + 1)
    if len(content) > MAX_CLAIMS_CSV_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"CSV exceeds maximum size of {MAX_CLAIMS_CSV_BYTES // (1024 * 1024)} MB",
        )
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    csv_file = io.StringIO(content.decode("utf-8", errors="replace"))
    reader = csv.DictReader(csv_file)

    patients_q = await db.execute(
        select(Patient.id).where(Patient.tenant_id == current_user.tenant_id)
    )
    valid_patient_ids = {row[0] for row in patients_q.all()}

    payers_q = await db.execute(
        select(PayerProfile.id).where(PayerProfile.tenant_id == current_user.tenant_id)
    )
    valid_payer_ids = {row[0] for row in payers_q.all()}

    created_claims: List[str] = []
    errors: List[Dict[str, Any]] = []

    for row_num, row in enumerate(reader, start=2):
        try:
            patient_id = int(row.get("patient_id", 0)) if row.get("patient_id") else None
            payer_id = int(row.get("payer_id", 0)) if row.get("payer_id") else None

            if patient_id is not None and patient_id not in valid_patient_ids:
                errors.append({"row": row_num, "error": f"patient_id {patient_id} not in tenant"})
                continue
            if payer_id is not None and payer_id not in valid_payer_ids:
                errors.append({"row": row_num, "error": f"payer_id {payer_id} not in tenant"})
                continue

            short_id = _uuid.uuid4().hex[:8].upper()
            claim_number = f"CLM-{datetime.now().strftime('%Y%m%d')}-{short_id}"
            new_claim = Claim(
                tenant_id=current_user.tenant_id,
                claim_number=claim_number,
                patient_id=patient_id,
                provider_id=int(row.get("provider_id", 0)) if row.get("provider_id") else None,
                payer_id=payer_id,
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
                db.add(ClaimLine(
                    claim_id=new_claim.id,
                    line_number=1,
                    cpt_code=row["cpt_code"],
                    units=int(row.get("units", 1)),
                    charge_amount=float(row.get("charge_amount", row.get("total_charges", 0))),
                ))

            if row.get("icd10_code"):
                db.add(ClaimDiagnosis(
                    claim_id=new_claim.id,
                    diagnosis_pointer=1,
                    icd10_code=row["icd10_code"],
                    is_primary=True,
                ))

            # Per-row commit. If a row fails on flush/commit, rollback ONLY
            # this row's transaction so subsequent rows aren't poisoned by a
            # PendingRollbackError cascade (closes v9-M5).
            await db.commit()
            created_claims.append(claim_number)
        except Exception as e:
            await db.rollback()
            errors.append({"row": row_num, "error": str(e)})

    # Audit log on a fresh transaction so it isn't affected by per-row state.
    await log_audit_event(
        db, current_user, action="claims_csv_imported", resource_type="claim",
        resource_id="batch", request=request,
        metadata={"created": len(created_claims), "errors": len(errors)},
    )
    await db.commit()

    return {
        "success": True,
        "message": f"Imported {len(created_claims)} claims",
        "data": {"claims_created": len(created_claims), "errors": errors},
    }


@router.delete("/{claim_id}")
async def delete_claim(
    claim_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Delete a claim. Admin role; only draft/rejected/void claims allowed."""
    current_user.require_role("admin")
    result = await db.execute(
        select(Claim).where(and_(Claim.id == claim_id, Claim.tenant_id == current_user.tenant_id))
    )
    claim = result.scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.state not in ("draft", "rejected", "void"):
        raise HTTPException(status_code=400, detail=f"Cannot delete claim in '{claim.state}' state. Void it first.")
    claim_number = claim.claim_number
    await db.delete(claim)
    await log_audit_event(
        db, current_user, action="claim_deleted", resource_type="claim",
        resource_id=str(claim_id), request=request,
        metadata={"claim_number": claim_number, "previous_state": claim.state},
    )
    await db.commit()
    return {"success": True, "message": "Claim deleted"}


@router.post("/batch/delete")
async def batch_delete_claims(
    body: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Delete multiple claims. Admin role; only draft/rejected/void allowed."""
    current_user.require_role("admin")
    claim_ids = body.get("claim_ids", [])
    if not claim_ids:
        raise HTTPException(status_code=422, detail="claim_ids required")

    deleted = 0
    deleted_ids: List[int] = []
    errors: List[str] = []
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
            deleted_ids.append(cid)
            deleted += 1

    await log_audit_event(
        db, current_user, action="claims_batch_deleted", resource_type="claim",
        resource_id="batch", request=request,
        metadata={"deleted": deleted, "deleted_ids": deleted_ids, "errors": len(errors)},
    )
    await db.commit()
    return {"success": True, "data": {"deleted": deleted, "errors": errors}}


@router.post("/{claim_id}/void")
async def void_claim(
    claim_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Void a claim (soft-delete, keeps record for audit). Billing role."""
    current_user.require_role("billing")
    result = await db.execute(
        select(Claim).where(and_(Claim.id == claim_id, Claim.tenant_id == current_user.tenant_id))
    )
    claim = result.scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    previous_state = claim.state
    claim.previous_state = previous_state
    claim.state = "void"
    db.add(ClaimEvent(
        claim_id=claim.id,
        event_type="voided",
        from_state=previous_state,
        to_state="void",
        message=f"Claim voided by {current_user.email}",
    ))
    await log_audit_event(
        db, current_user, action="claim_voided", resource_type="claim",
        resource_id=str(claim_id), request=request,
        metadata={"previous_state": previous_state},
    )
    await db.commit()
    return {"success": True, "message": "Claim voided"}
