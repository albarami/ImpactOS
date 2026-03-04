"""FastAPI scenario endpoints — MVP-4 + B-16 run-from-scenario.

GET  /v1/workspaces/{workspace_id}/scenarios                          — list (B-9)
GET  /v1/workspaces/{workspace_id}/scenarios/{id}                     — detail (B-10)
POST /v1/workspaces/{workspace_id}/scenarios                          — create
POST /v1/workspaces/{workspace_id}/scenarios/{id}/compile             — compile
POST /v1/workspaces/{workspace_id}/scenarios/{id}/mapping-decisions   — bulk
GET  /v1/workspaces/{workspace_id}/scenarios/{id}/versions            — history
POST /v1/workspaces/{workspace_id}/scenarios/{id}/lock                — lock
POST /v1/workspaces/{workspace_id}/scenarios/{id}/run                 — run (B-16)
POST /v1/workspaces/{workspace_id}/scenarios/compare-runs             — compare runs (S19-2)

S0-4: Workspace-scoped routes.
Deterministic — no LLM calls.
"""

import warnings
from uuid import UUID

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.responses import JSONResponse

from src.api.auth_deps import (
    WorkspaceMember,
    require_role,
    require_workspace_member,
)
from src.api.dependencies import (
    get_document_repo,
    get_extraction_job_repo,
    get_line_item_repo,
    get_model_data_repo,
    get_model_version_repo,
    get_result_set_repo,
    get_run_snapshot_repo,
    get_scenario_version_repo,
)
from src.compiler.scenario_compiler import CompilationInput, ScenarioCompiler
from src.models.common import new_uuid7
from src.models.document import BoQLineItem
from src.models.mapping import DecisionType, MappingDecision
from src.models.scenario import ScenarioSpec, TimeHorizon
from src.repositories.documents import (
    DocumentRepository,
    ExtractionJobRepository,
    LineItemRepository,
)
from src.repositories.engine import (
    ModelDataRepository,
    ModelVersionRepository,
    ResultSetRepository,
    RunSnapshotRepository,
)
from src.repositories.scenarios import ScenarioVersionRepository

router = APIRouter(prefix="/v1/workspaces", tags=["scenarios"])

# ---------------------------------------------------------------------------
# Stateless services (no DB needed)
# ---------------------------------------------------------------------------

_compiler = ScenarioCompiler()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateScenarioRequest(BaseModel):
    name: str
    workspace_id: str | None = None  # Optional — workspace_id from path takes precedence
    base_model_version_id: str
    base_year: int
    start_year: int
    end_year: int


class CreateScenarioResponse(BaseModel):
    scenario_spec_id: str
    version: int
    name: str


class LineItemPayload(BaseModel):
    line_item_id: str
    description: str
    total_value: float
    currency_code: str = "SAR"


class DecisionPayload(BaseModel):
    line_item_id: str
    final_sector_code: str | None = None
    decision_type: str
    suggested_confidence: float | None = None
    decided_by: str


class CompileRequest(BaseModel):
    line_items: list[LineItemPayload] | None = None
    document_id: str | None = None
    decisions: list[DecisionPayload]
    phasing: dict[str, float]
    default_domestic_share: float = 0.65


class MappingDecisionBulkItem(BaseModel):
    line_item_id: str
    final_sector_code: str | None = None
    decision_type: str
    decided_by: str
    rationale: str = ""


class MappingDecisionsBulkRequest(BaseModel):
    decisions: list[MappingDecisionBulkItem]


class MappingDecisionsBulkResponse(BaseModel):
    new_version: int
    decisions_processed: int


class VersionEntry(BaseModel):
    version: int
    updated_at: str


class VersionsResponse(BaseModel):
    versions: list[VersionEntry]


class LockRequest(BaseModel):
    actor: str


class LockResponse(BaseModel):
    new_version: int
    status: str


# --- B-16: Run-from-scenario ---


class SatelliteCoeffsPayload(BaseModel):
    jobs_coeff: list[float]
    import_ratio: list[float]
    va_ratio: list[float]


