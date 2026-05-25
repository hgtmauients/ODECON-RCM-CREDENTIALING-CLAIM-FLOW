"""
Durable credentialing queue worker.

Processes pending provider credentialing records and retries stale in-progress
records so checks are not lost on process restarts.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, select

from core.database import async_session_factory
from models.credentialing import ProviderCredentialing
from services.credentialing_runtime import run_credentialing_checks

logger = logging.getLogger(__name__)


async def process_credentialing_queue(*, batch_size: int = 25, stale_after_minutes: int = 30) -> None:
    """
    Drain pending credentialing work from DB and recover stale in-progress rows.

    This makes credentialing checks durable: if a node crashes after enqueue,
    records remain in DB and are reprocessed by this periodic worker.
    """
    async with async_session_factory() as db:
        stale_cutoff = datetime.utcnow() - timedelta(minutes=stale_after_minutes)

        # Recover stale in-progress records back to pending for retry.
        stale_result = await db.execute(
            select(ProviderCredentialing).where(and_(
                ProviderCredentialing.credentialing_status == "in_progress",
                ProviderCredentialing.completed_at.is_(None),
                ProviderCredentialing.started_at.isnot(None),
                ProviderCredentialing.started_at < stale_cutoff,
            ))
        )
        stale_records = stale_result.scalars().all()
        for rec in stale_records:
            rec.credentialing_status = "pending"
            rec.admin_notes = (rec.admin_notes or "") + "\n[auto] recovered stale in_progress job for retry"
        if stale_records:
            await db.commit()
            logger.warning("Recovered %d stale credentialing jobs", len(stale_records))

        # Pull pending work in deterministic order and claim it in this
        # transaction so concurrent workers cannot process the same provider.
        pending_result = await db.execute(
            select(ProviderCredentialing)
            .where(ProviderCredentialing.credentialing_status == "pending")
            .order_by(ProviderCredentialing.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        pending = pending_result.scalars().all()

        if not pending:
            return

        logger.info("Credentialing queue worker processing %d pending records", len(pending))
        now = datetime.utcnow()
        work_items = []
        for rec in pending:
            rec.credentialing_status = "in_progress"
            rec.started_at = now
            rec.completed_at = None
            work_items.append({
                "provider_id": rec.provider_id,
                "signup_data": rec.signup_data or {},
                "tenant_id": str(rec.tenant_id),
            })
        await db.commit()

    # Process outside the queue session; each run_credentialing_checks call
    # owns its own DB session + lifecycle.
    for item in work_items:
        try:
            await run_credentialing_checks(
                provider_id=item["provider_id"],
                signup_data=item["signup_data"],
                tenant_id=item["tenant_id"],
                preclaimed=True,
            )
        except Exception:
            logger.exception("Credentialing queue item failed provider_id=%s", item["provider_id"])
