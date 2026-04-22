"""
ClaimFlow - Pydantic schemas for request/response validation.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date


class ClaimLineCreate(BaseModel):
    line_number: int = 1
    cpt_code: str = Field(..., min_length=3, max_length=10)
    cpt_description: Optional[str] = None
    modifiers: Optional[List[str]] = None
    diagnosis_pointers: Optional[List[int]] = None
    service_date: Optional[date] = None
    units: int = 1
    place_of_service: Optional[str] = None
    charge_amount: float = Field(..., gt=0)


class ClaimDiagnosisCreate(BaseModel):
    diagnosis_pointer: int = 1
    icd10_code: str = Field(..., min_length=3, max_length=10)
    icd10_description: Optional[str] = None
    is_primary: bool = False


class ClaimCreate(BaseModel):
    patient_id: Optional[int] = None
    provider_id: Optional[int] = None
    payer_id: Optional[int] = None
    service_date_from: date
    service_date_to: Optional[date] = None
    total_charges: float = Field(..., gt=0)
    claim_type: str = "professional"
    billing_provider_npi: Optional[str] = Field(None, max_length=10)
    rendering_provider_npi: Optional[str] = Field(None, max_length=10)
    prior_auth_number: Optional[str] = None
    lines: Optional[List[ClaimLineCreate]] = None
    diagnoses: Optional[List[ClaimDiagnosisCreate]] = None


class ClaimBatchSubmit(BaseModel):
    claim_ids: List[int] = Field(..., min_length=1)
    payer_id: int


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=128)
    npi: Optional[str] = Field(None, max_length=10)
    tax_id: Optional[str] = Field(None, max_length=20)
    settings: Optional[dict] = None


class PayerProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    display_name: Optional[str] = None
    payer_id: Optional[str] = None
    state_code: Optional[str] = Field(None, max_length=2)
    clearinghouse: Optional[str] = None
    connection_method: Optional[str] = None
    format_837_type: Optional[str] = "837P"
    filing_limit_days: int = 365


class DenialCaseUpdate(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    priority: Optional[str] = None
    root_cause: Optional[str] = None
    preventable: Optional[bool] = None


class ERAEnrollmentCreate(BaseModel):
    provider_id: str
    payer_id: int
    clearinghouse: Optional[str] = None
    bank_name: Optional[str] = None
    routing_number: Optional[str] = None
    account_number: Optional[str] = None
    account_type: Optional[str] = "checking"
