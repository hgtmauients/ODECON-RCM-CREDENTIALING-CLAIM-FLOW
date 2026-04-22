"""
ClaimFlow - Tenant model.
Represents an organization/practice using ClaimFlow.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB

from models.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(128), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    settings = Column(JSONB, default=dict)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    npi = Column(String(10), nullable=True)
    tax_id = Column(String(20), nullable=True)
    address_line_1 = Column(String(255), nullable=True)
    address_line_2 = Column(String(255), nullable=True)
    city = Column(String(128), nullable=True)
    state = Column(String(2), nullable=True)
    zip_code = Column(String(10), nullable=True)
    phone = Column(String(20), nullable=True)
    billing_contact_email = Column(String(255), nullable=True)
