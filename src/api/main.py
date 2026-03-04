"""FastAPI application entry point for ImpactOS.

S0-4: Enhanced health check with DB connectivity. Workspace-scoped routers.
"""

import logging

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from src.api.auth import router as auth_router
from src.api.compiler import router as compiler_router
from src.api.data_quality import router as data_quality_router
from src.api.depth import router as depth_router
from src.api.documents import router as documents_router
from src.api.exports import router as exports_router
from src.api.feasibility import router as feasibility_router
from src.api.governance import router as governance_router
from src.api.libraries import router as libraries_router
from src.api.metrics import router as metrics_router
from src.api.models import router as models_router
from src.api.path_analytics import router as path_analytics_router
from src.api.runs import models_router as engine_models_router
from src.api.runs import router as engine_ws_router
from src.api.scenarios import router as scenarios_router
from src.api.taxonomy import router as taxonomy_router
from src.api.workforce import router as workforce_router
from src.api.workspaces import router as workspaces_router
from src.config.settings import Settings, get_settings, validate_settings_for_env

APP_VERSION = "0.1.0"

settings = get_settings()


def _check_startup_config(s: Settings) -> None:
    """Validate settings at startup. Exits in non-dev if invalid."""
    errors = validate_settings_for_env(s)
    if errors:
        import sys

        for err in errors:
            logging.getLogger(__name__).critical(
                "Startup config error: %s", err,
            )
        sys.exit(1)


_check_startup_config(settings)

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

# --- CORS middleware (S0-4: reads from settings.ALLOWED_ORIGINS) ---
_cors_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Routers ---
# Global routers (not workspace-scoped)
app.include_router(auth_router)
app.include_router(engine_models_router)
app.include_router(workspaces_router)

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
app.include_router(models_router)
app.include_router(path_analytics_router)
app.include_router(engine_ws_router)
app.include_router(scenarios_router)
app.include_router(taxonomy_router)
app.include_router(workforce_router)


# --- Infrastructure Endpoints (global) ---


@app.get("/health")
async def health_check() -> dict:
    """Liveness probe with component health checks.

    Phase 0 v2: Checks API + database + Redis + object storage.
    Returns 200 always (degraded status if components are down).
    """
    import asyncio

    checks: dict[str, bool] = {"api": True}

    async def _check_database() -> bool:
        try:
            from src.db.session import async_session_factory
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def _check_redis() -> bool:
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
            await r.ping()
            await r.aclose()
            return True
        except Exception:
            return False

    async def _check_object_storage() -> bool:
        try:
            from pathlib import Path
            storage_path = Path(settings.OBJECT_STORAGE_PATH)
            return storage_path.exists() and storage_path.is_dir()
        except Exception:
            return False

    db_ok, redis_ok, storage_ok = await asyncio.gather(
        _check_database(),
        _check_redis(),
        _check_object_storage(),
    )

    checks["database"] = db_ok
    checks["redis"] = redis_ok
    checks["object_storage"] = storage_ok

    all_ok = all(checks.values())

    return {
        "status": "ok" if all_ok else "degraded",
        "version": APP_VERSION,
        "environment": settings.ENVIRONMENT.value,
        "checks": checks,
    }


@app.get("/readiness")
async def readiness_check() -> dict:
    """Readiness probe — gates traffic until critical deps are up.

    Returns 200 when all critical dependencies (database) are healthy.
    Returns 503 when any critical dependency is unavailable.
    Non-critical deps (Redis, object storage) are reported but don't
    block readiness.
    """
    import asyncio

    from starlette.responses import JSONResponse

    checks: dict[str, bool] = {}

    async def _check_database() -> bool:
        try:
            from src.db.session import async_session_factory

            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def _check_redis() -> bool:
        try:
            import redis.asyncio as aioredis

            r = aioredis.from_url(
                settings.REDIS_URL, socket_connect_timeout=2,
            )
            await r.ping()
            await r.aclose()
            return True
        except Exception:
            return False

    db_ok, redis_ok = await asyncio.gather(
        _check_database(), _check_redis(),
    )
    checks["database"] = db_ok
    checks["redis"] = redis_ok

    ready = db_ok  # database is the critical gate

    status_code = 200 if ready else 503
    return JSONResponse(
        content={
            "ready": ready,
            "checks": checks,
            "environment": settings.ENVIRONMENT.value,
        },
        status_code=status_code,
    )


@app.get("/api/version")
async def get_version() -> dict[str, str]:
    """Return application name, version, and environment."""
    return {
        "name": "ImpactOS",
        "version": APP_VERSION,
        "environment": settings.ENVIRONMENT.value,
    }
