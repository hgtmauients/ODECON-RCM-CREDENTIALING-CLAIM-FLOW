"""
ClaimFlow - FastAPI application factory and lifecycle management.
This is the standalone multi-tenant RCM SaaS entry point.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text as sa_text
import uvicorn

logger = logging.getLogger("claimflow")


def _init_sentry() -> None:
    """Initialize Sentry if SENTRY_DSN is set. Safe to call when SDK is missing."""
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("ENV", "development"),
            release=os.getenv("RELEASE_VERSION"),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
            send_default_pii=False,  # PHI safety: do not auto-attach request bodies / headers
            integrations=[FastApiIntegration(), StarletteIntegration()],
        )
        logger.info("Sentry initialized for environment=%s", os.getenv("ENV"))
    except Exception as e:
        logger.warning("Failed to initialize Sentry: %s", e)


_init_sentry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle hooks."""
    from core.logging_config import setup_logging
    from core.scheduler import start_scheduler, stop_scheduler
    setup_logging()
    logger.info("ClaimFlow starting up")
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("ClaimFlow shutting down")


def create_app() -> FastAPI:
    from core.startup_checks import validate_api_startup_security
    validate_api_startup_security(os.environ)

    is_production = os.getenv("ENV", "development") == "production"

    # In production: disable interactive API docs and the OpenAPI schema endpoint
    # to avoid leaking the API surface to anonymous callers.
    docs_kwargs = {} if not is_production else {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }

    app = FastAPI(
        title="ClaimFlow",
        description="Multi-tenant Revenue Cycle Management SaaS",
        version="0.1.0",
        redirect_slashes=False,
        lifespan=lifespan,
        **docs_kwargs,
    )

    # --- CORS ---
    allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Tenant-ID",
            "Idempotency-Key",
            "X-Request-ID",
        ],
    )

    # --- Request ID + Rate limiting ---
    # NB: Starlette runs middlewares in REVERSE add order, so RequestIDMiddleware
    # (added last) runs FIRST and can tag the request id on every downstream log line.
    from core.rate_limit import RateLimitMiddleware, DEFAULT_REQUESTS, DEFAULT_WINDOW
    from core.request_id import RequestIDMiddleware
    app.add_middleware(RateLimitMiddleware, requests_per_window=DEFAULT_REQUESTS, window_seconds=DEFAULT_WINDOW)
    app.add_middleware(RequestIDMiddleware)

    # --- Global exception handler ---
    # Logs the full exception server-side; returns a generic message to clients
    # (no str(exc) or stack trace in the response body — avoids info disclosure).
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # --- Register routers ---
    from api.tenants import router as tenants_router
    from api.dev_login import router as dev_login_router
    from api.rcm import (
        claims_router,
        payer_profiles_router,
        payer_enrollment_router,
        denials_router,
        provider_approval_integration_router,
        edi_router,
        patients_router,
        caqh_router,
        codes_router,
    )
    from api.credentialing import router as credentialing_router
    from api.admin_users import router as admin_users_router
    from api.admin_audit import router as admin_audit_router
    from api.notifications import router as notifications_router
    from api.dashboard import router as dashboard_router
    from api.search import router as search_router

    app.include_router(tenants_router, prefix="/api")
    app.include_router(dev_login_router, prefix="/api")
    app.include_router(claims_router, prefix="/api")
    app.include_router(payer_profiles_router, prefix="/api")
    app.include_router(payer_enrollment_router, prefix="/api")
    app.include_router(denials_router, prefix="/api")
    app.include_router(provider_approval_integration_router, prefix="/api")
    app.include_router(edi_router, prefix="/api")
    app.include_router(patients_router, prefix="/api")
    app.include_router(caqh_router, prefix="/api")
    app.include_router(codes_router, prefix="/api")
    app.include_router(credentialing_router, prefix="/api")
    app.include_router(admin_users_router, prefix="/api")
    app.include_router(admin_audit_router, prefix="/api")
    app.include_router(notifications_router, prefix="/api")
    app.include_router(dashboard_router, prefix="/api")
    app.include_router(search_router, prefix="/api")

    # --- Health check ---
    # Returns 200 when DB is reachable, 503 when degraded so load balancers
    # and orchestrators (k8s, Docker, uptime monitors) can route around the
    # instance. Body always includes the same JSON shape for human inspection.
    @app.get("/health")
    async def health():
        from core.database import engine
        from core.scheduler import SCHEDULER_ENABLED
        try:
            async with engine.connect() as conn:
                await conn.execute(sa_text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False

        redis_ok = True
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis
                client = redis.Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
                redis_ok = bool(client.ping())
            except Exception:
                redis_ok = False

        body = {
            "status": "ok" if db_ok else "degraded",
            "service": "ClaimFlow",
            "database": db_ok,
            "redis": redis_ok,
            "scheduler_enabled": SCHEDULER_ENABLED,
        }
        return JSONResponse(status_code=200 if db_ok else 503, content=body)

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("ENV", "development") == "development",
    )
