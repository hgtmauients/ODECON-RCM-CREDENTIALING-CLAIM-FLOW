"""
ClaimFlow - Integration feature flags.
Controls which optional integrations are enabled at runtime.
All integrations are DISABLED by default per ClaimFlow's zero-integration-by-default policy.
"""

import os

INTEGRATIONS = {
    "emr_connector": os.getenv("CLAIMFLOW_ENABLE_EMR_CONNECTOR", "false").lower() == "true",
    "clinical_notes_nlp": os.getenv("CLAIMFLOW_ENABLE_CLINICAL_NOTES", "false").lower() == "true",
}


def is_enabled(integration_name: str) -> bool:
    return INTEGRATIONS.get(integration_name, False)
