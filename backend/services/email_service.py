"""
ClaimFlow - Email service abstraction.
Provides sendmail operations; defaults to logging in development.
Reads SMTP settings from per-tenant DB first, falls back to env vars.
"""

import os
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _env_smtp():
    return {
        "host": os.getenv("SMTP_HOST", ""),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "user": os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASS", ""),
        "from_email": os.getenv("FROM_EMAIL", "noreply@claimflow.io"),
    }


class EmailService:
    """Simple email service with fallback logging."""

    def __init__(
        self,
        host: str = "",
        port: int = 587,
        user: str = "",
        password: str = "",
        from_email: str = "noreply@claimflow.io",
    ):
        env = _env_smtp()
        self.host = host or env["host"]
        self.port = port if host else env["port"]
        self.user = user or env["user"]
        self.password = password or env["password"]
        self.from_email = from_email if host else env["from_email"]

    async def send_email(self, to: str, subject: str, body: str, html: Optional[str] = None) -> bool:
        if not self.host:
            logger.info(f"[EMAIL-DEV] To={to} Subject={subject}")
            return True

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to
            msg.attach(MIMEText(body, "plain"))
            if html:
                msg.attach(MIMEText(html, "html"))

            with smtplib.SMTP(self.host, self.port) as server:
                server.starttls()
                if self.user:
                    server.login(self.user, self.password)
                server.sendmail(self.from_email, [to], msg.as_string())

            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to}: {e}")
            return False

    async def send_credentialing_acknowledgement_email(
        self, provider_email: str, provider_name: str, state_name: str
    ):
        await self.send_email(
            to=provider_email,
            subject=f"ClaimFlow - Credentialing Application Received",
            body=f"Dear {provider_name},\n\nYour credentialing application has been received and is being processed.\n\nThank you,\nClaimFlow",
        )

    async def send_provider_welcome_email(self, provider_email: str, provider_name: str):
        await self.send_email(
            to=provider_email,
            subject="Welcome to ClaimFlow",
            body=f"Dear {provider_name},\n\nYour credentialing has been approved. Welcome to ClaimFlow!\n\nBest,\nClaimFlow Team",
        )

    async def send_provider_rejection_email(self, provider_email: str, provider_name: str, reason: str):
        await self.send_email(
            to=provider_email,
            subject="ClaimFlow - Credentialing Update",
            body=f"Dear {provider_name},\n\nUnfortunately your credentialing application was not approved.\nReason: {reason}\n\nPlease contact support for details.\n\nClaimFlow Team",
        )

    async def send_admin_notification(self, admin_email: str, provider_name: str, status: str):
        await self.send_email(
            to=admin_email,
            subject=f"ClaimFlow - Provider Credentialing {status.title()}",
            body=f"Provider {provider_name} credentialing completed with status: {status}",
        )


async def get_tenant_email_service(db: AsyncSession, tenant_id: str) -> EmailService:
    """Build an EmailService using the tenant's stored SMTP settings."""
    from core.tenant_config import get_tenant_setting
    host = await get_tenant_setting(db, tenant_id, "smtp_host", default="")
    port = int(await get_tenant_setting(db, tenant_id, "smtp_port", default="587") or "587")
    user = await get_tenant_setting(db, tenant_id, "smtp_user", default="")
    password = await get_tenant_setting(db, tenant_id, "smtp_pass", default="")
    from_email = await get_tenant_setting(db, tenant_id, "from_email", default="noreply@claimflow.io")
    return EmailService(host=host, port=port, user=user, password=password, from_email=from_email)


# Global instance using env vars only (backward-compatible)
email_service = EmailService()
