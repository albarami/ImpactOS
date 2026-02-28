"""FastAPI workforce endpoints — MVP-11.

POST /{workspace_id}/employment-coefficients            — create coefficients
GET  /{workspace_id}/employment-coefficients            — list by workspace
GET  /{workspace_id}/employment-coefficients/{id}       — get (latest or ?version=N)
POST /{workspace_id}/occupation-bridge                  — create bridge
GET  /{workspace_id}/occupation-bridge                  — list by workspace
GET  /{workspace_id}/occupation-bridge/{id}             — get (latest or ?version=N)
POST /{workspace_id}/saudization-rules                  — create rules
GET  /{workspace_id}/saudization-rules                  — list by workspace
GET  /{workspace_id}/saudization-rules/{id}             — get (latest or ?version=N)
POST /{workspace_id}/runs/{run_id}/workforce            — compute workforce impact
GET  /{workspace_id}/runs/{run_id}/workforce            — get workforce results

Workspace-scoped routes. Deterministic engine code only (no LLM).

All 9 amendments enforced.
"""

import logging
from uuid import UUID

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.dependencies import (
    get_employment_coefficients_repo,
    get_feasibility_result_repo,
    get_model_data_repo,
    get_result_set_repo,
    get_run_snapshot_repo,
    get_saudization_rules_repo,
    get_sector_occupation_bridge_repo,
    get_workforce_result_repo,
)
from src.engine.workforce import compute_workforce_impact
from src.models.common import new_uuid7
from src.models.workforce import (
    EmploymentCoefficients,
    SaudizationRules,
    SectorOccupationBridge,
)
from src.repositories.engine import (
    ModelDataRepository,
    ResultSetRepository,
    RunSnapshotRepository,
)
from src.repositories.feasibility import FeasibilityResultRepository
from src.repositories.workforce import (
    EmploymentCoefficientsRepository,
    SaudizationRulesRepository,
    SectorOccupationBridgeRepository,
    WorkforceResultRepository,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/workspaces", tags=["workforce"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateEmploymentCoefficientsRequest(BaseModel):
    model_version_id: str
    output_unit: str
    base_year: int
    coefficients: list[dict] = Field(default_factory=list)
    employment_coefficients_id: str | None = None  # For creating new versions


class EmploymentCoefficientsResponse(BaseModel):
    employment_coefficients_id: str
    version: int
    workspace_id: str
    model_version_id: str
    output_unit: str
    base_year: int
    coefficients: list[dict]
    created_at: str


class CreateOccupationBridgeRequest(BaseModel):
    model_version_id: str
    entries: list[dict] = Field(default_factory=list)
    bridge_id: str | None = None


class OccupationBridgeResponse(BaseModel):
    bridge_id: str
    version: int
    workspace_id: str
    model_version_id: str
    entries: list[dict]
    created_at: str


class CreateSaudizationRulesRequest(BaseModel):
    tier_assignments: list[dict] = Field(default_factory=list)
    sector_targets: list[dict] = Field(default_factory=list)
    rules_id: str | None = None


class SaudizationRulesResponse(BaseModel):
    rules_id: str
    version: int
    workspace_id: str
    tier_assignments: list[dict]
    sector_targets: list[dict]
    created_at: str


class ComputeWorkforceRequest(BaseModel):
    employment_coefficients_id: str
    employment_coefficients_version: int | None = None  # None = latest
    bridge_id: str | None = None
    bridge_version: int | None = None
    rules_id: str | None = None
    rules_version: int | None = None
    feasibility_result_id: str | None = None  # Amendment 1


class WorkforceResultResponse(BaseModel):
    workforce_result_id: str
    run_id: str
    workspace_id: str
    sector_employment: dict
    occupation_breakdowns: dict
    nationality_splits: dict
    saudization_gaps: dict
    sensitivity_envelopes: dict
    confidence_summary: dict
    employment_coefficients_id: str
    employment_coefficients_version: int
    bridge_id: str | None = None
    bridge_version: int | None = None
    rules_id: str | None = None
    rules_version: int | None = None
    satellite_coefficients_hash: str
    data_quality_notes: list[str]
    delta_x_source: str
    feasibility_result_id: str | None = None
    delta_x_unit: str
    coefficient_unit: str


# ---------------------------------------------------------------------------
# Employment Coefficients endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/employment-coefficients",
    status_code=201,
    response_model=EmploymentCoefficientsResponse,
)
async def create_employment_coefficients(
    workspace_id: UUID,
    body: CreateEmploymentCoefficientsRequest,
    repo: EmploymentCoefficientsRepository = Depends(get_employment_coefficients_repo),
) -> EmploymentCoefficientsResponse:
    """Create employment coefficients (or new version of existing)."""
    model_version_id = UUID(body.model_version_id)

    if body.employment_coefficients_id:
        ec_id = UUID(body.employment_coefficients_id)
        latest = await repo.get_latest(ec_id)
        version = (latest.version + 1) if latest else 1
    else:
        ec_id = new_uuid7()
        version = 1

    row = await repo.create(
        employment_coefficients_id=ec_id,
        version=version,
        model_version_id=model_version_id,
        workspace_id=workspace_id,
        output_unit=body.output_unit,
        base_year=body.base_year,
        coefficients=body.coefficients,
    )

    return EmploymentCoefficientsResponse(
        employment_coefficients_id=str(row.employment_coefficients_id),
        version=row.version,
        workspace_id=str(row.workspace_id),
        model_version_id=str(row.model_version_id),
        output_unit=row.output_unit,
        base_year=row.base_year,
        coefficients=row.coefficients,
        created_at=str(row.created_at),
    )


