"""Scenario models — ScenarioSpec, ShockItem variants, DataQualitySummary."""

from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import Field, model_validator

from src.models.common import (
    ConstraintConfidence,
    DisclosureTier,
    ImpactOSBase,
    UTCTimestamp,
    UUIDv7,
    new_uuid7,
    utc_now,
)


# ---------------------------------------------------------------------------
# Shock item variants (union type per Appendix A)
# ---------------------------------------------------------------------------


class FinalDemandShock(ImpactOSBase):
    """Final demand injection into a sector for a given year."""

    type: Literal["FINAL_DEMAND_SHOCK"] = "FINAL_DEMAND_SHOCK"
    sector_code: str = Field(..., min_length=1)
    year: int = Field(..., ge=1900, le=2100)
    amount_real_base_year: float = Field(..., description="Real base-year currency amount.")
    domestic_share: float = Field(..., ge=0.0, le=1.0)
    import_share: float = Field(..., ge=0.0, le=1.0)
    evidence_refs: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _shares_sum_to_one(self) -> "FinalDemandShock":
        total = round(self.domestic_share + self.import_share, 10)
        if abs(total - 1.0) > 1e-9:
            msg = f"domestic_share + import_share must equal 1.0, got {total}"
            raise ValueError(msg)
        return self


class ImportSubstitutionShock(ImpactOSBase):
    """Shift in import share for a sector."""

    type: Literal["IMPORT_SUBSTITUTION"] = "IMPORT_SUBSTITUTION"
    sector_code: str = Field(..., min_length=1)
    year: int = Field(..., ge=1900, le=2100)
    delta_import_share: float = Field(..., ge=-1.0, le=1.0)
    assumption_ref: UUID


class LocalContentChange(ImpactOSBase):
    """Target domestic share override for a sector."""

    type: Literal["LOCAL_CONTENT"] = "LOCAL_CONTENT"
    sector_code: str = Field(..., min_length=1)
    year: int = Field(..., ge=1900, le=2100)
    target_domestic_share: float = Field(..., ge=0.0, le=1.0)
    assumption_ref: UUID


class ConstraintOverride(ImpactOSBase):
    """Capacity/constraint override for feasibility layer (Phase 2)."""

    type: Literal["CONSTRAINT_OVERRIDE"] = "CONSTRAINT_OVERRIDE"
    sector_code: str = Field(..., min_length=1)
    year: int = Field(..., ge=1900, le=2100)
    cap_output: float | None = Field(default=None, ge=0.0)
    cap_jobs: int | None = Field(default=None, ge=0)
    confidence: ConstraintConfidence


ShockItem = Annotated[
    Union[FinalDemandShock, ImportSubstitutionShock, LocalContentChange, ConstraintOverride],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Time horizon
# ---------------------------------------------------------------------------


class TimeHorizon(ImpactOSBase):
    """Start/end year range for a phased scenario."""

    start_year: int = Field(..., ge=1900, le=2100)
    end_year: int = Field(..., ge=1900, le=2100)

    @model_validator(mode="after")
    def _end_after_start(self) -> "TimeHorizon":
        if self.end_year < self.start_year:
            msg = "end_year must be >= start_year"
            raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# Data quality summary (Section 5.5)
# ---------------------------------------------------------------------------


class MappingConfidence(ImpactOSBase):
    """Breakdown of mapping confidence bands."""

    high_pct: float = Field(..., ge=0.0, le=1.0)
    medium_pct: float = Field(..., ge=0.0, le=1.0)
    low_pct: float = Field(..., ge=0.0, le=1.0)


class ConstraintConfidenceBreakdown(ImpactOSBase):
    """Breakdown of constraint data provenance."""

    hard_data_pct: float = Field(..., ge=0.0, le=1.0)
    estimated_pct: float = Field(..., ge=0.0, le=1.0)
    assumed_pct: float = Field(..., ge=0.0, le=1.0)


class DataQualitySummary(ImpactOSBase):
    """Scenario-level data quality metadata per Section 5.5."""

    base_table_vintage_years: int = Field(..., ge=0)
    boq_coverage_pct: float = Field(..., ge=0.0, le=1.0)
    mapping_confidence: MappingConfidence
    unresolved_items_count: int = Field(..., ge=0)
    assumptions_count: int = Field(..., ge=0)
    constraint_confidence: ConstraintConfidenceBreakdown | None = None
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ScenarioSpec (versioned, per Section 5.3 / 6.3.1)
# ---------------------------------------------------------------------------


class ScenarioSpec(ImpactOSBase):
    """Versioned scenario specification — the core analytical unit.

    Each mutation creates a new version. Governed exports reference a
    specific (scenario_spec_id, version) pair.
    """

    scenario_spec_id: UUIDv7 = Field(default_factory=new_uuid7)
    version: int = Field(default=1, ge=1)
    name: str = Field(..., min_length=1, max_length=500)
    workspace_id: UUID
    disclosure_tier: DisclosureTier = Field(default=DisclosureTier.TIER0)
    base_model_version_id: UUID
    currency: str = Field(default="SAR", min_length=3, max_length=3)
    base_year: int = Field(..., ge=1900, le=2100)
    time_horizon: TimeHorizon
    shock_items: list[ShockItem] = Field(default_factory=list)
    assumption_ids: list[UUID] = Field(default_factory=list)
    data_quality_summary: DataQualitySummary | None = None
    created_at: UTCTimestamp = Field(default_factory=utc_now)
    updated_at: UTCTimestamp = Field(default_factory=utc_now)

    def next_version(self) -> "ScenarioSpec":
        """Create a copy with an incremented version number and fresh timestamps."""
        from src.models.common import utc_now

        now = utc_now()
        return self.model_copy(update={"version": self.version + 1, "updated_at": now})
