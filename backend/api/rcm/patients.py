"""
ClaimFlow - Patient/Subscriber API.
CRUD for patient demographics used in claim generation.

Access control: every endpoint requires the "billing" role (which expands
to admin and super_admin via the role hierarchy). PHI access (reads + writes)
is audit-logged via core.audit.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from typing import Optional
from pydantic import BaseModel, Field
from datetime import date
import logging

from core.database import get_db
from core.audit import log_audit_event
from core.csv_export import csv_response
from datetime import datetime
from api.auth import get_current_user, Principal
from models.patient import Patient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rcm/patients", tags=["RCM - Patients"])


class PatientCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    middle_name: Optional[str] = None
    suffix: Optional[str] = None
    date_of_birth: date
    gender: str = Field(..., pattern="^[MFU]$")
    address_line_1: str = Field(..., min_length=1)
    address_line_2: Optional[str] = None
    city: str = Field(..., min_length=1)
    state: str = Field(..., min_length=2, max_length=2)
    zip_code: str = Field(..., min_length=5, max_length=10)
    phone: Optional[str] = None
    email: Optional[str] = None
    member_id: str = Field(..., min_length=1, max_length=80)
    group_number: Optional[str] = None
    payer_id: Optional[int] = None
    relationship_to_subscriber: str = "18"


class PatientUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    member_id: Optional[str] = None
    group_number: Optional[str] = None
    payer_id: Optional[int] = None


@router.get("")
async def list_patients(
    request: Request,
    search: Optional[str] = None,
    payer_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List patients - scoped to tenant. Requires billing role."""
    current_user.require_role("billing")

    from sqlalchemy import func as sa_func
    filters = [Patient.tenant_id == current_user.tenant_id]
    if search:
        term = f"%{search}%"
        filters.append(or_(
            Patient.last_name.ilike(term),
            Patient.first_name.ilike(term),
            Patient.member_id.ilike(term),
        ))
    if payer_id:
        filters.append(Patient.payer_id == payer_id)

    data_query = (
        select(Patient).where(and_(*filters))
        .order_by(Patient.last_name, Patient.first_name).limit(limit).offset(offset)
    )
    count_query = select(sa_func.count(Patient.id)).where(and_(*filters))

    result = await db.execute(data_query)
    patients = result.scalars().all()
    total = (await db.execute(count_query)).scalar() or 0

    # PHI list access is audited at the LIST granularity (count + filter
    # context) rather than per-row to avoid log explosion.
    await log_audit_event(
        db, current_user, action="patient_list", resource_type="patient",
        resource_id="*", request=request,
        metadata={"count": len(patients), "filter_search": bool(search), "filter_payer": payer_id},
    )
    await db.commit()

    return {
        "success": True,
        "data": [{
            "id": p.id,
            "first_name": p.first_name,
            "last_name": p.last_name,
            "date_of_birth": p.date_of_birth.isoformat() if p.date_of_birth else None,
            "gender": p.gender,
            "member_id": p.member_id,
            "payer_id": p.payer_id,
            "city": p.city,
            "state": p.state,
        } for p in patients],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/export.csv")
async def export_patients_csv(
    request: Request,
    search: Optional[str] = None,
    payer_id: Optional[int] = None,
    limit: int = Query(10000, ge=1, le=50000),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Stream filtered patients as CSV. PHI export — billing role + audited."""
    current_user.require_role("billing")
    filters = [Patient.tenant_id == current_user.tenant_id]
    if search:
        term = f"%{search}%"
        filters.append(or_(
            Patient.last_name.ilike(term),
            Patient.first_name.ilike(term),
            Patient.member_id.ilike(term),
        ))
    if payer_id:
        filters.append(Patient.payer_id == payer_id)

    rows = (await db.execute(
        select(Patient).where(and_(*filters))
        .order_by(Patient.last_name, Patient.first_name).limit(limit)
    )).scalars().all()

    await log_audit_event(
        db, current_user, action="patients_csv_exported", resource_type="patient",
        resource_id="batch", request=request,
        metadata={"row_count": len(rows), "filter_search": bool(search)},
    )
    await db.commit()

    fieldnames = [
        "id", "first_name", "last_name", "middle_name", "suffix",
        "date_of_birth", "gender",
        "address_line_1", "address_line_2", "city", "state", "zip_code",
        "phone", "email",
        "member_id", "group_number", "payer_id", "relationship_to_subscriber",
    ]
    return csv_response(
        filename=f"patients_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        rows=rows,
        fieldnames=fieldnames,
        row_to_dict=lambda p: {
            "id": p.id,
            "first_name": p.first_name,
            "last_name": p.last_name,
            "middle_name": p.middle_name,
            "suffix": p.suffix,
            "date_of_birth": p.date_of_birth,
            "gender": p.gender,
            "address_line_1": p.address_line_1,
            "address_line_2": p.address_line_2,
            "city": p.city,
            "state": p.state,
            "zip_code": p.zip_code,
            "phone": p.phone,
            "email": p.email,
            "member_id": p.member_id,
            "group_number": p.group_number,
            "payer_id": p.payer_id,
            "relationship_to_subscriber": p.relationship_to_subscriber,
        },
    )


@router.get("/{patient_id}")
async def get_patient(
    patient_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Get patient detail. Requires billing role; PHI read is audited."""
    current_user.require_role("billing")

    result = await db.execute(
        select(Patient).where(and_(Patient.id == patient_id, Patient.tenant_id == current_user.tenant_id))
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    await log_audit_event(
        db, current_user, action="patient_viewed", resource_type="patient",
        resource_id=str(patient_id), request=request,
    )
    await db.commit()

    return {
        "success": True,
        "data": {
            "id": patient.id,
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "middle_name": patient.middle_name,
            "suffix": patient.suffix,
            "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
            "gender": patient.gender,
            "address_line_1": patient.address_line_1,
            "address_line_2": patient.address_line_2,
            "city": patient.city,
            "state": patient.state,
            "zip_code": patient.zip_code,
            "phone": patient.phone,
            "email": patient.email,
            "member_id": patient.member_id,
            "group_number": patient.group_number,
            "payer_id": patient.payer_id,
            "relationship_to_subscriber": patient.relationship_to_subscriber,
        },
    }


@router.post("")
async def create_patient(
    data: PatientCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Create a new patient. Requires billing role; mutation audited."""
    current_user.require_role("billing")

    patient = Patient(tenant_id=current_user.tenant_id, **data.model_dump())
    db.add(patient)
    await db.flush()
    await log_audit_event(
        db, current_user, action="patient_created", resource_type="patient",
        resource_id=str(patient.id), request=request,
        metadata={"member_id": patient.member_id},
    )
    await db.commit()
    await db.refresh(patient)
    return {"success": True, "data": {"id": patient.id}}


@router.put("/{patient_id}")
async def update_patient(
    patient_id: int,
    data: PatientUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Update patient demographics. Requires billing role; mutation audited."""
    current_user.require_role("billing")

    result = await db.execute(
        select(Patient).where(and_(Patient.id == patient_id, Patient.tenant_id == current_user.tenant_id))
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(patient, key, value)

    await log_audit_event(
        db, current_user, action="patient_updated", resource_type="patient",
        resource_id=str(patient_id), request=request,
        changes={"updated_fields": sorted(updates.keys())},
    )
    await db.commit()
    return {"success": True, "message": "Patient updated"}
