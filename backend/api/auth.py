"""
ClaimFlow - JWT/OIDC authentication and tenant-aware principal.
Supports both HS256 (dev) and RS256/JWKS (production OIDC providers).

Security model:
- Tenant ID MUST come from the JWT token, never from a request header.
- The X-Tenant-ID header is only honored when the principal has the
  super_admin role (for cross-tenant operations like impersonation).
- In production (ENV=production), JWT_SECRET must be set or startup fails.
"""

import base64
import os
import secrets
import logging
from dataclasses import dataclass, field
from uuid import UUID
from typing import Dict, Any, List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

import jwt
from jwt import PyJWKClient

from core.security_signal import log_security_signal
from core.database import get_db
from core.db_rls import set_tenant_context
from models.user import User
from models.tenant import Tenant

logger = logging.getLogger(__name__)

ENV = os.getenv("ENV", "development")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "claimflow")
JWT_ISSUER = os.getenv("JWT_ISSUER", "")
JWT_JWKS_URL = os.getenv("JWT_JWKS_URL", "")


def get_jwt_secret() -> str:
    """Resolve JWT signing secret.

    Production: fail-fast unless JWT_SECRET is set.
    Dev/test: when unset, generate a fresh per-process random secret so a
    static value is never compiled into the source tree (and so different
    processes can\'t accidentally cross-trust each other).
    """
    secret = os.getenv("JWT_SECRET", "")
    if secret:
        return secret
    if ENV == "production":
        raise RuntimeError(
            "JWT_SECRET is required in production. "
            "Generate one with: openssl rand -base64 32"
        )
    ephemeral = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode("ascii")
    logger.warning(
        "JWT_SECRET not set; using ephemeral per-process secret (env=%s). "
        "Tokens issued by this process will not validate after restart.",
        ENV,
    )
    return ephemeral


JWT_SECRET = get_jwt_secret()

if ENV == "production" and JWT_ALGORITHM == "HS256" and len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET must be at least 32 characters in production")

if ENV == "production" and JWT_ALGORITHM == "RS256" and not JWT_JWKS_URL:
    raise RuntimeError("JWT_JWKS_URL is required when JWT_ALGORITHM=RS256 in production")

_jwks_client: Optional[PyJWKClient] = None

security_scheme = HTTPBearer(auto_error=False)

ROLES = {
    "super_admin": ["super_admin", "admin", "billing", "credentialing", "readonly"],
    "admin": ["admin", "billing", "credentialing", "readonly"],
    "billing": ["billing", "readonly"],
    "credentialing": ["credentialing", "readonly"],
    "readonly": ["readonly"],
}


@dataclass
class Principal:
    """Authenticated user context passed into route handlers."""
    user_id: str
    tenant_id: str
    email: str
    roles: List[str] = field(default_factory=list)
    raw_claims: Dict[str, Any] = field(default_factory=dict)
    # The tenant_id originally embedded in the JWT (before any super_admin override).
    # Used for audit logging when super_admin acts on a different tenant.
    token_tenant_id: str = ""

    def has_role(self, role: str) -> bool:
        for user_role in self.roles:
            if role in ROLES.get(user_role, [user_role]):
                return True
        return role in self.roles

    def require_role(self, role: str) -> None:
        if not self.has_role(role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' required",
            )


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(JWT_JWKS_URL, cache_keys=True, lifespan=3600)
    return _jwks_client


