"""
Fee Schedule Service
Manages CPT code pricing by payer, state, and date
Ensures accurate billing rates with audit trail
"""

import os
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, case, func
from typing import List, Dict, Any, Optional
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from models.rcm import FeeSchedule, PayerProfile

logger = logging.getLogger(__name__)
ENV = os.getenv("ENV", "development")


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

    _DEFAULT_MEDICARE_RATES = {
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

    _MODIFIER_MULTIPLIERS = {
        "50": Decimal("1.50"),  # Bilateral procedure
        "51": Decimal("0.50"),  # Multiple procedures
        "52": Decimal("0.50"),  # Reduced services
        "62": Decimal("0.625"),  # Co-surgeons
        "80": Decimal("0.16"),  # Assistant surgeon
    }
    
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
    
    async def get_fee_for_cpt(
        self,
        cpt_code: str,
        payer: Optional[str | int] = None,
        state: Optional[str] = None,
        service_date: Optional[date] = None,
    ) -> Decimal:
        """
        Public lookup helper used by tests and billing flows.
        """
        if not cpt_code:
            raise ValueError("cpt_code is required")
        if service_date is None:
            service_date = date.today()
        return await self._get_fee(
            cpt_code=cpt_code,
            payer_id=payer,
            state_code=state,
            service_date=service_date,
        )

    async def calculate_charge_with_modifiers(
        self,
        cpt_code: str,
        modifiers: List[str],
        payer: Optional[str | int] = None,
        state: Optional[str] = None,
        service_date: Optional[date] = None,
    ) -> Decimal:
        """
        Public helper for computing a single CPT charge.
        """
        base_fee = await self.get_fee_for_cpt(cpt_code=cpt_code, payer=payer, state=state, service_date=service_date)
        return self._apply_modifier_adjustments(base_fee, modifiers)

    @staticmethod
    def _extract_fee_amount(record: Any) -> Optional[Decimal]:
        for field in ("allowable_amount", "fee", "non_facility_rate", "facility_rate"):
            value = getattr(record, field, None)
            if value is not None:
                if isinstance(value, Decimal):
                    return value
                if isinstance(value, (int, float)):
                    return Decimal(str(value))
                if isinstance(value, str):
                    try:
                        return Decimal(value)
                    except InvalidOperation:
                        continue
        return None

    def _default_rate(self, cpt_code: str) -> Decimal:
        return self._DEFAULT_MEDICARE_RATES.get(cpt_code, Decimal("100.00"))

    async def _get_fee(
        self,
        cpt_code: str,
        payer_id: Optional[str | int],
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
        
        query = (
            select(FeeSchedule)
            .join(PayerProfile, PayerProfile.id == FeeSchedule.payer_id)
            .where(and_(
                FeeSchedule.cpt_code == cpt_code,
                FeeSchedule.effective_date <= service_date,
                or_(FeeSchedule.end_date.is_(None), FeeSchedule.end_date >= service_date),
            ))
        )

        if payer_id is not None:
            if isinstance(payer_id, int):
                query = query.where(FeeSchedule.payer_id == payer_id)
            else:
                payer_text = str(payer_id).strip()
                if payer_text.isdigit():
                    query = query.where(FeeSchedule.payer_id == int(payer_text))
                else:
                    query = query.where(
                        or_(
                            PayerProfile.name == payer_text,
                            PayerProfile.display_name == payer_text,
                            PayerProfile.payer_id == payer_text,
                        )
                    )

        if state_code:
            query = query.where(or_(FeeSchedule.state_code == state_code, FeeSchedule.state_code.is_(None)))
            state_rank = case(
                (FeeSchedule.state_code == state_code, 0),
                (FeeSchedule.state_code.is_(None), 1),
                else_=2,
            )
            query = query.order_by(state_rank, FeeSchedule.effective_date.desc())
        else:
            query = query.order_by(FeeSchedule.effective_date.desc())

        result = await self.db.execute(query.limit(1))
        fee_record = result.scalar_one_or_none()
        if fee_record is not None:
            amount = self._extract_fee_amount(fee_record)
            if amount is not None:
                logger.info(
                    "Fee lookup: CPT=%s payer=%s state=%s amount=%s source=fee_schedules",
                    cpt_code, payer_id, state_code, amount,
                )
                return amount

        if payer_id is not None:
            raise FeeScheduleNotFoundError(
                f"No active fee schedule for CPT {cpt_code}, payer={payer_id}, state={state_code}, date={service_date}"
            )

        if ENV == "development":
            fallback = self._default_rate(cpt_code)
            logger.warning(
                "Fee schedule miss in development: CPT=%s payer=%s state=%s using fallback=%s",
                cpt_code, payer_id, state_code, fallback,
            )
            return fallback

        raise FeeScheduleNotFoundError(
            f"No active fee schedule for CPT {cpt_code}, payer={payer_id}, state={state_code}, date={service_date}"
        )
    
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
            elif modifier in self._MODIFIER_MULTIPLIERS:
                adjusted_fee = adjusted_fee * self._MODIFIER_MULTIPLIERS[modifier]
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
        filters = []
        if payer_id is not None:
            if isinstance(payer_id, int):
                filters.append(FeeSchedule.payer_id == payer_id)
            else:
                payer_text = str(payer_id).strip()
                if payer_text.isdigit():
                    filters.append(FeeSchedule.payer_id == int(payer_text))
                else:
                    filters.append(
                        FeeSchedule.payer_id.in_(
                            select(PayerProfile.id).where(
                                or_(
                                    PayerProfile.name == payer_text,
                                    PayerProfile.display_name == payer_text,
                                    PayerProfile.payer_id == payer_text,
                                )
                            )
                        )
                    )
        if state_code:
            filters.append(or_(FeeSchedule.state_code == state_code, FeeSchedule.state_code.is_(None)))

        query = select(
            func.count(FeeSchedule.id),
            func.min(FeeSchedule.effective_date),
            func.max(FeeSchedule.effective_date),
            func.max(FeeSchedule.updated_at),
        )
        if filters:
            query = query.where(and_(*filters))
        row = (await self.db.execute(query)).one()
        count, min_effective, max_effective, last_updated = row

        return {
            "source": "fee_schedules",
            "record_count": int(count or 0),
            "effective_date_min": min_effective.isoformat() if min_effective else None,
            "effective_date_max": max_effective.isoformat() if max_effective else None,
            "last_updated": (last_updated or datetime.now()).isoformat(),
            "payer_id": payer_id,
            "state_code": state_code,
            "note": "No active fee schedules found for filters." if not count else None,
        }

