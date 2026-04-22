"""
ClaimFlow - Patient/Subscriber model.
Stores demographics required for 837P claim generation.
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Column, Integer, String, Date, DateTime, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from models.base import Base


class Patient(Base):
    """
    Patient/subscriber demographics.
    Contains the minimum data needed for 837P Loop 2010BA (subscriber)
    and Loop 2010CA (patient if different from subscriber).
    """
    __tablename__ = "patients"
    __table_args__ = (
        Index("ix_patients_tenant_last_name", "tenant_id", "last_name"),
        Index("ix_patients_tenant_member_id", "tenant_id", "member_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identity
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    middle_name = Column(String(50))
    suffix = Column(String(10))  # Jr, Sr, III
    date_of_birth = Column(Date, nullable=False)
    gender = Column(String(1), nullable=False)  # M, F, U

    # Address
    address_line_1 = Column(String(255), nullable=False)
    address_line_2 = Column(String(255))
    city = Column(String(128), nullable=False)
    state = Column(String(2), nullable=False)
    zip_code = Column(String(10), nullable=False)

    # Contact
    phone = Column(String(20))
    email = Column(String(255))

    # Insurance - primary
    member_id = Column(String(80), nullable=False)  # Payer-assigned member/subscriber ID
    group_number = Column(String(50))
    payer_id = Column(Integer, index=True)  # FK to payer_profiles

    # Relationship to subscriber (for dependent claims)
    relationship_to_subscriber = Column(String(2), default="18")  # 18=Self, 01=Spouse, 19=Child
    subscriber_id = Column(Integer)  # Self-ref if patient IS subscriber

    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Patient(id={self.id}, name='{self.last_name}, {self.first_name}', member_id='{self.member_id}')>"
