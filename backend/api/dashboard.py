"""
ClaimFlow - Dashboard summary endpoint.

Powers the Home page KPI cards + work queues. One round-trip returns
everything the dashboard needs so the FE doesn\'t have to fan out 8 separate
requests on first paint.

All counts / amounts are tenant-scoped from the JWT principal.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, Principal
from core.database import get_db
from models.claims import Claim
from models.credentialing import ProviderCredentialing
from models.denials import DenialCase
from models.payer_credentialing import PayerCredentialingCase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary")
async def dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Return KPI counts + work queues + AR aging for the current tenant."""
    tenant_filter = current_user.tenant_id
    today = date.today()
    thirty_days_out = today + timedelta(days=30)

    # ---- claim counts by state (single GROUP BY query) ----
    claim_state_rows = await db.execute(
        select(Claim.state, func.count(Claim.id))
        .where(Claim.tenant_id == tenant_filter)
        .group_by(Claim.state)
    )
    claims_by_state: Dict[str, int] = {state: int(n) for state, n in claim_state_rows.all()}
    total_claims = sum(claims_by_state.values())

    # ---- AR (outstanding balance) — sum charges of submitted/accepted, minus paid ----
    ar_buckets: List[Dict[str, Any]] = []
    bucket_defs = [
        ("0-30", today - timedelta(days=30), today),
        ("31-60", today - timedelta(days=60), today - timedelta(days=31)),
        ("61-90", today - timedelta(days=90), today - timedelta(days=61)),
        ("90+", date(2000, 1, 1), today - timedelta(days=91)),
    ]
    for label, start_d, end_d in bucket_defs:
        row = await db.execute(
            select(
                func.coalesce(func.sum(Claim.total_charges - func.coalesce(Claim.total_paid, 0)), 0),
                func.count(Claim.id),
            ).where(and_(
                Claim.tenant_id == tenant_filter,
                Claim.state.in_(["submitted", "accepted", "partially_paid", "appealed"]),
                Claim.submitted_date.isnot(None),
                func.date(Claim.submitted_date) >= start_d,
                func.date(Claim.submitted_date) <= end_d,
            ))
        )
        amount, count = row.one()
        ar_buckets.append({"bucket": label, "amount": float(amount or 0), "count": int(count)})

    ar_total = sum(b["amount"] for b in ar_buckets)

    # ---- denial counts (open vs total this month) ----
    month_start = date(today.year, today.month, 1)
    year_start = date(today.year, 1, 1)
    open_denials_row = await db.execute(
        select(func.count(DenialCase.id)).where(and_(
            DenialCase.tenant_id == tenant_filter,
            DenialCase.status.in_(["new", "in_progress", "appealed"]),
        ))
    )
    open_denials = int(open_denials_row.scalar() or 0)

    denials_this_month_row = await db.execute(
        select(func.count(DenialCase.id)).where(and_(
            DenialCase.tenant_id == tenant_filter,
            func.date(DenialCase.created_at) >= month_start,
        ))
    )
    denials_this_month = int(denials_this_month_row.scalar() or 0)

    # ---- this-month claim counts + revenue ----
    this_month_claims_row = await db.execute(
        select(
            func.count(Claim.id),
            func.coalesce(func.sum(Claim.total_charges), 0),
            func.coalesce(func.sum(Claim.total_paid), 0),
        ).where(and_(
            Claim.tenant_id == tenant_filter,
            Claim.created_date.isnot(None),
            func.date(Claim.created_date) >= month_start,
        ))
    )
    mtd_claims, mtd_charges, mtd_paid = this_month_claims_row.one()
    mtd_claims = int(mtd_claims or 0)
    mtd_charges = float(mtd_charges or 0)
    mtd_paid = float(mtd_paid or 0)

    # ---- denial rate YTD: distinct denied claims / submitted claims ----
    ytd_submitted_row = await db.execute(
        select(func.count(Claim.id)).where(and_(
            Claim.tenant_id == tenant_filter,
            Claim.submitted_date.isnot(None),
            func.date(Claim.submitted_date) >= year_start,
        ))
    )
    ytd_submitted = int(ytd_submitted_row.scalar() or 0)

    ytd_denied_row = await db.execute(
        select(func.count(func.distinct(DenialCase.claim_id))).where(and_(
            DenialCase.tenant_id == tenant_filter,
            func.date(DenialCase.created_at) >= year_start,
        ))
    )
    ytd_denied = int(ytd_denied_row.scalar() or 0)

    denial_rate_pct = round((ytd_denied / ytd_submitted) * 100, 1) if ytd_submitted else 0.0

    # ---- collection rate YTD: total_paid / total_charges across paid+denied claims ----
    ytd_collection_row = await db.execute(
        select(
            func.coalesce(func.sum(Claim.total_charges), 0),
            func.coalesce(func.sum(Claim.total_paid), 0),
        ).where(and_(
            Claim.tenant_id == tenant_filter,
            Claim.submitted_date.isnot(None),
            func.date(Claim.submitted_date) >= year_start,
        ))
    )
    ytd_charges_total, ytd_paid_total = ytd_collection_row.one()
    ytd_charges_total = float(ytd_charges_total or 0)
    ytd_paid_total = float(ytd_paid_total or 0)
    collection_rate_pct = round((ytd_paid_total / ytd_charges_total) * 100, 1) if ytd_charges_total else 0.0

    # ---- credentialing queue counts ----
    cred_status_rows = await db.execute(
        select(ProviderCredentialing.credentialing_status, func.count(ProviderCredentialing.id))
        .where(ProviderCredentialing.tenant_id == tenant_filter)
        .group_by(ProviderCredentialing.credentialing_status)
    )
    credentialing_by_status: Dict[str, int] = {s: int(n) for s, n in cred_status_rows.all()}

    # ---- payer enrollment expiring within 30 days ----
    expiring_enrollments_row = await db.execute(
        select(func.count(PayerCredentialingCase.id)).where(and_(
            PayerCredentialingCase.tenant_id == tenant_filter,
            PayerCredentialingCase.expiration_date.isnot(None),
            PayerCredentialingCase.expiration_date <= thirty_days_out,
        ))
    )
    expiring_enrollments = int(expiring_enrollments_row.scalar() or 0)

    # ---- work queues: top buckets the operator should look at right now ----
    work_queues = [
        {
            "key": "draft_claims",
            "label": "Draft claims",
            "count": claims_by_state.get("draft", 0),
            "link": "/claims?state=draft",
        },
        {
            "key": "ready_to_submit",
            "label": "Ready to submit",
            "count": claims_by_state.get("ready_to_submit", 0),
            "link": "/claims?state=ready_to_submit",
        },
        {
            "key": "open_denials",
            "label": "Open denials",
            "count": open_denials,
            "link": "/denials",
        },
        {
            "key": "credentialing_review",
            "label": "Credentialing — needs review",
            "count": credentialing_by_status.get("requires_review", 0),
            "link": "/credentialing?status=requires_review",
        },
        {
            "key": "expiring_enrollments",
            "label": "Enrollments expiring ≤30d",
            "count": expiring_enrollments,
            "link": "/payer-enrollment",
        },
    ]

    return {
        "success": True,
        "data": {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "claims": {"by_state": claims_by_state, "total": total_claims},
            "ar": {"buckets": ar_buckets, "total": ar_total},
            "denials": {
                "open": open_denials,
                "this_month": denials_this_month,
            },
            "credentialing": {"by_status": credentialing_by_status},
            "enrollment": {"expiring_30d": expiring_enrollments},
            "work_queues": work_queues,
            "month_to_date": {
                "claims_created": mtd_claims,
                "charges": mtd_charges,
                "paid": mtd_paid,
            },
            "year_to_date": {
                "submitted": ytd_submitted,
                "denied": ytd_denied,
                "denial_rate_pct": denial_rate_pct,
                "collection_rate_pct": collection_rate_pct,
                "charges": ytd_charges_total,
                "paid": ytd_paid_total,
            },
        },
    }
