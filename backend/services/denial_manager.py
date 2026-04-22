"""
Denial Management Service
Auto-routes denials from 835 files, assigns playbooks, generates appeals
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from models.denials import DenialCase, DenialPlaybook, AppealTemplate, CARCCode, RARCCode
from models.claims import Claim, ClaimLine, ClaimEvent
from models.rcm import PayerProfile

logger = logging.getLogger(__name__)


class DenialManager:
    """
    Automated denial management
    Processes 835 denials, routes to queues, generates appeals
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def process_835_denials(self, edi_file_id: int, denials_data: List[Dict[str, Any]], tenant_id: str = None) -> Dict[str, Any]:
        """
        Process denials from 835 file
        Auto-creates DenialCases, assigns playbooks, routes to queues
        
        Args:
            edi_file_id: ID of the 835 file
            denials_data: List of denial records from 835 parser
                [{
                    "claim_number": "CLM001",
                    "line_number": 1,
                    "carc": "CO-16",
                    "rarc": "M51",
                    "denied_amount": 150.00,
                    "denial_description": "Missing information"
                }]
        """
        try:
            results = {
                "denials_processed": 0,
                "cases_created": 0,
                "errors": []
            }
            
            for denial in denials_data:
                try:
                    claim_number = denial.get("claim_number")
                    if not claim_number:
                        results["errors"].append("Denial record missing claim_number")
                        continue

                    # parse_835 produces "carc": "CO-16" (group-code). Strip the group prefix
                    # for CARC lookup, since CARCCode.code stores the bare reason code.
                    raw_carc = denial.get("carc") or ""
                    if "-" in raw_carc:
                        carc_code_only = raw_carc.split("-", 1)[1]
                    else:
                        carc_code_only = raw_carc

                    if not carc_code_only:
                        results["errors"].append(f"Denial for {claim_number} has no CARC code")
                        continue

                    # Find claim (tenant-scoped)
                    claim_query = select(Claim).where(Claim.claim_number == claim_number)
                    if tenant_id:
                        claim_query = claim_query.where(Claim.tenant_id == tenant_id)
                    claim_result = await self.db.execute(claim_query)
                    claim = claim_result.scalar_one_or_none()

                    if not claim:
                        results["errors"].append(f"Claim not found: {claim_number}")
                        continue

                    # Get CARC code details for auto-categorization
                    carc_result = await self.db.execute(
                        select(CARCCode).where(CARCCode.code == carc_code_only)
                    )
                    carc = carc_result.scalar_one_or_none()
                    
                    # Determine category
                    category = carc.category if carc else "uncategorized"
                    
                    # Find appropriate playbook (tenant-scoped via _find_playbook update below)
                    playbook = await self._find_playbook(carc_code_only, denial.get("rarc"), category, tenant_id=tenant_id or str(claim.tenant_id))

                    # Get payer for appeal window calculation (tenant-scoped)
                    payer = None
                    if claim.payer_id:
                        payer_result = await self.db.execute(
                            select(PayerProfile).where(and_(
                                PayerProfile.id == claim.payer_id,
                                PayerProfile.tenant_id == claim.tenant_id,
                            ))
                        )
                        payer = payer_result.scalar_one_or_none()

                    # Calculate appeal due date
                    appeal_window_days = payer.appeal_window_days if payer else 180
                    appeal_due_date = datetime.now().date() + timedelta(days=appeal_window_days)

                    denied_amount = denial.get("denied_amount") or 0
                    # Create denial case
                    denial_case = DenialCase(
                        tenant_id=tenant_id or str(claim.tenant_id),
                        claim_id=claim.id,
                        claim_line_id=denial.get("line_id"),
                        carc_code=carc_code_only,
                        rarc_code=denial.get("rarc"),
                        denial_description=denial.get("denial_description", ""),
                        denial_category=category,
                        denied_amount=denied_amount,
                        status="new",
                        appeal_due_date=appeal_due_date,
                        days_until_due=(appeal_due_date - datetime.now().date()).days,
                        playbook_id=playbook.id if playbook else None,
                        priority=self._determine_priority(denied_amount, appeal_due_date)
                    )
                    self.db.add(denial_case)
                    
                    # Update claim status
                    claim.state = "denied"
                    claim.denial_reason = denial.get("denial_description")
                    claim.denial_category = category
                    claim.appeal_due_date = appeal_due_date
                    
                    # Create claim event
                    event = ClaimEvent(
                        claim_id=claim.id,
                        event_type="denial_processed",
                        from_state=claim.previous_state or "adjudicated",
                        to_state="denied",
                        data={
                            "carc": carc_code_only,
                            "rarc": denial.get("rarc"),
                            "denied_amount": float(denied_amount),
                            "category": category
                        },
                        message=f"Denial: {carc_code_only} - {denial.get('denial_description', '')}",
                        edi_file_id=edi_file_id
                    )
                    self.db.add(event)
                    
                    # Route to appropriate queue based on category
                    queue = self._get_queue_for_category(category)
                    claim.current_queue = queue
                    
                    results["denials_processed"] += 1
                    results["cases_created"] += 1
                    
                except Exception as e:
                    logger.error(f"Error processing individual denial: {e}")
                    results["errors"].append(str(e))
            
            await self.db.commit()
            
            logger.info(f"Processed 835 denials", extra={
                "file_id": edi_file_id,
                "denials_processed": results["denials_processed"]
            })
            
            return results
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error processing 835 denials: {e}")
            raise
    
    async def generate_appeal(self, denial_case_id: int, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate appeal packet from template
        Returns appeal letter with merge fields filled

        tenant_id is required for multi-tenant safety. Pass it from the caller's
        authenticated principal to prevent cross-tenant data leakage.
        """
        try:
            denial_query = select(DenialCase).where(DenialCase.id == denial_case_id)
            if tenant_id:
                denial_query = denial_query.where(DenialCase.tenant_id == tenant_id)
            denial_result = await self.db.execute(denial_query)
            denial_case = denial_result.scalar_one_or_none()

            if not denial_case:
                raise ValueError("Denial case not found")

            if not denial_case.playbook_id:
                raise ValueError("No playbook assigned to this denial")

            # Tenant comes from the case (already validated above) for downstream lookups
            scoped_tenant_id = tenant_id or str(denial_case.tenant_id)

            playbook_result = await self.db.execute(
                select(DenialPlaybook).where(and_(
                    DenialPlaybook.id == denial_case.playbook_id,
                    DenialPlaybook.tenant_id == scoped_tenant_id,
                ))
            )
            playbook = playbook_result.scalar_one_or_none()

            if not playbook:
                raise ValueError("Playbook not found or not accessible")

            template_result = await self.db.execute(
                select(AppealTemplate).where(and_(
                    AppealTemplate.id == playbook.appeal_template_id,
                    AppealTemplate.tenant_id == scoped_tenant_id,
                ))
            )
            template = template_result.scalar_one_or_none()

            if not template:
                raise ValueError("Appeal template not found")

            claim_result = await self.db.execute(
                select(Claim).where(and_(
                    Claim.id == denial_case.claim_id,
                    Claim.tenant_id == scoped_tenant_id,
                ))
            )
            claim = claim_result.scalar_one_or_none()
            
            # Merge template with data
            merge_data = {
                "claim_number": claim.claim_number,
                "payer_claim_id": claim.payer_claim_id or "N/A",
                "service_date": claim.service_date_from.strftime('%m/%d/%Y') if claim.service_date_from else "",
                "denied_amount": f"${denial_case.denied_amount:.2f}",
                "carc_code": denial_case.carc_code,
                "rarc_code": denial_case.rarc_code or "",
                "denial_description": denial_case.denial_description,
                "current_date": datetime.now().strftime('%m/%d/%Y')
            }
            
            # Fill template
            appeal_letter = template.body
            for field, value in merge_data.items():
                appeal_letter = appeal_letter.replace(f"{{{{{field}}}}}", str(value))
            
            # Update denial case
            denial_case.appeal_letter_generated = True
            denial_case.status = "appeal_drafted"
            
            # Update template usage
            template.times_used += 1
            
            await self.db.commit()
            
            return {
                "success": True,
                "appeal_letter": appeal_letter,
                "required_attachments": playbook.required_attachments or [],
                "submission_method": playbook.submission_method,
                "submission_address": playbook.submission_address,
                "submission_fax": playbook.submission_fax,
                "submission_portal_url": playbook.submission_portal_url,
                "due_date": denial_case.appeal_due_date.isoformat() if denial_case.appeal_due_date else None,
                "staff_instructions": playbook.staff_instructions
            }
            
        except Exception as e:
            logger.error(f"Error generating appeal: {e}")
            raise
    
    async def analyze_denial_trends(
        self,
        payer_id: Optional[int] = None,
        date_range: Optional[tuple] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Root cause analysis of denials
        Identifies patterns and recommends rule updates
        """
        try:
            # Build query
            query = select(DenialCase)
            
            if payer_id:
                # Join with claims to filter by payer
                query = query.join(Claim).where(Claim.payer_id == payer_id)
            
            if date_range:
                query = query.where(and_(
                    DenialCase.created_at >= date_range[0],
                    DenialCase.created_at <= date_range[1]
                ))
            
            result = await self.db.execute(query)
            denials = result.scalars().all()
            
            # Analyze trends
            analysis = {
                "total_denials": len(denials),
                "total_denied_amount": sum(d.denied_amount for d in denials),
                "top_carc_codes": await self._get_top_codes(denials, "carc_code", limit),
                "top_categories": await self._get_top_categories(denials, limit),
                "preventable_denials": sum(1 for d in denials if d.preventable),
                "rule_recommendations": await self._get_rule_recommendations(denials)
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing denial trends: {e}")
            raise
    
    async def _find_playbook(
        self,
        carc: str,
        rarc: Optional[str],
        category: str,
        tenant_id: Optional[str] = None,
    ) -> Optional[DenialPlaybook]:
        """Find best matching playbook for denial codes (tenant-scoped)."""
        try:
            tenant_filter = []
            if tenant_id:
                tenant_filter.append(DenialPlaybook.tenant_id == tenant_id)

            if rarc:
                result = await self.db.execute(
                    select(DenialPlaybook).where(and_(
                        DenialPlaybook.carc_code == carc,
                        DenialPlaybook.rarc_code == rarc,
                        DenialPlaybook.is_active == True,
                        *tenant_filter,
                    ))
                )
                playbook = result.scalar_one_or_none()
                if playbook:
                    return playbook

            result = await self.db.execute(
                select(DenialPlaybook).where(and_(
                    DenialPlaybook.carc_code == carc,
                    DenialPlaybook.is_active == True,
                    *tenant_filter,
                ))
            )
            playbook = result.scalar_one_or_none()
            if playbook:
                return playbook

            result = await self.db.execute(
                select(DenialPlaybook).where(and_(
                    DenialPlaybook.denial_category == category,
                    DenialPlaybook.is_active == True,
                    *tenant_filter,
                ))
            )
            playbook = result.scalar_one_or_none()
            return playbook
            
        except Exception as e:
            logger.error(f"Error finding playbook: {e}")
            return None
    
    def _determine_priority(self, denied_amount: float, appeal_due_date: datetime.date) -> str:
        """Determine denial case priority based on amount and due date"""
        days_until_due = (appeal_due_date - datetime.now().date()).days
        
        # High dollar or urgent
        if denied_amount > 1000 or days_until_due < 14:
            return "critical"
        elif denied_amount > 500 or days_until_due < 30:
            return "high"
        elif denied_amount > 200 or days_until_due < 60:
            return "medium"
        else:
            return "low"
    
    def _get_queue_for_category(self, category: str) -> str:
        """Map denial category to queue"""
        queue_mapping = {
            "coding_error": "denied_coding",
            "medical_policy": "denied_medical",
            "missing_info": "denied_missing_info",
            "timely_filing": "denied_timely_filing",
            "authorization": "denied_auth",
            "duplicate": "denied_duplicate"
        }
        return queue_mapping.get(category, "denied_other")
    
    async def _get_top_codes(self, denials: List[DenialCase], code_field: str, limit: int) -> List[Dict[str, Any]]:
        """Get top N denial codes"""
        code_counts = {}
        code_amounts = {}
        
        for denial in denials:
            code = getattr(denial, code_field)
            if code:
                code_counts[code] = code_counts.get(code, 0) + 1
                code_amounts[code] = code_amounts.get(code, 0.0) + float(denial.denied_amount)
        
        top_codes = sorted(
            code_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]
        
        return [{
            "code": code,
            "count": count,
            "total_amount": code_amounts[code]
        } for code, count in top_codes]
    
    async def _get_top_categories(self, denials: List[DenialCase], limit: int) -> List[Dict[str, Any]]:
        """Get top N denial categories"""
        category_counts = {}
        category_amounts = {}
        
        for denial in denials:
            if denial.denial_category:
                category_counts[denial.denial_category] = category_counts.get(denial.denial_category, 0) + 1
                category_amounts[denial.denial_category] = category_amounts.get(denial.denial_category, 0.0) + float(denial.denied_amount)
        
        top_categories = sorted(
            category_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]
        
        return [{
            "category": cat,
            "count": count,
            "total_amount": category_amounts[cat]
        } for cat, count in top_categories]
    
    async def _get_rule_recommendations(self, denials: List[DenialCase]) -> List[str]:
        """Analyze preventable denials and recommend rule updates"""
        recommendations = []
        
        # Look for preventable denials
        preventable = [d for d in denials if d.preventable and d.suggested_rule_update]
        
        # Group by suggested rule
        rule_suggestions = {}
        for denial in preventable:
            suggestion = denial.suggested_rule_update
            if suggestion:
                rule_suggestions[suggestion] = rule_suggestions.get(suggestion, 0) + 1
        
        # Return top recommendations
        for suggestion, count in sorted(rule_suggestions.items(), key=lambda x: x[1], reverse=True):
            recommendations.append(f"{suggestion} (would prevent {count} denials)")
        
        return recommendations[:5]  # Top 5


class AutoPostingEngine:
    """
    Automatically post payments from 835 to claims
    Matches payments, detects under-payments, handles adjustments
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def auto_post_835(self, edi_file_id: int, payments_data: List[Dict[str, Any]], tenant_id: str = None) -> Dict[str, Any]:
        """
        Auto-post payments from 835 file
        
        Args:
            edi_file_id: ID of the 835 file
            payments_data: List of payment records from 835 parser
                [{
                    "claim_number": "CLM001",
                    "line_number": 1,
                    "billed_amount": 150.00,
                    "allowed_amount": 135.00,
                    "paid_amount": 108.00,
                    "patient_responsibility": 27.00,
                    "adjustment_codes": ["CO-45", "PR-1"]
                }]
        """
        try:
            results = {
                "claims_posted": 0,
                "total_paid": 0.0,
                "under_payments_detected": 0,
                "errors": []
            }
            
            for payment in payments_data:
                try:
                    # Find claim (tenant-scoped)
                    claim_query = select(Claim).where(Claim.claim_number == payment["claim_number"])
                    if tenant_id:
                        claim_query = claim_query.where(Claim.tenant_id == tenant_id)
                    claim_result = await self.db.execute(claim_query)
                    claim = claim_result.scalar_one_or_none()
                    
                    if not claim:
                        results["errors"].append(f"Claim not found: {payment['claim_number']}")
                        continue
                    
                    # Find claim line if specified
                    line = None
                    if payment.get("line_number"):
                        line_result = await self.db.execute(
                            select(ClaimLine).where(and_(
                                ClaimLine.claim_id == claim.id,
                                ClaimLine.line_number == payment["line_number"]
                            ))
                        )
                        line = line_result.scalar_one_or_none()
                    
                    # Post payment to claim
                    if line:
                        # Line-level posting
                        line.allowed_amount = payment.get("allowed_amount")
                        line.paid_amount = payment.get("paid_amount")
                        line.patient_responsibility = payment.get("patient_responsibility")
                        line.adjustment_amount = payment.get("adjustment_amount", 0.0)
                    else:
                        # Claim-level posting
                        claim.total_allowed = payment.get("allowed_amount")
                        claim.total_paid = payment.get("paid_amount")
                        claim.patient_responsibility = payment.get("patient_responsibility")
                        claim.adjustment_amount = payment.get("adjustment_amount", 0.0)
                    
                    # Update claim status
                    claim.state = "paid"
                    claim.paid_date = datetime.utcnow()
                    
                    # Check for under-payment
                    if payment.get("allowed_amount") and payment.get("paid_amount"):
                        expected = float(payment["allowed_amount"])
                        actual = float(payment["paid_amount"])
                        
                        if actual < expected * 0.95:  # More than 5% under
                            results["under_payments_detected"] += 1
                            # TODO: Flag for review
                    
                    # Create claim event
                    event = ClaimEvent(
                        claim_id=claim.id,
                        event_type="payment_posted",
                        from_state="adjudicated",
                        to_state="paid",
                        data={
                            "paid_amount": float(payment.get("paid_amount", 0)),
                            "allowed_amount": float(payment.get("allowed_amount", 0)),
                            "patient_responsibility": float(payment.get("patient_responsibility", 0))
                        },
                        message=f"Payment posted: ${payment.get('paid_amount', 0):.2f}",
                        edi_file_id=edi_file_id
                    )
                    self.db.add(event)
                    
                    results["claims_posted"] += 1
                    results["total_paid"] += float(payment.get("paid_amount", 0))
                    
                except Exception as e:
                    logger.error(f"Error posting individual payment: {e}")
                    results["errors"].append(str(e))
            
            await self.db.commit()
            
            logger.info(f"Auto-posted 835 payments", extra={
                "file_id": edi_file_id,
                "claims_posted": results["claims_posted"],
                "total_paid": results["total_paid"]
            })
            
            return results
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error auto-posting 835: {e}")
            raise

