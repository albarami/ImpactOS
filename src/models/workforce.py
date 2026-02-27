"""Pydantic schemas for the Workforce/Saudization Satellite — MVP-11.

Defines workforce enums, employment coefficients (versioned), sector-occupation
bridge (versioned), saudization rules (versioned), and immutable workforce
results with nationality splits, saudization gap ranges, and confidence-driven
sensitivity envelopes.

All 9 amendments incorporated:
- [1] delta_x_source + feasibility_result_id for feasible vector support
- [2] output_unit + base_year + delta_x_unit + coefficient_unit for unit safety
- [3] abs-based sensitivity bands for negative impacts
- [4] Bridge share validator with tolerance (UNMAPPED residual allowed)
- [5] NationalitySplit with unclassified 4th bucket
- [6] SaudizationGap with min/max projected Saudi %
- [7] Training fields on SaudizationGap
- [8] evidence_refs on all 4 sub-models
- [9] Idempotency fields on WorkforceResult
"""

from collections import defaultdict
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from src.models.common import (
    ConstraintConfidence,
    ImpactOSBase,
    UTCTimestamp,
    UUIDv7,
    new_uuid7,
    utc_now,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class NationalityTier(StrEnum):
    """Three-tier nationality classification for workforce planning."""

    SAUDI_READY = "SAUDI_READY"
    SAUDI_TRAINABLE = "SAUDI_TRAINABLE"
    EXPAT_RELIANT = "EXPAT_RELIANT"


class WorkforceConfidenceLevel(StrEnum):
    """Output quality confidence level for workforce results."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ---------------------------------------------------------------------------
# Sub-models (used inside versioned input models)
# ---------------------------------------------------------------------------


class SectorEmploymentCoefficient(ImpactOSBase):
    """Per-sector employment coefficient with confidence label."""

    sector_code: str = Field(..., min_length=1)
    jobs_per_million_sar: float = Field(
        ..., gt=0,
        description="Jobs created per million SAR of output change.",
    )
    confidence: ConstraintConfidence
    source_description: str = ""
    evidence_refs: list[UUID] = Field(default_factory=list)


class BridgeEntry(ImpactOSBase):
    """Maps a share of sector jobs to a specific occupation."""

    sector_code: str = Field(..., min_length=1)
    occupation_code: str = Field(..., min_length=1)
    share: float = Field(
        ..., ge=0.0, le=1.0,
        description="Proportion of sector jobs allocated to this occupation.",
    )
    confidence: ConstraintConfidence
    evidence_refs: list[UUID] = Field(default_factory=list)


class TierAssignment(ImpactOSBase):
    """Assigns a nationality tier to an occupation for Saudization analysis."""

    occupation_code: str = Field(..., min_length=1)
    nationality_tier: NationalityTier
    rationale: str = ""
    evidence_refs: list[UUID] = Field(default_factory=list)


class SectorSaudizationTarget(ImpactOSBase):
    """Policy target for Saudi workforce percentage in a sector."""

    sector_code: str = Field(..., min_length=1)
    target_saudi_pct: float = Field(
        ..., ge=0.0, le=1.0,
        description="Target Saudi workforce percentage (0-1).",
    )
    source: str = ""
    effective_year: int = Field(..., ge=1900, le=2100)
    evidence_refs: list[UUID] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Versioned input models (append-only, same pattern as ConstraintSet)
# ---------------------------------------------------------------------------


class EmploymentCoefficients(ImpactOSBase):
    """Versioned employment coefficients per sector.

    Amendment 2: Includes output_unit and base_year for unit safety.
    """

    employment_coefficients_id: UUIDv7 = Field(default_factory=new_uuid7)
    version: int = Field(default=1, ge=1)
    model_version_id: UUID
    workspace_id: UUID
    coefficients: list[SectorEmploymentCoefficient] = Field(default_factory=list)
    output_unit: Literal["SAR", "MILLION_SAR"] = Field(
        ...,
        description="Unit that delta_x must be in for these coefficients.",
    )
    base_year: int = Field(
        ..., ge=1900, le=2100,
        description="Reference year for these coefficients.",
    )
    created_at: UTCTimestamp = Field(default_factory=utc_now)

    def next_version(self) -> "EmploymentCoefficients":
        """Create the next version of these coefficients."""
        return self.model_copy(
            update={"version": self.version + 1, "created_at": utc_now()},
        )


class SectorOccupationBridge(ImpactOSBase):
    """Versioned sector-to-occupation bridge matrix.

    Amendment 4: Shares per sector may sum to < 1.0 (UNMAPPED residual).
    Validator rejects shares > 1.0 + tolerance.
    """

    bridge_id: UUIDv7 = Field(default_factory=new_uuid7)
    version: int = Field(default=1, ge=1)
    model_version_id: UUID
    workspace_id: UUID
    entries: list[BridgeEntry] = Field(default_factory=list)
    created_at: UTCTimestamp = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _validate_shares_per_sector(self) -> "SectorOccupationBridge":
        """Per-sector shares must not exceed 1.0 + tolerance."""
        sector_sums: dict[str, float] = defaultdict(float)
        for entry in self.entries:
            sector_sums[entry.sector_code] += entry.share
        tolerance = 1e-6
        for sector, total in sector_sums.items():
            if total > 1.0 + tolerance:
                raise ValueError(
                    f"Bridge shares for sector '{sector}' exceed 1.0: "
                    f"sum = {total:.6f}."
                )
        return self

    def next_version(self) -> "SectorOccupationBridge":
        """Create the next version of this bridge."""
        return self.model_copy(
            update={"version": self.version + 1, "created_at": utc_now()},
        )


class SaudizationRules(ImpactOSBase):
    """Versioned Saudization policy inputs (NOT model outputs).

    No model_version_id — rules are policy, not model-bound.
    """

    rules_id: UUIDv7 = Field(default_factory=new_uuid7)
    version: int = Field(default=1, ge=1)
    workspace_id: UUID
    tier_assignments: list[TierAssignment] = Field(default_factory=list)
    sector_targets: list[SectorSaudizationTarget] = Field(default_factory=list)
    created_at: UTCTimestamp = Field(default_factory=utc_now)

    def next_version(self) -> "SaudizationRules":
        """Create the next version of these rules."""
        return self.model_copy(
            update={"version": self.version + 1, "created_at": utc_now()},
        )


# ---------------------------------------------------------------------------
# Frozen output models (immutable results)
# ---------------------------------------------------------------------------


class SectorEmployment(ImpactOSBase, frozen=True):
    """Per-sector employment figures from the workforce satellite."""

    sector_code: str
    total_jobs: float
    direct_jobs: float
    indirect_jobs: float
    confidence: ConstraintConfidence


class OccupationBreakdown(ImpactOSBase, frozen=True):
    """Occupation-level job breakdown within a sector."""

    occupation_code: str
    jobs: float
    share_of_sector: float = Field(..., ge=0.0, le=1.0)
    confidence: ConstraintConfidence


class NationalitySplit(ImpactOSBase, frozen=True):
    """Nationality-tier split for a sector's jobs.

    Amendment 5: Includes 'unclassified' bucket — missing tier assignments
    go here, NOT into expat_reliant.
    """

    sector_code: str
    total_jobs: float
    saudi_ready: float
    saudi_trainable: float
    expat_reliant: float
    unclassified: float

    @model_validator(mode="after")
    def _validate_sum(self) -> "NationalitySplit":
        """total_jobs must equal sum of all four buckets (within tolerance)."""
        bucket_sum = (
            self.saudi_ready + self.saudi_trainable
            + self.expat_reliant + self.unclassified
        )
        if abs(self.total_jobs - bucket_sum) > 1.0:
            raise ValueError(
                f"total_jobs ({self.total_jobs}) does not match sum of buckets "
                f"({bucket_sum}). Difference: {abs(self.total_jobs - bucket_sum):.4f}."
            )
        return self


class SaudizationGap(ImpactOSBase, frozen=True):
    """Saudization gap analysis with min/max range.

    Amendment 6: Conservative (saudi_ready only) vs optimistic
    (saudi_ready + saudi_trainable) projected Saudi percentages.
    Amendment 7: Training pipeline fields for future enrichment.
    """

    sector_code: str
    projected_saudi_pct_min: float = Field(
        ...,
        description="Conservative: saudi_ready / total (Saudi-ready only).",
    )
    projected_saudi_pct_max: float = Field(
        ...,
        description="Optimistic: (saudi_ready + saudi_trainable) / total.",
    )
    target_saudi_pct: float
    gap_pct_min: float = Field(
        ...,
        description="target - projected_max (gap even with training).",
    )
    gap_pct_max: float = Field(
        ...,
        description="target - projected_min (gap without training).",
    )
    gap_jobs_min: int
    gap_jobs_max: int
    achievability_assessment: str = Field(
        ...,
        description=(
            "One of: ON_TRACK, ACHIEVABLE_WITH_TRAINING, MODERATE_GAP, "
            "SIGNIFICANT_GAP, CRITICAL_GAP, INSUFFICIENT_DATA."
        ),
    )
    estimated_training_duration_months: int | None = None
    training_capacity_note: str = ""


class SensitivityEnvelope(ImpactOSBase, frozen=True):
    """Confidence-driven sensitivity range for sector employment.

    Amendment 3: Uses abs(base) * band for correct ordering
    with both positive and negative impacts.
    """

    sector_code: str
    base_jobs: float
    low_jobs: float
    high_jobs: float
    confidence_band_pct: float

    @model_validator(mode="after")
    def _validate_ordering(self) -> "SensitivityEnvelope":
        """low_jobs <= base_jobs <= high_jobs must hold."""
        if self.low_jobs > self.base_jobs + 1e-6:
            raise ValueError(
                f"low_jobs ({self.low_jobs}) must be <= base_jobs ({self.base_jobs})."
            )
        if self.high_jobs < self.base_jobs - 1e-6:
            raise ValueError(
                f"high_jobs ({self.high_jobs}) must be >= base_jobs ({self.base_jobs})."
            )
        return self


# ---------------------------------------------------------------------------
# Confidence summary
# ---------------------------------------------------------------------------


class WorkforceConfidenceSummary(ImpactOSBase, frozen=True):
    """Aggregated confidence breakdown for a workforce result."""

    output_weighted_coefficient_confidence: float = Field(..., ge=0.0, le=1.0)
    bridge_coverage_pct: float = Field(..., ge=0.0, le=1.0)
    rule_coverage_pct: float = Field(..., ge=0.0, le=1.0)
    overall_confidence: WorkforceConfidenceLevel
    data_quality_notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# WorkforceResult (immutable aggregate)
# ---------------------------------------------------------------------------


class WorkforceResult(ImpactOSBase, frozen=True):
    """Immutable workforce satellite result.

    Amendment 1: delta_x_source + feasibility_result_id for feasible vectors.
    Amendment 2: delta_x_unit + coefficient_unit for audit trail.
    """

    workforce_result_id: UUIDv7 = Field(default_factory=new_uuid7)
    run_id: UUID
    workspace_id: UUID

    # Core results
    sector_employment: dict[str, SectorEmployment] = Field(default_factory=dict)
    occupation_breakdowns: dict[str, list[OccupationBreakdown]] = Field(
        default_factory=dict,
    )
    nationality_splits: dict[str, NationalitySplit] = Field(default_factory=dict)
    saudization_gaps: dict[str, SaudizationGap] = Field(default_factory=dict)
    sensitivity_envelopes: dict[str, SensitivityEnvelope] = Field(default_factory=dict)
    confidence_summary: WorkforceConfidenceSummary

    # Input version tracking (reproducibility)
    employment_coefficients_id: UUID
    employment_coefficients_version: int = Field(..., ge=1)
    bridge_id: UUID | None = None
    bridge_version: int | None = None
    rules_id: UUID | None = None
    rules_version: int | None = None
    satellite_coefficients_hash: str
    data_quality_notes: list[str] = Field(default_factory=list)

    # Amendment 1: Feasibility integration
    delta_x_source: Literal["unconstrained", "feasible"]
    feasibility_result_id: UUID | None = None

    # Amendment 2: Unit metadata
    delta_x_unit: str
    coefficient_unit: str

    created_at: UTCTimestamp = Field(default_factory=utc_now)
