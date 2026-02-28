"""Feasibility/Constraint Solver — MVP-10 Section 7.8.

Deterministic engine code: NumPy/SciPy only, NO LLM calls.

Two solver tiers:
1. ClippingSolver (MVP): composition-preserving element-wise capping
   + proportional scaling for aggregate constraints.
2. LPFeasibilitySolver: scipy.optimize.linprog for shadow prices only;
   feasible vector still from clipping (Amendment 7).

Gap sign convention: gap = unconstrained - feasible >= 0 (always positive).
"""

import logging
from dataclasses import dataclass
from uuid import UUID

import numpy as np

from src.engine.satellites import SatelliteCoefficients
from src.models.common import ConstraintConfidence
from src.models.feasibility import (
    BindingConstraint,
    ConfidenceSummary,
    Constraint,
    ConstraintType,
    EnablerRecommendation,
)

logger = logging.getLogger(__name__)

SOLVER_VERSION = "1.0.0"

# Tolerance for binding detection
_BINDING_TOL = 1e-8


# ---------------------------------------------------------------------------
# Engine-level dataclasses (not Pydantic — same pattern as SolveResult)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConstraintSpec:
    """Engine-level constraint specification for solver internals."""

    constraint_id: UUID
    constraint_type: str  # matches ConstraintType values
    sector_index: int | None  # None for cross-sector ("all")
    bound_value: float
    confidence: str  # matches ConstraintConfidence values


@dataclass(frozen=True)
class FeasibilitySolveResult:
    """Engine-level result from the feasibility solver."""

    feasible_delta_x: np.ndarray
    binding_mask: np.ndarray  # bool array, one per constraint
    shadow_prices: np.ndarray  # one per constraint
    constraint_ids: list[UUID]  # parallel to shadow_prices
    gap_per_sector: np.ndarray  # unconstrained - feasible per sector (>= 0)


# ---------------------------------------------------------------------------
# ClippingSolver — composition-preserving
# ---------------------------------------------------------------------------


class ClippingSolver:
    """Simple element-wise constraint solver using clipping.

    Phase 1: Sector-level capacity caps (CAPACITY_CAP).
    Phase 2: Aggregate constraints (LABOR, IMPORT, BUDGET) via
             proportional scaling.

    Shadow prices approximated as the gap value (unconstrained - feasible)
    for binding constraints.
    """

    def solve(
        self,
        *,
        unconstrained_delta_x: np.ndarray,
        constraints: list[ConstraintSpec],
        satellite_coefficients: SatelliteCoefficients | None = None,
        sector_codes: list[str],
    ) -> FeasibilitySolveResult:
        """Solve for feasible output vector subject to constraints.

        Args:
            unconstrained_delta_x: n-vector of unconstrained output changes.
            constraints: List of constraint specifications.
            satellite_coefficients: Needed for LABOR/IMPORT constraints.
            sector_codes: Ordered sector codes (length n).

        Returns:
            FeasibilitySolveResult with feasible vector, binding info, shadow prices.
        """
        n = len(sector_codes)
        if unconstrained_delta_x.shape != (n,):
            raise ValueError(
                f"unconstrained_delta_x dimension {unconstrained_delta_x.shape} "
                f"does not match sector_codes length {n}"
            )

        feasible = unconstrained_delta_x.copy().astype(float)

        # --- Phase 1: Sector-level capacity caps ---
        for spec in constraints:
            if spec.constraint_type == "CAPACITY_CAP" and spec.sector_index is not None:
                feasible[spec.sector_index] = min(
                    feasible[spec.sector_index], spec.bound_value,
                )

        # --- Phase 2: Aggregate constraints ---
        for spec in constraints:
            if spec.sector_index is not None:
                continue  # Already handled in Phase 1

            if spec.constraint_type == "LABOR_AVAILABILITY":
                if satellite_coefficients is None:
                    raise ValueError(
                        "LABOR_AVAILABILITY constraint requires satellite_coefficients"
                    )
                total = float(np.dot(satellite_coefficients.jobs_coeff, feasible))
                if total > spec.bound_value and total > 0:
                    scale = spec.bound_value / total
                    feasible *= scale

            elif spec.constraint_type == "IMPORT_BOTTLENECK":
                if satellite_coefficients is None:
                    raise ValueError(
                        "IMPORT_BOTTLENECK constraint requires satellite_coefficients"
                    )
                total = float(np.dot(satellite_coefficients.import_ratio, feasible))
                if total > spec.bound_value and total > 0:
                    scale = spec.bound_value / total
                    feasible *= scale

            elif spec.constraint_type == "BUDGET_CEILING":
                total = float(np.sum(feasible))
                if total > spec.bound_value and total > 0:
                    scale = spec.bound_value / total
                    feasible *= scale

        # Ensure non-negative
        feasible = np.maximum(feasible, 0.0)

        # --- Compute binding mask and shadow prices ---
        binding_mask = np.zeros(len(constraints), dtype=bool)
        shadow_prices = np.zeros(len(constraints))
        constraint_ids = [spec.constraint_id for spec in constraints]

        for i, spec in enumerate(constraints):
            if spec.constraint_type == "CAPACITY_CAP" and spec.sector_index is not None:
                gap = unconstrained_delta_x[spec.sector_index] - feasible[spec.sector_index]
                if gap > _BINDING_TOL:
                    binding_mask[i] = True
                    shadow_prices[i] = gap
            elif spec.sector_index is None:
                # Aggregate constraints
                if (
                    spec.constraint_type == "LABOR_AVAILABILITY"
                    and satellite_coefficients is not None
                ):
                    total_unconstrained = float(
                        np.dot(satellite_coefficients.jobs_coeff, unconstrained_delta_x)
                    )
                    if total_unconstrained > spec.bound_value + _BINDING_TOL:
                        binding_mask[i] = True
                        shadow_prices[i] = total_unconstrained - spec.bound_value
                elif (
                    spec.constraint_type == "IMPORT_BOTTLENECK"
                    and satellite_coefficients is not None
                ):
                    total_unconstrained = float(
                        np.dot(satellite_coefficients.import_ratio, unconstrained_delta_x)
                    )
                    if total_unconstrained > spec.bound_value + _BINDING_TOL:
                        binding_mask[i] = True
                        shadow_prices[i] = total_unconstrained - spec.bound_value
                elif spec.constraint_type == "BUDGET_CEILING":
                    total_unconstrained = float(np.sum(unconstrained_delta_x))
                    if total_unconstrained > spec.bound_value + _BINDING_TOL:
                        binding_mask[i] = True
                        shadow_prices[i] = total_unconstrained - spec.bound_value

        # Gap per sector: always >= 0
        gap_per_sector = unconstrained_delta_x - feasible

        return FeasibilitySolveResult(
            feasible_delta_x=feasible,
            binding_mask=binding_mask,
            shadow_prices=shadow_prices,
            constraint_ids=constraint_ids,
            gap_per_sector=gap_per_sector,
        )


