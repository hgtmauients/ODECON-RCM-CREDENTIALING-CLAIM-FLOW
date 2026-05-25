# Credentialing Runtime Migration Note (2026-05-25)

## Objective

Formalize the credentialing execution architecture after decoupling jobs from API modules and reducing duplicate execution paths.

## Why This Change

The previous runtime path allowed background credentialing checks to be triggered from API routes while a scheduler worker could also process queued records. That created:

- Layering inversion (`jobs` importing from `api`).
- Potential duplicate execution (API background task + queue worker).
- Harder testability and maintenance ownership boundaries.

## Architecture Before

- `backend/jobs/credentialing_queue.py` imported and called `api.credentialing.run_credentialing_checks`.
- `api/credentialing.py` both:
  - queued records (`pending`), and
  - spawned immediate background tasks in multiple endpoints.
- Scheduler worker and API background tasks could both race to process the same record.

## Architecture After

### New service-layer runtime module

- Added `backend/services/credentialing_runtime.py`.
- Canonical execution function:
  - `run_credentialing_checks(provider_id, signup_data, tenant_id, preclaimed=False)`

### Dependency direction

- `jobs/credentialing_queue.py` now imports from `services.credentialing_runtime` (not API).
- `api/credentialing.py` keeps a backward-compatible wrapper:
  - `api.credentialing.run_credentialing_checks(...)` delegates to service runtime.

### Trigger behavior by mode

- **Scheduler enabled** (`CLAIMFLOW_SCHEDULER_ENABLED=true`):
  - API endpoints leave records in `pending`.
  - Queue worker is the single execution path.
- **Scheduler disabled** (`CLAIMFLOW_SCHEDULER_ENABLED=false`):
  - API endpoints spawn background execution for local/dev behavior.

This preserves local usability while ensuring a single authoritative worker path in scheduler-enabled environments.

## Additional Related Cleanup in Same Pass

- `backend/core/scheduler.py` now uses `APP_BASE_URL` (fallback `https://noodledoc.com`) instead of hardcoded URL for expiration notification links.
- Removed stale Denials endpoint TODO in `webapp/src/pages/rcm/DenialDashboard.tsx`.
- `backend/services/patient_billing.py` no longer imports non-existent `core.config`; it now reads Twilio/SendGrid config from environment variables.

## Legacy Module Status

Legacy modules have now been removed from the codebase after confirming zero runtime imports:

- Removed `backend/services/database_service.py`
- Removed `backend/services/credentialing_rcm_integration.py`

Preferred enrollment path remains:

- `services.smart_payer_enrollment.create_smart_payer_enrollment_cases`

## Validation Performed

- `py -m pytest backend/tests/test_e2e_credentialing.py -q` -> passed.
- `py -m pytest backend/tests/test_adversarial_audit_findings.py backend/tests/test_tenant_isolation_http.py -q` -> passed.

## Migration Guidance for Contributors

1. **Do not add new runtime logic in API modules** for credentialing execution.
2. **Use `services/credentialing_runtime.py`** for execution behavior.
3. **Use scheduler queue path** as the production source of truth.
4. **Treat API wrapper as compatibility only**; new callers should import service runtime directly when appropriate.
5. **Prefer smart enrollment service** over legacy credentialing-RCM integration helper.

## Recommended Next Cleanup Step

- Add a CI check (import-graph/lint rule) preventing `jobs -> api` imports.
