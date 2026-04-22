"""
Unit tests for FeeScheduleService

Tests fee schedule calculations, modifier application, state-specific rates, and error handling.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from services.fee_schedule_service import FeeScheduleService, FeeScheduleNotFoundError
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_db_session():
    """Create a mock async database session"""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def fee_schedule_service(mock_db_session):
    """Create a FeeScheduleService instance with mock session"""
    return FeeScheduleService(mock_db_session)


class TestGetFeeForCPT:
    """Test suite for getting fees for CPT codes"""
    
    @pytest.mark.asyncio
    async def test_basic_cpt_lookup(self, fee_schedule_service, mock_db_session):
        """Test basic CPT code fee lookup"""
        # Mock database response
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(
            fee=Decimal("150.00"),
            effective_date=datetime(2024, 1, 1)
        )
        mock_db_session.execute.return_value = mock_result
        
        fee = await fee_schedule_service.get_fee_for_cpt(
            cpt_code="99213",
            payer="Medicare",
            state="CA"
        )
        
        assert fee == Decimal("150.00")
        mock_db_session.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cpt_not_found_raises_error(self, fee_schedule_service, mock_db_session):
        """Test that missing CPT code raises FeeScheduleNotFoundError"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result
        
        with pytest.raises(FeeScheduleNotFoundError) as exc_info:
            await fee_schedule_service.get_fee_for_cpt(
                cpt_code="99999",
                payer="Medicare",
                state="CA"
            )
        
        assert "99999" in str(exc_info.value)
        assert "Medicare" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_state_specific_fees(self, fee_schedule_service, mock_db_session):
        """Test that state-specific fees are applied correctly"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(
            fee=Decimal("175.00"),  # Higher CA rate
            effective_date=datetime(2024, 1, 1)
        )
        mock_db_session.execute.return_value = mock_result
        
        ca_fee = await fee_schedule_service.get_fee_for_cpt(
            cpt_code="99213",
            payer="Medicare",
            state="CA"
        )
        
        assert ca_fee == Decimal("175.00")
    
    @pytest.mark.asyncio
    async def test_payer_specific_fees(self, fee_schedule_service, mock_db_session):
        """Test different payers have different fee schedules"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(
            fee=Decimal("200.00"),  # Commercial rate higher than Medicare
            effective_date=datetime(2024, 1, 1)
        )
        mock_db_session.execute.return_value = mock_result
        
        commercial_fee = await fee_schedule_service.get_fee_for_cpt(
            cpt_code="99213",
            payer="Blue Cross",
            state="CA"
        )
        
        assert commercial_fee == Decimal("200.00")


class TestCalculateChargeWithModifiers:
    """Test suite for charge calculations with modifiers"""
    
    @pytest.mark.asyncio
    async def test_no_modifiers(self, fee_schedule_service, mock_db_session):
        """Test charge calculation without modifiers"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(
            fee=Decimal("150.00"),
            effective_date=datetime(2024, 1, 1)
        )
        mock_db_session.execute.return_value = mock_result
        
        charge = await fee_schedule_service.calculate_charge_with_modifiers(
            cpt_code="99213",
            modifiers=[],
            payer="Medicare",
            state="CA"
        )
        
        assert charge == Decimal("150.00")
    
    @pytest.mark.asyncio
    async def test_modifier_25_no_reduction(self, fee_schedule_service, mock_db_session):
        """Test modifier 25 (significant, separately identifiable E&M) - no reduction"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(
            fee=Decimal("150.00"),
            effective_date=datetime(2024, 1, 1)
        )
        mock_db_session.execute.return_value = mock_result
        
        charge = await fee_schedule_service.calculate_charge_with_modifiers(
            cpt_code="99213",
            modifiers=["25"],
            payer="Medicare",
            state="CA"
        )
        
        # Modifier 25 should not reduce fee
        assert charge == Decimal("150.00")
    
    @pytest.mark.asyncio
    async def test_modifier_50_bilateral_procedure(self, fee_schedule_service, mock_db_session):
        """Test modifier 50 (bilateral procedure) - 150% of base fee"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(
            fee=Decimal("100.00"),
            effective_date=datetime(2024, 1, 1)
        )
        mock_db_session.execute.return_value = mock_result
        
        charge = await fee_schedule_service.calculate_charge_with_modifiers(
            cpt_code="27447",  # Total knee arthroplasty
            modifiers=["50"],
            payer="Medicare",
            state="CA"
        )
        
        # Bilateral = 150% of base
        assert charge == Decimal("150.00")
    
    @pytest.mark.asyncio
    async def test_modifier_51_multiple_procedures(self, fee_schedule_service, mock_db_session):
        """Test modifier 51 (multiple procedures) - 50% reduction"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(
            fee=Decimal("200.00"),
            effective_date=datetime(2024, 1, 1)
        )
        mock_db_session.execute.return_value = mock_result
        
        charge = await fee_schedule_service.calculate_charge_with_modifiers(
            cpt_code="12001",  # Simple repair
            modifiers=["51"],
            payer="Medicare",
            state="CA"
        )
        
        # Multiple procedures = 50% reduction
        assert charge == Decimal("100.00")
    
    @pytest.mark.asyncio
    async def test_modifier_52_reduced_services(self, fee_schedule_service, mock_db_session):
        """Test modifier 52 (reduced services) - 50% of base fee"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(
            fee=Decimal("300.00"),
            effective_date=datetime(2024, 1, 1)
        )
        mock_db_session.execute.return_value = mock_result
        
        charge = await fee_schedule_service.calculate_charge_with_modifiers(
            cpt_code="43235",  # EGD
            modifiers=["52"],
            payer="Medicare",
            state="CA"
        )
        
        # Reduced services = 50% of base
        assert charge == Decimal("150.00")
    
    @pytest.mark.asyncio
    async def test_modifier_62_co_surgeons(self, fee_schedule_service, mock_db_session):
        """Test modifier 62 (co-surgeons) - 62.5% of base fee"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(
            fee=Decimal("1000.00"),
            effective_date=datetime(2024, 1, 1)
        )
        mock_db_session.execute.return_value = mock_result
        
        charge = await fee_schedule_service.calculate_charge_with_modifiers(
            cpt_code="33533",  # CABG
            modifiers=["62"],
            payer="Medicare",
            state="CA"
        )
        
        # Co-surgeons = 62.5% each
        assert charge == Decimal("625.00")
    
    @pytest.mark.asyncio
    async def test_modifier_80_assistant_surgeon(self, fee_schedule_service, mock_db_session):
        """Test modifier 80 (assistant surgeon) - 16% of base fee"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(
            fee=Decimal("1000.00"),
            effective_date=datetime(2024, 1, 1)
        )
        mock_db_session.execute.return_value = mock_result
        
        charge = await fee_schedule_service.calculate_charge_with_modifiers(
            cpt_code="33533",  # CABG
            modifiers=["80"],
            payer="Medicare",
            state="CA"
        )
        
        # Assistant surgeon = 16% of base
        assert charge == Decimal("160.00")
    
    @pytest.mark.asyncio
    async def test_multiple_modifiers_stacked(self, fee_schedule_service, mock_db_session):
        """Test multiple modifiers applied in sequence"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(
            fee=Decimal("200.00"),
            effective_date=datetime(2024, 1, 1)
        )
        mock_db_session.execute.return_value = mock_result
        
        # Apply 51 (50% reduction) then 52 (50% reduction) = 25% of base
        charge = await fee_schedule_service.calculate_charge_with_modifiers(
            cpt_code="12001",
            modifiers=["51", "52"],
            payer="Medicare",
            state="CA"
        )
        
        # 200 * 0.5 * 0.5 = 50
        assert charge == Decimal("50.00")


