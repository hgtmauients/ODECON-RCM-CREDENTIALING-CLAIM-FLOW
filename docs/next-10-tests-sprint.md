# Next 10 Tests Sprint (Implemented)

This sprint prioritized tests that protect authentication/session integrity, adapter contract stability, and provider-verification fail-closed behavior.

## Priority Order

1. [x] `AuthProvider` clears malformed session payloads on boot.
2. [x] `AuthProvider` tenant override updates persisted session user.
3. [x] `AuthProvider` login failure does not persist session state.
4. [x] `AuthProvider` logout removes legacy localStorage keys.
5. [x] Adapter `GET /license/verify` rejects missing required params.
6. [x] Adapter starter mode flags suspicious licenses as manual-review.
7. [x] Adapter upstream background response normalizes `clear=false` to `requires_review`.
8. [x] Credentialing service state-license non-200 fails closed to manual-review.
9. [x] Credentialing service infers verification from ACTIVE license status.
10. [x] Credentialing service background-check non-200 fails closed to requires_review.

## Files Updated

- `webapp/src/auth/__tests__/AuthProvider.test.tsx`
- `backend/tests/test_provider_adapter.py`
- `backend/tests/test_credentialing_service_integrations.py`
