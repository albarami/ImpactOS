"""Data quality Pydantic schemas — MVP-13.

Unified Data Quality Framework: scores data inputs on standardized dimensions,
produces run-level quality summaries, monitors source freshness, and integrates
with NFF governance publication gate decisions.

All 7 amendments applied:
1. STRUCTURAL_VALIDITY in QualityDimension
2. dimension_weights on InputQualityScore (stored for auditability)
3. mapping_coverage_pct on RunQualitySummary
4. Smooth freshness decay (engine-level — thresholds defined here)
5. summary_version + summary_hash on RunQualitySummary
6. force_recompute (API-level — no model impact)
7. PublicationGateMode: PASS / PASS_WITH_WARNINGS / FAIL_REQUIRES_WAIVER
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from src.models.common import ImpactOSBase, UTCTimestamp, utc_now

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class QualityDimension(StrEnum):
    """Standardized scoring dimensions for data quality assessment."""

    FRESHNESS = "FRESHNESS"
    COMPLETENESS = "COMPLETENESS"
    CONFIDENCE = "CONFIDENCE"
    PROVENANCE = "PROVENANCE"
    CONSISTENCY = "CONSISTENCY"
    STRUCTURAL_VALIDITY = "STRUCTURAL_VALIDITY"  # Amendment 1


class QualityGrade(StrEnum):
    """Letter grades that executives understand.

    Thresholds: A >= 0.9, B >= 0.75, C >= 0.6, D >= 0.4, F < 0.4.
    """

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


class StalenessLevel(StrEnum):
    """Source data freshness classification.

    Thresholds are configurable per source type via FreshnessThresholds.
    """

    CURRENT = "CURRENT"
    AGING = "AGING"
    STALE = "STALE"
    EXPIRED = "EXPIRED"


class PublicationGateMode(StrEnum):
    """Advisory publication gate outcome (Amendment 7).

    PASS: grade >= B AND no STALE/EXPIRED AND coverage >= 0.7
    PASS_WITH_WARNINGS: grade >= C AND no EXPIRED AND coverage >= 0.5
    FAIL_REQUIRES_WAIVER: anything below PASS_WITH_WARNINGS
    """

    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL_REQUIRES_WAIVER = "FAIL_REQUIRES_WAIVER"


# ---------------------------------------------------------------------------
# Configurable thresholds
# ---------------------------------------------------------------------------


class FreshnessThresholds(ImpactOSBase):
    """Configurable per-source-type freshness thresholds (in days).

    Source types age at different rates: IO tables are updated less
    frequently than policy rules.
    """

    aging_days: int = Field(..., ge=1)
    stale_days: int = Field(..., ge=1)
    expired_days: int = Field(..., ge=1)


DEFAULT_FRESHNESS_THRESHOLDS: dict[str, FreshnessThresholds] = {
    "io_table": FreshnessThresholds(
        aging_days=3 * 365, stale_days=5 * 365, expired_days=7 * 365,
    ),
    "coefficients": FreshnessThresholds(
        aging_days=365, stale_days=2 * 365, expired_days=3 * 365,
    ),
    "policy": FreshnessThresholds(
        aging_days=180, stale_days=365, expired_days=2 * 365,
    ),
    "default": FreshnessThresholds(
        aging_days=365, stale_days=2 * 365, expired_days=3 * 365,
    ),
}


class GradeThresholds(ImpactOSBase):
    """Configurable grade cutoff thresholds.

    Defaults: A >= 0.9, B >= 0.75, C >= 0.6, D >= 0.4, F < 0.4.
    """

    a_min: float = Field(default=0.9, ge=0.0, le=1.0)
    b_min: float = Field(default=0.75, ge=0.0, le=1.0)
    c_min: float = Field(default=0.6, ge=0.0, le=1.0)
    d_min: float = Field(default=0.4, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Scoring models
# ---------------------------------------------------------------------------


class DimensionScore(ImpactOSBase):
    """Score for a single quality dimension.

    Every penalty is EXPLAINED — no opaque scores.
    """

    dimension: QualityDimension
    score: float = Field(..., ge=0.0, le=1.0)
    grade: QualityGrade
    details: str
    penalties: list[str] = Field(default_factory=list)


class InputQualityScore(ImpactOSBase):
    """Quality score for a single data input used in a run.

    Amendment 2: dimension_weights stored for auditability — shows exactly
    what weights drove the overall score.
    """

    input_type: str  # e.g. "io_table", "employment_coefficients", etc.
    input_version_id: UUID | None = None
    dimension_scores: list[DimensionScore] = Field(default_factory=list)
    overall_score: float = Field(..., ge=0.0, le=1.0)
    overall_grade: QualityGrade
    dimension_weights: dict[str, float] = Field(default_factory=dict)
    computed_at: UTCTimestamp = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Freshness models
# ---------------------------------------------------------------------------


class FreshnessCheck(ImpactOSBase):
    """Freshness assessment for a single data source."""

    source_name: str
    source_type: str
    last_updated: datetime
    checked_at: UTCTimestamp = Field(default_factory=utc_now)
    staleness: StalenessLevel
    days_since_update: int = Field(..., ge=0)
    recommended_action: str


class FreshnessReport(ImpactOSBase):
    """Aggregate freshness status across all data sources."""

    checks: list[FreshnessCheck] = Field(default_factory=list)
    stale_count: int = Field(..., ge=0)
    expired_count: int = Field(..., ge=0)
    overall_freshness: StalenessLevel


# ---------------------------------------------------------------------------
# Run-level quality summary (the key deliverable)
# ---------------------------------------------------------------------------


class RunQualitySummary(ImpactOSBase, frozen=True):
    """Immutable run-level data quality summary.

    Produced after a scenario run. One per run (UniqueConstraint on run_id).
    Publication gate is ADVISORY — NFF governance is the actual blocker.

    Amendment 3: mapping_coverage_pct for gate logic.
    Amendment 5: summary_version + summary_hash for audit.
    Amendment 7: publication_gate_mode for nuanced gate signaling.
    """

    run_id: UUID
    workspace_id: UUID
    base_table_vintage: str  # e.g. "GASTAT 2019 IO Table"
    base_table_year: int
    years_since_base: int
    input_scores: list[InputQualityScore] = Field(default_factory=list)
    overall_run_score: float = Field(..., ge=0.0, le=1.0)
    overall_run_grade: QualityGrade
    freshness_report: FreshnessReport
    coverage_pct: float = Field(..., ge=0.0, le=1.0)
    mapping_coverage_pct: float | None = None  # Amendment 3
    key_gaps: list[str] = Field(default_factory=list)
    key_strengths: list[str] = Field(default_factory=list)
    recommendation: str
    publication_gate_pass: bool
    publication_gate_mode: PublicationGateMode  # Amendment 7
    summary_version: str = Field(default="1.0.0")  # Amendment 5
    summary_hash: str = Field(default="")  # Amendment 5
    created_at: UTCTimestamp = Field(default_factory=utc_now)
