"""
ClaimFlow - Audit log viewer API.

Read-only window onto the SecurityAuditLog table that B4 started populating.
Admin role required (the log records who-did-what to PHI / credentials /
config). Filters cover the common operator questions: "what did user X do?",
"what happened to claim Y?", "show me failed actions in the last hour".
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, Principal
from core.database import get_db
from models.audit import SecurityAuditLog

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/audit-log", tags=["Admin - Audit Log"])


def _serialize(row: SecurityAuditLog) -> dict:
    return {
        "id": row.id,
        "tenant_id": str(row.tenant_id) if row.tenant_id else None,
        "user_id": row.user_id,
        "user_email": row.user_email,
        "user_role": row.user_role,
        "action": row.action,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "ip_address": row.ip_address,
        "user_agent": row.user_agent,
        "changes": row.changes,
        "metadata": row.extra_data,
        "success": row.success,
        "error_message": row.error_message,
    }


@router.get("")
async def list_audit_events(
    action: Optional[str] = Query(None, description="Exact action match, e.g. 'patient_viewed'"),
    resource_type: Optional[str] = Query(None, description="e.g. 'patient' / 'claim'"),
    resource_id: Optional[str] = Query(None),
    user_email: Optional[str] = Query(None, description="Substring match on user_email"),
    success: Optional[bool] = Query(None, description="True = only successes; False = only failures"),
    since: Optional[datetime] = Query(None, description="ISO timestamp lower bound"),
    until: Optional[datetime] = Query(None, description="ISO timestamp upper bound"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List audit events for the current tenant (admin-only)."""
    current_user.require_role("admin")

    filters = [SecurityAuditLog.tenant_id == current_user.tenant_id]
    if action:
        filters.append(SecurityAuditLog.action == action)
    if resource_type:
        filters.append(SecurityAuditLog.resource_type == resource_type)
    if resource_id:
        filters.append(SecurityAuditLog.resource_id == resource_id)
    if user_email:
        filters.append(SecurityAuditLog.user_email.ilike(f"%{user_email.strip()}%"))
    if success is not None:
        filters.append(SecurityAuditLog.success.is_(success))
    if since:
        filters.append(SecurityAuditLog.timestamp >= since)
    if until:
        filters.append(SecurityAuditLog.timestamp <= until)

    data_query = (
        select(SecurityAuditLog).where(and_(*filters))
        .order_by(SecurityAuditLog.timestamp.desc())
        .limit(limit).offset(offset)
    )
    count_query = select(func.count(SecurityAuditLog.id)).where(and_(*filters))

    rows = (await db.execute(data_query)).scalars().all()
    total = (await db.execute(count_query)).scalar() or 0

    return {
        "success": True,
        "data": [_serialize(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/_meta/actions")
async def distinct_actions(
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Return the distinct action names for the FE filter dropdown."""
    current_user.require_role("admin")
    rows = await db.execute(
        select(SecurityAuditLog.action, func.count(SecurityAuditLog.id))
        .where(SecurityAuditLog.tenant_id == current_user.tenant_id)
        .group_by(SecurityAuditLog.action)
        .order_by(SecurityAuditLog.action)
    )
    return {
        "success": True,
        "data": [{"action": a, "count": c} for a, c in rows.all()],
    }
