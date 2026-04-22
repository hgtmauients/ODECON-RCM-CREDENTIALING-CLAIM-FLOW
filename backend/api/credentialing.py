"""
Provider Credentialing API
"""
import hashlib
import hmac
import os
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Dict, Any, Optional
from datetime import datetime
import logging
import asyncio

from core.database import get_db
from api.auth import get_current_user, Principal
from api.schemas import ProviderCreate, ProviderUpdate, ApproveRequest, RejectRequest, ProviderSignupWebhook
from models.credentialing import ProviderCredentialing, CredentialingVerificationLog
from services.credentialing_service import credentialing_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/credentialing", tags=["Credentialing"])


def _spawn_background(coro, name: str) -> None:
    """
    asyncio.create_task with error visibility.
    A bare create_task can swallow exceptions; this wrapper logs them.
    """
    task = asyncio.create_task(coro, name=name)

    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.exception("Background task %s failed", name, exc_info=exc)

    task.add_done_callback(_on_done)

WEBHOOK_REPLAY_WINDOW = 300  # 5 minutes


async def _verify_webhook_signature(payload: bytes, signature: str, secret: str, timestamp: str = "") -> bool:
    """Verify HMAC-SHA256 webhook signature with replay protection (Redis-backed when configured)."""
    if not secret:
        if os.getenv("ENV", "development") == "development":
            logger.warning("WEBHOOK_SECRET not set; allowing in dev mode only")
            return True
        logger.error("WEBHOOK_SECRET not configured - rejecting webhook")
        return False

    if timestamp:
        try:
            ts = int(timestamp)
            import time
            if abs(time.time() - ts) > WEBHOOK_REPLAY_WINDOW:
                logger.warning("Webhook timestamp outside acceptable window")
                return False
        except ValueError:
            pass

    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return False

    # Signature valid — now check for replay (multi-worker safe via Redis).
    from core.nonce_store import is_replay
    if await is_replay(signature):
        logger.warning("Webhook signature replay detected")
        return False

    return True


