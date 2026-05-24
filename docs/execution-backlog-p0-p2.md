# ClaimFlow Execution Backlog (P0/P1/P2)

## Objective

Raise system quality from ~8.4 to 9.0+ with a concrete, test-gated rollout plan that can be executed in small PRs.

## Delivery Model

- Branch strategy: one PR per backlog item group (small, reviewable changes).
- Release cadence: P0 weekly, P1 weekly/bi-weekly, P2 bi-weekly.
- Gate policy: no rollout to next phase until all phase gates are green.
- Risk policy: security-impacting items must include regression tests in the same PR.

---

## P0 (Immediate Hardening, 1-2 weeks)

### P0.1 Startup security config validator
- Scope:
  - Add a central startup validator for required production config and unsafe combinations.
  - Enforce critical settings (`JWT_SECRET`/JWKS rules, adapter auth requirements, trusted proxy config when forwarding headers are used).
- Files:
  - `backend/app/main.py`
  - `backend/core/` (new module: `startup_checks.py`)
  - `backend/adapter/main.py` (shared validation behavior)
- Tests:
  - Unit tests for each fail-fast path and valid path.
  - One integration test that verifies app startup fails for invalid production config.
- Test gate commands:
  - `py -3 -m pytest backend/tests/test_startup_checks.py -v`
  - `py -3 -m pytest backend/tests/test_provider_adapter.py -v`

### P0.2 Security regression suite marker + CI gate
- Scope:
  - Add a dedicated `@pytest.mark.security` marker and tag existing critical tests.
  - Add a CI job to run only `-m security` as a required check.
- Files:
  - `backend/pyproject.toml` (pytest markers)
  - `backend/tests/*` (tag critical tests)
  - `.github/workflows/ci.yml`
- Tests:
  - Verify marker registration and non-empty selection.
  - CI fails if security suite fails.
- Test gate commands:
  - `py -3 -m pytest backend/tests -m security -v`
  - `py -3 -m pytest backend/tests/test_auth_error_messages.py backend/tests/test_csv_export.py backend/tests/test_provider_adapter.py -v`

### P0.3 CSV/export context safety sweep
- Scope:
  - Extend CSV formula neutralization coverage to all export endpoints.
  - Add explicit tests for payloads coming from model fields typically exported.
- Files:
  - `backend/core/csv_export.py`
  - `backend/api/*` export routes
  - `backend/tests/test_csv_export.py`
- Tests:
  - Add table-driven tests for leading-space payloads and control chars.
- Test gate commands:
  - `py -3 -m pytest backend/tests/test_csv_export.py -v`
  - `py -3 -m pytest backend/tests -k export -v`

### P0 Exit Criteria
- All P0 tests passing locally and in CI.
- Security marker job present and required.
- No startup path allows known-invalid production security config.

---

## P1 (Reliability + Abuse Resistance, 2-4 weeks)

### P1.1 External integration resiliency baseline
- Scope:
  - Standardize timeout/retry policies across outbound HTTP integrations.
  - Document per-integration timeout budget and retry count.
- Files:
  - `backend/services/*.py` integration clients
  - `RUNBOOK.md`
- Tests:
  - Unit tests validating retry behavior and non-retry on client errors.
- Test gate commands:
  - `py -3 -m pytest backend/tests -k \"retry or timeout or integration\" -v`

### P1.2 Idempotency for critical mutation flows
- Scope:
  - Add idempotency key handling for high-risk mutation endpoints (webhooks, bulk mutation routes).
  - Persist short-lived idempotency records (Redis or DB-backed).
- Files:
  - `backend/api/credentialing.py`
  - `backend/api/rcm/claims.py`
  - `backend/core/` (idempotency helper module)
- Tests:
  - Duplicate request tests prove one-side effect only.
  - Concurrency test for race condition behavior.
- Test gate commands:
  - `py -3 -m pytest backend/tests -k \"idempotency or replay\" -v`
  - `py -3 -m pytest backend/tests/test_e2e_credentialing.py -v`
 - Status: expanded in-progress (guards now cover create + batch submit + credentialing decision mutations; helper concurrency test added)

### P1.3 Dependency and runtime security hygiene
- Scope:
  - Add automated dependency scanning and a weekly update cadence.
  - Add policy for critical CVEs: patch window + owner.
