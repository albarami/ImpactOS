"""FastAPI export endpoints — MVP-6.

POST /v1/workspaces/{workspace_id}/exports                    — create export
GET  /v1/workspaces/{workspace_id}/exports/{export_id}        — export status
POST /v1/workspaces/{workspace_id}/exports/variance-bridge    — variance bridge

S0-4: Workspace-scoped routes. NFF claims now fetched from DB (not empty).
Deterministic — no LLM calls.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.dependencies import get_claim_repo, get_export_repo
from src.export.orchestrator import (
    ExportOrchestrator,
    ExportRequest,
)
from src.export.variance_bridge import VarianceBridge
from src.models.common import ClaimStatus, ClaimType, DisclosureTier, ExportMode
from src.models.governance import Claim
from src.repositories.exports import ExportRepository
from src.repositories.governance import ClaimRepository

router = APIRouter(prefix="/v1/workspaces", tags=["exports"])

# ---------------------------------------------------------------------------
# Stateless services (no DB needed)
# ---------------------------------------------------------------------------

_orchestrator = ExportOrchestrator()
_bridge = VarianceBridge()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateExportRequest(BaseModel):
    run_id: str
    workspace_id: str | None = None  # Optional — workspace_id from path takes precedence
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
# Helpers
# ---------------------------------------------------------------------------


def _claim_row_to_model(row) -> Claim:
    """Convert ClaimRow to Claim Pydantic model for NFF gate checks."""
    return Claim(
        claim_id=row.claim_id,
        text=row.text,
        claim_type=ClaimType(row.claim_type),
        status=ClaimStatus(row.status),
        disclosure_tier=DisclosureTier(row.disclosure_tier),
        model_refs=[],
        evidence_refs=[],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{workspace_id}/exports", status_code=201, response_model=CreateExportResponse)
async def create_export(
    workspace_id: UUID,
    body: CreateExportRequest,
    repo: ExportRepository = Depends(get_export_repo),
    claim_repo: ClaimRepository = Depends(get_claim_repo),
) -> CreateExportResponse:
    """Create a new export — generates requested formats with watermarks.

    S0-4: NFF claims now fetched from DB by run_id (not empty list).
    Governed exports will be properly blocked if claims are unresolved.
    """
    request = ExportRequest(
        run_id=UUID(body.run_id),
        workspace_id=workspace_id,
        mode=ExportMode(body.mode),
        export_formats=body.export_formats,
        pack_data=body.pack_data,
    )

    # Fetch claims associated with this run from DB for NFF gate
    claim_rows = await claim_repo.get_by_run(UUID(body.run_id))
    claims = [_claim_row_to_model(r) for r in claim_rows]

    record = _orchestrator.execute(request=request, claims=claims)

    # Persist export metadata to DB
    await repo.create(
        export_id=record.export_id,
        run_id=record.run_id,
        mode=record.mode.value,
        status=record.status.value,
        checksums_json=record.checksums,
        blocked_reasons=record.blocking_reasons,
    )

    return CreateExportResponse(
        export_id=str(record.export_id),
        status=record.status.value,
        checksums=record.checksums,
        blocking_reasons=record.blocking_reasons,
    )


@router.get("/{workspace_id}/exports/{export_id}", response_model=ExportStatusResponse)
async def get_export_status(
    workspace_id: UUID,
    export_id: UUID,
    repo: ExportRepository = Depends(get_export_repo),
) -> ExportStatusResponse:
    """Get export status and metadata."""
    row = await repo.get(export_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Export {export_id} not found.")

    return ExportStatusResponse(
        export_id=str(row.export_id),
        run_id=str(row.run_id),
        mode=row.mode,
        status=row.status,
        checksums=row.checksums_json or {},
    )


@router.post("/{workspace_id}/exports/variance-bridge", response_model=VarianceBridgeResponse)
async def variance_bridge(
    workspace_id: UUID,
    body: VarianceBridgeRequest,
) -> VarianceBridgeResponse:
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
