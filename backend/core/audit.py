"""
ClaimFlow - Audit logging helpers.

Writes security events to the SecurityAuditLog table. Used at every PHI
read, credential decryption, claim mutation, payer config change, etc.

Two helper shapes:
- log_audit_event(...)  — explicit kwargs, used by callers that already have
                          a Principal in scope.
- audit(...)            — context-manager friendly ergonomic wrapper that
                          captures success/failure automatically.

Audit writes are added to the caller\'s session (db.add) but NOT committed
here — that lets the audit row commit atomically with the business write.
If the business write rolls back, the audit row rolls back with it.
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from models.audit import SecurityAuditLog
from api.auth import Principal

logger = logging.getLogger(__name__)


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


def _user_agent(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    return request.headers.get("User-Agent", None)


async def log_audit_event(
    db: AsyncSession,
    principal: Principal,
    action: str,
    resource_type: str,
    resource_id: str,
    *,
    request: Optional[Request] = None,
    changes: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    success: bool = True,
    error_message: Optional[str] = None,
) -> None:
    """Write an audit trail entry. Atomically commits with the caller\'s tx."""
    entry = SecurityAuditLog(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        user_email=principal.email,
        user_role=principal.roles[0] if principal.roles else None,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
        changes=changes,
        extra_data=metadata,
        success=success,
        error_message=error_message,
    )
    db.add(entry)
    logger.info(
        "AUDIT tenant=%s user=%s %s %s/%s",
        principal.tenant_id, principal.email, action, resource_type, resource_id,
    )


@asynccontextmanager
async def audit(
    db: AsyncSession,
    principal: Principal,
    action: str,
    resource_type: str,
    resource_id: str,
    *,
    request: Optional[Request] = None,
    changes: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Context manager. Logs success on clean exit, failure on exception.
    Re-raises the exception so the caller\'s normal error handling runs.

    Usage:
        async with audit(db, current_user, "patient_updated", "patient", str(pid)):
            ... mutation work ...
            await db.commit()
    """
    try:
        yield
    except Exception as exc:
        await log_audit_event(
            db, principal, action, resource_type, resource_id,
            request=request, changes=changes, metadata=metadata,
            success=False, error_message=str(exc),
        )
        # The audit row was added to a (possibly broken) transaction. Best-
        # effort flush to a separate session so the failure is captured even
        # when the business transaction rolls back.
        try:
            from core.database import async_session_factory
            async with async_session_factory() as fallback:
                fallback.add(SecurityAuditLog(
                    tenant_id=principal.tenant_id,
                    user_id=principal.user_id,
                    user_email=principal.email,
                    user_role=principal.roles[0] if principal.roles else None,
                    action=action,
                    resource_type=resource_type,
                    resource_id=str(resource_id),
                    ip_address=_client_ip(request),
                    user_agent=_user_agent(request),
                    changes=changes,
                    extra_data=metadata,
                    success=False,
                    error_message=str(exc),
                ))
                await fallback.commit()
        except Exception:
            logger.exception("Failed to flush audit row to fallback session")
        raise
    else:
        await log_audit_event(
            db, principal, action, resource_type, resource_id,
            request=request, changes=changes, metadata=metadata,
            success=True,
        )
