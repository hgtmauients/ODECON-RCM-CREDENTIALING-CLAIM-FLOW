# Security Telemetry Dashboard Baseline (P2.2)

## Event schema

Security events are emitted as log lines tagged with:
- `security_event`
- `security_fields`

`security_fields` includes:
- `schema_version` (current: 1)
- `env`
- `emitted_at_utc`
- event-specific dimensions (tenant_id, path, bucket, requested_tenant_id, etc.)

## Initial dashboard widgets

1. **Invalid token volume**
   - filter: `security_event=auth_token_invalid`
   - chart: events/minute
2. **Rate-limit exceed volume**
   - filter: `security_event=rate_limit_exceeded`
   - chart: events/minute + top `path`
3. **Webhook replay detections**
   - filter: `security_event=webhook_replay_detected`
   - chart: count + top `tenant_id`
4. **Tenant override attempts**
   - filters:
     - denied: `security_event=tenant_override_denied`
     - applied: `security_event=tenant_override_applied`
   - chart: denied/applied ratio by hour

## Alert seeds

- `auth_token_invalid` > 200 in 5m (warning)
- `rate_limit_exceeded` > 500 in 5m (warning)
- `webhook_replay_detected` >= 3 in 10m (critical)
- `webhook_replay_backend_unavailable` >= 1 in 5m (critical)
- `tenant_override_denied` spike > 20 in 10m (investigate)

## Triage flow

1. Validate whether spike is tenant-scoped or global.
2. Check for recent deploy/config change within previous hour.
3. Correlate with API error/latency and ingress source IPs.
4. If global + high severity, halt deploys and trigger incident channel.
5. File post-incident actions for rate limits, auth hardening, or partner remediation.
