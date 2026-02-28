"""Quality module enums, dataclasses, and Pydantic models (MVP-13).

Defines the 7 quality dimensions, severity levels, grading system,
and the core assessment models used throughout the Data Quality
Automation pipeline.

Deterministic -- no LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from src.models.common import (
    ImpactOSBase,
    UTCTimestamp,
    UUIDv7,
    new_uuid7,
    utc_now,
)


# ---------------------------------------------------------------------------
# Enums (all StrEnum)
# ---------------------------------------------------------------------------


class QualitySeverity(StrEnum):
    """Severity levels for quality warnings."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    WAIVER_REQUIRED = "WAIVER_REQUIRED"


class QualityGrade(StrEnum):
    """Composite quality grades from A (best) to F (worst)."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


class QualityDimension(StrEnum):
    """The 7 quality dimensions assessed for each run."""

    VINTAGE = "VINTAGE"
    MAPPING = "MAPPING"
    ASSUMPTIONS = "ASSUMPTIONS"
    CONSTRAINTS = "CONSTRAINTS"
    WORKFORCE = "WORKFORCE"
    PLAUSIBILITY = "PLAUSIBILITY"
    FRESHNESS = "FRESHNESS"


class NowcastStatus(StrEnum):
    """Lifecycle status for nowcast adjustments."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PlausibilityStatus(StrEnum):
    """Result of a plausibility check against benchmarks."""

    IN_RANGE = "IN_RANGE"
    ABOVE_RANGE = "ABOVE_RANGE"
    BELOW_RANGE = "BELOW_RANGE"
    NO_BENCHMARK = "NO_BENCHMARK"


class SourceUpdateFrequency(StrEnum):
    """Expected update cadence for a data source."""

    QUARTERLY = "QUARTERLY"
    ANNUAL = "ANNUAL"
    BIENNIAL = "BIENNIAL"
    TRIENNIAL = "TRIENNIAL"
    QUINQUENNIAL = "QUINQUENNIAL"
    PER_ENGAGEMENT = "PER_ENGAGEMENT"


# Cadence mapping: SourceUpdateFrequency -> expected days between updates.
FREQUENCY_DAYS: dict[SourceUpdateFrequency, int] = {
    SourceUpdateFrequency.QUARTERLY: 90,
    SourceUpdateFrequency.ANNUAL: 365,
    SourceUpdateFrequency.BIENNIAL: 730,
    SourceUpdateFrequency.TRIENNIAL: 1095,
    SourceUpdateFrequency.QUINQUENNIAL: 1825,
}


# ---------------------------------------------------------------------------
# Frozen dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceAge:
    """Immutable record of a data source's age and expected refresh cadence."""

    source_name: str
    age_days: float
    expected_frequency: SourceUpdateFrequency


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class QualityWarning(ImpactOSBase):
    """A single quality warning raised during assessment."""

    warning_id: UUIDv7 = Field(default_factory=new_uuid7)
    dimension: QualityDimension
    severity: QualitySeverity
    message: str
    detail: str | None = None
    recommendation: str | None = None


class DimensionAssessment(ImpactOSBase):
    """Per-dimension provenance and score (Amendment 9).

    Records the score, inputs, rules triggered, and warnings for
    a single quality dimension assessment.
    """

    dimension: QualityDimension
    score: float = Field(ge=0.0, le=1.0)
    applicable: bool
    inputs_used: dict[str, object] = Field(default_factory=dict)
    rules_triggered: list[str] = Field(default_factory=list)
    warnings: list[QualityWarning] = Field(default_factory=list)


class RunQualityAssessment(ImpactOSBase, frozen=True):
    """Immutable composite quality assessment for a run.

    Renamed from DataQualitySummary (Amendment 4), versioned (Amendment 5).
    Aggregates per-dimension scores into a single composite grade.
    """

    assessment_id: UUIDv7 = Field(default_factory=new_uuid7)
    assessment_version: int = Field(ge=1)
    run_id: UUID | None = None
    dimension_assessments: list[DimensionAssessment] = Field(default_factory=list)
    applicable_dimensions: list[QualityDimension] = Field(default_factory=list)
    assessed_dimensions: list[QualityDimension] = Field(default_factory=list)
    missing_dimensions: list[QualityDimension] = Field(default_factory=list)
    completeness_pct: float = 0.0
    composite_score: float = Field(default=0.0, ge=0.0, le=1.0)
    grade: QualityGrade = QualityGrade.F
    warnings: list[QualityWarning] = Field(default_factory=list)
    waiver_required_count: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    known_gaps: list[str] = Field(default_factory=list)
    notes: str | None = None
    created_at: UTCTimestamp = Field(default_factory=utc_now)
