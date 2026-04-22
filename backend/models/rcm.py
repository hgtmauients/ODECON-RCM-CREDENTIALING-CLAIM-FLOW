"""
Revenue Cycle Management (RCM) Database Models
Comprehensive models for payer profiles, rules, credentials, and RCM workflows
"""

from sqlalchemy import Column, Integer, String, Text, Numeric, Boolean, Date, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base


class PayerProfile(Base):
    """
    First-class payer entity - fully editable in admin UI
    No code changes needed to add/modify payers
    """
    __tablename__ = "payer_profiles"
    __table_args__ = (
        Index("ix_payer_profiles_tenant_name", "tenant_id", "name"),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # ===== IDENTITY =====
    name = Column(String(200), nullable=False, index=True)  # "HMSA", "UHA", "Quest/Medicaid"
    display_name = Column(String(200))  # "Hawaii Medical Service Association"
    payer_id = Column(String(50), index=True)  # For 837P submissions
    naic_code = Column(String(20))  # National Association of Insurance Commissioners code
    plan_ids = Column(JSON)  # Multiple plan IDs: ["HMSA-QUEST", "HMSA-PPO"]
    
    # ===== CONNECTIVITY =====
    clearinghouse = Column(String(100))  # "Waystar", "Availity", "Office Ally", "Change Healthcare"
    trading_partner_id = Column(String(50))  # Clearinghouse-specific TP ID
    submitter_id = Column(String(50))  # Your submitter ID
    receiver_id = Column(String(50))  # Payer receiver ID
    
    connection_method = Column(String(50))  # "clearinghouse", "sftp", "api", "portal"
    endpoint_url = Column(String(500))  # API or SFTP endpoint
    
    # ===== FORMATS & RULES =====
    format_837_type = Column(String(10))  # "837I" (institutional) or "837P" (professional)
    loop_segment_overrides = Column(JSON)  # Custom loop/segment requirements
    
    # Attachments
    supports_pwk_attachments = Column(Boolean, default=False)  # PWK segment for attachments
    attachment_method = Column(String(50))  # "embedded", "separate_file", "portal"
    
    # Telehealth
    supports_telehealth = Column(Boolean, default=False)
    telehealth_modifiers = Column(JSON)  # ["95", "GT", "FQ"]
    telehealth_pos_codes = Column(JSON)  # ["02", "10"]
    telehealth_parity = Column(Boolean, default=False)  # Pays same as in-person
    
    # Requirements
    requires_taxonomy = Column(Boolean, default=True)
    requires_npi_type_2 = Column(Boolean, default=False)
    requires_tin = Column(Boolean, default=True)
    requires_clia = Column(Boolean, default=False)  # Clinical Laboratory Improvement Amendments
    
    # Facility vs. Professional
    facility_professional_split = Column(String(50))  # "separate", "combined", "facility_only"
    
    # ===== ELIGIBILITY/STATUS/AUTH =====
    supports_270_271 = Column(Boolean, default=True)  # Real-time eligibility
    supports_276_277 = Column(Boolean, default=True)  # Claim status
    supports_278_auth = Column(Boolean, default=False)  # Prior authorization
    auth_portal_url = Column(String(500))  # If portal-only for auth
    auth_portal_login_required = Column(Boolean, default=False)
    
    # ===== ERA/EFT =====
    supports_835_era = Column(Boolean, default=True)  # Electronic Remittance Advice
    era_enrollment_required = Column(Boolean, default=True)
    era_enrollment_url = Column(String(500))
    era_enrollment_forms = Column(JSON)  # List of required forms
    
    eft_enrollment_required = Column(Boolean, default=False)
    eft_enrollment_url = Column(String(500))
    eft_banking_docs = Column(JSON)  # ["Voided check", "Bank letter"]
    
    # ===== SLAs & DEADLINES =====
    filing_limit_days = Column(Integer, default=365)  # Timely filing limit
    filing_limit_from = Column(String(50), default="service_date")  # "service_date" or "discharge_date"
    
    auth_response_days = Column(Integer, default=14)  # Days to get auth response
    appeal_window_days = Column(Integer, default=180)  # Days to file appeal after denial
    audit_response_days = Column(Integer, default=14)  # Days to respond to medical record request
    
    # ===== CONTRACT INFO =====
    has_contract = Column(Boolean, default=False)
    contract_type = Column(String(50))  # "direct", "network", "non_par"
    contract_effective_date = Column(Date)
    contract_end_date = Column(Date)
    contract_notes = Column(Text)
    
    # ===== CLAIM FREQUENCY CODES =====
    supports_corrected_claims = Column(Boolean, default=True)
    corrected_claim_frequency_code = Column(String(5), default="7")  # Usually "7" for corrected
    void_claim_frequency_code = Column(String(5), default="8")  # Usually "8" for void
    
    # Secondary claims (COB - Coordination of Benefits)
    accepts_secondary_claims = Column(Boolean, default=True)
    secondary_claim_requirements = Column(JSON)  # Special requirements for COB
    
    # ===== PAPER FALLBACK =====
    paper_claim_supported = Column(Boolean, default=True)
    paper_claim_address = Column(Text)  # Mailing address
    paper_claim_fax = Column(String(50))
    
    # ===== NOTIFICATIONS =====
    notification_rules = Column(JSON)  # Who to notify for what events
    escalation_rules = Column(JSON)  # Escalation paths for missed SLAs
    
    # ===== STATE-SPECIFIC =====
    state_code = Column(String(2), index=True)  # If state-specific (e.g., "HI" for HMSA)
    state_specific_requirements = Column(JSON)  # State-mandated requirements
    
    # ===== METADATA =====
    is_active = Column(Boolean, default=True, index=True)
    payer_status = Column(String(20), default="active")  # "active", "testing", "disabled"
    version = Column(Integer, default=1)
    is_draft = Column(Boolean, default=True)  # Draft -> Publish workflow
    published_at = Column(DateTime)
    last_era_received = Column(DateTime)  # Last 835 received from this payer
    supported_modifiers = Column(JSON)  # ["95", "GT", "GQ", "25", "59"]
    edi_version = Column(String(30), default="005010X222A1")  # X12 implementation guide version
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String(100))  # User who created
    updated_by = Column(String(100))  # User who last updated
    
    notes = Column(Text)  # General notes for ops team
    
    # ===== RELATIONSHIPS =====
    rules = relationship("PayerRule", back_populates="payer", cascade="all, delete-orphan")
    connections = relationship("TradingPartnerConnection", back_populates="payer", cascade="all, delete-orphan")
    fee_schedules = relationship("FeeSchedule", back_populates="payer", cascade="all, delete-orphan")
    credentials = relationship("PayerCredential", back_populates="payer", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<PayerProfile(id={self.id}, name='{self.name}', version={self.version})>"


class PayerRule(Base):
    """
    Decision table rules - ops can edit in visual rule builder
    Applied to claims before submission to ensure payer compliance
    """
    __tablename__ = "payer_rules"
    
    id = Column(Integer, primary_key=True, index=True)
    payer_id = Column(Integer, ForeignKey('payer_profiles.id'), nullable=False, index=True)
    
    # Rule metadata
    rule_name = Column(String(200), nullable=False)
    description = Column(Text)
    priority = Column(Integer, default=0)  # Higher = runs first
    
    # Conditions (JSON for flexibility)
    # Example: {"cpt_codes": ["99214", "99215"], "pos": ["02", "10"], "state": "HI", "telehealth": true}
    conditions = Column(JSON, nullable=False)
    
    # Actions (JSON)
    # Example: {"add_modifiers": ["95"], "require_auth": true, "route_to_queue": "telehealth", "set_flags": ["telehealth_parity"]}
    actions = Column(JSON, nullable=False)
    
    # Rule status
    is_active = Column(Boolean, default=True, index=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String(100))
    updated_by = Column(String(100))
    
    # Relationships
    payer = relationship("PayerProfile", back_populates="rules")
    
    def __repr__(self):
        return f"<PayerRule(id={self.id}, name='{self.rule_name}', payer_id={self.payer_id})>"


class TradingPartnerConnection(Base):
    """
    Clearinghouse/EDI connection details
    Credentials stored encrypted - ops enter directly in UI
    """
    __tablename__ = "trading_partner_connections"
    
    id = Column(Integer, primary_key=True, index=True)
    payer_id = Column(Integer, ForeignKey('payer_profiles.id'), nullable=False, index=True)
    
    # Connection identity
    connection_name = Column(String(200))  # "Waystar - HMSA", "Availity - Quest"
    clearinghouse_name = Column(String(100))  # "Waystar", "Availity", "Office Ally"
    connection_type = Column(String(50))  # "sftp", "api", "web_portal"
    
    # ===== SFTP DETAILS (if connection_type = "sftp") =====
    sftp_host = Column(String(200))
    sftp_port = Column(Integer, default=22)
    sftp_username = Column(String(100))
    sftp_password_encrypted = Column(Text)  # Encrypted password
    sftp_private_key_encrypted = Column(Text)  # Encrypted SSH private key (if key-based auth)
    sftp_inbound_path = Column(String(500))  # Where to pick up 277/835 files
    sftp_outbound_path = Column(String(500))  # Where to drop 837P files
    
    # ===== API DETAILS (if connection_type = "api") =====
    api_endpoint = Column(String(500))
    api_version = Column(String(50))
    api_key_encrypted = Column(Text)  # Encrypted API key
    api_secret_encrypted = Column(Text)  # Encrypted API secret
    api_token_encrypted = Column(Text)  # Encrypted access token
    api_auth_method = Column(String(50))  # "bearer", "basic", "oauth2"
    
    # OAuth2 specific
    oauth2_client_id = Column(String(200))
    oauth2_client_secret_encrypted = Column(Text)
    oauth2_token_url = Column(String(500))
    oauth2_scope = Column(String(500))
    
    # ===== WEB PORTAL DETAILS (if connection_type = "web_portal") =====
    portal_url = Column(String(500))
    portal_username = Column(String(100))
    portal_password_encrypted = Column(Text)  # Encrypted portal password
    portal_requires_mfa = Column(Boolean, default=False)
    portal_rpa_script_id = Column(String(100))  # If using RPA automation
    
    # ===== FILE NAMING & FORMATTING =====
    file_name_pattern = Column(String(200))  # "claim_{date}_{batch}.837p"
    file_extension = Column(String(10), default=".x12")
    use_compression = Column(Boolean, default=False)
    compression_type = Column(String(20))  # "gzip", "zip"
    
    # ===== CONNECTION METADATA =====
    is_active = Column(Boolean, default=True)
    last_tested = Column(DateTime)
    last_test_status = Column(String(50))  # "success", "failed"
    last_test_message = Column(Text)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String(100))
    
    # Relationships
    payer = relationship("PayerProfile", back_populates="connections")
    
    def __repr__(self):
        return f"<TradingPartnerConnection(id={self.id}, clearinghouse='{self.clearinghouse_name}', type='{self.connection_type}')>"


