# ClaimFlow — Production Readiness TODO

## System Audit Summary

### Architecture (Current State)
```
┌─────────────────────────────────────────────────────────┐
│  Frontend (React/TS)                                     │
│  └── api.ts (fetch + auth/tenant headers)               │
│  └── 6 RCM pages + 3 admin pages + credentialing page   │
├─────────────────────────────────────────────────────────┤
│  FastAPI Backend                                         │
│  ├── api/auth.py (JWT principal + tenant resolver)       │
│  ├── api/tenants.py (tenant CRUD)                        │
│  ├── api/rcm/* (claims, denials, payers, EDI, enrollment)│
│  ├── api/credentialing.py (provider onboard + verify)    │
│  ├── services/* (EDI, rules, denials, encryption, email) │
│  └── jobs/poll_835_files.py (background poller)          │
├─────────────────────────────────────────────────────────┤
│  PostgreSQL + SQLAlchemy (async)                         │
│  └── 28 tables, all tenant-scoped                        │
│  └── Alembic migrations (rcm_001 → rcm_006)             │
└─────────────────────────────────────────────────────────┘
```

### What Works Now
- [x] Multi-tenant data model with `tenant_id` on all tables
- [x] JWT auth with Principal (user_id, tenant_id, email, roles)
- [x] Claims CRUD + validation + batch submit + CSV import
- [x] EDI 837 generation (writes to disk with proper ANSI X12 envelope)
- [x] EDI 835/277 parsing (CLP/CAS/STC segment extraction)
- [x] EDI file upload/list/detail API
- [x] Denial case management + playbook + appeal generation
- [x] Payer profile CRUD + rules + connections + fee schedules
- [x] Provider credentialing webhook with HMAC validation
- [x] Payer enrollment (ERA/EFT, document vault, renewals)
- [x] Smart payer enrollment (state-license-aware)
- [x] Encryption service (AES-256-GCM)
- [x] Email service (SMTP with dev fallback)
- [x] Background 835/277 polling (tenant-scoped)
- [x] Frontend API client with tenant header injection
- [x] Zero external integrations by default

---

## Production TODO

### P0 — Blocking for any deployment

| # | Task | Effort |
|---|------|--------|
| 1 | **Alembic configuration** — Add `alembic.ini` + `env.py` pointing to `core.database` engine and `models.base.Base.metadata` | S |
| 2 | **Environment configuration** — Create `.env.example` with all required vars (DATABASE_URL, JWT_SECRET, CLAIMFLOW_ENCRYPTION_KEY, SMTP_*, CORS_ORIGINS, EDI_STORAGE_PATH) | S |
| 3 | **Frontend build system** — Add `package.json`, `tsconfig.json`, `vite.config.ts` (or similar) so the webapp compiles | M |
| 4 | **Frontend routing** — Add `App.tsx` with React Router paths for all pages | M |
| 5 | **Auth flow (frontend)** — Login page / OIDC redirect + token storage + apiService.setAuthToken integration | M |
| 6 | **Docker compose** — `docker-compose.yml` with postgres + backend + frontend for local dev | M |
| 7 | **CORS + proxy** — Ensure frontend dev server proxies `/api` to backend correctly | S |

### P1 — Required for production security

| # | Task | Effort |
|---|------|--------|
| 8 | **RS256 JWT validation** — Support JWKS endpoint for production OIDC (Auth0/Keycloak/Okta) instead of HS256 dev secret | M |
| 9 | **Rate limiting** — Add slowapi or similar to protect auth + webhook + EDI upload endpoints | S |
| 10 | **Input validation** — Replace `Dict[str, Any]` request bodies with Pydantic models for all endpoints | L |
| 11 | **RBAC policy enforcement** — Define role matrix (super_admin, org_admin, billing, credentialing, readonly) and enforce consistently | M |
| 12 | **Audit logging** — Wire `SecurityAuditLog` writes into credential access, claim submit, provider approve/reject flows | M |
| 13 | **Secret rotation** — Implement key rotation for CLAIMFLOW_ENCRYPTION_KEY (re-encrypt on rotation) | M |
| 14 | **Webhook replay protection** — Add nonce/timestamp window check beyond HMAC signature | S |
| 15 | **HTTPS enforcement** — Add TLS termination docs / HSTS headers | S |