class RunFromScenarioRequest(BaseModel):
    mode: str = "SANDBOX"
    satellite_coefficients: SatelliteCoeffsPayload
    deflators: dict[str, float] | None = None


class RunFromScenarioResultSet(BaseModel):
    result_id: str
    metric_type: str
    values: dict[str, float]


class RunFromScenarioSnapshot(BaseModel):
    run_id: str
    model_version_id: str


class RunFromScenarioResponse(BaseModel):
    run_id: str
    result_sets: list[RunFromScenarioResultSet]
    snapshot: RunFromScenarioSnapshot


# --- B-9: Scenario list response ---


class ScenarioListItem(BaseModel):
    scenario_spec_id: str
    name: str
    version: int
    workspace_id: str
    created_at: str
    status: str


class ScenarioListResponse(BaseModel):
    items: list[ScenarioListItem]
    total: int
    next_cursor: str | None = None


# --- B-10: Scenario detail response ---


class TimeHorizonResponse(BaseModel):
    start_year: int
    end_year: int


class ScenarioDetailResponse(BaseModel):
    scenario_spec_id: str
    name: str
    version: int
    workspace_id: str
    base_model_version_id: str
    base_year: int
    currency: str
    disclosure_tier: str
    time_horizon: TimeHorizonResponse
    shock_items: list[dict]
    assumption_ids: list[str]
    status: str
    created_at: str
    updated_at: str


# --- S19-2: Scenario comparison schemas ---


class CompareRunsRequest(BaseModel):
    run_id_a: str
    run_id_b: str
    include_annual: bool = False
    include_peak: bool = False


class MetricComparison(BaseModel):
    metric_type: str
    value_a: float
    value_b: float
    delta: float
    pct_change: float | None = None


class AnnualComparison(BaseModel):
    year: int
    metrics: list[MetricComparison]


class PeakComparison(BaseModel):
    peak_year_a: int | None = None
    peak_year_b: int | None = None
    metrics: list[MetricComparison]


