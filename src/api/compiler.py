"""FastAPI AI compiler endpoints — MVP-8.

POST /v1/compiler/compile              — trigger AI-assisted compilation
GET  /v1/compiler/{id}/status          — suggestion status
POST /v1/compiler/{id}/decisions       — accept/reject suggestions in bulk

CRITICAL: Agent-to-Math Boundary enforced. All outputs are Pydantic-validated
JSON. Agents propose mappings — they NEVER compute economic results.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from uuid_extensions import uuid7

from src.agents.assumption_agent import AssumptionDraftAgent
from src.agents.mapping_agent import MappingSuggestionAgent
from src.agents.split_agent import SplitAgent
from src.compiler.ai_compiler import (
    AICompilationInput,
    AICompilationResult,
    AICompiler,
    CompilationMode,
)
from src.compiler.learning import LearningLoop, OverridePair
from src.models.document import BoQLineItem
from src.models.mapping import MappingLibraryEntry
from src.models.scenario import TimeHorizon

router = APIRouter(prefix="/v1/compiler", tags=["compiler"])

# ---------------------------------------------------------------------------
# In-memory stores (MVP — replaced by PostgreSQL in production)
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

_learning_loop = LearningLoop()

# compilation_id → AICompilationResult + metadata
_compilation_store: dict[UUID, dict] = {}


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CompileLineItem(BaseModel):
    line_item_id: str
    raw_text: str
    total_value: float = 0.0


class CompileRequest(BaseModel):
    workspace_id: str
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


@router.post("/compile", status_code=201, response_model=CompileResponse)
async def trigger_compilation(body: CompileRequest) -> CompileResponse:
    """Trigger AI-assisted compilation for a set of line items."""
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
        workspace_id=UUID(body.workspace_id),
        scenario_name=body.scenario_name,
        base_model_version_id=UUID(body.base_model_version_id),
        base_year=body.base_year,
        time_horizon=TimeHorizon(start_year=body.start_year, end_year=body.end_year),
        line_items=boq_items,
        taxonomy=_default_taxonomy,
        phasing=phasing,
    )

    result = _ai_compiler.compile(inp)

    # Store for status/decision endpoints
    comp_id = uuid7()
    _compilation_store[comp_id] = {
        "result": result,
        "line_items": body.line_items,
        "decisions": {},  # line_item_id → decision
    }

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


@router.get("/{compilation_id}/status", response_model=StatusResponse)
async def get_status(compilation_id: UUID) -> StatusResponse:
    """Get compilation suggestion status."""
    record = _compilation_store.get(compilation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Compilation not found.")

    result: AICompilationResult = record["result"]
    return StatusResponse(
        compilation_id=str(compilation_id),
        total_suggestions=len(result.mapping_suggestions),
        high_confidence=result.high_confidence_count,
        medium_confidence=result.medium_confidence_count,
        low_confidence=result.low_confidence_count,
        assumption_drafts=len(result.assumption_drafts),
    )


@router.post("/{compilation_id}/decisions", response_model=BulkDecisionResponse)
async def bulk_decisions(
    compilation_id: UUID,
    body: BulkDecisionRequest,
) -> BulkDecisionResponse:
    """Accept or reject suggestions in bulk."""
    record = _compilation_store.get(compilation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Compilation not found.")

    result: AICompilationResult = record["result"]
    suggestion_map = {str(s.line_item_id): s for s in result.mapping_suggestions}

    accepted = 0
    rejected = 0

    for decision in body.decisions:
        suggestion = suggestion_map.get(decision.line_item_id)
        if suggestion is None:
            continue

        if decision.action == "accept":
            accepted += 1
            # Record in learning loop
            _learning_loop.record_override(OverridePair(
                engagement_id=uuid7(),
                line_item_id=UUID(decision.line_item_id),
                line_item_text=suggestion.explanation,
                suggested_sector_code=suggestion.sector_code,
                final_sector_code=suggestion.sector_code,
            ))
        elif decision.action == "reject":
            rejected += 1
            final_code = decision.override_sector_code or suggestion.sector_code
            _learning_loop.record_override(OverridePair(
                engagement_id=uuid7(),
                line_item_id=UUID(decision.line_item_id),
                line_item_text=suggestion.explanation,
                suggested_sector_code=suggestion.sector_code,
                final_sector_code=final_code,
            ))

        record["decisions"][decision.line_item_id] = decision.action

    return BulkDecisionResponse(
        accepted=accepted,
        rejected=rejected,
        total=accepted + rejected,
    )
