"""
Payer-Specific Credentialing Models
Tracks provider enrollment with each individual payer
Integrates with existing provider verification system
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, Date, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base


class PayerCredentialingCase(Base):
    """
    Track provider credentialing with specific payer
    Created after provider passes initial verification
    One case per provider per payer
    """
    __tablename__ = "payer_credentialing_cases"
    __table_args__ = (
        Index("ix_payer_cred_cases_tenant_status", "tenant_id", "status"),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Links
    provider_id = Column(String(100), nullable=False, index=True)  # Links to provider_credentialing.provider_id
    payer_id = Column(Integer, ForeignKey('payer_profiles.id'), nullable=False, index=True)
    
    # Status workflow
    status = Column(String(50), default="draft", index=True)
    # States: "draft", "ready_to_submit", "submitted", "in_review", "additional_info_requested", "approved", "rejected", "resubmission_required"
    
    # Submission tracking
    submitted_date = Column(Date, index=True)
    submission_method = Column(String(50))  # "portal", "mail", "fax", "email"
    submission_tracking_number = Column(String(100))
    
    # Payer response
    effective_date = Column(Date, index=True)  # When credentialing becomes effective
    expiration_date = Column(Date, index=True)  # When re-credentialing needed
    
    # Payer contacts
    payer_rep_name = Column(String(200))
    payer_rep_email = Column(String(200))
    payer_rep_phone = Column(String(50))
    payer_rep_extension = Column(String(20))
    ticket_number = Column(String(100))  # Payer's internal ticket/case number
    
    # Payer-specific checklist
    # Example: [
    #   {"item": "W-9", "required": true, "completed": true, "doc_id": 123, "completed_date": "2024-01-15"},
    #   {"item": "License Copy", "required": true, "completed": true, "doc_id": 124},
    #   {"item": "Malpractice Insurance", "required": true, "completed": false},
    #   {"item": "CAQH Profile", "required": true, "completed": true, "caqh_id": "12345"},
    #   {"item": "Hospital Privileges", "required": false, "completed": null}
    # ]
    checklist = Column(JSON)
    
    # Checklist progress
    total_items = Column(Integer, default=0)
    completed_items = Column(Integer, default=0)
    completion_percentage = Column(Integer, default=0)
    
    # Response/feedback from payer
    payer_response_date = Column(Date)
    payer_response = Column(Text)
    additional_info_requested = Column(JSON)  # List of items payer needs
    rejection_reason = Column(Text)
    
    # Recredentialing
    requires_recredentialing = Column(Boolean, default=False)
    recredentialing_frequency_months = Column(Integer)  # How often to re-cred (e.g., 36 months)
    next_recredentialing_date = Column(Date, index=True)
    recredentialing_reminder_sent = Column(Boolean, default=False)
    
    # Communication log
    # Example: [
    #   {"date": "2024-01-10", "type": "email", "from": "ops@example.com", "to": "rep@payer.com", "subject": "Credentialing submission"},
    #   {"date": "2024-01-12", "type": "phone", "notes": "Followed up on missing W-9"}
    # ]
    communication_log = Column(JSON)
    
    # Internal notes
    notes = Column(Text)
    internal_status_notes = Column(Text)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String(100))
    updated_by = Column(String(100))
    
    # Assigned to
    assigned_to = Column(String(100), index=True)  # Ops person working this case
    
    def __repr__(self):
        return f"<PayerCredentialingCase(id={self.id}, provider_id='{self.provider_id}', payer_id={self.payer_id}, status='{self.status}')>"


class ERAEnrollmentCase(Base):
    """
    Track ERA/EFT enrollment separately from credentialing
    For receiving 835 electronic remittances
    """
    __tablename__ = "era_enrollment_cases"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Links
    provider_id = Column(String(100), nullable=False, index=True)
    payer_id = Column(Integer, ForeignKey('payer_profiles.id'), nullable=False, index=True)
    clearinghouse = Column(String(100))  # "Waystar", "Availity", etc.
    
    # Status workflow
    status = Column(String(50), default="pending", index=True)
    # States: "pending", "forms_submitted", "testing", "test_successful", "active", "failed", "inactive"
    
    # Enrollment dates
    enrollment_date = Column(Date)  # When submitted
    effective_date = Column(Date, index=True)  # When active
    tested_date = Column(Date)  # When test 835 received
    
    # Banking information (ENCRYPTED - sensitive!)
    bank_name = Column(String(200))
    routing_number_encrypted = Column(Text)  # Encrypted routing number
    account_number_encrypted = Column(Text)  # Encrypted account number
    account_type = Column(String(50))  # "checking", "savings"
    
    # EDI identifiers
    submitter_id = Column(String(50))  # Your submitter ID with clearinghouse
    receiver_id = Column(String(50))  # Payer's receiver ID for 835
    
    # Enrollment checklist
    # Example: [
    #   {"item": "Bank letter", "completed": true, "doc_id": 789},
    #   {"item": "Voided check", "completed": true, "doc_id": 790},
    #   {"item": "ERA enrollment form", "completed": true, "doc_id": 791},
    #   {"item": "Test 835 received", "completed": false}
    # ]
    checklist = Column(JSON)
    
    # Test 835 tracking
    test_835_file_id = Column(Integer, ForeignKey('edi_files.id'))  # Link to test 835 file
    test_835_received = Column(Boolean, default=False)
    test_835_date = Column(Date)
    test_835_amount = Column(String(20))  # Usually $0.01 test payment
    
    # Production tracking
    first_production_835_date = Column(Date)
    last_835_received_date = Column(Date)
    total_835_files_received = Column(Integer, default=0)
    
    # Notes
    notes = Column(Text)
    submission_notes = Column(Text)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String(100))
    assigned_to = Column(String(100))
    
    def __repr__(self):
        return f"<ERAEnrollmentCase(id={self.id}, provider_id='{self.provider_id}', payer_id={self.payer_id}, status='{self.status}')>"


class ProviderDocument(Base):
    """
    Secure document vault for provider credentialing documents
    Supports versioning and expiration tracking
    """
    __tablename__ = "provider_documents"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Provider link
    provider_id = Column(String(100), nullable=False, index=True)
    
    # Document classification
    document_type = Column(String(100), nullable=False, index=True)
    # Types: "w9", "license", "dea", "malpractice", "caqh_profile", "hospital_privileges", 
    #        "board_certification", "cv", "references", "disclosure_form", "clia_certificate"
    document_name = Column(String(500), nullable=False)
    description = Column(Text)
    
    # File information
    file_path = Column(String(1000), nullable=False)  # Secure storage path
    file_size = Column(Integer)
    mime_type = Column(String(100))
    original_filename = Column(String(500))
    
    # Versioning
    version = Column(Integer, default=1)
    parent_document_id = Column(Integer, ForeignKey('provider_documents.id'))  # For tracking versions
    is_latest_version = Column(Boolean, default=True, index=True)
    
    # Expiration tracking
    issue_date = Column(Date)
    expiration_date = Column(Date, index=True)
    days_until_expiration = Column(Integer)  # Computed for alerts
    renewal_reminder_sent = Column(Boolean, default=False)
    
    # Verification status
    is_verified = Column(Boolean, default=False)
    verified_by = Column(String(100))
    verified_at = Column(DateTime)
    
    # Links to cases
    credentialing_case_id = Column(Integer, ForeignKey('payer_credentialing_cases.id'))
    era_enrollment_case_id = Column(Integer, ForeignKey('era_enrollment_cases.id'))
    
    # Encryption (for sensitive docs)
    is_encrypted = Column(Boolean, default=True)
    encryption_key_id = Column(String(100))
    
    # State-specific (if document is state-specific)
    state_code = Column(String(2), index=True)
    
    # Metadata
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    uploaded_by = Column(String(100))
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Tags for organization
    tags = Column(JSON)  # ["credentialing", "active", "urgent"]
    
    # Relationships
    versions = relationship("ProviderDocument", remote_side=[parent_document_id])
    
    def __repr__(self):
        return f"<ProviderDocument(id={self.id}, type='{self.document_type}', provider_id='{self.provider_id}', version={self.version})>"


class CredentialingRenewal(Base):
    """
    Track recurring credentialing renewals and expirations
    Auto-creates tasks when renewals are due
    """
    __tablename__ = "credentialing_renewals"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Links
    credentialing_case_id = Column(Integer, ForeignKey('payer_credentialing_cases.id'), nullable=False, index=True)
    provider_id = Column(String(100), nullable=False, index=True)
    payer_id = Column(Integer, ForeignKey('payer_profiles.id'), nullable=False)
    
    # Renewal schedule
    renewal_type = Column(String(50))  # "credentialing", "license", "malpractice", "dea"
    renewal_frequency_months = Column(Integer)  # How often to renew
    
    # Dates
    current_expiration_date = Column(Date, nullable=False, index=True)
    next_renewal_start_date = Column(Date, index=True)  # When to start renewal process
    
    # Reminders
    reminder_1_sent = Column(Boolean, default=False)  # 90 days before
    reminder_1_date = Column(Date)
    reminder_2_sent = Column(Boolean, default=False)  # 60 days before
    reminder_2_date = Column(Date)
    reminder_3_sent = Column(Boolean, default=False)  # 30 days before
    reminder_3_date = Column(Date)
    urgent_alert_sent = Column(Boolean, default=False)  # 14 days before
    
    # Status
    renewal_initiated = Column(Boolean, default=False)
    renewal_completed = Column(Boolean, default=False)
    renewal_completed_date = Column(Date)
    
    # New expiration after renewal
    new_expiration_date = Column(Date)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<CredentialingRenewal(id={self.id}, provider_id='{self.provider_id}', payer_id={self.payer_id}, expires='{self.current_expiration_date}')>"

