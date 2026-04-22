"""
ClaimFlow - API-Cert Integration Service.
Real-time healthcare license verification across 50 states + territories.
Also includes OIG, SAM, CMS preclusion, and DEA checks in one call.

Free tier: 50 verifications/month. Sign up at api-cert.com.
Reads the API key from per-tenant DB settings first, falls back to API_CERT_KEY env var.
"""

import os
import logging
from typing import Dict, Any, Optional, List

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

API_CERT_BASE_URL = os.getenv("API_CERT_BASE_URL", "https://api.api-cert.com")

_coverage_cache: Optional[Dict[str, List[str]]] = None


def _env_key() -> str:
    return os.getenv("API_CERT_KEY", "")


def is_configured() -> bool:
    return bool(_env_key())


async def is_configured_for_tenant(db: AsyncSession, tenant_id: str) -> bool:
    """Check whether API-Cert is configured at either tenant or env level."""
    from core.tenant_config import get_tenant_setting
    key = await get_tenant_setting(db, tenant_id, "api_cert_key")
    return bool(key)


async def get_tenant_api_key(db: AsyncSession, tenant_id: str) -> str:
    """Resolve API-Cert key: tenant DB → env var."""
    from core.tenant_config import get_tenant_setting
    return await get_tenant_setting(db, tenant_id, "api_cert_key", default="") or ""


class APICertClient:
    """Client for API-Cert healthcare license verification API."""

    def __init__(self, api_key: Optional[str] = None):
        self.base_url = API_CERT_BASE_URL
        self.api_key = api_key or _env_key()

    async def get_coverage(self) -> Dict[str, List[str]]:
        global _coverage_cache
        if _coverage_cache:
            return _coverage_cache

        if not self.api_key:
            return {}

        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self.base_url}/v1/states",
                    headers={"X-API-Key": self.api_key},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    states = data.get("states", [])
                    coverage = {}
                    for s in states:
                        code = s.get("state_code", "")
                        types = s.get("supported_license_types", [])
                        if code and types:
                            coverage[code] = types
                    _coverage_cache = coverage
                    return coverage
        except Exception as e:
            logger.warning(f"Failed to fetch API-Cert coverage: {e}")
        return {}

    async def supports_state(self, state: str, license_type: str = "MD") -> bool:
        coverage = await self.get_coverage()
        supported_types = coverage.get(state.upper(), [])
        return license_type.upper() in supported_types

    async def verify_license(
        self,
        last_name: str,
        state: str,
        license_type: str = "MD",
        first_name: Optional[str] = None,
        license_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Verify a healthcare license via API-Cert.
        Returns structured result with license status, exclusion checks, and DEA info.
        """
        if not self.api_key:
            return {
                "verified": False,
                "source": "api_cert",
                "error": "API_CERT_KEY not configured",
            }

        if not await self.supports_state(state, license_type):
            return {
                "verified": False,
                "source": "api_cert",
                "state": state,
                "license_type": license_type,
                "status": "NOT_COVERED",
                "message": f"API-Cert does not cover {license_type} in {state}",
            }

        try:
            import httpx
            payload: Dict[str, Any] = {
                "license_type": license_type.upper(),
                "state": state.upper(),
                "last_name": last_name,
            }
            if first_name:
                payload["first_name"] = first_name
            if license_number:
                payload["license_number"] = license_number

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/verify",
                    headers={
                        "X-API-Key": self.api_key,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "verified": data.get("verified", False),
                        "source": "api_cert",
                        "state": state,
                        "license_type": license_type,
                        "full_name": data.get("full_name"),
                        "license_number": data.get("license_number"),
                        "status": data.get("status"),
                        "issue_date": data.get("issue_date"),
                        "expiration_date": data.get("expiration_date"),
                        "disciplinary_flag": data.get("disciplinary_flag"),
                        "npi": data.get("npi"),
                        "oig_excluded": data.get("oig_excluded"),
                        "sam_excluded": data.get("sam_excluded"),
                        "cms_precluded": data.get("cms_precluded"),
                        "dea_number": data.get("dea_number"),
                        "dea_status": data.get("dea_status"),
                        "dea_expiration": data.get("dea_expiration"),
                        "latency_ms": data.get("latency_ms"),
                        "match_count": data.get("match_count", 0),
                    }
                elif resp.status_code == 429:
                    return {
                        "verified": False,
                        "source": "api_cert",
                        "error": "Rate limit exceeded (free tier: 50/month)",
                    }
                else:
                    return {
                        "verified": False,
                        "source": "api_cert",
                        "error": f"API-Cert returned {resp.status_code}: {resp.text}",
                    }

        except Exception as e:
            logger.error(f"API-Cert verification failed: {e}")
            return {"verified": False, "source": "api_cert", "error": str(e)}

    async def get_usage(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"error": "Not configured"}

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.base_url}/v1/usage",
                    headers={"X-API-Key": self.api_key},
                )
                if resp.status_code == 200:
                    return resp.json()
                return {"error": f"Status {resp.status_code}"}
        except Exception as e:
            return {"error": str(e)}


async def get_tenant_client(db: AsyncSession, tenant_id: str) -> APICertClient:
    """Build an APICertClient using the tenant's stored API key."""
    key = await get_tenant_api_key(db, tenant_id)
    return APICertClient(api_key=key)


# Global client using env var only (backward-compatible)
api_cert_client = APICertClient()
