"""
Denial Management Models
CARC/RARC code mapping, appeal tracking, and denial analytics
"""

from sqlalchemy import Column, Integer, String, Text, Numeric, Boolean, Date, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base


class DenialCase(Base):
    """
    Denial management and appeal tracking
    Created automatically when 835 contains denial codes
    """
    __tablename__ = "denial_cases"
    __table_args__ = (
        Index("ix_denial_cases_tenant_status", "tenant_id", "status"),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Related claim
    claim_id = Column(Integer, ForeignKey('claims.id'), nullable=False, index=True)
    claim_line_id = Column(Integer, ForeignKey('claim_lines.id'), index=True)  # Specific line if partial denial
    
    # Denial codes
    carc_code = Column(String(20), nullable=False, index=True)  # Claim Adjustment Reason Code (e.g., "CO-16")
    rarc_code = Column(String(20), index=True)  # Remittance Advice Remark Code (e.g., "M51")
    denial_description = Column(Text)
    
    # Categorization (auto-assigned from CARC/RARC mapping)
    denial_category = Column(String(100), index=True)  # "coding_error", "medical_policy", "missing_info", "timely_filing"
    denial_subcategory = Column(String(100))
    
    # Financial impact
    denied_amount = Column(Numeric(10, 2), nullable=False)
    
    # Case management
    status = Column(String(50), default="new", index=True)  # "new", "in_review", "appeal_drafted", "appeal_submitted", "won", "lost", "closed"
    assigned_to = Column(String(100), index=True)  # User assigned to work this
    priority = Column(String(20), default="medium")  # "low", "medium", "high", "critical"
    
    # Deadlines
    appeal_due_date = Column(Date, index=True)  # Auto-calculated from payer appeal window
    days_until_due = Column(Integer)  # Computed for SLA alerts
    
    # Appeal information
    playbook_id = Column(Integer, ForeignKey('denial_playbooks.id'))  # Auto-assigned based on CARC/RARC
    appeal_letter_generated = Column(Boolean, default=False)
    appeal_letter_path = Column(String(1000))
    appeal_submitted_date = Column(Date)
    appeal_submission_method = Column(String(50))  # "portal", "fax", "mail"
    appeal_tracking_number = Column(String(100))
    
    # Response
    appeal_response_date = Column(Date)
    appeal_won = Column(Boolean)
    appeal_recovery_amount = Column(Numeric(10, 2))
    
    # Root cause
    root_cause = Column(Text)  # Human-entered analysis
    preventable = Column(Boolean)  # Could this have been prevented with better rules?
    suggested_rule_update = Column(Text)  # Recommendation for payer profile rule
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    closed_at = Column(DateTime)
    created_by = Column(String(100))
    
    # Relationships
    playbook = relationship("DenialPlaybook", foreign_keys=[playbook_id])
    
    def __repr__(self):
        return f"<DenialCase(id={self.id}, claim_id={self.claim_id}, carc='{self.carc_code}', status='{self.status}')>"


class DenialPlaybook(Base):
    """
    Templated response strategies for denial types
    Maps CARC/RARC codes to appeal templates and required documentation
    """
    __tablename__ = "denial_playbooks"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Denial identification
    carc_code = Column(String(20), index=True)
    rarc_code = Column(String(20), index=True)
    denial_category = Column(String(100), index=True)
    
    # Playbook info
    playbook_name = Column(String(200), nullable=False)
    description = Column(Text)
    
    # Appeal strategy
    appeal_template_id = Column(Integer, ForeignKey('appeal_templates.id'))
    required_attachments = Column(JSON)  # ["medical_records", "prior_auth", "modifier_justification"]
    submission_method = Column(String(50))  # "portal", "fax", "mail"
    submission_address = Column(Text)  # Where to send appeal
    submission_fax = Column(String(50))
    submission_portal_url = Column(String(500))
    
    # Success metrics
    typical_turnaround_days = Column(Integer)
    success_rate = Column(Numeric(5, 2))  # Historical win rate (e.g., 75.50%)
    total_appeals = Column(Integer, default=0)
    won_appeals = Column(Integer, default=0)
    
    # Instructions for staff
    staff_instructions = Column(Text)  # Step-by-step guide
    common_pitfalls = Column(JSON)  # List of things to watch out for
    
    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    appeal_template = relationship("AppealTemplate", foreign_keys=[appeal_template_id])
    
    def __repr__(self):
        return f"<DenialPlaybook(id={self.id}, carc='{self.carc_code}', category='{self.denial_category}')>"


class AppealTemplate(Base):
    """
    Appeal letter templates with merge fields
    Generate customized appeals automatically
    """
    __tablename__ = "appeal_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Template info
    template_name = Column(String(200), nullable=False)
    template_type = Column(String(100))  # "appeal_letter", "missing_info_request", "reconsideration"
    description = Column(Text)
    
    # Content
    subject = Column(String(500))
    body = Column(Text, nullable=False)  # With merge fields: {{patient_name}}, {{claim_number}}, {{service_date}}
    
    # Merge fields available
    available_merge_fields = Column(JSON)  # List of fields that can be used
    
    # Formatting
    letterhead_template = Column(String(100))  # Which letterhead to use
    signature_block = Column(Text)
    
    # Usage tracking
    times_used = Column(Integer, default=0)
    
    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String(100))
    
    def __repr__(self):
        return f"<AppealTemplate(id={self.id}, name='{self.template_name}')>"


class CARCCode(Base):
    """
    Reference table for Claim Adjustment Reason Codes
    Used to auto-categorize denials
    """
    __tablename__ = "carc_codes"
    
    id = Column(Integer, primary_key=True, index=True)
    
    code = Column(String(20), unique=True, nullable=False, index=True)  # "CO-16", "PR-1", "OA-23"
    description = Column(Text, nullable=False)
    
    # Auto-categorization
    category = Column(String(100), index=True)  # "coding_error", "medical_policy", "missing_info", etc.
    subcategory = Column(String(100))
    
    # Routing
    default_queue = Column(String(100))  # Where to route denials with this code
    
    # Appeal guidance
    is_appealable = Column(Boolean, default=True)
    typical_success_rate = Column(Numeric(5, 2))
    common_resolution = Column(Text)  # How to fix this
    
    # References
    cms_reference_url = Column(String(500))
    
    def __repr__(self):
        return f"<CARCCode(code='{self.code}', category='{self.category}')>"


class RARCCode(Base):
    """
    Reference table for Remittance Advice Remark Codes
    Provides additional context for denials
    """
    __tablename__ = "rarc_codes"
    
    id = Column(Integer, primary_key=True, index=True)
    
    code = Column(String(20), unique=True, nullable=False, index=True)  # "M51", "N522", etc.
    description = Column(Text, nullable=False)
    
    # Categorization
    category = Column(String(100))
    
    # Additional guidance
    resolution_guidance = Column(Text)
    
    def __repr__(self):
        return f"<RARCCode(code='{self.code}')>"

