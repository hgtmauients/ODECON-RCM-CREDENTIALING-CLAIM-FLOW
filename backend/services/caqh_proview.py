"""
ClaimFlow - CAQH ProView Integration Service.
Pulls provider credentialing data from CAQH ProView API.

CAQH ProView is the universal provider credentialing database used by most US payers.
Providers maintain their own profiles; participating organizations can query them.

Reads credentials from per-tenant DB settings first, falls back to env vars.
"""

import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

CAQH_BASE_URL = os.getenv("CAQH_BASE_URL", "https://proview-demo.caqh.org/RosterAPI/api")


def _env_creds() -> tuple:
    return (
        os.getenv("CAQH_ORG_ID", ""),
        os.getenv("CAQH_USERNAME", ""),
        os.getenv("CAQH_PASSWORD", ""),
    )


def is_configured() -> bool:
    org, user, pw = _env_creds()
    return bool(org and user and pw)


async def is_configured_for_tenant(db: AsyncSession, tenant_id: str) -> bool:
    from core.tenant_config import get_tenant_setting
    org = await get_tenant_setting(db, tenant_id, "caqh_org_id")
    user = await get_tenant_setting(db, tenant_id, "caqh_username")
    pw = await get_tenant_setting(db, tenant_id, "caqh_password")
    return bool(org and user and pw)


