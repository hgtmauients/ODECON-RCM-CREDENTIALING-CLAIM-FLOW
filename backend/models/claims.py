"""
Claims State Machine & Event Log
Full claims lifecycle tracking with append-only event stream
"""

from sqlalchemy import Column, Integer, String, Text, Numeric, Boolean, Date, DateTime, ForeignKey, JSON, Enum as SQLEnum, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
import enum

from models.base import Base


class ClaimState(str, enum.Enum):
    """Claim lifecycle states"""
    DRAFT = "draft"  # Being created
    VALIDATED = "validated"  # Passed validation rules
    READY_TO_SUBMIT = "ready_to_submit"  # In submission queue
    SUBMITTED = "submitted"  # Sent to clearinghouse/payer
    ACCEPTED = "accepted"  # 277CA acknowledgment received
    REJECTED = "rejected"  # 277 rejection received
    ADJUDICATED = "adjudicated"  # 835 received (paid or denied)
    PAID = "paid"  # Full payment received
    PARTIALLY_PAID = "partially_paid"  # Partial payment
    DENIED = "denied"  # Fully denied
    APPEALED = "appealed"  # Appeal submitted
    APPEAL_WON = "appeal_won"  # Appeal successful
    APPEAL_LOST = "appeal_lost"  # Appeal denied
    VOID = "void"  # Voided
    CORRECTED = "corrected"  # Corrected claim submitted


