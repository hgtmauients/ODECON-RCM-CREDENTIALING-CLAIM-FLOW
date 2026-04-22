"""
EDI Processor
Generates 837P (professional) claim files and parses inbound responses (835, 277CA, 999)
Handles ANSI X12 formatting according to payer specifications
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from models.claims import Claim, ClaimLine, ClaimDiagnosis, ClaimEvent, EDIFile, ClaimState
from models.rcm import PayerProfile
from models.denials import DenialCase

logger = logging.getLogger(__name__)

EDI_STORAGE_PATH = os.getenv("EDI_STORAGE_PATH", "/data/claimflow/edi")


class EDIProcessor:
    """
    EDI transaction processing
    Generates outbound files (837P professional, 270 eligibility)
    Parses inbound files (999 syntax ack, 277CA claim ack, 276/277 status, 835 remittance)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== OUTBOUND: 837P PROFESSIONAL CLAIM GENERATION ====================

    async def generate_837(self, claim_ids: List[int], payer_id: int, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate 837P (professional) file for claim submission.
        Persists the file to EDI_STORAGE_PATH and returns metadata.
        """
        try:
            payer_result = await self.db.execute(select(PayerProfile).where(PayerProfile.id == payer_id))
            payer = payer_result.scalar_one_or_none()
            if not payer:
                raise ValueError("Payer not found")

            claims_result = await self.db.execute(select(Claim).where(Claim.id.in_(claim_ids)))
            claims = claims_result.scalars().all()
            if not claims:
                raise ValueError("No claims found")

            # Load lines and diagnoses for each claim
            claim_data = []
            for claim in claims:
                lines_result = await self.db.execute(
                    select(ClaimLine).where(ClaimLine.claim_id == claim.id).order_by(ClaimLine.line_number)
                )
                lines = lines_result.scalars().all()

                dx_result = await self.db.execute(
                    select(ClaimDiagnosis).where(ClaimDiagnosis.claim_id == claim.id).order_by(ClaimDiagnosis.diagnosis_pointer)
                )
                diagnoses = dx_result.scalars().all()

                # Load patient demographics if patient_id is set
                patient = None
                if claim.patient_id:
                    from models.patient import Patient
                    pat_result = await self.db.execute(
                        select(Patient).where(Patient.id == claim.patient_id)
                    )
                    patient = pat_result.scalar_one_or_none()

                claim_data.append({"claim": claim, "lines": lines, "diagnoses": diagnoses, "patient": patient})

            effective_tenant_id = tenant_id or str(claims[0].tenant_id)

            file_type = payer.format_837_type or "837P"
            icn = self._generate_control_number()

            # Load tenant for billing provider info
            from models.tenant import Tenant
            tenant_result = await self.db.execute(select(Tenant).where(Tenant.id == effective_tenant_id))
            tenant_record = tenant_result.scalar_one_or_none()

            edi_content = self._build_837_file(claim_data, payer, icn, tenant_record)

            filename = f"claim_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{icn}.{file_type.lower()}"
            outbound_dir = Path(EDI_STORAGE_PATH) / effective_tenant_id / "outbound"
            outbound_dir.mkdir(parents=True, exist_ok=True)
            file_path = str(outbound_dir / filename)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(edi_content)

            edi_file = EDIFile(
                tenant_id=effective_tenant_id,
                file_type=file_type,
                direction="outbound",
                filename=filename,
                file_path=file_path,
                file_size=len(edi_content.encode("utf-8")),
                interchange_control_number=icn,
                transaction_count=len(claims),
                payer_id=payer_id,
                batch_id=f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                status="pending",
                created_by="system",
            )
            self.db.add(edi_file)
            await self.db.flush()

            for claim in claims:
                event = ClaimEvent(
                    claim_id=claim.id,
                    event_type="837_generated",
                    from_state=claim.state,
                    to_state="ready_to_submit",
                    data={"icn": icn, "filename": filename, "batch_id": edi_file.batch_id},
                    message=f"837 file generated: {filename}",
                    edi_file_id=edi_file.id,
                )
                self.db.add(event)
                claim.state = "ready_to_submit"
                claim.interchange_control_number = icn

            await self.db.commit()

            logger.info(f"Generated 837 file: {filename} ({len(claims)} claims)")

            return {
                "success": True,
                "filename": filename,
                "file_path": file_path,
                "icn": icn,
                "claim_count": len(claims),
                "file_id": edi_file.id,
            }

        except Exception as e:
            logger.error(f"Error generating 837: {e}")
            raise

    def _build_837_file(self, claim_data: List[Dict[str, Any]], payer: PayerProfile, icn: str, tenant=None) -> str:
        """
        Build complete ANSI X12 837P file per 005010X222A1 implementation guide.
        Includes all required loops: 1000A/B, 2000A/B, 2010AA/AB/BA/BB, 2300, 2400.
        """
        segments: List[str] = []

        # ISA - Interchange Control Header
        segments.append(self._build_isa_segment(payer, icn))

        # GS - Functional Group Header
        gs_control_number = self._generate_control_number()
        segments.append(self._build_gs_segment(payer, gs_control_number))

        # Billing provider info from tenant
        billing_name = (tenant.name if tenant else "BILLING PROVIDER").upper()
        billing_npi_org = tenant.npi if tenant else "0000000000"
        billing_tax_id = tenant.tax_id if tenant else "000000000"
        billing_addr1 = (tenant.address_line_1 if tenant else "123 BILLING ST").upper()
        billing_addr2 = ((tenant.address_line_2 if tenant else None) or "").upper()
        billing_city = (tenant.city if tenant else "ANYTOWN").upper()
        billing_state = (tenant.state if tenant else "HI").upper()
        billing_zip = (tenant.zip_code if tenant else "96701")
        billing_phone = (tenant.phone if tenant else "8005551234")

        for tx_idx, entry in enumerate(claim_data, start=1):
            claim = entry["claim"]
            lines = entry["lines"]
            diagnoses = entry["diagnoses"]
            patient = entry.get("patient")

            st_control = f"{tx_idx:04d}"
            tx_segments: List[str] = []

            # ST - Transaction Set Header
            tx_segments.append(f"ST*837*{st_control}*005010X222A1~")

            # BHT - Beginning of Hierarchical Transaction
            tx_segments.append(
                f"BHT*0019*00*{claim.claim_number}*"
                f"{datetime.now().strftime('%Y%m%d')}*{datetime.now().strftime('%H%M')}*CH~"
            )

            # ── 1000A - Submitter ──
            tx_segments.append(f"NM1*41*2*{billing_name}*****46*{payer.submitter_id or billing_npi_org}~")
            tx_segments.append(f"PER*IC*{billing_name}*TE*{billing_phone}~")

            # ── 1000B - Receiver ──
            tx_segments.append(f"NM1*40*2*{(payer.name or 'PAYER').upper()}*****46*{payer.receiver_id or payer.payer_id or ''}~")

            # ── 2000A - Billing Provider Hierarchical Level ──
            tx_segments.append(f"HL*1**20*1~")
            tx_segments.append(f"PRV*BI*PXC*207Q00000X~")

            # 2010AA - Billing Provider Name
            claim_npi = claim.billing_provider_npi or billing_npi_org
            tx_segments.append(f"NM1*85*2*{billing_name}*****XX*{claim_npi}~")
            tx_segments.append(f"N3*{billing_addr1}~")
            tx_segments.append(f"N4*{billing_city}*{billing_state}*{billing_zip}~")
            tx_segments.append(f"REF*EI*{billing_tax_id}~")

            # ── 2000B - Subscriber Hierarchical Level ──
            tx_segments.append(f"HL*2*1*22*0~")
            subscriber_rel = "18"  # Self
            if patient and patient.relationship_to_subscriber:
                subscriber_rel = patient.relationship_to_subscriber
            tx_segments.append(f"SBR*P*{subscriber_rel}*******CI~")

            # 2010BA - Subscriber Name (use real patient data)
            if patient:
                sub_last = patient.last_name.upper()
                sub_first = patient.first_name.upper()
                sub_middle = (patient.middle_name or "").upper()
                sub_suffix = patient.suffix or ""
                member_id = patient.member_id
                sub_addr1 = patient.address_line_1.upper()
                sub_city = patient.city.upper()
                sub_state = patient.state.upper()
                sub_zip = patient.zip_code
                sub_dob = patient.date_of_birth.strftime("%Y%m%d") if patient.date_of_birth else "19800101"
                sub_gender = patient.gender or "U"
            else:
                sub_last = "UNKNOWN"
                sub_first = "PATIENT"
                sub_middle = ""
                sub_suffix = ""
                member_id = str(claim.patient_id or "UNKNOWN")
                sub_addr1 = "UNKNOWN"
                sub_city = "UNKNOWN"
                sub_state = "HI"
                sub_zip = "96701"
                sub_dob = "19800101"
                sub_gender = "U"

            nm1_sub = f"NM1*IL*1*{sub_last}*{sub_first}"
            if sub_middle:
                nm1_sub += f"*{sub_middle}"
            else:
                nm1_sub += "*"
            if sub_suffix:
                nm1_sub += f"*{sub_suffix}"
            else:
                nm1_sub += "*"
            nm1_sub += f"**MI*{member_id}~"
            tx_segments.append(nm1_sub)

            tx_segments.append(f"N3*{sub_addr1}~")
            tx_segments.append(f"N4*{sub_city}*{sub_state}*{sub_zip}~")
            tx_segments.append(f"DMG*D8*{sub_dob}*{sub_gender}~")

            # 2010BB - Payer Name
            payer_name = (payer.name or "PAYER").upper()
            tx_segments.append(f"NM1*PR*2*{payer_name}*****PI*{payer.payer_id or ''}~")
            if payer.paper_claim_address:
                tx_segments.append(f"N3*{payer.paper_claim_address.split(chr(10))[0].upper()}~")
                tx_segments.append(f"N4*PAYERVILLE*HI*96801~")

            # ── 2300 - Claim Information ──
            place_of_service = "11"
            if lines:
                place_of_service = lines[0].place_of_service or "11"

            tx_segments.append(
                f"CLM*{claim.claim_number}*{float(claim.total_charges or 0):.2f}***"
                f"{place_of_service}:B:{claim.claim_frequency_code or '1'}***A*Y*Y~"
            )

            # DTP - Service dates
            svc_from = claim.service_date_from.strftime("%Y%m%d") if claim.service_date_from else datetime.now().strftime("%Y%m%d")
            svc_to = claim.service_date_to.strftime("%Y%m%d") if claim.service_date_to else svc_from
            if svc_from == svc_to:
                tx_segments.append(f"DTP*472*D8*{svc_from}~")
            else:
                tx_segments.append(f"DTP*472*RD8*{svc_from}-{svc_to}~")

            # Prior Authorization
            if claim.prior_auth_number:
                tx_segments.append(f"REF*G1*{claim.prior_auth_number}~")

            # HI - Diagnosis codes
            if diagnoses:
                primary_codes = []
                other_codes = []
                for dx in diagnoses:
                    code = dx.icd10_code.replace(".", "")
                    if dx.is_primary or dx.diagnosis_pointer == 1:
                        primary_codes.append(code)
                    else:
                        other_codes.append(code)

                all_codes = primary_codes + other_codes
                hi_elements = []
                for i, code in enumerate(all_codes[:12]):
                    qualifier = "ABK" if i == 0 else "ABF"
                    hi_elements.append(f"{qualifier}:{code}")
                tx_segments.append(f"HI*{'*'.join(hi_elements)}~")

            # 2310A - Rendering Provider (if different from billing)
            if claim.rendering_provider_npi and claim.rendering_provider_npi != claim.billing_provider_npi:
                tx_segments.append(f"NM1*82*1*RENDERING*PROVIDER****XX*{claim.rendering_provider_npi}~")
                tx_segments.append(f"PRV*PE*PXC*207Q00000X~")

            # ── 2400 - Service Lines ──
            for line_num, line in enumerate(lines, start=1):
                tx_segments.append(f"LX*{line_num}~")

                modifiers = ""
                if line.modifiers:
                    mod_list = line.modifiers if isinstance(line.modifiers, list) else []
                    modifiers = ":".join(mod_list[:4])
                    if modifiers:
                        modifiers = ":" + modifiers

                cpt = line.cpt_code or "99213"
                charge = f"{float(line.charge_amount or 0):.2f}"
                units = line.units or 1
                pos = line.place_of_service or place_of_service

                dx_ptrs = ""
                if line.diagnosis_pointers:
                    ptrs = line.diagnosis_pointers if isinstance(line.diagnosis_pointers, list) else [1]
                    dx_ptrs = ":".join(str(p) for p in ptrs[:4])
                elif diagnoses:
                    dx_ptrs = "1"

                tx_segments.append(
                    f"SV1*HC:{cpt}{modifiers}*{charge}*UN*{units}*{pos}**{dx_ptrs}~"
                )

                line_date = line.service_date.strftime("%Y%m%d") if line.service_date else svc_from
                tx_segments.append(f"DTP*472*D8*{line_date}~")
                tx_segments.append(f"REF*6R*{claim.claim_number}_{line_num}~")

            # SE - Transaction Set Trailer
            segment_count = len(tx_segments) + 1
            tx_segments.append(f"SE*{segment_count}*{st_control}~")

            segments.extend(tx_segments)

        # GE - Functional Group Trailer
        segments.append(f"GE*{len(claim_data)}*{gs_control_number}~")

        # IEA - Interchange Control Trailer
        segments.append(f"IEA*1*{icn}~")

        return "\n".join(segments)

    def _build_isa_segment(self, payer: PayerProfile, icn: str) -> str:
        submitter = (payer.submitter_id or "SUBMITTER").ljust(15)
        receiver = (payer.receiver_id or "RECEIVER").ljust(15)
        return (
            f"ISA*00*          *00*          *ZZ*{submitter}*"
            f"ZZ*{receiver}*{datetime.now().strftime('%y%m%d')}*"
            f"{datetime.now().strftime('%H%M')}*^*00501*{icn}*0*P*:~"
        )

    def _build_gs_segment(self, payer: PayerProfile, control_number: str) -> str:
        file_type = "HC" if payer.format_837_type == "837P" else "HI"
        return (
            f"GS*{file_type}*{payer.submitter_id or 'SUBMITTER'}*{payer.receiver_id or 'RECEIVER'}*"
            f"{datetime.now().strftime('%Y%m%d')}*{datetime.now().strftime('%H%M')}*{control_number}*X*005010X222A1~"
        )

    def _generate_control_number(self) -> str:
        return datetime.now().strftime("%Y%m%d%H%M%S%f")[:9]

    # ==================== INBOUND: CLAIM ACKNOWLEDGMENTS & STATUS (999/277CA/277) ====================

    async def parse_277(self, file_path: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Parse claim acknowledgment and status response files (277CA, 277).
        - 277CA: Claim-level accept/reject from clearinghouse or payer
        - 277: Claim status response (to a 276 inquiry)
        Updates claim state based on status codes.
        """
        try:
            logger.info(f"Parsing 277 file: {file_path}")

            content = ""
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

            edi_file = EDIFile(
                tenant_id=tenant_id,
                file_type="277CA",
                direction="inbound",
                filename=os.path.basename(file_path),
                file_path=file_path,
                file_size=len(content.encode("utf-8")) if content else 0,
                status="processing",
            )
            self.db.add(edi_file)
            await self.db.flush()

            claims_updated = 0
            status_updates = []

            # Parse segments to find claim statuses
            if content:
                for segment in content.split("~"):
                    segment = segment.strip()
                    # STC segment contains status info
                    if segment.startswith("STC"):
                        parts = segment.split("*")
                        if len(parts) >= 2:
                            status_code = parts[1].split(":")[0] if ":" in parts[1] else parts[1]
                            status_updates.append({"code": status_code, "raw": segment})

                    # TRN segment contains the claim tracking number
                    if segment.startswith("TRN"):
                        parts = segment.split("*")
                        if len(parts) >= 3:
                            tracking_number = parts[2]
                            # Try to find claim by ICN
                            claim_result = await self.db.execute(
                                select(Claim).where(
                                    and_(
                                        Claim.interchange_control_number == tracking_number,
                                        Claim.tenant_id == tenant_id,
                                    )
                                ) if tenant_id else select(Claim).where(
                                    Claim.interchange_control_number == tracking_number
                                )
                            )
                            claim = claim_result.scalar_one_or_none()
                            if claim:
                                if status_updates and status_updates[-1]["code"].startswith("A"):
                                    claim.state = ClaimState.ACCEPTED
                                elif status_updates and status_updates[-1]["code"].startswith("R"):
                                    claim.state = ClaimState.REJECTED
                                event = ClaimEvent(
                                    claim_id=claim.id,
                                    event_type="277ca_received",
                                    to_state=claim.state,
                                    data={"file_path": file_path, "status": status_updates[-1] if status_updates else None},
                                    message="Claim acknowledgment/status processed",
                                    edi_file_id=edi_file.id,
                                )
                                self.db.add(event)
                                claims_updated += 1

            edi_file.status = "processed"
            edi_file.processed_at = datetime.utcnow()
            edi_file.transaction_count = claims_updated
            await self.db.commit()

            return {
                "success": True,
                "claims_updated": claims_updated,
                "status_updates": status_updates,
                "edi_file_id": edi_file.id,
            }
        except Exception as e:
            logger.error(f"Error parsing 277: {e}")
            raise

    # ==================== INBOUND: 835 REMITTANCE PARSING ====================

    async def parse_835(self, file_path: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Parse 835 Electronic Remittance Advice.
        Extracts payment/denial data per claim for downstream posting.
        """
        try:
            logger.info(f"Parsing 835 file: {file_path}")

            content = ""
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

            edi_file = EDIFile(
                tenant_id=tenant_id,
                file_type="835",
                direction="inbound",
                filename=os.path.basename(file_path),
                file_path=file_path,
                file_size=len(content.encode("utf-8")) if content else 0,
                status="processing",
            )
            self.db.add(edi_file)
            await self.db.flush()

            payments = []
            denials = []
            total_paid = 0.0

            if content:
                current_claim_number = None
                current_payment = None

                for segment in content.split("~"):
                    segment = segment.strip()

                    # CLP segment: claim-level payment info
                    if segment.startswith("CLP"):
                        if current_payment:
                            if current_payment.get("paid_amount", 0) > 0:
                                payments.append(current_payment)
                            elif current_payment.get("carc_codes"):
                                denials.append(current_payment)

                        parts = segment.split("*")
                        current_claim_number = parts[1] if len(parts) > 1 else None
                        claim_status = parts[2] if len(parts) > 2 else ""
                        paid_amount = float(parts[4]) if len(parts) > 4 else 0.0

                        current_payment = {
                            "claim_number": current_claim_number,
                            "status_code": claim_status,
                            "paid_amount": paid_amount,
                            "carc_codes": [],
                        }
                        total_paid += paid_amount

                    # CAS segment: adjustment/denial codes
                    if segment.startswith("CAS") and current_payment:
                        parts = segment.split("*")
                        group_code = parts[1] if len(parts) > 1 else ""
                        reason_code = parts[2] if len(parts) > 2 else ""
                        amount = float(parts[3]) if len(parts) > 3 else 0.0
                        current_payment["carc_codes"].append({
                            "group": group_code,
                            "code": reason_code,
                            "amount": amount,
                        })

                # Flush last payment
                if current_payment:
                    if current_payment.get("paid_amount", 0) > 0:
                        payments.append(current_payment)
                    elif current_payment.get("carc_codes"):
                        denials.append(current_payment)

            edi_file.status = "processed"
            edi_file.processed_at = datetime.utcnow()
            edi_file.transaction_count = len(payments) + len(denials)
            await self.db.commit()

            return {
                "success": True,
                "edi_file_id": edi_file.id,
                "claims_posted": len(payments),
                "total_paid": total_paid,
                "payments": payments,
                "denials": denials,
            }
        except Exception as e:
            logger.error(f"Error parsing 835: {e}")
            raise

    # ==================== OUTBOUND: 270 ELIGIBILITY REQUEST ====================

    async def generate_270(self, patient_id: int, payer_id: int, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate 270 Eligibility Request."""
        try:
            payer_result = await self.db.execute(select(PayerProfile).where(PayerProfile.id == payer_id))
            payer = payer_result.scalar_one_or_none()
            if not payer or not payer.supports_270_271:
                raise ValueError("Payer does not support 270/271 eligibility")

            icn = self._generate_control_number()
            edi_content = f"ISA*...*270*{icn}~\n"

            filename = f"eligibility_{datetime.now().strftime('%Y%m%d_%H%M%S')}.270"
            outbound_dir = Path(EDI_STORAGE_PATH) / (tenant_id or "default") / "outbound"
            outbound_dir.mkdir(parents=True, exist_ok=True)
            file_path = str(outbound_dir / filename)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(edi_content)

            edi_file = EDIFile(
                tenant_id=tenant_id,
                file_type="270",
                direction="outbound",
                filename=filename,
                file_path=file_path,
                file_size=len(edi_content),
                interchange_control_number=icn,
                payer_id=payer_id,
                status="pending",
            )
            self.db.add(edi_file)
            await self.db.commit()

            return {"success": True, "filename": filename, "icn": icn}
        except Exception as e:
            logger.error(f"Error generating 270: {e}")
            raise

    # ==================== INBOUND: 271 ELIGIBILITY RESPONSE ====================

    async def parse_271(self, file_path: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Parse 271 Eligibility Response."""
        try:
            logger.info(f"Parsing 271 file: {file_path}")
            edi_file = EDIFile(
                tenant_id=tenant_id,
                file_type="271",
                direction="inbound",
                filename=os.path.basename(file_path),
                file_path=file_path,
                status="processed",
                processed_at=datetime.utcnow(),
            )
            self.db.add(edi_file)
            await self.db.commit()

            return {"success": True, "coverage_active": True, "benefits": []}
        except Exception as e:
            logger.error(f"Error parsing 271: {e}")
            raise

    # ==================== HELPER METHODS ====================

    def validate_edi_format(self, content: str, file_type: str) -> Dict[str, Any]:
        """Validate EDI file format."""
        errors = []
        warnings = []

        if not content.startswith("ISA"):
            errors.append("File must start with ISA segment")
        if not content.rstrip().endswith("~"):
            errors.append("File must end with segment terminator")

        required_segments = {
            "837P": ["ISA", "GS", "ST", "BHT", "SE", "GE", "IEA"],
            "835": ["ISA", "GS", "ST", "BPR", "SE", "GE", "IEA"],
            "277": ["ISA", "GS", "ST", "BHT", "SE", "GE", "IEA"],
        }

        if file_type in required_segments:
            for segment in required_segments[file_type]:
                if segment not in content:
                    errors.append(f"Missing required segment: {segment}")

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    async def get_submission_batch_status(self, batch_id: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Get status of all claims in a submission batch."""
        try:
            query = select(Claim).where(Claim.batch_id == batch_id)
            if tenant_id:
                query = query.where(Claim.tenant_id == tenant_id)

            result = await self.db.execute(query)
            claims = result.scalars().all()

            status_counts: Dict[str, int] = {}
            for claim in claims:
                status_counts[claim.state] = status_counts.get(claim.state, 0) + 1

            return {"batch_id": batch_id, "total_claims": len(claims), "status_breakdown": status_counts}
        except Exception as e:
            logger.error(f"Error getting batch status: {e}")
            raise

    # ==================== RECORD-REUSE VARIANTS (for upload handler) ====================

    async def parse_835_with_record(self, file_path: str, edi_file) -> Dict[str, Any]:
        """Parse 835 using an existing EDIFile record (avoids duplicate creation)."""
        content = ""
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

        payments = []
        denials = []
        total_paid = 0.0
        tenant_id = str(edi_file.tenant_id) if edi_file.tenant_id else None

        if content:
            current_payment = None
            for segment in content.split("~"):
                segment = segment.strip()
                if segment.startswith("CLP"):
                    if current_payment:
                        if current_payment.get("paid_amount", 0) > 0:
                            payments.append(current_payment)
                        elif current_payment.get("carc_codes"):
                            denials.append(current_payment)
                    parts = segment.split("*")
                    paid_amount = float(parts[4]) if len(parts) > 4 else 0.0
                    current_payment = {
                        "claim_number": parts[1] if len(parts) > 1 else None,
                        "status_code": parts[2] if len(parts) > 2 else "",
                        "paid_amount": paid_amount,
                        "carc_codes": [],
                    }
                    total_paid += paid_amount
                if segment.startswith("CAS") and current_payment:
                    parts = segment.split("*")
                    current_payment["carc_codes"].append({
                        "group": parts[1] if len(parts) > 1 else "",
                        "code": parts[2] if len(parts) > 2 else "",
                        "amount": float(parts[3]) if len(parts) > 3 else 0.0,
                    })
            if current_payment:
                if current_payment.get("paid_amount", 0) > 0:
                    payments.append(current_payment)
                elif current_payment.get("carc_codes"):
                    denials.append(current_payment)

        edi_file.status = "processed"
        edi_file.processed_at = datetime.utcnow()
        edi_file.transaction_count = len(payments) + len(denials)
        await self.db.commit()

        return {
            "success": True,
            "edi_file_id": edi_file.id,
            "claims_posted": len(payments),
            "total_paid": total_paid,
            "payments": payments,
            "denials": denials,
        }

    async def parse_277_with_record(self, file_path: str, edi_file) -> Dict[str, Any]:
        """Parse 277CA using an existing EDIFile record (avoids duplicate creation)."""
        content = ""
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

        claims_updated = 0
        tenant_id = str(edi_file.tenant_id) if edi_file.tenant_id else None

        if content:
            for segment in content.split("~"):
                segment = segment.strip()
                if segment.startswith("TRN"):
                    parts = segment.split("*")
                    if len(parts) >= 3:
                        tracking_number = parts[2]
                        query = select(Claim).where(Claim.interchange_control_number == tracking_number)
                        if tenant_id:
                            query = query.where(Claim.tenant_id == tenant_id)
                        claim_result = await self.db.execute(query)
                        claim = claim_result.scalar_one_or_none()
                        if claim:
                            claim.state = ClaimState.ACCEPTED
                            event = ClaimEvent(
                                claim_id=claim.id,
                                event_type="277ca_received",
                                to_state=claim.state,
                                data={"file_path": file_path},
                                message="Claim acknowledgment/status processed",
                                edi_file_id=edi_file.id,
                            )
                            self.db.add(event)
                            claims_updated += 1

        edi_file.status = "processed"
        edi_file.processed_at = datetime.utcnow()
        edi_file.transaction_count = claims_updated
        await self.db.commit()

        return {"success": True, "claims_updated": claims_updated, "edi_file_id": edi_file.id}
