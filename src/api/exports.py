"""FastAPI export endpoints — MVP-6 + B-12 download.

POST /v1/workspaces/{workspace_id}/exports                                — create export
GET  /v1/workspaces/{workspace_id}/exports/{export_id}                    — export status
GET  /v1/workspaces/{workspace_id}/exports/{export_id}/download/{format}  — download artifact (B-12)
POST /v1/workspaces/{workspace_id}/exports/variance-bridge                — variance bridge

S0-4: Workspace-scoped routes. NFF claims now fetched from DB (not empty).
Deterministic — no LLM calls.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.api.dependencies import (
    get_claim_repo,
    get_data_quality_repo,
    get_export_artifact_storage,
    get_export_repo,
)
from src.export.artifact_storage import ExportArtifactStorage
from src.export.orchestrator import (
    ExportOrchestrator,
    ExportRequest,
)
from src.quality.models import RunQualityAssessment
from src.repositories.data_quality import DataQualityRepository
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

_DOWNLOAD_NON_READY = frozenset({"BLOCKED", "FAILED", "PENDING", "GENERATING"})

_FORMAT_MIME: dict[str, str] = {
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

_FORMAT_EXT: dict[str, str] = {
    "excel": "xlsx",
    "pptx": "pptx",
}


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
    quality_repo: DataQualityRepository = Depends(get_data_quality_repo),
    artifact_store: ExportArtifactStorage = Depends(get_export_artifact_storage),
) -> CreateExportResponse:
    """Create a new export — generates requested formats with watermarks.

    S0-4: NFF claims now fetched from DB by run_id (not empty list).
    B-12: Artifact bytes are persisted to object storage at creation time.
    """
    request = ExportRequest(
        run_id=UUID(body.run_id),
        workspace_id=workspace_id,
        mode=ExportMode(body.mode),
        export_formats=body.export_formats,
        pack_data=body.pack_data,
    )

    claim_rows = await claim_repo.get_by_run(UUID(body.run_id))
    claims = [_claim_row_to_model(r) for r in claim_rows]

    quality_assessment: RunQualityAssessment | None = None
    quality_row = await quality_repo.get_by_run(UUID(body.run_id))
    if quality_row is not None and quality_row.payload:
        try:
            quality_assessment = RunQualityAssessment.model_validate(quality_row.payload)
        except Exception:
            pass

    record = _orchestrator.execute(
        request=request,
        claims=claims,
        quality_assessment=quality_assessment,
    )

    artifact_refs: dict[str, str] = {}
    if record.artifacts:
        for fmt, data in record.artifacts.items():
            key = ExportArtifactStorage.build_key(str(record.export_id), fmt)
            artifact_store.store(key, data)
            artifact_refs[fmt] = key

    await repo.create(
        export_id=record.export_id,
        run_id=record.run_id,
        mode=record.mode.value,
        status=record.status.value,
        checksums_json=record.checksums,
        blocked_reasons=record.blocking_reasons,
        artifact_refs_json=artifact_refs or None,
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
    """Get export status and metadata (workspace-scoped via run linkage)."""
    row = await repo.get_for_workspace(export_id, workspace_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Export {export_id} not found.")

    return ExportStatusResponse(
        export_id=str(row.export_id),
        run_id=str(row.run_id),
        mode=row.mode,
        status=row.status,
        checksums=row.checksums_json or {},
    )


@router.get("/{workspace_id}/exports/{export_id}/download/{format}")
async def download_export_artifact(
    workspace_id: UUID,
    export_id: UUID,
    format: str,
    repo: ExportRepository = Depends(get_export_repo),
    artifact_store: ExportArtifactStorage = Depends(get_export_artifact_storage),
) -> Response:
    """B-12: Download a persisted export artifact by format (excel/pptx).

    Returns the raw bytes with correct MIME type and Content-Disposition.
    """
    row = await repo.get_for_workspace(export_id, workspace_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Export {export_id} not found.")

    if row.status in _DOWNLOAD_NON_READY:
        raise HTTPException(
            status_code=409,
            detail=f"Export {export_id} is not ready for download (status={row.status}).",
        )

    artifact_refs: dict = row.artifact_refs_json or {}
    storage_key = artifact_refs.get(format)
    if not storage_key:
        raise HTTPException(
            status_code=404,
            detail=f"No artifact for format '{format}' on export {export_id}.",
        )

    try:
        data = artifact_store.retrieve(storage_key)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Artifact file missing for export {export_id} format '{format}'.",
        )

    mime = _FORMAT_MIME.get(format, "application/octet-stream")
    ext = _FORMAT_EXT.get(format, format)
    filename = f"export_{export_id}.{ext}"

    return Response(
        content=data,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
