"""
Credentialing & RCM Integration Service
Connects existing provider verification with payer enrollment
Auto-creates payer cases after provider approval
"""

import logging
from typing import Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

logger = logging.getLogger(__name__)


async def create_payer_enrollment_cases(provider_id: str, db: AsyncSession, tenant_id: str = None) -> Dict[str, Any]:
    """
    Auto-create payer credentialing cases for all active payers
    Called after provider is approved in credentialing queue
    
    Note: prefer create_smart_payer_enrollment_cases from smart_payer_enrollment.py
    which also filters by provider state licenses.
    """
    try:
        from models.payer_credentialing import PayerCredentialingCase
        from models.rcm import PayerProfile

        if not tenant_id:
            return {"success": False, "cases_created": 0, "error": "tenant_id is required"}
        
        query = select(PayerProfile).where(and_(
            PayerProfile.is_active == True,
            PayerProfile.is_draft == False,
        ))
        if tenant_id:
            query = query.where(PayerProfile.tenant_id == tenant_id)

        payers_result = await db.execute(query)
        payers = payers_result.scalars().all()
        
        cases_created = 0
        case_ids = []
        
        for payer in payers:
            # Check if case already exists for this provider-payer combo
            existing_result = await db.execute(
                select(PayerCredentialingCase).where(and_(
                    PayerCredentialingCase.provider_id == provider_id,
                    PayerCredentialingCase.payer_id == payer.id
                ))
            )
            existing_case = existing_result.scalar_one_or_none()
            
            if existing_case:
                logger.debug(f"Payer case already exists for provider {provider_id} with payer {payer.name}")
                continue
            
            # Build payer-specific checklist
            # In production, this would come from payer profile configuration
            checklist = _build_default_checklist(payer)
            
            # Create new payer credentialing case
            new_case = PayerCredentialingCase(
                tenant_id=tenant_id,
                provider_id=provider_id,
                payer_id=payer.id,
                status="draft",
                checklist=checklist,
                total_items=len(checklist),
                completed_items=0,
                completion_percentage=0,
                created_by="system_auto_create",
                notes=f"Auto-created after provider verification approval on {datetime.now().strftime('%Y-%m-%d')}"
            )
            
            db.add(new_case)
            cases_created += 1
            case_ids.append({"payer_name": payer.name, "payer_id": payer.id})
        
        if cases_created > 0:
            await db.commit()
            logger.info(f"Auto-created {cases_created} payer enrollment cases for provider {provider_id}")
        
        return {
            "success": True,
            "cases_created": cases_created,
            "case_details": case_ids,
            "message": f"Created {cases_created} payer enrollment case(s). Provider can now be enrolled with specific payers."
        }
        
    except Exception as e:
        logger.error(f"Error creating payer enrollment cases: {e}")
        # Don't fail provider approval if payer case creation fails
        return {
            "success": False,
            "cases_created": 0,
            "error": str(e),
            "message": "Could not auto-create payer cases. Create manually if RCM module is active."
        }


def _build_default_checklist(payer: Any) -> list:
    """
    Build default credentialing checklist for payer
    In production, this would be configured in payer profile
    """
    # Base checklist (common to all payers)
    checklist = [
        {
            "item": "W-9 Tax Form",
            "required": True,
            "completed": False,
            "doc_type": "w9",
            "description": "IRS W-9 form with TIN/SSN"
        },
        {
            "item": "Medical License Copy",
            "required": True,
            "completed": False,
            "doc_type": "license",
            "description": "Current state medical license"
        },
        {
            "item": "Malpractice Insurance",
            "required": True,
            "completed": False,
            "doc_type": "malpractice",
            "description": "Current malpractice insurance certificate"
        },
        {
            "item": "NPI Verification",
            "required": True,
            "completed": False,
            "doc_type": "npi",
            "description": "NPI Type 1 (Individual) verified"
        }
    ]
    
    # Payer-specific additions
    payer_name = payer.name.upper()
    
    # Medicare-specific
    if "MEDICARE" in payer_name:
        checklist.extend([
            {
                "item": "PECOS Enrollment",
                "required": True,
                "completed": False,
                "description": "Provider Enrollment, Chain, and Ownership System"
            },
            {
                "item": "PTAN",
                "required": True,
                "completed": False,
                "description": "Provider Transaction Access Number"
            }
        ])
    
    # Medicaid-specific
    if "MEDICAID" in payer_name or "QUEST" in payer_name or "AHCCCS" in payer_name or "STAR" in payer_name:
        checklist.append({
            "item": "State Medicaid Provider Number",
            "required": True,
            "completed": False,
            "description": "State Medicaid enrollment number"
        })
    
    # CAQH for most commercial payers
    if payer_name not in ["MEDICARE"]:
        checklist.append({
            "item": "CAQH Profile",
            "required": True,
            "completed": False,
            "doc_type": "caqh_profile",
            "description": "Current CAQH profile with attestation"
        })
    
    # DEA for controlled substance prescribers
    checklist.append({
        "item": "DEA Certificate (if applicable)",
        "required": False,
        "completed": False,
        "doc_type": "dea",
        "description": "DEA registration for controlled substances"
    })
    
    return checklist


# Export integration function for use in approval endpoint
__all__ = ['create_payer_enrollment_cases']

