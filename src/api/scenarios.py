"""FastAPI scenario endpoints — MVP-4.

POST /v1/workspaces/{workspace_id}/scenarios                          — create
POST /v1/workspaces/{workspace_id}/scenarios/{id}/compile             — compile
POST /v1/workspaces/{workspace_id}/scenarios/{id}/mapping-decisions   — bulk
GET  /v1/workspaces/{workspace_id}/scenarios/{id}/versions            — history
POST /v1/workspaces/{workspace_id}/scenarios/{id}/lock                — lock

S0-4: Workspace-scoped routes.
Deterministic — no LLM calls.
"""

import warnings
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.responses import JSONResponse

from src.api.dependencies import (
    get_document_repo,
    get_extraction_job_repo,
    get_line_item_repo,
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
            evidence_snippet_ids=[UUID(eid) if isinstance(eid, str) else eid for eid in evidence_ids],
        ))
    return boq_items


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{workspace_id}/scenarios", status_code=201, response_model=CreateScenarioResponse)
async def create_scenario(
    workspace_id: UUID,
    body: CreateScenarioRequest,
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
    repo: ScenarioVersionRepository = Depends(get_scenario_version_repo),
) -> LockResponse:
    """Lock mappings for governed run — creates new version."""
    spec = await _get_latest_or_404(repo, scenario_id)
    new_spec = await _record_new_version(repo, spec)

    return LockResponse(
        new_version=new_spec.version,
        status="locked",
    )