@router.get(
    "/{workspace_id}/employment-coefficients",
    response_model=list[EmploymentCoefficientsResponse],
)
async def list_employment_coefficients(
    workspace_id: UUID,
    repo: EmploymentCoefficientsRepository = Depends(get_employment_coefficients_repo),
) -> list[EmploymentCoefficientsResponse]:
    """List all employment coefficients for a workspace."""
    rows = await repo.get_by_workspace(workspace_id)
    return [
        EmploymentCoefficientsResponse(
            employment_coefficients_id=str(r.employment_coefficients_id),
            version=r.version,
            workspace_id=str(r.workspace_id),
            model_version_id=str(r.model_version_id),
            output_unit=r.output_unit,
            base_year=r.base_year,
            coefficients=r.coefficients,
            created_at=str(r.created_at),
        )
        for r in rows
    ]


@router.get(
    "/{workspace_id}/employment-coefficients/{employment_coefficients_id}",
    response_model=EmploymentCoefficientsResponse,
)
async def get_employment_coefficients(
    workspace_id: UUID,
    employment_coefficients_id: UUID,
    version: int | None = Query(default=None),
    repo: EmploymentCoefficientsRepository = Depends(get_employment_coefficients_repo),
) -> EmploymentCoefficientsResponse:
    """Get employment coefficients (latest or specific version)."""
    if version is not None:
        row = await repo.get(employment_coefficients_id, version)
    else:
        row = await repo.get_latest(employment_coefficients_id)

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Employment coefficients {employment_coefficients_id} not found.",
        )

    return EmploymentCoefficientsResponse(
        employment_coefficients_id=str(row.employment_coefficients_id),
        version=row.version,
        workspace_id=str(row.workspace_id),
        model_version_id=str(row.model_version_id),
        output_unit=row.output_unit,
        base_year=row.base_year,
        coefficients=row.coefficients,
        created_at=str(row.created_at),
    )


