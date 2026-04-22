"""
ClaimFlow - Tenant-scoped user model.

Replaces the hardcoded DEV_USERS dict in dev_login. Users authenticate either
via the database-backed login (dev/staging) or via OIDC (prod, when
JWT_ALGORITHM=RS256 + JWT_JWKS_URL is configured).

Roles are stored as a JSONB array of strings drawn from the ROLES hierarchy
in api/auth.py: super_admin / admin / billing / credentialing / readonly.

Passwords are stored as Argon2 hashes via passlib. We never store plaintext.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from models.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    # Argon2 hash. NULL means OIDC-only (no password login).
    password_hash = Column(String(255), nullable=True)
    roles = Column(ARRAY(String), nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Email is unique per tenant (so two tenants can have the same email)
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        Index("ix_users_email_active", "email", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<User {self.email} tenant={self.tenant_id} roles={self.roles}>"