def _decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT. Supports HS256 (dev) and RS256/JWKS (prod)."""
    if JWT_ALGORITHM == "RS256" and JWT_JWKS_URL:
        try:
            client = _get_jwks_client()
            signing_key = client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=JWT_AUDIENCE,
                issuer=JWT_ISSUER if JWT_ISSUER else None,
                options={"verify_iss": bool(JWT_ISSUER)},
            )
            return payload
        except jwt.ExpiredSignatureError:
            log_security_signal("auth_token_expired", path="jwt_decode", algorithm="RS256")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
        except jwt.InvalidTokenError as exc:
            logger.info("RS256 token validation failed: %s", exc)
            log_security_signal("auth_token_invalid", path="jwt_decode", algorithm="RS256")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # HS256 path - audience and issuer are always verified when configured.
    options: Dict[str, Any] = {
        "verify_iss": bool(JWT_ISSUER),
        "verify_aud": bool(JWT_AUDIENCE),
    }

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE if JWT_AUDIENCE else None,
            issuer=JWT_ISSUER if JWT_ISSUER else None,
            options=options,
        )
        return payload
    except jwt.ExpiredSignatureError:
        log_security_signal("auth_token_expired", path="jwt_decode", algorithm=JWT_ALGORITHM)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError as exc:
        logger.info("JWT validation failed: %s", exc)
        log_security_signal("auth_token_invalid", path="jwt_decode", algorithm=JWT_ALGORITHM)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> Principal:
    """
    FastAPI dependency: validates JWT and returns a Principal with tenant context.

    Tenant resolution:
    1. The JWT MUST contain a tenant_id claim (or the namespaced equivalent).
       Without it, the request is rejected.
    2. The X-Tenant-ID header is only honored when the principal has super_admin role
       (allows cross-tenant operations like support / impersonation).
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )

    payload = _decode_token(credentials.credentials)

    # Tenant resolution: support both a top-level claim and a namespaced claim
    # (some IdPs add custom claims under a URL prefix). If both are present
    # they MUST agree — otherwise reject the token to avoid silent ambiguity.
    primary_tid = payload.get("tenant_id") or ""
    namespaced_tid = payload.get("https://claimflow.io/tenant_id") or ""

    if primary_tid and namespaced_tid and primary_tid != namespaced_tid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token contains conflicting tenant_id claims",
        )

    token_tenant_id = primary_tid or namespaced_tid
    if not token_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain a tenant_id claim",
        )
    try:
        token_tenant_uuid = UUID(str(token_tenant_id))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token tenant_id claim is invalid",
        )

    tenant_result = await db.execute(
        select(Tenant.id).where(
            and_(
                Tenant.id == token_tenant_uuid,
                Tenant.is_active.is_(True),
            )
        )
    )
    if not tenant_result.scalar_one_or_none():
        log_security_signal(
            "auth_tenant_inactive_or_missing",
            user_id=payload.get("sub", ""),
            token_tenant_id=token_tenant_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is inactive",
        )

    token_roles = payload.get("roles", []) or []
    roles = list(token_roles)
    is_super_admin = any(r == "super_admin" for r in roles)

    header_tenant_id = request.headers.get("X-Tenant-ID")
    effective_tenant_id = token_tenant_id

    user_id = payload.get("sub", "")
    if user_id:
        try:
            user_uuid = UUID(str(user_id))
            user_result = await db.execute(
                select(User).where(
                    and_(
                        User.id == user_uuid,
                        User.tenant_id == token_tenant_uuid,
                    )
                )
            )
            user_row = user_result.scalar_one_or_none()
            if not user_row or not user_row.is_active:
                log_security_signal(
                    "auth_user_inactive_or_missing",
                    user_id=str(user_id),
                    token_tenant_id=token_tenant_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token",
                )
            # Enforce server-side revocation by using current DB roles over stale JWT roles.
            roles = list(user_row.roles or [])
            is_super_admin = any(r == "super_admin" for r in roles)
        except ValueError:
            token_email = str(payload.get("email", "")).strip().lower()
            if not token_email:
                log_security_signal(
                    "auth_oidc_subject_unmapped",
                    user_id=str(user_id),
                    token_tenant_id=token_tenant_id,
                    reason="missing_email_claim",
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token",
                )

            oidc_user_result = await db.execute(
                select(User).where(
                    and_(
                        User.email == token_email,
                        User.tenant_id == token_tenant_uuid,
                    )
                )
            )
            oidc_users = oidc_user_result.scalars().all()
            if len(oidc_users) != 1 or not oidc_users[0].is_active:
                logger.info(
                    "OIDC subject rejected due to unmapped user: env=%s sub=%s email=%s",
                    ENV,
                    user_id,
                    token_email,
                )
                log_security_signal(
                    "auth_oidc_subject_unmapped",
                    user_id=str(user_id),
                    token_tenant_id=token_tenant_id,
                    token_email=token_email,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token",
                )
            roles = list(oidc_users[0].roles or [])
            is_super_admin = any(r == "super_admin" for r in roles)

    if header_tenant_id and header_tenant_id != token_tenant_id:
        if not is_super_admin:
            log_security_signal(
                "tenant_override_denied",
                user_id=payload.get("sub", ""),
                token_tenant_id=token_tenant_id,
                requested_tenant_id=header_tenant_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="X-Tenant-ID override requires super_admin role",
            )
        try:
            requested_tenant_uuid = UUID(str(header_tenant_id))
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="X-Tenant-ID must be a valid tenant UUID",
            )
        requested_tenant_result = await db.execute(
            select(Tenant.id).where(
                and_(
                    Tenant.id == requested_tenant_uuid,
                    Tenant.is_active.is_(True),
                )
            )
        )
        if not requested_tenant_result.scalar_one_or_none():
            log_security_signal(
                "tenant_override_target_inactive_or_missing",
                user_id=payload.get("sub", ""),
                token_tenant_id=token_tenant_id,
                requested_tenant_id=header_tenant_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="X-Tenant-ID target tenant is inactive or missing",
            )
        logger.info(
            "Super-admin tenant override: user=%s token_tenant=%s acting_as=%s",
            payload.get("sub", ""), token_tenant_id, header_tenant_id,
        )
        log_security_signal(
            "tenant_override_applied",
            user_id=payload.get("sub", ""),
            token_tenant_id=token_tenant_id,
            requested_tenant_id=header_tenant_id,
        )
        effective_tenant_id = header_tenant_id

    await set_tenant_context(db, effective_tenant_id)
    return Principal(
        user_id=payload.get("sub", ""),
        tenant_id=effective_tenant_id,
        email=payload.get("email", ""),
        roles=roles,
        raw_claims=payload,
        token_tenant_id=token_tenant_id,
    )
