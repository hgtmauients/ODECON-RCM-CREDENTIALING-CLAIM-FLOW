"""
Payer Enrollment API
Manages provider enrollment with specific payers
"""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
import logging

from core.database import get_db
from models.payer_credentialing import PayerCredentialingCase, ERAEnrollmentCase, ProviderDocument, CredentialingRenewal
from models.credentialing import ProviderCredentialing
from models.rcm import PayerProfile
from api.auth import get_current_user, Principal
from services.encryption import encrypt_credential, decrypt_credential

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rcm/payer-enrollment", tags=["RCM - Payer Enrollment"])


@router.get("/cases")
async def list_payer_credentialing_cases(
    provider_id: Optional[str] = None,
    payer_id: Optional[int] = None,
    status: Optional[str] = None,
    expiring_soon: Optional[bool] = False,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List payer credentialing cases - scoped to tenant"""
    try:
        query = select(PayerCredentialingCase).where(
            PayerCredentialingCase.tenant_id == current_user.tenant_id
        )

        if provider_id:
            query = query.where(PayerCredentialingCase.provider_id == provider_id)
        if payer_id:
            query = query.where(PayerCredentialingCase.payer_id == payer_id)
        if status:
            query = query.where(PayerCredentialingCase.status == status)
        if expiring_soon:
            ninety_days_out = date.today() + timedelta(days=90)
            query = query.where(and_(
                PayerCredentialingCase.expiration_date.isnot(None),
                PayerCredentialingCase.expiration_date <= ninety_days_out,
            ))

        query = query.order_by(desc(PayerCredentialingCase.created_at)).limit(limit).offset(offset)
        result = await db.execute(query)
        cases = result.scalars().all()

        cases_with_payer_names = []
        for case in cases:
            payer_result = await db.execute(
                select(PayerProfile).where(and_(
                    PayerProfile.id == case.payer_id,
                    PayerProfile.tenant_id == current_user.tenant_id,
                ))
            )
            payer = payer_result.scalar_one_or_none()

            provider_result = await db.execute(
                select(ProviderCredentialing).where(and_(
                    ProviderCredentialing.provider_id == case.provider_id,
                    ProviderCredentialing.tenant_id == current_user.tenant_id,
                ))
            )
            provider_cred = provider_result.scalar_one_or_none()

            provider_name = "Unknown"
            if provider_cred and provider_cred.signup_data:
                signup = provider_cred.signup_data
                provider_name = f"{signup.get('first_name', '')} {signup.get('last_name', '')}".strip()

            cases_with_payer_names.append({
                "id": case.id,
                "provider_id": case.provider_id,
                "provider_name": provider_name,
                "payer_id": case.payer_id,
                "payer_name": payer.name if payer else "Unknown",
                "status": case.status,
                "submitted_date": case.submitted_date.isoformat() if case.submitted_date else None,
                "effective_date": case.effective_date.isoformat() if case.effective_date else None,
                "expiration_date": case.expiration_date.isoformat() if case.expiration_date else None,
                "completion_percentage": case.completion_percentage,
                "assigned_to": case.assigned_to,
                "created_at": case.created_at.isoformat() if case.created_at else None,
            })

        return {"success": True, "data": cases_with_payer_names, "total": len(cases)}
    except Exception as e:
        logger.error(f"Error listing payer credentialing cases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cases/{case_id}")
async def get_payer_credentialing_case(
    case_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Get single payer credentialing case detail - scoped to tenant."""
    result = await db.execute(
        select(PayerCredentialingCase).where(and_(
            PayerCredentialingCase.id == case_id,
            PayerCredentialingCase.tenant_id == current_user.tenant_id,
        ))
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Enrollment case not found")

    payer_result = await db.execute(
        select(PayerProfile).where(and_(
            PayerProfile.id == case.payer_id,
            PayerProfile.tenant_id == current_user.tenant_id,
        ))
    )
    payer = payer_result.scalar_one_or_none()

    provider_result = await db.execute(
        select(ProviderCredentialing).where(and_(
            ProviderCredentialing.provider_id == case.provider_id,
            ProviderCredentialing.tenant_id == current_user.tenant_id,
        ))
    )
    provider_cred = provider_result.scalar_one_or_none()
    provider_name = "Unknown"
    if provider_cred and provider_cred.signup_data:
        signup = provider_cred.signup_data
        provider_name = f"{signup.get('first_name', '')} {signup.get('last_name', '')}".strip()

    return {
        "success": True,
        "data": {
            "id": case.id,
            "provider_id": case.provider_id,
            "provider_name": provider_name,
            "payer_id": case.payer_id,
            "payer_name": payer.name if payer else "Unknown",
            "status": case.status,
            "submitted_date": case.submitted_date.isoformat() if case.submitted_date else None,
            "effective_date": case.effective_date.isoformat() if case.effective_date else None,
            "expiration_date": case.expiration_date.isoformat() if case.expiration_date else None,
            "completion_percentage": case.completion_percentage,
            "assigned_to": case.assigned_to,
            "checklist": case.checklist or [],
            "payer_rep_name": case.payer_rep_name,
            "payer_rep_email": case.payer_rep_email,
            "payer_rep_phone": case.payer_rep_phone,
            "ticket_number": case.ticket_number,
            "notes": case.notes,
            "created_at": case.created_at.isoformat() if case.created_at else None,
        },
    }


@router.post("/cases/auto-create")
async def auto_create_payer_cases(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Auto-create payer credentialing cases for all active payers - scoped to tenant"""
    try:
        payers_result = await db.execute(
            select(PayerProfile).where(and_(
                PayerProfile.is_active == True,
                PayerProfile.is_draft == False,
                PayerProfile.tenant_id == current_user.tenant_id,
            ))
        )
        payers = payers_result.scalars().all()
        cases_created = 0

        for payer in payers:
            existing_result = await db.execute(
                select(PayerCredentialingCase).where(and_(
                    PayerCredentialingCase.provider_id == provider_id,
                    PayerCredentialingCase.payer_id == payer.id,
                    PayerCredentialingCase.tenant_id == current_user.tenant_id,
                ))
            )
            existing = existing_result.scalar_one_or_none()

            if not existing:
                default_checklist = [
                    {"item": "W-9", "required": True, "completed": False},
                    {"item": "License Copy", "required": True, "completed": False},
                    {"item": "Malpractice Insurance", "required": True, "completed": False},
                    {"item": "CAQH Profile", "required": True, "completed": False},
                    {"item": "NPI Verification", "required": True, "completed": False},
                ]

                new_case = PayerCredentialingCase(
                    tenant_id=current_user.tenant_id,
                    provider_id=provider_id,
                    payer_id=payer.id,
                    status="draft",
                    checklist=default_checklist,
                    total_items=len(default_checklist),
                    completed_items=0,
                    completion_percentage=0,
                    created_by=current_user.email,
                )
                db.add(new_case)
                cases_created += 1

        await db.commit()
        logger.info(f"Auto-created {cases_created} payer credentialing cases for provider {provider_id}")
        return {"success": True, "message": f"Created {cases_created} payer credentialing cases", "data": {"cases_created": cases_created}}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error auto-creating payer cases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/cases/{case_id}/checklist")
async def update_case_checklist(
    case_id: int,
    checklist_updates: List[Dict[str, Any]],
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Update checklist items for credentialing case - scoped to tenant"""
    try:
        result = await db.execute(
            select(PayerCredentialingCase).where(and_(
                PayerCredentialingCase.id == case_id,
                PayerCredentialingCase.tenant_id == current_user.tenant_id,
            ))
        )
        case = result.scalar_one_or_none()
        if not case:
            raise HTTPException(status_code=404, detail="Credentialing case not found")

        case.checklist = checklist_updates
        completed = sum(1 for item in checklist_updates if item.get('completed'))
        case.completed_items = completed
        case.completion_percentage = int((completed / len(checklist_updates)) * 100) if checklist_updates else 0
        if case.completion_percentage == 100:
            case.status = "ready_to_submit"
        case.updated_by = current_user.email
        await db.commit()

        return {"success": True, "message": "Checklist updated", "data": {"completion_percentage": case.completion_percentage, "status": case.status}}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating checklist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/era-enrollment")
async def list_era_enrollments(
    provider_id: Optional[str] = None,
    payer_id: Optional[int] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List ERA/EFT enrollment cases - scoped to tenant"""
    try:
        query = select(ERAEnrollmentCase).where(ERAEnrollmentCase.tenant_id == current_user.tenant_id)
        if provider_id:
            query = query.where(ERAEnrollmentCase.provider_id == provider_id)
        if payer_id:
            query = query.where(ERAEnrollmentCase.payer_id == payer_id)
        if status:
            query = query.where(ERAEnrollmentCase.status == status)

        result = await db.execute(query)
        enrollments = result.scalars().all()

        return {
            "success": True,
            "data": [{
                "id": e.id,
                "provider_id": e.provider_id,
                "payer_id": e.payer_id,
                "clearinghouse": e.clearinghouse,
                "status": e.status,
                "effective_date": e.effective_date.isoformat() if e.effective_date else None,
                "test_835_received": e.test_835_received,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            } for e in enrollments],
        }
    except Exception as e:
        logger.error(f"Error listing ERA enrollments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/era-enrollment")
async def create_era_enrollment(
    enrollment_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Create ERA/EFT enrollment case - scoped to tenant"""
    try:
        if 'routing_number' in enrollment_data:
            enrollment_data['routing_number_encrypted'] = await encrypt_credential(enrollment_data.pop('routing_number'))
        if 'account_number' in enrollment_data:
            enrollment_data['account_number_encrypted'] = await encrypt_credential(enrollment_data.pop('account_number'))

        new_enrollment = ERAEnrollmentCase(
            tenant_id=current_user.tenant_id,
            **enrollment_data,
            status="pending",
            created_by=current_user.email,
        )
        db.add(new_enrollment)
        await db.commit()
        await db.refresh(new_enrollment)

        return {"success": True, "message": "ERA enrollment case created", "data": {"id": new_enrollment.id}}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating ERA enrollment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/upload")
async def upload_provider_document(
    provider_id: str,
    document_type: str,
    file: UploadFile = File(...),
    expiration_date: Optional[date] = None,
    state_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Upload provider document to secure vault - scoped to tenant"""
    try:
        file_path = f"/secure_storage/{current_user.tenant_id}/providers/{provider_id}/{document_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        new_doc = ProviderDocument(
            tenant_id=current_user.tenant_id,
            provider_id=provider_id,
            document_type=document_type,
            document_name=file.filename or f"{document_type}_document",
            file_path=file_path,
            file_size=0,
            mime_type=file.content_type,
            original_filename=file.filename,
            expiration_date=expiration_date,
            state_code=state_code,
            uploaded_by=current_user.email,
            is_encrypted=True,
        )
        db.add(new_doc)
        await db.commit()
        await db.refresh(new_doc)

        return {"success": True, "message": "Document uploaded successfully", "data": {"id": new_doc.id, "document_type": document_type}}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error uploading document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents")
async def list_provider_documents(
    provider_id: str,
    document_type: Optional[str] = None,
    expiring_soon: Optional[bool] = False,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List provider documents - scoped to tenant"""
    try:
        query = select(ProviderDocument).where(and_(
            ProviderDocument.provider_id == provider_id,
            ProviderDocument.is_latest_version == True,
            ProviderDocument.tenant_id == current_user.tenant_id,
        ))

        if document_type:
            query = query.where(ProviderDocument.document_type == document_type)
        if expiring_soon:
            ninety_days_out = date.today() + timedelta(days=90)
            query = query.where(and_(
                ProviderDocument.expiration_date.isnot(None),
                ProviderDocument.expiration_date <= ninety_days_out,
            ))

        query = query.order_by(ProviderDocument.uploaded_at)
        result = await db.execute(query)
        documents = result.scalars().all()

        return {
            "success": True,
            "data": [{
                "id": d.id,
                "document_type": d.document_type,
                "document_name": d.document_name,
                "expiration_date": d.expiration_date.isoformat() if d.expiration_date else None,
                "days_until_expiration": d.days_until_expiration,
                "is_verified": d.is_verified,
                "version": d.version,
                "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            } for d in documents],
        }
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))