- Files:
  - `.github/workflows/` (dependency scan workflow)
  - `RUNBOOK.md` (security patch SOP)
- Tests/gates:
  - CI scan job required.
  - Block merge on critical vulnerabilities in runtime dependencies.
- Test gate commands:
  - CI-managed (scan workflow required check).
 - Status: baseline implemented (`dependency-security-scan` job with `pip-audit` + `npm audit --audit-level=high`)

### P1 Exit Criteria
- Outbound integrations use standardized timeout/retry policies.
- Duplicate mutation attempts are safely handled on critical endpoints.
- Dependency scan runs automatically and is enforced in CI.

---

## P2 (Observability + Operability, 3-6 weeks)

### P2.1 SLOs and alert thresholds
- Scope:
  - Define backend API SLOs (availability, p95 latency, error budget).
  - Add alert thresholds and runbook actions for breaches.
- Files:
  - `RUNBOOK.md`
  - `docs/` (SLO/alert policy doc)
- Tests/gates:
  - Release checklist enforces SLO dashboard review before production deploy.

### P2.2 Security telemetry dashboard baseline
- Scope:
  - Track auth failures, replay failures, rate-limit violations, and tenant override attempts.
  - Define incident triage flow for spikes.
- Files:
  - `backend/core/logging_config.py`
  - `backend/core/audit.py`
  - `RUNBOOK.md`
- Tests:
  - Unit tests for emitted security event fields.
  - Integration tests for key security event flows.
- Test gate commands:
  - `py -3 -m pytest backend/tests -k \"audit or security\" -v`

### P2.3 Release gate expansion
- Scope:
  - Expand `backend/scripts/release_production.py` release checks to include:
    - security regression subset
    - critical route smoke checks
    - basic post-deploy error-rate guard
- Files:
  - `backend/scripts/release_production.py`
  - `backend/scripts/verify_production_canary.py`
- Tests:
  - Unit tests for release report parsing and fail/allow behavior.
- Test gate commands:
  - `py -3 -m pytest backend/tests -k \"release or canary\" -v`
 - Status: expanded in-progress (`release_production.py` now includes security gate, post-deploy smoke, critical route smoke, and log-based error-rate guard; unit tests added)

### P2 Exit Criteria
- SLOs/alerts documented and operational.
- Security event telemetry present and actionable.
- Release script enforces expanded pre/post checks.

---

## Rollout Order (Concrete)

1. **Phase A (Week 1):** P0.1 + P0.2  
   - Rollout: dev -> staging -> production.
   - Hold point: do not start P1 until startup validation + security CI gate are stable for one release cycle.

2. **Phase B (Week 2):** P0.3  
   - Rollout: dev -> staging data export validation -> production.
   - Hold point: export regression tests green for one full CI day.

3. **Phase C (Weeks 3-4):** P1.1 + P1.2  
   - Rollout: per integration area in separate PRs.
   - Hold point: no idempotency regressions in credentialing and claims E2E tests.

4. **Phase D (Week 5):** P1.3  
   - Rollout: CI-only first, then enforce as required checks.

5. **Phase E (Weeks 6-8):** P2.1 + P2.2 + P2.3  
   - Rollout: telemetry/readiness in staging first, then production after one successful release canary cycle.

---

## Required Test Gates by Phase

### Global gate (every PR)
- `py -3 -m pytest backend/tests/test_tenant_isolation_http.py -v`
- `py -3 -m pytest backend/tests/test_tenant_escape_vectors.py -v`
- `py -3 -m pytest backend/tests/test_rate_limit_keying.py -v`
- `py -3 -m pytest backend/tests/test_provider_adapter.py -v`
- `py -3 -m pytest backend/tests/test_csv_export.py -v`
- `py -3 -m pytest backend/tests/test_auth_error_messages.py -v`

### Pre-release gate (before `release_production.py`)
- Full backend test suite in CI is green.
- Security marker suite is green (`-m security` once introduced in P0.2).
- Last canary result in staging indicates GO.

---

## Tracking Template (copy per backlog item)

```
Item:
Owner:
PR:
Status: todo | in_progress | blocked | done
Risk: low | medium | high
Tests Added:
Test Gate Result:
Rollout Stage: dev | staging | prod
Notes:
```

