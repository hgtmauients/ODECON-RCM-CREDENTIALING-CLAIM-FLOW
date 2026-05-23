"""
Payer Enrollment API
Manages provider enrollment with specific payers.

Access control: list/get require billing or credentialing; mutations require
credentialing (which expands via the role hierarchy to admin / super_admin).
All mutations are audit-logged.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
import logging
import os
import base64

from pydantic import BaseModel, Field, ConfigDict

from core.database import get_db
from core.audit import log_audit_event
from core.storage import safe_filename, build_relative_path, StoragePathError
from models.payer_credentialing import PayerCredentialingCase, ERAEnrollmentCase, ProviderDocument
from models.credentialing import ProviderCredentialing
from models.rcm import PayerProfile
from api.auth import get_current_user, Principal
from services.encryption import encrypt_credential

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rcm/payer-enrollment", tags=["RCM - Payer Enrollment"])

# Allowed PayerCredentialingCase status values.
_VALID_CASE_STATUSES = frozenset({
    "draft", "in_progress", "ready_to_submit", "submitted",
    "in_review", "approved", "rejected", "renewal_due",
})
_VALID_CASE_TRANSITIONS = {
    "draft": {"in_progress", "rejected"},
    "in_progress": {"ready_to_submit", "submitted", "rejected"},
    "ready_to_submit": {"submitted", "rejected"},
    "submitted": {"in_review", "approved", "rejected", "renewal_due"},
    "in_review": {"approved", "rejected", "renewal_due"},
    "approved": {"renewal_due"},
    "rejected": {"in_progress"},
    "renewal_due": {"in_progress", "submitted"},
}


class EnrollmentCaseUpdate(BaseModel):
    """Whitelisted updatable fields with proper validation."""
    model_config = ConfigDict(extra="ignore")

    notes: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Optional[str] = None  # validated against enum below
    payer_rep_name: Optional[str] = None
    payer_rep_email: Optional[str] = None
    payer_rep_phone: Optional[str] = None
    ticket_number: Optional[str] = None
    submitted_date: Optional[date] = None
    effective_date: Optional[date] = None
    expiration_date: Optional[date] = None


async def _verify_provider_in_tenant(provider_id: str, tenant_id: str, db: AsyncSession) -> None:
    """404 if provider_id does not belong to the current user\'s tenant."""
    check = await db.execute(
        select(ProviderCredentialing.id).where(and_(
            ProviderCredentialing.provider_id == provider_id,
            ProviderCredentialing.tenant_id == tenant_id,
        ))
    )
    if not check.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Provider not found")


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
    """List payer credentialing cases - scoped to tenant. Returns full filtered total."""
    current_user.require_role("credentialing")
    try:
        from sqlalchemy import func as sa_func

        filters = [PayerCredentialingCase.tenant_id == current_user.tenant_id]
        if provider_id:
            filters.append(PayerCredentialingCase.provider_id == provider_id)
        if payer_id:
            filters.append(PayerCredentialingCase.payer_id == payer_id)
        if status:
            filters.append(PayerCredentialingCase.status == status)
        if expiring_soon:
            ninety_days_out = date.today() + timedelta(days=90)
            filters.extend([
                PayerCredentialingCase.expiration_date.isnot(None),
                PayerCredentialingCase.expiration_date <= ninety_days_out,
            ])

        data_query = (
            select(PayerCredentialingCase)
            .where(and_(*filters))
            .order_by(desc(PayerCredentialingCase.created_at))
            .limit(limit)
            .offset(offset)
        )
        count_query = select(sa_func.count(PayerCredentialingCase.id)).where(and_(*filters))

        result = await db.execute(data_query)
        cases = result.scalars().all()

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

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

        return {
            "success": True,
            "data": cases_with_payer_names,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception:
        logger.exception("Error listing payer credentialing cases")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/cases/{case_id}")
async def get_payer_credentialing_case(
    case_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Get single payer credentialing case detail - scoped to tenant."""
    current_user.require_role("credentialing")
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


@router.put("/cases/{case_id}")
async def update_payer_credentialing_case(
    case_id: int,
    updates: EnrollmentCaseUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Update editable case fields. Tenant-scoped; mutation audited.

    Status is validated against an allowed enum; date fields are parsed by
    Pydantic. (Closes v9-M1 + v9-M2.)
    """
    current_user.require_role("credentialing")
    try:
        result = await db.execute(
            select(PayerCredentialingCase)
            .where(and_(
                PayerCredentialingCase.id == case_id,
                PayerCredentialingCase.tenant_id == current_user.tenant_id,
            ))
            .with_for_update()
        )
        case = result.scalar_one_or_none()
        if not case:
            raise HTTPException(status_code=404, detail="Enrollment case not found")

        applied = updates.model_dump(exclude_unset=True)
        if "status" in applied and applied["status"] not in _VALID_CASE_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"status must be one of {sorted(_VALID_CASE_STATUSES)}",
            )
        if "status" in applied:
            next_status = applied["status"]
            current_status = case.status
            if next_status != current_status and next_status not in _VALID_CASE_TRANSITIONS.get(current_status, set()):
                raise HTTPException(
                    status_code=409,
                    detail=f"Invalid enrollment status transition: {current_status} -> {next_status}",
                )

        for key, value in applied.items():
            if hasattr(case, key):
                setattr(case, key, value)

        await log_audit_event(
            db, current_user, action="enrollment_case_updated",
            resource_type="enrollment_case", resource_id=str(case_id),
            request=request, changes={"updated_fields": sorted(applied.keys())},
        )
        await db.commit()
        return {"success": True, "message": "Case updated"}
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Error updating enrollment case %s", case_id)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/cases/auto-create")
async def auto_create_payer_cases(
    provider_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Auto-create payer credentialing cases for all active payers - scoped to tenant"""
    current_user.require_role("credentialing")
    await _verify_provider_in_tenant(provider_id, current_user.tenant_id, db)
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

        await log_audit_event(
            db, current_user, action="enrollment_cases_auto_created",
            resource_type="provider", resource_id=provider_id,
            request=request, metadata={"cases_created": cases_created},
        )
        await db.commit()
        logger.info(f"Auto-created {cases_created} payer credentialing cases for provider {provider_id}")
        return {"success": True, "message": f"Created {cases_created} payer credentialing cases", "data": {"cases_created": cases_created}}
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Error auto-creating payer cases")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/cases/{case_id}/checklist")
async def update_case_checklist(
    case_id: int,
    checklist_updates: List[Dict[str, Any]],
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Update checklist items for credentialing case - scoped to tenant"""
    current_user.require_role("credentialing")
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
        if case.completion_percentage == 100 and case.status in {"draft", "in_progress"}:
            case.status = "ready_to_submit"
        case.updated_by = current_user.email

        await log_audit_event(
            db, current_user, action="enrollment_checklist_updated",
            resource_type="enrollment_case", resource_id=str(case_id),
            request=request,
            metadata={"completed_items": completed, "completion_percentage": case.completion_percentage},
        )
        await db.commit()

        return {"success": True, "message": "Checklist updated", "data": {"completion_percentage": case.completion_percentage, "status": case.status}}
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Error updating checklist")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/era-enrollment")
async def list_era_enrollments(
    provider_id: Optional[str] = None,
    payer_id: Optional[int] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List ERA/EFT enrollment cases - scoped to tenant"""
    current_user.require_role("credentialing")
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/era-enrollment")
async def create_era_enrollment(
    enrollment_data: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Create ERA/EFT enrollment case - scoped to tenant. Writes encrypted bank info."""
    current_user.require_role("credentialing")
    try:
        # Encrypt sensitive bank account fields before storage.
        if 'routing_number' in enrollment_data:
            enrollment_data['routing_number_encrypted'] = await encrypt_credential(enrollment_data.pop('routing_number'))
        if 'account_number' in enrollment_data:
            enrollment_data['account_number_encrypted'] = await encrypt_credential(enrollment_data.pop('account_number'))

        provider_id = enrollment_data.get("provider_id")
        if provider_id:
            await _verify_provider_in_tenant(provider_id, current_user.tenant_id, db)

        clean = {k: v for k, v in enrollment_data.items() if k not in {"id", "tenant_id", "created_at", "created_by", "status"}}
        new_enrollment = ERAEnrollmentCase(
            tenant_id=current_user.tenant_id,
            **clean,
            status="pending",
            created_by=current_user.email,
        )
        db.add(new_enrollment)
        await db.flush()

        await log_audit_event(
            db, current_user, action="era_enrollment_created",
            resource_type="era_enrollment", resource_id=str(new_enrollment.id),
            request=request,
            metadata={"payer_id": enrollment_data.get("payer_id"), "provider_id": provider_id,
                       "bank_credentials_provided": "routing_number_encrypted" in enrollment_data},
        )
        await db.commit()
        await db.refresh(new_enrollment)
        return {"success": True, "message": "ERA enrollment case created", "data": {"id": new_enrollment.id}}
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Error creating ERA enrollment")
        raise HTTPException(status_code=500, detail="Internal server error")


MAX_DOC_UPLOAD_BYTES = int(os.getenv("MAX_DOC_UPLOAD_BYTES", str(20 * 1024 * 1024)))  # 20 MB
ALLOWED_DOC_MIME_PREFIXES = ("application/pdf", "image/", "application/vnd.openxmlformats", "application/msword")
# Whitelist of supported document type slugs. Restrictive on purpose so the
# value is safe to embed in a storage path.
_VALID_DOCUMENT_TYPES = frozenset({
    "license", "dea", "cned", "malpractice_insurance", "w9", "caqh", "npi",
    "board_certification", "diploma", "cv", "passport", "drivers_license",
    "specialty_certification", "other",
})


@router.post("/documents/upload")
async def upload_provider_document(
    provider_id: str,
    document_type: str,
    request: Request,
    file: UploadFile = File(...),
    expiration_date: Optional[date] = None,
    state_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Upload a provider credentialing document.

    Hardening:
      - require credentialing role (mutates a credentialing artifact)
      - verify provider_id ∈ tenant (closes v9-H2)
      - validate document_type against an allowlist (closes path-traversal vector)
      - sanitize filename via core.storage.safe_filename
      - storage layer rejects any "../" or absolute components (closes NEW-C2)
      - audit-log the upload
    """
    current_user.require_role("credentialing")
    await _verify_provider_in_tenant(provider_id, current_user.tenant_id, db)

    if document_type not in _VALID_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"document_type must be one of {sorted(_VALID_DOCUMENT_TYPES)}",
        )

    content = await file.read(MAX_DOC_UPLOAD_BYTES + 1)
    if len(content) > MAX_DOC_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Document exceeds maximum size of {MAX_DOC_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    mime_type = file.content_type or "application/octet-stream"
    if not any(mime_type.startswith(p) for p in ALLOWED_DOC_MIME_PREFIXES):
        raise HTTPException(status_code=400, detail=f"Unsupported document mime type: {mime_type}")

    from core.storage import storage
    safe_name = safe_filename(file.filename, fallback=f"{document_type}.bin")
    timestamp_segment = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        relative_path = build_relative_path(
            "providers", provider_id, f"{document_type}_{timestamp_segment}_{safe_name}",
        )
    except StoragePathError:
        # provider_id failed sanitization (e.g. contained "/" or "..").
        # _verify_provider_in_tenant should have already rejected it, but we
        # still treat this as a 400 — never a 500 — to avoid revealing
        # internal validation state.
        raise HTTPException(status_code=400, detail="Invalid provider_id")

    try:
        # Encrypt provider docs at rest before writing to tenant storage.
        encoded = base64.b64encode(content).decode("ascii")
        encrypted_blob = await encrypt_credential(encoded)
        encrypted_bytes = encrypted_blob.encode("utf-8")
        stored_path = await storage.write(relative_path, encrypted_bytes, tenant_id=str(current_user.tenant_id))
    except StoragePathError:
        raise HTTPException(status_code=400, detail="Invalid storage path")
    except Exception:
        logger.exception("Failed to persist provider document")
        raise HTTPException(status_code=500, detail="Failed to persist document")

    try:
        new_doc = ProviderDocument(
            tenant_id=current_user.tenant_id,
            provider_id=provider_id,
            document_type=document_type,
            document_name=file.filename or f"{document_type}_document",
            file_path=stored_path,
            file_size=len(content),
            mime_type=mime_type,
            original_filename=file.filename,
            expiration_date=expiration_date,
            state_code=state_code,
            uploaded_by=current_user.email,
            is_encrypted=True,
            encryption_key_id="app-default",
        )
        db.add(new_doc)
        await db.flush()
        await log_audit_event(
            db, current_user, action="provider_document_uploaded",
            resource_type="provider_document", resource_id=str(new_doc.id),
            request=request,
            metadata={
                "provider_id": provider_id, "document_type": document_type,
                "file_size": new_doc.file_size, "mime_type": mime_type,
            },
        )
        await db.commit()
        await db.refresh(new_doc)

        return {
            "success": True,
            "message": "Document uploaded successfully",
            "data": {
                "id": new_doc.id,
                "document_type": document_type,
                "file_size": new_doc.file_size,
                "mime_type": new_doc.mime_type,
            },
        }
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Error creating ProviderDocument row after storage write")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/documents")
async def list_provider_documents(
    provider_id: str,
    document_type: Optional[str] = None,
    expiring_soon: Optional[bool] = False,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List provider documents - scoped to tenant + verified provider membership."""
    current_user.require_role("credentialing")
    await _verify_provider_in_tenant(provider_id, current_user.tenant_id, db)
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
        raise HTTPException(status_code=500, detail="Internal server error")