# ---------------------------------------------------------------------------
# Occupation Bridge endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/occupation-bridge",
    status_code=201,
    response_model=OccupationBridgeResponse,
)
async def create_occupation_bridge(
    workspace_id: UUID,
    body: CreateOccupationBridgeRequest,
    repo: SectorOccupationBridgeRepository = Depends(get_sector_occupation_bridge_repo),
) -> OccupationBridgeResponse:
    """Create sector-occupation bridge (or new version)."""
    model_version_id = UUID(body.model_version_id)

    if body.bridge_id:
        bridge_id = UUID(body.bridge_id)
        latest = await repo.get_latest(bridge_id)
        version = (latest.version + 1) if latest else 1
    else:
        bridge_id = new_uuid7()
        version = 1

    row = await repo.create(
        bridge_id=bridge_id,
        version=version,
        model_version_id=model_version_id,
        workspace_id=workspace_id,
        entries=body.entries,
    )

    return OccupationBridgeResponse(
        bridge_id=str(row.bridge_id),
        version=row.version,
        workspace_id=str(row.workspace_id),
        model_version_id=str(row.model_version_id),
        entries=row.entries,
        created_at=str(row.created_at),
    )


@router.get(
    "/{workspace_id}/occupation-bridge",
    response_model=list[OccupationBridgeResponse],
)
async def list_occupation_bridges(
    workspace_id: UUID,
    repo: SectorOccupationBridgeRepository = Depends(get_sector_occupation_bridge_repo),
) -> list[OccupationBridgeResponse]:
    """List all occupation bridges for a workspace."""
    rows = await repo.get_by_workspace(workspace_id)
    return [
        OccupationBridgeResponse(
            bridge_id=str(r.bridge_id),
            version=r.version,
            workspace_id=str(r.workspace_id),
            model_version_id=str(r.model_version_id),
            entries=r.entries,
            created_at=str(r.created_at),
        )
        for r in rows
    ]


@router.get(
    "/{workspace_id}/occupation-bridge/{bridge_id}",
    response_model=OccupationBridgeResponse,
)
async def get_occupation_bridge(
    workspace_id: UUID,
    bridge_id: UUID,
    version: int | None = Query(default=None),
    repo: SectorOccupationBridgeRepository = Depends(get_sector_occupation_bridge_repo),
) -> OccupationBridgeResponse:
    """Get occupation bridge (latest or specific version)."""
    if version is not None:
        row = await repo.get(bridge_id, version)
    else:
        row = await repo.get_latest(bridge_id)

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Occupation bridge {bridge_id} not found.",
        )

    return OccupationBridgeResponse(
        bridge_id=str(row.bridge_id),
        version=row.version,
        workspace_id=str(row.workspace_id),
        model_version_id=str(row.model_version_id),
        entries=row.entries,
        created_at=str(row.created_at),
    )


# ---------------------------------------------------------------------------
# Saudization Rules endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/saudization-rules",
    status_code=201,
    response_model=SaudizationRulesResponse,
)
async def create_saudization_rules(
    workspace_id: UUID,
    body: CreateSaudizationRulesRequest,
    repo: SaudizationRulesRepository = Depends(get_saudization_rules_repo),
) -> SaudizationRulesResponse:
    """Create saudization rules (or new version)."""
    if body.rules_id:
        rules_id = UUID(body.rules_id)
        latest = await repo.get_latest(rules_id)
        version = (latest.version + 1) if latest else 1
    else:
        rules_id = new_uuid7()
        version = 1

    row = await repo.create(
        rules_id=rules_id,
        version=version,
        workspace_id=workspace_id,
        tier_assignments=body.tier_assignments,
        sector_targets=body.sector_targets,
    )

    return SaudizationRulesResponse(
        rules_id=str(row.rules_id),
        version=row.version,
        workspace_id=str(row.workspace_id),
        tier_assignments=row.tier_assignments,
        sector_targets=row.sector_targets,
        created_at=str(row.created_at),
    )


@router.get(
    "/{workspace_id}/saudization-rules",
    response_model=list[SaudizationRulesResponse],
)
async def list_saudization_rules(
    workspace_id: UUID,
    repo: SaudizationRulesRepository = Depends(get_saudization_rules_repo),
) -> list[SaudizationRulesResponse]:
    """List all saudization rules for a workspace."""
    rows = await repo.get_by_workspace(workspace_id)
    return [
        SaudizationRulesResponse(
            rules_id=str(r.rules_id),
            version=r.version,
            workspace_id=str(r.workspace_id),
            tier_assignments=r.tier_assignments,
            sector_targets=r.sector_targets,
            created_at=str(r.created_at),
        )
        for r in rows
    ]


