"""
ClaimFlow - Background job scheduler.
Uses APScheduler for periodic tasks (835 polling, renewal reminders, etc.).
Starts with the FastAPI lifespan if CLAIMFLOW_SCHEDULER_ENABLED=true.

Multi-worker safety: each scheduled job acquires a Postgres advisory lock
before executing. If another worker holds the lock, the job no-ops on this
worker. This makes it safe to run with N uvicorn workers without duplicate
runs, without needing a separate scheduler container.
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text as sa_text
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
SCHEDULER_ENABLED = os.getenv("CLAIMFLOW_SCHEDULER_ENABLED", "false").lower() == "true"

# Stable lock IDs (any 64-bit signed int). Different jobs use different IDs.
_LOCK_ID_835_POLL = 0x1F00_835A_AAAA_0001
_LOCK_ID_EXPIRATION = 0x1F00_835A_AAAA_0002
_LOCK_ID_277_POLL = 0x1F00_835A_AAAA_0003
_LOCK_ID_CREDENTIALING_QUEUE = 0x1F00_835A_AAAA_0004


@asynccontextmanager
async def _try_advisory_lock(lock_id: int) -> AsyncIterator[bool]:
    """
    Acquire a Postgres session-scoped advisory lock. Yields True if acquired,
    False if another connection holds it. Releases on exit.
    """
    from core.database import engine
    conn = await engine.connect()
    try:
        result = await conn.execute(
            sa_text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": lock_id},
        )
        acquired = bool(result.scalar())
        try:
            yield acquired
        finally:
            if acquired:
                await conn.execute(
                    sa_text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": lock_id},
                )
    finally:
        await conn.close()


def register_jobs():
    """Register all periodic jobs."""

    scheduler.add_job(
        _run_835_poll,
        CronTrigger(minute=0),  # Every hour at :00
        id="poll_835_files",
        name="Poll clearinghouse for 835",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        _run_277_poll,
        CronTrigger(minute=10),  # Every hour at :10
        id="poll_277_files",
        name="Poll clearinghouse for 277/277CA",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        _run_expiration_check,
        CronTrigger(hour=6, minute=0),
        id="check_expirations",
        name="Check credential expirations",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        _run_credentialing_queue,
        CronTrigger(minute="*/5"),  # Every 5 minutes
        id="process_credentialing_queue",
        name="Process credentialing queue",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    logger.info(f"Registered {len(scheduler.get_jobs())} scheduled jobs")


async def _run_835_poll():
    """Wrapper to call the 835 polling job under an advisory lock."""
    async with _try_advisory_lock(_LOCK_ID_835_POLL) as acquired:
        if not acquired:
            logger.debug("835 poll skipped on this worker (another worker holds the lock)")
            return
        try:
            from jobs.poll_835_files import poll_and_process_835_files
            await poll_and_process_835_files()
        except Exception as e:
            logger.error(f"835 poll job failed: {e}")


async def _run_277_poll():
    """Wrapper to call the 277 polling job under an advisory lock."""
    async with _try_advisory_lock(_LOCK_ID_277_POLL) as acquired:
        if not acquired:
            logger.debug("277 poll skipped on this worker (another worker holds the lock)")
            return
        try:
            from jobs.poll_835_files import poll_277_files
            await poll_277_files()
        except Exception as e:
            logger.error(f"277 poll job failed: {e}")


async def _run_credentialing_queue():
    """Drain pending credentialing jobs under an advisory lock."""
    async with _try_advisory_lock(_LOCK_ID_CREDENTIALING_QUEUE) as acquired:
        if not acquired:
            logger.debug("Credentialing queue skipped on this worker (another worker holds the lock)")
            return
        try:
            from jobs.credentialing_queue import process_credentialing_queue
            await process_credentialing_queue()
        except Exception as e:
            logger.error(f"Credentialing queue job failed: {e}")


async def _run_expiration_check():
    """Check for upcoming credential/license expirations per tenant.

    For every tenant with expiring credentials, write an in-app notification
    (deduplicated within a 24h window so we don\'t spam the same alert on
    every nightly run) and best-effort email admins if SMTP is configured.
    """
    async with _try_advisory_lock(_LOCK_ID_EXPIRATION) as acquired:
        if not acquired:
            logger.debug("Expiration check skipped on this worker (another worker holds the lock)")
            return
        try:
            from core.database import async_session_factory
            from models.tenant import Tenant
            from models.user import User
            from models.payer_credentialing import CredentialingRenewal
            from services.notify import (
                already_notified, create_notification, email_notification,
            )
            from sqlalchemy import select, and_
            from datetime import date, timedelta

            async with async_session_factory() as db:
                tenants_result = await db.execute(select(Tenant).where(Tenant.is_active == True))
                tenants = tenants_result.scalars().all()

                thirty_days = date.today() + timedelta(days=30)
                for tenant in tenants:
                    result = await db.execute(
                        select(CredentialingRenewal).where(and_(
                            CredentialingRenewal.tenant_id == tenant.id,
                            CredentialingRenewal.current_expiration_date <= thirty_days,
                            CredentialingRenewal.renewal_completed == False,
                        ))
                    )
                    expiring = result.scalars().all()
                    if not expiring:
                        continue

                    logger.warning(
                        "[tenant=%s] %d credentials expiring within 30 days",
                        tenant.slug, len(expiring),
                    )

                    # Dedupe per (tenant, day) so we only notify once per day
                    # even if the scheduler runs multiple times.
                    dedupe_key = f"expirations:{date.today().isoformat()}"
                    if await already_notified(db, str(tenant.id), "credential.expiring", dedupe_key):
                        continue

                    title = f"{len(expiring)} credential{'s' if len(expiring) != 1 else ''} expiring within 30 days"
                    message = "Open the Credentialing queue or Payer Enrollment to review."

                    await create_notification(
                        db,
                        tenant_id=tenant.id,
                        type="credential.expiring",
                        title=title,
                        message=message,
                        severity="warning",
                        link_url="/credentialing",
                        metadata={"count": len(expiring)},
                        deduplicate_key=dedupe_key,
                    )
                    await db.commit()

                    # Email tenant admins (best-effort).
                    admin_rows = await db.execute(
                        select(User.email).where(and_(
                            User.tenant_id == tenant.id,
                            User.is_active.is_(True),
                            User.roles.any("admin"),
                        ))
                    )
                    recipients = [row[0] for row in admin_rows.all() if row[0]]
                    if recipients:
                        await email_notification(
                            db,
                            tenant_id=str(tenant.id),
                            subject=f"[NoodleDoc] {title}",
                            body=(
                                f"Tenant: {tenant.name}\n"
                                f"{title}.\n\n"
                                f"Sign in and open the Credentialing queue to review:\n"
                                f"https://noodledoc.com/credentialing\n"
                            ),
                            recipients=recipients,
                        )
        except Exception as e:
            logger.exception("Expiration check failed: %s", e)


def start_scheduler():
    """Start the scheduler if enabled."""
    if not SCHEDULER_ENABLED:
        logger.info("Scheduler disabled (set CLAIMFLOW_SCHEDULER_ENABLED=true to enable)")
        return

    register_jobs()
    scheduler.start()
    logger.info("Scheduler started (advisory-locked for multi-worker safety)")


def stop_scheduler():
    """Shutdown the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
