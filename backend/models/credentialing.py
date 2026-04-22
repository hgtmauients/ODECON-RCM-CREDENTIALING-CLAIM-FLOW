"""
Provider Credentialing Models
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship
from datetime import datetime
from models.base import Base

class ProviderCredentialing(Base):
    __tablename__ = "provider_credentialing"
    __table_args__ = (
        Index("ix_provider_cred_tenant_provider", "tenant_id", "provider_id", unique=True),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    provider_id = Column(String(100), nullable=False, index=True)
    
    # Signup Info
    signup_data = Column(JSON, nullable=False)
    license_url = Column(String(255))
    signup_date = Column(DateTime, default=datetime.utcnow)

    # Multi-state licenses: [{"state": "HI", "license_number": "MD-21277", "expiration": "2026-12-31", "status": "active"}]
    licenses = Column(JSON, default=list)
    # Specialties: [{"specialty": "Psychiatry", "board": "ABPN", "certified": true, "expiration": "2028-06-30"}]
    specialties = Column(JSON, default=list)
    # DEA: [{"dea_number": "BH1234567", "state": "HI", "schedules": ["II","III","IV","V"], "expiration": "2027-06-30"}]
    dea_certificates = Column(JSON, default=list)
    # CNED (Controlled substance / Narcotics Enforcement Division): [{"state": "HI", "certificate_number": "CNED-1234", "expiration": "2026-12-31"}]
    cned_certificates = Column(JSON, default=list)

    # Verification Results
    npi_verification = Column(JSON)
    state_license_verification = Column(JSON)
    specialty_board_verification = Column(JSON)
    background_check = Column(JSON)
    oig_check = Column(JSON)
    sam_check = Column(JSON)
    
    # Overall Status
    credentialing_status = Column(String(50), default='pending')  # pending, in_progress, passed, failed, requires_review
    overall_score = Column(Integer)  # 0-100
    
    # Dates
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    verified_by = Column(String(100))
    verified_at = Column(DateTime)
    
    # Notes
    admin_notes = Column(Text)
    rejection_reason = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CredentialingVerificationLog(Base):
    __tablename__ = "credentialing_verification_log"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    provider_id = Column(String(100), nullable=False, index=True)
    verification_type = Column(String(50), nullable=False)  # npi, state_license, background, oig, sam
    status = Column(String(50), nullable=False)  # success, failed, error
    result = Column(JSON)
    api_response = Column(JSON)
    error_message = Column(Text)
    verified_at = Column(DateTime, default=datetime.utcnow)