class CAQHProViewClient:
    """
    Client for CAQH ProView Roster API and Provider Data API.

    API Capabilities:
    - Roster: Add/remove providers from your org's roster
    - Provider Status: Check attestation status
    - Provider Data: Pull full credentialing profile (licenses, education, malpractice, etc.)
    """

    def __init__(
        self,
        org_id: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.base_url = CAQH_BASE_URL
        env_org, env_user, env_pw = _env_creds()
        self.org_id = org_id or env_org
        self.auth = (username or env_user, password or env_pw)

    async def get_provider_status(self, caqh_provider_id: str) -> Dict[str, Any]:
        """
        Check provider's CAQH ProView attestation status.
        """
        if not (self.org_id and self.auth[0] and self.auth[1]):
            return {"provider_found": False, "error": "CAQH credentials not configured"}

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self.base_url}/Roster",
                    params={
                        "organizationId": self.org_id,
                        "caqhProviderId": caqh_provider_id,
                    },
                    auth=self.auth,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "provider_found": True,
                        "caqh_provider_id": caqh_provider_id,
                        "roster_status": data.get("roster_status", "UNKNOWN"),
                        "provider_status": data.get("provider_status", ""),
                        "provider_status_date": data.get("provider_status_date", ""),
                        "authorization_flag": data.get("authorization_flag", "N"),
                    }
                elif resp.status_code == 404:
                    return {"provider_found": False, "caqh_provider_id": caqh_provider_id}
                else:
                    return {"provider_found": False, "error": f"CAQH API returned {resp.status_code}"}

        except Exception as e:
            logger.error(f"CAQH status check failed: {e}")
            return {"provider_found": False, "error": str(e)}

    async def get_provider_data(self, caqh_provider_id: str) -> Dict[str, Any]:
        """
        Pull full provider credentialing profile from CAQH ProView.
        """
        if not (self.org_id and self.auth[0] and self.auth[1]):
            return {"success": False, "error": "CAQH credentials not configured"}

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self.base_url}/ProviderData",
                    params={
                        "organizationId": self.org_id,
                        "caqhProviderId": caqh_provider_id,
                        "attestation_date": "",
                    },
                    auth=self.auth,
                )

                if resp.status_code != 200:
                    return {"success": False, "error": f"CAQH API returned {resp.status_code}: {resp.text}"}

                raw = resp.json()
                return self._parse_provider_data(raw, caqh_provider_id)

        except Exception as e:
            logger.error(f"CAQH data pull failed for {caqh_provider_id}: {e}")
            return {"success": False, "error": str(e)}

    def _parse_provider_data(self, raw: Dict[str, Any], caqh_id: str) -> Dict[str, Any]:
        """Parse CAQH ProView response into ClaimFlow-compatible structure."""
        provider = raw.get("provider", raw)

        licenses = []
        for lic in provider.get("licenses", provider.get("state_licenses", [])):
            licenses.append({
                "state": lic.get("state", lic.get("license_state", "")),
                "license_number": lic.get("license_number", ""),
                "license_type": lic.get("license_type", "MD"),
                "status": lic.get("license_status", lic.get("status", "")),
                "issue_date": lic.get("issue_date", ""),
                "expiration_date": lic.get("expiration_date", ""),
            })

        certifications = []
        for cert in provider.get("board_certifications", provider.get("certifications", [])):
            certifications.append({
                "board_name": cert.get("certifying_board", cert.get("board_name", "")),
                "specialty": cert.get("specialty", ""),
                "status": cert.get("certification_status", cert.get("status", "")),
                "effective_date": cert.get("effective_date", cert.get("initial_certification_date", "")),
                "expiration_date": cert.get("expiration_date", ""),
            })

        malpractice = []
        for ins in provider.get("malpractice_insurance", provider.get("liability_insurance", [])):
            malpractice.append({
                "carrier_name": ins.get("insurance_carrier", ins.get("carrier_name", "")),
                "policy_number": ins.get("policy_number", ""),
                "coverage_per_occurrence": ins.get("amount_per_occurrence", ins.get("per_occurrence", "")),
                "coverage_aggregate": ins.get("aggregate_amount", ins.get("aggregate", "")),
                "effective_date": ins.get("effective_date", ""),
                "expiration_date": ins.get("expiration_date", ""),
            })

        education = []
        for edu in provider.get("education", provider.get("medical_education", [])):
            education.append({
                "institution": edu.get("school_name", edu.get("institution", "")),
                "degree": edu.get("degree", ""),
                "graduation_date": edu.get("graduation_date", edu.get("completion_date", "")),
                "type": edu.get("education_type", "medical_school"),
            })

        dea = []
        for d in provider.get("dea_certificates", provider.get("dea", [])):
            dea.append({
                "dea_number": d.get("dea_number", ""),
                "state": d.get("state", ""),
                "expiration_date": d.get("expiration_date", ""),
                "schedules": d.get("schedules", []),
            })

        privileges = []
        for priv in provider.get("hospital_privileges", provider.get("privileges", [])):
            privileges.append({
                "hospital_name": priv.get("hospital_name", priv.get("facility_name", "")),
                "status": priv.get("status", priv.get("privilege_status", "")),
                "start_date": priv.get("start_date", priv.get("appointment_date", "")),
                "department": priv.get("department", ""),
            })

        return {
            "success": True,
            "caqh_provider_id": caqh_id,
            "pulled_at": datetime.utcnow().isoformat(),
            "demographics": {
                "first_name": provider.get("first_name", ""),
                "last_name": provider.get("last_name", ""),
                "middle_name": provider.get("middle_name", ""),
                "suffix": provider.get("suffix", ""),
                "date_of_birth": provider.get("birth_date", provider.get("date_of_birth", "")),
                "gender": provider.get("gender", ""),
                "npi": provider.get("npi", provider.get("provider_npi", "")),
                "ssn_last_four": provider.get("ssn_last_four", ""),
                "email": provider.get("email", ""),
                "phone": provider.get("phone", provider.get("practice_phone", "")),
            },
            "licenses": licenses,
            "board_certifications": certifications,
            "malpractice_insurance": malpractice,
            "education": education,
            "dea_certificates": dea,
            "hospital_privileges": privileges,
            "practice_locations": provider.get("practice_locations", []),
            "disclosure_answers": provider.get("disclosure_questions", provider.get("disclosures", [])),
        }

    async def add_to_roster(self, provider_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a provider to your organization's CAQH roster."""
        if not (self.org_id and self.auth[0] and self.auth[1]):
            return {"success": False, "error": "CAQH credentials not configured"}

        try:
            import httpx
            payload = {
                "organizationId": self.org_id,
                "firstName": provider_data.get("first_name", ""),
                "lastName": provider_data.get("last_name", ""),
                "npi": provider_data.get("npi", ""),
                "dateOfBirth": provider_data.get("date_of_birth", ""),
                "stateCode": provider_data.get("state_code", ""),
                "licenseNumber": provider_data.get("license_number", ""),
                "type": "PV",
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.base_url}/Roster",
                    json=payload,
                    auth=self.auth,
                )

                if resp.status_code in (200, 201):
                    data = resp.json()
                    return {
                        "success": True,
                        "caqh_provider_id": data.get("caqhProviderId", ""),
                        "message": "Provider added to CAQH roster",
                    }
                else:
                    return {"success": False, "error": f"CAQH returned {resp.status_code}: {resp.text}"}

        except Exception as e:
            logger.error(f"CAQH roster add failed: {e}")
            return {"success": False, "error": str(e)}

    async def search_by_npi(self, npi: str) -> Dict[str, Any]:
        """Search for a provider's CAQH ID using their NPI."""
        if not (self.org_id and self.auth[0] and self.auth[1]):
            return {"found": False, "error": "CAQH credentials not configured"}

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self.base_url}/Roster",
                    params={
                        "organizationId": self.org_id,
                        "npi": npi,
                    },
                    auth=self.auth,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    providers = data if isinstance(data, list) else [data]
                    if providers:
                        return {
                            "found": True,
                            "caqh_provider_id": providers[0].get("caqhProviderId", ""),
                            "roster_status": providers[0].get("roster_status", ""),
                        }
                return {"found": False}

        except Exception as e:
            logger.error(f"CAQH NPI search failed: {e}")
            return {"found": False, "error": str(e)}


async def get_tenant_client(db: AsyncSession, tenant_id: str) -> CAQHProViewClient:
    """Build a CAQHProViewClient using the tenant's stored credentials."""
    from core.tenant_config import get_tenant_setting
    org_id = await get_tenant_setting(db, tenant_id, "caqh_org_id", default="")
    username = await get_tenant_setting(db, tenant_id, "caqh_username", default="")
    password = await get_tenant_setting(db, tenant_id, "caqh_password", default="")
    return CAQHProViewClient(org_id=org_id, username=username, password=password)


# Global client using env vars only (backward-compatible)
caqh_client = CAQHProViewClient()