# ---------------------------------------------------------------------------
# Helpers: conversion, enabler recommendations, confidence summary
# ---------------------------------------------------------------------------


def constraints_to_specs(
    constraints: list[Constraint],
    sector_codes: list[str],
) -> list[ConstraintSpec]:
    """Convert Pydantic Constraint models to engine-level ConstraintSpec.

    Maps sector_code to sector_index. Constraints with applies_to='all'
    get sector_index=None (cross-sector).
    """
    sector_index_map = {code: i for i, code in enumerate(sector_codes)}
    specs: list[ConstraintSpec] = []

    for c in constraints:
        if c.applies_to == "all":
            sector_index = None
        else:
            if c.applies_to not in sector_index_map:
                raise ValueError(
                    f"Sector code '{c.applies_to}' not found in model. "
                    f"Valid codes: {sector_codes}"
                )
            sector_index = sector_index_map[c.applies_to]

        specs.append(ConstraintSpec(
            constraint_id=c.constraint_id,
            constraint_type=c.constraint_type.value,
            sector_index=sector_index,
            bound_value=c.value,
            confidence=c.confidence.value,
        ))

    return specs


# Enabler recommendation templates by constraint type
_ENABLER_TEMPLATES: dict[str, tuple[str, str]] = {
    "CAPACITY_CAP": (
        "Expand production capacity",
        "Invest in capacity expansion or process optimization",
    ),
    "LABOR_AVAILABILITY": (
        "Increase labor supply",
        "Expand training programs or ease labor mobility restrictions",
    ),
    "IMPORT_BOTTLENECK": (
        "Ease import constraints",
        "Diversify import sources, expand port capacity, or reduce trade barriers",
    ),
    "BUDGET_CEILING": (
        "Increase budget allocation",
        "Explore phased spending or additional funding sources",
    ),
    "RAMP_RATE": (
        "Adjust ramp-up timeline",
        "Phase project delivery to match realistic ramp-up capacity",
    ),
}


def generate_enabler_recommendations(
    binding_constraints: list[BindingConstraint],
    constraints: list[Constraint],
) -> list[EnablerRecommendation]:
    """Generate deterministic enabler recommendations for binding constraints.

    Ranked by shadow_price (highest = rank 1). Uses template library per type.
    """
    if not binding_constraints:
        return []

    # Sort by shadow price descending
    sorted_binding = sorted(
        binding_constraints,
        key=lambda b: b.shadow_price,
        reverse=True,
    )

    # Build lookup for constraint details
    constraint_map = {c.constraint_id: c for c in constraints}

    recommendations: list[EnablerRecommendation] = []
    for rank, bc in enumerate(sorted_binding, 1):
        ctype = (
            bc.constraint_type.value
            if isinstance(bc.constraint_type, ConstraintType)
            else bc.constraint_type
        )
        template = _ENABLER_TEMPLATES.get(
            ctype, ("Address constraint", "Review and relax constraint")
        )
        title, description = template

        # Customize title with sector info
        if bc.sector_code != "all":
            title = f"{title} in {bc.sector_code}"

        original = constraint_map.get(bc.constraint_id)
        policy_lever = description
        if original and original.notes:
            policy_lever = f"{description}. Context: {original.notes}"

        recommendations.append(EnablerRecommendation(
            constraint_id=bc.constraint_id,
            title=title,
            description=description,
            policy_lever=policy_lever,
            estimated_unlock_value=bc.gap_to_feasible,
            priority_rank=rank,
        ))

    return recommendations


def compute_confidence_summary(
    constraints: list[Constraint],
) -> ConfidenceSummary:
    """Compute confidence breakdown from constraint list."""
    total = len(constraints)
    if total == 0:
        return ConfidenceSummary(
            hard_pct=0.0, estimated_pct=0.0, assumed_pct=0.0,
            total_constraints=0,
        )

    counts = {
        ConstraintConfidence.HARD: 0,
        ConstraintConfidence.ESTIMATED: 0,
        ConstraintConfidence.ASSUMED: 0,
    }
    for c in constraints:
        counts[c.confidence] = counts.get(c.confidence, 0) + 1

    return ConfidenceSummary(
        hard_pct=round(counts[ConstraintConfidence.HARD] / total, 4),
        estimated_pct=round(counts[ConstraintConfidence.ESTIMATED] / total, 4),
        assumed_pct=round(counts[ConstraintConfidence.ASSUMED] / total, 4),
        total_constraints=total,
    )
