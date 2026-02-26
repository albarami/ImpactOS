"""FastAPI governance endpoints — MVP-5.

POST /v1/governance/claims/extract           — extract claims from draft text
POST /v1/governance/nff/check                — NFF gate check
POST /v1/governance/assumptions              — create assumption
POST /v1/governance/assumptions/{id}/approve — approve assumption
GET  /v1/governance/status/{run_id}          — governance status for a run
GET  /v1/governance/blocking-reasons/{run_id}— blocking reasons for a run

Deterministic — no LLM calls.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.governance.assumption_registry import AssumptionRegistry
from src.governance.claim_extractor import ClaimExtractor
from src.governance.publication_gate import PublicationGate
from src.models.common import AssumptionType, ClaimStatus
from src.models.governance import Assumption, AssumptionRange

router = APIRouter(prefix="/v1/governance", tags=["governance"])

# ---------------------------------------------------------------------------
# In-memory stores (MVP — replaced by PostgreSQL in production)
# ---------------------------------------------------------------------------

_extractor = ClaimExtractor()
_gate = PublicationGate()
_assumption_registry = AssumptionRegistry()

# In-memory claim store keyed by claim_id
_claims: dict[UUID, dict] = {}
# run_id → list of claim_ids
_run_claims: dict[UUID, list[UUID]] = {}


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ExtractClaimsRequest(BaseModel):
    draft_text: str
    workspace_id: str
    run_id: str


class ClaimResponse(BaseModel):
    claim_id: str
    text: str
    claim_type: str
    status: str


class ExtractClaimsResponse(BaseModel):
    claims: list[ClaimResponse]
    total: int
    needs_evidence_count: int


class NFFCheckRequest(BaseModel):
    claim_ids: list[str]


class BlockingReasonResponse(BaseModel):
    claim_id: str
    current_status: str
    reason: str


class NFFCheckResponse(BaseModel):
    passed: bool
    total_claims: int
    blocking_reasons: list[BlockingReasonResponse]


class CreateAssumptionRequest(BaseModel):
    type: str
    value: float
    units: str
    justification: str


class CreateAssumptionResponse(BaseModel):
    assumption_id: str
    status: str


class ApproveAssumptionRequest(BaseModel):
    range_min: float | None = None
    range_max: float | None = None
    actor: str


class ApproveAssumptionResponse(BaseModel):
    assumption_id: str
    status: str
    range_min: float | None = None
    range_max: float | None = None


class GovernanceStatusResponse(BaseModel):
    run_id: str
    claims_total: int
    claims_resolved: int
    claims_unresolved: int
    assumptions_total: int
    assumptions_approved: int
    nff_passed: bool


class BlockingReasonsResponse(BaseModel):
    run_id: str
    blocking_reasons: list[BlockingReasonResponse]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/claims/extract", response_model=ExtractClaimsResponse)
async def extract_claims(body: ExtractClaimsRequest) -> ExtractClaimsResponse:
    """Extract atomic claims from draft narrative text."""
    result = _extractor.extract(
        draft_text=body.draft_text,
        workspace_id=UUID(body.workspace_id),
        run_id=UUID(body.run_id),
    )

    run_id = UUID(body.run_id)
    claim_responses: list[ClaimResponse] = []

    for claim in result.claims:
        # Store claim for later retrieval
        _claims[claim.claim_id] = {
            "claim": claim,
            "run_id": run_id,
        }
        _run_claims.setdefault(run_id, []).append(claim.claim_id)

        claim_responses.append(ClaimResponse(
            claim_id=str(claim.claim_id),
            text=claim.text,
            claim_type=claim.claim_type.value,
            status=claim.status.value,
        ))

    return ExtractClaimsResponse(
        claims=claim_responses,
        total=result.total,
        needs_evidence_count=result.needs_evidence_count,
    )


@router.post("/nff/check", response_model=NFFCheckResponse)
async def nff_check(body: NFFCheckRequest) -> NFFCheckResponse:
    """NFF gate: validate claims are supported or resolved."""
    from src.models.governance import Claim as ClaimModel

    claims: list[ClaimModel] = []
    for cid_str in body.claim_ids:
        cid = UUID(cid_str)
        entry = _claims.get(cid)
        if entry is not None:
            claims.append(entry["claim"])

    gate_result = _gate.check(claims)

    blocking = [
        BlockingReasonResponse(
            claim_id=str(br.claim_id),
            current_status=br.current_status.value,
            reason=br.reason,
        )
        for br in gate_result.blocking_reasons
    ]

    return NFFCheckResponse(
        passed=gate_result.passed,
        total_claims=gate_result.total_claims,
        blocking_reasons=blocking,
    )


@router.post("/assumptions", status_code=201, response_model=CreateAssumptionResponse)
async def create_assumption(body: CreateAssumptionRequest) -> CreateAssumptionResponse:
    """Create a new assumption (draft status)."""
    assumption = Assumption(
        type=AssumptionType(body.type),
        value=body.value,
        units=body.units,
        justification=body.justification,
    )
    _assumption_registry.register(assumption)

    return CreateAssumptionResponse(
        assumption_id=str(assumption.assumption_id),
        status=assumption.status.value,
    )


@router.post("/assumptions/{assumption_id}/approve", response_model=ApproveAssumptionResponse)
async def approve_assumption(
    assumption_id: UUID,
    body: ApproveAssumptionRequest,
) -> ApproveAssumptionResponse:
    """Approve an assumption — requires sensitivity range."""
    if body.range_min is None or body.range_max is None:
        raise HTTPException(
            status_code=400,
            detail="Approved assumptions must include range_min and range_max.",
        )

    try:
        approved = _assumption_registry.approve(
            assumption_id=assumption_id,
            range_=AssumptionRange(min=body.range_min, max=body.range_max),
            actor=UUID(body.actor),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ApproveAssumptionResponse(
        assumption_id=str(approved.assumption_id),
        status=approved.status.value,
        range_min=approved.range.min if approved.range else None,
        range_max=approved.range.max if approved.range else None,
    )


@router.get("/status/{run_id}", response_model=GovernanceStatusResponse)
async def get_governance_status(run_id: UUID) -> GovernanceStatusResponse:
    """Get governance status for a run."""
    # Collect claims for this run
    claim_ids = _run_claims.get(run_id, [])
    claims = [_claims[cid]["claim"] for cid in claim_ids if cid in _claims]

    resolved_states = {
        ClaimStatus.SUPPORTED,
        ClaimStatus.APPROVED_FOR_EXPORT,
        ClaimStatus.REWRITTEN_AS_ASSUMPTION,
        ClaimStatus.DELETED,
    }
    resolved = sum(1 for c in claims if c.status in resolved_states)

    # Collect assumptions
    all_assumptions = _assumption_registry.list_all()
    approved_count = sum(1 for a in all_assumptions if a.status.value == "APPROVED")

    # NFF check
    gate_result = _gate.check(claims)

    return GovernanceStatusResponse(
        run_id=str(run_id),
        claims_total=len(claims),
        claims_resolved=resolved,
        claims_unresolved=len(claims) - resolved,
        assumptions_total=len(all_assumptions),
        assumptions_approved=approved_count,
        nff_passed=gate_result.passed,
    )


@router.get("/blocking-reasons/{run_id}", response_model=BlockingReasonsResponse)
async def get_blocking_reasons(run_id: UUID) -> BlockingReasonsResponse:
    """Get blocking reasons for a run."""
    claim_ids = _run_claims.get(run_id, [])
    claims = [_claims[cid]["claim"] for cid in claim_ids if cid in _claims]

    gate_result = _gate.check(claims)

    blocking = [
        BlockingReasonResponse(
            claim_id=str(br.claim_id),
            current_status=br.current_status.value,
            reason=br.reason,
        )
        for br in gate_result.blocking_reasons
    ]

    return BlockingReasonsResponse(
        run_id=str(run_id),
        blocking_reasons=blocking,
    )