@router.get(
    "/{workspace_id}/saudization-rules/{rules_id}",
    response_model=SaudizationRulesResponse,
)
async def get_saudization_rules(
    workspace_id: UUID,
    rules_id: UUID,
    version: int | None = Query(default=None),
    repo: SaudizationRulesRepository = Depends(get_saudization_rules_repo),
) -> SaudizationRulesResponse:
    """Get saudization rules (latest or specific version)."""
    if version is not None:
        row = await repo.get(rules_id, version)
    else:
        row = await repo.get_latest(rules_id)

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Saudization rules {rules_id} not found.",
        )

    return SaudizationRulesResponse(
        rules_id=str(row.rules_id),
        version=row.version,
        workspace_id=str(row.workspace_id),
        tier_assignments=row.tier_assignments,
        sector_targets=row.sector_targets,
        created_at=str(row.created_at),
    )


# ---------------------------------------------------------------------------
# Compute Workforce Impact
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/runs/{run_id}/workforce",
    response_model=WorkforceResultResponse,
)
async def compute_workforce(
    workspace_id: UUID,
    run_id: UUID,
    body: ComputeWorkforceRequest,
    ec_repo: EmploymentCoefficientsRepository = Depends(get_employment_coefficients_repo),
    bridge_repo: SectorOccupationBridgeRepository = Depends(get_sector_occupation_bridge_repo),
    rules_repo: SaudizationRulesRepository = Depends(get_saudization_rules_repo),
    result_repo: WorkforceResultRepository = Depends(get_workforce_result_repo),
    run_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    result_set_repo: ResultSetRepository = Depends(get_result_set_repo),
    model_data_repo: ModelDataRepository = Depends(get_model_data_repo),
    feas_repo: FeasibilityResultRepository = Depends(get_feasibility_result_repo),
) -> WorkforceResultResponse:
    """Compute workforce impact for a run.

    Amendment 1: Accepts optional feasibility_result_id for feasible delta_x.
    Amendment 2: Unit normalization.
    Amendment 9: Idempotency — returns existing result if same inputs.
    """
    ec_id = UUID(body.employment_coefficients_id)

    # 1. Load run snapshot
    run_snapshot = await run_repo.get(run_id)
    if run_snapshot is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")

    # 2. Load employment coefficients
    if body.employment_coefficients_version is not None:
        ec_row = await ec_repo.get(ec_id, body.employment_coefficients_version)
    else:
        ec_row = await ec_repo.get_latest(ec_id)

    if ec_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Employment coefficients {ec_id} not found.",
        )

    # Model version compatibility check
    if ec_row.model_version_id != run_snapshot.model_version_id:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Model version mismatch: coefficients use "
                f"{ec_row.model_version_id} but run uses "
                f"{run_snapshot.model_version_id}."
            ),
        )

    # 3. Determine delta_x source (Amendment 1)
    delta_x_source = "unconstrained"
    feasibility_result_id = None

    if body.feasibility_result_id:
        feas_id = UUID(body.feasibility_result_id)
        feas_row = await feas_repo.get(feas_id)
        if feas_row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Feasibility result {feas_id} not found.",
            )
        if feas_row.unconstrained_run_id != run_id:
            raise HTTPException(
                status_code=422,
                detail="Feasibility result does not reference this run.",
            )
        delta_x_source = "feasible"
        feasibility_result_id = feas_id

    # 4. Amendment 9: Idempotency check
    existing = await result_repo.get_existing(
        run_id=run_id,
        employment_coefficients_id=ec_row.employment_coefficients_id,
        employment_coefficients_version=ec_row.version,
        delta_x_source=delta_x_source,
    )
    if existing is not None:
        return _row_to_response(existing)

    # 5. Load model data for sector codes
    model_data = await model_data_repo.get(run_snapshot.model_version_id)
    if model_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model data for {run_snapshot.model_version_id} not found.",
        )
    sector_codes: list[str] = model_data.sector_codes

    # 6. Load delta_x values
    if delta_x_source == "feasible" and body.feasibility_result_id:
        feas_id = UUID(body.feasibility_result_id)
        feas_row = await feas_repo.get(feas_id)
        total_dict = feas_row.feasible_delta_x
        # For feasible, direct/indirect are approximated proportionally
        direct_dict = total_dict
        indirect_dict = {sc: 0.0 for sc in sector_codes}
    else:
        result_sets = await result_set_repo.get_by_run(run_id)
        total_dict = None
        direct_dict = None
        indirect_dict = None

        for rs in result_sets:
            if rs.metric_type == "total_output":
                total_dict = rs.values
            elif rs.metric_type == "direct_effect":
                direct_dict = rs.values
            elif rs.metric_type == "indirect_effect":
                indirect_dict = rs.values

        if total_dict is None:
            raise HTTPException(
                status_code=404,
                detail=f"No total_output ResultSet found for run {run_id}.",
            )
        if direct_dict is None:
            direct_dict = total_dict
        if indirect_dict is None:
            indirect_dict = {sc: 0.0 for sc in sector_codes}

    # 7. Convert to numpy arrays
    delta_x_total = np.array(
        [total_dict.get(sc, 0.0) for sc in sector_codes], dtype=float,
    )
    delta_x_direct = np.array(
        [direct_dict.get(sc, 0.0) for sc in sector_codes], dtype=float,
    )
    delta_x_indirect = np.array(
        [indirect_dict.get(sc, 0.0) for sc in sector_codes], dtype=float,
    )

    # 8. Build domain models from DB rows
    from src.models.workforce import (
        BridgeEntry,
        SectorEmploymentCoefficient,
        SectorSaudizationTarget,
        TierAssignment,
    )

    ec_model = EmploymentCoefficients(
        employment_coefficients_id=ec_row.employment_coefficients_id,
        version=ec_row.version,
        model_version_id=ec_row.model_version_id,
        workspace_id=ec_row.workspace_id,
        output_unit=ec_row.output_unit,
        base_year=ec_row.base_year,
        coefficients=[
            SectorEmploymentCoefficient(**c) for c in ec_row.coefficients
        ],
    )

    # 9. Optionally load bridge
    bridge_model = None
    if body.bridge_id:
        bridge_id = UUID(body.bridge_id)
        if body.bridge_version is not None:
            bridge_row = await bridge_repo.get(bridge_id, body.bridge_version)
        else:
            bridge_row = await bridge_repo.get_latest(bridge_id)
        if bridge_row:
            bridge_model = SectorOccupationBridge(
                bridge_id=bridge_row.bridge_id,
                version=bridge_row.version,
                model_version_id=bridge_row.model_version_id,
                workspace_id=bridge_row.workspace_id,
                entries=[BridgeEntry(**e) for e in bridge_row.entries],
            )

    # 10. Optionally load rules
    rules_model = None
    if body.rules_id:
        rules_id_val = UUID(body.rules_id)
        if body.rules_version is not None:
            rules_row = await rules_repo.get(rules_id_val, body.rules_version)
        else:
            rules_row = await rules_repo.get_latest(rules_id_val)
        if rules_row:
            rules_model = SaudizationRules(
                rules_id=rules_row.rules_id,
                version=rules_row.version,
                workspace_id=rules_row.workspace_id,
                tier_assignments=[TierAssignment(**t) for t in rules_row.tier_assignments],
                sector_targets=[SectorSaudizationTarget(**s) for s in rules_row.sector_targets],
            )

    # 11. Compute workforce impact
    wf_result = compute_workforce_impact(
        delta_x_total=delta_x_total,
        delta_x_direct=delta_x_direct,
        delta_x_indirect=delta_x_indirect,
        sector_codes=sector_codes,
        coefficients=ec_model,
        bridge=bridge_model,
        rules=rules_model,
        delta_x_source=delta_x_source,
        feasibility_result_id=feasibility_result_id,
        delta_x_unit="SAR",
    )

    # 12. Persist result
    wf_id = new_uuid7()
    result_data = wf_result.model_dump(mode="json")

    await result_repo.create(
        workforce_result_id=wf_id,
        workspace_id=workspace_id,
        run_id=run_id,
        employment_coefficients_id=ec_row.employment_coefficients_id,
        employment_coefficients_version=ec_row.version,
        bridge_id=bridge_model.bridge_id if bridge_model else None,
        bridge_version=bridge_model.version if bridge_model else None,
        rules_id=rules_model.rules_id if rules_model else None,
        rules_version=rules_model.version if rules_model else None,
        results=result_data,
        confidence_summary=result_data.get("confidence_summary", {}),
        data_quality_notes=result_data.get("data_quality_notes", []),
        satellite_coefficients_hash=wf_result.satellite_coefficients_hash,
        delta_x_source=delta_x_source,
        feasibility_result_id=feasibility_result_id,
    )

    return WorkforceResultResponse(
        workforce_result_id=str(wf_id),
        run_id=str(run_id),
        workspace_id=str(workspace_id),
        sector_employment=result_data.get("sector_employment", {}),
        occupation_breakdowns=result_data.get("occupation_breakdowns", {}),
        nationality_splits=result_data.get("nationality_splits", {}),
        saudization_gaps=result_data.get("saudization_gaps", {}),
        sensitivity_envelopes=result_data.get("sensitivity_envelopes", {}),
        confidence_summary=result_data.get("confidence_summary", {}),
        employment_coefficients_id=str(ec_row.employment_coefficients_id),
        employment_coefficients_version=ec_row.version,
        bridge_id=str(bridge_model.bridge_id) if bridge_model else None,
        bridge_version=bridge_model.version if bridge_model else None,
        rules_id=str(rules_model.rules_id) if rules_model else None,
        rules_version=rules_model.version if rules_model else None,
        satellite_coefficients_hash=wf_result.satellite_coefficients_hash,
        data_quality_notes=result_data.get("data_quality_notes", []),
        delta_x_source=delta_x_source,
        feasibility_result_id=str(feasibility_result_id) if feasibility_result_id else None,
        delta_x_unit="SAR",
        coefficient_unit=ec_row.output_unit,
    )


