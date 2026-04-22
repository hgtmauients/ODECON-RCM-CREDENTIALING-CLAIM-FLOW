"""
EDI File Management API
Upload, list, and manage EDI files (837, 277, 835)
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from typing import Optional
from datetime import datetime
import os
import logging

from core.database import get_db
from api.auth import get_current_user, Principal
from models.claims import EDIFile
from services.edi_processor import EDIProcessor, EDI_STORAGE_PATH

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


@router.post("/upload")
async def upload_edi_file(
    file: UploadFile = File(...),
    file_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """
    Upload an EDI file (835, 277, etc.) for processing.
    Ingests inbound files manually when clearinghouse polling is not configured.
    """
    content = await file.read()
    content_str = content.decode("utf-8", errors="replace")

    # Auto-detect file type if not provided
    if not file_type:
        if "835" in (file.filename or ""):
            file_type = "835"
        elif "277" in (file.filename or ""):
            file_type = "277CA"
        elif "271" in (file.filename or ""):
            file_type = "271"
        else:
            file_type = "unknown"

    # Persist file (non-blocking)
    import asyncio
    inbound_dir = os.path.join(EDI_STORAGE_PATH, current_user.tenant_id, "inbound")
    dest_path = os.path.join(inbound_dir, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")

    def _write_file():
        os.makedirs(inbound_dir, exist_ok=True)
        with open(dest_path, "wb") as f_out:
            f_out.write(content)

    await asyncio.to_thread(_write_file)

    # Create EDI file record
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

    # Process the file (parsers will use the existing edi_file record)
    processor = EDIProcessor(db)
    parse_result = {}
    try:
        if file_type == "835":
            parse_result = await processor.parse_835_with_record(dest_path, edi_file)
        elif file_type in ("277CA", "277"):
            parse_result = await processor.parse_277_with_record(dest_path, edi_file)
        else:
            edi_file.status = "processed"
            await db.commit()
    except Exception as e:
        logger.error(f"Error processing uploaded EDI file: {e}")
        edi_file.status = "error"
        edi_file.error_message = str(e)
        await db.commit()

    return {
        "success": True,
        "message": f"EDI file uploaded and processing initiated",
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
            "file_path": edi_file.file_path,
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


@router.get("/files/{file_id}/download")
async def download_edi_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Download raw EDI file content."""
    from fastapi.responses import FileResponse, PlainTextResponse

    result = await db.execute(
        select(EDIFile).where(and_(EDIFile.id == file_id, EDIFile.tenant_id == current_user.tenant_id))
    )
    edi_file = result.scalar_one_or_none()
    if not edi_file:
        raise HTTPException(status_code=404, detail="EDI file not found")

    if not os.path.exists(edi_file.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=edi_file.file_path,
        filename=edi_file.filename,
        media_type="application/octet-stream",
    )
