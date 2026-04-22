"""
ClaimFlow - Tenant user / RBAC administration API.

Admins can list, create, update, deactivate users in their own tenant.
super_admin can act across tenants. All mutations are audit-logged.

Roles assignable from this endpoint are the canonical set defined in
api/auth.py:ROLES — anything outside that set is rejected.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import ROLES, get_current_user, Principal
from core.audit import log_audit_event
from core.database import get_db
from core.password import hash_password
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/users", tags=["Admin - Users"])

ASSIGNABLE_ROLES = frozenset(ROLES.keys())


def _validate_roles(roles: List[str]) -> List[str]:
    cleaned = sorted({r for r in roles if r})
    bad = [r for r in cleaned if r not in ASSIGNABLE_ROLES]
    if bad:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown role(s): {bad}. Valid: {sorted(ASSIGNABLE_ROLES)}",
        )
    return cleaned


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    email: EmailStr
    full_name: Optional[str] = Field(None, max_length=255)
    password: str = Field(..., min_length=8, max_length=256)
    roles: List[str] = Field(default_factory=lambda: ["readonly"])
    is_active: bool = True


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    full_name: Optional[str] = Field(None, max_length=255)
    roles: Optional[List[str]] = None
    is_active: Optional[bool] = None


class PasswordReset(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=256)


def _serialize(u: User) -> dict:
    return {
        "id": str(u.id),
        "tenant_id": str(u.tenant_id),
        "email": u.email,
        "full_name": u.full_name,
        "roles": list(u.roles or []),
        "is_active": u.is_active,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@router.get("")
async def list_users(
    request: Request,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    role: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List users in the current tenant. Admin role required."""
    current_user.require_role("admin")

    filters = [User.tenant_id == current_user.tenant_id]
    if is_active is not None:
        filters.append(User.is_active.is_(is_active))
    if search:
        term = f"%{search.strip()}%"
        filters.append(or_(User.email.ilike(term), User.full_name.ilike(term)))
    if role:
        if role not in ASSIGNABLE_ROLES:
            raise HTTPException(status_code=422, detail=f"Unknown role: {role}")
        filters.append(User.roles.any(role))

    data_query = (
        select(User).where(and_(*filters))
        .order_by(User.created_at.desc()).limit(limit).offset(offset)
    )
    count_query = select(func.count(User.id)).where(and_(*filters))

    rows = (await db.execute(data_query)).scalars().all()
    total = (await db.execute(count_query)).scalar() or 0

    return {
        "success": True,
        "data": [_serialize(u) for u in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("")
async def create_user(
    payload: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Create a tenant user. Admin role required; mutation audited."""
    current_user.require_role("admin")
    roles = _validate_roles(payload.roles)
    # Only super_admin can grant the super_admin role.
    if "super_admin" in roles and not current_user.has_role("super_admin"):
        raise HTTPException(status_code=403, detail="Only super_admin can grant super_admin")

    email = payload.email.lower().strip()
    existing = await db.execute(
        select(User.id).where(and_(
            User.tenant_id == current_user.tenant_id,
            User.email == email,
        ))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A user with that email already exists in this tenant")

    user = User(
        tenant_id=current_user.tenant_id,
        email=email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        roles=roles,
        is_active=payload.is_active,
        created_by=current_user.email,
    )
    db.add(user)
    await db.flush()

    await log_audit_event(
        db, current_user, action="user_created", resource_type="user",
        resource_id=str(user.id), request=request,
        metadata={"email": email, "roles": roles, "is_active": payload.is_active},
    )
    await db.commit()
    await db.refresh(user)
    return {"success": True, "data": _serialize(user)}


async def _load_user(user_id: UUID, current_user: Principal, db: AsyncSession) -> User:
    result = await db.execute(
        select(User).where(and_(
            User.id == user_id,
            User.tenant_id == current_user.tenant_id,
        ))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/{user_id}")
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    current_user.require_role("admin")
    user = await _load_user(user_id, current_user, db)
    return {"success": True, "data": _serialize(user)}


@router.put("/{user_id}")
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Update a user. Admin role required.

    Self-edit safety: an admin cannot remove their own super_admin role or
    deactivate themselves (would lock them out instantly).
    """
    current_user.require_role("admin")
    user = await _load_user(user_id, current_user, db)

    updates = payload.model_dump(exclude_unset=True)

    if "roles" in updates:
        new_roles = _validate_roles(updates["roles"] or [])
        # Only super_admin can grant or revoke super_admin.
        old_super = "super_admin" in (user.roles or [])
        new_super = "super_admin" in new_roles
        if old_super != new_super and not current_user.has_role("super_admin"):
            raise HTTPException(status_code=403, detail="Only super_admin can change the super_admin role")
        # Self-protect: don't let an admin demote themselves out of super_admin
        # if they are the last one in the tenant.
        if str(user.id) == current_user.user_id and old_super and not new_super:
            other_supers = await db.execute(
                select(func.count(User.id)).where(and_(
                    User.tenant_id == current_user.tenant_id,
                    User.id != user.id,
                    User.is_active.is_(True),
                    User.roles.any("super_admin"),
                ))
            )
            if (other_supers.scalar() or 0) == 0:
                raise HTTPException(
                    status_code=409,
                    detail="Refusing to remove super_admin from the last active super_admin in this tenant",
                )
        user.roles = new_roles

    if "full_name" in updates:
        user.full_name = updates["full_name"]

    if "is_active" in updates:
        if str(user.id) == current_user.user_id and updates["is_active"] is False:
            raise HTTPException(status_code=409, detail="Refusing to deactivate yourself")
        user.is_active = bool(updates["is_active"])

    await log_audit_event(
        db, current_user, action="user_updated", resource_type="user",
        resource_id=str(user.id), request=request,
        changes={"updated_fields": sorted(updates.keys())},
    )
    await db.commit()
    return {"success": True, "data": _serialize(user)}


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: UUID,
    payload: PasswordReset,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    current_user.require_role("admin")
    user = await _load_user(user_id, current_user, db)
    user.password_hash = hash_password(payload.new_password)
    await log_audit_event(
        db, current_user, action="user_password_reset", resource_type="user",
        resource_id=str(user.id), request=request,
    )
    await db.commit()
    return {"success": True, "message": "Password reset"}


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Soft-delete: flips is_active=False. We keep the row for audit history."""
    current_user.require_role("admin")
    user = await _load_user(user_id, current_user, db)
    if str(user.id) == current_user.user_id:
        raise HTTPException(status_code=409, detail="Refusing to deactivate yourself")
    user.is_active = False
    await log_audit_event(
        db, current_user, action="user_deactivated", resource_type="user",
        resource_id=str(user.id), request=request,
    )
    await db.commit()
    return {"success": True, "message": "User deactivated"}


@router.get("/_meta/roles")
async def list_assignable_roles(current_user: Principal = Depends(get_current_user)):
    """Return the role catalog for the FE dropdowns."""
    current_user.require_role("admin")
    return {
        "success": True,
        "data": [
            {"name": role, "expands_to": sorted(set(expansion))}
            for role, expansion in ROLES.items()
        ],
    }