class Claim(Base):
    """
    Claim with state machine
    Tracks full lifecycle from creation to payment
    """
    __tablename__ = "claims"
    __table_args__ = (
        Index("ix_claims_tenant_state", "tenant_id", "state"),
        Index("ix_claims_tenant_service_date", "tenant_id", "service_date_from"),
        Index("ix_claims_tenant_claim_number", "tenant_id", "claim_number", unique=True),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Claim identifiers
    claim_number = Column(String(50), nullable=False, index=True)  # Internal claim number
    payer_claim_id = Column(String(100), index=True)  # Payer's claim ID (from 277)
    original_claim_id = Column(Integer, ForeignKey('claims.id'))  # For corrected claims
    
    # Relationships
    patient_id = Column(Integer, index=True)  # Link to patient
    provider_id = Column(Integer, index=True)  # Link to provider
    payer_id = Column(Integer, nullable=True, index=True)  # Removed FK constraint - will link when payer_profiles exists
    facility_id = Column(Integer)  # Link to facility/location
    
    # State machine
    state = Column(SQLEnum(ClaimState), nullable=False, default=ClaimState.DRAFT, index=True)
    previous_state = Column(SQLEnum(ClaimState))
    current_queue = Column(String(100), index=True)  # "ready_to_submit", "auth_required", "denied_coding"
    
    # Service dates
    service_date_from = Column(Date, nullable=False, index=True)
    service_date_to = Column(Date)
    
    # Claim dates
    created_date = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    validated_date = Column(DateTime)
    submitted_date = Column(DateTime, index=True)
    adjudicated_date = Column(DateTime)
    paid_date = Column(DateTime)
    
    # Amounts
    total_charges = Column(Numeric(10, 2), nullable=False)
    total_allowed = Column(Numeric(10, 2))
    total_paid = Column(Numeric(10, 2))
    patient_responsibility = Column(Numeric(10, 2))
    adjustment_amount = Column(Numeric(10, 2))
    
    # Claim type
    claim_type = Column(String(50))  # "professional", "institutional"
    claim_frequency_code = Column(String(5), default="1")  # 1=original, 7=corrected, 8=void
    billing_provider_npi = Column(String(10), index=True)
    rendering_provider_npi = Column(String(10))
    
    # Prior authorization
    prior_auth_number = Column(String(100))
    requires_prior_auth = Column(Boolean, default=False)
    auth_obtained = Column(Boolean, default=False)
    
    # Timely filing
    filing_deadline = Column(Date, index=True)  # Auto-calculated from service date + payer filing limit
    days_until_filing_deadline = Column(Integer)  # Computed field for SLA alerts
    
    # Flags (from rules engine)
    flags = Column(JSON)  # {"telehealth_parity": true, "requires_attachment": true}
    
    # Submission tracking
    submission_method = Column(String(50))  # "electronic", "paper", "portal"
    clearinghouse_id = Column(String(100))
    interchange_control_number = Column(String(50))  # 837P file ICN
    batch_id = Column(String(100), index=True)  # Submission batch
    
    # Denial info (if denied)
    denial_reason = Column(Text)
    denial_category = Column(String(100))  # "coding_error", "medical_policy", "missing_info"
    appeal_due_date = Column(Date)
    
    # Metadata
    created_by = Column(String(100))
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    notes = Column(Text)
    
    # Relationships
    lines = relationship("ClaimLine", back_populates="claim", cascade="all, delete-orphan")
    events = relationship("ClaimEvent", back_populates="claim", cascade="all, delete-orphan", order_by="ClaimEvent.timestamp")
    diagnosis_codes = relationship("ClaimDiagnosis", back_populates="claim", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Claim(id={self.id}, number='{self.claim_number}', state='{self.state}')>"


class ClaimLine(Base):
    """
    Individual line items on a claim
    Each service/procedure is a separate line
    """
    __tablename__ = "claim_lines"
    
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey('claims.id'), nullable=False, index=True)
    
    line_number = Column(Integer, nullable=False)  # Sequence on claim
    
    # Procedure code
    cpt_code = Column(String(10), nullable=False, index=True)
    cpt_description = Column(Text)
    modifiers = Column(JSON)  # ["95", "26"]
    
    # Diagnosis pointers
    diagnosis_pointers = Column(JSON)  # [1, 2] - points to claim diagnosis codes
    
    # Service details
    service_date = Column(Date)
    units = Column(Integer, default=1)
    place_of_service = Column(String(5))  # POS code
    
    # Amounts
    charge_amount = Column(Numeric(10, 2), nullable=False)
    allowed_amount = Column(Numeric(10, 2))
    paid_amount = Column(Numeric(10, 2))
    patient_responsibility = Column(Numeric(10, 2))
    adjustment_amount = Column(Numeric(10, 2))
    
    # Denial info (if denied)
    is_denied = Column(Boolean, default=False)
    carc_code = Column(String(20))  # Claim Adjustment Reason Code
    rarc_code = Column(String(20))  # Remittance Advice Remark Code
    denial_description = Column(Text)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    claim = relationship("Claim", back_populates="lines")
    
    def __repr__(self):
        return f"<ClaimLine(id={self.id}, claim_id={self.claim_id}, cpt='{self.cpt_code}')>"


class ClaimDiagnosis(Base):
    """
    Diagnosis codes on a claim
    Separate table for proper normalization
    """
    __tablename__ = "claim_diagnoses"
    
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey('claims.id'), nullable=False, index=True)
    
    diagnosis_pointer = Column(Integer, nullable=False)  # 1, 2, 3...
    icd10_code = Column(String(10), nullable=False, index=True)
    icd10_description = Column(Text)
    is_primary = Column(Boolean, default=False)  # First diagnosis
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    claim = relationship("Claim", back_populates="diagnosis_codes")
    
    def __repr__(self):
        return f"<ClaimDiagnosis(claim_id={self.claim_id}, icd10='{self.icd10_code}')>"


class ClaimEvent(Base):
    """
    Append-only event log for claim
    Every state change, file received, note added is an event
    """
    __tablename__ = "claim_events"
    
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey('claims.id'), nullable=False, index=True)
    
    # Event metadata
    event_type = Column(String(50), nullable=False, index=True)  # "state_changed", "277ca_received", "835_received", "note_added", "submitted_to_clearinghouse"
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id = Column(String(100))  # Who triggered (null for automated events)
    
    # State change tracking
    from_state = Column(String(50))
    to_state = Column(String(50))
    
    # Event data (JSON for flexibility)
    # Examples:
    # {"tracking_number": "12345"} for submission
    # {"payer_claim_id": "ABC123", "status": "Accepted"} for 277
    # {"payment_amount": 150.00, "carc": "CO-45"} for 835
    data = Column(JSON)
    
    # Associated file
    edi_file_id = Column(Integer, ForeignKey('edi_files.id'))
    document_id = Column(Integer)  # Link to document vault
    
    # Message/notes
    message = Column(Text)
    
    # Relationships
    claim = relationship("Claim", back_populates="events")
    edi_file = relationship("EDIFile", foreign_keys=[edi_file_id])
    
    def __repr__(self):
        return f"<ClaimEvent(claim_id={self.claim_id}, type='{self.event_type}', timestamp='{self.timestamp}')>"


