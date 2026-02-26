"""FastAPI export endpoints — MVP-6.

POST /v1/exports                    — create export
GET  /v1/exports/{export_id}        — export status
POST /v1/exports/variance-bridge    — variance bridge between two runs

Deterministic — no LLM calls.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.export.orchestrator import (
    ExportOrchestrator,
    ExportRecord,
    ExportRequest,
)
from src.export.variance_bridge import VarianceBridge
from src.models.common import ExportMode

router = APIRouter(prefix="/v1/exports", tags=["exports"])

# ---------------------------------------------------------------------------
# In-memory stores (MVP — replaced by PostgreSQL in production)
# ---------------------------------------------------------------------------

_orchestrator = ExportOrchestrator()
_bridge = VarianceBridge()
_export_store: dict[UUID, ExportRecord] = {}


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateExportRequest(BaseModel):
    run_id: str
    workspace_id: str
    mode: str
    export_formats: list[str]
    pack_data: dict


class CreateExportResponse(BaseModel):
    export_id: str
    status: str
    checksums: dict[str, str] = Field(default_factory=dict)
    blocking_reasons: list[str] = Field(default_factory=list)


class ExportStatusResponse(BaseModel):
    export_id: str
    run_id: str
    mode: str
    status: str
    checksums: dict[str, str] = Field(default_factory=dict)


class VarianceBridgeRequest(BaseModel):
    run_a: dict
    run_b: dict


class VarianceDriverResponse(BaseModel):
    driver_type: str
    description: str
    impact: float


class VarianceBridgeResponse(BaseModel):
    start_value: float
    end_value: float
    total_variance: float
    drivers: list[VarianceDriverResponse]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201, response_model=CreateExportResponse)
async def create_export(body: CreateExportRequest) -> CreateExportResponse:
    """Create a new export — generates requested formats with watermarks."""
    request = ExportRequest(
        run_id=UUID(body.run_id),
        workspace_id=UUID(body.workspace_id),
        mode=ExportMode(body.mode),
        export_formats=body.export_formats,
        pack_data=body.pack_data,
    )

    # For MVP, no claims lookup — sandbox always passes, governed with empty claims
    record = _orchestrator.execute(request=request, claims=[])

    _export_store[record.export_id] = record

    return CreateExportResponse(
        export_id=str(record.export_id),
        status=record.status.value,
        checksums=record.checksums,
        blocking_reasons=record.blocking_reasons,
    )


@router.get("/{export_id}", response_model=ExportStatusResponse)
async def get_export_status(export_id: UUID) -> ExportStatusResponse:
    """Get export status and metadata."""
    record = _export_store.get(export_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Export {export_id} not found.")

    return ExportStatusResponse(
        export_id=str(record.export_id),
        run_id=str(record.run_id),
        mode=record.mode.value,
        status=record.status.value,
        checksums=record.checksums,
    )


@router.post("/variance-bridge", response_model=VarianceBridgeResponse)
async def variance_bridge(body: VarianceBridgeRequest) -> VarianceBridgeResponse:
    """Compare two runs and decompose changes into drivers."""
    result = _bridge.compare(run_a=body.run_a, run_b=body.run_b)

    return VarianceBridgeResponse(
        start_value=result.start_value,
        end_value=result.end_value,
        total_variance=result.total_variance,
        drivers=[
            VarianceDriverResponse(
                driver_type=d.driver_type.value,
                description=d.description,
                impact=d.impact,
            )
            for d in result.drivers
        ],
    )