class CompareRunsResponse(BaseModel):
    run_id_a: str
    run_id_b: str
    model_version_a: str
    model_version_b: str
    metrics: list[MetricComparison]
    annual: list[AnnualComparison] | None = None
    peak: PeakComparison | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec_from_row(row) -> ScenarioSpec:
    """Convert ScenarioSpecRow to ScenarioSpec Pydantic model."""
    th = row.time_horizon or {}
    return ScenarioSpec(
        scenario_spec_id=row.scenario_spec_id,
        version=row.version,
        name=row.name,
        workspace_id=row.workspace_id,
        base_model_version_id=row.base_model_version_id,
        base_year=row.base_year,
        time_horizon=(
            TimeHorizon(**th)
            if th
            else TimeHorizon(start_year=row.base_year, end_year=row.base_year)
        ),
        shock_items=[],
        assumption_ids=[],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _get_latest_or_404(
    repo: ScenarioVersionRepository,
    scenario_id: UUID,
) -> ScenarioSpec:
    """Fetch latest scenario version or raise 404."""
    row = await repo.get_latest(scenario_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found.")
    return _spec_from_row(row)


async def _record_new_version(
    repo: ScenarioVersionRepository,
    spec: ScenarioSpec,
    *,
    is_locked: bool = False,
) -> ScenarioSpec:
    """Create a new version of a scenario in the DB."""
    new_spec = spec.next_version()
    await repo.create(
        scenario_spec_id=new_spec.scenario_spec_id,
        version=new_spec.version,
        name=new_spec.name,
        workspace_id=new_spec.workspace_id,
        base_model_version_id=new_spec.base_model_version_id,
        base_year=new_spec.base_year,
        time_horizon=new_spec.time_horizon.model_dump(),
        shock_items=(
            [si.model_dump() for si in new_spec.shock_items]
            if new_spec.shock_items else []
        ),
        assumption_ids=(
            [str(aid) for aid in new_spec.assumption_ids]
            if new_spec.assumption_ids else []
        ),
        is_locked=is_locked,
    )
    return new_spec


def _build_line_items_from_payload(payload_items: list[LineItemPayload]) -> list[BoQLineItem]:
    """Convert inline LineItemPayload objects to BoQLineItem models."""
    line_items: list[BoQLineItem] = []
    for li_payload in payload_items:
        li = BoQLineItem(
            line_item_id=UUID(li_payload.line_item_id),
            doc_id=new_uuid7(),
            extraction_job_id=new_uuid7(),
            raw_text=li_payload.description,
            description=li_payload.description,
            total_value=li_payload.total_value,
            currency_code=li_payload.currency_code,
            page_ref=0,
            evidence_snippet_ids=[new_uuid7()],
        )
        line_items.append(li)
    return line_items


async def _load_items_from_document(
    *,
    doc_id_str: str,
    workspace_id: UUID,
    doc_repo: DocumentRepository,
    job_repo: ExtractionJobRepository,
    li_repo: LineItemRepository,
) -> list[BoQLineItem]:
    """Load line items from a stored document's latest completed extraction.

    Mirrors compiler.py's helper but stays local to the deterministic path.
    """
    doc_id = UUID(doc_id_str)
    doc_row = await doc_repo.get(doc_id)
    if doc_row is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id_str} not found.")
    latest_job = await job_repo.get_latest_completed(doc_id)
    if latest_job is None:
        raise HTTPException(
            status_code=409,
            detail=f"Document {doc_id_str} has no completed extraction.",
        )
    li_rows = await li_repo.get_by_extraction_job(latest_job.job_id)
    if not li_rows:
        raise HTTPException(
            status_code=409,
            detail=f"Document {doc_id_str} has no extracted line items.",
        )
    boq_items: list[BoQLineItem] = []
    for row in li_rows:
        evidence_ids = row.evidence_snippet_ids or [new_uuid7()]
        boq_items.append(BoQLineItem(
            line_item_id=row.line_item_id,
            doc_id=row.doc_id,
            extraction_job_id=row.extraction_job_id,
            raw_text=row.raw_text,
            description=row.description or row.raw_text,
            quantity=row.quantity,
            unit=row.unit,
            unit_price=row.unit_price,
            total_value=row.total_value or 0.0,
            currency_code=row.currency_code,
            category_code=row.category_code,
            page_ref=row.page_ref,
            evidence_snippet_ids=[
                UUID(eid) if isinstance(eid, str) else eid
                for eid in evidence_ids
            ],
        ))
    return boq_items


def _extract_aggregate(values: dict) -> float:
    """Deterministic aggregate: use _total if present, else sum numeric values."""
    if "_total" in values:
        return float(values["_total"])
    return sum(float(v) for v in values.values() if isinstance(v, (int, float)))


def _build_metric_comparison(
    metric_type: str,
    values_a: dict,
    values_b: dict,
) -> MetricComparison:
    va = _extract_aggregate(values_a)
    vb = _extract_aggregate(values_b)
    delta = vb - va
    pct = (delta / va * 100) if va != 0.0 else None
    return MetricComparison(
        metric_type=metric_type,
        value_a=va, value_b=vb,
        delta=delta, pct_change=pct,
    )


def _build_annual_comparisons(
    annual_a: list, annual_b: list, years: list[int],
) -> list[AnnualComparison]:
    """Build per-year metric comparisons from annual ResultSet rows."""
    def _group(rows):
        out: dict = {}
        for r in rows:
            out.setdefault(r.year, {})[r.metric_type] = r.values
        return out
    ga, gb = _group(annual_a), _group(annual_b)
    result: list[AnnualComparison] = []
    for y in years:
        year_a, year_b = ga.get(y, {}), gb.get(y, {})
        shared = sorted(set(year_a) & set(year_b))
        result.append(AnnualComparison(
            year=y,
            metrics=[_build_metric_comparison(mt, year_a[mt], year_b[mt]) for mt in shared],
        ))
    return result


def _build_peak_comparison(peak_a: list, peak_b: list) -> PeakComparison:
    """Build peak-year metric comparison."""
    map_a = {r.metric_type: r.values for r in peak_a}
    map_b = {r.metric_type: r.values for r in peak_b}
    shared = sorted(set(map_a) & set(map_b))
    return PeakComparison(
        peak_year_a=peak_a[0].year if peak_a else None,
        peak_year_b=peak_b[0].year if peak_b else None,
        metrics=[_build_metric_comparison(mt, map_a[mt], map_b[mt]) for mt in shared],
    )


def _derive_status(row) -> str:
    """Derive scenario status from data.

    - is_locked=True → LOCKED
    - Non-empty shock_items → COMPILED
    - Otherwise → DRAFT
    """
    if getattr(row, "is_locked", False):
        return "LOCKED"
    shock_items = row.shock_items
    if shock_items and len(shock_items) > 0:
        return "COMPILED"
    return "DRAFT"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


# --- S19-2: Scenario comparison ---


@router.post(
    "/{workspace_id}/scenarios/compare-runs",
    response_model=CompareRunsResponse,
)
async def compare_runs(
    workspace_id: UUID,
    body: CompareRunsRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    rs_repo: ResultSetRepository = Depends(get_result_set_repo),
) -> CompareRunsResponse:
    """Compare two runs' deterministic outputs within the same workspace."""
    run_id_a = UUID(body.run_id_a)
    run_id_b = UUID(body.run_id_b)

    # 1. Load and validate runs
    snap_a = await snap_repo.get(run_id_a)
    if snap_a is None or snap_a.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail={
            "reason_code": "COMPARE_RUN_NOT_FOUND",
            "message": f"Run {body.run_id_a} not found in workspace.",
        })
    snap_b = await snap_repo.get(run_id_b)
    if snap_b is None or snap_b.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail={
            "reason_code": "COMPARE_RUN_NOT_FOUND",
            "message": f"Run {body.run_id_b} not found in workspace.",
        })

    # 2. Load cumulative results (series_kind=None)
    results_a = await rs_repo.get_by_run_series(run_id_a, series_kind=None)
    results_b = await rs_repo.get_by_run_series(run_id_b, series_kind=None)
    if not results_a:
        raise HTTPException(status_code=422, detail={
            "reason_code": "COMPARE_NO_RESULTS",
            "message": f"Run {body.run_id_a} has no result sets.",
        })
    if not results_b:
        raise HTTPException(status_code=422, detail={
            "reason_code": "COMPARE_NO_RESULTS",
            "message": f"Run {body.run_id_b} has no result sets.",
        })

    # 3. Model mismatch check
    if snap_a.model_version_id != snap_b.model_version_id:
        raise HTTPException(status_code=422, detail={
            "reason_code": "COMPARE_MODEL_MISMATCH",
            "message": "Runs use different model versions.",
        })

    # 4. Metric set validation
    metrics_a = {r.metric_type for r in results_a}
    metrics_b = {r.metric_type for r in results_b}
    if metrics_a != metrics_b:
        raise HTTPException(status_code=422, detail={
            "reason_code": "COMPARE_METRIC_SET_MISMATCH",
            "message": f"Metric sets differ: a={sorted(metrics_a)}, b={sorted(metrics_b)}.",
        })

    # 5. Build cumulative comparisons
    map_a = {r.metric_type: r.values for r in results_a}
    map_b = {r.metric_type: r.values for r in results_b}
    metrics = [
        _build_metric_comparison(mt, map_a[mt], map_b[mt])
        for mt in sorted(metrics_a)
    ]

    # 6. Annual comparison (optional)
    annual = None
    if body.include_annual:
        annual_a = await rs_repo.get_by_run_series(run_id_a, series_kind="annual")
        annual_b = await rs_repo.get_by_run_series(run_id_b, series_kind="annual")
        if not annual_a or not annual_b:
            raise HTTPException(status_code=422, detail={
                "reason_code": "COMPARE_ANNUAL_UNAVAILABLE",
                "message": "Annual series data not available for one or both runs.",
            })
        years_a = {r.year for r in annual_a}
        years_b = {r.year for r in annual_b}
        if years_a != years_b:
            raise HTTPException(status_code=422, detail={
                "reason_code": "COMPARE_ANNUAL_YEAR_MISMATCH",
                "message": f"Year sets differ: a={sorted(years_a)}, b={sorted(years_b)}.",
            })
        annual = _build_annual_comparisons(annual_a, annual_b, sorted(years_a))

    # 7. Peak comparison (optional)
    peak = None
    if body.include_peak:
        peak_a = await rs_repo.get_by_run_series(run_id_a, series_kind="peak")
        peak_b = await rs_repo.get_by_run_series(run_id_b, series_kind="peak")
        if not peak_a or not peak_b:
            raise HTTPException(status_code=422, detail={
                "reason_code": "COMPARE_PEAK_UNAVAILABLE",
                "message": "Peak data not available for one or both runs.",
            })
        peak = _build_peak_comparison(peak_a, peak_b)

    return CompareRunsResponse(
        run_id_a=str(run_id_a),
        run_id_b=str(run_id_b),
        model_version_a=str(snap_a.model_version_id),
        model_version_b=str(snap_b.model_version_id),
        metrics=metrics,
        annual=annual,
        peak=peak,
    )


