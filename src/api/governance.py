"""FastAPI governance endpoints — MVP-5.

POST /v1/workspaces/{workspace_id}/governance/claims/extract   — extract claims
POST /v1/workspaces/{workspace_id}/governance/nff/check        — NFF gate check
POST /v1/workspaces/{workspace_id}/governance/assumptions      — create assumption
POST /v1/workspaces/{workspace_id}/governance/assumptions/{id}/approve — approve
GET  /v1/workspaces/{workspace_id}/governance/status/{run_id}  — governance status
GET  /v1/workspaces/{workspace_id}/governance/blocking-reasons/{run_id}

S0-4: Workspace-scoped routes.
Deterministic — no LLM calls.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.auth_deps import WorkspaceMember, require_workspace_member
from src.api.dependencies import (
    get_assumption_repo,
    get_claim_repo,
    get_evidence_snippet_repo,
    get_run_snapshot_repo,
)
from src.governance.claim_extractor import ClaimExtractor
from src.governance.publication_gate import PublicationGate
from src.models.common import (
    AssumptionType,
    ClaimStatus,
    ClaimType,
    DisclosureTier,
)
from src.models.governance import VALID_CLAIM_TRANSITIONS, Assumption, Claim
from src.repositories.engine import RunSnapshotRepository
from src.repositories.governance import (
    AssumptionRepository,
    ClaimRepository,
    EvidenceSnippetRepository,
)

router = APIRouter(prefix="/v1/workspaces", tags=["governance"])

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
    workspace_id: str | None = None  # Optional — workspace_id from path takes precedence
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


# --- B-11: Claim list / detail / update schemas ---


class ClaimListItem(BaseModel):
    claim_id: str
    text: str
    claim_type: str
    status: str
    disclosure_tier: str
    created_at: str
    updated_at: str


class ClaimListResponse(BaseModel):
    items: list[ClaimListItem]
    total: int


class ClaimDetailResponse(BaseModel):
    claim_id: str
    text: str
    claim_type: str
    status: str
    disclosure_tier: str
    model_refs: list
    evidence_refs: list
    run_id: str | None
    created_at: str
    updated_at: str


class UpdateClaimRequest(BaseModel):
    status: str
    resolution_text: str | None = None
    resolved_by: str | None = None


class UpdateClaimResponse(BaseModel):
    claim_id: str
    status: str
    updated_at: str


# --- B-7: Evidence list / detail / link schemas ---


class EvidenceListItem(BaseModel):
    snippet_id: str
    source_id: str
    page: int
    extracted_text: str
    checksum: str
    created_at: str


class EvidenceListResponse(BaseModel):
    items: list[EvidenceListItem]
    total: int


class BBoxResponse(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class EvidenceDetailResponse(BaseModel):
    snippet_id: str
    source_id: str
    page: int
    bbox: BBoxResponse
    extracted_text: str
    table_cell_ref: dict | None = None
    checksum: str
    created_at: str


class LinkEvidenceRequest(BaseModel):
    evidence_ids: list[str]


class LinkEvidenceResponse(BaseModel):
    claim_id: str
    evidence_ids: list[str]
    total_linked: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_claim(row: object) -> Claim:
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


@router.post("/{workspace_id}/governance/claims/extract", response_model=ExtractClaimsResponse)
async def extract_claims(
    workspace_id: UUID,
    body: ExtractClaimsRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    claim_repo: ClaimRepository = Depends(get_claim_repo),
) -> ExtractClaimsResponse:
    """Extract atomic claims from draft narrative text."""
    result = _extractor.extract(
        draft_text=body.draft_text,
        workspace_id=workspace_id,
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


@router.post("/{workspace_id}/governance/nff/check", response_model=NFFCheckResponse)
async def nff_check(
    workspace_id: UUID,
    body: NFFCheckRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
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


@router.post(
    "/{workspace_id}/governance/assumptions",
    status_code=201,
    response_model=CreateAssumptionResponse,
)
async def create_assumption(
    workspace_id: UUID,
    body: CreateAssumptionRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
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


@router.post(
    "/{workspace_id}/governance/assumptions/{assumption_id}/approve",
    response_model=ApproveAssumptionResponse,
)
async def approve_assumption(
    workspace_id: UUID,
    assumption_id: UUID,
    body: ApproveAssumptionRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
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
            detail=(
                f"Cannot approve: assumption {assumption_id}"
                f" is not DRAFT (currently {row.status})."
            ),
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


@router.get("/{workspace_id}/governance/status/{run_id}", response_model=GovernanceStatusResponse)
async def get_governance_status(
    workspace_id: UUID,
    run_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
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


@router.get(
    "/{workspace_id}/governance/blocking-reasons/{run_id}",
    response_model=BlockingReasonsResponse,
)
async def get_blocking_reasons(
    workspace_id: UUID,
    run_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
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


# ---------------------------------------------------------------------------
# B-11: Claim list / detail / update
# Workspace ownership enforced via run_id → RunSnapshot.workspace_id join.
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/governance/claims", response_model=ClaimListResponse)
async def list_claims(
    workspace_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    claim_repo: ClaimRepository = Depends(get_claim_repo),
    run_id: UUID | None = Query(default=None, description="Filter claims by run_id"),
) -> ClaimListResponse:
    """List claims, optionally filtered by run_id.

    When run_id is provided, only claims whose run belongs to this workspace
    are returned (workspace-safe join).
    """
    if run_id is not None:
        rows = await claim_repo.get_by_run_for_workspace(run_id, workspace_id)
    else:
        rows = await claim_repo.list_all()

    items = [
        ClaimListItem(
            claim_id=str(r.claim_id),
            text=r.text,
            claim_type=r.claim_type,
            status=r.status,
            disclosure_tier=r.disclosure_tier,
            created_at=r.created_at.isoformat(),
            updated_at=r.updated_at.isoformat(),
        )
        for r in rows
    ]
    return ClaimListResponse(items=items, total=len(items))


@router.get(
    "/{workspace_id}/governance/claims/{claim_id}",
    response_model=ClaimDetailResponse,
)
async def get_claim_detail(
    workspace_id: UUID,
    claim_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    claim_repo: ClaimRepository = Depends(get_claim_repo),
) -> ClaimDetailResponse:
    """Get a single claim by ID (workspace-scoped via run linkage)."""
    row = await claim_repo.get_for_workspace(claim_id, workspace_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found.")

    return ClaimDetailResponse(
        claim_id=str(row.claim_id),
        text=row.text,
        claim_type=row.claim_type,
        status=row.status,
        disclosure_tier=row.disclosure_tier,
        model_refs=row.model_refs or [],
        evidence_refs=row.evidence_refs or [],
        run_id=str(row.run_id) if row.run_id else None,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@router.put(
    "/{workspace_id}/governance/claims/{claim_id}",
    response_model=UpdateClaimResponse,
)
async def update_claim_status(
    workspace_id: UUID,
    claim_id: UUID,
    body: UpdateClaimRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    claim_repo: ClaimRepository = Depends(get_claim_repo),
) -> UpdateClaimResponse:
    """Update a claim's status with state-machine transition validation.

    Returns 409 if the requested transition is not allowed.
    Returns 404 if claim not found or wrong workspace.
    """
    row = await claim_repo.get_for_workspace(claim_id, workspace_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found.")

    current_status = ClaimStatus(row.status)
    try:
        target_status = ClaimStatus(body.status)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status value: {body.status}",
        ) from exc

    allowed = VALID_CLAIM_TRANSITIONS.get(current_status, frozenset())
    if target_status not in allowed:
        allowed_names = sorted(s.value for s in allowed) if allowed else []
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot transition from {current_status.value} to {target_status.value}. "
                f"Allowed transitions: {allowed_names}"
            ),
        )

    updated = await claim_repo.update_status(claim_id, target_status.value)
    return UpdateClaimResponse(
        claim_id=str(updated.claim_id),
        status=updated.status,
        updated_at=updated.updated_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# B-7: Evidence list / detail / link
# Workspace ownership enforced via source_id → Document.workspace_id join.
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/governance/evidence", response_model=EvidenceListResponse)
async def list_evidence(
    workspace_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    run_id: UUID | None = Query(default=None, description="Filter evidence by run_id"),
    evidence_repo: EvidenceSnippetRepository = Depends(get_evidence_snippet_repo),
    run_snapshot_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
) -> EvidenceListResponse:
    """B-7: List evidence snippets scoped to a run within a workspace.

    Returns 404 if run_id does not exist or belongs to another workspace.
    Returns only evidence snippets linked to claims in the specified run.
    """
    if run_id is not None:
        snapshot = await run_snapshot_repo.get(run_id)
        if snapshot is None:
            raise HTTPException(
                status_code=404, detail=f"Run {run_id} not found.",
            )
        if snapshot.workspace_id != workspace_id:
            raise HTTPException(
                status_code=404, detail=f"Run {run_id} not found.",
            )
        rows = await evidence_repo.list_by_run_for_workspace(run_id, workspace_id)
    else:
        rows = await evidence_repo.list_by_workspace(workspace_id)

    items = [
        EvidenceListItem(
            snippet_id=str(r.snippet_id),
            source_id=str(r.source_id),
            page=r.page,
            extracted_text=r.extracted_text,
            checksum=r.checksum,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]
    return EvidenceListResponse(items=items, total=len(items))


@router.get(
    "/{workspace_id}/governance/evidence/{snippet_id}",
    response_model=EvidenceDetailResponse,
)
async def get_evidence_detail(
    workspace_id: UUID,
    snippet_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    evidence_repo: EvidenceSnippetRepository = Depends(get_evidence_snippet_repo),
) -> EvidenceDetailResponse:
    """B-7: Get evidence snippet detail (workspace-scoped via document)."""
    row = await evidence_repo.get_for_workspace(snippet_id, workspace_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Evidence snippet {snippet_id} not found.")
    return EvidenceDetailResponse(
        snippet_id=str(row.snippet_id),
        source_id=str(row.source_id),
        page=row.page,
        bbox=BBoxResponse(x0=row.bbox_x0, y0=row.bbox_y0, x1=row.bbox_x1, y1=row.bbox_y1),
        extracted_text=row.extracted_text,
        table_cell_ref=row.table_cell_ref,
        checksum=row.checksum,
        created_at=row.created_at.isoformat(),
    )


@router.post(
    "/{workspace_id}/governance/claims/{claim_id}/evidence",
    response_model=LinkEvidenceResponse,
)
async def link_evidence_to_claim(
    workspace_id: UUID,
    claim_id: UUID,
    body: LinkEvidenceRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    evidence_repo: EvidenceSnippetRepository = Depends(get_evidence_snippet_repo),
    claim_repo: ClaimRepository = Depends(get_claim_repo),
) -> LinkEvidenceResponse:
    """B-7: Link evidence snippets to a claim (workspace-scoped, with dedupe)."""
    claim_row = await claim_repo.get_for_workspace(claim_id, workspace_id)
    if claim_row is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found.")

    validated_ids: list[UUID] = []
    for eid_str in body.evidence_ids:
        eid = UUID(eid_str)
        snippet_row = await evidence_repo.get_for_workspace(eid, workspace_id)
        if snippet_row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Evidence snippet {eid_str} not found.",
            )
        validated_ids.append(eid)

    updated = await claim_repo.link_evidence_many(claim_id, validated_ids)
    return LinkEvidenceResponse(
        claim_id=str(claim_id),
        evidence_ids=[str(eid) for eid in validated_ids],
        total_linked=len(updated.evidence_refs) if updated else 0,
    )
