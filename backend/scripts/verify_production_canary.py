"""
One-command production canary verifier for ClaimFlow.

Runs a synthetic claim lifecycle via the live API:
  health -> payer+connection -> patient -> claim -> validate -> submit -> 277 -> 835

Then performs deterministic cleanup of all canary artifacts and prints a JSON
report with a strict GO/NO-GO verdict.

Usage (inside backend container):
    python -m scripts.verify_production_canary --tenant 00000000-0000-0000-0000-000000000001
"""

import argparse
import asyncio
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import httpx
import jwt
from sqlalchemy import and_, select, text

from core.database import async_session_factory
from models.claims import Claim
from models.user import User


DEFAULT_API_BASE = "http://127.0.0.1:8000/api"


@dataclass
class Resources:
    run_id: str
    payer_ids: List[int] = field(default_factory=list)
    connection_ids: List[int] = field(default_factory=list)
    patient_ids: List[int] = field(default_factory=list)
    claim_ids: List[int] = field(default_factory=list)
    edi_file_ids: List[int] = field(default_factory=list)
    user_ids: List[str] = field(default_factory=list)


def _tenant_token(
    *,
    user_id: str,
    tenant_id: str,
    email: str,
    jwt_audience: str,
    jwt_algorithm: str,
    jwt_secret: str = "",
    jwt_private_key: str = "",
) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "tenant_id": tenant_id,
        "roles": ["super_admin", "admin", "billing", "credentialing"],
        "aud": jwt_audience,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    algo = (jwt_algorithm or "HS256").upper()
    if algo == "RS256":
        if not jwt_private_key:
            raise ValueError("JWT private key is required when jwt_algorithm=RS256")
        return jwt.encode(payload, jwt_private_key, algorithm="RS256")
    if not jwt_secret:
        raise ValueError("JWT secret is required when jwt_algorithm=HS256")
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


async def _ensure_canary_user(*, tenant_id: str, email: str) -> str:
    tenant_uuid = UUID(str(tenant_id))
    normalized_email = email.strip().lower()
    async with async_session_factory() as db:
        result = await db.execute(
            select(User).where(and_(User.tenant_id == tenant_uuid, User.email == normalized_email))
        )
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                id=uuid4(),
                tenant_id=tenant_uuid,
                email=normalized_email,
                full_name="Production Canary User",
                roles=["super_admin", "admin", "billing", "credentialing"],
                is_active=True,
                created_by="verify_production_canary",
            )
            db.add(user)
        else:
            user.roles = ["super_admin", "admin", "billing", "credentialing"]
            user.is_active = True
            if not user.full_name:
                user.full_name = "Production Canary User"
        await db.commit()
        return str(user.id)


async def _api_json(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    token: str,
    tenant_id: str,
    **kwargs: Any,
) -> tuple[int, Dict[str, Any]]:
    resp = await client.request(
        method,
        path,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": tenant_id,
        },
        **kwargs,
    )
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text}
    return resp.status_code, body


async def _upload_edi(
    client: httpx.AsyncClient,
    *,
    token: str,
    tenant_id: str,
    file_name: str,
    file_type: str,
    content: str,
) -> tuple[int, Dict[str, Any]]:
    resp = await client.post(
        "/rcm/edi/upload",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": tenant_id,
        },
        files={"file": (file_name, content.encode("utf-8"), "application/octet-stream")},
        data={"file_type": file_type},
    )
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text}
    return resp.status_code, body


async def _get_claim_icn(claim_id: int) -> str:
    async with async_session_factory() as db:
        result = await db.execute(select(Claim.interchange_control_number).where(Claim.id == claim_id))
        icn = result.scalar_one_or_none()
        return str(icn or "000000999")


async def _cleanup(resources: Resources) -> None:
    async with async_session_factory() as db:
        for claim_id in resources.claim_ids:
            await db.execute(text("DELETE FROM denial_cases WHERE claim_id = :id"), {"id": claim_id})
            await db.execute(text("DELETE FROM claim_events WHERE claim_id = :id"), {"id": claim_id})
            await db.execute(text("DELETE FROM claim_diagnoses WHERE claim_id = :id"), {"id": claim_id})
            await db.execute(text("DELETE FROM claim_lines WHERE claim_id = :id"), {"id": claim_id})
            await db.execute(text("DELETE FROM claim_validations WHERE claim_id = :id"), {"id": claim_id})
            await db.execute(text("DELETE FROM claims WHERE id = :id"), {"id": claim_id})

        for edi_id in resources.edi_file_ids:
            await db.execute(text("DELETE FROM edi_files WHERE id = :id"), {"id": edi_id})

        for patient_id in resources.patient_ids:
            await db.execute(text("DELETE FROM patients WHERE id = :id"), {"id": patient_id})

        for user_id in resources.user_ids:
            await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})

        for connection_id in resources.connection_ids:
            await db.execute(text("DELETE FROM trading_partner_connections WHERE id = :id"), {"id": connection_id})

        for payer_id in resources.payer_ids:
            await db.execute(text("DELETE FROM payer_profile_versions WHERE payer_id = :id"), {"id": payer_id})
            await db.execute(text("DELETE FROM payer_profiles WHERE id = :id"), {"id": payer_id})

        await db.commit()