class EDIFile(Base):
    """
    837P/837I/270/271/276/277CA/835 files
    Tracks all EDI files sent and received
    """
    __tablename__ = "edi_files"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # File classification
    file_type = Column(String(10), nullable=False, index=True)  # "837P", "837I", "270", "271", "276", "277CA", "835"
    direction = Column(String(10), nullable=False, index=True)  # "outbound", "inbound"
    
    # File info
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)  # Secure storage path
    file_size = Column(Integer)
    
    # EDI control numbers
    interchange_control_number = Column(String(50), index=True)  # ISA13
    group_control_number = Column(String(50))  # GS06
    transaction_count = Column(Integer)  # Number of transactions in file
    
    # Related entities
    payer_id = Column(Integer, ForeignKey('payer_profiles.id'), index=True)
    batch_id = Column(String(100), index=True)
    
    # Processing status
    status = Column(String(50), nullable=False, default="pending", index=True)  # "pending", "processing", "processed", "error"
    processed_at = Column(DateTime)
    error_message = Column(Text)
    validation_errors = Column(JSON)  # List of validation errors
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    created_by = Column(String(100))
    
    def __repr__(self):
        return f"<EDIFile(id={self.id}, type='{self.file_type}', direction='{self.direction}', filename='{self.filename}')>"


class ClaimQueue(Base):
    """
    Work queues for claim management
    Routes claims based on status and rules
    """
    __tablename__ = "claim_queues"
    __table_args__ = (
        Index("ix_claim_queues_tenant_name", "tenant_id", "name", unique=True),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Queue identity
    name = Column(String(200), nullable=False, index=True)  # "ready_to_submit", "auth_required"
    display_name = Column(String(200))
    description = Column(Text)
    queue_type = Column(String(100))  # "claims", "denials", "auth", "appeals"
    
    # Assignment
    auto_assign_role = Column(String(100))  # "billing", "coding", "clinical"
    load_balancing = Column(Boolean, default=True)
    
    # SLA
    default_sla_hours = Column(Integer)  # Default time to work item
    escalation_sla_hours = Column(Integer)  # When to escalate
    
    # Notification rules
    notification_rules = Column(JSON)  # Who to notify when items enter queue
    escalation_rules = Column(JSON)  # Escalation path when SLA missed
    
    # Visual
    color = Column(String(20))  # Queue color in Kanban view
    icon = Column(String(50))  # Icon name
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<ClaimQueue(id={self.id}, name='{self.name}')>"


class ClaimValidation(Base):
    """
    Validation results from rules engine
    Tracks which rules passed/failed for each claim
    """
    __tablename__ = "claim_validations"
    
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey('claims.id'), nullable=False, index=True)
    
    # Validation metadata
    validated_at = Column(DateTime(timezone=True), server_default=func.now())
    validation_version = Column(String(50))  # Rules engine version
    
    # Results
    passed = Column(Boolean, nullable=False)
    errors = Column(JSON)  # List of validation errors
    warnings = Column(JSON)  # List of warnings
    
    # Rules applied
    rules_evaluated = Column(Integer)  # How many rules ran
    rules_matched = Column(Integer)  # How many matched
    actions_executed = Column(JSON)  # List of actions taken
    
    # Flags set by rules
    flags_set = Column(JSON)  # Flags added by rules
    modifiers_added = Column(JSON)  # Modifiers added by rules
    
    def __repr__(self):
        return f"<ClaimValidation(claim_id={self.claim_id}, passed={self.passed})>"