### P2 — Required for production reliability

| # | Task | Effort |
|---|------|--------|
| 16 | **Database migrations testing** — Test `rcm_006` migration against real Postgres (verify constraint drops/creates) | M |
| 17 | **EDI file storage** — Replace local filesystem with S3/Azure Blob + pre-signed download URLs | M |
| 18 | **Background job runner** — Replace `asyncio.create_task` in credentialing with Celery/ARQ/APScheduler for reliability | M |
| 19 | **Health check depth** — `/health` should verify DB connectivity + storage access | S |
| 20 | **Error handling** — Replace generic `except Exception` catches with typed error responses | M |
| 21 | **Connection pooling tuning** — Profile and tune DB pool (pool_size, max_overflow, pool_timeout) | S |
| 22 | **Logging structured** — Switch to JSON structured logging (correlation_id, tenant_id, user_id in every log line) | M |
| 23 | **Graceful shutdown** — Ensure in-flight requests complete before app exit | S |

### P3 — Feature completeness for MVP

| # | Task | Effort |
|---|------|--------|
| 24 | **Rules engine execution** — `RulesEngine.validate_claim` needs full implementation (condition matching + action execution) | L |
| 25 | **Denial manager** — `DenialManager.generate_appeal` + `process_835_denials` need concrete implementations | L |
| 26 | **Auto-posting engine** — `AutoPostingEngine.auto_post_835` needs to update claim amounts + state transitions | M |
| 27 | **Clearinghouse transport** — `ClearinghouseService.submit_837_file` + `poll_for_835_files` need real SFTP/API logic | L |
| 28 | **Smart payer enrollment** — `create_smart_payer_enrollment_cases` + `get_provider_eligible_payers` need tenant_id params wired | M |
| 29 | **Claim number generation** — Current timestamp-based numbers can collide under load; use sequence or UUID | S |
| 30 | **Pagination** — Add proper `total_count` via separate COUNT query on list endpoints | M |
| 31 | **837 completeness** — Full 2000A/2000B/2300/2400 loop generation per implementation guide | XL |
| 32 | **Tenant onboarding flow** — Self-service signup API + first-user bootstrap | M |

### P4 — Quality & Observability

| # | Task | Effort |
|---|------|--------|
| 33 | **Unit tests** — Cover rules_engine, edi_processor parse logic, encryption roundtrips | L |
| 34 | **Integration tests** — Full claim lifecycle (create → validate → submit → 277 → 835 → payment post) | L |
| 35 | **API contract tests** — OpenAPI schema snapshot tests to catch breaking changes | M |
| 36 | **Metrics** — Prometheus/StatsD: request latency, claim counts by state, EDI processing times | M |
| 37 | **Alerting** — SLA breach alerts for filing deadlines, appeal due dates, credential expirations | M |
| 38 | **CI/CD pipeline** — GitHub Actions (lint, test, build, deploy to staging) | M |

### P5 — Nice-to-have / Post-MVP

| # | Task | Effort |
|---|------|--------|
| 39 | **Tenant white-labeling** — Custom branding per tenant (logo, colors, email templates) | M |
| 40 | **Bulk operations** — Batch validate, batch re-submit, batch appeal generation | M |
| 41 | **Real-time notifications** — WebSocket or SSE for claim state changes | M |
| 42 | **Reporting/dashboards** — Aggregate analytics (days in AR, denial rate, collection rate) | L |
| 43 | **FHIR compatibility** — Optional FHIR resource mapping for claims/patients | L |
| 44 | **Multi-currency** — Support non-USD for international deployments | S |
| 45 | **Plugin system** — Formal interface for custom EMR connectors | L |

---

## Effort Key
- **S** = Small (< 1 day)
- **M** = Medium (1-3 days)
- **L** = Large (3-5 days)
- **XL** = Extra Large (1-2 weeks)

## Recommended Sprint Order
1. Sprint 1 (Week 1-2): P0 items #1-7 → app runs end-to-end locally
2. Sprint 2 (Week 3-4): P1 items #8-15 → security hardened
3. Sprint 3 (Week 5-6): P2 items #16-23 → reliable for staging
4. Sprint 4 (Week 7-10): P3 items #24-32 → feature complete MVP
5. Sprint 5 (Week 11-12): P4 items #33-38 → production observable
