"""
Automated Provider Credentialing Service.
"""
import hashlib
import hmac
import httpx
import json
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from urllib.parse import urlparse

from core.http_client import request_with_retry

logger = logging.getLogger(__name__)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class CredentialingService:
    """Service for automated provider credentialing checks"""
    
    def __init__(self):
        self.npi_api_url = "https://npiregistry.cms.hhs.gov/api/"
        self.oig_api_url = "https://oig.hhs.gov/exclusions/api/search"
        self.sam_api_url = "https://api.sam.gov/api/entity-information/"
        self.state_license_provider_url = os.getenv("STATE_LICENSE_PROVIDER_URL", "").strip()
        self.background_check_provider_url = os.getenv("BACKGROUND_CHECK_PROVIDER_URL", "").strip()
        self.adapter_api_key = os.getenv("ADAPTER_API_KEY", "").strip()
        self.adapter_shared_secret = os.getenv("ADAPTER_SHARED_SECRET", "").strip()
        self.adapter_timeout_seconds = float(os.getenv("ADAPTER_CLIENT_TIMEOUT_SECONDS", "30"))
        self.adapter_max_retries = max(0, int(os.getenv("ADAPTER_CLIENT_MAX_RETRIES", "2")))
        self.adapter_retry_backoff_seconds = float(os.getenv("ADAPTER_CLIENT_RETRY_BACKOFF_SECONDS", "0.2"))
        self.integration_timeout_seconds = float(os.getenv("INTEGRATION_HTTP_TIMEOUT_SECONDS", "30"))
        self.integration_max_retries = max(0, int(os.getenv("INTEGRATION_HTTP_MAX_RETRIES", "2")))
        self.integration_retry_backoff_seconds = float(os.getenv("INTEGRATION_HTTP_RETRY_BACKOFF_SECONDS", "0.2"))

    @staticmethod
    def _canonical_body_bytes(payload: Optional[Dict[str, Any]]) -> bytes:
        if not payload:
            return b""
        return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()

    def _adapter_headers(
        self,
        *,
        method: str,
        url: str,
        body_bytes: bytes = b"",
    ) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.adapter_api_key:
            headers["X-Adapter-Key"] = self.adapter_api_key
        if self.adapter_shared_secret:
            timestamp = str(int(datetime.now(timezone.utc).timestamp()))
            path = urlparse(url).path or "/"
            body_hash = hashlib.sha256(body_bytes).hexdigest()
            message = f"{timestamp}.{method.upper()}.{path}.{body_hash}"
            signature = hmac.new(
                self.adapter_shared_secret.encode(),
                message.encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Adapter-Timestamp"] = timestamp
            headers["X-Adapter-Signature"] = signature
        return headers

    async def _request_adapter_with_retry(
        self,
        *,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        body_bytes = self._canonical_body_bytes(json_body)
        headers = self._adapter_headers(method=method, url=url, body_bytes=body_bytes)
        return await request_with_retry(
            method=method,
            url=url,
            params=params,
            json_body=json_body,
            headers=headers or None,
            timeout_seconds=self.adapter_timeout_seconds,
            max_retries=self.adapter_max_retries,
            retry_backoff_seconds=self.adapter_retry_backoff_seconds,
            retry_on_statuses=(500, 502, 503, 504),
            client_factory=httpx.AsyncClient,
        )
    
    async def verify_npi(self, npi: str) -> Dict[str, Any]:
        """
        Verify NPI with CMS NPPES Registry
        """
        try:
            response = await request_with_retry(
                method="GET",
                url=self.npi_api_url,
                params={
                    "number": npi,
                    "version": "2.1",
                },
                timeout_seconds=self.integration_timeout_seconds,
                max_retries=self.integration_max_retries,
                retry_backoff_seconds=self.integration_retry_backoff_seconds,
                retry_on_statuses=(429, 500, 502, 503, 504),
                client_factory=httpx.AsyncClient,
            )
                
            if response.status_code == 200:
                data = response.json()
                
                if data.get("result_count", 0) > 0:
                    provider = data["results"][0]
                    
                    return {
                        "verified": True,
                        "npi": npi,
                        "provider_name": f"{provider.get('basic', {}).get('first_name', '')} {provider.get('basic', {}).get('last_name', '')}",
                        "provider_type": provider.get("enumeration_type", ""),
                        "taxonomy": [t.get("desc") for t in provider.get("taxonomies", [])],
                        "address": provider.get("addresses", [{}])[0] if provider.get("addresses") else {},
                        "verified_at": _utc_iso()
                    }
                
            return {
                "verified": False,
                "npi": npi,
                "error": "NPI not found in registry"
            }
        
        except Exception as e:
            logger.error(f"Error verifying NPI {npi}: {e}")
            return {
                "verified": False,
                "npi": npi,
                "error": str(e)
            }
    
    async def verify_state_license(
        self,
        state_code: str,
        license_number: str,
        provider_name: str,
        dob: str
    ) -> Dict[str, Any]:
        """
        Verify state medical license.
        Uses a configurable integration endpoint when provided.
        Without integration configuration, fail closed to manual review.
        """
        try:
            if not self.state_license_provider_url:
                return {
                    "verified": False,
                    "state": state_code,
                    "license_number": license_number,
                    "error": "state_license_provider_not_configured",
                    "requires_manual_review": True,
                    "source": "manual_policy",
                    "checked_at": _utc_iso(),
                }

            response = await self._request_adapter_with_retry(
                method="GET",
                url=self.state_license_provider_url,
                params={
                    "state": state_code,
                    "license_number": license_number,
                    "name": provider_name,
                    "dob": dob,
                },
            )

            if response.status_code == 200:
                data = response.json()
                status = str(data.get("status", "")).upper()
                verified = bool(data.get("verified", False))
                # If provider doesn't return explicit verified flag, infer from active-ish statuses.
                if not verified and status in {"ACTIVE", "CURRENT", "VALID"}:
                    verified = True

                return {
                    "verified": verified,
                    "state": state_code,
                    "license_number": license_number,
                    "status": status or "UNKNOWN",
                    "issue_date": data.get("issue_date"),
                    "expiration_date": data.get("expiration_date"),
                    "discipline_history": data.get("discipline_history", []),
                    "requires_manual_review": not verified,
                    "source": "state_license_provider",
                    "verified_at": _utc_iso(),
                }

            return {
                "verified": False,
                "state": state_code,
                "license_number": license_number,
                "error": f"state_license_lookup_failed_{response.status_code}",
                "requires_manual_review": True,
                "source": "state_license_provider",
                "checked_at": _utc_iso(),
            }

        except Exception as e:
            logger.error(f"Error verifying state license: {e}")
            return {
                "verified": False,
                "state": state_code,
                "license_number": license_number,
                "error": str(e),
                "requires_manual_review": True,
                "source": "state_license_provider",
                "checked_at": _utc_iso(),
            }
    
    async def check_oig_exclusion(
        self,
        provider_name: str,
        dob: str,
        npi: str
    ) -> Dict[str, Any]:
        """
        Check OIG exclusion list
        """
        try:
            response = await request_with_retry(
                method="GET",
                url=self.oig_api_url,
                params={
                    "name": provider_name,
                    "npi": npi,
                },
                timeout_seconds=self.integration_timeout_seconds,
                max_retries=self.integration_max_retries,
                retry_backoff_seconds=self.integration_retry_backoff_seconds,
                retry_on_statuses=(429, 500, 502, 503, 504),
                client_factory=httpx.AsyncClient,
            )
                
            if response.status_code == 200:
                data = response.json()
                
                return {
                    "verified": True,
                    "excluded": data.get("excluded", False),
                    "exclusion_date": data.get("exclusion_date"),
                    "exclusion_type": data.get("exclusion_type"),
                    "checked_at": _utc_iso()
                }
            
            return {
                "verified": False,
                "excluded": None,
                "error": f"OIG lookup failed with status {response.status_code}",
                "checked_at": _utc_iso()
            }
        
        except Exception as e:
            logger.error(f"Error checking OIG exclusion: {e}")
            return {
                "verified": False,
                "excluded": None,
                "error": str(e)
            }
    
    async def check_sam_exclusion(
        self,
        provider_name: str,
        dob: str
    ) -> Dict[str, Any]:
        """
        Check SAM exclusion list
        """
        try:
            response = await request_with_retry(
                method="GET",
                url=self.sam_api_url,
                params={
                    "name": provider_name,
                },
                timeout_seconds=self.integration_timeout_seconds,
                max_retries=self.integration_max_retries,
                retry_backoff_seconds=self.integration_retry_backoff_seconds,
                retry_on_statuses=(429, 500, 502, 503, 504),
                client_factory=httpx.AsyncClient,
            )
                
            if response.status_code == 200:
                data = response.json()
                
                return {
                    "verified": True,
                    "excluded": data.get("excluded", False),
                    "exclusion_date": data.get("exclusion_date"),
                    "checked_at": _utc_iso()
                }
            
            return {
                "verified": False,
                "excluded": None,
                "error": f"SAM lookup failed with status {response.status_code}",
                "checked_at": _utc_iso()
            }
        
        except Exception as e:
            logger.error(f"Error checking SAM exclusion: {e}")
            return {
                "verified": False,
                "excluded": None,
                "error": str(e)
            }
    
    async def run_background_check(
        self,
        first_name: str,
        last_name: str,
        dob: str,
        ssn: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run background check via configurable integration.
        Without integration configuration, fail closed to manual review.
        """
        if not self.background_check_provider_url:
            return {
                "verified": False,
                "clear": False,
                "findings": [],
                "recommendation": "requires_review",
                "checked_at": _utc_iso(),
                "source": "manual_policy",
                "error": "background_check_provider_not_configured",
            }

        try:
            response = await self._request_adapter_with_retry(
                method="POST",
                url=self.background_check_provider_url,
                json_body={
                    "first_name": first_name,
                    "last_name": last_name,
                    "dob": dob,
                    "ssn": ssn,
                },
            )
            if response.status_code == 200:
                data = response.json()
                clear = bool(data.get("clear", False))
                return {
                    "verified": bool(data.get("verified", True)),
                    "clear": clear,
                    "findings": data.get("findings", []),
                    "recommendation": data.get("recommendation", "clear" if clear else "requires_review"),
                    "checked_at": _utc_iso(),
                    "source": "background_check_provider",
                }

            return {
                "verified": False,
                "clear": False,
                "findings": [],
                "recommendation": "requires_review",
                "checked_at": _utc_iso(),
                "source": "background_check_provider",
                "error": f"background_check_lookup_failed_{response.status_code}",
            }
        except Exception as e:
            logger.error(f"Error running background check: {e}")
            return {
                "verified": False,
                "clear": False,
                "findings": [],
                "recommendation": "requires_review",
                "checked_at": _utc_iso(),
                "source": "background_check_provider",
                "error": str(e),
            }

        # Defensive fallback; should be unreachable.
        return {
            "verified": False,
            "clear": False,
            "findings": [],
            "recommendation": "requires_review",
            "checked_at": _utc_iso(),
            "source": "manual_policy",
        }
    
    def calculate_credentialing_score(self, results: Dict[str, Any]) -> int:
        """
        Calculate overall credentialing score (0-100)
        """
        score = 0
        
        # NPI verification (20 points)
        if results.get("npi_verification", {}).get("verified"):
            score += 20
        
        # State license verification (30 points)
        state_license = results.get("state_license_verification", {})
        if state_license.get("verified") and str(state_license.get("status", "")).upper() in {"ACTIVE", "CURRENT", "VALID"}:
            score += 30
        
        # Background check (20 points)
        if results.get("background_check", {}).get("verified") and results.get("background_check", {}).get("clear"):
            score += 20
        
        # OIG check (15 points)
        if results.get("oig_check", {}).get("verified") and not results.get("oig_check", {}).get("excluded"):
            score += 15
        
        # SAM check (10 points)
        if results.get("sam_check", {}).get("verified") and not results.get("sam_check", {}).get("excluded"):
            score += 10
        
        # Specialty board (5 points) - optional
        if results.get("specialty_board_verification", {}).get("verified"):
            score += 5
        
        return score
    
    def determine_status(self, score: int) -> str:
        """
        Determine credentialing status based on score
        """
        if score >= 80:
            return "passed"
        elif score >= 60:
            return "requires_review"
        else:
            return "failed"


credentialing_service = CredentialingService()

