"""FastAPI export endpoints — MVP-6 + B-12 download.

POST /v1/workspaces/{workspace_id}/exports                                — create export
GET  /v1/workspaces/{workspace_id}/exports/{export_id}                    — export status
GET  /v1/workspaces/{workspace_id}/exports/{export_id}/download/{format}  — download artifact (B-12)
POST /v1/workspaces/{workspace_id}/exports/variance-bridge                — variance bridge
POST /v1/workspaces/{workspace_id}/variance-bridges                       — compute+persist bridge (S23)
GET  /v1/workspaces/{workspace_id}/variance-bridges/{analysis_id}         — get bridge analysis (S23)
GET  /v1/workspaces/{workspace_id}/variance-bridges                       — list bridge analyses (S23)

S0-4: Workspace-scoped routes. NFF claims now fetched from DB (not empty).
Deterministic — no LLM calls.
"""

import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.api.auth_deps import (
    WorkspaceMember,
    require_role,
    require_workspace_member,
)
from src.api.dependencies import (
    get_claim_repo,
    get_data_quality_repo,
    get_export_artifact_storage,
    get_export_repo,
    get_model_version_repo,
    get_result_set_repo,
    get_run_snapshot_repo,
    get_scenario_version_repo,
    get_variance_bridge_repo,
)
from src.api.runs import ALLOWED_RUNTIME_PROVENANCE
from src.export.artifact_storage import ExportArtifactStorage
from src.export.orchestrator import ExportOrchestrator, ExportRequest
from src.export.variance_bridge import AdvancedVarianceBridge, VarianceBridge
from src.models.common import ClaimStatus, ClaimType, DisclosureTier, ExportMode
from src.models.export import BridgeReasonCode, VarianceBridgeAnalysis
from src.models.governance import Claim
from src.quality.models import RunQualityAssessment
from src.repositories.data_quality import DataQualityRepository
from src.repositories.engine import (
    ModelVersionRepository,
    ResultSetRepository,
    RunSnapshotRepository,
)
from src.repositories.exports import ExportRepository, VarianceBridgeRepository
from src.repositories.governance import ClaimRepository
from src.repositories.scenarios import ScenarioVersionRepository

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


# Sprint 23: Advanced variance bridge request/response schemas


class CreateBridgeRequest(BaseModel):
    """Request to compute and persist a variance bridge."""
    run_a_id: UUID
    run_b_id: UUID
    metric_type: str = Field(default="total_output", min_length=1, max_length=100)


class BridgeDriverResponse(BaseModel):
    """Single driver in a bridge analysis response."""
    driver_type: str
    description: str
    impact: float
    raw_magnitude: float
    weight: float
    source_field: str | None = None
    diff_summary: str | None = None


class BridgeAnalysisResponse(BaseModel):
    """Full bridge analysis response."""
    analysis_id: str
    workspace_id: str
    run_a_id: str
    run_b_id: str
    metric_type: str
    analysis_version: str
    start_value: float
    end_value: float
    total_variance: float
    drivers: list[BridgeDriverResponse]
    config_hash: str
    result_checksum: str
    created_at: str


class BridgeErrorDetail(BaseModel):
    """Structured error response for bridge failures."""
    reason_code: str
    message: str


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
# Helpers
# ---------------------------------------------------------------------------


