"""
Smart Payer Enrollment Service
Intelligently creates payer enrollment cases based on:
- Provider's active state licenses
- Provider's credentialing verification score
- Payer's state-specific requirements
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

logger = logging.getLogger(__name__)


async def create_smart_payer_enrollment_cases(
    provider_id: str,
    db: AsyncSession,
    provider_verification_data: Dict[str, Any],
    tenant_id: str = None,
) -> Dict[str, Any]:
    """
    Intelligently create payer enrollment cases based on provider's licenses
    
    Flow:
    1. Get provider's state license verification data
    2. Get all active payers
    3. For EACH state where provider is licensed in good standing:
       - Create cases for payers in that state
    4. For national payers (Medicare), create case
    
    Args:
        provider_id: Provider ID from provider_credentialing
        db: Database session
        provider_verification_data: Data from ProviderCredentialing.signup_data
    
    Returns:
        Dict with cases created, organized by state
    """
    try:
        from models.payer_credentialing import PayerCredentialingCase
        from models.rcm import PayerProfile
        from models.credentialing import ProviderCredentialing
        
        # Get provider credentialing record for license data
        cred_query = select(ProviderCredentialing).where(ProviderCredentialing.provider_id == provider_id)
        if tenant_id:
            cred_query = cred_query.where(ProviderCredentialing.tenant_id == tenant_id)
        cred_result = await db.execute(cred_query)
        provider_cred = cred_result.scalar_one_or_none()
        
        if not provider_cred:
            return {
                "success": False,
                "error": "Provider credentialing record not found"
            }
        
        # Extract state licenses from verification
        state_license_data = provider_cred.state_license_verification or {}
        
        # Get states where provider is licensed in good standing
        licensed_states = []
        
        # From state_license_verification JSON
        if isinstance(state_license_data, dict) and state_license_data.get('verified'):
            state = state_license_data.get('state')
            status = state_license_data.get('status', '').upper()
            
            if state and status in ['ACTIVE', 'CURRENT', 'VALID', 'GOOD STANDING']:
                licensed_states.append(state)
        
        # Also check signup_data for state_code
        signup_data = provider_cred.signup_data or {}
        primary_state = signup_data.get('state_code')
        if primary_state and primary_state not in licensed_states:
            licensed_states.append(primary_state)
        
        logger.info(f"Provider {provider_id} licensed in states: {licensed_states}")
        
        # Get all active payers (tenant-scoped)
        payer_query = select(PayerProfile).where(and_(
            PayerProfile.is_active == True,
            PayerProfile.is_draft == False
        ))
        if tenant_id:
            payer_query = payer_query.where(PayerProfile.tenant_id == tenant_id)
        payers_result = await db.execute(payer_query)
        payers = payers_result.scalars().all()
        
        cases_created = 0
        cases_by_state = {}
        skipped_payers = []
        
        for payer in payers:
            # Check if payer is state-specific
            payer_state = payer.state_code
            
            # Skip if payer is state-specific and provider not licensed in that state
            if payer_state:
                if payer_state not in licensed_states:
                    skipped_payers.append({
                        "payer_name": payer.name,
                        "payer_state": payer_state,
                        "reason": f"Provider not licensed in {payer_state}"
                    })
                    logger.debug(f"Skipping {payer.name} - Provider not licensed in {payer_state}")
                    continue
            
            # National payers (no state_code) - always create if provider has at least one license
            # State-specific payers - only if provider licensed in that state
            
            # Check if case already exists (tenant-scoped to prevent cross-tenant collisions)
            existing_query = select(PayerCredentialingCase).where(and_(
                PayerCredentialingCase.provider_id == provider_id,
                PayerCredentialingCase.payer_id == payer.id,
            ))
            if tenant_id:
                existing_query = existing_query.where(
                    PayerCredentialingCase.tenant_id == tenant_id
                )
            existing_result = await db.execute(existing_query)
            existing_case = existing_result.scalar_one_or_none()
            
            if existing_case:
                logger.debug(f"Payer case already exists for {payer.name}")
                continue
            
            # Build intelligent checklist based on payer and provider
            checklist = _build_intelligent_checklist(payer, provider_cred, licensed_states)
            
            # Create payer credentialing case
            new_case = PayerCredentialingCase(
                tenant_id=tenant_id or str(provider_cred.tenant_id),
                provider_id=provider_id,
                payer_id=payer.id,
                status="draft",
                checklist=checklist,
                total_items=len(checklist),
                completed_items=0,
                completion_percentage=0,
                created_by="smart_auto_create",
                notes=f"Auto-created after provider verification approval. Provider licensed in: {', '.join(licensed_states)}"
            )
            
            db.add(new_case)
            cases_created += 1
            
            # Track by state
            state_key = payer_state or "National"
            if state_key not in cases_by_state:
                cases_by_state[state_key] = []
            cases_by_state[state_key].append(payer.name)
        
        if cases_created > 0:
            await db.commit()
            logger.info(f"Smart enrollment: Created {cases_created} payer cases for provider {provider_id} across {len(cases_by_state)} state(s)")
        
        return {
            "success": True,
            "cases_created": cases_created,
            "licensed_states": licensed_states,
            "cases_by_state": cases_by_state,
            "skipped_payers": skipped_payers,
            "message": f"Created {cases_created} payer enrollment cases for states: {', '.join(licensed_states)}"
        }
        
    except Exception as e:
        logger.error(f"Error in smart payer enrollment: {e}")
        return {
            "success": False,
            "cases_created": 0,
            "error": str(e)
        }


def _build_intelligent_checklist(payer: Any, provider_cred: Any, licensed_states: List[str]) -> List[Dict]:
    """
    Build intelligent checklist based on:
    - Payer requirements
    - Provider's verification status
    - State-specific requirements
    """
    checklist = []
    signup_data = provider_cred.signup_data or {}
    
    # W-9 (always required)
    checklist.append({
        "item": "W-9 Tax Form",
        "required": True,
        "completed": False,
        "doc_type": "w9",
        "description": "IRS W-9 form with TIN/SSN",
        "auto_completable": False
    })
    
    # State License - auto-mark as completed if already verified
    state_license_verified = (
        provider_cred.state_license_verification and 
        provider_cred.state_license_verification.get('verified', False)
    )
    
    checklist.append({
        "item": "Medical License Copy",
        "required": True,
        "completed": state_license_verified,
        "doc_type": "license",
        "description": f"State medical license(s) for: {', '.join(licensed_states)}",
        "auto_completed": state_license_verified,
        "verification_source": "Provider verification system"
    })
    
    # NPI - auto-mark as completed if verified
    npi_verified = (
        provider_cred.npi_verification and 
        provider_cred.npi_verification.get('verified', False)
    )
    
    checklist.append({
        "item": "NPI Verification",
        "required": True,
        "completed": npi_verified,
        "doc_type": "npi",
        "description": f"NPI: {signup_data.get('npi', 'N/A')}",
        "auto_completed": npi_verified,
        "verification_source": "CMS NPPES Registry"
    })
    
    # Malpractice Insurance
    checklist.append({
        "item": "Malpractice Insurance",
        "required": True,
        "completed": False,
        "doc_type": "malpractice",
        "description": "Current malpractice insurance certificate ($1M/$3M minimum)",
        "auto_completable": False
    })
    
    # Background Check - auto-mark if passed
    background_passed = (
        provider_cred.background_check and 
        provider_cred.background_check.get('verified', False)
    )
    
    if background_passed:
        checklist.append({
            "item": "Background Check",
            "required": True,
            "completed": True,
            "description": "Background check completed and passed",
            "auto_completed": True,
            "verification_source": "Provider verification system"
        })
    
    # OIG Exclusion Check - auto-mark if passed
    oig_passed = (
        provider_cred.oig_check and 
        provider_cred.oig_check.get('verified', False) and
        not provider_cred.oig_check.get('excluded', False)
    )
    
    if oig_passed:
        checklist.append({
            "item": "OIG Exclusion Screening",
            "required": True,
            "completed": True,
            "description": "Not on OIG exclusion list",
            "auto_completed": True,
            "verification_source": "HHS OIG database"
        })
    
    # SAM.gov Check - auto-mark if passed
    sam_passed = (
        provider_cred.sam_check and 
        provider_cred.sam_check.get('verified', False)
    )
    
    if sam_passed:
        checklist.append({
            "item": "SAM.gov Screening",
            "required": True,
            "completed": True,
            "description": "Not on SAM.gov exclusion list",
            "auto_completed": True,
            "verification_source": "SAM.gov database"
        })
    
    # Payer-specific requirements
    payer_name = payer.name.upper()
    
    # Medicare-specific
    if "MEDICARE" in payer_name:
        checklist.extend([
            {
                "item": "PECOS Enrollment",
                "required": True,
                "completed": False,
                "description": "Medicare Provider Enrollment, Chain, and Ownership System"
            },
            {
                "item": "PTAN",
                "required": True,
                "completed": False,
                "description": "Provider Transaction Access Number from Medicare"
            }
        ])
    
    # Medicaid-specific (state-dependent)
    if "MEDICAID" in payer_name or "QUEST" in payer_name or "AHCCCS" in payer_name or "STAR" in payer_name or "DENALI" in payer_name:
        payer_state = payer.state_code
        checklist.append({
            "item": f"{payer_state or 'State'} Medicaid Provider Number",
            "required": True,
            "completed": False,
            "description": f"Medicaid enrollment number for {payer_state or 'applicable state'}"
        })
    
    # CAQH for commercial payers
    if "MEDICARE" not in payer_name and "MEDICAID" not in payer_name:
        checklist.append({
            "item": "CAQH Profile",
            "required": True,
            "completed": False,
            "doc_type": "caqh_profile",
            "description": "Current CAQH profile with attestation (within 120 days)"
        })
    
    # DEA (if provider prescribes controlled substances)
    # Auto-detect from signup data or specialty
    specialty = signup_data.get('specialty', '').upper()
    prescribes_controlled = any(term in specialty for term in ['PSYCHIATRY', 'PAIN', 'ANESTHESIA', 'FAMILY', 'INTERNAL'])
    
    checklist.append({
        "item": "DEA Certificate",
        "required": prescribes_controlled,
        "completed": False,
        "doc_type": "dea",
        "description": "DEA registration for controlled substances" + (" (Required for your specialty)" if prescribes_controlled else " (If applicable)")
    })
    
    # State-specific requirements
    for state in licensed_states:
        if state == "TX":
            checklist.append({
                "item": "Texas Medical Board Verification",
                "required": True,
                "completed": False,
                "description": "Texas-specific board verification"
            })
        elif state == "CA":
            checklist.append({
                "item": "California Medical Board License",
                "required": True,
                "completed": False,
                "description": "California medical license verification"
            })
        elif state == "NY":
            checklist.append({
                "item": "OPMC Good Standing Letter",
                "required": True,
                "completed": False,
                "description": "NY Office of Professional Medical Conduct verification"
            })
    
    return checklist


async def get_provider_eligible_payers(provider_id: str, db: AsyncSession, tenant_id: str = None) -> Dict[str, Any]:
    """
    Get list of payers provider is eligible for based on state licenses
    
    Returns:
        {
            "eligible_payers": [list of payers],
            "licensed_states": [list of states],
            "ineligible_payers": [payers provider can't enroll with yet]
        }
    """
    try:
        from models.credentialing import ProviderCredentialing
        from models.rcm import PayerProfile
        
        # Get provider credentials
        cred_result = await db.execute(
            select(ProviderCredentialing).where(ProviderCredentialing.provider_id == provider_id)
        )
        provider_cred = cred_result.scalar_one_or_none()
        
        if not provider_cred:
            return {"error": "Provider not found"}
        
        # Extract licensed states
        licensed_states = []
        
        # From state_license_verification
        state_license = provider_cred.state_license_verification or {}
        if state_license.get('verified') and state_license.get('status', '').upper() in ['ACTIVE', 'CURRENT', 'VALID']:
            licensed_states.append(state_license.get('state'))
        
        # From signup data
        signup_data = provider_cred.signup_data or {}
        primary_state = signup_data.get('state_code')
        if primary_state and primary_state not in licensed_states:
            licensed_states.append(primary_state)
        
        # Get all payers (tenant-scoped)
        payer_query = select(PayerProfile).where(PayerProfile.is_active == True)
        if tenant_id:
            payer_query = payer_query.where(PayerProfile.tenant_id == tenant_id)
        payers_result = await db.execute(payer_query)
        payers = payers_result.scalars().all()
        
        eligible_payers = []
        ineligible_payers = []
        
        for payer in payers:
            if payer.state_code:
                # State-specific payer
                if payer.state_code in licensed_states:
                    eligible_payers.append({
                        "payer_id": payer.id,
                        "payer_name": payer.name,
                        "state": payer.state_code,
                        "reason": f"Provider licensed in {payer.state_code}"
                    })
                else:
                    ineligible_payers.append({
                        "payer_id": payer.id,
                        "payer_name": payer.name,
                        "state": payer.state_code,
                        "reason": f"Provider not licensed in {payer.state_code}"
                    })
            else:
                # National payer (Medicare, etc.)
                if len(licensed_states) > 0:
                    eligible_payers.append({
                        "payer_id": payer.id,
                        "payer_name": payer.name,
                        "state": "National",
                        "reason": "National payer, provider has valid license"
                    })
        
        return {
            "success": True,
            "provider_id": provider_id,
            "licensed_states": licensed_states,
            "eligible_payers": eligible_payers,
            "ineligible_payers": ineligible_payers,
            "total_eligible": len(eligible_payers),
            "total_ineligible": len(ineligible_payers)
        }
        
    except Exception as e:
        logger.error(f"Error getting eligible payers: {e}")
        return {"success": False, "error": str(e)}


async def auto_complete_checklist_from_verification(
    case_id: int,
    provider_id: str,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Auto-complete checklist items that were already verified in Stage 1
    
    Example:
    - NPI already verified in Stage 1 → Mark as completed with reference
    - License already verified → Mark as completed
    - OIG check already passed → Mark as completed
    
    This saves ops time by not re-verifying what was already checked
    """
    try:
        from models.payer_credentialing import PayerCredentialingCase
        from models.credentialing import ProviderCredentialing
        
        # Get case
        case_result = await db.execute(
            select(PayerCredentialingCase).where(PayerCredentialingCase.id == case_id)
        )
        case = case_result.scalar_one_or_none()
        
        if not case:
            return {"success": False, "error": "Case not found"}
        
        # Get provider verification
        cred_result = await db.execute(
            select(ProviderCredentialing).where(ProviderCredentialing.provider_id == provider_id)
        )
        provider_cred = cred_result.scalar_one_or_none()
        
        if not provider_cred:
            return {"success": False, "error": "Provider credentials not found"}
        
        # Get current checklist
        checklist = case.checklist or []
        items_auto_completed = 0
        
        # Auto-complete based on verification data
        for item in checklist:
            if not item.get('completed'):
                # NPI Verification
                if item.get('doc_type') == 'npi' and provider_cred.npi_verification:
                    if provider_cred.npi_verification.get('verified'):
                        item['completed'] = True
                        item['auto_completed'] = True
                        item['completed_date'] = datetime.now().isoformat()
                        item['verification_source'] = "CMS NPPES Registry (Stage 1)"
                        items_auto_completed += 1
                
                # License
                elif item.get('doc_type') == 'license' and provider_cred.state_license_verification:
                    if provider_cred.state_license_verification.get('verified'):
                        item['completed'] = True
                        item['auto_completed'] = True
                        item['completed_date'] = datetime.now().isoformat()
                        item['verification_source'] = "State licensing board (Stage 1)"
                        items_auto_completed += 1
                
                # Background Check
                elif 'Background Check' in item.get('item', '') and provider_cred.background_check:
                    if provider_cred.background_check.get('verified'):
                        item['completed'] = True
                        item['auto_completed'] = True
                        item['completed_date'] = datetime.now().isoformat()
                        item['verification_source'] = "Background check service (Stage 1)"
                        items_auto_completed += 1
        
        # Update case
        case.checklist = checklist
        case.completed_items = sum(1 for item in checklist if item.get('completed'))
        case.completion_percentage = int((case.completed_items / len(checklist)) * 100) if checklist else 0
        
        await db.commit()
        
        logger.info(f"Auto-completed {items_auto_completed} checklist items for case {case_id}")
        
        return {
            "success": True,
            "items_auto_completed": items_auto_completed,
            "completion_percentage": case.completion_percentage
        }
        
    except Exception as e:
        logger.error(f"Error auto-completing checklist: {e}")
        return {"success": False, "error": str(e)}