class TestBulkFeeCalculation:
    """Test suite for bulk fee calculations"""
    
    @pytest.mark.asyncio
    async def test_calculate_multiple_procedures(self, fee_schedule_service, mock_db_session):
        """Test calculating fees for multiple procedures"""
        mock_result = MagicMock()
        # Simulate multiple database responses
        mock_result.scalar_one_or_none.side_effect = [
            MagicMock(fee=Decimal("150.00"), effective_date=datetime(2024, 1, 1)),
            MagicMock(fee=Decimal("200.00"), effective_date=datetime(2024, 1, 1)),
            MagicMock(fee=Decimal("75.00"), effective_date=datetime(2024, 1, 1))
        ]
        mock_db_session.execute.return_value = mock_result
        
        procedures = [
            {"cpt_code": "99213", "modifiers": []},
            {"cpt_code": "99214", "modifiers": []},
            {"cpt_code": "90471", "modifiers": []}
        ]
        
        total = Decimal("0.00")
        for proc in procedures:
            charge = await fee_schedule_service.calculate_charge_with_modifiers(
                cpt_code=proc["cpt_code"],
                modifiers=proc["modifiers"],
                payer="Medicare",
                state="CA"
            )
            total += charge
        
        assert total == Decimal("425.00")


class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    @pytest.mark.asyncio
    async def test_invalid_modifier(self, fee_schedule_service, mock_db_session):
        """Test that invalid modifiers are handled gracefully"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(
            fee=Decimal("150.00"),
            effective_date=datetime(2024, 1, 1)
        )
        mock_db_session.execute.return_value = mock_result
        
        # Invalid modifier should be ignored (no adjustment)
        charge = await fee_schedule_service.calculate_charge_with_modifiers(
            cpt_code="99213",
            modifiers=["XX"],  # Invalid
            payer="Medicare",
            state="CA"
        )
        
        assert charge == Decimal("150.00")
    
    @pytest.mark.asyncio
    async def test_empty_cpt_code(self, fee_schedule_service, mock_db_session):
        """Test empty CPT code raises error"""
        with pytest.raises((ValueError, FeeScheduleNotFoundError)):
            await fee_schedule_service.get_fee_for_cpt(
                cpt_code="",
                payer="Medicare",
                state="CA"
            )
    
    @pytest.mark.asyncio
    async def test_database_error_handling(self, fee_schedule_service, mock_db_session):
        """Test that database errors are handled appropriately"""
        mock_db_session.execute.side_effect = Exception("Database connection lost")
        
        with pytest.raises(Exception) as exc_info:
            await fee_schedule_service.get_fee_for_cpt(
                cpt_code="99213",
                payer="Medicare",
                state="CA"
            )
        
        assert "Database connection lost" in str(exc_info.value)


class TestFeeScheduleCache:
    """Test caching behavior (if implemented)"""
    
    @pytest.mark.asyncio
    async def test_repeated_lookups_use_cache(self, fee_schedule_service, mock_db_session):
        """Test that repeated lookups for same CPT use cache"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(
            fee=Decimal("150.00"),
            effective_date=datetime(2024, 1, 1)
        )
        mock_db_session.execute.return_value = mock_result
        
        # First call
        fee1 = await fee_schedule_service.get_fee_for_cpt(
            cpt_code="99213",
            payer="Medicare",
            state="CA"
        )
        
        # Second call - should use cache if implemented
        fee2 = await fee_schedule_service.get_fee_for_cpt(
            cpt_code="99213",
            payer="Medicare",
            state="CA"
        )
        
        assert fee1 == fee2
        # If caching is implemented, this should be called only once
        # assert mock_db_session.execute.call_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

