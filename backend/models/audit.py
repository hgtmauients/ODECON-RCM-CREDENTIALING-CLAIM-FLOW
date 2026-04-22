"""
Audit & Security Models
Track all sensitive operations for compliance
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base


class CredentialAccessLog(Base):
    """
    Log every time credentials are accessed/decrypted
    Critical for security audits and compliance
    """
    __tablename__ = "credential_access_log"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Who
    user_id = Column(String(100), nullable=False, index=True)
    user_email = Column(String(200))
    user_role = Column(String(50))
    
    # What
    payer_id = Column(Integer, ForeignKey('payer_profiles.id'), index=True)
    credential_type = Column(String(50), nullable=False)  # "api_key", "sftp_password", "portal_login"
    action = Column(String(50), nullable=False, index=True)  # "viewed", "updated", "deleted", "rotated"
    
    # When
    accessed_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Where
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    
    # Context
    reason = Column(Text)  # Why was credential accessed
    
    def __repr__(self):
        return f"<CredentialAccessLog(user={self.user_id}, payer={self.payer_id}, action={self.action})>"


class SecurityAuditLog(Base):
    """
    General security audit log
    Tracks all sensitive operations across RCM system
    """
    __tablename__ = "security_audit_log"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Who
    user_id = Column(String(100), nullable=False, index=True)
    user_email = Column(String(200))
    user_role = Column(String(50))
    
    # What
    action = Column(String(100), nullable=False, index=True)
    # Actions: "payer_created", "payer_published", "rule_created", "claim_submitted", 
    #          "denial_appealed", "provider_approved", "credential_rotated"
    
    resource_type = Column(String(50), index=True)  # "payer", "claim", "denial", "credential"
    resource_id = Column(String(100), index=True)
    
    # When
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Where
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    
    # Details
    changes = Column(JSON)  # Before/after for updates
    extra_data = Column("metadata", JSON)  # Additional context
    
    # Result
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    
    def __repr__(self):
        return f"<SecurityAuditLog(user={self.user_id}, action={self.action}, resource={self.resource_type}/{self.resource_id})>"


class MFAAttempt(Base):
    """
    Track MFA attempts for sensitive operations
    """
    __tablename__ = "mfa_attempts"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    user_id = Column(String(100), nullable=False, index=True)
    operation = Column(String(100), nullable=False)  # "update_payer_credential", "delete_payer"
    
    # MFA details
    mfa_method = Column(String(50))  # "totp", "sms", "email"
    attempt_time = Column(DateTime(timezone=True), server_default=func.now())
    success = Column(Boolean, nullable=False)
    
    # Security
    ip_address = Column(String(50))
    
    def __repr__(self):
        return f"<MFAAttempt(user={self.user_id}, operation={self.operation}, success={self.success})>"

