"""
ClaimFlow - Global search.

A single endpoint that fans out a substring search across the four
operator-relevant entities (claims, providers, payers, denials) and returns
typed hits the FE can render in a unified results dropdown.

Tenant-scoped on every leg. Each hit carries enough fields for the FE to
construct a deep link (claim_id, provider_id, etc).
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, Principal
from core.database import get_db
from models.claims import Claim
from models.credentialing import ProviderCredentialing
from models.denials import DenialCase
from models.rcm import PayerProfile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["Search"])

# Per-entity result cap to keep the unified response small + snappy.
_PER_ENTITY_LIMIT = 8


@router.get("")
async def global_search(
    q: str = Query(..., min_length=1, max_length=128, description="Substring (case-insensitive)"),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Return up to N hits per entity for the given substring.

    Search columns:
      - claims     : claim_number ILIKE, payer_claim_id ILIKE
      - providers  : provider_id ILIKE; signup_data->>first_name / last_name / npi ILIKE
      - payers     : name ILIKE, display_name ILIKE, payer_id ILIKE
      - denials    : denial_description ILIKE, carc_code ILIKE, rarc_code ILIKE
    """
    current_user.require_role("billing")
    term = f"%{q.strip()}%"
    tenant_filter = current_user.tenant_id

    # ---- claims ----
    claims_rows = (await db.execute(
        select(Claim.id, Claim.claim_number, Claim.payer_claim_id, Claim.state, Claim.total_charges)
        .where(and_(
            Claim.tenant_id == tenant_filter,
            or_(Claim.claim_number.ilike(term), Claim.payer_claim_id.ilike(term)),
        ))
        .order_by(Claim.created_date.desc())
        .limit(_PER_ENTITY_LIMIT)
    )).all()
    claims_hits: List[Dict[str, Any]] = [{
        "type": "claim",
        "id": str(r[0]),
        "title": r[1] or f"Claim #{r[0]}",
        "subtitle": f"{r[3] or 'unknown'}" + (f" · payer ref {r[2]}" if r[2] else ""),
        "link": f"/claims/{r[0]}",
        "extra": {"total_charges": float(r[4]) if r[4] else 0},
    } for r in claims_rows]

    # ---- providers (search the JSONB signup_data text) ----
    from sqlalchemy import cast, String
    signup_text = cast(ProviderCredentialing.signup_data, String)
    providers_rows = (await db.execute(
        select(
            ProviderCredentialing.provider_id,
            ProviderCredentialing.signup_data,
            ProviderCredentialing.credentialing_status,
        ).where(and_(
            ProviderCredentialing.tenant_id == tenant_filter,
            or_(
                ProviderCredentialing.provider_id.ilike(term),
                signup_text.ilike(term),
            ),
        ))
        .order_by(ProviderCredentialing.created_at.desc())
        .limit(_PER_ENTITY_LIMIT)
    )).all()
    providers_hits: List[Dict[str, Any]] = []
    for prov_id, signup, status in providers_rows:
        signup = signup or {}
        first = signup.get("first_name", "")
        last = signup.get("last_name", "")
        name = f"{first} {last}".strip() or prov_id
        npi = signup.get("npi", "")
        providers_hits.append({
            "type": "provider",
            "id": prov_id,
            "title": name,
            "subtitle": " · ".join(filter(None, [
                f"NPI {npi}" if npi else "",
                f"status {status}" if status else "",
            ])) or prov_id,
            # The credentialing modal opens via the Credentialing list; deep
            # link is the list filtered to this provider for now.
            "link": f"/credentialing?status={status}" if status else "/credentialing",
            "extra": {"npi": npi},
        })

    # ---- payers ----
    payers_rows = (await db.execute(
        select(PayerProfile.id, PayerProfile.name, PayerProfile.display_name,
               PayerProfile.payer_id, PayerProfile.is_active, PayerProfile.is_draft)
        .where(and_(
            PayerProfile.tenant_id == tenant_filter,
            or_(
                PayerProfile.name.ilike(term),
                PayerProfile.display_name.ilike(term),
                PayerProfile.payer_id.ilike(term),
            ),
        ))
        .order_by(PayerProfile.name)
        .limit(_PER_ENTITY_LIMIT)
    )).all()
    payers_hits: List[Dict[str, Any]] = [{
        "type": "payer",
        "id": str(r[0]),
        "title": r[2] or r[1],
        "subtitle": " · ".join(filter(None, [
            f"payer id {r[3]}" if r[3] else "",
            "draft" if r[5] else ("active" if r[4] else "inactive"),
        ])),
        "link": f"/admin/payers/{r[0]}",
    } for r in payers_rows]

    # ---- denials ----
    denials_rows = (await db.execute(
        select(DenialCase.id, DenialCase.claim_id, DenialCase.carc_code,
               DenialCase.rarc_code, DenialCase.denial_description,
               DenialCase.status, DenialCase.denied_amount)
        .where(and_(
            DenialCase.tenant_id == tenant_filter,
            or_(
                DenialCase.denial_description.ilike(term),
                DenialCase.carc_code.ilike(term),
                DenialCase.rarc_code.ilike(term),
            ),
        ))
        .order_by(DenialCase.created_at.desc())
        .limit(_PER_ENTITY_LIMIT)
    )).all()
    denials_hits: List[Dict[str, Any]] = [{
        "type": "denial",
        "id": str(r[0]),
        "title": (r[4] or "Denial")[:120],
        "subtitle": " · ".join(filter(None, [
            f"CARC {r[2]}" if r[2] else "",
            f"RARC {r[3]}" if r[3] else "",
            f"status {r[5]}" if r[5] else "",
        ])),
        "link": f"/denials/{r[0]}",
        "extra": {"denied_amount": float(r[6]) if r[6] else 0, "claim_id": r[1]},
    } for r in denials_rows]

    return {
        "success": True,
        "data": {
            "query": q,
            "claims": claims_hits,
            "providers": providers_hits,
            "payers": payers_hits,
            "denials": denials_hits,
            "total": len(claims_hits) + len(providers_hits) + len(payers_hits) + len(denials_hits),
        },
    }
