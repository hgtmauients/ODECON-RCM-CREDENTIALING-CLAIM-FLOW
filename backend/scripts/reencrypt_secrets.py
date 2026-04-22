"""
One-off lazy re-encrypt sweep.

Reads every encrypted column we know about and re-writes it under the active
encryption version. Run this AFTER rotating CLAIMFLOW_ENCRYPTION_KEY +
bumping CLAIMFLOW_ENCRYPTION_KEY_VERSION (see RUNBOOK § Secret rotation).

Once the sweep is complete you can drop the previous _v<N> slot from .env.

Idempotent: blobs already at the active version are simply re-written under
the same version (cheap; cost is dominated by DB I/O, not crypto).

Usage:
    docker exec noodledoc-backend-1 python -m scripts.reencrypt_secrets
    docker exec noodledoc-backend-1 python -m scripts.reencrypt_secrets --dry-run
"""

import argparse
import asyncio
import logging
import sys

from sqlalchemy import select

from core.database import async_session_factory
from services.encryption import reencrypt_with_active_key

logger = logging.getLogger("reencrypt")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def _sweep(dry_run: bool) -> int:
    """Walk every table that holds encrypted blobs and re-write each row.

    Tables / columns:
      - tenants.settings JSONB (any *_encrypted key)
      - era_enrollment_cases.routing_number_encrypted, account_number_encrypted
      - trading_partner_connections.sftp_password_encrypted, api_key_encrypted,
        api_secret_encrypted, portal_password_encrypted
    """
    from models.tenant import Tenant
    from models.payer_credentialing import ERAEnrollmentCase
    from models.rcm import TradingPartnerConnection

    rewritten = 0
    skipped = 0
    failed = 0

    async with async_session_factory() as db:
        # 1) tenants.settings JSONB — find every key ending in _encrypted.
        tenants = (await db.execute(select(Tenant))).scalars().all()
        for t in tenants:
            settings = dict(t.settings or {})
            changed = False
            for key, value in list(settings.items()):
                if not key.endswith("_encrypted") or not isinstance(value, str) or not value:
                    continue
                try:
                    settings[key] = await reencrypt_with_active_key(value)
                    changed = True
                    rewritten += 1
                    logger.info("tenant=%s settings.%s rewritten", t.id, key)
                except Exception as e:
                    failed += 1
                    logger.error("tenant=%s settings.%s FAILED: %s", t.id, key, e)
            if changed and not dry_run:
                t.settings = settings

        # 2) ERA enrollment cases (bank account numbers).
        eras = (await db.execute(select(ERAEnrollmentCase))).scalars().all()
        for era in eras:
            for col in ("routing_number_encrypted", "account_number_encrypted"):
                blob = getattr(era, col, None)
                if not blob:
                    skipped += 1
                    continue
                try:
                    new_blob = await reencrypt_with_active_key(blob)
                    if not dry_run:
                        setattr(era, col, new_blob)
                    rewritten += 1
                    logger.info("era_enrollment_case=%s %s rewritten", era.id, col)
                except Exception as e:
                    failed += 1
                    logger.error("era_enrollment_case=%s %s FAILED: %s", era.id, col, e)

        # 3) Trading partner connections (clearinghouse credentials).
        conns = (await db.execute(select(TradingPartnerConnection))).scalars().all()
        for c in conns:
            for col in (
                "sftp_password_encrypted",
                "api_key_encrypted",
                "api_secret_encrypted",
                "portal_password_encrypted",
            ):
                blob = getattr(c, col, None)
                if not blob:
                    skipped += 1
                    continue
                try:
                    new_blob = await reencrypt_with_active_key(blob)
                    if not dry_run:
                        setattr(c, col, new_blob)
                    rewritten += 1
                    logger.info("trading_partner_connection=%s %s rewritten", c.id, col)
                except Exception as e:
                    failed += 1
                    logger.error("trading_partner_connection=%s %s FAILED: %s", c.id, col, e)

        if dry_run:
            await db.rollback()
            logger.info("DRY RUN — no changes committed")
        else:
            await db.commit()

    logger.info("Done. rewritten=%d skipped=%d failed=%d (dry_run=%s)", rewritten, skipped, failed, dry_run)
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-encrypt every secret under the active key version")
    parser.add_argument("--dry-run", action="store_true", help="Skip the commit (default: false)")
    args = parser.parse_args()
    return asyncio.run(_sweep(dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
