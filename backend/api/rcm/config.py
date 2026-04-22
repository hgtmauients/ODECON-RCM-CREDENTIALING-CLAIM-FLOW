"""
ClaimFlow RCM Module Configuration
Environment variables and settings
"""

import os
from typing import Optional


class RCMConfig:
    """Configuration for ClaimFlow RCM processing"""

    # Feature Flags
    FEE_SCHEDULE_ENABLED: bool = os.getenv(
        "FEE_SCHEDULE_ENABLED", "true"
    ).lower() == "true"

    FHIR_MAPPING_ENABLED: bool = os.getenv(
        "FHIR_MAPPING_ENABLED", "false"
    ).lower() == "true"

    # Fee Schedule Defaults
    DEFAULT_COLLECTION_RATE: float = float(os.getenv("DEFAULT_COLLECTION_RATE", "0.80"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    ENABLE_PHI_SAFE_LOGGING: bool = os.getenv(
        "ENABLE_PHI_SAFE_LOGGING", "true"
    ).lower() == "true"

    # Rate Limits
    MAX_BATCH_SIZE: int = int(os.getenv("MAX_BATCH_SIZE", "100"))
    MAX_ENCOUNTERS_PER_REQUEST: int = int(os.getenv("MAX_ENCOUNTERS_PER_REQUEST", "200"))

    # Database
    CLAIM_CREATION_TIMEOUT: int = int(os.getenv("CLAIM_CREATION_TIMEOUT", "30"))

    @classmethod
    def get_config_status(cls) -> dict:
        """Get configuration status for health checks"""
        return {
            "fee_schedule_enabled": cls.FEE_SCHEDULE_ENABLED,
            "fhir_mapping_enabled": cls.FHIR_MAPPING_ENABLED,
            "max_batch_size": cls.MAX_BATCH_SIZE,
        }


config = RCMConfig()
