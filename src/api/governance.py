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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.dependencies import get_assumption_repo, get_claim_repo
from src.governance.claim_extractor import ClaimExtractor
from src.governance.publication_gate import PublicationGate
from src.models.common import AssumptionStatus, AssumptionType, ClaimStatus, ClaimType, DisclosureTier
from src.models.governance import Assumption, AssumptionRange, Claim
from src.repositories.governance import AssumptionRepository, ClaimRepository

router = APIRouter(prefix="/v1/governance", tags=["governance"])

# ---------------------------------------------------------------------------
# Stateless services (no DB needed)
# ---------------------------------------------------------------------------

_extractor = ClaimExtractor()
_gate = PublicationGate()


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
# Helpers
# ---------------------------------------------------------------------------


def _row_to_claim(row) -> Claim:
    """Convert ClaimRow to Claim Pydantic model for gate checks."""
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


@router.post("/claims/extract", response_model=ExtractClaimsResponse)
async def extract_claims(
    body: ExtractClaimsRequest,
    claim_repo: ClaimRepository = Depends(get_claim_repo),
) -> ExtractClaimsResponse:
    """Extract atomic claims from draft narrative text."""
    result = _extractor.extract(
        draft_text=body.draft_text,
        workspace_id=UUID(body.workspace_id),
        run_id=UUID(body.run_id),
    )

    run_id = UUID(body.run_id)
    claim_responses: list[ClaimResponse] = []

    for claim in result.claims:
        await claim_repo.create(
            claim_id=claim.claim_id,
            text=claim.text,
            claim_type=claim.claim_type.value,
            status=claim.status.value,
            disclosure_tier=claim.disclosure_tier.value,
            model_refs=[mr.model_dump() for mr in claim.model_refs] if claim.model_refs else [],
            evidence_refs=[str(er) for er in claim.evidence_refs] if claim.evidence_refs else [],
            run_id=run_id,
        )

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
async def nff_check(
    body: NFFCheckRequest,
    claim_repo: ClaimRepository = Depends(get_claim_repo),
) -> NFFCheckResponse:
    """NFF gate: validate claims are supported or resolved."""
    claims: list[Claim] = []
    for cid_str in body.claim_ids:
        cid = UUID(cid_str)
        row = await claim_repo.get(cid)
        if row is not None:
            claims.append(_row_to_claim(row))

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
async def create_assumption(
    body: CreateAssumptionRequest,
    assumption_repo: AssumptionRepository = Depends(get_assumption_repo),
) -> CreateAssumptionResponse:
    """Create a new assumption (draft status)."""
    assumption = Assumption(
        type=AssumptionType(body.type),
        value=body.value,
        units=body.units,
        justification=body.justification,
    )

    await assumption_repo.create(
        assumption_id=assumption.assumption_id,
        type=assumption.type.value,
        value=assumption.value,
        units=assumption.units,
        justification=assumption.justification,
        evidence_refs=[str(er) for er in assumption.evidence_refs],
        status=assumption.status.value,
    )

    return CreateAssumptionResponse(
        assumption_id=str(assumption.assumption_id),
        status=assumption.status.value,
    )


@router.post("/assumptions/{assumption_id}/approve", response_model=ApproveAssumptionResponse)
async def approve_assumption(
    assumption_id: UUID,
    body: ApproveAssumptionRequest,
    assumption_repo: AssumptionRepository = Depends(get_assumption_repo),
) -> ApproveAssumptionResponse:
    """Approve an assumption — requires sensitivity range."""
    if body.range_min is None or body.range_max is None:
        raise HTTPException(
            status_code=400,
            detail="Approved assumptions must include range_min and range_max.",
        )

    row = await assumption_repo.get(assumption_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Assumption {assumption_id} not found.")

    if row.status != "DRAFT":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve: assumption {assumption_id} is not DRAFT (currently {row.status}).",
        )

    range_json = {"min": body.range_min, "max": body.range_max}
    updated = await assumption_repo.approve(
        assumption_id=assumption_id,
        range_json=range_json,
        actor=UUID(body.actor),
    )

    return ApproveAssumptionResponse(
        assumption_id=str(updated.assumption_id),
        status=updated.status,
        range_min=updated.range_json.get("min") if updated.range_json else None,
        range_max=updated.range_json.get("max") if updated.range_json else None,
    )


@router.get("/status/{run_id}", response_model=GovernanceStatusResponse)
async def get_governance_status(
    run_id: UUID,
    claim_repo: ClaimRepository = Depends(get_claim_repo),
    assumption_repo: AssumptionRepository = Depends(get_assumption_repo),
) -> GovernanceStatusResponse:
    """Get governance status for a run."""
    claim_rows = await claim_repo.get_by_run(run_id)
    claims = [_row_to_claim(r) for r in claim_rows]

    resolved_states = {
        ClaimStatus.SUPPORTED,
        ClaimStatus.APPROVED_FOR_EXPORT,
        ClaimStatus.REWRITTEN_AS_ASSUMPTION,
        ClaimStatus.DELETED,
    }
    resolved = sum(1 for c in claims if c.status in resolved_states)

    all_assumptions = await assumption_repo.list_all()
    approved_count = sum(1 for a in all_assumptions if a.status == "APPROVED")

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
async def get_blocking_reasons(
    run_id: UUID,
    claim_repo: ClaimRepository = Depends(get_claim_repo),
) -> BlockingReasonsResponse:
    """Get blocking reasons for a run."""
    claim_rows = await claim_repo.get_by_run(run_id)
    claims = [_row_to_claim(r) for r in claim_rows]

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
