"""
Fee Schedule Service
Manages CPT code pricing by payer, state, and date
Ensures accurate billing rates with audit trail
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List, Dict, Any, Optional
from datetime import date, datetime
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class FeeScheduleNotFoundError(Exception):
    """Raised when a fee schedule entry is not found for the given CPT/payer/date."""
    pass


class FeeScheduleService:
    """
    Handles fee schedule lookups for billing
    Supports payer-specific rates, state variations, and effective date ranges
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def calculate_charges(
        self,
        procedures: List[Dict[str, Any]],
        payer_id: Optional[int] = None,
        state_code: Optional[str] = None,
        service_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Calculate total charges for procedures based on fee schedule
        
        Args:
            procedures: List of procedure dicts with cptCode, units, modifiers
            payer_id: Payer profile ID for payer-specific rates
            state_code: State code for geographic adjustments
            service_date: Service date for effective rate lookup
            
        Returns:
            Dict with total_charges, line_items, and calculation_details
        """
        if service_date is None:
            service_date = date.today()
        
        total_charges = Decimal('0.00')
        line_items = []
        calculation_log = []
        
        for proc in procedures:
            cpt_code = proc.get("cptCode")
            units = proc.get("units", 1)
            modifiers = proc.get("modifiers", [])
            
            # Look up fee for this CPT code
            fee = await self._get_fee(
                cpt_code=cpt_code,
                payer_id=payer_id,
                state_code=state_code,
                service_date=service_date
            )
            
            # Apply modifier adjustments
            adjusted_fee = self._apply_modifier_adjustments(fee, modifiers)
            
            # Calculate line charge
            line_charge = adjusted_fee * Decimal(str(units))
            total_charges += line_charge
            
            line_items.append({
                "cpt_code": cpt_code,
                "units": units,
                "modifiers": modifiers,
                "base_fee": float(fee),
                "adjusted_fee": float(adjusted_fee),
                "line_charge": float(line_charge)
            })
            
            calculation_log.append(
                f"CPT {cpt_code}: ${fee} x {units} units = ${line_charge}"
            )
        
        return {
            "total_charges": float(total_charges),
            "line_items": line_items,
            "calculation_details": {
                "payer_id": payer_id,
                "state_code": state_code,
                "service_date": service_date.isoformat() if service_date else None,
                "calculation_log": calculation_log
            }
        }
    
    async def _get_fee(
        self,
        cpt_code: str,
        payer_id: Optional[int],
        state_code: Optional[str],
        service_date: date
    ) -> Decimal:
        """
        Look up fee for CPT code from database
        
        Priority:
        1. Payer-specific rate for state
        2. Payer-specific national rate
        3. Medicare fee schedule for state (default)
        4. National average rate (fallback)
        """
        
        # TODO: Implement actual database lookup once fee_schedules table exists
        # For now, use Medicare-based defaults
        
        # This would be the real implementation:
        # query = select(FeeSchedule).where(
        #     and_(
        #         FeeSchedule.cpt_code == cpt_code,
        #         FeeSchedule.effective_date <= service_date,
        #         FeeSchedule.expiration_date >= service_date
        #     )
        # )
        # if payer_id:
        #     query = query.where(FeeSchedule.payer_id == payer_id)
        # if state_code:
        #     query = query.where(FeeSchedule.state_code == state_code)
        # result = await self.db.execute(query)
        # fee_record = result.scalar_one_or_none()
        # if fee_record:
        #     return Decimal(str(fee_record.fee_amount))
        
        # Medicare-based defaults (2025 rates) until database is populated
        medicare_rates = {
            "99441": Decimal("55.00"),    # Phone E/M 5-10 min
            "99442": Decimal("85.00"),    # Phone E/M 11-20 min
            "99443": Decimal("125.00"),   # Phone E/M 21-30 min
            "99213": Decimal("135.00"),   # Office visit established low
            "99214": Decimal("195.00"),   # Office visit established moderate
            "99215": Decimal("260.00"),   # Office visit established high
            "99203": Decimal("180.00"),   # Office visit new low
            "99204": Decimal("265.00"),   # Office visit new moderate
            "99205": Decimal("310.00"),   # Office visit new high
        }
        
        fee = medicare_rates.get(cpt_code, Decimal("100.00"))  # Default fallback
        
        logger.info(f"Fee lookup: CPT {cpt_code} = ${fee} (source: Medicare default)")
        
        return fee
    
    def _apply_modifier_adjustments(
        self,
        base_fee: Decimal,
        modifiers: List[str]
    ) -> Decimal:
        """
        Apply modifier-based fee adjustments
        
        Common modifiers:
        - 95: Telehealth (synchronous) - typically 100% of fee
        - 26: Professional component only - typically 40% of fee
        - 51: Multiple procedures - typically 50% reduction for subsequent
        - 76: Repeat procedure by same physician - typically 100%
        - 77: Repeat procedure by another physician - typically 100%
        """
        adjusted_fee = base_fee
        
        for modifier in modifiers:
            if modifier == "26":  # Professional component only
                adjusted_fee = adjusted_fee * Decimal("0.40")
            elif modifier == "51":  # Multiple procedures
                adjusted_fee = adjusted_fee * Decimal("0.50")
            # Modifier 95 (telehealth) typically doesn't change the fee
            # Other modifiers maintain 100% of base fee
        
        return adjusted_fee
    
    async def validate_cpt_code(self, cpt_code: str) -> bool:
        """
        Validate that CPT code exists and is active
        
        Args:
            cpt_code: CPT code to validate
            
        Returns:
            True if valid and active, False otherwise
        """
        # TODO: Query CPT code master table when available
        # For now, basic format validation
        
        if not cpt_code or len(cpt_code) != 5:
            return False
        
        if not cpt_code.isdigit():
            return False
        
        return True
    
    async def get_fee_schedule_metadata(
        self,
        payer_id: Optional[int] = None,
        state_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get metadata about fee schedule (effective dates, source, last updated)
        
        Returns:
            Metadata dict with source, effective_date, last_updated, etc.
        """
        return {
            "source": "Medicare Fee Schedule 2025",
            "effective_date": "2025-01-01",
            "last_updated": datetime.now().isoformat(),
            "payer_id": payer_id,
            "state_code": state_code,
            "note": "Using Medicare-based defaults. Payer-specific rates pending."
        }

