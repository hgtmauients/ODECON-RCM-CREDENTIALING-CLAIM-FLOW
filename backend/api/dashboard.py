"""
ClaimFlow - Dashboard summary endpoint.

Powers the Home page KPI cards + work queues. One round-trip returns
everything the dashboard needs so the FE doesn\'t have to fan out 8 separate
requests on first paint.

All counts / amounts are tenant-scoped from the JWT principal.
"""

import logging
import os
import base64
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import and_, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, Principal
from core.database import get_db
from core.scheduler import get_scheduler_status
from jobs.credentialing_queue import get_credentialing_queue_stats
from models.audit import CredentialAccessLog, SecurityAuditLog
from models.claims import Claim
from models.credentialing import ProviderCredentialing
from models.denials import DenialCase
from models.payer_credentialing import PayerCredentialingCase
from models.rcm import PayerProfile, TradingPartnerConnection
from models.tenant import Tenant
import api.auth as auth_core
import core.idempotency as idempotency_core
import core.tenant_config as tenant_config_core

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 1)


def _delta_pct(current: float, previous: float) -> Optional[float]:
    if previous == 0:
        return None
    return round(((current - previous) / previous) * 100.0, 1)


def _coerce_state_key(value: Any) -> str:
    state_value = getattr(value, "value", value)
    return str(state_value)


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    mid = len(sorted_values) // 2
    if len(sorted_values) % 2 == 1:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2.0


def _threshold_alert(
    *,
    key: str,
    label: str,
    value: float,
    threshold: float,
    direction: str,
    warn_buffer: float = 0.0,
) -> Dict[str, Any]:
    """
    Build a normalized threshold alert object.

    direction:
      - "gt": breach when value > threshold
      - "lt": breach when value < threshold
    """
    if direction == "gt":
        breached = value > threshold
        warning = (not breached) and value >= max(0.0, threshold - warn_buffer)
    else:
        breached = value < threshold
        warning = (not breached) and value <= threshold + warn_buffer
    status = "breach" if breached else ("warning" if warning else "ok")
    return {
        "key": key,
        "label": label,
        "value": round(value, 2),
        "threshold": threshold,
        "direction": direction,
        "status": status,
        "breached": breached,
    }


def _is_valid_encryption_key(raw_key: str) -> bool:
    if not raw_key:
        return False
    try:
        decoded = base64.b64decode(raw_key)
    except Exception:
        return False
    return len(decoded) in {16, 24, 32}


async def _collect_rls_coverage(db: AsyncSession) -> Dict[str, Any]:
    tenant_tables_result = await db.execute(text("""
        SELECT table_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND column_name = 'tenant_id'
        ORDER BY table_name
    """))
    tenant_tables = [row[0] for row in tenant_tables_result.all()]

    coverage_rows = await db.execute(text("""
        SELECT c.relname AS table_name, c.relrowsecurity, c.relforcerowsecurity
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = current_schema()
          AND c.relkind = 'r'
        ORDER BY c.relname
    """))
    class_state = {
        row[0]: {"rowsecurity": bool(row[1]), "forcerowsecurity": bool(row[2])}
        for row in coverage_rows.all()
    }

    policy_rows = await db.execute(text("""
        SELECT tablename
        FROM pg_policies
        WHERE schemaname = current_schema()
        GROUP BY tablename
    """))
    policy_tables = {row[0] for row in policy_rows.all()}

    uncovered_tables: List[str] = []
    not_forced_tables: List[str] = []
    policy_missing_tables: List[str] = []
    for table_name in tenant_tables:
        state = class_state.get(table_name, {"rowsecurity": False, "forcerowsecurity": False})
        if not state.get("rowsecurity"):
            uncovered_tables.append(table_name)
        if not state.get("forcerowsecurity"):
            not_forced_tables.append(table_name)
        if table_name not in policy_tables:
            policy_missing_tables.append(table_name)

    covered_count = len(tenant_tables) - len(uncovered_tables)
    forced_count = len(tenant_tables) - len(not_forced_tables)
    policy_count = len(tenant_tables) - len(policy_missing_tables)
    tenant_table_count = len(tenant_tables)
    coverage_pct = _percent(covered_count, tenant_table_count)
    forced_pct = _percent(forced_count, tenant_table_count)
    policy_pct = _percent(policy_count, tenant_table_count)

    return {
        "tenant_tables": tenant_table_count,
        "coverage_pct": coverage_pct,
        "forced_pct": forced_pct,
        "policy_pct": policy_pct,
        "covered_tables": covered_count,
        "forced_tables": forced_count,
        "policy_tables": policy_count,
        "missing_row_security_tables": uncovered_tables,
        "missing_force_rls_tables": not_forced_tables,
        "missing_policy_tables": policy_missing_tables,
        "is_strictly_enforced": not uncovered_tables and not not_forced_tables and not policy_missing_tables,
    }


