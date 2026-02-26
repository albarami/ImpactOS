"""FastAPI application entry point for ImpactOS."""

import logging

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.documents import router as documents_router
from src.api.exports import router as exports_router
from src.api.governance import router as governance_router
from src.api.metrics import router as metrics_router
from src.api.runs import router as runs_router
from src.api.scenarios import router as scenarios_router
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
app.include_router(documents_router)
app.include_router(exports_router)
app.include_router(governance_router)
app.include_router(metrics_router)
app.include_router(runs_router)
app.include_router(scenarios_router)


# --- Endpoints ---


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Lightweight liveness probe."""
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT.value,
    }


@app.get("/api/version")
async def get_version() -> dict[str, str]:
    """Return application name, version, and environment."""
    return {
        "name": "ImpactOS",
        "version": APP_VERSION,
        "environment": settings.ENVIRONMENT.value,
    }
