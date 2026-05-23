# ClaimFlow

**Multi-tenant Revenue Cycle Management SaaS**

---

## Overview

ClaimFlow is a standalone, vendor-agnostic RCM platform with OAuth/OIDC authentication, tenant-safe data boundaries, and a default manual/CSV + EDI workflow. It ships with zero live integrations enabled by default.

---

## Contents

### Backend (`backend/`)

#### App Shell
- `app/main.py` - FastAPI application factory
- `core/database.py` - Async PostgreSQL session factory
- `api/auth.py` - JWT/OIDC principal extraction (tenant_id, roles)
- `api/tenants.py` - Tenant CRUD API
- `core/integrations.py` - Feature flag system

#### API Routers (`backend/api/`)
- `credentialing.py` - Provider credentialing endpoints (webhook + CRUD)
- `rcm/claims.py` - Claims management (CRUD, validate, batch submit, CSV import)
- `rcm/denials.py` - Denial management
- `rcm/payer_enrollment.py` - Payer enrollment & ERA
- `rcm/payer_profiles.py` - Payer profiles CRUD + fee schedules
- `rcm/edi.py` - EDI file upload/list/detail
- `rcm/provider_approval_integration.py` - Provider → payer enrollment bridge

#### Database Models (`backend/models/`)
- `base.py` - Shared SQLAlchemy DeclarativeBase
- `tenant.py` - Tenant entity
- `rcm.py` - PayerProfile, PayerRule, TradingPartnerConnection, PayerCredential, FeeSchedule
- `claims.py` - Claim, ClaimLine, ClaimDiagnosis, ClaimEvent, EDIFile, ClaimQueue
- `denials.py` - DenialCase, DenialPlaybook, AppealTemplate, CARCCode, RARCCode
- `payer_credentialing.py` - PayerCredentialingCase, ERAEnrollmentCase, ProviderDocument
- `credentialing.py` - ProviderCredentialing, CredentialingVerificationLog
- `audit.py` - CredentialAccessLog, SecurityAuditLog, MFAAttempt

All models include `tenant_id` for multi-tenant isolation.

#### Services (`backend/services/`)
- `encryption.py` - AES-256-GCM envelope encryption
- `email_service.py` - SMTP abstraction (dev-mode logging fallback)
- `database_service.py` - Provider entity service
- `credentialing_service.py` - NPI verification, license checks, OIG/SAM
- `smart_payer_enrollment.py` - Smart enrollment based on state licenses
- `denial_manager.py` - Denial case management
- `clearinghouse_transport.py` - SFTP/EDI file transport
- `edi_processor.py` - 837P generation, claim acknowledgment (277CA) and remittance (835) parsing
- `fee_schedule_service.py` - Fee schedule management
- `rules_engine.py` - Payer rules engine
- `patient_billing.py` - Patient billing communications

#### Provider Verification Adapter (`backend/adapter/`)
- `adapter/main.py` - FastAPI adapter that normalizes license/background checks
- Endpoints: `GET /license/verify`, `POST /background/check`, `GET /health`
- Local docker service: `provider-adapter` (wired by default in `docker-compose.yml`)

#### Background Jobs (`backend/jobs/`)
- `poll_835_files.py` - Poll clearinghouse for remittances (835) and claim acknowledgments (277CA) (tenant-scoped)

#### Migrations (`backend/alembic/versions/`)
- `rcm_001` through `rcm_005` - Original schema
- `rcm_006_add_tenants_and_tenant_id.py` - Multi-tenancy migration

### Frontend (`webapp/`)

#### Services
- `src/services/api.ts` - Core API client (auth + tenant header injection)
- `src/services/payerProfileService.ts` - Payer profile API wrapper
- `src/services/iconReplacementService.ts` - Icon components

#### Pages (`webapp/src/pages/rcm/`)
- `ClaimsManagement.tsx` - Claims dashboard
- `ClaimDetail.tsx` - Single claim detail + timeline
- `DenialDashboard.tsx` - Denial cases overview
- `DenialDetail.tsx` - Denial detail + playbook
- `PayerEnrollment.tsx` - Payer enrollment management
- `EDIFileManager.tsx` - EDI upload/list

#### Utilities
- `src/utils/logger.ts` - Logging utility
- `src/utils/formatters.ts` - Currency/date formatting

---

## Database Tables (28 total)

| Group | Tables |
|-------|--------|
| Platform | `tenants` |
| Credentialing | `provider_credentialing`, `credentialing_verification_log` |
| RCM Core | `payer_profiles`, `payer_rules`, `trading_partner_connections`, `payer_credentials`, `fee_schedules`, `payer_profile_versions` |
| Claims | `claims`, `claim_lines`, `claim_diagnoses`, `claim_events`, `edi_files`, `claim_queues`, `claim_validations` |
| Denials | `denial_cases`, `denial_playbooks`, `appeal_templates`, `carc_codes`, `rarc_codes` |
| Payer Credentialing | `payer_credentialing_cases`, `era_enrollment_cases`, `provider_documents`, `credentialing_renewals` |
| Audit | `credential_access_log`, `security_audit_log`, `mfa_attempts` |

---

## Quick Start

```bash
cd backend
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql+asyncpg://claimflow:claimflow@localhost:5432/claimflow"
export JWT_SECRET="your-secret-key"

# Run migrations
alembic upgrade head

# Start server
python -m app.main
```

---

## Architecture

- **Auth**: JWT/OIDC with tenant_id claim
- **Multi-tenancy**: Application-level tenant_id filtering on all queries
- **EDI**: Manual CSV/EDI upload by default; optional clearinghouse transport
- **Integrations**: Zero enabled by default; feature-flagged addons

---

## Dependencies

- Python 3.11+
- FastAPI, SQLAlchemy 2.0+, asyncpg
- PostgreSQL 14+
- React 18+, TypeScript
