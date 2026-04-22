"""
ClaimFlow - JWT/OIDC authentication and tenant-aware principal.
Supports both HS256 (dev) and RS256/JWKS (production OIDC providers).
"""

import os
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

JWT_SECRET = os.getenv("JWT_SECRET", "claimflow-dev-secret-change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "claimflow")
JWT_ISSUER = os.getenv("JWT_ISSUER", "")
JWT_JWKS_URL = os.getenv("JWT_JWKS_URL", "")

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
    """Decode and validate a JWT. Supports HS256 dev and RS256/JWKS prod."""
    if JWT_ALGORITHM == "RS256" and JWT_JWKS_URL:
        try:
            client = _get_jwks_client()
            signing_key = client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=JWT_AUDIENCE,
                issuer=JWT_ISSUER or None,
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
        except jwt.InvalidTokenError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}")

    options: Dict[str, Any] = {}
    if not JWT_ISSUER:
        options["verify_iss"] = False
    if JWT_AUDIENCE == "claimflow" and JWT_SECRET.startswith("claimflow-dev"):
        options["verify_aud"] = False

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE if options.get("verify_aud", True) else None,
            issuer=JWT_ISSUER if options.get("verify_iss", True) else None,
            options=options,
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}")


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> Principal:
    """FastAPI dependency - validates JWT and returns a Principal with tenant context."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )

    payload = _decode_token(credentials.credentials)

    tenant_id = (
        payload.get("tenant_id")
        or payload.get("https://claimflow.io/tenant_id")
        or request.headers.get("X-Tenant-ID")
    )
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tenant_id not found in token or headers",
        )

    return Principal(
        user_id=payload.get("sub", ""),
        tenant_id=tenant_id,
        email=payload.get("email", ""),
        roles=payload.get("roles", []),
        raw_claims=payload,
    )
