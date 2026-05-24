# SLO and Alert Policy (P2.1 Baseline)

## Service Level Objectives

### API Availability SLO
- Target: **99.9%** monthly availability for `GET /health`
- Error budget: ~43m 49s/month
- Burn alerts:
  - fast burn: >10% budget consumed in 1h
  - slow burn: >25% budget consumed in 24h

### API Latency SLO
- Target: p95 latency:
  - read endpoints: **< 500ms**
  - mutation endpoints: **< 1.2s**
- Burn alerts:
  - p95 above threshold for 15 minutes (warning)
  - p95 above threshold for 60 minutes (critical)

### Critical Workflow SLO
- Claim lifecycle canary (`verify_production_canary`) must remain GO on each deploy.
- Alert when two consecutive canary runs fail.

## Security Signal Alerts (P2.2 Baseline)

Alert on `SECURITY-SIGNAL` events for:
- `auth_token_invalid` spike
- `rate_limit_exceeded` spike
- `webhook_replay_detected`
- `webhook_replay_backend_unavailable`
- `webhook_signature_invalid`
- `webhook_secret_missing`

Suggested thresholds:
- invalid token spike: >200 events / 5m
- rate-limit spike: >500 events / 5m
- webhook replay detected: >=3 events / 10m
- replay backend unavailable: any event (critical)

## Operational Response

1. Confirm if issue is tenant-specific or global.
2. Inspect recent deploys/config changes.
3. If global and high-severity, pause deploys and roll back.
4. Open incident channel and track remediation with ETA.
