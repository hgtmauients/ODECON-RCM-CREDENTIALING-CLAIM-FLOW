"""
ClaimFlow - Seed CARC/RARC reference codes.
Run: python -m scripts.seed_carc_rarc
Populates the carc_codes and rarc_codes tables with standard CMS codes.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import async_session_factory
from models.denials import CARCCode, RARCCode
from sqlalchemy import select

# Most common CARC codes used in healthcare RCM
CARC_CODES = [
    ("1", "Deductible amount", "patient_responsibility", "deductible", True),
    ("2", "Coinsurance amount", "patient_responsibility", "coinsurance", True),
    ("3", "Copay amount", "patient_responsibility", "copay", True),
    ("4", "The procedure code is inconsistent with the modifier used", "coding_error", "modifier", True),
    ("5", "The procedure code/bill type is inconsistent with the place of service", "coding_error", "pos", True),
    ("6", "The procedure/revenue code is inconsistent with the patient's age", "coding_error", "age", True),
    ("9", "The diagnosis is inconsistent with the patient's age", "coding_error", "diagnosis", True),
    ("11", "The diagnosis is inconsistent with the procedure", "coding_error", "diagnosis", True),
    ("16", "Claim/service lacks information or has submission/billing error(s)", "missing_info", "billing_error", True),
    ("18", "Exact duplicate claim/service", "duplicate", "duplicate", False),
    ("22", "This care may be covered by another payer per coordination of benefits", "cob", "other_payer", True),
    ("23", "The impact of prior payer(s) adjudication including payments and/or adjustments", "cob", "prior_payer", True),
    ("27", "Expenses incurred after coverage terminated", "eligibility", "terminated", False),
    ("29", "The time limit for filing has expired", "timely_filing", "late", False),
    ("31", "Patient cannot be identified as our insured", "eligibility", "not_covered", False),
    ("32", "Our records indicate that this dependent is not an eligible dependent", "eligibility", "dependent", False),
    ("33", "Insured has no dependent coverage", "eligibility", "no_dependent", False),
    ("35", "Lifetime benefit maximum has been reached", "benefit_limit", "lifetime_max", False),
    ("39", "Services denied at the time authorization/pre-certification was requested", "authorization", "denied_auth", True),
    ("45", "Charge exceeds fee schedule/maximum allowable", "contractual", "fee_schedule", True),
    ("49", "This is a non-covered service because it is a routine/preventive exam", "non_covered", "routine", False),
    ("50", "These are non-covered services because this is not deemed a medical necessity", "medical_necessity", "not_necessary", True),
    ("55", "Procedure/treatment/drug is deemed experimental/investigational", "non_covered", "experimental", True),
    ("58", "Treatment was deemed by the payer to have been rendered in an inappropriate setting", "medical_necessity", "setting", True),
    ("59", "Processed based on multiple or concurrent procedure rules", "contractual", "multiple_proc", True),
    ("96", "Non-covered charge(s)", "non_covered", "general", False),
    ("97", "The benefit for this service is included in the payment/allowance for another service", "bundling", "included", True),
    ("109", "Claim/service not covered by this payer/contractor", "non_covered", "not_covered", False),
    ("119", "Benefit maximum for this time period or occurrence has been reached", "benefit_limit", "period_max", False),
    ("140", "Patient/Insured health identification number and name do not match", "eligibility", "id_mismatch", True),
    ("167", "This (these) diagnosis(es) is (are) not covered", "non_covered", "diagnosis", False),
    ("170", "Payment is denied when performed/billed by this type of provider", "non_covered", "provider_type", False),
    ("197", "Precertification/authorization/notification absent", "authorization", "no_auth", True),
    ("204", "This service/equipment/drug is not covered under the patient's current benefit plan", "non_covered", "not_in_plan", False),
    ("219", "Based on regulatory requirements, this service was paid at a reduced rate", "contractual", "regulatory", True),
    ("226", "Information requested from the Billing/Rendering Provider was not provided", "missing_info", "provider_info", True),
    ("227", "Information requested from the patient/insured/responsible party was not provided", "missing_info", "patient_info", True),
    ("236", "This procedure or procedure/modifier combination is not compatible with another procedure", "coding_error", "incompatible", True),
    ("242", "Services not provided by network/primary care providers", "network", "out_of_network", True),
    ("252", "An attachment/other documentation is required to adjudicate this claim/service", "missing_info", "attachment", True),
    ("256", "Service not payable per managed care contract", "contractual", "contract", False),
]

# Most common RARC codes
RARC_CODES = [
    ("M1", "X-ray not taken within the time frame", "documentation"),
    ("M15", "Separately billed services/tests have been bundled", "bundling"),
    ("M20", "Missing/incomplete/invalid HCPCS", "coding"),
    ("M51", "Missing/incomplete/invalid procedure code(s)", "coding"),
    ("M76", "Missing/incomplete/invalid diagnosis or condition", "coding"),
    ("M77", "Missing/incomplete/invalid place of service", "coding"),
    ("M80", "Not covered when performed during the same session/date as a previously processed service", "bundling"),
    ("MA01", "Alert: If you do not agree with what we approved for these services, you may appeal", "informational"),
    ("MA04", "Secondary payment cannot be considered without the identity of or payment information from the primary payer", "cob"),
    ("MA07", "The claim information has also been forwarded to Medicaid for review", "informational"),
    ("MA18", "The claim information is also being forwarded to the patient's supplemental insurer", "cob"),
    ("MA130", "Your claim contains incomplete and/or invalid information, and no appeal rights are afforded", "missing_info"),
    ("N1", "Alert: You may appeal this decision", "informational"),
    ("N30", "Patient ineligible for this service", "eligibility"),
    ("N95", "This provider type/provider specialty may not bill this service", "provider"),
    ("N115", "This decision was based on a National Coverage Determination (NCD)", "medical_policy"),
    ("N386", "This decision was based on a Local Coverage Determination (LCD)", "medical_policy"),
    ("N432", "Alert: Claim was processed in accordance with the requirements of a demonstration project", "informational"),
    ("N522", "Duplicate of a claim processed, or to be processed, as a crossover claim", "duplicate"),
    ("N527", "We processed this claim as an adjusted claim", "adjustment"),
    ("N657", "This should be billed with the appropriate code for the type of service", "coding"),
]


async def seed():
    async with async_session_factory() as db:
        # Check if already seeded
        existing = await db.execute(select(CARCCode).limit(1))
        if existing.scalar_one_or_none():
            print("CARC codes already seeded, skipping...")
        else:
            for code, desc, category, subcategory, appealable in CARC_CODES:
                entry = CARCCode(
                    code=code,
                    description=desc,
                    category=category,
                    subcategory=subcategory,
                    is_appealable=appealable,
                )
                db.add(entry)
            await db.commit()
            print(f"Seeded {len(CARC_CODES)} CARC codes")

        existing_rarc = await db.execute(select(RARCCode).limit(1))
        if existing_rarc.scalar_one_or_none():
            print("RARC codes already seeded, skipping...")
        else:
            for code, desc, category in RARC_CODES:
                entry = RARCCode(
                    code=code,
                    description=desc,
                    category=category,
                )
                db.add(entry)
            await db.commit()
            print(f"Seeded {len(RARC_CODES)} RARC codes")

        print("Done!")


if __name__ == "__main__":
    asyncio.run(seed())
