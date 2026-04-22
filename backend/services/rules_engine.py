"""
Rules Engine
Evaluates payer rules against claims before submission
Applies modifiers, sets flags, routes to queues automatically
"""

import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from models.rcm import PayerRule
from models.claims import Claim, ClaimLine, ClaimDiagnosis, ClaimValidation

logger = logging.getLogger(__name__)


class RulesEngine:
    """
    Applies payer-specific rules to claims
    No code changes needed - ops configure rules in UI
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def validate_claim(self, claim_id: int, tenant_id: str = None) -> Dict[str, Any]:
        """
        Main entry point: Validate claim against all payer rules
        Returns validation results with errors, warnings, and actions taken
        """
        try:
            # Get claim with relationships (tenant-scoped)
            claim_query = select(Claim).where(Claim.id == claim_id)
            if tenant_id:
                claim_query = claim_query.where(Claim.tenant_id == tenant_id)
            claim_result = await self.db.execute(claim_query)
            claim = claim_result.scalar_one_or_none()
            
            if not claim:
                return {"passed": False, "errors": ["Claim not found"]}
            
            # Get all active rules for this payer, ordered by priority
            rules_result = await self.db.execute(
                select(PayerRule)
                .where(and_(
                    PayerRule.payer_id == claim.payer_id,
                    PayerRule.is_active == True
                ))
                .order_by(PayerRule.priority.desc())
            )
            rules = rules_result.scalars().all()
            
            # Get claim lines and diagnoses
            lines_result = await self.db.execute(
                select(ClaimLine).where(ClaimLine.claim_id == claim_id)
            )
            claim_lines = lines_result.scalars().all()
            
            diagnosis_result = await self.db.execute(
                select(ClaimDiagnosis).where(ClaimDiagnosis.claim_id == claim_id)
            )
            claim_diagnoses = diagnosis_result.scalars().all()
            
            # Evaluate rules
            validation_results = {
                "passed": True,
                "errors": [],
                "warnings": [],
                "rules_evaluated": 0,
                "rules_matched": 0,
                "actions_executed": [],
                "flags_set": [],
                "modifiers_added": []
            }
            
            for rule in rules:
                validation_results["rules_evaluated"] += 1
                
                # Check if rule conditions match
                if await self._evaluate_conditions(rule.conditions, claim, claim_lines, claim_diagnoses):
                    validation_results["rules_matched"] += 1
                    logger.debug(f"Rule matched: {rule.rule_name}", extra={"claim_id": claim_id, "rule_id": rule.id})
                    
                    # Execute actions
                    action_results = await self._execute_actions(rule.actions, claim, claim_lines)
                    validation_results["actions_executed"].extend(action_results["actions"])
                    validation_results["flags_set"].extend(action_results.get("flags", []))
                    validation_results["modifiers_added"].extend(action_results.get("modifiers", []))
                    
                    # Check if actions include rejection
                    if action_results.get("reject"):
                        validation_results["passed"] = False
                        validation_results["errors"].append(action_results.get("reject_reason", "Claim rejected by rule"))
            
            # Save validation results
            validation_record = ClaimValidation(
                claim_id=claim_id,
                passed=validation_results["passed"],
                errors=validation_results["errors"],
                warnings=validation_results["warnings"],
                rules_evaluated=validation_results["rules_evaluated"],
                rules_matched=validation_results["rules_matched"],
                actions_executed=validation_results["actions_executed"],
                flags_set=validation_results["flags_set"],
                modifiers_added=validation_results["modifiers_added"]
            )
            self.db.add(validation_record)
            await self.db.commit()
            
            logger.info(f"Claim validation complete", extra={
                "claim_id": claim_id,
                "passed": validation_results["passed"],
                "rules_matched": validation_results["rules_matched"]
            })
            
            return validation_results
            
        except Exception as e:
            logger.error(f"Error validating claim {claim_id}: {e}")
            return {
                "passed": False,
                "errors": [f"Validation error: {str(e)}"]
            }
    
    async def _evaluate_conditions(
        self, 
        conditions: Dict[str, Any], 
        claim: Claim, 
        claim_lines: List[ClaimLine],
        claim_diagnoses: List[ClaimDiagnosis]
    ) -> bool:
        """
        Evaluate if conditions match claim
        Returns True if ALL conditions match
        """
        try:
            # CPT codes condition
            if "cpt_codes" in conditions:
                cpt_codes_on_claim = [line.cpt_code for line in claim_lines]
                required_cpts = conditions["cpt_codes"]
                
                # Check if ANY line has a CPT in the required list
                if not any(cpt in required_cpts for cpt in cpt_codes_on_claim):
                    return False
            
            # Place of Service condition
            if "pos" in conditions:
                pos_on_claim = [line.place_of_service for line in claim_lines]
                required_pos = conditions["pos"]
                
                if not any(pos in required_pos for pos in pos_on_claim if pos):
                    return False
            
            # Diagnosis pattern condition (regex)
            if "diagnosis_pattern" in conditions:
                diagnosis_codes = [dx.icd10_code for dx in claim_diagnoses]
                pattern = conditions["diagnosis_pattern"]
                
                if not any(re.match(pattern, dx) for dx in diagnosis_codes):
                    return False
            
            # Diagnosis group condition (starts with)
            if "diagnosis_group" in conditions:
                diagnosis_codes = [dx.icd10_code for dx in claim_diagnoses]
                group_prefix = conditions["diagnosis_group"]
                
                if not any(dx.startswith(group_prefix) for dx in diagnosis_codes):
                    return False
            
            # State condition
            if "state" in conditions:
                # Would need to get provider/facility state from relationships
                # Placeholder for now
                pass
            
            # Telehealth condition
            if "telehealth" in conditions:
                required_telehealth = conditions["telehealth"]
                # Check if claim has telehealth flags
                is_telehealth = claim.flags and claim.flags.get("is_telehealth", False)
                
                if required_telehealth != is_telehealth:
                    return False
            
            # Age condition
            if "age_min" in conditions or "age_max" in conditions:
                # Would need patient DOB to calculate age
                # Placeholder for now
                pass
            
            # All conditions matched
            return True
            
        except Exception as e:
            logger.error(f"Error evaluating conditions: {e}")
            return False
    
    async def _execute_actions(
        self,
        actions: Dict[str, Any],
        claim: Claim,
        claim_lines: List[ClaimLine]
    ) -> Dict[str, Any]:
        """
        Execute rule actions on claim
        Modifies claim/lines in memory (caller must commit)
        """
        results = {
            "actions": [],
            "flags": [],
            "modifiers": [],
            "reject": False,
            "reject_reason": None
        }
        
        try:
            # Add modifiers
            if "add_modifiers" in actions:
                modifiers_to_add = actions["add_modifiers"]
                
                for line in claim_lines:
                    existing_modifiers = line.modifiers or []
                    
                    for modifier in modifiers_to_add:
                        if modifier not in existing_modifiers:
                            existing_modifiers.append(modifier)
                            results["modifiers"].append(modifier)
                    
                    line.modifiers = existing_modifiers
                
                results["actions"].append(f"Added modifiers: {', '.join(modifiers_to_add)}")
            
            # Set flags
            if "set_flags" in actions:
                flags_to_set = actions["set_flags"]
                claim_flags = claim.flags or {}
                
                for flag in flags_to_set:
                    claim_flags[flag] = True
                    results["flags"].append(flag)
                
                claim.flags = claim_flags
                results["actions"].append(f"Set flags: {', '.join(flags_to_set)}")
            
            # Require prior authorization
            if "require_auth" in actions and actions["require_auth"]:
                claim.requires_prior_auth = True
                results["actions"].append("Marked as requiring prior authorization")
                
                if not claim.auth_obtained:
                    results["warnings"] = results.get("warnings", [])
                    results["warnings"].append("Prior authorization not obtained")
            
            # Route to queue
            if "route_to_queue" in actions:
                queue_name = actions["route_to_queue"]
                claim.current_queue = queue_name
                results["actions"].append(f"Routed to queue: {queue_name}")
            
            # Add attachment requirement
            if "add_attachment" in actions:
                attachment_type = actions["add_attachment"]
                claim_flags = claim.flags or {}
                claim_flags["required_attachments"] = claim_flags.get("required_attachments", [])
                claim_flags["required_attachments"].append(attachment_type)
                claim.flags = claim_flags
                results["actions"].append(f"Added attachment requirement: {attachment_type}")
            
            # Reject claim
            if "reject_with_reason" in actions:
                results["reject"] = True
                results["reject_reason"] = actions["reject_with_reason"]
                claim.current_queue = "validation_failed"
                results["actions"].append(f"Rejected: {actions['reject_with_reason']}")
            
            return results
            
        except Exception as e:
            logger.error(f"Error executing actions: {e}")
            return results
    
    async def get_applicable_rules_summary(self, payer_id: int) -> Dict[str, Any]:
        """
        Get summary of all active rules for a payer
        Useful for displaying what will happen during validation
        """
        try:
            rules_result = await self.db.execute(
                select(PayerRule)
                .where(and_(
                    PayerRule.payer_id == payer_id,
                    PayerRule.is_active == True
                ))
                .order_by(PayerRule.priority.desc())
            )
            rules = rules_result.scalars().all()
            
            return {
                "total_rules": len(rules),
                "rules": [{
                    "id": rule.id,
                    "name": rule.rule_name,
                    "priority": rule.priority,
                    "conditions_summary": self._summarize_conditions(rule.conditions),
                    "actions_summary": self._summarize_actions(rule.actions)
                } for rule in rules]
            }
        except Exception as e:
            logger.error(f"Error getting rules summary: {e}")
            return {"total_rules": 0, "rules": []}
    
    def _summarize_conditions(self, conditions: Dict[str, Any]) -> str:
        """Convert conditions JSON to human-readable string"""
        parts = []
        
        if "cpt_codes" in conditions:
            parts.append(f"CPT in {conditions['cpt_codes']}")
        if "pos" in conditions:
            parts.append(f"POS in {conditions['pos']}")
        if "diagnosis_pattern" in conditions:
            parts.append(f"Diagnosis matches {conditions['diagnosis_pattern']}")
        if "state" in conditions:
            parts.append(f"State = {conditions['state']}")
        if "telehealth" in conditions:
            parts.append(f"Telehealth = {conditions['telehealth']}")
        
        return " AND ".join(parts) if parts else "Always applies"
    
    def _summarize_actions(self, actions: Dict[str, Any]) -> str:
        """Convert actions JSON to human-readable string"""
        parts = []
        
        if "add_modifiers" in actions:
            parts.append(f"Add modifiers: {', '.join(actions['add_modifiers'])}")
        if "require_auth" in actions and actions["require_auth"]:
            parts.append("Require prior auth")
        if "route_to_queue" in actions:
            parts.append(f"Route to: {actions['route_to_queue']}")
        if "set_flags" in actions:
            parts.append(f"Set flags: {', '.join(actions['set_flags'])}")
        if "reject_with_reason" in actions:
            parts.append(f"Reject: {actions['reject_with_reason']}")
        
        return "; ".join(parts) if parts else "No actions"

