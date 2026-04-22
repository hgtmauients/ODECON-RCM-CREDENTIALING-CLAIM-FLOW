"""
ClaimFlow - Dev login endpoint.
Issues JWTs for local development. In production, use an external OIDC provider.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import jwt

router = APIRouter(prefix="/auth", tags=["Auth"])

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
DEV_MODE = os.getenv("ENV", "development") == "development"

DEV_USERS: Dict[str, Dict[str, Any]] = {
    "admin@claimflow.io": {
        "password": "admin",
        "user_id": "dev-admin-001",
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "roles": ["super_admin", "admin", "billing"],
    },
    "billing@claimflow.io": {
        "password": "billing",
        "user_id": "dev-billing-001",
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "roles": ["billing"],
    },
}


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
async def dev_login(req: LoginRequest):
    """Dev-only login endpoint. Returns a JWT for local testing."""
    if not DEV_MODE:
        raise HTTPException(status_code=404, detail="Not found")

    user = DEV_USERS.get(req.email)
    if not user or user["password"] != req.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    payload = {
        "sub": user["user_id"],
        "email": req.email,
        "tenant_id": user["tenant_id"],
        "roles": user["roles"],
        "aud": os.getenv("JWT_AUDIENCE", "claimflow"),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "email": req.email,
            "user_id": user["user_id"],
            "tenant_id": user["tenant_id"],
            "roles": user["roles"],
        },
    }
