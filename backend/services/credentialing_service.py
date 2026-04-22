"""
Automated Provider Credentialing Service
"""
import httpx
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class CredentialingService:
    """Service for automated provider credentialing checks"""
    
    def __init__(self):
        self.npi_api_url = "https://npiregistry.cms.hhs.gov/api/"
        self.oig_api_url = "https://oig.hhs.gov/exclusions/api/search"
        self.sam_api_url = "https://api.sam.gov/api/entity-information/"
    
    async def verify_npi(self, npi: str) -> Dict[str, Any]:
        """
        Verify NPI with CMS NPPES Registry
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    self.npi_api_url,
                    params={
                        "number": npi,
                        "version": "2.1"
                    }
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
                            "verified_at": datetime.utcnow().isoformat()
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
        Verify state medical license
        Note: Each state has different API - this is a placeholder
        """
        try:
            # State-specific API endpoints
            state_apis = {
                "CA": "https://www.mbc.ca.gov/licensing-lookup-api",
                "TX": "https://www.tmb.state.tx.us/api/license-verification",
                "NY": "https://www.op.nysed.gov/api/profession",
                "FL": "https://www.flhealthsource.gov/api/license"
            }
            
            api_url = state_apis.get(state_code)
            
            if not api_url:
                return {
                    "verified": False,
                    "state": state_code,
                    "license_number": license_number,
                    "error": f"State API not configured for {state_code}"
                }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    api_url,
                    params={
                        "license_number": license_number,
                        "name": provider_name,
                        "dob": dob
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    return {
                        "verified": True,
                        "state": state_code,
                        "license_number": license_number,
                        "status": data.get("status", "unknown"),
                        "issue_date": data.get("issue_date"),
                        "expiration_date": data.get("expiration_date"),
                        "discipline_history": data.get("discipline_history", []),
                        "verified_at": datetime.utcnow().isoformat()
                    }
            
            return {
                "verified": False,
                "state": state_code,
                "license_number": license_number,
                "error": "License not found"
            }
        
        except Exception as e:
            logger.error(f"Error verifying state license: {e}")
            return {
                "verified": False,
                "state": state_code,
                "license_number": license_number,
                "error": str(e)
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
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    self.oig_api_url,
                    params={
                        "name": provider_name,
                        "npi": npi
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    return {
                        "excluded": data.get("excluded", False),
                        "exclusion_date": data.get("exclusion_date"),
                        "exclusion_type": data.get("exclusion_type"),
                        "checked_at": datetime.utcnow().isoformat()
                    }
            
            return {
                "excluded": False,
                "checked_at": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error checking OIG exclusion: {e}")
            return {
                "excluded": False,
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
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    self.sam_api_url,
                    params={
                        "name": provider_name
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    return {
                        "excluded": data.get("excluded", False),
                        "exclusion_date": data.get("exclusion_date"),
                        "checked_at": datetime.utcnow().isoformat()
                    }
            
            return {
                "excluded": False,
                "checked_at": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error checking SAM exclusion: {e}")
            return {
                "excluded": False,
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
        Run background check (placeholder - requires integration with background check service)
        """
        # This would integrate with services like VerifiedFirst, Certn, etc.
        # For now, return a placeholder
        return {
            "clear": True,
            "findings": [],
            "recommendation": "approve",
            "checked_at": datetime.utcnow().isoformat(),
            "note": "Background check service not yet integrated"
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
        if state_license.get("verified") and state_license.get("status") == "active":
            score += 30
        
        # Background check (20 points)
        if results.get("background_check", {}).get("clear"):
            score += 20
        
        # OIG check (15 points)
        if not results.get("oig_check", {}).get("excluded"):
            score += 15
        
        # SAM check (10 points)
        if not results.get("sam_check", {}).get("excluded"):
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

