"""FastAPI AI compiler endpoints — MVP-8, amended MVP-12, S0-4.

POST /v1/workspaces/{workspace_id}/compiler/compile                        — trigger
GET  /v1/workspaces/{workspace_id}/compiler/{id}                           — detail (B-17)
GET  /v1/workspaces/{workspace_id}/compiler/{id}/status                    — suggestion status
POST /v1/workspaces/{workspace_id}/compiler/{id}/decisions                 — accept/reject
GET  /v1/workspaces/{workspace_id}/compiler/{id}/decisions/{li}            — B-4 get
PUT  /v1/workspaces/{workspace_id}/compiler/{id}/decisions/{li}            — B-4 put
POST /v1/workspaces/{workspace_id}/compiler/{id}/decisions/bulk-approve    — B-5
GET  /v1/workspaces/{workspace_id}/compiler/{id}/decisions/{li}/audit      — B-8

S0-4: Doc→shock wiring — compile accepts document_id to load stored line items.
CRITICAL: Agent-to-Math Boundary enforced. All outputs are Pydantic-validated
JSON. Agents propose mappings — they NEVER compute economic results.

Amendment 3 (MVP-12): bulk_decisions auto-captures to LibraryLearningLoop.
Amendment 4 (MVP-12): compile uses list_for_agent() when available.
S0-4 Amendment 1: Loads line items from latest COMPLETED extraction only.
S0-4 Amendment 2: 409 when document has no completed extraction or no line items.
S0-4 Amendment 3: workspace_id removed from request body (path param only).
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from starlette.responses import JSONResponse
from uuid_extensions import uuid7

from src.agents.assumption_agent import AssumptionDraftAgent
from src.agents.mapping_agent import MappingSuggestionAgent
from src.agents.split_agent import SplitAgent
from src.api.dependencies import (
    get_compilation_repo,
    get_document_repo,
    get_extraction_job_repo,
    get_line_item_repo,
    get_mapping_decision_repo,
    get_mapping_library_repo,
    get_override_pair_repo,
)
from src.compiler.ai_compiler import (
    AICompilationInput,
    AICompiler,
)
from src.compiler.mapping_state import VALID_MAPPING_TRANSITIONS, MappingState
from src.db.tables import CompilationRow, MappingDecisionRow
from src.models.common import new_uuid7
from src.models.document import BoQLineItem
from src.models.mapping import MappingLibraryEntry
from src.models.scenario import TimeHorizon
from src.repositories.compiler import CompilationRepository, OverridePairRepository
from src.repositories.documents import (
    DocumentRepository,
    ExtractionJobRepository,
    LineItemRepository,
)
from src.repositories.libraries import MappingLibraryRepository
from src.repositories.mapping_decisions import MappingDecisionRepository

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
    """Compile request — provide EITHER line_items OR document_id, not both.

    S0-4 Amendment 3: workspace_id removed from body (use path parameter).
    """

    scenario_name: str
    base_model_version_id: str
    base_year: int
    start_year: int
    end_year: int
    line_items: list[CompileLineItem] | None = None
    document_id: str | None = None
    phasing: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_exactly_one_source(self) -> "CompileRequest":
        has_items = self.line_items is not None and len(self.line_items) > 0
        has_doc = self.document_id is not None
        if has_items and has_doc:
            msg = "Provide either line_items or document_id, not both."
            raise ValueError(msg)
        if not has_items and not has_doc:
            msg = "Provide either line_items (inline) or document_id (from stored extraction)."
            raise ValueError(msg)
        return self


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
    mapping_repo: MappingLibraryRepository = Depends(get_mapping_library_repo),
    doc_repo: DocumentRepository = Depends(get_document_repo),
    job_repo: ExtractionJobRepository = Depends(get_extraction_job_repo),
    li_repo: LineItemRepository = Depends(get_line_item_repo),
) -> CompileResponse:
    """Trigger AI-assisted compilation for a set of line items.

    Accepts EITHER inline line_items OR document_id (loads from DB).
    S0-4: Doc→shock wiring — compile from stored documents.
    Amendment 1 (S0-4): Uses latest COMPLETED extraction only.
    Amendment 2 (S0-4): 409 if no completed extraction or no line items.
    Amendment 4 (MVP-12): Uses workspace library entries via list_for_agent().
    """
    # --- Resolve line items: inline OR from document ---
    boq_items: list[BoQLineItem] = []

    if body.document_id is not None:
        boq_items = await _load_items_from_document(
            doc_id_str=body.document_id,
            workspace_id=workspace_id,
            doc_repo=doc_repo,
            job_repo=job_repo,
            li_repo=li_repo,
        )
    else:
        # Inline line items (existing path)
        assert body.line_items is not None  # noqa: S101 — guaranteed by validator
        evidence_id = uuid7()  # Placeholder for MVP
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

    # --- Build compilation ---
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

    result = await compiler.compile(inp)

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
        "workspace_id": str(workspace_id),
        "document_id": body.document_id,
        "line_items": (
            [li.model_dump(mode="json") for li in body.line_items]
            if body.line_items
            else None
        ),
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


async def _load_items_from_document(
    *,
    doc_id_str: str,
    workspace_id: UUID,
    doc_repo: DocumentRepository,
    job_repo: ExtractionJobRepository,
    li_repo: LineItemRepository,
) -> list[BoQLineItem]:
    """Load line items from a stored document's latest completed extraction.

    S0-4 Amendment 1: Only uses the latest COMPLETED extraction job.
    S0-4 Amendment 2: Returns 409 if no completed extraction or no line items.
    """
    doc_id = UUID(doc_id_str)

    # Verify document exists and belongs to this workspace
    doc_row = await doc_repo.get(doc_id)
    if doc_row is None or doc_row.workspace_id != workspace_id:
        raise HTTPException(
            status_code=404,
            detail=f"Document {doc_id_str} not found in this workspace.",
        )

    # Amendment 1: Latest completed extraction only
    latest_job = await job_repo.get_latest_completed(doc_id)
    if latest_job is None:
        raise HTTPException(
            status_code=409,
            detail=f"Document {doc_id_str} has no completed extraction. "
                   f"Run extraction first: POST /v1/workspaces/{workspace_id}"
                   f"/documents/{doc_id_str}/extract",
        )

    # Load line items scoped to that extraction job
    li_rows = await li_repo.get_by_extraction_job(latest_job.job_id)

    # Amendment 2: Explicit error when no line items
    if not li_rows:
        raise HTTPException(
            status_code=409,
            detail=f"Document {doc_id_str} has no extracted line items. "
                   f"Trigger extraction first: POST /v1/workspaces/{workspace_id}"
                   f"/documents/{doc_id_str}/extract",
        )

    # Convert LineItemRow → BoQLineItem
    boq_items: list[BoQLineItem] = []
    for row in li_rows:
        evidence_ids = row.evidence_snippet_ids or [uuid7()]
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


# ---------------------------------------------------------------------------
# Helpers: compilation workspace ownership
# ---------------------------------------------------------------------------


async def _get_compilation_or_404(
    comp_repo: CompilationRepository,
    compilation_id: UUID,
    workspace_id: UUID,
) -> CompilationRow:
    """Get compilation and verify workspace ownership, raise 404 otherwise."""
    row = await comp_repo.get(compilation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Compilation not found.")

    # Verify workspace ownership via metadata — strict: missing ws = 404
    meta = row.metadata_json or {}
    stored_ws = meta.get("workspace_id")
    if stored_ws is None or stored_ws != str(workspace_id):
        raise HTTPException(status_code=404, detail="Compilation not found.")

    return row


# ---------------------------------------------------------------------------
# B-17: Compilation detail — GET /compiler/{compilation_id}
# ---------------------------------------------------------------------------


class CompilationDetailSuggestion(BaseModel):
    line_item_id: str
    sector_code: str
    confidence: float
    explanation: str
    # Merged decision state (None when no decision exists for this line item)
    decision_state: str | None = None
    final_sector_code: str | None = None
    decision_type: str | None = None
    decision_note: str | None = None
    decided_by: str | None = None
    decided_at: str | None = None


class CompilationDetailResponse(BaseModel):
    compilation_id: str
    suggestions: list[CompilationDetailSuggestion]
    split_proposals: list[dict]
    assumption_drafts: list[dict]
    high_confidence: int
    medium_confidence: int
    low_confidence: int
    metadata: dict
    # Overall decision status derived from merged per-line state
    total_line_items: int = 0
    decided_count: int = 0
    status_summary: dict[str, int] = Field(default_factory=dict)


@router.get(
    "/{workspace_id}/compiler/{compilation_id}",
    response_model=CompilationDetailResponse,
)
async def get_compilation_detail(
    workspace_id: UUID,
    compilation_id: UUID,
    comp_repo: CompilationRepository = Depends(get_compilation_repo),
    decision_repo: MappingDecisionRepository = Depends(get_mapping_decision_repo),
) -> CompilationDetailResponse:
    """B-17: Get full compilation detail with merged per-line decision state.

    Returns the immutable AI compilation output (suggestions, split proposals,
    assumption drafts) enriched with the latest HITL decision state per line
    item from the mapping_decisions table, plus overall status fields.
    """
    row = await _get_compilation_or_404(comp_repo, compilation_id, workspace_id)

    rj = row.result_json or {}

    # Load latest decision per line_item for this compilation
    decision_rows = await decision_repo.list_latest_by_compilation(compilation_id)
    decision_map: dict[str, MappingDecisionRow] = {
        str(d.line_item_id): d for d in decision_rows
    }

    # Build suggestions with merged decision state
    suggestions: list[CompilationDetailSuggestion] = []
    decided_count = 0
    status_summary: dict[str, int] = {}

    for s in rj.get("mapping_suggestions", []):
        li_id = s.get("line_item_id", "")
        dec = decision_map.get(li_id)

        suggestions.append(CompilationDetailSuggestion(
            line_item_id=li_id,
            sector_code=s.get("sector_code", ""),
            confidence=s.get("confidence", 0.0),
            explanation=s.get("explanation", ""),
            decision_state=dec.state if dec else None,
            final_sector_code=dec.final_sector_code if dec else None,
            decision_type=dec.decision_type if dec else None,
            decision_note=dec.decision_note if dec else None,
            decided_by=str(dec.decided_by) if dec else None,
            decided_at=dec.decided_at.isoformat() if dec else None,
        ))

        # Count only matched decisions (ignore orphans)
        if dec is not None:
            decided_count += 1
            status_summary[dec.state] = status_summary.get(dec.state, 0) + 1

    return CompilationDetailResponse(
        compilation_id=str(compilation_id),
        suggestions=suggestions,
        split_proposals=rj.get("split_proposals", []),
        assumption_drafts=rj.get("assumption_drafts", []),
        high_confidence=rj.get("high_confidence_count", 0),
        medium_confidence=rj.get("medium_confidence_count", 0),
        low_confidence=rj.get("low_confidence_count", 0),
        metadata=row.metadata_json or {},
        total_line_items=len(suggestions),
        decided_count=decided_count,
        status_summary=status_summary,
    )


# ---------------------------------------------------------------------------
# B-4: Per-line mapping decision CRUD (compiler-scoped)
# ---------------------------------------------------------------------------


class DecisionPutRequest(BaseModel):
    state: str
    suggested_sector_code: str | None = None
    suggested_confidence: float | None = None
    final_sector_code: str | None = None
    decision_type: str | None = None
    decision_note: str | None = None
    decided_by: str


class DecisionResponse(BaseModel):
    mapping_decision_id: str
    line_item_id: str
    compilation_id: str
    state: str
    suggested_sector_code: str | None = None
    suggested_confidence: float | None = None
    final_sector_code: str | None = None
    decision_type: str | None = None
    decision_note: str | None = None
    decided_by: str
    decided_at: str
    created_at: str


def _decision_row_to_response(row: MappingDecisionRow) -> DecisionResponse:
    """Convert MappingDecisionRow to response schema."""
    return DecisionResponse(
        mapping_decision_id=str(row.mapping_decision_id),
        line_item_id=str(row.line_item_id),
        compilation_id=str(row.scenario_spec_id),
        state=row.state,
        suggested_sector_code=row.suggested_sector_code,
        suggested_confidence=row.suggested_confidence,
        final_sector_code=row.final_sector_code,
        decision_type=row.decision_type,
        decision_note=row.decision_note,
        decided_by=str(row.decided_by),
        decided_at=row.decided_at.isoformat(),
        created_at=row.created_at.isoformat(),
    )


@router.get(
    "/{workspace_id}/compiler/{compilation_id}/decisions/{line_item_id}",
    response_model=DecisionResponse,
)
async def get_decision(
    workspace_id: UUID,
    compilation_id: UUID,
    line_item_id: UUID,
    comp_repo: CompilationRepository = Depends(get_compilation_repo),
    decision_repo: MappingDecisionRepository = Depends(get_mapping_decision_repo),
) -> DecisionResponse:
    """B-4: Get current mapping decision for a line item in a compilation."""
    await _get_compilation_or_404(comp_repo, compilation_id, workspace_id)

    row = await decision_repo.get_latest(compilation_id, line_item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Decision not found")

    return _decision_row_to_response(row)


@router.put(
    "/{workspace_id}/compiler/{compilation_id}/decisions/{line_item_id}",
    response_model=DecisionResponse,
)
async def put_decision(
    workspace_id: UUID,
    compilation_id: UUID,
    line_item_id: UUID,
    body: DecisionPutRequest,
    comp_repo: CompilationRepository = Depends(get_compilation_repo),
    decision_repo: MappingDecisionRepository = Depends(get_mapping_decision_repo),
) -> JSONResponse:
    """B-4: Create or update a mapping decision (append-only, state validated)."""
    await _get_compilation_or_404(comp_repo, compilation_id, workspace_id)

    # Validate target state is a valid MappingState
    try:
        target_state = MappingState(body.state)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid state: {body.state}. "
                   f"Valid states: {[s.value for s in MappingState]}",
        )

    # Validate: APPROVED/OVERRIDDEN require final_sector_code
    if target_state in (MappingState.APPROVED, MappingState.OVERRIDDEN):
        if not body.final_sector_code:
            raise HTTPException(
                status_code=422,
                detail="final_sector_code is required for "
                       "APPROVED/OVERRIDDEN states",
            )

    # Validate: EXCLUDED requires non-empty decision_note (rationale)
    if target_state == MappingState.EXCLUDED:
        if not body.decision_note or not body.decision_note.strip():
            raise HTTPException(
                status_code=422,
                detail="decision_note (rationale) is required for "
                       "EXCLUDED state",
            )

    # Check existing decision for state transition validation
    existing = await decision_repo.get_latest(compilation_id, line_item_id)

    if existing is not None:
        # Validate transition
        current_state = MappingState(existing.state)
        allowed = VALID_MAPPING_TRANSITIONS.get(current_state, frozenset())
        if target_state not in allowed:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot transition from {current_state.value} "
                       f"to {target_state.value}. "
                       f"Allowed: {sorted(s.value for s in allowed)}",
            )
        status_code = 200
    else:
        status_code = 201

    # Create new append-only decision row
    # (scenario_spec_id column stores compilation_id for compiler scope)
    row = await decision_repo.create(
        mapping_decision_id=new_uuid7(),
        line_item_id=line_item_id,
        scenario_spec_id=compilation_id,
        state=target_state.value,
        suggested_sector_code=body.suggested_sector_code,
        suggested_confidence=body.suggested_confidence,
        final_sector_code=body.final_sector_code,
        decision_type=body.decision_type,
        decision_note=body.decision_note,
        decided_by=UUID(body.decided_by),
    )

    response_data = _decision_row_to_response(row)
    return JSONResponse(
        content=response_data.model_dump(),
        status_code=status_code,
    )


# ---------------------------------------------------------------------------
# B-5: Bulk threshold approval (compiler-scoped)
# ---------------------------------------------------------------------------


class BulkApproveRequest(BaseModel):
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    decided_by: str


class BulkApproveResponse(BaseModel):
    approved_count: int
    skipped_count: int
    total_items: int


@router.post(
    "/{workspace_id}/compiler/{compilation_id}/decisions/bulk-approve",
    response_model=BulkApproveResponse,
)
async def bulk_approve_decisions(
    workspace_id: UUID,
    compilation_id: UUID,
    body: BulkApproveRequest,
    comp_repo: CompilationRepository = Depends(get_compilation_repo),
    decision_repo: MappingDecisionRepository = Depends(get_mapping_decision_repo),
) -> BulkApproveResponse:
    """B-5: Bulk-approve AI_SUGGESTED decisions above confidence threshold."""
    await _get_compilation_or_404(comp_repo, compilation_id, workspace_id)

    # Get ALL latest AI_SUGGESTED decisions (regardless of threshold)
    all_suggested = await decision_repo.list_latest_by_scenario_and_state(
        compilation_id,
        MappingState.AI_SUGGESTED.value,
    )
    total_items = len(all_suggested)

    # Filter by confidence threshold
    eligible = [
        row for row in all_suggested
        if row.suggested_confidence is not None
        and row.suggested_confidence >= body.confidence_threshold
    ]

    actor_id = UUID(body.decided_by)
    approved_count = 0

    for decision_row in eligible:
        await decision_repo.create(
            mapping_decision_id=new_uuid7(),
            line_item_id=decision_row.line_item_id,
            scenario_spec_id=compilation_id,
            state=MappingState.APPROVED.value,
            suggested_sector_code=decision_row.suggested_sector_code,
            suggested_confidence=decision_row.suggested_confidence,
            final_sector_code=(
                decision_row.final_sector_code
                or decision_row.suggested_sector_code
            ),
            decision_type="APPROVED",
            decision_note=(
                f"Bulk approved "
                f"(threshold={body.confidence_threshold})"
            ),
            decided_by=actor_id,
        )
        approved_count += 1

    return BulkApproveResponse(
        approved_count=approved_count,
        skipped_count=total_items - approved_count,
        total_items=total_items,
    )


# ---------------------------------------------------------------------------
# B-8: Mapping audit trail (compiler-scoped)
# ---------------------------------------------------------------------------

_STATE_TO_ACTION: dict[str, str] = {
    "UNMAPPED": "reset",
    "AI_SUGGESTED": "suggest",
    "APPROVED": "approve",
    "OVERRIDDEN": "override",
    "MANAGER_REVIEW": "escalate",
    "EXCLUDED": "exclude",
    "LOCKED": "lock",
}


class AuditEntryResponse(BaseModel):
    action: str
    from_state: str | None
    to_state: str
    actor: str
    rationale: str | None
    timestamp: str


class AuditTrailResponse(BaseModel):
    entries: list[AuditEntryResponse]


@router.get(
    "/{workspace_id}/compiler/{compilation_id}/decisions/{line_item_id}/audit",
    response_model=AuditTrailResponse,
)
async def get_decision_audit_trail(
    workspace_id: UUID,
    compilation_id: UUID,
    line_item_id: UUID,
    comp_repo: CompilationRepository = Depends(get_compilation_repo),
    decision_repo: MappingDecisionRepository = Depends(get_mapping_decision_repo),
) -> AuditTrailResponse:
    """B-8: Get full audit trail for a line item's mapping decisions."""
    await _get_compilation_or_404(comp_repo, compilation_id, workspace_id)

    rows = await decision_repo.list_history(compilation_id, line_item_id)

    entries: list[AuditEntryResponse] = []
    prev_state: str | None = None
    for r in rows:
        to_state = r.state
        entries.append(AuditEntryResponse(
            action=_STATE_TO_ACTION.get(to_state, to_state.lower()),
            from_state=prev_state,
            to_state=to_state,
            actor=str(r.decided_by),
            rationale=r.decision_note,
            timestamp=r.decided_at.isoformat(),
        ))
        prev_state = to_state

    return AuditTrailResponse(entries=entries)
