"""
EDI File Management API
Upload, list, and manage EDI files (837, 277, 835).

Access control: list/get/download require billing; upload requires billing
(uploads can drive claim state machine and so are mutations).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from typing import Any, Dict, Optional
from datetime import datetime
import os
import logging

from core.database import get_db
from core.audit import log_audit_event
from core.storage import safe_filename, sanitize_component, StoragePathError
from api.auth import get_current_user, Principal
from models.claims import EDIFile
from services.edi_processor import EDIProcessor, EDI_STORAGE_PATH
from services.denial_manager import DenialManager, AutoPostingEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rcm/edi", tags=["RCM - EDI Files"])


@router.get("/files")
async def list_edi_files(
    file_type: Optional[str] = None,
    direction: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List EDI files - scoped to tenant"""
    current_user.require_role("billing")
    query = select(EDIFile).where(EDIFile.tenant_id == current_user.tenant_id)

    if file_type:
        query = query.where(EDIFile.file_type == file_type)
    if direction:
        query = query.where(EDIFile.direction == direction)
    if status:
        query = query.where(EDIFile.status == status)

    query = query.order_by(desc(EDIFile.created_at)).limit(limit).offset(offset)
    result = await db.execute(query)
    files = result.scalars().all()

    return {
        "success": True,
        "data": [{
            "id": f.id,
            "file_type": f.file_type,
            "direction": f.direction,
            "filename": f.filename,
            "file_size": f.file_size,
            "interchange_control_number": f.interchange_control_number,
            "transaction_count": f.transaction_count,
            "status": f.status,
            "processed_at": f.processed_at.isoformat() if f.processed_at else None,
            "error_message": f.error_message,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        } for f in files],
    }


MAX_EDI_UPLOAD_BYTES = int(os.getenv("MAX_EDI_UPLOAD_BYTES", str(10 * 1024 * 1024)))  # 10 MB default
ALLOWED_EDI_TYPES = {"835", "277CA", "277", "271", "999", "unknown"}