class PayerCredential(Base):
    """
    Encrypted credentials for payer portals/APIs
    Ops enter directly in UI - stored encrypted
    """
    __tablename__ = "payer_credentials"
    
    id = Column(Integer, primary_key=True, index=True)
    payer_id = Column(Integer, ForeignKey('payer_profiles.id'), nullable=False, index=True)
    
    # Credential metadata
    credential_type = Column(String(50))  # "portal_login", "api_key", "sftp", "clearinghouse"
    credential_name = Column(String(200))  # "HMSA Portal Login", "Waystar API Key"
    
    # Encrypted values (stored as JSON with encryption)
    # Example: {"username": "encrypted_value", "password": "encrypted_value", "api_key": "encrypted_value"}
    encrypted_data = Column(Text, nullable=False)
    
    # Encryption metadata
    encryption_key_id = Column(String(100))  # Which key was used to encrypt
    encryption_algorithm = Column(String(50), default="AES-256-GCM")
    
    # Expiration & rotation
    expires_at = Column(DateTime)  # If credentials expire
    rotation_required = Column(Boolean, default=False)
    rotation_frequency_days = Column(Integer)  # How often to rotate
    last_rotated = Column(DateTime)
    
    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String(100))
    
    # Relationships
    payer = relationship("PayerProfile", back_populates="credentials")
    
    def __repr__(self):
        return f"<PayerCredential(id={self.id}, type='{self.credential_type}', name='{self.credential_name}')>"