# ---------------------------------------------------------------------------
# Get Workforce Results
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/runs/{run_id}/workforce",
    response_model=list[WorkforceResultResponse],
)
async def get_workforce_results(
    workspace_id: UUID,
    run_id: UUID,
    result_repo: WorkforceResultRepository = Depends(get_workforce_result_repo),
) -> list[WorkforceResultResponse]:
    """Get all workforce results for a run."""
    rows = await result_repo.get_by_run(run_id)
    return [_row_to_response(r) for r in rows]


def _row_to_response(r) -> WorkforceResultResponse:
    """Convert a WorkforceResultRow to response model."""
    results = r.results or {}
    return WorkforceResultResponse(
        workforce_result_id=str(r.workforce_result_id),
        run_id=str(r.run_id),
        workspace_id=str(r.workspace_id),
        sector_employment=results.get("sector_employment", {}),
        occupation_breakdowns=results.get("occupation_breakdowns", {}),
        nationality_splits=results.get("nationality_splits", {}),
        saudization_gaps=results.get("saudization_gaps", {}),
        sensitivity_envelopes=results.get("sensitivity_envelopes", {}),
        confidence_summary=r.confidence_summary or {},
        employment_coefficients_id=str(r.employment_coefficients_id),
        employment_coefficients_version=r.employment_coefficients_version,
        bridge_id=str(r.bridge_id) if r.bridge_id else None,
        bridge_version=r.bridge_version,
        rules_id=str(r.rules_id) if r.rules_id else None,
        rules_version=r.rules_version,
        satellite_coefficients_hash=r.satellite_coefficients_hash,
        data_quality_notes=r.data_quality_notes or [],
        delta_x_source=r.delta_x_source,
        feasibility_result_id=str(r.feasibility_result_id) if r.feasibility_result_id else None,
        delta_x_unit=results.get("delta_x_unit", "SAR"),
        coefficient_unit=results.get("coefficient_unit", "MILLION_SAR"),
    )