async def _check_model_provenance(
    run_id: UUID, snap_repo, mv_repo,
) -> bool:
    """Check if the run's model has disallowed provenance.

    Returns True if provenance_class is NOT in ALLOWED_RUNTIME_PROVENANCE.
    """
    snap_row = await snap_repo.get(run_id)
    if snap_row is None:
        return True
    mv_row = await mv_repo.get(snap_row.model_version_id)
    if mv_row is None:
        return True
    prov = getattr(mv_row, "provenance_class", "unknown")
    return prov not in ALLOWED_RUNTIME_PROVENANCE


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{workspace_id}/exports", status_code=201, response_model=CreateExportResponse)
async def create_export(
    workspace_id: UUID,
    body: CreateExportRequest,
    member: WorkspaceMember = Depends(require_role("manager", "admin")),
    repo: ExportRepository = Depends(get_export_repo),
    claim_repo: ClaimRepository = Depends(get_claim_repo),
    quality_repo: DataQualityRepository = Depends(get_data_quality_repo),
    artifact_store: ExportArtifactStorage = Depends(get_export_artifact_storage),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    mv_repo: ModelVersionRepository = Depends(get_model_version_repo),
) -> CreateExportResponse:
    """Create a new export — generates requested formats with watermarks.

    D-5.1: Computes effective_used_synthetic from quality payload AND
    model provenance_class. Does not trust quality payload alone.
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
            quality_assessment = RunQualityAssessment.model_validate(
                quality_row.payload,
            )
        except Exception:
            pass

    model_provenance_disallowed = await _check_model_provenance(
        UUID(body.run_id), snap_repo, mv_repo,
    )

    record = _orchestrator.execute(
        request=request,
        claims=claims,
        quality_assessment=quality_assessment,
        model_provenance_disallowed=model_provenance_disallowed,
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
    member: WorkspaceMember = Depends(require_workspace_member),
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
    member: WorkspaceMember = Depends(require_role("manager", "admin")),
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
    member: WorkspaceMember = Depends(require_workspace_member),
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


def _scenario_row_to_bridge_dict(row: "ScenarioSpecRow") -> dict:
    """Convert ScenarioSpecRow to dict for bridge engine spec comparison."""
    return {
        "time_horizon": row.time_horizon if isinstance(row.time_horizon, dict) else {},
        "shock_items": row.shock_items if isinstance(row.shock_items, list) else [],
    }


def _snapshot_to_dict(snap: "RunSnapshotRow") -> dict:
    """Extract all version-ID fields from a snapshot for bridge attribution.

    Includes all artifact-version fields for forward-compatibility with
    future driver categories beyond the current 7.
    """
    def _str_or_none(val: object) -> str | None:
        return str(val) if val is not None else None

    return {
        "model_version_id": _str_or_none(snap.model_version_id),
        "taxonomy_version_id": _str_or_none(getattr(snap, "taxonomy_version_id", None)),
        "concordance_version_id": _str_or_none(
            getattr(snap, "concordance_version_id", None)
        ),
        "mapping_library_version_id": _str_or_none(snap.mapping_library_version_id),
        "assumption_library_version_id": _str_or_none(
            getattr(snap, "assumption_library_version_id", None)
        ),
        "prompt_pack_version_id": _str_or_none(
            getattr(snap, "prompt_pack_version_id", None)
        ),
        "constraint_set_version_id": _str_or_none(snap.constraint_set_version_id),
    }


# ---------------------------------------------------------------------------
# Sprint 23: Variance Bridge Analytics (additive)
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/variance-bridges",
    status_code=201,
    response_model=BridgeAnalysisResponse,
)
async def create_variance_bridge(
    workspace_id: UUID,
    body: CreateBridgeRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    bridge_repo: VarianceBridgeRepository = Depends(get_variance_bridge_repo),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    result_repo: ResultSetRepository = Depends(get_result_set_repo),
    scenario_repo: ScenarioVersionRepository = Depends(get_scenario_version_repo),
) -> BridgeAnalysisResponse:
    """Compute + persist a variance bridge between two runs.

    Directional: A->B is different from B->A.
    Idempotent: same config_hash returns existing analysis.
    """
    # Validate: same run_id
    if body.run_a_id == body.run_b_id:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": BridgeReasonCode.BRIDGE_SAME_RUN,
                "message": "Cannot compare a run with itself",
            },
        )

    # Fetch run snapshots (workspace-scoped: returns None if wrong workspace)
    snap_a = await snap_repo.get(body.run_a_id)
    if snap_a is None or (snap_a.workspace_id and snap_a.workspace_id != workspace_id):
        raise HTTPException(
            status_code=404,
            detail={
                "reason_code": BridgeReasonCode.BRIDGE_RUN_NOT_FOUND,
                "message": f"Run {body.run_a_id} not found in workspace",
            },
        )

    snap_b = await snap_repo.get(body.run_b_id)
    if snap_b is None or (snap_b.workspace_id and snap_b.workspace_id != workspace_id):
        raise HTTPException(
            status_code=404,
            detail={
                "reason_code": BridgeReasonCode.BRIDGE_RUN_NOT_FOUND,
                "message": f"Run {body.run_b_id} not found in workspace",
            },
        )

    # Fetch result sets
    results_a = await result_repo.get_by_run(body.run_a_id)
    result_a = next((r for r in results_a if r.metric_type == body.metric_type), None)
    if result_a is None:
        raise HTTPException(
            status_code=404,
            detail={
                "reason_code": BridgeReasonCode.BRIDGE_NO_RESULTS,
                "message": f"No {body.metric_type} result for run {body.run_a_id}",
            },
        )

    results_b = await result_repo.get_by_run(body.run_b_id)
    result_b = next((r for r in results_b if r.metric_type == body.metric_type), None)
    if result_b is None:
        raise HTTPException(
            status_code=404,
            detail={
                "reason_code": BridgeReasonCode.BRIDGE_NO_RESULTS,
                "message": f"No {body.metric_type} result for run {body.run_b_id}",
            },
        )

    # Build artifact dicts for engine (include all version fields for
    # forward-compatibility with future driver categories)
    snap_a_dict = _snapshot_to_dict(snap_a)
    snap_b_dict = _snapshot_to_dict(snap_b)

    result_a_dict = {
        "values": result_a.values if isinstance(result_a.values, dict) else {},
    }
    result_b_dict = {
        "values": result_b.values if isinstance(result_b.values, dict) else {},
    }

    # I-2: Fetch ScenarioSpec for PHASING/IMPORT_SHARE/FEASIBILITY detection
    spec_a_dict: dict | None = None
    spec_b_dict: dict | None = None
    if getattr(snap_a, "scenario_spec_id", None):
        spec_row_a = await scenario_repo.get_by_id_and_version(
            snap_a.scenario_spec_id,
            snap_a.scenario_spec_version or 1,
        )
        if spec_row_a:
            spec_a_dict = _scenario_row_to_bridge_dict(spec_row_a)
    if getattr(snap_b, "scenario_spec_id", None):
        spec_row_b = await scenario_repo.get_by_id_and_version(
            snap_b.scenario_spec_id,
            snap_b.scenario_spec_version or 1,
        )
        if spec_row_b:
            spec_b_dict = _scenario_row_to_bridge_dict(spec_row_b)

    # Compute bridge
    bridge_result = AdvancedVarianceBridge.compute_from_artifacts(
        run_a_snapshot=snap_a_dict,
        run_b_snapshot=snap_b_dict,
        result_a=result_a_dict,
        result_b=result_b_dict,
        spec_a=spec_a_dict,
        spec_b=spec_b_dict,
    )

    # Build config for persistence (directional -- no sorting!)
    config = {
        "workspace_id": str(workspace_id),
        "run_a_id": str(body.run_a_id),
        "run_b_id": str(body.run_b_id),
        "metric_type": body.metric_type,
        "analysis_version": "bridge_v1",
    }
    config_hash = "sha256:" + hashlib.sha256(
        json.dumps(config, sort_keys=True).encode()
    ).hexdigest()

    # Build result JSON
    result_json = {
        "start_value": bridge_result.start_value,
        "end_value": bridge_result.end_value,
        "total_variance": bridge_result.total_variance,
        "drivers": [
            {
                "driver_type": d.driver_type.value,
                "description": d.description,
                "impact": d.impact,
                "raw_magnitude": d.raw_magnitude,
                "weight": d.weight,
                "source_field": d.source_field,
                "diff_summary": d.diff_summary,
            }
            for d in bridge_result.drivers
        ],
        "diagnostics": {
            "checksum": bridge_result.diagnostics.checksum,
            "tolerance_used": bridge_result.diagnostics.tolerance_used,
            "identity_verified": bridge_result.diagnostics.identity_verified,
        },
    }

    # Persist (idempotent by config_hash)
    analysis = VarianceBridgeAnalysis(
        workspace_id=workspace_id,
        run_a_id=body.run_a_id,
        run_b_id=body.run_b_id,
        metric_type=body.metric_type,
        config_json=config,
        config_hash=config_hash,
        result_json=result_json,
        result_checksum=bridge_result.diagnostics.checksum,
    )
    saved = await bridge_repo.create(analysis)

    return _bridge_to_response(saved, result_json)


@router.get(
    "/{workspace_id}/variance-bridges/{analysis_id}",
    response_model=BridgeAnalysisResponse,
)
async def get_variance_bridge_analysis(
    workspace_id: UUID,
    analysis_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    bridge_repo: VarianceBridgeRepository = Depends(get_variance_bridge_repo),
) -> BridgeAnalysisResponse:
    """Get a single variance bridge analysis."""
    analysis = await bridge_repo.get(workspace_id, analysis_id)
    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail={
                "reason_code": BridgeReasonCode.BRIDGE_NOT_FOUND,
                "message": "Bridge analysis not found",
            },
        )
    return _bridge_to_response(analysis, analysis.result_json)


@router.get(
    "/{workspace_id}/variance-bridges",
    response_model=list[BridgeAnalysisResponse],
)
async def list_variance_bridges(
    workspace_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    bridge_repo: VarianceBridgeRepository = Depends(get_variance_bridge_repo),
    limit: int = 50,
    offset: int = 0,
) -> list[BridgeAnalysisResponse]:
    """List variance bridges for a workspace."""
    analyses = await bridge_repo.list_for_workspace(
        workspace_id, limit=limit, offset=offset,
    )
    return [_bridge_to_response(a, a.result_json) for a in analyses]


def _bridge_to_response(
    analysis: VarianceBridgeAnalysis,
    result_json: dict,
) -> BridgeAnalysisResponse:
    """Convert persisted analysis + result JSON to API response."""
    drivers = result_json.get("drivers", [])
    return BridgeAnalysisResponse(
        analysis_id=str(analysis.analysis_id),
        workspace_id=str(analysis.workspace_id),
        run_a_id=str(analysis.run_a_id),
        run_b_id=str(analysis.run_b_id),
        metric_type=analysis.metric_type,
        analysis_version=analysis.analysis_version,
        start_value=result_json.get("start_value", 0.0),
        end_value=result_json.get("end_value", 0.0),
        total_variance=result_json.get("total_variance", 0.0),
        drivers=[
            BridgeDriverResponse(
                driver_type=d["driver_type"],
                description=d["description"],
                impact=d["impact"],
                raw_magnitude=d.get("raw_magnitude", 0.0),
                weight=d.get("weight", 0.0),
                source_field=d.get("source_field"),
                diff_summary=d.get("diff_summary"),
            )
            for d in drivers
        ],
        config_hash=analysis.config_hash,
        result_checksum=analysis.result_checksum,
        created_at=str(analysis.created_at),
    )
