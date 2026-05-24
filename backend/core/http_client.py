"""
Shared outbound HTTP client policy for integration calls.

Centralizes timeout/retry/backoff behavior so external-service interactions
have consistent resilience defaults across modules.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Iterable

import httpx


AsyncClientFactory = Callable[..., Any]


async def request_with_retry(
    *,
    method: str,
    url: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    auth: Any = None,
    content: str | bytes | None = None,
    timeout_seconds: float = 30.0,
    max_retries: int = 2,
    retry_backoff_seconds: float = 0.2,
    retry_on_statuses: Iterable[int] = (500, 502, 503, 504),
    client_factory: AsyncClientFactory = httpx.AsyncClient,
) -> httpx.Response:
    """
    Execute one HTTP request with bounded retries and exponential backoff.

    Retries:
    - transport-level failures (timeout, connection reset, DNS, etc)
    - response statuses in `retry_on_statuses`
    """
    max_retries = max(0, int(max_retries))
    retryable_statuses = {int(s) for s in retry_on_statuses}
    attempt = 0
    last_exception: Exception | None = None

    while attempt <= max_retries:
        try:
            async with client_factory(timeout=timeout_seconds) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_body,
                    headers=headers,
                    auth=auth,
                    content=content,
                )

            if response.status_code in retryable_statuses and attempt < max_retries:
                await asyncio.sleep(retry_backoff_seconds * (2**attempt))
                attempt += 1
                continue
            return response

        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exception = exc
            if attempt >= max_retries:
                raise
            await asyncio.sleep(retry_backoff_seconds * (2**attempt))
            attempt += 1

    if last_exception:
        raise last_exception
    raise RuntimeError("unreachable retry state")
