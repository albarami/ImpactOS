"""Workforce satellite result schemas — MVP-11.

All amendments applied:
1. BaselineSectorWorkforce for compliance checks
2. Nitaqat target ranges preserved (COMPLIANT/AT_RISK/NON_COMPLIANT/NO_TARGET/INSUFFICIENT_DATA)
3. Negative jobs handled (min/max numeric order, not semantic low/high)
4. Provenance fields populated from __init__ injected D-4 objects
5. Typed models for training_gap_summary and overrides_applied
6. Unified confidence vocabulary (worst_confidence)
8. result_granularity metadata
9. Formal missing-data defaults documented
10. Dynamic caveats from actual inputs
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from src.data.workforce.nationality_classification import NationalityTier
from src.models.common import ImpactOSBase

# ---------------------------------------------------------------------------
# Amendment 1: Baseline workforce stock
# ---------------------------------------------------------------------------


class BaselineSectorWorkforce(ImpactOSBase):
    """Current workforce stock for a sector (from D-4/GOSI).

    Required for computing projected_saudi_pct and Nitaqat compliance.
    Without this, compliance fields are null + caveat added.
    """

    sector_code: str
    total_employment: float
    saudi_employment: float | None = None
    saudi_share: float | None = None
    source: str = "unknown"
    year: int = 0


# ---------------------------------------------------------------------------
# Task 1a: Occupation Impact
# ---------------------------------------------------------------------------


class OccupationImpact(ImpactOSBase):
    """Employment impact for a specific occupation within a sector."""

    sector_code: str
    occupation_code: str
    occupation_label: str
    jobs: float
    share_of_sector: float
    bridge_confidence: str


# ---------------------------------------------------------------------------
# Task 1b: Nationality Split (Amendment 3: min/mid/max numeric order)
# ---------------------------------------------------------------------------


class NationalitySplit(ImpactOSBase):
    """Three-tier nationality feasibility for a sector-occupation pair.

    IMPORTANT: Outputs are RANGES, not point estimates.

    Amendment 3: Fields use min/mid/max (numeric order) to handle
    negative job impacts correctly. For contraction scenarios, min < mid < max
    numerically even though the Saudi share range is reversed.
    """

    sector_code: str
    occupation_code: str
    tier: NationalityTier
    total_jobs: float

    # Range-based output (Amendment 3: numeric order)
    saudi_jobs_min: float
    saudi_jobs_mid: float
    saudi_jobs_max: float

    classification_confidence: str
    current_saudi_pct: float | None = None
    rationale: str = ""


# ---------------------------------------------------------------------------
# Amendment 5: Typed models for training gap and overrides
# ---------------------------------------------------------------------------


class TrainingGapEntry(ImpactOSBase):
    """A sector-occupation pair requiring Saudi training investment."""

    sector_code: str
    occupation_code: str
    tier: NationalityTier
    total_jobs: float
    gap_jobs: float
    nitaqat_target: float | None = None


class AppliedOverride(ImpactOSBase):
    """Record of an analyst override applied to nationality classification."""

    sector_code: str
    occupation_code: str
    original_tier: NationalityTier
    override_tier: NationalityTier
    overridden_by: str
    engagement_id: str | None = None
    rationale: str = ""


# ---------------------------------------------------------------------------
# Task 1c: Sector Workforce Summary (Amendment 2: Nitaqat ranges)
# ---------------------------------------------------------------------------

# Amendment 2: compliance status enum
NitaqatComplianceStatus = Literal[
    "COMPLIANT", "AT_RISK", "NON_COMPLIANT", "NO_TARGET", "INSUFFICIENT_DATA",
]


class SectorWorkforceSummary(ImpactOSBase):
    """Complete workforce picture for one sector."""

    sector_code: str
    sector_label: str = ""

    # Total jobs
    total_jobs: float

    # Occupation breakdown
    occupation_impacts: list[OccupationImpact] = Field(default_factory=list)

    # Nationality split (aggregated across occupations)
    saudi_ready_jobs: float = 0.0
    saudi_trainable_jobs: float = 0.0
    expat_reliant_jobs: float = 0.0

    # Ranges for Saudi achievability (Amendment 3: min/mid/max)
    projected_saudi_jobs_min: float = 0.0
    projected_saudi_jobs_mid: float = 0.0
    projected_saudi_jobs_max: float = 0.0
    projected_saudi_pct_range: tuple[float, float] | None = None

    # Nitaqat compliance (Amendment 2: ranges preserved)
    nitaqat_target_effective: float | None = None
    nitaqat_target_range: tuple[float, float] | None = None
    nitaqat_compliance_status: NitaqatComplianceStatus | None = None
    nitaqat_gap_jobs: float | None = None

    # Confidence
    overall_confidence: str = "ASSUMED"
    confidence_breakdown: dict[str, int] = Field(default_factory=dict)

    # Training gap
    training_gap_occupations: list[str] = Field(default_factory=list)

    # Amendment 1: Baseline data used
    has_baseline: bool = False


# ---------------------------------------------------------------------------
# Task 1d: Complete Workforce Result
# ---------------------------------------------------------------------------


class WorkforceResult(ImpactOSBase):
    """Complete workforce satellite analysis result.

    This is the primary output of MVP-11. It answers:
    - How many jobs? (total + by sector + by occupation)
    - How many Saudi jobs? (range, not point estimate)
    - Is this achievable? (Nitaqat compliance check)
    - What training is needed? (trainable tier gap analysis)
    """

    # Per-sector detail
    sector_summaries: list[SectorWorkforceSummary] = Field(
        default_factory=list,
    )

    # Economy-wide aggregates (Amendment 3: min/mid/max)
    total_jobs: float = 0.0
    total_saudi_jobs_min: float = 0.0
    total_saudi_jobs_mid: float = 0.0
    total_saudi_jobs_max: float = 0.0
    total_saudi_pct_range: tuple[float, float] | None = None

    # Tier aggregates
    total_saudi_ready: float = 0.0
    total_saudi_trainable: float = 0.0
    total_expat_reliant: float = 0.0

    # Compliance summary
    sectors_compliant: int = 0
    sectors_non_compliant: int = 0
    sectors_no_target: int = 0
    sectors_at_risk: int = 0
    sectors_insufficient_data: int = 0
    total_nitaqat_gap_jobs: float = 0.0

    # Training pipeline (Amendment 5: typed)
    training_gap_summary: list[TrainingGapEntry] = Field(
        default_factory=list,
    )

    # Data provenance (Amendment 4: populated from __init__)
    bridge_version: str = ""
    classification_version: str = ""
    coefficient_provenance: dict = Field(default_factory=dict)
    overrides_applied: list[AppliedOverride] = Field(default_factory=list)

    # Confidence
    overall_confidence: str = "ASSUMED"
    confidence_caveats: list[str] = Field(default_factory=list)

    # Metadata
    known_limitations: list[str] = Field(default_factory=list)

    # Amendment 8: result granularity
    result_granularity: Literal["section", "division"] = "section"
