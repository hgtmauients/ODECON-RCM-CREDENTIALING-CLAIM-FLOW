"""
ClaimFlow - Audit logging helpers.
Writes security events to the SecurityAuditLog table.
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from models.audit import SecurityAuditLog
from api.auth import Principal

logger = logging.getLogger(__name__)


async def log_audit_event(
    db: AsyncSession,
    principal: Principal,
    action: str,
    resource_type: str,
    resource_id: str,
    *,
    changes: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    success: bool = True,
    error_message: Optional[str] = None,
) -> None:
    """Write an audit trail entry."""
    entry = SecurityAuditLog(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        user_email=principal.email,
        user_role=principal.roles[0] if principal.roles else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        changes=changes,
        extra_data=metadata,
        success=success,
        error_message=error_message,
    )
    db.add(entry)
    # Don't commit here — let the caller's transaction commit include this
    logger.info(f"AUDIT: {principal.email} {action} {resource_type}/{resource_id}")
