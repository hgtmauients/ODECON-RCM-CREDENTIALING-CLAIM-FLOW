"""
Proactive breach-transition alert hooks.

Evaluates dashboard threshold alerts per tenant and dispatches notifications
when an alert transitions into BREACH state.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import String, and_, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import Principal
from api.dashboard import compliance_security_controls, scalability_readiness
from core.http_client import request_with_retry
from core.outbound_guard import assert_safe_http_url
from core.tenant_config import get_tenant_setting
from models.notification import Notification, SEVERITY_ERROR
from models.tenant import Tenant
from models.user import User
from services.notify import create_notification, email_notification

logger = logging.getLogger(__name__)


def _should_emit_breach(previous_status: str | None, current_status: str) -> bool:
    return current_status == "breach" and previous_status != "breach"


async def _latest_alert_status(
    db: AsyncSession,
    *,
    tenant_id: str,
    alert_key: str,
) -> str | None:
    result = await db.execute(
        select(Notification.extra_data).where(and_(
            Notification.tenant_id == tenant_id,
            Notification.type == "system.alert.threshold",
            cast(Notification.extra_data["alert_key"], String) == f'"{alert_key}"',
        ))
        .order_by(Notification.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    return str((row or {}).get("current_status") or "").strip() or None


async def _post_webhook(url: str, payload: dict[str, Any]) -> bool:
    try:
        assert_safe_http_url(url, field_name="alert_webhook_url")
        response = await request_with_retry(
            method="POST",
            url=url,
            json_body=payload,
            timeout_seconds=10.0,
            max_retries=1,
            retry_backoff_seconds=0.2,
            retry_on_statuses=(429, 500, 502, 503, 504),
        )
        return 200 <= response.status_code < 300
    except Exception:
        logger.exception("Alert webhook dispatch failed")
        return False


async def _dispatch_external_channels(
    db: AsyncSession,
    *,
    tenant_id: str,
    title: str,
    body: str,
    payload: dict[str, Any],
) -> dict[str, bool]:
    admin_rows = await db.execute(
        select(User.email).where(and_(
            User.tenant_id == tenant_id,
            User.is_active.is_(True),
            User.roles.any("admin"),
        ))
    )
    recipients = [row[0] for row in admin_rows.all() if row[0]]
    email_ok = await email_notification(
        db,
        tenant_id=tenant_id,
        subject=title,
        body=body,
        recipients=recipients,
    )

    alert_webhook_url = await get_tenant_setting(db, tenant_id, "alert_webhook_url", default="")
    slack_webhook_url = await get_tenant_setting(db, tenant_id, "slack_webhook_url", default="")
    webhook_ok = False
    slack_ok = False
    if alert_webhook_url:
        webhook_ok = await _post_webhook(alert_webhook_url, payload)
    if slack_webhook_url:
        slack_payload = {
            "text": f"{title}\n{body}",
        }
        slack_ok = await _post_webhook(slack_webhook_url, slack_payload)

    return {
        "email": email_ok,
        "webhook": webhook_ok,
        "slack": slack_ok,
    }


async def _emit_breach_notification(
    db: AsyncSession,
    *,
    tenant_id: str,
    section: str,
    alert: dict[str, Any],
    previous_status: str | None,
) -> None:
    label = str(alert.get("label", "Threshold breach"))
    value = alert.get("value")
    threshold = alert.get("threshold")
    direction = alert.get("direction", "gt")
    compare = ">" if direction == "gt" else "<"
    title = f"[NoodleDoc] {section} breach: {label}"
    body = (
        f"Tenant: {tenant_id}\n"
        f"Alert: {label}\n"
        f"Status transition: {previous_status or 'none'} -> breach\n"
        f"Value: {value} {compare} {threshold}\n"
        f"Time (UTC): {datetime.now(timezone.utc).isoformat()}\n"
    )
    payload = {
        "tenant_id": tenant_id,
        "section": section,
        "alert_key": alert.get("key"),
        "label": label,
        "previous_status": previous_status,
        "current_status": "breach",
        "value": value,
        "threshold": threshold,
        "direction": direction,
        "emitted_at": datetime.now(timezone.utc).isoformat(),
    }
    channel_results = await _dispatch_external_channels(
        db,
        tenant_id=tenant_id,
        title=title,
        body=body,
        payload=payload,
    )

    await create_notification(
        db,
        tenant_id=tenant_id,
        type="system.alert.threshold",
        severity=SEVERITY_ERROR,
        title=label,
        message=f"Threshold breach detected in {section}: value={value}, threshold={threshold}",
        link_url="/dashboard",
        metadata={
            "alert_key": alert.get("key"),
            "section": section,
            "previous_status": previous_status,
            "current_status": "breach",
            "threshold": threshold,
            "value": value,
            "direction": direction,
            "channels": channel_results,
        },
    )


async def monitor_breach_transitions(*, batch_limit: int = 500) -> dict[str, int]:
    """
    Evaluate tenant alerts and dispatch notifications on breach transitions.
    """
    from core.database import async_session_factory

    totals = {
        "tenants_scanned": 0,
        "alerts_checked": 0,
        "breach_transitions": 0,
    }

    async with async_session_factory() as db:
        tenants_result = await db.execute(
            select(Tenant.id).where(Tenant.is_active.is_(True)).order_by(Tenant.created_at.asc()).limit(batch_limit)
        )
        tenant_ids = [str(row[0]) for row in tenants_result.all()]
        for tenant_id in tenant_ids:
            totals["tenants_scanned"] += 1
            principal = Principal(
                user_id="system-alert-monitor",
                tenant_id=tenant_id,
                token_tenant_id=tenant_id,
                email="system-alert-monitor@noodledoc.local",
                roles=["admin", "billing"],
            )
            compliance = await compliance_security_controls(db=db, current_user=principal)
            scalability = await scalability_readiness(db=db, current_user=principal)
            alert_groups = [
                ("compliance", list((compliance or {}).get("data", {}).get("alerts", []) or [])),
                ("scalability", list((scalability or {}).get("data", {}).get("alerts", []) or [])),
            ]
            for section, alerts in alert_groups:
                for alert in alerts:
                    totals["alerts_checked"] += 1
                    key = str(alert.get("key", "")).strip()
                    if not key:
                        continue
                    current_status = str(alert.get("status", "ok"))
                    previous_status = await _latest_alert_status(
                        db,
                        tenant_id=tenant_id,
                        alert_key=key,
                    )
                    if _should_emit_breach(previous_status, current_status):
                        await _emit_breach_notification(
                            db,
                            tenant_id=tenant_id,
                            section=section,
                            alert=alert,
                            previous_status=previous_status,
                        )
                        totals["breach_transitions"] += 1
            await db.commit()
    return totals
