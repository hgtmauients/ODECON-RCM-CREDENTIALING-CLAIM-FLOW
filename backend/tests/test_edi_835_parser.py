"""
Unit tests for the EDI 835 parser (services.edi_processor._parse_835_content).

Pure parser tests — no DB, no async. Verifies CAS triplet extraction,
LQ remark code parsing, and shape produced for downstream consumers.
"""

import pytest

from services.edi_processor import EDIProcessor


def test_parse_835_empty_returns_empty_lists():
    out = EDIProcessor._parse_835_content("")
    assert out == {"payments": [], "denials": [], "total_paid": 0.0}


def test_parse_835_single_payment_no_cas():
    content = "ISA*~CLP*CLM-1*1*100.00*100.00**MC*REFNUM~"
    out = EDIProcessor._parse_835_content(content)
    assert out["total_paid"] == 100.00
    assert len(out["payments"]) == 1
    assert out["payments"][0]["claim_number"] == "CLM-1"
    assert out["payments"][0]["paid_amount"] == 100.00
    assert out["denials"] == []


def test_parse_835_single_denial_with_one_cas():
    content = "ISA*~CLP*CLM-DEN*4*100.00*0.00**MC*REFNUM~CAS*CO*16*100.00~"
    out = EDIProcessor._parse_835_content(content)
    assert out["payments"] == []
    assert len(out["denials"]) == 1
    d = out["denials"][0]
    assert d["claim_number"] == "CLM-DEN"
    assert d["carc"] == "CO-16"
    assert d["denied_amount"] == 100.00
    assert d["carc_codes"] == [{"group": "CO", "code": "16", "amount": 100.00}]


def test_parse_835_cas_with_multiple_triplets():
    """CAS segments can carry up to 6 (group, reason, amount) triplets."""
    content = (
        "ISA*~"
        "CLP*CLM-MULTI*4*100.00*0.00**MC*REFNUM~"
        # CAS with 3 triplets in one segment
        "CAS*CO*16*40.00*45*30.00*97*30.00~"
    )
    out = EDIProcessor._parse_835_content(content)
    assert len(out["denials"]) == 1
    d = out["denials"][0]
    assert d["denied_amount"] == 100.00
    codes = d["carc_codes"]
    assert len(codes) == 3
    assert {c["code"] for c in codes} == {"16", "45", "97"}
    assert all(c["group"] == "CO" for c in codes)


def test_parse_835_lq_remark_code():
    content = (
        "ISA*~"
        "CLP*CLM-RMK*4*100.00*0.00~"
        "CAS*CO*16*100.00~"
        "LQ*HE*M51~"
    )
    out = EDIProcessor._parse_835_content(content)
    d = out["denials"][0]
    assert d["rarc"] == "M51"


def test_parse_835_multiple_claims_segregates_payments_and_denials():
    content = (
        "ISA*~"
        "CLP*PAID-1*1*150.00*150.00~"
        "CLP*DENIED-1*4*200.00*0.00~"
        "CAS*CO*29*200.00~"
        "CLP*PAID-2*1*75.50*75.50~"
    )
    out = EDIProcessor._parse_835_content(content)
    assert len(out["payments"]) == 2
    assert len(out["denials"]) == 1
    assert out["total_paid"] == 150.00 + 0.00 + 75.50  # CLP04 = paid amount
    assert {p["claim_number"] for p in out["payments"]} == {"PAID-1", "PAID-2"}
    assert out["denials"][0]["claim_number"] == "DENIED-1"


def test_parse_835_zero_pay_no_adjustments_treated_as_payment():
    """A CLP with paid=0 and no CAS still records a payment (visibility)."""
    content = "ISA*~CLP*CLM-ZERO*1*50.00*0.00~"
    out = EDIProcessor._parse_835_content(content)
    assert len(out["payments"]) == 1
    assert out["payments"][0]["paid_amount"] == 0.0
    assert out["denials"] == []
