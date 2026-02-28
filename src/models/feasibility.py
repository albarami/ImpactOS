"""Pydantic schemas for the Feasibility/Constraint Layer — MVP-10.

Defines constraint types, constraint sets (versioned), feasibility results,
binding constraints, enabler recommendations, and confidence summaries.

The feasibility layer produces TWO results for every scenario:
- Unconstrained (pure Leontief)
- Feasible (real-world constraints applied)
The gap between them quantifies what must change to make a plan work.

Gap sign convention: gap = unconstrained - feasible >= 0 (always positive).
"""

from enum import StrEnum
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


class ConstraintType(StrEnum):
    """Types of real-world constraints that limit unconstrained Leontief output."""

    CAPACITY_CAP = "CAPACITY_CAP"
    RAMP_RATE = "RAMP_RATE"
    LABOR_AVAILABILITY = "LABOR_AVAILABILITY"
    IMPORT_BOTTLENECK = "IMPORT_BOTTLENECK"
    BUDGET_CEILING = "BUDGET_CEILING"


# Reuse ConstraintConfidence from src/models/common.py (HARD, ESTIMATED, ASSUMED)
# — no new enum needed.


# ---------------------------------------------------------------------------
# TimeWindow helper
# ---------------------------------------------------------------------------


class TimeWindow(ImpactOSBase):
    """Year range for time-windowed constraints."""

    start_year: int = Field(..., ge=1900, le=2100)
    end_year: int = Field(..., ge=1900, le=2100)

    @model_validator(mode="after")
    def _end_ge_start(self) -> "TimeWindow":
        if self.end_year < self.start_year:
            raise ValueError(
                f"end_year ({self.end_year}) must be >= start_year ({self.start_year})"
            )
        return self


# ---------------------------------------------------------------------------
# Constraint + ConstraintSet (versioned)
# ---------------------------------------------------------------------------


class Constraint(ImpactOSBase):
    """A single real-world constraint on economic output."""

    constraint_id: UUIDv7 = Field(default_factory=new_uuid7)
    constraint_type: ConstraintType
    applies_to: str = Field(
        ..., min_length=1,
        description="Sector code or 'all' for cross-sector constraints.",
    )
    value: float = Field(..., description="Constraint bound value.")
    unit: str = Field(
        ..., min_length=1,
        description="Unit of the constraint value, e.g. 'SAR', 'jobs', 'pct'.",
    )
    time_window: TimeWindow | None = None
    confidence: ConstraintConfidence
    evidence_refs: list[UUID] = Field(default_factory=list)
    notes: str = ""


class ConstraintSet(ImpactOSBase):
    """Versioned constraint set — append-only, same pattern as ScenarioSpec."""

    constraint_set_id: UUIDv7 = Field(default_factory=new_uuid7)
    version: int = Field(default=1, ge=1)
    workspace_id: UUID
    model_version_id: UUID
    name: str = Field(..., min_length=1, max_length=500)
    constraints: list[Constraint] = Field(default_factory=list)
    created_at: UTCTimestamp = Field(default_factory=utc_now)
    created_by: UUID | None = None

    def next_version(self) -> "ConstraintSet":
        """Create the next version of this constraint set."""
        now = utc_now()
        return self.model_copy(
            update={"version": self.version + 1, "created_at": now},
        )


# ---------------------------------------------------------------------------
# Binding constraints + enabler recommendations
# ---------------------------------------------------------------------------


class BindingConstraint(ImpactOSBase):
    """A constraint that is active (binding) in the feasibility solution."""

    constraint_id: UUID
    constraint_type: ConstraintType
    sector_code: str
    shadow_price: float = Field(
        ...,
        description="Marginal value of relaxing this constraint by one unit.",
    )
    gap_to_feasible: float = Field(
        ...,
        description=(
            "Output lost at this constraint: "
            "unconstrained value minus feasible value."
        ),
    )
    recommendation: str = ""