class FeeSchedule(Base):
    """
    Payer-specific fee schedules - uploadable via CSV
    """
    __tablename__ = "fee_schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    payer_id = Column(Integer, ForeignKey('payer_profiles.id'), nullable=False, index=True)
    
    # Location
    state_code = Column(String(2), index=True)
    locality = Column(String(20))  # Medicare locality code
    
    # Code
    cpt_code = Column(String(10), nullable=False, index=True)
    description = Column(Text)
    
    # Rate
    allowable_amount = Column(Numeric(10, 2), nullable=False)
    facility_rate = Column(Numeric(10, 2))  # If different from non-facility
    non_facility_rate = Column(Numeric(10, 2))
    
    # Effective dates
    effective_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date)
    
    # Modifiers affect rate
    modifier_adjustments = Column(JSON)  # {"26": 0.7, "TC": 0.3, "50": 1.5}
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    uploaded_by = Column(String(100))
    upload_batch_id = Column(String(100))  # Track bulk uploads
    
    # Relationships
    payer = relationship("PayerProfile", back_populates="fee_schedules")
    
    def __repr__(self):
        return f"<FeeSchedule(id={self.id}, payer_id={self.payer_id}, cpt='{self.cpt_code}', amount={self.allowable_amount})>"


class PayerProfileVersion(Base):
    """
    Version history for payer profiles
    Allows rollback and diff viewing
    """
    __tablename__ = "payer_profile_versions"
    
    id = Column(Integer, primary_key=True, index=True)
    payer_id = Column(Integer, ForeignKey('payer_profiles.id'), nullable=False, index=True)
    
    version_number = Column(Integer, nullable=False)
    
    # Full snapshot of payer profile at this version
    profile_data = Column(JSON, nullable=False)
    
    # Change metadata
    change_summary = Column(Text)  # "Added telehealth support, updated filing deadline"
    changed_by = Column(String(100))
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Publish status
    is_published = Column(Boolean, default=False)
    published_at = Column(DateTime)
    published_by = Column(String(100))
    
    def __repr__(self):
        return f"<PayerProfileVersion(payer_id={self.payer_id}, version={self.version_number})>"

