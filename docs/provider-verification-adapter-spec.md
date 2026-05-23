# Provider Verification Adapter Spec

This document defines the drop-in adapter contract used by ClaimFlow for provider verification.

## Purpose

Decouple ClaimFlow from vendor-specific APIs for:

- license verification
- background checks

ClaimFlow only calls two stable endpoints:

- `GET /license/verify`
- `POST /background/check`

## Service Location

Starter service implementation in this repo:

- `backend/adapter/main.py`

Local docker compose service name:

- `provider-adapter` on port `8010`

## Endpoint Contracts

## `GET /license/verify`

### Request

Query params:

- `state` (required)
- `license_number` (required)
- `name` (optional)
- `dob` (optional)

### Response (normalized)

```json
{
  "verified": true,
  "state": "HI",
  "license_number": "HI-12345",
  "status": "ACTIVE",
  "issue_date": null,
  "expiration_date": null,
  "discipline_history": [],
  "requires_manual_review": false,
  "source": "provider_adapter",
  "verified_at": "2026-05-23T00:00:00+00:00"
}
```

### Failure response shape

```json
{
  "verified": false,
  "state": "HI",
  "license_number": "HI-12345",
  "error": "license_upstream_http_503",
  "requires_manual_review": true,
  "source": "provider_adapter",
  "checked_at": "2026-05-23T00:00:00+00:00"
}
```

## `POST /background/check`

### Request

```json
{
  "first_name": "Jane",
  "last_name": "Doe",
  "dob": "1980-01-01",
  "ssn": "optional"
}
```

### Response (normalized)

```json
{
  "verified": true,
  "clear": true,
  "findings": [],
  "recommendation": "clear",
  "checked_at": "2026-05-23T00:00:00+00:00",
  "source": "provider_adapter"
}
```

### Failure response shape

```json
{
  "verified": false,
  "clear": false,
  "findings": [],
  "recommendation": "requires_review",
  "checked_at": "2026-05-23T00:00:00+00:00",
  "source": "provider_adapter",
  "error": "background_upstream_http_503"
}
```

## Modes

## Starter mode (default)

When `LICENSE_UPSTREAM_URL` and/or `BACKGROUND_UPSTREAM_URL` are empty:

- adapter returns deterministic local decisions
- useful for local dev + immediate wiring

## Upstream mode

Set env vars on adapter service:

- `LICENSE_UPSTREAM_URL`
- `BACKGROUND_UPSTREAM_URL`

Adapter proxies to upstream, then normalizes response.

## ClaimFlow Wiring

Set backend env vars:

- `STATE_LICENSE_PROVIDER_URL`
- `BACKGROUND_CHECK_PROVIDER_URL`

Local defaults are wired in `docker-compose.yml` to:

- `http://provider-adapter:8010/license/verify`
- `http://provider-adapter:8010/background/check`

## Health Check

`GET /health` returns:

- service status
- whether each verifier is in starter or upstream mode

