"""
Notification dispatch helper.

Two channels: in-app (always — writes to the notifications table) and email
(opt-in: only when the tenant has SMTP configured + at least one admin user
exists). The scheduler expirations job + denial creation hooks call the
helpers here instead of calling the email/notification primitives directly.
"""

import logging
from datetime import datetime, timezone
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.notification import Notification, SEVERITY_INFO

logger = logging.getLogger(__name__)


async def create_notification(
    db: AsyncSession,
    *,
    tenant_id: str | UUID,
    type: str,
    title: str,
    message: Optional[str] = None,
    severity: str = SEVERITY_INFO,
    user_id: str | UUID | None = None,
    link_url: Optional[str] = None,
    metadata: Optional[dict] = None,
    deduplicate_key: Optional[str] = None,
) -> Notification:
    """Insert a Notification row. Caller is responsible for the commit.

    `deduplicate_key`, when supplied, is folded into metadata.dedupe so a
    follow-up sweep can avoid creating duplicate alerts for the same
    underlying event (e.g. the same expiring license re-discovered every
    nightly run). The caller queries metadata->>'dedupe' before inserting.
    """
    payload_metadata = dict(metadata or {})
    if deduplicate_key:
        payload_metadata.setdefault("dedupe", deduplicate_key)

    n = Notification(
        tenant_id=tenant_id,
        user_id=user_id,
        type=type,
        severity=severity,
        title=title,
        message=message,
        link_url=link_url,
        extra_data=payload_metadata or None,
    )
    db.add(n)
    return n


async def already_notified(
    db: AsyncSession,
    tenant_id: str | UUID,
    type: str,
    deduplicate_key: str,
    *,
    within_hours: int = 24,
) -> bool:
    """True if we already created a notification of this type with the same
    dedupe key in the last N hours. Used to avoid spamming the same alert
    on every scheduler tick."""
    from sqlalchemy import cast, String
    cutoff = datetime.now(timezone.utc).timestamp() - (within_hours * 3600)
    res = await db.execute(
        select(Notification.id).where(and_(
            Notification.tenant_id == tenant_id,
            Notification.type == type,
            Notification.created_at >= datetime.fromtimestamp(cutoff, tz=timezone.utc),
            cast(Notification.extra_data["dedupe"], String) == f'"{deduplicate_key}"',
        )).limit(1)
    )
    return res.scalar_one_or_none() is not None


async def email_notification(
    db: AsyncSession,
    *,
    tenant_id: str,
    subject: str,
    body: str,
    recipients: Iterable[str],
) -> bool:
    """Send `body` via the tenant\'s configured SMTP. Best-effort — returns
    True on success, False on any failure (logged). Does NOT raise.

    Email is opt-in: when SMTP isn\'t configured for the tenant we silently
    no-op so the in-app notification still lands.
    """
    from core.tenant_config import get_tenant_setting

    smtp_host = await get_tenant_setting(db, tenant_id, "smtp_host")
    if not smtp_host:
        logger.debug("Skipping email for tenant=%s: SMTP not configured", tenant_id)
        return False

    smtp_port = int(await get_tenant_setting(db, tenant_id, "smtp_port", default="587"))
    smtp_user = await get_tenant_setting(db, tenant_id, "smtp_user", default="")
    smtp_pass = await get_tenant_setting(db, tenant_id, "smtp_pass", default="")
    from_email = await get_tenant_setting(db, tenant_id, "from_email", default="noreply@noodledoc.com")

    addrs = [r for r in recipients if r]
    if not addrs:
        return False

    try:
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = ", ".join(addrs)

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, addrs, msg.as_string())
        logger.info("Email sent: tenant=%s subject=%r recipients=%d", tenant_id, subject, len(addrs))
        return True
    except Exception as e:
        logger.warning("Email send failed for tenant=%s: %s", tenant_id, e)
        return False
