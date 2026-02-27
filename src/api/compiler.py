"""FastAPI AI compiler endpoints — MVP-8, amended MVP-12.

POST /v1/workspaces/{workspace_id}/compiler/compile              — trigger compilation
GET  /v1/workspaces/{workspace_id}/compiler/{id}/status          — suggestion status
POST /v1/workspaces/{workspace_id}/compiler/{id}/decisions       — accept/reject bulk

S0-4: Workspace-scoped routes.
CRITICAL: Agent-to-Math Boundary enforced. All outputs are Pydantic-validated
JSON. Agents propose mappings — they NEVER compute economic results.

Amendment 3 (MVP-12): bulk_decisions auto-captures to LibraryLearningLoop.
Amendment 4 (MVP-12): compile uses list_for_agent() when available.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from uuid_extensions import uuid7

from src.agents.assumption_agent import AssumptionDraftAgent
from src.agents.mapping_agent import MappingSuggestionAgent
from src.agents.split_agent import SplitAgent
from src.api.dependencies import (
    get_compilation_repo,
    get_mapping_library_repo,
    get_override_pair_repo,
)
from src.compiler.ai_compiler import (
    AICompilationInput,
    AICompiler,
)
from src.models.document import BoQLineItem
from src.models.mapping import MappingLibraryEntry
from src.models.scenario import TimeHorizon
from src.repositories.compiler import CompilationRepository, OverridePairRepository
from src.repositories.libraries import MappingLibraryRepository

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/workspaces", tags=["compiler"])

# ---------------------------------------------------------------------------
# Static reference data (stays — no DB needed)
# ---------------------------------------------------------------------------

_default_library = [
    MappingLibraryEntry(pattern="concrete works", sector_code="F", confidence=0.95),
    MappingLibraryEntry(pattern="steel reinforcement", sector_code="F", confidence=0.90),
    MappingLibraryEntry(pattern="transport services", sector_code="H", confidence=0.88),
    MappingLibraryEntry(pattern="catering services", sector_code="I", confidence=0.85),
    MappingLibraryEntry(pattern="software development", sector_code="J", confidence=0.92),
    MappingLibraryEntry(pattern="electrical works", sector_code="F", confidence=0.88),
    MappingLibraryEntry(pattern="plumbing works", sector_code="F", confidence=0.87),
]

_default_taxonomy = [
    {"sector_code": "A", "sector_name": "Agriculture"},
    {"sector_code": "B", "sector_name": "Mining"},
    {"sector_code": "C", "sector_name": "Manufacturing"},
    {"sector_code": "D", "sector_name": "Utilities"},
    {"sector_code": "F", "sector_name": "Construction"},
    {"sector_code": "G", "sector_name": "Trade"},
    {"sector_code": "H", "sector_name": "Transport"},
    {"sector_code": "I", "sector_name": "Accommodation/Food"},
    {"sector_code": "J", "sector_name": "ICT"},
]

_ai_compiler = AICompiler(
    mapping_agent=MappingSuggestionAgent(library=_default_library),
    split_agent=SplitAgent(defaults=[]),
    assumption_agent=AssumptionDraftAgent(),
)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CompileLineItem(BaseModel):
    line_item_id: str
    raw_text: str
    total_value: float = 0.0


class CompileRequest(BaseModel):
    workspace_id: str | None = None  # Optional — workspace_id from path takes precedence
    scenario_name: str
    base_model_version_id: str
    base_year: int
    start_year: int
    end_year: int
    line_items: list[CompileLineItem]
    phasing: dict[str, float] = Field(default_factory=dict)


class SuggestionOut(BaseModel):
    line_item_id: str
    sector_code: str
    confidence: float
    explanation: str


class CompileResponse(BaseModel):
    compilation_id: str
    suggestions: list[SuggestionOut]
    high_confidence: int
    medium_confidence: int
    low_confidence: int


class StatusResponse(BaseModel):
    compilation_id: str
    total_suggestions: int
    high_confidence: int
    medium_confidence: int
    low_confidence: int
    assumption_drafts: int


class DecisionItem(BaseModel):
    line_item_id: str
    action: str  # "accept" | "reject"
    override_sector_code: str | None = None
    note: str | None = None


class BulkDecisionRequest(BaseModel):
    decisions: list[DecisionItem]


class BulkDecisionResponse(BaseModel):
    accepted: int
    rejected: int
    total: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{workspace_id}/compiler/compile", status_code=201, response_model=CompileResponse)
async def trigger_compilation(
    workspace_id: UUID,
    body: CompileRequest,
    comp_repo: CompilationRepository = Depends(get_compilation_repo),
    mapping_repo: MappingLibraryRepository = Depends(
        get_mapping_library_repo,
    ),
) -> CompileResponse:
    """Trigger AI-assisted compilation for a set of line items.

    Amendment 4 (MVP-12): Uses workspace library entries via list_for_agent()
    when available, falling back to _default_library.
    """
    # Amendment 4: Try workspace library first, fallback to defaults
    try:
        library = await mapping_repo.list_for_agent(workspace_id)
    except Exception:
        _logger.warning(
            "list_for_agent failed for %s, using default library",
            workspace_id,
        )
        library = []

    if not library:
        library = _default_library

    compiler = AICompiler(
        mapping_agent=MappingSuggestionAgent(library=library),
        split_agent=SplitAgent(defaults=[]),
        assumption_agent=AssumptionDraftAgent(),
    )

    # Convert API line items to BoQLineItem models
    evidence_id = uuid7()  # Placeholder for MVP
    boq_items: list[BoQLineItem] = []
    for item in body.line_items:
        boq_items.append(BoQLineItem(
            line_item_id=UUID(item.line_item_id),
            doc_id=uuid7(),
            extraction_job_id=uuid7(),
            raw_text=item.raw_text,
            description=item.raw_text,
            total_value=item.total_value,
            page_ref=0,
            evidence_snippet_ids=[evidence_id],
        ))

    # Convert phasing keys to int
    phasing = {int(k): v for k, v in body.phasing.items()}

    inp = AICompilationInput(
        workspace_id=workspace_id,
        scenario_name=body.scenario_name,
        base_model_version_id=UUID(body.base_model_version_id),
        base_year=body.base_year,
        time_horizon=TimeHorizon(start_year=body.start_year, end_year=body.end_year),
        line_items=boq_items,
        taxonomy=_default_taxonomy,
        phasing=phasing,
    )

    result = compiler.compile(inp)

    # Serialize result for DB storage
    result_json = {
        "mapping_suggestions": [
            {
                "line_item_id": str(s.line_item_id),
                "sector_code": s.sector_code,
                "confidence": s.confidence,
                "explanation": s.explanation,
            }
            for s in result.mapping_suggestions
        ],
        "split_proposals": [s.model_dump(mode="json") for s in result.split_proposals],
        "assumption_drafts": [a.model_dump(mode="json") for a in result.assumption_drafts],
        "high_confidence_count": result.high_confidence_count,
        "medium_confidence_count": result.medium_confidence_count,
        "low_confidence_count": result.low_confidence_count,
        "mode": str(result.mode),
    }
    metadata_json = {
        "line_items": [li.model_dump(mode="json") for li in body.line_items],
        "decisions": {},
    }

    comp_id = uuid7()
    await comp_repo.create(
        compilation_id=comp_id,
        result_json=result_json,
        metadata_json=metadata_json,
    )

    suggestions_out = [
        SuggestionOut(
            line_item_id=str(s.line_item_id),
            sector_code=s.sector_code,
            confidence=s.confidence,
            explanation=s.explanation,
        )
        for s in result.mapping_suggestions
    ]

    return CompileResponse(
        compilation_id=str(comp_id),
        suggestions=suggestions_out,
        high_confidence=result.high_confidence_count,
        medium_confidence=result.medium_confidence_count,
        low_confidence=result.low_confidence_count,
    )


@router.get("/{workspace_id}/compiler/{compilation_id}/status", response_model=StatusResponse)
async def get_status(
    workspace_id: UUID,
    compilation_id: UUID,
    comp_repo: CompilationRepository = Depends(get_compilation_repo),
) -> StatusResponse:
    """Get compilation suggestion status."""
    row = await comp_repo.get(compilation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Compilation not found.")

    rj = row.result_json
    return StatusResponse(
        compilation_id=str(compilation_id),
        total_suggestions=len(rj.get("mapping_suggestions", [])),
        high_confidence=rj.get("high_confidence_count", 0),
        medium_confidence=rj.get("medium_confidence_count", 0),
        low_confidence=rj.get("low_confidence_count", 0),
        assumption_drafts=len(rj.get("assumption_drafts", [])),
    )


@router.post(
    "/{workspace_id}/compiler/{compilation_id}/decisions",
    response_model=BulkDecisionResponse,
)
async def bulk_decisions(
    workspace_id: UUID,
    compilation_id: UUID,
    body: BulkDecisionRequest,
    comp_repo: CompilationRepository = Depends(get_compilation_repo),
    override_repo: OverridePairRepository = Depends(get_override_pair_repo),
    mapping_repo: MappingLibraryRepository = Depends(
        get_mapping_library_repo,
    ),
) -> BulkDecisionResponse:
    """Accept or reject suggestions in bulk.

    Amendment 3 (MVP-12): Auto-captures to mapping library via repository.
    Wrapped in try/except — library failure never blocks decisions.
    """
    row = await comp_repo.get(compilation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Compilation not found.")

    suggestion_map = {
        s["line_item_id"]: s
        for s in row.result_json.get("mapping_suggestions", [])
    }

    accepted = 0
    rejected = 0
    engagement_id = uuid7()

    for decision in body.decisions:
        suggestion = suggestion_map.get(decision.line_item_id)
        if suggestion is None:
            continue

        if decision.action == "accept":
            accepted += 1
            await override_repo.create(
                override_id=uuid7(),
                engagement_id=engagement_id,
                line_item_id=UUID(decision.line_item_id),
                line_item_text=suggestion["explanation"],
                suggested_sector_code=suggestion["sector_code"],
                final_sector_code=suggestion["sector_code"],
            )
            # Amendment 3: auto-capture approved mapping to library
            try:
                from src.models.common import new_uuid7
                await mapping_repo.create_entry(
                    entry_id=new_uuid7(),
                    workspace_id=workspace_id,
                    pattern=suggestion["explanation"],
                    sector_code=suggestion["sector_code"],
                    confidence=suggestion.get("confidence", 0.8),
                    source_engagement_id=engagement_id,
                    status="DRAFT",
                )
            except Exception:
                _logger.warning(
                    "Library auto-capture failed for accept %s",
                    decision.line_item_id,
                    exc_info=True,
                )
        elif decision.action == "reject":
            rejected += 1
            final_code = (
                decision.override_sector_code or suggestion["sector_code"]
            )
            await override_repo.create(
                override_id=uuid7(),
                engagement_id=engagement_id,
                line_item_id=UUID(decision.line_item_id),
                line_item_text=suggestion["explanation"],
                suggested_sector_code=suggestion["sector_code"],
                final_sector_code=final_code,
            )
            # Amendment 3: auto-capture override (high-value signal)
            if decision.override_sector_code:
                try:
                    from src.models.common import new_uuid7
                    await mapping_repo.create_entry(
                        entry_id=new_uuid7(),
                        workspace_id=workspace_id,
                        pattern=suggestion["explanation"],
                        sector_code=final_code,
                        confidence=0.9,
                        source_engagement_id=engagement_id,
                        status="DRAFT",
                    )
                except Exception:
                    _logger.warning(
                        "Library auto-capture failed for override %s",
                        decision.line_item_id,
                        exc_info=True,
                    )

    return BulkDecisionResponse(
        accepted=accepted,
        rejected=rejected,
        total=accepted + rejected,
    )
