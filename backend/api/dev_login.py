"""
ClaimFlow - Database-backed password login.

Reads users from the `users` table (User model). Argon2-hashed passwords.
Replaces the hardcoded DEV_USERS dict that previously lived here.

Production guidance:
- Prefer OIDC (set JWT_ALGORITHM=RS256 + JWT_JWKS_URL). Authorization Code
  flow with PKCE handled by the IdP, this endpoint isn\'t used.
- If you must run password login in production (small / single-tenant
  deploy), set ALLOW_PASSWORD_LOGIN=true. Otherwise the endpoint 404s in
  ENV=production so it can\'t be brute-forced from the public internet.

Bootstrapping:
- Seed the first super_admin via `python -m scripts.bootstrap_admin`.
- After that, admins manage all users via /api/admin/users.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import JWT_SECRET, JWT_ALGORITHM, get_current_user, Principal
from core.audit import log_audit_event
from core.database import get_db
from core.password import verify_password, hash_password, needs_rehash
from models.tenant import Tenant
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])


def _password_login_enabled() -> bool:
    env = os.getenv("ENV", "development")
    if env != "production":
        return True
    return os.getenv("ALLOW_PASSWORD_LOGIN", "").lower() in ("1", "true", "yes")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # Optional: pin login to a specific tenant if the email is shared across
    # tenants. When omitted we look up the user by email and require exactly
    # one match to avoid silent ambiguity.
    tenant_id: str | None = None


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Validate email + password against the users table and return a JWT.

    Generic 401 response for every failure mode (wrong password, missing user,
    inactive user, ambiguous email-without-tenant) so an attacker cannot
    enumerate accounts.
    """
    if not _password_login_enabled():
        raise HTTPException(status_code=404, detail="Not found")

    email = req.email.strip().lower()

    filters = [User.email == email, User.is_active.is_(True)]
    if req.tenant_id:
        filters.append(User.tenant_id == req.tenant_id)

    result = await db.execute(
        select(User)
        .join(Tenant, Tenant.id == User.tenant_id)
        .where(and_(*filters, Tenant.is_active.is_(True)))
    )
    matches = result.scalars().all()

    if len(matches) != 1 or not matches[0].password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = matches[0]
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Refresh the hash if Argon2 parameters have moved on.
    if needs_rehash(user.password_hash):
        try:
            user.password_hash = hash_password(req.password)
        except Exception:
            logger.warning("password_hash rehash failed for user %s", user.id)

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    payload = {
        "sub": str(user.id),
        "email": user.email,
        "tenant_id": str(user.tenant_id),
        "roles": list(user.roles or []),
        "aud": os.getenv("JWT_AUDIENCE", "claimflow"),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "email": user.email,
            "user_id": str(user.id),
            "tenant_id": str(user.tenant_id),
            "roles": list(user.roles or []),
            "full_name": user.full_name,
        },
    }


@router.get("/me")
async def me(current_user: Principal = Depends(get_current_user)):
    """Return the JWT-derived principal (handy for FE rehydration)."""
    return {
        "user_id": current_user.user_id,
        "tenant_id": current_user.tenant_id,
        "email": current_user.email,
        "roles": current_user.roles,
    }


class ChangePasswordRequest(BaseModel):
    """Self-service password change body."""
    model_config = ConfigDict(extra="ignore")
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=8, max_length=256)


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Change the signed-in user's password.

    Generic 401 on any failure (wrong current password, missing user, OIDC
    user with no password hash) so an attacker who steals an access token
    cannot enumerate the password-vs-OIDC distinction.
    """
    try:
        user_uuid = UUID(current_user.user_id)
    except (TypeError, ValueError):
        # Tokens minted via OIDC may carry a non-UUID `sub` (e.g. an
        # external IdP user identifier). Those users don\'t have a row in
        # the users table — they cannot change their password here.
        raise HTTPException(status_code=401, detail="Invalid credentials")

    res = await db.execute(
        select(User).where(and_(
            User.id == user_uuid,
            User.tenant_id == current_user.tenant_id,
        ))
    )
    user = res.scalar_one_or_none()
    if not user or not user.is_active or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(payload.current_password, user.password_hash):
        # Audit the failure so brute-force attempts via leaked tokens are
        # visible in the security log.
        await log_audit_event(
            db, current_user, action="password_change_failed", resource_type="user",
            resource_id=str(user.id), request=request,
            success=False, error_message="current_password mismatch",
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=422, detail="New password must differ from current")

    user.password_hash = hash_password(payload.new_password)
    await log_audit_event(
        db, current_user, action="password_changed_self", resource_type="user",
        resource_id=str(user.id), request=request,
    )
    await db.commit()
    return {"success": True, "message": "Password changed"}