@router.post("/webhook/provider-signup")
async def handle_provider_signup(
    signup_data: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Webhook endpoint for provider signups with signature validation."""
    signature = request.headers.get("X-Webhook-Signature", "")
    timestamp = request.headers.get("X-Webhook-Timestamp", "")
    body = await request.body()

    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required for webhooks")

    from core.tenant_config import get_tenant_setting
    webhook_secret = await get_tenant_setting(db, tenant_id, "webhook_secret", default=os.getenv("WEBHOOK_SECRET", ""))
    if not await _verify_webhook_signature(body, signature, webhook_secret, timestamp):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        provider_id = f"PROV_{signup_data.get('npi', 'unknown')}_{int(datetime.utcnow().timestamp())}"

        credentialing = ProviderCredentialing(
            tenant_id=tenant_id,
            provider_id=provider_id,
            signup_data=signup_data,
            license_url=signup_data.get("license_url"),
            credentialing_status="pending",
        )
        db.add(credentialing)
        await db.commit()

        _spawn_background(run_credentialing_checks(provider_id, signup_data, tenant_id), "credentialing-checks")

        return {
            "success": True,
            "provider_id": provider_id,
            "status": "credentialing_initiated",
        }
    except Exception as e:
        logger.error(f"Error handling provider signup: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{provider_id}")
async def get_credentialing_status(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Get credentialing status - scoped to tenant"""
    try:
        result = await db.execute(
            select(ProviderCredentialing).where(and_(
                ProviderCredentialing.provider_id == provider_id,
                ProviderCredentialing.tenant_id == current_user.tenant_id,
            ))
        )
        credentialing = result.scalar_one_or_none()
        if not credentialing:
            raise HTTPException(status_code=404, detail="Credentialing record not found")

        return {
            "success": True,
            "data": {
                "provider_id": credentialing.provider_id,
                "credentialing_status": credentialing.credentialing_status,
                "overall_score": credentialing.overall_score,
                "npi_verification": credentialing.npi_verification,
                "state_license_verification": credentialing.state_license_verification,
                "background_check": credentialing.background_check,
                "oig_check": credentialing.oig_check,
                "sam_check": credentialing.sam_check,
                "signup_date": credentialing.signup_date.isoformat() if credentialing.signup_date else None,
                "completed_at": credentialing.completed_at.isoformat() if credentialing.completed_at else None,
                "admin_notes": credentialing.admin_notes,
                "rejection_reason": credentialing.rejection_reason,
                "licenses": credentialing.licenses or [],
                "specialties": credentialing.specialties or [],
                "dea_certificates": credentialing.dea_certificates or [],
                "cned_certificates": credentialing.cned_certificates or [],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting credentialing status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("")
async def list_credentialing_queue(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List credentialing queue - scoped to tenant"""
    try:
        query = select(ProviderCredentialing).where(
            ProviderCredentialing.tenant_id == current_user.tenant_id
        )
        if status:
            query = query.where(ProviderCredentialing.credentialing_status == status)

        result = await db.execute(query.order_by(ProviderCredentialing.created_at.desc()))
        credentialing_records = result.scalars().all()

        return {
            "success": True,
            "data": [{
                "provider_id": cr.provider_id,
                "signup_data": cr.signup_data,
                "credentialing_status": cr.credentialing_status,
                "overall_score": cr.overall_score,
                "signup_date": cr.signup_date.isoformat() if cr.signup_date else None,
                "completed_at": cr.completed_at.isoformat() if cr.completed_at else None,
            } for cr in credentialing_records],
        }
    except Exception as e:
        logger.error(f"Error listing credentialing queue: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/manual")
async def create_provider_manual(
    body: ProviderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Manually create a provider credentialing record (no webhook needed)."""
    current_user.require_role("admin")

    import uuid
    npi = body.npi
    provider_id = f"PROV_{npi}_{uuid.uuid4().hex[:8]}"

    credentialing = ProviderCredentialing(
        tenant_id=current_user.tenant_id,
        provider_id=provider_id,
        signup_data={
            "first_name": body.first_name,
            "last_name": body.last_name,
            "email": body.email or "",
            "npi": npi,
            "state_code": body.state_code or "",
            "license_number": body.license_number or "",
            "specialty": body.specialty or "",
            "provider_type": body.provider_type or "MD",
            "date_of_birth": body.date_of_birth or "",
            "phone": body.phone or "",
        },
        licenses=[lic.model_dump() for lic in (body.licenses or [])],
        specialties=[sp.model_dump() for sp in (body.specialties or [])],
        dea_certificates=[d.model_dump() for d in (body.dea_certificates or [])],
        cned_certificates=[c.model_dump() for c in (body.cned_certificates or [])],
        license_url=body.license_url,
        credentialing_status="pending",
    )
    db.add(credentialing)
    await db.commit()

    if body.run_checks:
        _spawn_background(run_credentialing_checks(provider_id, credentialing.signup_data, current_user.tenant_id), "credentialing-checks")

    return {
        "success": True,
        "provider_id": provider_id,
        "status": "credentialing_initiated" if body.run_checks else "pending",
    }


@router.put("/{provider_id}")
async def update_provider(
    provider_id: str,
    body: ProviderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Update provider credentialing record."""
    current_user.require_role("admin")
    result = await db.execute(
        select(ProviderCredentialing).where(and_(
            ProviderCredentialing.provider_id == provider_id,
            ProviderCredentialing.tenant_id == current_user.tenant_id,
        ))
    )
    credentialing = result.scalar_one_or_none()
    if not credentialing:
        raise HTTPException(status_code=404, detail="Provider not found")

    updates = body.model_dump(exclude_unset=True)
    updated_data = {**(credentialing.signup_data or {})}
    signup_fields = {"first_name", "last_name", "email", "npi", "state_code",
                     "license_number", "specialty", "provider_type", "date_of_birth", "phone"}
    for f in signup_fields:
        if f in updates and updates[f] is not None:
            updated_data[f] = updates[f]
    credentialing.signup_data = updated_data

    if body.admin_notes is not None:
        credentialing.admin_notes = body.admin_notes
    if body.license_url is not None:
        credentialing.license_url = body.license_url
    if body.licenses is not None:
        credentialing.licenses = [lic.model_dump() for lic in body.licenses]
    if body.specialties is not None:
        credentialing.specialties = [sp.model_dump() for sp in body.specialties]
    if body.dea_certificates is not None:
        credentialing.dea_certificates = [d.model_dump() for d in body.dea_certificates]
    if body.cned_certificates is not None:
        credentialing.cned_certificates = [c.model_dump() for c in body.cned_certificates]

    await db.commit()
    return {"success": True, "message": "Provider updated"}


@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Delete provider credentialing record."""
    current_user.require_role("admin")
    result = await db.execute(
        select(ProviderCredentialing).where(and_(
            ProviderCredentialing.provider_id == provider_id,
            ProviderCredentialing.tenant_id == current_user.tenant_id,
        ))
    )
    credentialing = result.scalar_one_or_none()
    if not credentialing:
        raise HTTPException(status_code=404, detail="Provider not found")

    await db.delete(credentialing)
    await db.commit()
    return {"success": True, "message": "Provider deleted"}


@router.post("/{provider_id}/rerun-checks")
async def rerun_credentialing_checks(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Re-run all verification checks for a provider."""
    current_user.require_role("admin")
    result = await db.execute(
        select(ProviderCredentialing).where(and_(
            ProviderCredentialing.provider_id == provider_id,
            ProviderCredentialing.tenant_id == current_user.tenant_id,
        ))
    )
    credentialing = result.scalar_one_or_none()
    if not credentialing:
        raise HTTPException(status_code=404, detail="Provider not found")

    credentialing.credentialing_status = "pending"
    await db.commit()

    _spawn_background(run_credentialing_checks(provider_id, credentialing.signup_data or {}, current_user.tenant_id), "credentialing-checks")
    return {"success": True, "message": "Verification checks re-initiated"}


@router.post("/{provider_id}/approve")
async def approve_provider(
    provider_id: str,
    body: Optional[ApproveRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Approve provider credentialing - scoped to tenant"""
    current_user.require_role("admin")
    notes = body.notes if body else None
    try:
        result = await db.execute(
            select(ProviderCredentialing).where(and_(
                ProviderCredentialing.provider_id == provider_id,
                ProviderCredentialing.tenant_id == current_user.tenant_id,
            ))
        )
        credentialing = result.scalar_one_or_none()
        if not credentialing:
            raise HTTPException(status_code=404, detail="Credentialing record not found")

        credentialing.credentialing_status = "passed"
        credentialing.verified_by = current_user.user_id
        credentialing.verified_at = datetime.utcnow()
        credentialing.admin_notes = notes
        await db.commit()

        # Auto-create payer enrollment cases for the approved provider
        payer_cases_result = {}
        try:
            from services.smart_payer_enrollment import create_smart_payer_enrollment_cases
            payer_cases_result = await create_smart_payer_enrollment_cases(
                provider_id=provider_id,
                db=db,
                provider_verification_data=credentialing.signup_data or {},
                tenant_id=current_user.tenant_id,
            )
            logger.info(f"Auto-created payer enrollment cases for {provider_id}: {payer_cases_result}")
        except Exception as e:
            logger.warning(f"Payer case auto-creation failed for {provider_id}: {e}")

        return {
            "success": True,
            "message": "Provider approved",
            "payer_enrollment": payer_cases_result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving provider: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{provider_id}/reject")
async def reject_provider(
    provider_id: str,
    body: RejectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Reject provider credentialing - scoped to tenant"""
    current_user.require_role("admin")
    reason = body.reason
    try:
        result = await db.execute(
            select(ProviderCredentialing).where(and_(
                ProviderCredentialing.provider_id == provider_id,
                ProviderCredentialing.tenant_id == current_user.tenant_id,
            ))
        )
        credentialing = result.scalar_one_or_none()
        if not credentialing:
            raise HTTPException(status_code=404, detail="Credentialing record not found")

        credentialing.credentialing_status = "failed"
        credentialing.verified_by = current_user.user_id
        credentialing.verified_at = datetime.utcnow()
        credentialing.rejection_reason = reason
        await db.commit()

        return {"success": True, "message": "Provider rejected"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting provider: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


async def run_credentialing_checks(provider_id: str, signup_data: Dict[str, Any], tenant_id: str):
    """Run all credentialing checks in parallel (background task)."""
    from core.database import async_session_factory

    async with async_session_factory() as db:
        try:
            result = await db.execute(
                select(ProviderCredentialing).where(and_(
                    ProviderCredentialing.provider_id == provider_id,
                    ProviderCredentialing.tenant_id == tenant_id,
                ))
            )
            credentialing = result.scalar_one_or_none()
            if not credentialing:
                return

            credentialing.credentialing_status = "in_progress"
            await db.commit()

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
            api_cert_result = results.get("api_cert_verification", {})
            if api_cert_result.get("verified") and api_cert_result.get("status") == "ACTIVE":
                credentialing.state_license_verification = {
                    "verified": True,
                    "license_number": api_cert_result.get("license_number"),
                    "status": api_cert_result.get("status"),
                    "expiration_date": api_cert_result.get("expiration_date"),
                    "full_name": api_cert_result.get("full_name"),
                    "disciplinary_flag": api_cert_result.get("disciplinary_flag"),
                    "source": "api_cert",
                }
                # Also use API-Cert exclusion results if available
                if api_cert_result.get("oig_excluded") is not None:
                    credentialing.oig_check = {
                        "excluded": api_cert_result["oig_excluded"],
                        "source": "api_cert",
                    }
                if api_cert_result.get("sam_excluded") is not None:
                    credentialing.sam_check = {
                        "excluded": api_cert_result["sam_excluded"],
                        "source": "api_cert",
                    }
                logger.info(f"API-Cert verified license for {provider_id} in {signup_data.get('state_code')}")
            elif api_cert_result.get("status") == "NOT_COVERED":
                logger.info(f"API-Cert does not cover {signup_data.get('state_code')} - using internal checks only")

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
                            active = [l for l in caqh_licenses if l.get("status", "").upper() in ("ACTIVE", "CURRENT", "")]
                            if active and not results.get("state_license_verification", {}).get("verified"):
                                credentialing.state_license_verification = {
                                    "verified": True,
                                    "licenses": active,
                                    "source": "caqh_proview",
                                }
                                score = credentialing_service.calculate_credentialing_score({
                                    **results,
                                    "state_license_verification": credentialing.state_license_verification,
                                })
                                status = credentialing_service.determine_status(score)
                            logger.info(f"CAQH enrichment for {provider_id}: {len(caqh_licenses)} licenses found")
                except Exception as caqh_err:
                    logger.warning(f"CAQH enrichment failed for {provider_id}: {caqh_err}")

            credentialing.overall_score = score
            credentialing.credentialing_status = status
            credentialing.completed_at = datetime.utcnow()
            await db.commit()

            logger.info(f"Credentialing completed for {provider_id}: {status} (score: {score})")
        except Exception as e:
            # On any failure mid-flight, do NOT leave the provider stuck in
            # in_progress forever. Roll back the transaction, then in a fresh
            # session set the status to requires_review so an operator can
            # see the error and act on it.
            logger.exception(f"Error running credentialing checks for {provider_id}: {e}")
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
                logger.error(f"Failed to set recovery status for {provider_id}: {recovery_err}")
