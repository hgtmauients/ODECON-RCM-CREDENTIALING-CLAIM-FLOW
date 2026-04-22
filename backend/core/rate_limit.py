"""
ClaimFlow - Rate limiting middleware.
Simple in-memory sliding window rate limiter per IP.
For production, use Redis-backed rate limiting.
"""

import time
import logging
from collections import defaultdict
from typing import Dict, List

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW = 60  # seconds


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_window: int = RATE_LIMIT_REQUESTS, window_seconds: int = RATE_LIMIT_WINDOW):
        super().__init__(app)
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self._hits: Dict[str, List[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Clean old entries
        self._hits[client_ip] = [t for t in self._hits[client_ip] if t > now - self.window_seconds]

        if len(self._hits[client_ip]) >= self.requests_per_window:
            logger.warning(f"Rate limit exceeded for {client_ip}")
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={"Retry-After": str(self.window_seconds)},
            )

        self._hits[client_ip].append(now)
        response = await call_next(request)
        return response
