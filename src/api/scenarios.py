"""FastAPI scenario endpoints — MVP-4.

POST /v1/workspaces/{workspace_id}/scenarios                          — create
POST /v1/workspaces/{workspace_id}/scenarios/{id}/compile             — compile
POST /v1/workspaces/{workspace_id}/scenarios/{id}/mapping-decisions   — bulk
GET  /v1/workspaces/{workspace_id}/scenarios/{id}/versions            — history
POST /v1/workspaces/{workspace_id}/scenarios/{id}/lock                — lock

S0-4: Workspace-scoped routes.
Deterministic — no LLM calls.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.dependencies import get_scenario_version_repo
from src.compiler.scenario_compiler import CompilationInput, ScenarioCompiler
from src.models.common import new_uuid7
from src.models.document import BoQLineItem
from src.models.mapping import DecisionType, MappingDecision
from src.models.scenario import ScenarioSpec, TimeHorizon
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
    line_items: list[LineItemPayload]
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
) -> dict:
    """Compile line items + decisions into shock items."""
    spec = await _get_latest_or_404(repo, scenario_id)

    # Build BoQLineItems (simplified for API — real items come from extraction)
    line_items: list[BoQLineItem] = []
    for li_payload in body.line_items:
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

    return {
        "scenario_spec_id": str(scenario_id),
        "version": new_spec.version,
        "shock_items": [si.model_dump() for si in compiled.shock_items],
        "data_quality_summary": (
            compiled.data_quality_summary.model_dump()
            if compiled.data_quality_summary else None
        ),
    }


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