# --- B-9: Scenario list ---


@router.get("/{workspace_id}/scenarios", response_model=ScenarioListResponse)
async def list_scenarios(
    workspace_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    limit: int = 20,
    cursor: str | None = None,
    repo: ScenarioVersionRepository = Depends(get_scenario_version_repo),
) -> ScenarioListResponse:
    """B-9: List scenarios for a workspace (latest version per spec, paginated)."""
    cursor_created_at: str | None = None
    cursor_scenario_spec_id: str | None = None
    if cursor:
        import base64
        decoded = base64.b64decode(cursor).decode("utf-8")
        parts = decoded.split("|", 1)
        if len(parts) == 2:
            cursor_created_at, cursor_scenario_spec_id = parts

    rows, total = await repo.list_latest_by_workspace(
        workspace_id,
        limit=limit,
        cursor_created_at=cursor_created_at,
        cursor_scenario_spec_id=cursor_scenario_spec_id,
    )

    items = [
        ScenarioListItem(
            scenario_spec_id=str(r.scenario_spec_id),
            name=r.name,
            version=r.version,
            workspace_id=str(r.workspace_id),
            created_at=r.created_at.isoformat(),
            status=_derive_status(r),
        )
        for r in rows
    ]

    next_cursor: str | None = None
    if len(rows) == limit:
        import base64
        last = rows[-1]
        raw = f"{last.created_at.isoformat()}|{last.scenario_spec_id}"
        next_cursor = base64.b64encode(raw.encode("utf-8")).decode("utf-8")

    return ScenarioListResponse(
        items=items,
        total=total,
        next_cursor=next_cursor,
    )


