"""
Payer Profiles API
CRUD operations for payer profiles with credential management
Ops can configure everything in the UI - no code changes needed
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timezone
import logging
import csv
import io
import os

from core.database import get_db
from core.audit import log_audit_event
from core.outbound_guard import assert_safe_http_url
from models.rcm import (
    PayerProfile,
    PayerRule,
    TradingPartnerConnection,
    FeeSchedule,
    PayerProfileVersion,
)
from api.auth import get_current_user, Principal
from services.encryption import encrypt_credential

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rcm/payers", tags=["RCM - Payer Profiles"])


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

# Fields that callers must never be allowed to overwrite via the bulk-update path.
# tenant_id absence here is the v9-NEW-H1 reaffirmed bug — once excluded, the
# payer cannot be reassigned to another tenant via PUT /rcm/payers/{id}.
_PROTECTED_PAYER_FIELDS = frozenset({"id", "tenant_id", "created_at", "created_by"})
_PROTECTED_RULE_FIELDS = frozenset({"id", "tenant_id", "payer_id", "created_at", "created_by"})

# CSV upload limits (configurable per env).
MAX_FEE_SCHEDULE_BYTES = int(os.getenv("MAX_FEE_SCHEDULE_BYTES", str(20 * 1024 * 1024)))  # 20 MB


async def _verify_payer_tenant(payer_id: int, tenant_id: str, db: AsyncSession) -> None:
    """Verify payer belongs to the current user's tenant. Raises 404 if not."""
    check = await db.execute(
        select(PayerProfile.id).where(and_(PayerProfile.id == payer_id, PayerProfile.tenant_id == tenant_id))
    )
    if not check.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Payer not found")


# ==================== PAYER PROFILES ====================

