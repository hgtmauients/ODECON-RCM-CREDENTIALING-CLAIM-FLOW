"""
835 File Polling Background Job
Automatically downloads 835 remittance files from clearinghouse SFTP
Runs every hour as scheduled task - processes per-tenant
"""

import asyncio
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from core.database import get_async_session
from models.tenant import Tenant
from models.rcm import PayerProfile, TradingPartnerConnection
from services.clearinghouse_transport import ClearinghouseService
from services.edi_processor import EDIProcessor
from services.denial_manager import DenialManager, AutoPostingEngine

logger = logging.getLogger(__name__)


async def poll_and_process_835_files():
    """
    Main polling function - downloads and processes 835 files.
    Iterates over active tenants to ensure tenant-scoped processing.
    """
    async for db in get_async_session():
        try:
            logger.info("Starting 835 file polling job...")

            # Get all active tenants
            tenants_result = await db.execute(
                select(Tenant).where(Tenant.is_active == True)
            )
            tenants = tenants_result.scalars().all()

            for tenant in tenants:
                await _poll_835_for_tenant(db, tenant)

        except Exception as e:
            logger.error(f"Fatal error in 835 polling job: {e}")
            raise


async def _poll_835_for_tenant(db: AsyncSession, tenant):
    """Process 835 polling for a single tenant."""
    try:
        payers_result = await db.execute(
            select(PayerProfile).where(and_(
                PayerProfile.is_active == True,
                PayerProfile.supports_835_era == True,
                PayerProfile.tenant_id == tenant.id,
            ))
        )
        payers = payers_result.scalars().all()

        if not payers:
            return

        total_files_downloaded = 0
        total_files_processed = 0
        errors = []

        transport = ClearinghouseService(db)
        edi_processor = EDIProcessor(db)
        denial_manager = DenialManager(db)
        auto_poster = AutoPostingEngine(db)

        for payer in payers:
            try:
                files = await transport.poll_for_835_files(payer.id)
                if not files:
                    continue

                total_files_downloaded += len(files)
                logger.info(f"[tenant={tenant.slug}] Downloaded {len(files)} 835 files from {payer.name}")

                for file_path in files:
                    try:
                        parse_result = await edi_processor.parse_835(file_path, tenant_id=str(tenant.id))

                        if parse_result.get("payments"):
                            await auto_poster.auto_post_835(
                                edi_file_id=parse_result.get("edi_file_id"),
                                payments_data=parse_result["payments"],
                            )

                        if parse_result.get("denials"):
                            await denial_manager.process_835_denials(
                                edi_file_id=parse_result.get("edi_file_id"),
                                denials_data=parse_result["denials"],
                            )

                        total_files_processed += 1
                    except Exception as e:
                        logger.error(f"[tenant={tenant.slug}] Error processing 835 file {file_path}: {e}")
                        errors.append(f"{file_path}: {str(e)}")

            except Exception as e:
                logger.error(f"[tenant={tenant.slug}] Error polling payer {payer.name}: {e}")
                errors.append(f"{payer.name}: {str(e)}")

        logger.info(f"[tenant={tenant.slug}] 835 polling complete: {total_files_downloaded} downloaded, {total_files_processed} processed")
        if errors:
            logger.warning(f"[tenant={tenant.slug}] Errors: {len(errors)}")

    except Exception as e:
        logger.error(f"[tenant={tenant.slug}] Error in tenant 835 processing: {e}")


async def poll_277_files():
    """Poll for 277 claim acknowledgment files - tenant-scoped."""
    async for db in get_async_session():
        try:
            tenants_result = await db.execute(select(Tenant).where(Tenant.is_active == True))
            tenants = tenants_result.scalars().all()

            for tenant in tenants:
                payers_result = await db.execute(
                    select(PayerProfile).where(and_(
                        PayerProfile.is_active == True,
                        PayerProfile.supports_276_277 == True,
                        PayerProfile.tenant_id == tenant.id,
                    ))
                )
                payers = payers_result.scalars().all()

                transport = ClearinghouseService(db)
                edi_processor = EDIProcessor(db)

                for payer in payers:
                    try:
                        files = await transport.poll_for_files(payer.id, file_pattern="*.277")
                        for file_path in files:
                            await edi_processor.parse_277(file_path, tenant_id=str(tenant.id))
                    except Exception as e:
                        logger.error(f"[tenant={tenant.slug}] Error polling 277 for {payer.name}: {e}")

        except Exception as e:
            logger.error(f"Fatal error in 277 polling: {e}")


if __name__ == "__main__":
    asyncio.run(poll_and_process_835_files())
