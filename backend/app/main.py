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
    app = FastAPI(
        title="ClaimFlow",
        description="Multi-tenant Revenue Cycle Management SaaS",
        version="0.1.0",
        redirect_slashes=False,
        lifespan=lifespan,
    )

    # --- CORS ---
    allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Rate limiting ---
    from core.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware, requests_per_window=200, window_seconds=60)

    # --- Global exception handler ---
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception")
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

    # --- Health check ---
    @app.get("/health")
    async def health():
        from core.database import engine
        try:
            async with engine.connect() as conn:
                await conn.execute(sa_text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
        status_val = "ok" if db_ok else "degraded"
        return {"status": status_val, "service": "ClaimFlow", "database": db_ok}

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("ENV", "development") == "development",
    )