@router.get("")
async def list_payers(
    state_code: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_draft: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user)
):
    """
    List all payer profiles
    Filterable by state, active status, draft status, and search query.
    Pass no is_active / is_draft to see all (including drafts).
    """
    current_user.require_role("billing")
    try:
        query = select(PayerProfile).where(PayerProfile.tenant_id == current_user.tenant_id)

        if state_code:
            query = query.where(PayerProfile.state_code == state_code)

        if is_active is not None:
            query = query.where(PayerProfile.is_active == is_active)

        if is_draft is not None:
            query = query.where(PayerProfile.is_draft == is_draft)
        
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    PayerProfile.name.ilike(search_term),
                    PayerProfile.display_name.ilike(search_term),
                    PayerProfile.payer_id.ilike(search_term)
                )
            )
        
        # Order by name
        query = query.order_by(PayerProfile.name).limit(limit).offset(offset)
        
        result = await db.execute(query)
        payers = result.scalars().all()
        
        # Get total count
        count_query = select(func.count(PayerProfile.id)).where(PayerProfile.tenant_id == current_user.tenant_id)
        if state_code:
            count_query = count_query.where(PayerProfile.state_code == state_code)
        if is_active is not None:
            count_query = count_query.where(PayerProfile.is_active == is_active)
        if is_draft is not None:
            count_query = count_query.where(PayerProfile.is_draft == is_draft)
        
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        return {
            "success": True,
            "data": [{
                "id": p.id,
                "name": p.name,
                "display_name": p.display_name,
                "payer_id": p.payer_id,
                "state_code": p.state_code,
                "clearinghouse": p.clearinghouse,
                "is_active": p.is_active,
                "is_draft": p.is_draft,
                "version": p.version,
                "has_contract": p.has_contract,
                "supports_telehealth": p.supports_telehealth,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None
            } for p in payers],
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error listing payers: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{payer_id}")
async def get_payer(
    payer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user)
):
    """
    Get full payer profile with all details
    """
    current_user.require_role("billing")
    try:
        result = await db.execute(
            select(PayerProfile).where(and_(PayerProfile.id == payer_id, PayerProfile.tenant_id == current_user.tenant_id))
        )
        payer = result.scalar_one_or_none()
        
        if not payer:
            raise HTTPException(status_code=404, detail="Payer not found")
        
        # Get related data counts
        rules_count_result = await db.execute(
            select(func.count(PayerRule.id)).where(PayerRule.payer_id == payer_id)
        )
        rules_count = rules_count_result.scalar() or 0
        
        connections_count_result = await db.execute(
            select(func.count(TradingPartnerConnection.id)).where(TradingPartnerConnection.payer_id == payer_id)
        )
        connections_count = connections_count_result.scalar() or 0
        
        fee_schedules_count_result = await db.execute(
            select(func.count(FeeSchedule.id)).where(FeeSchedule.payer_id == payer_id)
        )
        fee_schedules_count = fee_schedules_count_result.scalar() or 0
        
        return {
            "success": True,
            "data": {
                # Identity
                "id": payer.id,
                "name": payer.name,
                "display_name": payer.display_name,
                "payer_id": payer.payer_id,
                "naic_code": payer.naic_code,
                "plan_ids": payer.plan_ids,
                
                # Connectivity
                "clearinghouse": payer.clearinghouse,
                "trading_partner_id": payer.trading_partner_id,
                "submitter_id": payer.submitter_id,
                "receiver_id": payer.receiver_id,
                "connection_method": payer.connection_method,
                "endpoint_url": payer.endpoint_url,
                
                # Formats & Rules
                "format_837_type": payer.format_837_type,
                "loop_segment_overrides": payer.loop_segment_overrides,
                "supports_pwk_attachments": payer.supports_pwk_attachments,
                "attachment_method": payer.attachment_method,
                
                # Telehealth
                "supports_telehealth": payer.supports_telehealth,
                "telehealth_modifiers": payer.telehealth_modifiers,
                "telehealth_pos_codes": payer.telehealth_pos_codes,
                "telehealth_parity": payer.telehealth_parity,
                
                # Requirements
                "requires_taxonomy": payer.requires_taxonomy,
                "requires_npi_type_2": payer.requires_npi_type_2,
                "requires_tin": payer.requires_tin,
                "requires_clia": payer.requires_clia,
                "facility_professional_split": payer.facility_professional_split,
                
                # Eligibility/Status/Auth
                "supports_270_271": payer.supports_270_271,
                "supports_276_277": payer.supports_276_277,
                "supports_278_auth": payer.supports_278_auth,
                "auth_portal_url": payer.auth_portal_url,
                "auth_portal_login_required": payer.auth_portal_login_required,
                
                # ERA/EFT
                "supports_835_era": payer.supports_835_era,
                "era_enrollment_required": payer.era_enrollment_required,
                "era_enrollment_url": payer.era_enrollment_url,
                "era_enrollment_forms": payer.era_enrollment_forms,
                "eft_enrollment_required": payer.eft_enrollment_required,
                "eft_enrollment_url": payer.eft_enrollment_url,
                "eft_banking_docs": payer.eft_banking_docs,
                
                # SLAs
                "filing_limit_days": payer.filing_limit_days,
                "filing_limit_from": payer.filing_limit_from,
                "auth_response_days": payer.auth_response_days,
                "appeal_window_days": payer.appeal_window_days,
                "audit_response_days": payer.audit_response_days,
                
                # Contract
                "has_contract": payer.has_contract,
                "contract_type": payer.contract_type,
                "contract_effective_date": payer.contract_effective_date.isoformat() if payer.contract_effective_date else None,
                "contract_end_date": payer.contract_end_date.isoformat() if payer.contract_end_date else None,
                "contract_notes": payer.contract_notes,
                
                # Claim Frequency
                "supports_corrected_claims": payer.supports_corrected_claims,
                "corrected_claim_frequency_code": payer.corrected_claim_frequency_code,
                "void_claim_frequency_code": payer.void_claim_frequency_code,
                "accepts_secondary_claims": payer.accepts_secondary_claims,
                "secondary_claim_requirements": payer.secondary_claim_requirements,
                
                # Paper Fallback
                "paper_claim_supported": payer.paper_claim_supported,
                "paper_claim_address": payer.paper_claim_address,
                "paper_claim_fax": payer.paper_claim_fax,
                
                # Notifications
                "notification_rules": payer.notification_rules,
                "escalation_rules": payer.escalation_rules,
                
                # State-specific
                "state_code": payer.state_code,
                "state_specific_requirements": payer.state_specific_requirements,
                
                # Metadata
                "is_active": payer.is_active,
                "version": payer.version,
                "is_draft": payer.is_draft,
                "published_at": payer.published_at.isoformat() if payer.published_at else None,
                "created_at": payer.created_at.isoformat() if payer.created_at else None,
                "updated_at": payer.updated_at.isoformat() if payer.updated_at else None,
                "created_by": payer.created_by,
                "updated_by": payer.updated_by,
                "notes": payer.notes,
                
                # Related data counts
                "rules_count": rules_count,
                "connections_count": connections_count,
                "fee_schedules_count": fee_schedules_count
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting payer {payer_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("")
async def create_payer(
    payer_data: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Create new payer profile. Admin role required; mutation audited."""
    current_user.require_role("admin")
    try:
        clean = {k: v for k, v in payer_data.items() if k not in _PROTECTED_PAYER_FIELDS}
        new_payer = PayerProfile(
            **clean,
            tenant_id=current_user.tenant_id,
            created_by=current_user.email,
            is_draft=True,
            version=1,
        )
        db.add(new_payer)
        await db.flush()

        version = PayerProfileVersion(
            payer_id=new_payer.id,
            version_number=1,
            profile_data=payer_data,
            change_summary="Initial creation",
            changed_by=current_user.email,
        )
        db.add(version)

        await log_audit_event(
            db, current_user, action="payer_created", resource_type="payer",
            resource_id=str(new_payer.id), request=request,
            metadata={"name": new_payer.name},
        )
        await db.commit()
        await db.refresh(new_payer)

        return {
            "success": True,
            "message": "Payer profile created successfully",
            "data": {"id": new_payer.id, "version": new_payer.version},
        }
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Error creating payer")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{payer_id}")
async def update_payer(
    payer_id: int,
    updates: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Update payer profile. Admin role required; mutation audited.

    tenant_id is in _PROTECTED_PAYER_FIELDS so the payer cannot be reassigned
    to another tenant via the bulk update path (closes NEW-H1).
    """
    current_user.require_role("admin")
    try:
        result = await db.execute(
            select(PayerProfile).where(and_(
                PayerProfile.id == payer_id,
                PayerProfile.tenant_id == current_user.tenant_id,
            ))
        )
        payer = result.scalar_one_or_none()
        if not payer:
            raise HTTPException(status_code=404, detail="Payer not found")

        applied = []
        for key, value in updates.items():
            if key in _PROTECTED_PAYER_FIELDS:
                continue
            if hasattr(payer, key):
                setattr(payer, key, value)
                applied.append(key)

        payer.version += 1
        payer.updated_by = current_user.email
        payer.is_draft = True

        version = PayerProfileVersion(
            payer_id=payer.id,
            version_number=payer.version,
            profile_data=updates,
            change_summary=updates.get("change_summary", "Updated configuration"),
            changed_by=current_user.email,
        )
        db.add(version)

        await log_audit_event(
            db, current_user, action="payer_updated", resource_type="payer",
            resource_id=str(payer.id), request=request,
            changes={"updated_fields": sorted(applied), "new_version": payer.version},
        )
        await db.commit()
        await db.refresh(payer)

        return {
            "success": True,
            "message": "Payer profile updated successfully",
            "data": {"id": payer.id, "version": payer.version},
        }
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Error updating payer %s", payer_id)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{payer_id}/publish")
async def publish_payer(
    payer_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Publish payer profile (Draft → Published). Admin role required."""
    current_user.require_role("admin")
    try:
        result = await db.execute(
            select(PayerProfile).where(and_(
                PayerProfile.id == payer_id,
                PayerProfile.tenant_id == current_user.tenant_id,
            ))
        )
        payer = result.scalar_one_or_none()
        if not payer:
            raise HTTPException(status_code=404, detail="Payer not found")

        payer.is_draft = False
        payer.published_at = _utcnow_naive()

        version_result = await db.execute(
            select(PayerProfileVersion)
            .where(PayerProfileVersion.payer_id == payer_id)
            .order_by(desc(PayerProfileVersion.version_number))
            .limit(1)
        )
        latest_version = version_result.scalar_one_or_none()
        if latest_version:
            latest_version.is_published = True
            latest_version.published_at = _utcnow_naive()
            latest_version.published_by = current_user.email

        await log_audit_event(
            db, current_user, action="payer_published", resource_type="payer",
            resource_id=str(payer.id), request=request,
            metadata={"version": latest_version.version_number if latest_version else None},
        )
        await db.commit()

        return {
            "success": True,
            "message": f"Payer profile '{payer.name}' published successfully",
        }
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Error publishing payer %s", payer_id)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{payer_id}")
async def delete_payer(
    payer_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Deactivate payer profile (soft delete). Admin role required."""
    current_user.require_role("admin")
    try:
        result = await db.execute(
            select(PayerProfile).where(and_(
                PayerProfile.id == payer_id,
                PayerProfile.tenant_id == current_user.tenant_id,
            ))
        )
        payer = result.scalar_one_or_none()
        if not payer:
            raise HTTPException(status_code=404, detail="Payer not found")

        payer.is_active = False
        payer.updated_by = current_user.email

        await log_audit_event(
            db, current_user, action="payer_deactivated", resource_type="payer",
            resource_id=str(payer.id), request=request,
        )
        await db.commit()

        return {
            "success": True,
            "message": f"Payer profile '{payer.name}' deactivated successfully",
        }
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Error deleting payer %s", payer_id)
        raise HTTPException(status_code=500, detail="Internal server error")


# ==================== PAYER RULES ====================

@router.get("/{payer_id}/rules")
async def get_payer_rules(
    payer_id: int,
    is_active: Optional[bool] = True,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user)
):
    """
    Get all rules for a payer
    """
    current_user.require_role("billing")
    try:
        await _verify_payer_tenant(payer_id, current_user.tenant_id, db)
        query = select(PayerRule).where(PayerRule.payer_id == payer_id)
        
        if is_active is not None:
            query = query.where(PayerRule.is_active == is_active)
        
        query = query.order_by(desc(PayerRule.priority))
        
        result = await db.execute(query)
        rules = result.scalars().all()
        
        return {
            "success": True,
            "data": [{
                "id": r.id,
                "rule_name": r.rule_name,
                "description": r.description,
                "priority": r.priority,
                "conditions": r.conditions,
                "actions": r.actions,
                "is_active": r.is_active,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "created_by": r.created_by
            } for r in rules]
        }
    except Exception as e:
        logger.error(f"Error getting rules for payer {payer_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{payer_id}/rules")
async def create_payer_rule(
    payer_id: int,
    rule_data: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Create new rule for payer. Admin role required; mutation audited."""
    current_user.require_role("admin")
    try:
        await _verify_payer_tenant(payer_id, current_user.tenant_id, db)
        clean = {k: v for k, v in rule_data.items() if k not in _PROTECTED_RULE_FIELDS}
        new_rule = PayerRule(
            payer_id=payer_id,
            **clean,
            created_by=current_user.email,
        )
        db.add(new_rule)
        await db.flush()

        await log_audit_event(
            db, current_user, action="payer_rule_created", resource_type="payer_rule",
            resource_id=str(new_rule.id), request=request,
            metadata={"payer_id": payer_id, "rule_name": getattr(new_rule, "rule_name", None)},
        )
        await db.commit()
        await db.refresh(new_rule)
        return {
            "success": True,
            "message": "Rule created successfully",
            "data": {"id": new_rule.id},
        }
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Error creating rule for payer %s", payer_id)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/rules/{rule_id}")
async def update_payer_rule(
    rule_id: int,
    updates: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Update payer rule. Admin role required.

    tenant_id and payer_id are excluded so a rule cannot be moved to another
    payer / tenant via this path (closes NEW-H2).
    """
    current_user.require_role("admin")
    try:
        result = await db.execute(
            select(PayerRule).join(PayerProfile, PayerRule.payer_id == PayerProfile.id).where(
                and_(PayerRule.id == rule_id, PayerProfile.tenant_id == current_user.tenant_id)
            )
        )
        rule = result.scalar_one_or_none()
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        applied = []
        for key, value in updates.items():
            if key in _PROTECTED_RULE_FIELDS:
                continue
            if hasattr(rule, key):
                setattr(rule, key, value)
                applied.append(key)
        rule.updated_by = current_user.email

        await log_audit_event(
            db, current_user, action="payer_rule_updated", resource_type="payer_rule",
            resource_id=str(rule_id), request=request,
            changes={"updated_fields": sorted(applied)},
        )
        await db.commit()
        return {"success": True, "message": "Rule updated successfully"}
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Error updating rule %s", rule_id)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/rules/{rule_id}")
async def delete_payer_rule(
    rule_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Deactivate rule. Admin role required."""
    current_user.require_role("admin")
    try:
        result = await db.execute(
            select(PayerRule).join(PayerProfile, PayerRule.payer_id == PayerProfile.id).where(
                and_(PayerRule.id == rule_id, PayerProfile.tenant_id == current_user.tenant_id)
            )
        )
        rule = result.scalar_one_or_none()
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        rule.is_active = False
        rule.updated_by = current_user.email

        await log_audit_event(
            db, current_user, action="payer_rule_deactivated", resource_type="payer_rule",
            resource_id=str(rule_id), request=request,
        )
        await db.commit()
        return {"success": True, "message": "Rule deactivated successfully"}
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Error deleting rule %s", rule_id)
        raise HTTPException(status_code=500, detail="Internal server error")


# ==================== TRADING PARTNER CONNECTIONS ====================

@router.get("/{payer_id}/connections")
async def get_payer_connections(
    payer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user)
):
    """
    Get all trading partner connections for a payer
    Credentials are returned encrypted (not decrypted in API)
    """
    current_user.require_role("admin")
    try:
        await _verify_payer_tenant(payer_id, current_user.tenant_id, db)
        result = await db.execute(
            select(TradingPartnerConnection)
            .join(PayerProfile, TradingPartnerConnection.payer_id == PayerProfile.id)
            .where(TradingPartnerConnection.payer_id == payer_id)
            .where(PayerProfile.tenant_id == current_user.tenant_id)
            .where(TradingPartnerConnection.is_active == True)
        )
        connections = result.scalars().all()
        
        return {
            "success": True,
            "data": [{
                "id": c.id,
                "connection_name": c.connection_name,
                "clearinghouse_name": c.clearinghouse_name,
                "connection_type": c.connection_type,
                "is_active": c.is_active,
                "last_tested": c.last_tested.isoformat() if c.last_tested else None,
                "last_test_status": c.last_test_status,
                "last_test_message": c.last_test_message,
                # Don't return encrypted credentials in list view
            } for c in connections]
        }
    except Exception as e:
        logger.error(f"Error getting connections for payer {payer_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{payer_id}/connections")
async def create_payer_connection(
    payer_id: int,
    connection_data: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Create trading partner connection. Admin role required (writes secrets)."""
    current_user.require_role("admin")
    try:
        await _verify_payer_tenant(payer_id, current_user.tenant_id, db)
        api_endpoint = str(connection_data.get("api_endpoint") or "").strip()
        if api_endpoint:
            assert_safe_http_url(api_endpoint, field_name="api_endpoint")
        # Encrypt sensitive fields before storage.
        for raw_key, enc_key in (
            ("sftp_password", "sftp_password_encrypted"),
            ("api_key", "api_key_encrypted"),
            ("api_secret", "api_secret_encrypted"),
            ("portal_password", "portal_password_encrypted"),
        ):
            if raw_key in connection_data:
                connection_data[enc_key] = await encrypt_credential(connection_data.pop(raw_key))

        clean = {k: v for k, v in connection_data.items() if k not in {"id", "tenant_id", "payer_id", "created_at", "created_by"}}
        new_connection = TradingPartnerConnection(
            payer_id=payer_id,
            **clean,
            created_by=current_user.email,
        )
        db.add(new_connection)
        await db.flush()

        await log_audit_event(
            db, current_user, action="payer_connection_created", resource_type="payer_connection",
            resource_id=str(new_connection.id), request=request,
            metadata={
                "payer_id": payer_id,
                "connection_name": getattr(new_connection, "connection_name", None),
                "credentials_provided": [k for k in ("sftp_password_encrypted", "api_key_encrypted", "api_secret_encrypted", "portal_password_encrypted") if k in connection_data],
            },
        )
        await db.commit()
        await db.refresh(new_connection)
        return {
            "success": True,
            "message": "Connection created successfully (credentials encrypted)",
            "data": {"id": new_connection.id},
        }
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Error creating connection for payer %s", payer_id)
        raise HTTPException(status_code=500, detail="Internal server error")


# ==================== FEE SCHEDULES ====================

@router.get("/{payer_id}/fee-schedules")
async def list_fee_schedules(
    payer_id: int,
    cpt_code: Optional[str] = None,
    state_code: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List fee schedules for a payer - scoped to tenant"""
    current_user.require_role("billing")
    # Verify payer belongs to tenant
    payer_check = await db.execute(
        select(PayerProfile.id).where(and_(PayerProfile.id == payer_id, PayerProfile.tenant_id == current_user.tenant_id))
    )
    if not payer_check.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Payer not found")

    query = select(FeeSchedule).where(FeeSchedule.payer_id == payer_id)
    if cpt_code:
        query = query.where(FeeSchedule.cpt_code == cpt_code)
    if state_code:
        query = query.where(FeeSchedule.state_code == state_code)

    query = query.order_by(FeeSchedule.cpt_code).limit(limit).offset(offset)
    result = await db.execute(query)
    schedules = result.scalars().all()

    return {
        "success": True,
        "data": [{
            "id": s.id,
            "cpt_code": s.cpt_code,
            "description": s.description,
            "allowable_amount": float(s.allowable_amount) if s.allowable_amount else None,
            "facility_rate": float(s.facility_rate) if s.facility_rate else None,
            "non_facility_rate": float(s.non_facility_rate) if s.non_facility_rate else None,
            "state_code": s.state_code,
            "locality": s.locality,
            "effective_date": s.effective_date.isoformat() if s.effective_date else None,
            "end_date": s.end_date.isoformat() if s.end_date else None,
        } for s in schedules],
    }


@router.get("/fee-schedules")
async def list_all_fee_schedules(
    cpt_code: Optional[str] = None,
    payer_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List fee schedules across all tenant payers"""
    current_user.require_role("billing")
    # Only show fee schedules for payers belonging to the tenant
    query = (
        select(FeeSchedule)
        .join(PayerProfile, FeeSchedule.payer_id == PayerProfile.id)
        .where(PayerProfile.tenant_id == current_user.tenant_id)
    )
    if cpt_code:
        query = query.where(FeeSchedule.cpt_code == cpt_code)
    if payer_id:
        query = query.where(FeeSchedule.payer_id == payer_id)

    query = query.order_by(FeeSchedule.cpt_code).limit(limit).offset(offset)
    result = await db.execute(query)
    schedules = result.scalars().all()

    return {
        "success": True,
        "data": [{
            "id": s.id,
            "payer_id": s.payer_id,
            "cpt_code": s.cpt_code,
            "description": s.description,
            "allowable_amount": float(s.allowable_amount) if s.allowable_amount else None,
            "facility_rate": float(s.facility_rate) if s.facility_rate else None,
            "non_facility_rate": float(s.non_facility_rate) if s.non_facility_rate else None,
            "effective_date": s.effective_date.isoformat() if s.effective_date else None,
        } for s in schedules],
    }


@router.post("/{payer_id}/fee-schedules/upload")
async def upload_fee_schedule(
    payer_id: int,
    request: Request,
    file: UploadFile = File(...),
    state_code: Optional[str] = None,
    locality: Optional[str] = None,
    effective_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Upload fee schedule CSV. Admin role; size-capped; mime-validated.

    Format: cpt_code, description, allowable_amount, [facility_rate],
    [non_facility_rate], [state_code], [locality]
    """
    current_user.require_role("admin")
    try:
        await _verify_payer_tenant(payer_id, current_user.tenant_id, db)

        if not (file.filename or "").lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="File must be a .csv")

        contents = await file.read(MAX_FEE_SCHEDULE_BYTES + 1)
        if len(contents) > MAX_FEE_SCHEDULE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Fee schedule exceeds maximum size of {MAX_FEE_SCHEDULE_BYTES // (1024 * 1024)} MB",
            )
        if not contents:
            raise HTTPException(status_code=400, detail="Empty file")

        csv_file = io.StringIO(contents.decode("utf-8", errors="replace"))
        reader = csv.DictReader(csv_file)
        batch_id = f"upload_{_utcnow_naive().strftime('%Y%m%d_%H%M%S')}"
        uploaded_count = 0
        errors: List[Dict[str, Any]] = []

        for row_num, row in enumerate(reader, start=2):
            try:
                fee_schedule = FeeSchedule(
                    payer_id=payer_id,
                    state_code=state_code or row.get("state_code"),
                    locality=locality or row.get("locality"),
                    cpt_code=row["cpt_code"],
                    description=row.get("description", ""),
                    allowable_amount=float(row["allowable_amount"]),
                    facility_rate=float(row["facility_rate"]) if row.get("facility_rate") else None,
                    non_facility_rate=float(row["non_facility_rate"]) if row.get("non_facility_rate") else None,
                    effective_date=effective_date or _utcnow_naive().date(),
                    uploaded_by=current_user.email,
                    upload_batch_id=batch_id,
                )
                db.add(fee_schedule)
                # Flush per row so a bad row triggers IntegrityError now (not at
                # the end of the loop) and we can rollback just that row before
                # continuing.
                await db.flush()
                uploaded_count += 1
            except Exception as row_err:
                await db.rollback()
                errors.append({"row": row_num, "error": str(row_err)})

        await log_audit_event(
            db, current_user, action="fee_schedule_uploaded", resource_type="fee_schedule",
            resource_id=batch_id, request=request,
            metadata={"payer_id": payer_id, "rows_inserted": uploaded_count, "errors": len(errors)},
        )
        await db.commit()

        return {
            "success": True,
            "message": f"Uploaded {uploaded_count} fee schedule entries",
            "data": {"batch_id": batch_id, "count": uploaded_count, "errors": errors},
        }
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Error uploading fee schedule for payer %s", payer_id)
        raise HTTPException(status_code=500, detail="Internal server error")


# ==================== VERSION HISTORY ====================

@router.get("/{payer_id}/versions")
async def get_payer_versions(
    payer_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user)
):
    """
    Get version history for payer profile
    """
    current_user.require_role("billing")
    try:
        await _verify_payer_tenant(payer_id, current_user.tenant_id, db)
        result = await db.execute(
            select(PayerProfileVersion)
            .where(PayerProfileVersion.payer_id == payer_id)
            .order_by(desc(PayerProfileVersion.version_number))
            .limit(limit)
        )
        versions = result.scalars().all()
        
        return {
            "success": True,
            "data": [{
                "id": v.id,
                "version_number": v.version_number,
                "change_summary": v.change_summary,
                "changed_by": v.changed_by,
                "changed_at": v.changed_at.isoformat() if v.changed_at else None,
                "is_published": v.is_published,
                "published_at": v.published_at.isoformat() if v.published_at else None,
                "published_by": v.published_by
            } for v in versions]
        }
    except Exception as e:
        logger.error(f"Error getting versions for payer {payer_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{payer_id}/test-connection")
async def test_payer_connection(
    payer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user)
):
    """
    Test clearinghouse connection for payer
    Tests SFTP/API connectivity before going live
    """
    current_user.require_role("admin")
    try:
        await _verify_payer_tenant(payer_id, current_user.tenant_id, db)
        # Get payer connection
        conn_result = await db.execute(
            select(TradingPartnerConnection)
            .join(PayerProfile, TradingPartnerConnection.payer_id == PayerProfile.id)
            .where(TradingPartnerConnection.payer_id == payer_id)
            .where(PayerProfile.tenant_id == current_user.tenant_id)
            .limit(1)
        )
        connection = conn_result.scalar_one_or_none()
        
        if not connection:
            raise HTTPException(status_code=404, detail="No connection configured for this payer")
        
        # Test based on connection type
        from services.clearinghouse_transport import SFTPTransport, APITransport
        
        if connection.connection_type == "sftp":
            sftp = SFTPTransport(db)
            test_result = await sftp.test_connection(connection)
        elif connection.connection_type == "api":
            api = APITransport(db)
            test_result = await api.test_connection(connection)
        else:
            return {
                "success": False,
                "message": f"Connection testing not supported for type: {connection.connection_type}"
            }
        
        # Update connection record
        connection.last_tested = _utcnow_naive()
        connection.last_test_status = "success" if test_result["success"] else "failed"
        connection.last_test_message = test_result["message"]
        await db.commit()
        
        return {
            "success": test_result["success"],
            "message": test_result["message"],
            "data": test_result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing connection for payer {payer_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