def _compute_go(report: Dict[str, Any]) -> bool:
    go_conditions = [
        report.get("health_ok") is True,
        report.get("validate_passed") is True,
        report.get("submit_success") is True,
        report.get("upload_277_success") is True,
        int((report.get("upload_277_parse") or {}).get("claims_updated", 0)) >= 1,
        report.get("upload_835_success") is True,
        report.get("claim_final_state") in {"denied", "paid", "partially_paid", "adjudicated"},
        "277ca_received" in report.get("event_types", []),
        any(e in report.get("event_types", []) for e in ("denial_processed", "payment_posted")),
    ]
    return all(go_conditions)


async def _run(args: argparse.Namespace) -> int:
    run_id = secrets.token_hex(6)
    resources = Resources(run_id=run_id)
    report: Dict[str, Any] = {"run_id": run_id}

    jwt_algorithm = (args.jwt_algorithm or os.getenv("JWT_ALGORITHM", "HS256")).upper()
    jwt_secret = args.jwt_secret or os.getenv("JWT_SECRET", "")
    jwt_private_key = args.jwt_private_key or os.getenv("JWT_PRIVATE_KEY", "")
    jwt_audience = args.jwt_audience or os.getenv("JWT_AUDIENCE", "claimflow")
    report["jwt_algorithm"] = jwt_algorithm
    if jwt_algorithm == "HS256" and not jwt_secret:
        print(json.dumps({"go": False, "error": "JWT secret missing", "hint": "--jwt-secret or JWT_SECRET env"}, indent=2))
        return 2
    if jwt_algorithm == "RS256" and not jwt_private_key:
        print(
            json.dumps(
                {
                    "go": False,
                    "error": "JWT private key missing for RS256 canary token minting",
                    "hint": "--jwt-private-key or JWT_PRIVATE_KEY env",
                },
                indent=2,
            )
        )
        return 2

    if "@" in args.canary_email:
        local_part, domain = args.canary_email.split("@", 1)
        canary_email = f"{local_part}+{run_id}@{domain}"
    else:
        canary_email = f"canary.{run_id}@noodledoc.local"
    canary_user_id = await _ensure_canary_user(tenant_id=args.tenant, email=canary_email)
    resources.user_ids.append(canary_user_id)
    report["canary_user_id"] = canary_user_id
    report["canary_user_email"] = canary_email

    token = _tenant_token(
        user_id=canary_user_id,
        tenant_id=args.tenant,
        email=canary_email,
        jwt_audience=jwt_audience,
        jwt_algorithm=jwt_algorithm,
        jwt_secret=jwt_secret,
        jwt_private_key=jwt_private_key,
    )

    try:
        async with httpx.AsyncClient(base_url=args.api_base, timeout=30.0) as client:
            root_base = args.api_base[:-4] if args.api_base.endswith("/api") else args.api_base.rstrip("/")
            health_candidates = [f"{root_base}/health", f"{root_base}/api/health"]
            health_checks: List[Dict[str, Any]] = []
            health_ok = False
            for health_url in health_candidates:
                try:
                    h = await client.get(health_url)
                    h_body: Any
                    if h.headers.get("content-type", "").startswith("application/json"):
                        h_body = h.json()
                    else:
                        h_body = h.text
                    health_checks.append({"url": health_url, "status": h.status_code, "body": h_body})
                    if h.status_code == 200:
                        health_ok = True
                except Exception as e:
                    health_checks.append({"url": health_url, "status": None, "error": str(e)})
            report["health_checks"] = health_checks
            report["health_ok"] = health_ok

            suffix = run_id
            payer_payload = {
                "name": f"Canary Payer {suffix}",
                "payer_id": f"CANARY{suffix[:6]}",
                "format_837_type": "837P",
                "filing_limit_days": 365,
                "supports_270_271": True,
                "supports_276_277": True,
                "supports_835_era": True,
                "connection_method": "api",
                "clearinghouse": "Canary API",
                "is_active": True,
            }
            code, payer = await _api_json(client, "POST", "/rcm/payers", token=token, tenant_id=args.tenant, json=payer_payload)
            report["payer_create_status"] = code
            if code != 200 or not payer.get("success"):
                report["payer_create_body"] = payer
                raise RuntimeError("payer create failed")
            payer_id = payer["data"]["id"]
            resources.payer_ids.append(payer_id)
            report["payer_id"] = payer_id

            conn_payload = {
                "connection_name": f"Canary API {suffix}",
                "clearinghouse_name": "Canary API",
                "connection_type": "api",
                "api_endpoint": args.canary_api_endpoint,
                "api_auth_method": "bearer",
                "is_active": True,
            }
            code, conn = await _api_json(
                client,
                "POST",
                f"/rcm/payers/{payer_id}/connections",
                token=token,
                tenant_id=args.tenant,
                json=conn_payload,
            )
            report["connection_create_status"] = code
            report["connection_create_success"] = bool(conn.get("success")) if isinstance(conn, dict) else False
            if code != 200 or not conn.get("success"):
                report["connection_create_body"] = conn
                raise RuntimeError("payer connection create failed")
            resources.connection_ids.append(conn["data"]["id"])

            patient_payload = {
                "first_name": "Canary",
                "last_name": f"Prod{suffix}",
                "date_of_birth": "1985-03-15",
                "gender": "F",
                "address_line_1": "100 Main Street",
                "city": "Honolulu",
                "state": "HI",
                "zip_code": "96801",
                "phone": "8085559999",
                "email": f"canary.patient.{suffix}@example.com",
                "member_id": f"CANARY-{suffix}",
                "group_number": "GRP-CANARY",
                "payer_id": payer_id,
                "relationship_to_subscriber": "18",
            }
            code, patient = await _api_json(client, "POST", "/rcm/patients", token=token, tenant_id=args.tenant, json=patient_payload)
            report["patient_create_status"] = code
            if code != 200 or not patient.get("success"):
                report["patient_create_body"] = patient
                raise RuntimeError("patient create failed")
            patient_id = patient["data"]["id"]
            resources.patient_ids.append(patient_id)
            report["patient_id"] = patient_id

            claim_payload = {
                "patient_id": patient_id,
                "payer_id": payer_id,
                "service_date_from": str(date.today()),
                "total_charges": 175.00,
                "claim_type": "professional",
                "billing_provider_npi": "1234567890",
                "rendering_provider_npi": "1234567890",
                "notes": f"CANARY_PROD_VERIFICATION::{run_id}",
                "lines": [{
                    "line_number": 1,
                    "cpt_code": "99214",
                    "cpt_description": "Office visit",
                    "units": 1,
                    "charge_amount": 175.00,
                    "place_of_service": "11",
                    "diagnosis_pointers": [1],
                }],
                "diagnoses": [{
                    "diagnosis_pointer": 1,
                    "icd10_code": "E11.9",
                    "icd10_description": "Type 2 diabetes mellitus without complications",
                    "is_primary": True,
                }],
            }
            code, claim = await _api_json(client, "POST", "/rcm/claims", token=token, tenant_id=args.tenant, json=claim_payload)
            report["claim_create_status"] = code
            if code != 200 or not claim.get("success"):
                report["claim_create_body"] = claim
                raise RuntimeError("claim create failed")
            claim_id = claim["data"]["id"]
            claim_number = claim["data"]["claim_number"]
            resources.claim_ids.append(claim_id)
            report["claim_id"] = claim_id
            report["claim_number"] = claim_number

            code, validate = await _api_json(client, "POST", f"/rcm/claims/{claim_id}/validate", token=token, tenant_id=args.tenant)
            report["validate_status"] = code
            report["validate_passed"] = bool(validate.get("data", {}).get("passed")) if isinstance(validate, dict) else False
            if code != 200:
                report["validate_body"] = validate
                raise RuntimeError("claim validate failed")

            code, submit = await _api_json(
                client,
                "POST",
                "/rcm/claims/batch/submit",
                token=token,
                tenant_id=args.tenant,
                json={"claim_ids": [claim_id], "payer_id": payer_id},
            )
            report["submit_status"] = code
            report["submit_success"] = bool(submit.get("success")) if isinstance(submit, dict) else False
            if code != 200:
                report["submit_body"] = submit
                raise RuntimeError("claim submit failed")
            file_id = submit.get("data", {}).get("file_id")
            if file_id:
                resources.edi_file_ids.append(file_id)

            icn = await _get_claim_icn(claim_id)
            report["claim_icn"] = icn

            content_277 = (
                f"ISA*00*          *00*          *ZZ*CLEARINGHOUSE  *ZZ*CLAIMFLOW      *260420*1200*^*00501*{icn}*0*P*:~\n"
                "GS*HN*CLEARINGHOUSE*CLAIMFLOW*20260420*1200*1*X*005010X214~\n"
                "ST*277*0001*005010X214~\n"
                "BHT*0085*08*277CA_TEST*20260420*1200~\n"
                f"TRN*1*{icn}*CLEARINGHOUSE~\n"
                "STC*A1:20:PR*20260420~\n"
                "SE*6*0001~\n"
                "GE*1*1~\n"
                f"IEA*1*{icn}~\n"
            )
            code, up277 = await _upload_edi(
                client,
                token=token,
                tenant_id=args.tenant,
                file_name=f"canary_{run_id}.277",
                file_type="277CA",
                content=content_277,
            )
            report["upload_277_status"] = code
            report["upload_277_success"] = bool(up277.get("success")) if isinstance(up277, dict) else False
            report["upload_277_parse"] = up277.get("data", {}).get("parse_result") if isinstance(up277, dict) else None
            if isinstance(up277, dict) and up277.get("data", {}).get("id"):
                resources.edi_file_ids.append(up277["data"]["id"])
            if code != 200 or not up277.get("success"):
                raise RuntimeError("277 upload failed")

            content_835 = (
                "ISA*00*          *00*          *ZZ*PAYER          *ZZ*CLAIMFLOW      *260420*1400*^*00501*000000001*0*P*:~\n"
                "GS*HP*PAYER*CLAIMFLOW*20260420*1400*1*X*005010X221A1~\n"
                "ST*835*0001*005010X221A1~\n"
                "BPR*I*125.00*C*ACH*CCP*01*999999999*DA*123456789**01*999999999*DA*987654321*20260425~\n"
                "TRN*1*TRACE001*1234567890~\n"
                f"CLP*{claim_number}*1*175.00*125.00**MC*PAYERCLM001~\n"
                "CAS*CO*45*50.00~\n"
                "SE*8*0001~\n"
                "GE*1*1~\n"
                "IEA*1*000000001~\n"
            )
            code, up835 = await _upload_edi(
                client,
                token=token,
                tenant_id=args.tenant,
                file_name=f"canary_{run_id}.835",
                file_type="835",
                content=content_835,
            )
            report["upload_835_status"] = code
            report["upload_835_success"] = bool(up835.get("success")) if isinstance(up835, dict) else False
            report["upload_835_parse"] = up835.get("data", {}).get("parse_result") if isinstance(up835, dict) else None
            if isinstance(up835, dict) and up835.get("data", {}).get("id"):
                resources.edi_file_ids.append(up835["data"]["id"])
            if code != 200 or not up835.get("success"):
                raise RuntimeError("835 upload failed")

            code, claim_detail = await _api_json(client, "GET", f"/rcm/claims/{claim_id}", token=token, tenant_id=args.tenant)
            report["claim_detail_status"] = code
            report["claim_final_state"] = claim_detail.get("data", {}).get("state") if isinstance(claim_detail, dict) else None

            code, events = await _api_json(client, "GET", f"/rcm/claims/{claim_id}/events", token=token, tenant_id=args.tenant)
            report["events_status"] = code
            report["event_types"] = [e.get("event_type") for e in events.get("data", [])] if isinstance(events, dict) else []

            report["go"] = _compute_go(report)

    except Exception as e:
        report["go"] = False
        report["error"] = str(e)
    finally:
        if not args.no_cleanup:
            try:
                await _cleanup(resources)
                report["cleanup"] = "ok"
            except Exception as cleanup_error:
                report["cleanup"] = f"failed: {cleanup_error}"
                report["go"] = False

    print(json.dumps(report, indent=2))
    return 0 if report.get("go") else 10


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ClaimFlow production canary and return strict GO/NO-GO")
    parser.add_argument("--tenant", required=True, help="Tenant UUID for canary run")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="API base URL")
    parser.add_argument("--jwt-algorithm", default="", help="JWT algorithm override (HS256 or RS256)")
    parser.add_argument("--jwt-secret", default="", help="JWT signing secret (defaults to JWT_SECRET env)")
    parser.add_argument("--jwt-private-key", default="", help="JWT RS256 private key PEM (defaults to JWT_PRIVATE_KEY env)")
    parser.add_argument("--jwt-audience", default="", help="JWT audience (defaults to JWT_AUDIENCE env)")
    parser.add_argument("--canary-email", default="canary.rcm+prod@noodledoc.com", help="Email claim for token/audit")
    parser.add_argument("--canary-api-endpoint", default="https://httpbin.org/anything", help="Canary clearinghouse API endpoint")
    parser.add_argument("--no-cleanup", action="store_true", help="Keep canary records for debugging")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
