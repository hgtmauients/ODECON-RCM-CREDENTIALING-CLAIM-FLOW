"""
ClaimFlow - Per-user notification feed.

Tenant-scoped. Users see notifications targeted at them OR tenant-wide
(user_id NULL). Mark-read updates the read_at column. The bell in the FE
header polls /unread-count cheaply; the drawer fetches the list.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, Principal
from core.database import get_db
from models.notification import Notification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _audience_filter(current_user: Principal):
    """Notifications targeted at this user OR tenant-wide."""
    return and_(
        Notification.tenant_id == current_user.tenant_id,
        or_(
            Notification.user_id.is_(None),
            Notification.user_id == _safe_uuid(current_user.user_id),
        ),
    )


def _safe_uuid(value: str | None) -> Optional[UUID]:
    if not value:
        return None
    try:
        return UUID(value)
    except (TypeError, ValueError):
        return None


def _serialize(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "type": n.type,
        "severity": n.severity,
        "title": n.title,
        "message": n.message,
        "link_url": n.link_url,
        "metadata": n.extra_data,
        "is_read": n.read_at is not None,
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@router.get("")
async def list_notifications(
    is_read: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List notifications for the current user (own + tenant-wide)."""
    filters = [_audience_filter(current_user)]
    if is_read is True:
        filters.append(Notification.read_at.isnot(None))
    elif is_read is False:
        filters.append(Notification.read_at.is_(None))

    data_query = (
        select(Notification).where(and_(*filters))
        .order_by(Notification.created_at.desc()).limit(limit).offset(offset)
    )
    count_query = select(func.count(Notification.id)).where(and_(*filters))

    rows = (await db.execute(data_query)).scalars().all()
    total = (await db.execute(count_query)).scalar() or 0
    return {
        "success": True,
        "data": [_serialize(n) for n in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/unread-count")
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Cheap count for the bell badge."""
    res = await db.execute(
        select(func.count(Notification.id)).where(and_(
            _audience_filter(current_user),
            Notification.read_at.is_(None),
        ))
    )
    return {"success": True, "data": {"unread": int(res.scalar() or 0)}}


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    res = await db.execute(
        select(Notification).where(and_(
            Notification.id == notification_id,
            _audience_filter(current_user),
        ))
    )
    n = res.scalar_one_or_none()
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    if n.read_at is None:
        n.read_at = datetime.now(timezone.utc)
        await db.commit()
    return {"success": True, "data": _serialize(n)}


@router.post("/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Bulk mark every unread notification visible to this user as read."""
    res = await db.execute(
        select(Notification).where(and_(
            _audience_filter(current_user),
            Notification.read_at.is_(None),
        ))
    )
    now = datetime.now(timezone.utc)
    count = 0
    for n in res.scalars().all():
        n.read_at = now
        count += 1
    await db.commit()
    return {"success": True, "data": {"marked_read": count}}