@router.get("/summary")
async def dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Return KPI counts + work queues + AR aging for the current tenant."""
    current_user.require_role("billing")
    tenant_filter = current_user.tenant_id
    today = date.today()
    thirty_days_out = today + timedelta(days=30)

    # ---- claim counts by state (single GROUP BY query) ----
    claim_state_rows = await db.execute(
        select(Claim.state, func.count(Claim.id))
        .where(Claim.tenant_id == tenant_filter)
        .group_by(Claim.state)
    )
    claims_by_state: Dict[str, int] = {_coerce_state_key(state): int(n) for state, n in claim_state_rows.all()}
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
            DenialCase.status.in_(["new", "in_review", "appeal_drafted", "appeal_submitted"]),
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


@router.get("/integrations")
async def integrations_overview(
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """
    Enterprise integration ecosystem readiness for the current tenant.

    Returns whether major integration surfaces are configured and the current
    clearinghouse connection footprint.
    """
    current_user.require_role("billing")
    tenant_filter = current_user.tenant_id

    def _has_setting(settings: Dict[str, Any], key: str) -> bool:
        value = settings.get(key)
        return value is not None and value != ""

    tenant_result = await db.execute(select(Tenant).where(Tenant.id == tenant_filter))
    tenant = tenant_result.scalar_one_or_none()
    tenant_settings: Dict[str, Any] = tenant.settings or {} if tenant else {}

    active_conn_result = await db.execute(
        select(func.count(TradingPartnerConnection.id))
        .join(PayerProfile, TradingPartnerConnection.payer_id == PayerProfile.id)
        .where(and_(
            PayerProfile.tenant_id == tenant_filter,
            TradingPartnerConnection.is_active.is_(True),
        ))
    )
    active_connections = int(active_conn_result.scalar() or 0)

    protocol_rows = await db.execute(
        select(TradingPartnerConnection.connection_type, func.count(TradingPartnerConnection.id))
        .join(PayerProfile, TradingPartnerConnection.payer_id == PayerProfile.id)
        .where(and_(
            PayerProfile.tenant_id == tenant_filter,
            TradingPartnerConnection.is_active.is_(True),
        ))
        .group_by(TradingPartnerConnection.connection_type)
    )
    protocols = {ctype: int(count) for ctype, count in protocol_rows.all()}

    tested_rows = await db.execute(
        select(
            func.sum(case((TradingPartnerConnection.last_test_status == "success", 1), else_=0)),
            func.sum(case((TradingPartnerConnection.last_tested.isnot(None), 1), else_=0)),
        )
        .join(PayerProfile, TradingPartnerConnection.payer_id == PayerProfile.id)
        .where(and_(
            PayerProfile.tenant_id == tenant_filter,
            TradingPartnerConnection.is_active.is_(True),
        ))
    )
    successful_tests, tested_total = tested_rows.one()
    successful_tests = int(successful_tests or 0)
    tested_total = int(tested_total or 0)

    payer_count_row = await db.execute(
        select(func.count(PayerProfile.id)).where(and_(
            PayerProfile.tenant_id == tenant_filter,
            PayerProfile.is_active.is_(True),
        ))
    )
    active_payers = int(payer_count_row.scalar() or 0)

    smtp_configured = _has_setting(tenant_settings, "smtp_host")
    webhook_configured = _has_setting(tenant_settings, "webhook_secret_encrypted")
    api_cert_configured = _has_setting(tenant_settings, "api_cert_key_encrypted") or bool(os.getenv("API_CERT_KEY"))
    caqh_configured = (
        _has_setting(tenant_settings, "caqh_org_id")
        and _has_setting(tenant_settings, "caqh_username")
        and (_has_setting(tenant_settings, "caqh_password_encrypted") or bool(os.getenv("CAQH_PASSWORD")))
    )
    state_license_provider = bool(os.getenv("STATE_LICENSE_PROVIDER_URL", "").strip())
    background_provider = bool(os.getenv("BACKGROUND_CHECK_PROVIDER_URL", "").strip())
    adapter_auth = bool(os.getenv("ADAPTER_API_KEY", "").strip()) and bool(os.getenv("ADAPTER_SHARED_SECRET", "").strip())

    configured_surfaces = [
        active_connections > 0,
        smtp_configured,
        webhook_configured,
        api_cert_configured,
        caqh_configured,
        state_license_provider,
        background_provider,
        adapter_auth,
    ]
    coverage_pct = _percent(sum(1 for x in configured_surfaces if x), len(configured_surfaces))

    return {
        "success": True,
        "data": {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "coverage_pct": coverage_pct,
            "clearinghouse": {
                "active_payers": active_payers,
                "active_connections": active_connections,
                "protocols": protocols,
                "tested_connections": tested_total,
                "successful_tests": successful_tests,
                "test_success_pct": _percent(successful_tests, tested_total),
            },
            "credentialing_integrations": {
                "state_license_provider_configured": state_license_provider,
                "background_check_provider_configured": background_provider,
                "api_cert_configured": api_cert_configured,
                "caqh_configured": caqh_configured,
            },
            "notifications": {
                "smtp_configured": smtp_configured,
            },
            "security": {
                "webhook_secret_configured": webhook_configured,
                "adapter_auth_configured": adapter_auth,
            },
        },
    }


@router.get("/benchmarks")
async def operational_benchmarks(
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """
    Operational analytics and benchmark metrics for the current tenant.
    Includes directional trend data over 7/30/90-day windows.
    """
    current_user.require_role("billing")
    tenant_filter = current_user.tenant_id
    today = date.today()
    windows = (7, 30, 90)
    last_30 = today - timedelta(days=30)
    last_90 = today - timedelta(days=90)

    def _window_bounds(days: int) -> tuple[date, date, date, date]:
        current_start = today - timedelta(days=days)
        current_end = today
        prev_end = current_start
        prev_start = prev_end - timedelta(days=days)
        return current_start, current_end, prev_start, prev_end

    async def _claim_count_for_window(field_name: str, start_date: date, end_date: date) -> int:
        claim_date_field = getattr(Claim, field_name)
        result = await db.execute(
            select(func.count(Claim.id)).where(and_(
                Claim.tenant_id == tenant_filter,
                claim_date_field.isnot(None),
                func.date(claim_date_field) >= start_date,
                func.date(claim_date_field) < end_date,
            ))
        )
        return int(result.scalar() or 0)

    async def _denial_count_for_window(start_date: date, end_date: date) -> int:
        result = await db.execute(
            select(func.count(func.distinct(DenialCase.claim_id))).where(and_(
                DenialCase.tenant_id == tenant_filter,
                func.date(DenialCase.created_at) >= start_date,
                func.date(DenialCase.created_at) < end_date,
            ))
        )
        return int(result.scalar() or 0)

    async def _credentialing_completed_for_window(start_date: date, end_date: date) -> int:
        result = await db.execute(
            select(func.count(ProviderCredentialing.id)).where(and_(
                ProviderCredentialing.tenant_id == tenant_filter,
                ProviderCredentialing.completed_at.isnot(None),
                func.date(ProviderCredentialing.completed_at) >= start_date,
                func.date(ProviderCredentialing.completed_at) < end_date,
            ))
        )
        return int(result.scalar() or 0)

    async def _payer_approved_for_window(start_date: date, end_date: date) -> int:
        result = await db.execute(
            select(func.count(PayerCredentialingCase.id)).where(and_(
                PayerCredentialingCase.tenant_id == tenant_filter,
                PayerCredentialingCase.status == "approved",
                PayerCredentialingCase.effective_date.isnot(None),
                PayerCredentialingCase.effective_date >= start_date,
                PayerCredentialingCase.effective_date < end_date,
            ))
        )
        return int(result.scalar() or 0)

    submitted_row = await db.execute(
        select(func.count(Claim.id)).where(and_(
            Claim.tenant_id == tenant_filter,
            Claim.submitted_date.isnot(None),
            func.date(Claim.submitted_date) >= last_30,
        ))
    )
    submitted_30d = int(submitted_row.scalar() or 0)

    adjudicated_row = await db.execute(
        select(func.count(Claim.id)).where(and_(
            Claim.tenant_id == tenant_filter,
            Claim.adjudicated_date.isnot(None),
            func.date(Claim.adjudicated_date) >= last_30,
        ))
    )
    adjudicated_30d = int(adjudicated_row.scalar() or 0)

    denied_claims_row = await db.execute(
        select(func.count(func.distinct(DenialCase.claim_id))).where(and_(
            DenialCase.tenant_id == tenant_filter,
            func.date(DenialCase.created_at) >= last_30,
        ))
    )
    denied_30d = int(denied_claims_row.scalar() or 0)

    trend_points: List[Dict[str, Any]] = []
    for days in windows:
        cur_start, cur_end, prev_start, prev_end = _window_bounds(days)
        current_submitted = await _claim_count_for_window("submitted_date", cur_start, cur_end)
        previous_submitted = await _claim_count_for_window("submitted_date", prev_start, prev_end)
        current_adjudicated = await _claim_count_for_window("adjudicated_date", cur_start, cur_end)
        previous_adjudicated = await _claim_count_for_window("adjudicated_date", prev_start, prev_end)
        current_denied = await _denial_count_for_window(cur_start, cur_end)
        previous_denied = await _denial_count_for_window(prev_start, prev_end)
        current_credentialing_completed = await _credentialing_completed_for_window(cur_start, cur_end)
        previous_credentialing_completed = await _credentialing_completed_for_window(prev_start, prev_end)
        current_payer_approved = await _payer_approved_for_window(cur_start, cur_end)
        previous_payer_approved = await _payer_approved_for_window(prev_start, prev_end)

        trend_points.append({
            "window_days": days,
            "submitted_claims": {
                "current": current_submitted,
                "previous": previous_submitted,
                "delta_pct": _delta_pct(float(current_submitted), float(previous_submitted)),
            },
            "adjudicated_claims": {
                "current": current_adjudicated,
                "previous": previous_adjudicated,
                "delta_pct": _delta_pct(float(current_adjudicated), float(previous_adjudicated)),
            },
            "denied_claims": {
                "current": current_denied,
                "previous": previous_denied,
                "delta_pct": _delta_pct(float(current_denied), float(previous_denied)),
            },
            "credentialing_completed": {
                "current": current_credentialing_completed,
                "previous": previous_credentialing_completed,
                "delta_pct": _delta_pct(float(current_credentialing_completed), float(previous_credentialing_completed)),
            },
            "payer_enrollment_approved": {
                "current": current_payer_approved,
                "previous": previous_payer_approved,
                "delta_pct": _delta_pct(float(current_payer_approved), float(previous_payer_approved)),
            },
        })

    cycle_rows = await db.execute(
        select(Claim.submitted_date, Claim.adjudicated_date, Claim.state).where(and_(
            Claim.tenant_id == tenant_filter,
            Claim.submitted_date.isnot(None),
            Claim.adjudicated_date.isnot(None),
            func.date(Claim.submitted_date) >= last_90,
        ))
    )

    cycle_days: List[float] = []
    first_pass_paid = 0
    total_cycle = 0
    for submitted_at, adjudicated_at, state in cycle_rows.all():
        if not submitted_at or not adjudicated_at:
            continue
        days = (adjudicated_at - submitted_at).total_seconds() / 86400.0
        if days < 0:
            continue
        cycle_days.append(days)
        total_cycle += 1
        state_value = getattr(state, "value", state)
        if state_value in {"paid", "partially_paid"}:
            first_pass_paid += 1

    cycle_days_sorted = sorted(cycle_days)
    avg_cycle_days = round(sum(cycle_days_sorted) / len(cycle_days_sorted), 2) if cycle_days_sorted else 0.0
    p50_cycle_days = round(_median(cycle_days_sorted), 2) if cycle_days_sorted else 0.0
    p95_idx = int((len(cycle_days_sorted) - 1) * 0.95) if cycle_days_sorted else 0
    p95_cycle_days = round(cycle_days_sorted[p95_idx], 2) if cycle_days_sorted else 0.0

    open_denials_row = await db.execute(
        select(func.count(DenialCase.id)).where(and_(
            DenialCase.tenant_id == tenant_filter,
            DenialCase.status.in_(["new", "in_review", "appeal_drafted", "appeal_submitted"]),
        ))
    )
    open_denials = int(open_denials_row.scalar() or 0)

    status_rows = await db.execute(
        select(Claim.state, func.count(Claim.id))
        .where(Claim.tenant_id == tenant_filter)
        .group_by(Claim.state)
    )
    by_state = {_coerce_state_key(state): int(count) for state, count in status_rows.all()}

    credentialing_status_rows = await db.execute(
        select(ProviderCredentialing.credentialing_status, func.count(ProviderCredentialing.id))
        .where(ProviderCredentialing.tenant_id == tenant_filter)
        .group_by(ProviderCredentialing.credentialing_status)
    )
    credentialing_by_status = {str(status): int(count) for status, count in credentialing_status_rows.all()}

    completed_rows = await db.execute(
        select(ProviderCredentialing.signup_date, ProviderCredentialing.completed_at).where(and_(
            ProviderCredentialing.tenant_id == tenant_filter,
            ProviderCredentialing.completed_at.isnot(None),
            func.date(ProviderCredentialing.completed_at) >= last_90,
        ))
    )
    completion_days: List[float] = []
    for signup_at, completed_at in completed_rows.all():
        if not signup_at or not completed_at:
            continue
        diff = (completed_at - signup_at).total_seconds() / 86400.0
        if diff >= 0:
            completion_days.append(diff)
    completion_days_sorted = sorted(completion_days)

    payer_status_rows = await db.execute(
        select(PayerCredentialingCase.status, func.count(PayerCredentialingCase.id))
        .where(PayerCredentialingCase.tenant_id == tenant_filter)
        .group_by(PayerCredentialingCase.status)
    )
    enrollment_by_status = {str(status): int(count) for status, count in payer_status_rows.all()}

    submitted_enrollment_30d_row = await db.execute(
        select(func.count(PayerCredentialingCase.id)).where(and_(
            PayerCredentialingCase.tenant_id == tenant_filter,
            PayerCredentialingCase.submitted_date.isnot(None),
            PayerCredentialingCase.submitted_date >= last_30,
        ))
    )
    submitted_enrollment_30d = int(submitted_enrollment_30d_row.scalar() or 0)

    approved_enrollment_30d_row = await db.execute(
        select(func.count(PayerCredentialingCase.id)).where(and_(
            PayerCredentialingCase.tenant_id == tenant_filter,
            PayerCredentialingCase.status == "approved",
            PayerCredentialingCase.effective_date.isnot(None),
            PayerCredentialingCase.effective_date >= last_30,
        ))
    )
    approved_enrollment_30d = int(approved_enrollment_30d_row.scalar() or 0)

    enrollment_cycle_rows = await db.execute(
        select(PayerCredentialingCase.submitted_date, PayerCredentialingCase.effective_date).where(and_(
            PayerCredentialingCase.tenant_id == tenant_filter,
            PayerCredentialingCase.status == "approved",
            PayerCredentialingCase.submitted_date.isnot(None),
            PayerCredentialingCase.effective_date.isnot(None),
            PayerCredentialingCase.effective_date >= last_90,
        ))
    )
    enrollment_cycle_days: List[float] = []
    for submitted_date, effective_date in enrollment_cycle_rows.all():
        if not submitted_date or not effective_date:
            continue
        diff = float((effective_date - submitted_date).days)
        if diff >= 0:
            enrollment_cycle_days.append(diff)
    enrollment_cycle_days_sorted = sorted(enrollment_cycle_days)

    scheduler_status = get_scheduler_status()
    queue_stats = get_credentialing_queue_stats()
    scheduler_jobs = scheduler_status.get("jobs", {})
    scheduler_failures = int(sum(int((job or {}).get("failures", 0)) for job in scheduler_jobs.values()))
    scheduler_runs = int(sum(int((job or {}).get("runs", 0)) for job in scheduler_jobs.values()))
    queue_runs = int(queue_stats.get("runs", 0) or 0)
    queue_failed = int(queue_stats.get("items_failed", 0) or 0)
    queue_claimed = int(queue_stats.get("items_claimed", 0) or 0)

    return {
        "success": True,
        "data": {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "throughput_30d": {
                "submitted": submitted_30d,
                "adjudicated": adjudicated_30d,
                "denied_claims": denied_30d,
            },
            "rates_30d": {
                "denial_rate_pct": _percent(denied_30d, submitted_30d),
                "first_pass_paid_rate_pct": _percent(first_pass_paid, total_cycle),
            },
            "cycle_time_days_90d": {
                "sample_size": len(cycle_days_sorted),
                "avg": avg_cycle_days,
                "p50": p50_cycle_days,
                "p95": p95_cycle_days,
            },
            "trend_windows": trend_points,
            "backlog": {
                "open_denials": open_denials,
                "draft_claims": by_state.get("draft", 0),
                "ready_to_submit": by_state.get("ready_to_submit", 0),
                "submitted": by_state.get("submitted", 0),
            },
            "credentialing_depth": {
                "by_status": credentialing_by_status,
                "completed_90d": len(completion_days_sorted),
                "completion_days_90d": {
                    "avg": round(sum(completion_days_sorted) / len(completion_days_sorted), 2) if completion_days_sorted else 0.0,
                    "median": round(_median(completion_days_sorted), 2) if completion_days_sorted else 0.0,
                    "p95": round(completion_days_sorted[int((len(completion_days_sorted) - 1) * 0.95)], 2)
                    if completion_days_sorted else 0.0,
                },
            },
            "payer_enrollment_lifecycle": {
                "by_status": enrollment_by_status,
                "submitted_30d": submitted_enrollment_30d,
                "approved_30d": approved_enrollment_30d,
                "approval_cycle_days_90d": {
                    "sample_size": len(enrollment_cycle_days_sorted),
                    "avg": round(sum(enrollment_cycle_days_sorted) / len(enrollment_cycle_days_sorted), 2) if enrollment_cycle_days_sorted else 0.0,
                    "median": round(_median(enrollment_cycle_days_sorted), 2) if enrollment_cycle_days_sorted else 0.0,
                },
            },
            "rcm_reliability_hardening": {
                "scheduler": {
                    "enabled": bool(scheduler_status.get("enabled")),
                    "running": bool(scheduler_status.get("running")),
                    "runs": scheduler_runs,
                    "failures": scheduler_failures,
                    "failure_rate_pct": _percent(scheduler_failures, scheduler_runs),
                },
                "credentialing_queue": {
                    "runs": queue_runs,
                    "items_claimed": queue_claimed,
                    "items_failed": queue_failed,
                    "item_failure_rate_pct": _percent(queue_failed, queue_claimed),
                    "stale_recovered": int(queue_stats.get("stale_recovered", 0) or 0),
                    "last_success_at": queue_stats.get("last_success_at"),
                    "last_failure_at": queue_stats.get("last_failure_at"),
                },
            },
        },
    }


@router.get("/compliance")
async def compliance_security_controls(
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """
    Compliance and security control maturity snapshot for the current tenant.
    """
    current_user.require_role("admin")
    tenant_filter = current_user.tenant_id
    now_utc = datetime.now(timezone.utc)
    last_30 = (now_utc - timedelta(days=30)).date()

    jwt_algorithm = (auth_core.JWT_ALGORITHM or "HS256").upper()
    jwt_secure = bool(auth_core.JWT_JWKS_URL.startswith("https://")) if jwt_algorithm == "RS256" else len(auth_core.JWT_SECRET) >= 32
    encryption_key_ok = _is_valid_encryption_key(os.getenv("CLAIMFLOW_ENCRYPTION_KEY", ""))
    cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    cors_strict = bool(cors_origins) and all("*" not in origin and origin.startswith("https://") for origin in cors_origins)
    outbound_guard_strict = os.getenv("ALLOW_PRIVATE_OUTBOUND_DESTINATIONS", "").strip().lower() not in {"1", "true", "yes", "y"}
    tenant_secret_scope_enforced = tenant_config_core.TENANT_SCOPED_KEYS == tenant_config_core.SENSITIVE_KEYS
    idempotency_enforced = bool(idempotency_core.REDIS_URL) or idempotency_core.ENV != "production"

    security_events_row = await db.execute(
        select(func.count(SecurityAuditLog.id)).where(and_(
            SecurityAuditLog.tenant_id == tenant_filter,
            func.date(SecurityAuditLog.timestamp) >= last_30,
        ))
    )
    security_events_30d = int(security_events_row.scalar() or 0)

    failed_security_events_row = await db.execute(
        select(func.count(SecurityAuditLog.id)).where(and_(
            SecurityAuditLog.tenant_id == tenant_filter,
            func.date(SecurityAuditLog.timestamp) >= last_30,
            SecurityAuditLog.success.is_(False),
        ))
    )
    failed_security_events_30d = int(failed_security_events_row.scalar() or 0)

    credential_access_row = await db.execute(
        select(func.count(CredentialAccessLog.id)).where(and_(
            CredentialAccessLog.tenant_id == tenant_filter,
            func.date(CredentialAccessLog.accessed_at) >= last_30,
        ))
    )
    credential_access_30d = int(credential_access_row.scalar() or 0)

    rls_coverage = await _collect_rls_coverage(db)
    rls_coverage_ok = bool(rls_coverage["is_strictly_enforced"])

    controls = [
        {"key": "jwt_validation", "label": "JWT validation hardening", "ok": jwt_secure, "detail": f"algorithm={jwt_algorithm}"},
        {"key": "encryption_key", "label": "Encryption key quality", "ok": encryption_key_ok, "detail": "CLAIMFLOW_ENCRYPTION_KEY length and format"},
        {"key": "cors_strict", "label": "CORS production strictness", "ok": cors_strict, "detail": "No wildcard and HTTPS origins"},
        {"key": "tenant_secret_scope", "label": "Tenant-scoped sensitive settings", "ok": tenant_secret_scope_enforced, "detail": "TENANT_SCOPED_KEYS == SENSITIVE_KEYS"},
        {"key": "outbound_ssrf_guard", "label": "Outbound private destination guard", "ok": outbound_guard_strict, "detail": "ALLOW_PRIVATE_OUTBOUND_DESTINATIONS disabled"},
        {"key": "idempotency_store", "label": "Production idempotency backing store", "ok": idempotency_enforced, "detail": "Redis required in production"},
        {
            "key": "db_rls_policy_coverage",
            "label": "DB RLS policy + force coverage",
            "ok": rls_coverage_ok,
            "detail": (
                f"coverage={rls_coverage['coverage_pct']}% "
                f"forced={rls_coverage['forced_pct']}% "
                f"policy={rls_coverage['policy_pct']}%"
            ),
        },
    ]
    passing_controls = sum(1 for item in controls if item["ok"])
    maturity_score = round(((passing_controls / len(controls)) * 100.0) * 0.7 + (float(rls_coverage["coverage_pct"]) * 0.3), 1)
    security_failure_rate_pct = _percent(failed_security_events_30d, max(security_events_30d, 1))
    compliance_alerts = [
        _threshold_alert(
            key="rls_coverage_pct",
            label="RLS coverage below required threshold",
            value=float(rls_coverage["coverage_pct"]),
            threshold=100.0,
            direction="lt",
            warn_buffer=5.0,
        ),
        _threshold_alert(
            key="rls_forced_pct",
            label="RLS FORCE coverage below required threshold",
            value=float(rls_coverage["forced_pct"]),
            threshold=100.0,
            direction="lt",
            warn_buffer=5.0,
        ),
        _threshold_alert(
            key="security_failure_rate_pct",
            label="Security audit failure rate above threshold",
            value=float(security_failure_rate_pct),
            threshold=2.0,
            direction="gt",
            warn_buffer=0.5,
        ),
        _threshold_alert(
            key="maturity_score",
            label="Compliance maturity score below target",
            value=float(maturity_score),
            threshold=85.0,
            direction="lt",
            warn_buffer=5.0,
        ),
    ]
    compliance_breaches = sum(1 for alert in compliance_alerts if alert["status"] == "breach")
    compliance_warnings = sum(1 for alert in compliance_alerts if alert["status"] == "warning")

    return {
        "success": True,
        "data": {
            "as_of": now_utc.isoformat(),
            "maturity_score": maturity_score,
            "controls": controls,
            "rls_policy_coverage": {
                "tenant_tables": int(rls_coverage["tenant_tables"]),
                "policy_tables": int(rls_coverage["policy_tables"]),
                "coverage_pct": float(rls_coverage["coverage_pct"]),
                "forced_pct": float(rls_coverage["forced_pct"]),
                "strict_enforcement": bool(rls_coverage["is_strictly_enforced"]),
                "missing_row_security_tables": list(rls_coverage["missing_row_security_tables"]),
                "missing_force_rls_tables": list(rls_coverage["missing_force_rls_tables"]),
                "missing_policy_tables": list(rls_coverage["missing_policy_tables"]),
            },
            "audit_activity_30d": {
                "security_events": security_events_30d,
                "security_failures": failed_security_events_30d,
                "security_failure_rate_pct": security_failure_rate_pct,
                "credential_access_events": credential_access_30d,
            },
            "alerts": compliance_alerts,
            "alert_summary": {
                "breach_count": compliance_breaches,
                "warning_count": compliance_warnings,
                "ok_count": len(compliance_alerts) - compliance_breaches - compliance_warnings,
            },
        },
    }


@router.get("/rls-assurance")
async def rls_assurance(
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """
    Strict runtime assurance view for DB tenant RLS coverage.
    """
    current_user.require_role("admin")
    coverage = await _collect_rls_coverage(db)
    return {
        "success": True,
        "data": {
            "as_of": datetime.now(timezone.utc).isoformat(),
            **coverage,
        },
    }


@router.get("/scalability")
async def scalability_readiness(
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """
    Implementation/scalability readiness and execution risk signals.
    """
    current_user.require_role("billing")
    tenant_filter = current_user.tenant_id
    now_utc = datetime.now(timezone.utc)
    last_30 = (now_utc - timedelta(days=30)).date()

    scheduler_status = get_scheduler_status()
    queue_stats = get_credentialing_queue_stats()

    scheduler_jobs = scheduler_status.get("jobs", {})
    scheduler_runs = int(sum(int((job or {}).get("runs", 0)) for job in scheduler_jobs.values()))
    scheduler_failures = int(sum(int((job or {}).get("failures", 0)) for job in scheduler_jobs.values()))
    scheduler_skips_locked = int(sum(int((job or {}).get("skips_locked", 0)) for job in scheduler_jobs.values()))

    queue_runs = int(queue_stats.get("runs", 0) or 0)
    queue_claimed = int(queue_stats.get("items_claimed", 0) or 0)
    queue_failed = int(queue_stats.get("items_failed", 0) or 0)
    queue_stale_recovered = int(queue_stats.get("stale_recovered", 0) or 0)

    claim_backlog_row = await db.execute(
        select(func.count(Claim.id)).where(and_(
            Claim.tenant_id == tenant_filter,
            Claim.state.in_(["draft", "ready_to_submit", "submitted", "rejected"]),
        ))
    )
    claim_backlog = int(claim_backlog_row.scalar() or 0)

    submitted_30d_row = await db.execute(
        select(func.count(Claim.id)).where(and_(
            Claim.tenant_id == tenant_filter,
            Claim.submitted_date.isnot(None),
            func.date(Claim.submitted_date) >= last_30,
        ))
    )
    submitted_30d = int(submitted_30d_row.scalar() or 0)

    adjudicated_30d_row = await db.execute(
        select(func.count(Claim.id)).where(and_(
            Claim.tenant_id == tenant_filter,
            Claim.adjudicated_date.isnot(None),
            func.date(Claim.adjudicated_date) >= last_30,
        ))
    )
    adjudicated_30d = int(adjudicated_30d_row.scalar() or 0)

    credentialing_backlog_row = await db.execute(
        select(func.count(ProviderCredentialing.id)).where(and_(
            ProviderCredentialing.tenant_id == tenant_filter,
            ProviderCredentialing.credentialing_status.in_(["pending", "in_progress", "requires_review"]),
        ))
    )
    credentialing_backlog = int(credentialing_backlog_row.scalar() or 0)

    credentialing_completed_30d_row = await db.execute(
        select(func.count(ProviderCredentialing.id)).where(and_(
            ProviderCredentialing.tenant_id == tenant_filter,
            ProviderCredentialing.completed_at.isnot(None),
            func.date(ProviderCredentialing.completed_at) >= last_30,
        ))
    )
    credentialing_completed_30d = int(credentialing_completed_30d_row.scalar() or 0)

    enrollment_backlog_row = await db.execute(
        select(func.count(PayerCredentialingCase.id)).where(and_(
            PayerCredentialingCase.tenant_id == tenant_filter,
            PayerCredentialingCase.status.in_(["draft", "ready_to_submit", "submitted", "in_review", "additional_info_requested", "resubmission_required"]),
        ))
    )
    enrollment_backlog = int(enrollment_backlog_row.scalar() or 0)

    enrollment_approved_30d_row = await db.execute(
        select(func.count(PayerCredentialingCase.id)).where(and_(
            PayerCredentialingCase.tenant_id == tenant_filter,
            PayerCredentialingCase.status == "approved",
            PayerCredentialingCase.effective_date.isnot(None),
            PayerCredentialingCase.effective_date >= last_30,
        ))
    )
    enrollment_approved_30d = int(enrollment_approved_30d_row.scalar() or 0)

    claim_pressure = round(claim_backlog / max(submitted_30d, 1), 2)
    credentialing_pressure = round(credentialing_backlog / max(credentialing_completed_30d, 1), 2)
    enrollment_pressure = round(enrollment_backlog / max(enrollment_approved_30d, 1), 2)

    pool_size = int(os.getenv("DB_POOL_SIZE", "10"))
    max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    worker_count = int(os.getenv("WEB_CONCURRENCY", "1"))
    db_capacity = pool_size + max_overflow
    per_worker_capacity = round(db_capacity / max(worker_count, 1), 1)

    reliability_score = 100.0
    reliability_score -= min(30.0, _percent(scheduler_failures, max(scheduler_runs, 1)))
    reliability_score -= min(30.0, _percent(queue_failed, max(queue_claimed, 1)))
    reliability_score -= min(20.0, claim_pressure * 10.0)
    reliability_score -= min(20.0, credentialing_pressure * 10.0)
    reliability_score = round(max(0.0, reliability_score), 1)
    scheduler_failure_rate_pct = _percent(scheduler_failures, max(scheduler_runs, 1))
    queue_failure_rate_pct = _percent(queue_failed, max(queue_claimed, 1))
    scalability_alerts = [
        _threshold_alert(
            key="scheduler_failure_rate_pct",
            label="Scheduler failure rate above threshold",
            value=float(scheduler_failure_rate_pct),
            threshold=2.0,
            direction="gt",
            warn_buffer=0.5,
        ),
        _threshold_alert(
            key="queue_failure_rate_pct",
            label="Credentialing queue failure rate above threshold",
            value=float(queue_failure_rate_pct),
            threshold=2.0,
            direction="gt",
            warn_buffer=0.5,
        ),
        _threshold_alert(
            key="claims_pressure",
            label="Claims backlog pressure above threshold",
            value=float(claim_pressure),
            threshold=1.5,
            direction="gt",
            warn_buffer=0.2,
        ),
        _threshold_alert(
            key="credentialing_pressure",
            label="Credentialing backlog pressure above threshold",
            value=float(credentialing_pressure),
            threshold=1.5,
            direction="gt",
            warn_buffer=0.2,
        ),
        _threshold_alert(
            key="enrollment_pressure",
            label="Enrollment backlog pressure above threshold",
            value=float(enrollment_pressure),
            threshold=1.5,
            direction="gt",
            warn_buffer=0.2,
        ),
        _threshold_alert(
            key="readiness_score",
            label="Scalability readiness score below target",
            value=float(reliability_score),
            threshold=80.0,
            direction="lt",
            warn_buffer=5.0,
        ),
    ]
    scalability_breaches = sum(1 for alert in scalability_alerts if alert["status"] == "breach")
    scalability_warnings = sum(1 for alert in scalability_alerts if alert["status"] == "warning")

    return {
        "success": True,
        "data": {
            "as_of": now_utc.isoformat(),
            "readiness_score": reliability_score,
            "capacity": {
                "db_pool_size": pool_size,
                "db_max_overflow": max_overflow,
                "db_total_capacity": db_capacity,
                "web_concurrency": worker_count,
                "db_capacity_per_worker": per_worker_capacity,
            },
            "job_reliability": {
                "scheduler_enabled": bool(scheduler_status.get("enabled")),
                "scheduler_running": bool(scheduler_status.get("running")),
                "scheduler_runs": scheduler_runs,
                "scheduler_failures": scheduler_failures,
                "scheduler_skips_locked": scheduler_skips_locked,
                "scheduler_failure_rate_pct": scheduler_failure_rate_pct,
                "queue_runs": queue_runs,
                "queue_items_claimed": queue_claimed,
                "queue_items_failed": queue_failed,
                "queue_failure_rate_pct": queue_failure_rate_pct,
                "queue_stale_recovered": queue_stale_recovered,
            },
            "throughput_30d": {
                "claims_submitted": submitted_30d,
                "claims_adjudicated": adjudicated_30d,
                "credentialing_completed": credentialing_completed_30d,
                "enrollment_approved": enrollment_approved_30d,
            },
            "backlog": {
                "claims": claim_backlog,
                "credentialing": credentialing_backlog,
                "payer_enrollment": enrollment_backlog,
            },
            "pressure": {
                "claims_backlog_to_submit_ratio": claim_pressure,
                "credentialing_backlog_to_completed_ratio": credentialing_pressure,
                "enrollment_backlog_to_approved_ratio": enrollment_pressure,
            },
            "alerts": scalability_alerts,
            "alert_summary": {
                "breach_count": scalability_breaches,
                "warning_count": scalability_warnings,
                "ok_count": len(scalability_alerts) - scalability_breaches - scalability_warnings,
            },
        },
    }
