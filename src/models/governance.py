"""Governance models — Assumption, Claim, EvidenceSnippet (NFF governance)."""

from uuid import UUID

from pydantic import Field, model_validator

from src.models.common import (
    AssumptionStatus,
    AssumptionType,
    ClaimStatus,
    ClaimType,
    DisclosureTier,
    ImpactOSBase,
    UTCTimestamp,
    UUIDv7,
    new_uuid7,
    utc_now,
)


# ---------------------------------------------------------------------------
# Valid claim status transitions (state machine)
# ---------------------------------------------------------------------------

VALID_CLAIM_TRANSITIONS: dict[ClaimStatus, frozenset[ClaimStatus]] = {
    ClaimStatus.EXTRACTED: frozenset({
        ClaimStatus.NEEDS_EVIDENCE,
        ClaimStatus.SUPPORTED,
        ClaimStatus.DELETED,
    }),
    ClaimStatus.NEEDS_EVIDENCE: frozenset({
        ClaimStatus.SUPPORTED,
        ClaimStatus.REWRITTEN_AS_ASSUMPTION,
        ClaimStatus.DELETED,
    }),
    ClaimStatus.SUPPORTED: frozenset({
        ClaimStatus.APPROVED_FOR_EXPORT,
        ClaimStatus.DELETED,
    }),
    ClaimStatus.REWRITTEN_AS_ASSUMPTION: frozenset({
        ClaimStatus.DELETED,
    }),
    ClaimStatus.DELETED: frozenset(),
    ClaimStatus.APPROVED_FOR_EXPORT: frozenset(),
}


# ---------------------------------------------------------------------------
# Bounding box for evidence coordinates
# ---------------------------------------------------------------------------


class BoundingBox(ImpactOSBase):
    """Normalised page coordinates (0..1) for an evidence snippet."""

    x0: float = Field(..., ge=0.0, le=1.0)
    y0: float = Field(..., ge=0.0, le=1.0)
    x1: float = Field(..., ge=0.0, le=1.0)
    y1: float = Field(..., ge=0.0, le=1.0)


class TableCellRef(ImpactOSBase):
    """Pointer to a specific cell in an extracted table."""

    table_id: str = Field(..., min_length=1)
    row: int = Field(..., ge=0)
    col: int = Field(..., ge=0)


# ---------------------------------------------------------------------------
# Assumption (versioned, governed — Appendix B)
# ---------------------------------------------------------------------------


class AssumptionRange(ImpactOSBase):
    """Sensitivity range for an approved assumption."""

    min: float
    max: float

    @model_validator(mode="after")
    def _max_ge_min(self) -> "AssumptionRange":
        if self.max < self.min:
            msg = "max must be >= min"
            raise ValueError(msg)
        return self


class Assumption(ImpactOSBase):
    """Governed assumption per Appendix B.

    When status is APPROVED, a range must be provided for sensitivity analysis.
    """

    assumption_id: UUIDv7 = Field(default_factory=new_uuid7)
    type: AssumptionType
    value: float
    range: AssumptionRange | None = None
    units: str = Field(..., min_length=1, max_length=50)
    justification: str = Field(..., min_length=1, max_length=5000)
    evidence_refs: list[UUID] = Field(default_factory=list)
    status: AssumptionStatus = Field(default=AssumptionStatus.DRAFT)
    approved_by: UUID | None = None
    approved_at: UTCTimestamp | None = None
    created_at: UTCTimestamp = Field(default_factory=utc_now)
    updated_at: UTCTimestamp = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _approved_requires_range(self) -> "Assumption":
        if self.status == AssumptionStatus.APPROVED and self.range is None:
            msg = "Approved assumptions must include a sensitivity range."
            raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# Model reference for claims
# ---------------------------------------------------------------------------


class ModelRef(ImpactOSBase):
    """Reference linking a claim to a specific model run metric."""

    run_id: UUID
    metric: str = Field(..., min_length=1)
    value: float


# ---------------------------------------------------------------------------
# Claim (versioned, governed — Appendix C)
# ---------------------------------------------------------------------------


class Claim(ImpactOSBase):
    """Governed claim per NFF governance (Appendix C).

    Claims must be typed and resolved before governed export is permitted.
    """

    claim_id: UUIDv7 = Field(default_factory=new_uuid7)
    text: str = Field(..., min_length=1, max_length=5000)
    claim_type: ClaimType
    status: ClaimStatus = Field(default=ClaimStatus.EXTRACTED)
    disclosure_tier: DisclosureTier = Field(default=DisclosureTier.TIER0)
    model_refs: list[ModelRef] = Field(default_factory=list)
    evidence_refs: list[UUID] = Field(default_factory=list)
    created_at: UTCTimestamp = Field(default_factory=utc_now)
    updated_at: UTCTimestamp = Field(default_factory=utc_now)

    def transition_to(self, new_status: ClaimStatus) -> "Claim":
        """Return a copy with the new status if the transition is valid.

        Raises:
            ValueError: If the transition is not allowed by the state machine.
        """
        allowed = VALID_CLAIM_TRANSITIONS.get(self.status, frozenset())
        if new_status not in allowed:
            msg = f"Cannot transition from {self.status} to {new_status}."
            raise ValueError(msg)
        from src.models.common import utc_now

        return self.model_copy(update={"status": new_status, "updated_at": utc_now()})


# ---------------------------------------------------------------------------
# EvidenceSnippet (immutable — Appendix C / Section 5.4)
# ---------------------------------------------------------------------------


class EvidenceSnippet(ImpactOSBase, frozen=True):
    """Immutable fine-grained source reference for audit-grade traceability."""

    snippet_id: UUIDv7 = Field(default_factory=new_uuid7)
    source_id: UUID
    page: int = Field(..., ge=0, description="0-indexed page number.")
    bbox: BoundingBox
    extracted_text: str = Field(..., min_length=1)
    table_cell_ref: TableCellRef | None = None
    checksum: str = Field(
        ...,
        pattern=r"^sha256:[a-f0-9]{64}$",
        description="SHA-256 hash of the source document.",
    )
    created_at: UTCTimestamp = Field(default_factory=utc_now)
