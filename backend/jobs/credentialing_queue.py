"""
Durable credentialing queue worker.

Processes pending provider credentialing records and retries stale in-progress
records so checks are not lost on process restarts.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select

from core.database import async_session_factory
from models.credentialing import ProviderCredentialing
from services.credentialing_runtime import run_credentialing_checks

logger = logging.getLogger(__name__)

_queue_metrics = {
    "runs": 0,
    "items_claimed": 0,
    "items_failed": 0,
    "stale_recovered": 0,
    "last_run_at": None,
    "last_success_at": None,
    "last_failure_at": None,
    "last_error": None,
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _capture_queue_exception(exc: Exception) -> None:
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("queue_worker", "credentialing")
            sentry_sdk.capture_exception(exc)
    except Exception:
        pass


def get_credentialing_queue_stats() -> dict:
    """Expose queue worker metrics for health/monitoring endpoints."""
    return dict(_queue_metrics)


async def process_credentialing_queue(*, batch_size: int = 25, stale_after_minutes: int = 30) -> None:
    """
    Drain pending credentialing work from DB and recover stale in-progress rows.

    This makes credentialing checks durable: if a node crashes after enqueue,
    records remain in DB and are reprocessed by this periodic worker.
    """
    _queue_metrics["runs"] += 1
    _queue_metrics["last_run_at"] = _utcnow_iso()
    run_failed = False
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
            _queue_metrics["stale_recovered"] += len(stale_records)

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
            _queue_metrics["last_success_at"] = _utcnow_iso()
            _queue_metrics["last_error"] = None
            return

        logger.info("Credentialing queue worker processing %d pending records", len(pending))
        _queue_metrics["items_claimed"] += len(pending)
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
        except Exception as e:
            logger.exception("Credentialing queue item failed provider_id=%s", item["provider_id"])
            _queue_metrics["items_failed"] += 1
            _queue_metrics["last_failure_at"] = _utcnow_iso()
            _queue_metrics["last_error"] = f"provider_id={item['provider_id']}"
            _capture_queue_exception(e)
            run_failed = True

    if not run_failed:
        _queue_metrics["last_success_at"] = _utcnow_iso()
        _queue_metrics["last_error"] = None
