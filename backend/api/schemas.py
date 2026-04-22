"""
ClaimFlow - Pydantic schemas for request/response validation.

All mutating endpoints should use a typed schema instead of Dict[str, Any]
to get free input validation, type coercion, and OpenAPI docs.
"""

from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import List, Optional, Any, Dict
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


# ──────────── Credentialing ────────────

class LicenseEntry(BaseModel):
    state: str = Field(..., min_length=2, max_length=2)
    license_number: str = Field(..., min_length=1, max_length=50)
    license_type: Optional[str] = "MD"
    expiration: Optional[str] = None
    status: Optional[str] = "active"


class SpecialtyEntry(BaseModel):
    specialty: str = Field(..., min_length=1, max_length=100)
    board: Optional[str] = None
    certified: bool = False
    expiration: Optional[str] = None


class DEAEntry(BaseModel):
    dea_number: str = Field(..., min_length=1, max_length=20)
    state: Optional[str] = Field(None, max_length=2)
    schedules: Optional[Any] = None
    expiration: Optional[str] = None


class CNEDEntry(BaseModel):
    state: str = Field(..., min_length=2, max_length=2)
    certificate_number: str = Field(..., min_length=1, max_length=50)
    expiration: Optional[str] = None


class ProviderCreate(BaseModel):
    """Used for manual provider creation in the Credentialing Queue."""
    model_config = ConfigDict(extra="ignore")

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    npi: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    state_code: Optional[str] = Field(None, max_length=2)
    license_number: Optional[str] = Field(None, max_length=50)
    specialty: Optional[str] = None
    provider_type: Optional[str] = "MD"
    date_of_birth: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=20)
    license_url: Optional[str] = None
    licenses: Optional[List[LicenseEntry]] = None
    specialties: Optional[List[SpecialtyEntry]] = None
    dea_certificates: Optional[List[DEAEntry]] = None
    cned_certificates: Optional[List[CNEDEntry]] = None
    run_checks: bool = True


class ProviderUpdate(BaseModel):
    """Editable fields on an existing provider."""
    model_config = ConfigDict(extra="ignore")

    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    email: Optional[EmailStr] = None
    npi: Optional[str] = Field(None, min_length=10, max_length=10, pattern=r"^\d{10}$")
    state_code: Optional[str] = Field(None, max_length=2)
    license_number: Optional[str] = Field(None, max_length=50)
    specialty: Optional[str] = None
    provider_type: Optional[str] = None
    date_of_birth: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=20)
    license_url: Optional[str] = None
    admin_notes: Optional[str] = None
    licenses: Optional[List[LicenseEntry]] = None
    specialties: Optional[List[SpecialtyEntry]] = None
    dea_certificates: Optional[List[DEAEntry]] = None
    cned_certificates: Optional[List[CNEDEntry]] = None


class ApproveRequest(BaseModel):
    notes: Optional[str] = None


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


# ──────────── Tenants & Settings ────────────

class TenantUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = Field(None, max_length=255)
    npi: Optional[str] = Field(None, max_length=10)
    tax_id: Optional[str] = Field(None, max_length=20)
    address_line_1: Optional[str] = Field(None, max_length=255)
    address_line_2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=128)
    state: Optional[str] = Field(None, max_length=2)
    zip_code: Optional[str] = Field(None, max_length=10)
    phone: Optional[str] = Field(None, max_length=20)
    billing_contact_email: Optional[EmailStr] = None
    settings: Optional[Dict[str, Any]] = None


class TenantSettingsUpdate(BaseModel):
    """Per-tenant integration settings. Only allow-listed keys are persisted."""
    model_config = ConfigDict(extra="ignore")

    api_cert_key: Optional[str] = None
    caqh_org_id: Optional[str] = None
    caqh_username: Optional[str] = None
    caqh_password: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[Any] = None
    smtp_user: Optional[str] = None
    smtp_pass: Optional[str] = None
    from_email: Optional[str] = None
    webhook_secret: Optional[str] = None


class TestSmtpRequest(BaseModel):
    to: Optional[EmailStr] = None


# ──────────── Webhooks ────────────

class ProviderSignupWebhook(BaseModel):
    """Inbound webhook from an external signup form."""
    model_config = ConfigDict(extra="allow")  # Permit additional pass-through fields

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    npi: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    state_code: Optional[str] = Field(None, max_length=2)
    license_number: Optional[str] = None
    license_url: Optional[str] = None