# --- B-10: Scenario detail ---


@router.get(
    "/{workspace_id}/scenarios/{scenario_id}",
    response_model=ScenarioDetailResponse,
)
async def get_scenario_detail(
    workspace_id: UUID,
    scenario_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    repo: ScenarioVersionRepository = Depends(get_scenario_version_repo),
) -> ScenarioDetailResponse:
    """B-10: Get full scenario detail (latest version, workspace-scoped)."""
    row = await repo.get_latest_by_workspace(scenario_id, workspace_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Scenario not found")

    th = row.time_horizon or {}

    return ScenarioDetailResponse(
        scenario_spec_id=str(row.scenario_spec_id),
        name=row.name,
        version=row.version,
        workspace_id=str(row.workspace_id),
        base_model_version_id=str(row.base_model_version_id),
        base_year=row.base_year,
        currency=row.currency,
        disclosure_tier=row.disclosure_tier,
        time_horizon=TimeHorizonResponse(
            start_year=th.get("start_year", row.base_year),
            end_year=th.get("end_year", row.base_year),
        ),
        shock_items=row.shock_items or [],
        assumption_ids=[str(a) for a in (row.assumption_ids or [])],
        status=_derive_status(row),
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@router.post("/{workspace_id}/scenarios", status_code=201, response_model=CreateScenarioResponse)
async def create_scenario(
    workspace_id: UUID,
    body: CreateScenarioRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    repo: ScenarioVersionRepository = Depends(get_scenario_version_repo),
) -> CreateScenarioResponse:
    """Create a new scenario (version 1)."""
    spec = ScenarioSpec(
        name=body.name,
        workspace_id=workspace_id,
        base_model_version_id=UUID(body.base_model_version_id),
        base_year=body.base_year,
        time_horizon=TimeHorizon(start_year=body.start_year, end_year=body.end_year),
    )

    await repo.create(
        scenario_spec_id=spec.scenario_spec_id,
        version=spec.version,
        name=spec.name,
        workspace_id=spec.workspace_id,
        base_model_version_id=spec.base_model_version_id,
        base_year=spec.base_year,
        time_horizon=spec.time_horizon.model_dump(),
    )

    return CreateScenarioResponse(
        scenario_spec_id=str(spec.scenario_spec_id),
        version=spec.version,
        name=spec.name,
    )


@router.post("/{workspace_id}/scenarios/{scenario_id}/compile")
async def compile_scenario(
    workspace_id: UUID,
    scenario_id: UUID,
    body: CompileRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    repo: ScenarioVersionRepository = Depends(get_scenario_version_repo),
    doc_repo: DocumentRepository = Depends(get_document_repo),
    job_repo: ExtractionJobRepository = Depends(get_extraction_job_repo),
    li_repo: LineItemRepository = Depends(get_line_item_repo),
) -> dict:
    """Compile line items + decisions into shock items.

    Accepts EITHER document_id (preferred) OR inline line_items (deprecated).
    """
    spec = await _get_latest_or_404(repo, scenario_id)

    # --- Resolve line items: document_id OR inline payload ---
    headers: dict[str, str] = {}

    if body.document_id is not None:
        # Preferred path: load from stored extraction
        line_items = await _load_items_from_document(
            doc_id_str=body.document_id,
            workspace_id=workspace_id,
            doc_repo=doc_repo,
            job_repo=job_repo,
            li_repo=li_repo,
        )
    elif body.line_items is not None and len(body.line_items) > 0:
        # Legacy payload path (deprecated)
        warnings.warn(
            "Inline line_items in CompileRequest is deprecated. "
            "Use document_id instead.",
            DeprecationWarning,
            stacklevel=1,
        )
        line_items = _build_line_items_from_payload(body.line_items)
        headers["deprecation"] = "Use document_id instead of inline line_items"
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide either document_id or non-empty line_items.",
        )

    # Build MappingDecisions
    decisions: list[MappingDecision] = []
    for dec_payload in body.decisions:
        dec = MappingDecision(
            line_item_id=UUID(dec_payload.line_item_id),
            suggested_sector_code=dec_payload.final_sector_code,
            suggested_confidence=dec_payload.suggested_confidence,
            final_sector_code=dec_payload.final_sector_code,
            decision_type=DecisionType(dec_payload.decision_type),
            decided_by=UUID(dec_payload.decided_by),
        )
        decisions.append(dec)

    # For document-backed compiles, auto-approve unmapped line items so the
    # deterministic compiler can produce shock vectors without requiring a
    # prior HITL pass.  Uses category_code from extraction when available,
    # otherwise falls back to "F" (Construction — the most common BoQ sector).
    if body.document_id is not None:
        mapped_ids = {d.line_item_id for d in decisions}
        for li in line_items:
            if li.line_item_id not in mapped_ids:
                sector = li.category_code or "F"
                decisions.append(MappingDecision(
                    line_item_id=li.line_item_id,
                    suggested_sector_code=sector,
                    suggested_confidence=1.0,
                    final_sector_code=sector,
                    decision_type=DecisionType.APPROVED,
                    decided_by=new_uuid7(),
                ))

    # Build compilation input
    phasing = {int(year): share for year, share in body.phasing.items()}

    inp = CompilationInput(
        workspace_id=workspace_id,
        scenario_name=spec.name,
        base_model_version_id=spec.base_model_version_id,
        base_year=spec.base_year,
        time_horizon=spec.time_horizon,
        line_items=line_items,
        decisions=decisions,
        default_domestic_share=body.default_domestic_share,
        default_import_share=1.0 - body.default_domestic_share,
        phasing=phasing,
    )

    compiled = _compiler.compile(inp)

    new_spec = await _record_new_version(repo, spec)

    response_data = {
        "scenario_spec_id": str(scenario_id),
        "version": new_spec.version,
        "shock_items": [si.model_dump() for si in compiled.shock_items],
        "data_quality_summary": (
            compiled.data_quality_summary.model_dump()
            if compiled.data_quality_summary else None
        ),
    }

    if headers:
        return JSONResponse(content=response_data, headers=headers)
    return response_data


@router.post(
    "/{workspace_id}/scenarios/{scenario_id}/mapping-decisions",
    response_model=MappingDecisionsBulkResponse,
)
async def bulk_mapping_decisions(
    workspace_id: UUID,
    scenario_id: UUID,
    body: MappingDecisionsBulkRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    repo: ScenarioVersionRepository = Depends(get_scenario_version_repo),
) -> MappingDecisionsBulkResponse:
    """Submit bulk mapping decisions — creates new version."""
    spec = await _get_latest_or_404(repo, scenario_id)
    new_spec = await _record_new_version(repo, spec)

    return MappingDecisionsBulkResponse(
        new_version=new_spec.version,
        decisions_processed=len(body.decisions),
    )


@router.get("/{workspace_id}/scenarios/{scenario_id}/versions", response_model=VersionsResponse)
async def get_versions(
    workspace_id: UUID,
    scenario_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    repo: ScenarioVersionRepository = Depends(get_scenario_version_repo),
) -> VersionsResponse:
    """Get all versions of a scenario."""
    rows = await repo.get_versions(scenario_id)
    if not rows:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found.")

    return VersionsResponse(
        versions=[
            VersionEntry(version=r.version, updated_at=r.updated_at.isoformat())
            for r in rows
        ]
    )


@router.post("/{workspace_id}/scenarios/{scenario_id}/lock", response_model=LockResponse)
async def lock_scenario(
    workspace_id: UUID,
    scenario_id: UUID,
    body: LockRequest,
    member: WorkspaceMember = Depends(require_role("manager", "admin")),
    repo: ScenarioVersionRepository = Depends(get_scenario_version_repo),
) -> LockResponse:
    """Lock mappings for governed run — creates new version with is_locked=True."""
    spec = await _get_latest_or_404(repo, scenario_id)
    new_spec = await _record_new_version(repo, spec, is_locked=True)

    return LockResponse(
        new_version=new_spec.version,
        status="locked",
    )


# ---------------------------------------------------------------------------
# B-16: Run-from-scenario convenience endpoint
# ---------------------------------------------------------------------------


def _shock_items_to_annual_shocks(
    shock_items: list[dict],
    sector_codes: list[str],
) -> dict[int, np.ndarray]:
    """Convert scenario shock_items into annual_shocks aligned to model sector order.

    Only FINAL_DEMAND_SHOCK items contribute to final demand vectors.
    Other shock types are ignored for the base I-O run.
    """
    sector_index = {code: i for i, code in enumerate(sector_codes)}
    n = len(sector_codes)
    year_shocks: dict[int, np.ndarray] = {}

    for item in shock_items:
        if item.get("type") != "FINAL_DEMAND_SHOCK":
            continue
        year = item["year"]
        code = item["sector_code"]
        amount = item["amount_real_base_year"]
        domestic_share = item.get("domestic_share", 1.0)

        if code not in sector_index:
            continue

        if year not in year_shocks:
            year_shocks[year] = np.zeros(n, dtype=np.float64)

        year_shocks[year][sector_index[code]] += amount * domestic_share

    return year_shocks


@router.post(
    "/{workspace_id}/scenarios/{scenario_id}/run",
    response_model=RunFromScenarioResponse,
)
async def run_from_scenario(
    workspace_id: UUID,
    scenario_id: UUID,
    body: RunFromScenarioRequest,
    member: WorkspaceMember = Depends(require_role("manager", "admin")),
    repo: ScenarioVersionRepository = Depends(get_scenario_version_repo),
    mv_repo: ModelVersionRepository = Depends(get_model_version_repo),
    md_repo: ModelDataRepository = Depends(get_model_data_repo),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    rs_repo: ResultSetRepository = Depends(get_result_set_repo),
) -> RunFromScenarioResponse:
    """B-16: Execute an engine run from a compiled scenario.

    Resolves latest scenario version by workspace, validates compilation
    and lock state, converts shock_items to annual_shocks, and reuses
    the deterministic engine path.
    """
    row = await repo.get_latest_by_workspace(scenario_id, workspace_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Scenario not found")

    if not row.shock_items:
        raise HTTPException(
            status_code=409,
            detail="Scenario is not compiled (no shock items).",
        )

    if body.mode == "GOVERNED" and not row.is_locked:
        raise HTTPException(
            status_code=409,
            detail="Governed runs require a locked scenario.",
        )

    from src.api.runs import (
        SatelliteCoeffsPayload as RunSatPayload,
    )
    from src.api.runs import (
        _enforce_model_provenance,
        _ensure_model_loaded,
        _make_satellite_coefficients,
        _make_version_refs,
        _model_store,
        _persist_run_result,
        _single_run_to_response,
    )
    from src.engine.batch import BatchRequest, BatchRunner, ScenarioInput

    model_version_id = row.base_model_version_id
    await _enforce_model_provenance(model_version_id, mv_repo)
    loaded = await _ensure_model_loaded(model_version_id, mv_repo, md_repo)

    annual_shocks = _shock_items_to_annual_shocks(
        row.shock_items, loaded.sector_codes,
    )

    sat_payload = RunSatPayload(
        jobs_coeff=body.satellite_coefficients.jobs_coeff,
        import_ratio=body.satellite_coefficients.import_ratio,
        va_ratio=body.satellite_coefficients.va_ratio,
    )
    coeffs = _make_satellite_coefficients(sat_payload)

    deflators: dict[int, float] | None = None
    if body.deflators:
        deflators = {int(y): v for y, v in body.deflators.items()}

    scenario_input = ScenarioInput(
        scenario_spec_id=row.scenario_spec_id,
        scenario_spec_version=row.version,
        name=row.name,
        annual_shocks=annual_shocks,
        base_year=row.base_year,
        deflators=deflators,
    )

    runner = BatchRunner(model_store=_model_store)
    request = BatchRequest(
        scenarios=[scenario_input],
        model_version_id=model_version_id,
        satellite_coefficients=coeffs,
        version_refs=_make_version_refs(),
    )

    result = runner.run(request)
    sr = result.run_results[0]

    await _persist_run_result(sr, snap_repo, rs_repo, workspace_id=workspace_id)

    run_resp = _single_run_to_response(sr)
    return RunFromScenarioResponse(
        run_id=run_resp.run_id,
        result_sets=[
            RunFromScenarioResultSet(
                result_id=rs.result_id,
                metric_type=rs.metric_type,
                values=rs.values,
            )
            for rs in run_resp.result_sets
        ],
        snapshot=RunFromScenarioSnapshot(
            run_id=run_resp.snapshot.run_id,
            model_version_id=run_resp.snapshot.model_version_id,
        ),
    )
