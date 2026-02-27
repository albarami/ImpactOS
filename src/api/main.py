"""FastAPI application entry point for ImpactOS.

S0-4: Enhanced health check with DB connectivity. Workspace-scoped routers.
"""

import logging

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from src.api.compiler import router as compiler_router
from src.api.data_quality import router as data_quality_router
from src.api.depth import router as depth_router
from src.api.documents import router as documents_router
from src.api.exports import router as exports_router
from src.api.feasibility import router as feasibility_router
from src.api.governance import router as governance_router
from src.api.libraries import router as libraries_router
from src.api.metrics import router as metrics_router
from src.api.runs import models_router as engine_models_router
from src.api.runs import router as engine_ws_router
from src.api.scenarios import router as scenarios_router
from src.api.workforce import router as workforce_router
from src.config.settings import get_settings

APP_VERSION = "0.1.0"

settings = get_settings()

_LOG_NAME_TO_LEVEL: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

# --- Structured logging ---
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if settings.ENVIRONMENT == "dev"
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        _LOG_NAME_TO_LEVEL[settings.LOG_LEVEL.value],
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# --- FastAPI app ---
app = FastAPI(
    title="ImpactOS API",
    description="Impact & Scenario Intelligence System for Strategic Gears.",
    version=APP_VERSION,
)

# --- CORS middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENVIRONMENT == "dev" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Routers ---
# Global routers (not workspace-scoped)
app.include_router(engine_models_router)

# Workspace-scoped routers (all under /v1/workspaces/{workspace_id}/...)
app.include_router(compiler_router)
app.include_router(data_quality_router)
app.include_router(depth_router)
app.include_router(documents_router)
app.include_router(exports_router)
app.include_router(feasibility_router)
app.include_router(governance_router)
app.include_router(libraries_router)
app.include_router(metrics_router)
app.include_router(engine_ws_router)
app.include_router(scenarios_router)
app.include_router(workforce_router)


# --- Infrastructure Endpoints (global) ---


@app.get("/health")
async def health_check() -> dict:
    """Liveness probe with component health checks.

    S0-4: Enhanced with database connectivity check.
    Returns 200 always (degraded status if components are down).
    """
    checks: dict[str, bool] = {"api": True}

    # Database connectivity check
    try:
        from src.db.session import async_session_factory
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False

    all_ok = all(checks.values())

    return {
        "status": "ok" if all_ok else "degraded",
        "version": APP_VERSION,
        "environment": settings.ENVIRONMENT.value,
        "checks": checks,
    }


@app.get("/api/version")
async def get_version() -> dict[str, str]:
    """Return application name, version, and environment."""
    return {
        "name": "ImpactOS",
        "version": APP_VERSION,
        "environment": settings.ENVIRONMENT.value,
    }
