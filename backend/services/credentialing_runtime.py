"""
Credentialing runtime execution helpers.

This module owns the background verification execution path so jobs and API
can depend on a service-layer function instead of importing each other.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import and_, select

from models.credentialing import ProviderCredentialing
from services.credentialing_service import credentialing_service

logger = logging.getLogger(__name__)
_IN_PROGRESS_STALE_MINUTES = int(os.getenv("CREDENTIALING_IN_PROGRESS_STALE_MINUTES", "30"))


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _collect_associated_licenses(
    *,
    api_cert_result: Dict[str, Any],
    prior_state_license: Dict[str, Any],
) -> list[Dict[str, Any]]:
    """
    Keep all license artifacts we can safely preserve for audit/review UX.
    """
    licenses: list[Dict[str, Any]] = []
    for key in ("associated_licenses", "licenses", "matches", "candidate_licenses"):
        for item in _as_list(api_cert_result.get(key)):
            if isinstance(item, dict):
                licenses.append(item)
    for item in _as_list(prior_state_license.get("licenses")):
        if isinstance(item, dict):
            licenses.append(item)

    # Deduplicate while preserving order.
    seen: set[str] = set()
    deduped: list[Dict[str, Any]] = []
    for item in licenses:
        marker = (
            str(item.get("license_number", "")),
            str(item.get("state", "")),
            str(item.get("status", "")),
            str(item.get("expiration_date", "")),
        )
        key = "|".join(marker)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _merge_state_license_with_caqh(
    *,
    state_license_verification: Dict[str, Any],
    caqh_licenses: list[Dict[str, Any]],
    state_code: str,
    preferred_license_number: str,
) -> Dict[str, Any]:
    """
    Backfill missing license metadata from CAQH without dropping primary results.
    """
    merged = dict(_as_dict(state_license_verification))
    licenses = [lic for lic in caqh_licenses if isinstance(lic, dict)]
    if not licenses:
        return merged

    active = [l for l in licenses if str(l.get("status", "")).upper() in ("ACTIVE", "CURRENT", "VALID", "")]
    preferred = preferred_license_number or str(merged.get("license_number", "") or "")

    chosen: Dict[str, Any] | None = None
    if preferred:
        for item in active or licenses:
            if str(item.get("license_number", "")).strip() == preferred:
                chosen = item
                break
    if chosen is None and state_code:
        for item in active or licenses:
            if str(item.get("state", "")).upper() == str(state_code).upper():
                chosen = item
                break
    if chosen is None:
        chosen = (active or licenses)[0]

    if not merged:
        merged = {
            "verified": True,
            "source": "caqh_proview",
        }
    merged.setdefault("verified", True)
    merged.setdefault("source", "caqh_proview")
    merged.setdefault("state", chosen.get("state") or state_code)
    if not merged.get("license_number"):
        merged["license_number"] = chosen.get("license_number")
    if not merged.get("status"):
        merged["status"] = chosen.get("status")
    if not merged.get("issue_date"):
        merged["issue_date"] = chosen.get("issue_date")
    if not merged.get("expiration_date"):
        merged["expiration_date"] = chosen.get("expiration_date")

    associated: list[Dict[str, Any]] = []
    for item in _as_list(merged.get("associated_licenses")):
        if isinstance(item, dict):
            associated.append(item)
    associated.extend(licenses)

    deduped: list[Dict[str, Any]] = []
    by_key: dict[str, Dict[str, Any]] = {}
    for item in associated:
        key = "|".join((
            str(item.get("license_number", "")),
            str(item.get("state", "")),
            str(item.get("status", "")),
        ))
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = dict(item)
            continue
        # Prefer the richer record when duplicate license/state/status appears.
        if (not existing.get("expiration_date")) and item.get("expiration_date"):
            existing["expiration_date"] = item.get("expiration_date")
        if (not existing.get("issue_date")) and item.get("issue_date"):
            existing["issue_date"] = item.get("issue_date")
        by_key[key] = existing
    deduped.extend(by_key.values())
    merged["associated_licenses"] = deduped
    return merged


async def run_credentialing_checks(
    provider_id: str,
    signup_data: Dict[str, Any],
    tenant_id: str,
    *,
    preclaimed: bool = False,
) -> None:
    """Run all credentialing checks in parallel (background task)."""
    from core.database import async_session_factory

    async with async_session_factory() as db:
        try:
            result = await db.execute(
                select(ProviderCredentialing)
                .where(and_(
                    ProviderCredentialing.provider_id == provider_id,
                    ProviderCredentialing.tenant_id == tenant_id,
                ))
                .with_for_update()
            )
            credentialing = result.scalar_one_or_none()
            if not credentialing:
                return

            now = _utcnow_naive()
            if not preclaimed:
                if credentialing.credentialing_status in ("passed", "failed"):
                    return
                if (
                    credentialing.credentialing_status == "in_progress"
                    and credentialing.started_at
                    and (now - credentialing.started_at).total_seconds() < (_IN_PROGRESS_STALE_MINUTES * 60)
                ):
                    # Another worker is actively processing this provider.
                    return

                credentialing.credentialing_status = "in_progress"
                credentialing.started_at = now
                credentialing.completed_at = None
                await db.commit()
            elif credentialing.credentialing_status != "in_progress":
                # Queue pre-claimed this row, but status changed before execution.
                return

            check_keys = []
            check_coros = []

            if signup_data.get("npi"):
                check_keys.append("npi_verification")
                check_coros.append(credentialing_service.verify_npi(signup_data["npi"]))
            if signup_data.get("state_code") and signup_data.get("license_number"):
                check_keys.append("state_license_verification")
                check_coros.append(credentialing_service.verify_state_license(
                    signup_data["state_code"], signup_data["license_number"],
                    f"{signup_data.get('first_name', '')} {signup_data.get('last_name', '')}",
                    signup_data.get("date_of_birth", ""),
                ))
            check_keys.append("background_check")
            check_coros.append(credentialing_service.run_background_check(
                signup_data.get("first_name", ""), signup_data.get("last_name", ""),
                signup_data.get("date_of_birth", ""),
            ))
            if signup_data.get("npi"):
                check_keys.append("oig_check")
                check_coros.append(credentialing_service.check_oig_exclusion(
                    f"{signup_data.get('first_name', '')} {signup_data.get('last_name', '')}",
                    signup_data.get("date_of_birth", ""), signup_data["npi"],
                ))
            check_keys.append("sam_check")
            check_coros.append(credentialing_service.check_sam_exclusion(
                f"{signup_data.get('first_name', '')} {signup_data.get('last_name', '')}",
                signup_data.get("date_of_birth", ""),
                signup_data.get("npi"),
            ))

            # API-Cert: real-time state license verification (50 states, free tier)
            from services.api_cert import get_tenant_client as get_api_cert_client, is_configured_for_tenant as api_cert_configured_for_tenant
            if await api_cert_configured_for_tenant(db, tenant_id) and signup_data.get("state_code") and signup_data.get("last_name"):
                tenant_api_cert = await get_api_cert_client(db, tenant_id)
                check_keys.append("api_cert_verification")
                check_coros.append(tenant_api_cert.verify_license(
                    last_name=signup_data["last_name"],
                    state=signup_data["state_code"],
                    license_type=signup_data.get("provider_type", "MD"),
                    first_name=signup_data.get("first_name"),
                    license_number=signup_data.get("license_number"),
                ))

            results_list = await asyncio.gather(*check_coros, return_exceptions=True)
            results = {}
            for key, value in zip(check_keys, results_list):
                results[key] = value if not isinstance(value, Exception) else {"error": str(value)}

            score = credentialing_service.calculate_credentialing_score(results)
            status = credentialing_service.determine_status(score)

            credentialing.npi_verification = results.get("npi_verification")
            credentialing.state_license_verification = results.get("state_license_verification")
            credentialing.background_check = results.get("background_check")
            credentialing.oig_check = results.get("oig_check")
            credentialing.sam_check = results.get("sam_check")

            # If API-Cert verified the license, upgrade state_license_verification
            api_cert_result = _as_dict(results.get("api_cert_verification"))
            prior_state_license = _as_dict(credentialing.state_license_verification)
            if api_cert_result.get("verified") and api_cert_result.get("status") == "ACTIVE":
                associated_licenses = _collect_associated_licenses(
                    api_cert_result=api_cert_result,
                    prior_state_license=prior_state_license,
                )
                credentialing.state_license_verification = {
                    "verified": True,
                    "state": signup_data.get("state_code"),
                    "license_number": api_cert_result.get("license_number"),
                    "status": api_cert_result.get("status"),
                    "issue_date": api_cert_result.get("issue_date"),
                    "expiration_date": api_cert_result.get("expiration_date"),
                    "full_name": api_cert_result.get("full_name"),
                    "npi": api_cert_result.get("npi"),
                    "disciplinary_flag": api_cert_result.get("disciplinary_flag"),
                    "discipline_history": prior_state_license.get("discipline_history", []),
                    "dea_number": api_cert_result.get("dea_number"),
                    "dea_status": api_cert_result.get("dea_status"),
                    "dea_expiration": api_cert_result.get("dea_expiration"),
                    "cms_precluded": api_cert_result.get("cms_precluded"),
                    "match_count": api_cert_result.get("match_count"),
                    "latency_ms": api_cert_result.get("latency_ms"),
                    "associated_licenses": associated_licenses,
                    "source": "api_cert",
                    "verified_at": _utcnow_naive().isoformat(),
                }
                # Also use API-Cert exclusion results if available
                if api_cert_result.get("oig_excluded") is not None:
                    credentialing.oig_check = {
                        "verified": True,
                        "excluded": api_cert_result["oig_excluded"],
                        "source": "api_cert",
                        "checked_at": _utcnow_naive().isoformat(),
                    }
                if api_cert_result.get("sam_excluded") is not None:
                    credentialing.sam_check = {
                        "verified": True,
                        "excluded": api_cert_result["sam_excluded"],
                        "source": "api_cert",
                        "checked_at": _utcnow_naive().isoformat(),
                    }
                logger.info("API-Cert verified license for %s in %s", provider_id, signup_data.get("state_code"))
            elif api_cert_result.get("status") == "NOT_COVERED":
                logger.info("API-Cert does not cover %s - using internal checks only", signup_data.get("state_code"))

            # Recalculate score with potentially upgraded results
            final_results = {
                "npi_verification": credentialing.npi_verification,
                "state_license_verification": credentialing.state_license_verification,
                "background_check": credentialing.background_check,
                "oig_check": credentialing.oig_check,
                "sam_check": credentialing.sam_check,
            }
            score = credentialing_service.calculate_credentialing_score(final_results)
            status = credentialing_service.determine_status(score)

            # CAQH enrichment (if configured, as additional data source)
            from services.caqh_proview import get_tenant_client as get_caqh_client, is_configured_for_tenant as caqh_configured_for_tenant
            if await caqh_configured_for_tenant(db, tenant_id) and signup_data.get("npi"):
                try:
                    tenant_caqh = await get_caqh_client(db, tenant_id)
                    caqh_search = await tenant_caqh.search_by_npi(signup_data["npi"])
                    if caqh_search.get("found"):
                        caqh_id = caqh_search["caqh_provider_id"]
                        caqh_data = await tenant_caqh.get_provider_data(caqh_id)
                        if caqh_data.get("success"):
                            caqh_licenses = caqh_data.get("licenses", [])
                            merged_license = _merge_state_license_with_caqh(
                                state_license_verification=_as_dict(credentialing.state_license_verification),
                                caqh_licenses=_as_list(caqh_licenses),
                                state_code=str(signup_data.get("state_code", "")),
                                preferred_license_number=str(signup_data.get("license_number", "")),
                            )
                            if merged_license:
                                credentialing.state_license_verification = merged_license
                                score = credentialing_service.calculate_credentialing_score({
                                    **results,
                                    "state_license_verification": merged_license,
                                })
                                status = credentialing_service.determine_status(score)
                            logger.info("CAQH enrichment for %s: %d licenses found", provider_id, len(caqh_licenses))
                except Exception as caqh_err:
                    logger.warning("CAQH enrichment failed for %s: %s", provider_id, caqh_err)

            credentialing.overall_score = score
            credentialing.credentialing_status = status
            credentialing.completed_at = _utcnow_naive()
            await db.commit()

            logger.info("Credentialing completed for %s: %s (score: %s)", provider_id, status, score)
        except Exception as e:
            # On any failure mid-flight, do NOT leave the provider stuck in
            # in_progress forever. Roll back the transaction, then in a fresh
            # session set the status to requires_review so an operator can
            # see the error and act on it.
            logger.exception("Error running credentialing checks for %s: %s", provider_id, e)
            try:
                await db.rollback()
            except Exception:
                pass
            try:
                async with async_session_factory() as recovery_db:
                    recovery_result = await recovery_db.execute(
                        select(ProviderCredentialing).where(and_(
                            ProviderCredentialing.provider_id == provider_id,
                            ProviderCredentialing.tenant_id == tenant_id,
                        ))
                    )
                    rec = recovery_result.scalar_one_or_none()
                    if rec and rec.credentialing_status in ("pending", "in_progress"):
                        rec.credentialing_status = "requires_review"
                        rec.admin_notes = (rec.admin_notes or "") + f"\n[auto] verification job failed: {e}"
                        await recovery_db.commit()
            except Exception as recovery_err:
                logger.error("Failed to set recovery status for %s: %s", provider_id, recovery_err)