class EnablerRecommendation(ImpactOSBase):
    """Policy action to relax a binding constraint."""

    constraint_id: UUID
    title: str = Field(..., min_length=1)
    description: str = ""
    policy_lever: str = Field(
        ..., min_length=1,
        description=(
            "Concrete policy action, e.g. "
            "'Increase training capacity', 'Ease import quotas'."
        ),
    )
    estimated_unlock_value: float = Field(
        ..., ge=0.0,
        description="Additional output unlocked if this constraint is relaxed.",
    )
    priority_rank: int = Field(..., ge=1)


# ---------------------------------------------------------------------------
# Confidence summary
# ---------------------------------------------------------------------------


class ConfidenceSummary(ImpactOSBase):
    """Aggregated confidence breakdown of constraints used in a solve."""

    hard_pct: float = Field(..., ge=0.0, le=1.0)
    estimated_pct: float = Field(..., ge=0.0, le=1.0)
    assumed_pct: float = Field(..., ge=0.0, le=1.0)
    total_constraints: int = Field(..., ge=0)


# ---------------------------------------------------------------------------
# FeasibilityResult (immutable)
# ---------------------------------------------------------------------------


class FeasibilityResult(ImpactOSBase, frozen=True):
    """Immutable result of a feasibility solve.

    Gap sign convention: gap = unconstrained - feasible, always >= 0.
    """

    feasibility_result_id: UUIDv7 = Field(default_factory=new_uuid7)
    unconstrained_run_id: UUID
    constraint_set_id: UUID
    constraint_set_version: int = Field(..., ge=1)

    # Output vectors keyed by sector_code
    feasible_delta_x: dict[str, float] = Field(
        ...,
        description="Feasible output change vector keyed by sector code.",
    )
    unconstrained_delta_x: dict[str, float] = Field(
        ...,
        description="Original unconstrained output change for comparison.",
    )
    gap_vs_unconstrained: dict[str, float] = Field(
        ...,
        description=(
            "Per-sector gap: unconstrained - feasible. "
            "Always >= 0 (output lost to constraints)."
        ),
    )

    # Aggregates
    total_feasible_output: float
    total_unconstrained_output: float
    total_gap: float = Field(
        ...,
        description="Sum of all per-sector gaps. Always >= 0.",
    )

    # Constraint analysis
    binding_constraints: list[BindingConstraint] = Field(default_factory=list)
    slack_constraints: list[UUID] = Field(
        default_factory=list,
        description="IDs of constraints that are NOT binding (have slack).",
    )
    enabler_recommendations: list[EnablerRecommendation] = Field(
        default_factory=list,
    )

    # Confidence
    confidence_summary: ConfidenceSummary

    # Reproducibility: satellite coefficients used (Amendment 1B)
    satellite_coefficients_hash: str = Field(
        ...,
        description="SHA-256 of satellite coefficient arrays used in solve.",
    )
    satellite_coefficients_snapshot: dict | None = Field(
        default=None,
        description="Actual coefficients used, as {sector_code: value} dicts.",
    )

    # Solver metadata (Amendment 6)
    solver_type: str = Field(
        ...,
        description="Solver used: 'clipping' or 'lp'.",
    )
    solver_version: str = Field(
        default="1.0.0",
        description="Solver version string.",
    )
    lp_status: str | None = Field(
        default=None,
        description="LP solver status: 'optimal', 'infeasible', 'failed', or None.",
    )
    fallback_used: bool = Field(
        default=False,
        description="True if LP failed and clipping was used as fallback.",
    )

    created_at: UTCTimestamp = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _enforce_gap_sign_convention(self) -> "FeasibilityResult":
        """Enforce: gap = unconstrained - feasible >= 0 everywhere."""
        for sector, gap_val in self.gap_vs_unconstrained.items():
            if gap_val < 0:
                raise ValueError(
                    f"gap_vs_unconstrained['{sector}'] = {gap_val} is negative. "
                    f"Gap must be >= 0 (unconstrained - feasible)."
                )
        if self.total_gap < 0:
            raise ValueError(
                f"total_gap = {self.total_gap} is negative. Must be >= 0."
            )
        return self
