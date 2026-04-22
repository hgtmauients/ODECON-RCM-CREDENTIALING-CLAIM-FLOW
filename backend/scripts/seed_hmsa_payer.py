"""
Seed HMSA (Hawaii Medical Service Association) as a payer profile for the
specified tenant.

HMSA is the Blue Cross Blue Shield licensee in Hawaii — the dominant
commercial payer in the state. Field values below are sensible defaults
suitable for a Waystar / Availity / Office Ally connection. The actual
trading partner ID, submitter ID, and connection credentials are tenant-
specific and should be edited after seeding via the Payer admin UI.

Idempotent — re-running with the same name updates the existing draft.

Usage:
    docker exec noodledoc-backend-1 python -m scripts.seed_hmsa_payer \
        --tenant 00000000-0000-0000-0000-000000000001
"""

import argparse
import asyncio
import sys
from datetime import date

from sqlalchemy import and_, select

from core.database import async_session_factory
from models.rcm import PayerProfile


# Standard HMSA defaults. These values come from publicly-documented HMSA
# provider materials + standard Blue Cross 837P conventions. Trading-partner
# / submitter / receiver IDs are clearinghouse-specific and intentionally
# left blank for the operator to fill in.
HMSA_DEFAULTS = {
    "name": "HMSA",
    "display_name": "Hawaii Medical Service Association",
    "payer_id": "HMSA001",  # Common HMSA payer ID; verify against your clearinghouse
    "naic_code": "97225",
    "plan_ids": ["HMSA-PPO", "HMSA-HMO", "HMSA-QUEST"],
    # Connectivity — operator must complete these from the Payer admin UI.
    "clearinghouse": "Waystar",
    "trading_partner_id": "",
    "submitter_id": "",
    "receiver_id": "HMSA",
    "connection_method": "clearinghouse",
    # Formats
    "format_837_type": "837P",
    "supports_pwk_attachments": False,
    # Telehealth — HMSA pays parity for synchronous telehealth (POS 02 / 10)
    "supports_telehealth": True,
    "telehealth_modifiers": ["95", "GT"],
    "telehealth_pos_codes": ["02", "10"],
    "telehealth_parity": True,
    # Requirements
    "requires_taxonomy": True,
    "requires_npi_type_2": False,
    "requires_tin": True,
    "requires_clia": False,
    # Eligibility / status / auth
    "supports_270_271": True,
    "supports_276_277": True,
    "supports_278_auth": True,
    "auth_portal_url": "https://hhin.hmsa.com/",
    "auth_portal_login_required": True,
    # ERA / EFT
    "supports_835_era": True,
    "era_enrollment_required": True,
    "era_enrollment_url": "https://hhin.hmsa.com/",
    "eft_enrollment_required": True,
    # SLAs — HMSA enforces a 12-month timely filing limit and a 60-day
    # appeal window (per the HMSA Provider Resource Center).
    "filing_limit_days": 365,
    "filing_limit_from": "service_date",
    "auth_response_days": 14,
    "appeal_window_days": 60,
    "audit_response_days": 30,
    # Claim frequency / corrections — HMSA accepts the standard X12 codes:
    # 7 = replacement, 8 = void.
    "supports_corrected_claims": True,
    "corrected_claim_frequency_code": "7",
    "void_claim_frequency_code": "8",
    "accepts_secondary_claims": True,
    # Paper fallback
    "paper_claim_supported": True,
    "paper_claim_address": "HMSA\nP.O. Box 860\nHonolulu, HI 96808-0860",
    # State-specific
    "state_code": "HI",
    "is_active": True,
    "is_draft": False,
    "version": 1,
    "notes": "Seeded via scripts/seed_hmsa_payer.py — verify trading partner / submitter IDs against the live clearinghouse before going live.",
}


async def _seed(tenant_id: str) -> int:
    async with async_session_factory() as db:
        existing = await db.execute(
            select(PayerProfile).where(and_(
                PayerProfile.tenant_id == tenant_id,
                PayerProfile.name == HMSA_DEFAULTS["name"],
            ))
        )
        row = existing.scalar_one_or_none()
        if row:
            for k, v in HMSA_DEFAULTS.items():
                if hasattr(row, k):
                    setattr(row, k, v)
            row.updated_by = "seed_hmsa_payer"
            print(f"Updated existing HMSA payer (id={row.id}) for tenant {tenant_id}")
        else:
            row = PayerProfile(
                tenant_id=tenant_id,
                created_by="seed_hmsa_payer",
                published_at=None,
                **HMSA_DEFAULTS,
            )
            db.add(row)
            await db.flush()
            print(f"Created HMSA payer (id={row.id}) for tenant {tenant_id}")
        await db.commit()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed HMSA as a payer profile for a tenant")
    parser.add_argument("--tenant", required=True, help="Tenant UUID")
    args = parser.parse_args()
    return asyncio.run(_seed(args.tenant))


if __name__ == "__main__":
    sys.exit(main())