@router.post("/upload")
async def upload_edi_file(
    request: Request,
    file: UploadFile = File(...),
    file_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Upload an EDI file (835, 277, etc.) for processing.

    Hardening: billing role gate, size cap, ISA sniff, sanitized filename
    + tenant component, audit log on success.
    """
    current_user.require_role("billing")

    content = await file.read(MAX_EDI_UPLOAD_BYTES + 1)
    if len(content) > MAX_EDI_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"EDI file exceeds maximum size of {MAX_EDI_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if not content[:3] == b"ISA":
        raise HTTPException(
            status_code=400,
            detail="File does not look like a valid X12 EDI file (must start with ISA segment)",
        )

    if not file_type:
        if "835" in (file.filename or ""):
            file_type = "835"
        elif "277" in (file.filename or ""):
            file_type = "277CA"
        elif "271" in (file.filename or ""):
            file_type = "271"
        else:
            file_type = "unknown"

    if file_type not in ALLOWED_EDI_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file_type: {file_type}")

    # Path safety: sanitize the tenant component and filename. The tenant id
    # comes from the JWT-authenticated principal so it is already trusted, but
    # we run it through sanitize_component as defense in depth.
    try:
        tenant_segment = sanitize_component(str(current_user.tenant_id), label="tenant_id")
    except StoragePathError:
        raise HTTPException(status_code=400, detail="Invalid tenant context")
    safe_name = safe_filename(file.filename, fallback=f"{file_type}.edi")

    import asyncio
    inbound_dir = os.path.join(EDI_STORAGE_PATH, tenant_segment, "inbound")
    dest_path = os.path.join(inbound_dir, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}")

    def _write_file():
        os.makedirs(inbound_dir, exist_ok=True)
        with open(dest_path, "wb") as f_out:
            f_out.write(content)

    await asyncio.to_thread(_write_file)

    edi_file = EDIFile(
        tenant_id=current_user.tenant_id,
        file_type=file_type,
        direction="inbound",
        filename=file.filename or "upload",
        file_path=dest_path,
        file_size=len(content),
        status="processing",
        created_by=current_user.email,
    )
    db.add(edi_file)
    await db.commit()
    await db.refresh(edi_file)

    processor = EDIProcessor(db)
    parse_result: dict = {}
    try:
        if file_type == "835":
            parse_result = await processor.parse_835_with_record(dest_path, edi_file)
            tenant_id_str = str(current_user.tenant_id)
            auto_posting = {"claims_posted": 0, "total_paid": 0.0, "errors": []}
            denials = {"denials_processed": 0, "cases_created": 0, "errors": []}

            if parse_result.get("payments"):
                auto_poster = AutoPostingEngine(db)
                auto_posting = await auto_poster.auto_post_835(
                    edi_file_id=edi_file.id,
                    payments_data=parse_result["payments"],
                    tenant_id=tenant_id_str,
                )

            if parse_result.get("denials"):
                denial_manager = DenialManager(db)
                denials = await denial_manager.process_835_denials(
                    edi_file_id=edi_file.id,
                    denials_data=parse_result["denials"],
                    tenant_id=tenant_id_str,
                )

            # Keep backward-compatible summary fields while exposing downstream
            # post/denial results that were previously only run in polling jobs.
            parse_result["claims_extracted"] = parse_result.get("claims_posted", 0)
            parse_result["claims_posted"] = auto_posting.get("claims_posted", 0)
            parse_result["auto_posting"] = auto_posting
            parse_result["denial_processing"] = denials
        elif file_type in ("277CA", "277"):
            parse_result = await processor.parse_277_with_record(dest_path, edi_file)
        else:
            edi_file.status = "processed"
            await db.commit()
    except Exception as e:
        logger.exception("Error processing uploaded EDI file")
        edi_file.status = "error"
        edi_file.error_message = str(e)
        await db.commit()

    await log_audit_event(
        db, current_user, action="edi_file_uploaded", resource_type="edi_file",
        resource_id=str(edi_file.id), request=request,
        metadata={"file_type": file_type, "size": len(content), "status": edi_file.status},
    )
    await db.commit()

    return {
        "success": True,
        "message": "EDI file uploaded and processing initiated",
        "data": {
            "id": edi_file.id,
            "file_type": file_type,
            "filename": file.filename,
            "status": edi_file.status,
            "parse_result": parse_result,
        },
    }


@router.get("/files/{file_id}")
async def get_edi_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Get EDI file details - scoped to tenant"""
    current_user.require_role("billing")
    result = await db.execute(
        select(EDIFile).where(and_(EDIFile.id == file_id, EDIFile.tenant_id == current_user.tenant_id))
    )
    edi_file = result.scalar_one_or_none()
    if not edi_file:
        raise HTTPException(status_code=404, detail="EDI file not found")

    return {
        "success": True,
        "data": {
            "id": edi_file.id,
            "file_type": edi_file.file_type,
            "direction": edi_file.direction,
            "filename": edi_file.filename,
            # file_path intentionally omitted to avoid disclosing server filesystem layout.
            "file_size": edi_file.file_size,
            "interchange_control_number": edi_file.interchange_control_number,
            "transaction_count": edi_file.transaction_count,
            "status": edi_file.status,
            "processed_at": edi_file.processed_at.isoformat() if edi_file.processed_at else None,
            "error_message": edi_file.error_message,
            "validation_errors": edi_file.validation_errors,
            "created_at": edi_file.created_at.isoformat() if edi_file.created_at else None,
        },
    }


@router.get("/files/{file_id}/parsed")
async def get_edi_file_parsed(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Return the raw EDI file plus a structured per-segment parse view.

    Powers the EDI Debug Panel — operators use this to diagnose why a 277CA
    didn\'t move a claim, what CARC codes a 835 carried, or whether the payer
    sent a malformed segment.
    """
    current_user.require_role("billing")

    result = await db.execute(
        select(EDIFile).where(and_(EDIFile.id == file_id, EDIFile.tenant_id == current_user.tenant_id))
    )
    edi_file = result.scalar_one_or_none()
    if not edi_file:
        raise HTTPException(status_code=404, detail="EDI file not found")

    # Containment check (same as download endpoint)
    storage_root = os.path.realpath(EDI_STORAGE_PATH)
    real_path = os.path.realpath(edi_file.file_path or "")
    if not (real_path == storage_root or real_path.startswith(storage_root + os.sep)):
        raise HTTPException(status_code=404, detail="File not found")
    if not os.path.exists(real_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    try:
        with open(real_path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except Exception:
        logger.exception("Failed to read EDI file %s for parse view", file_id)
        raise HTTPException(status_code=500, detail="Failed to read file")

    # Segment-level parse — strip whitespace, split on ~, skip empties.
    segments = []
    for idx, segment in enumerate(raw.split("~")):
        s = segment.strip()
        if not s:
            continue
        parts = s.split("*")
        tag = parts[0]
        elements = parts[1:]
        segments.append({
            "index": idx,
            "tag": tag,
            "raw": s,
            "elements": elements,
        })

    # Format-specific summary so the FE can show the most useful first.
    summary: Dict[str, Any] = {"segment_count": len(segments)}
    if edi_file.file_type == "835":
        # Run the existing pure parser for full payment/denial breakdown.
        try:
            parsed = EDIProcessor._parse_835_content(raw)
            summary["claims_paid"] = len(parsed.get("payments", []))
            summary["claims_denied"] = len(parsed.get("denials", []))
            summary["total_paid"] = parsed.get("total_paid", 0)
            summary["payments"] = parsed.get("payments", [])
            summary["denials"] = parsed.get("denials", [])
        except Exception as e:
            summary["parse_error"] = str(e)
    elif edi_file.file_type in ("277CA", "277"):
        # Pull TRN tracking + the most recent STC code per TRN.
        track_count = sum(1 for s in segments if s["tag"] == "TRN")
        stc_count = sum(1 for s in segments if s["tag"] == "STC")
        summary["tracking_numbers"] = track_count
        summary["status_segments"] = stc_count

    return {
        "success": True,
        "data": {
            "id": edi_file.id,
            "file_type": edi_file.file_type,
            "filename": edi_file.filename,
            "file_size": edi_file.file_size,
            "status": edi_file.status,
            "error_message": edi_file.error_message,
            "raw": raw,
            "segments": segments,
            "summary": summary,
        },
    }


@router.get("/files/{file_id}/download")
async def download_edi_file(
    file_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Download raw EDI file content. Audited at the access layer."""
    from fastapi.responses import FileResponse

    current_user.require_role("billing")
    result = await db.execute(
        select(EDIFile).where(and_(EDIFile.id == file_id, EDIFile.tenant_id == current_user.tenant_id))
    )
    edi_file = result.scalar_one_or_none()
    if not edi_file:
        raise HTTPException(status_code=404, detail="EDI file not found")

    # Defense in depth: only serve files that live under the configured EDI
    # storage root. Without this, a corrupted file_path could be coerced into
    # serving arbitrary readable files.
    storage_root = os.path.realpath(EDI_STORAGE_PATH)
    real_path = os.path.realpath(edi_file.file_path)
    if not (real_path == storage_root or real_path.startswith(storage_root + os.sep)):
        logger.warning("Refusing to serve EDI file outside storage root: %s", real_path)
        raise HTTPException(status_code=404, detail="File not found")

    if not os.path.exists(real_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    # Serve with sanitized download filename so a corrupted DB row can't
    # inject control characters into Content-Disposition.
    download_name = safe_filename(edi_file.filename, fallback=f"edi_{file_id}.edi")

    await log_audit_event(
        db, current_user, action="edi_file_downloaded", resource_type="edi_file",
        resource_id=str(file_id), request=request,
        metadata={"file_type": edi_file.file_type},
    )
    await db.commit()

    return FileResponse(
        path=real_path,
        filename=download_name,
        media_type="application/octet-stream",
    )
