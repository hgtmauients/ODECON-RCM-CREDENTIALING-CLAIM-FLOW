"""
ClaimFlow - Background job scheduler.
Uses APScheduler for periodic tasks (835 polling, renewal reminders, etc.).
Starts with the FastAPI lifespan if CLAIMFLOW_SCHEDULER_ENABLED=true.
"""

import os
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
SCHEDULER_ENABLED = os.getenv("CLAIMFLOW_SCHEDULER_ENABLED", "false").lower() == "true"


def register_jobs():
    """Register all periodic jobs."""

    # Poll for 835/277CA files every hour
    scheduler.add_job(
        _run_835_poll,
        CronTrigger(minute=0),  # Every hour at :00
        id="poll_835_files",
        name="Poll clearinghouse for 835/277CA",
        replace_existing=True,
    )

    # Check credential/license expirations daily at 6am
    scheduler.add_job(
        _run_expiration_check,
        CronTrigger(hour=6, minute=0),
        id="check_expirations",
        name="Check credential expirations",
        replace_existing=True,
    )

    logger.info(f"Registered {len(scheduler.get_jobs())} scheduled jobs")


async def _run_835_poll():
    """Wrapper to call the 835 polling job."""
    try:
        from jobs.poll_835_files import poll_and_process_835_files
        await poll_and_process_835_files()
    except Exception as e:
        logger.error(f"835 poll job failed: {e}")


async def _run_expiration_check():
    """Check for upcoming credential/license expirations per tenant."""
    try:
        from core.database import async_session_factory
        from models.tenant import Tenant
        from models.payer_credentialing import CredentialingRenewal
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
                if expiring:
                    logger.warning(f"[tenant={tenant.slug}] {len(expiring)} credentials expiring within 30 days")
    except Exception as e:
        logger.error(f"Expiration check failed: {e}")


def start_scheduler():
    """Start the scheduler if enabled."""
    if not SCHEDULER_ENABLED:
        logger.info("Scheduler disabled (set CLAIMFLOW_SCHEDULER_ENABLED=true to enable)")
        return

    register_jobs()
    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler():
    """Shutdown the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
