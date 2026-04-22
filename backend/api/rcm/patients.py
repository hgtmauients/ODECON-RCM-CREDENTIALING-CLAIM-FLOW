"""
ClaimFlow - Patient/Subscriber API.
CRUD for patient demographics used in claim generation.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc
from typing import Optional
from pydantic import BaseModel, Field
from datetime import date
import logging

from core.database import get_db
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
    search: Optional[str] = None,
    payer_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List patients - scoped to tenant."""
    query = select(Patient).where(Patient.tenant_id == current_user.tenant_id)

    if search:
        term = f"%{search}%"
        query = query.where(or_(
            Patient.last_name.ilike(term),
            Patient.first_name.ilike(term),
            Patient.member_id.ilike(term),
        ))
    if payer_id:
        query = query.where(Patient.payer_id == payer_id)

    query = query.order_by(Patient.last_name, Patient.first_name).limit(limit).offset(offset)
    result = await db.execute(query)
    patients = result.scalars().all()

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
    }


@router.get("/{patient_id}")
async def get_patient(
    patient_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Get patient detail."""
    result = await db.execute(
        select(Patient).where(and_(Patient.id == patient_id, Patient.tenant_id == current_user.tenant_id))
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

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
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Create a new patient."""
    patient = Patient(tenant_id=current_user.tenant_id, **data.model_dump())
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    return {"success": True, "data": {"id": patient.id}}


@router.put("/{patient_id}")
async def update_patient(
    patient_id: int,
    data: PatientUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Update patient demographics."""
    result = await db.execute(
        select(Patient).where(and_(Patient.id == patient_id, Patient.tenant_id == current_user.tenant_id))
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(patient, key, value)

    await db.commit()
    return {"success": True, "message": "Patient updated"}
