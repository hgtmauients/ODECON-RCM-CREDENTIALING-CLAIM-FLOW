"""
ClaimFlow - In-app notification model.

Notifications can be tenant-wide (user_id NULL — every user in the tenant
sees them) or user-targeted. They power the bell + drawer in the frontend
header. The scheduler.expirations job + denial creation hooks also populate
this table so operators see actionable alerts without having to poll a list.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from models.base import Base


SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"
SEVERITY_SUCCESS = "success"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    # NULL = tenant-wide; otherwise scoped to the specific user (UUID from User.id)
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Discriminator used by the FE for routing / icon choice. e.g.
    # "credential.expiring", "denial.new", "claim.rejected", "system.error".
    type = Column(String(64), nullable=False, index=True)
    severity = Column(String(16), nullable=False, default=SEVERITY_INFO)

    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    # Optional in-app deep link, e.g. "/credentialing/PROV_123"
    link_url = Column(String(512), nullable=True)
    # Free-form context for FE rendering (counts, IDs, dates, etc.)
    extra_data = Column("metadata", JSONB, nullable=True)

    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True,
    )

    __table_args__ = (
        Index("ix_notifications_tenant_user_unread", "tenant_id", "user_id", "read_at"),
    )

    def __repr__(self) -> str:
        return f"<Notification {self.type} tenant={self.tenant_id} user={self.user_id} read={bool(self.read_at)}>"
