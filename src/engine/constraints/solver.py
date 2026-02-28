"""Feasibility Solver — iterative clipping of unconstrained IO results.

v1 uses iterative clipping. Each constraint is applied independently.
The gap between unconstrained and feasible quantifies the deliverability gap.

Known limitation: Clipping violates IO accounting identities. A constrained
optimization (LP/QP) approach would maintain consistency but is deferred
to Phase 3.

Amendments applied:
1. ConstraintBoundScope respected (ABSOLUTE_TOTAL vs DELTA_ONLY)
2. BUDGET excluded from solver (pre-solve only)
4. Economy-wide proportional allocation
5. SAUDIZATION produces compliance diagnostics, not clipping
7. Ramp = base-to-target growth (not YoY sequential)
9. ConstraintConfidenceSummary computed
10. Order-independent sector clipping (min of implied caps)
11. Separate output-enablers from compliance-enablers
"""

from dataclasses import dataclass, field
from uuid import UUID

import numpy as np

from src.engine.constraints.schema import (
    Constraint,
    ConstraintBoundScope,
    ConstraintSet,
    ConstraintType,
    ConstraintUnit,
)
from src.engine.satellites import SatelliteCoefficients, SatelliteResult
from src.models.common import ConstraintConfidence, new_uuid7

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BindingConstraint:
    """A constraint that actually bound (clipped) the result."""

    constraint_id: UUID
    constraint_type: ConstraintType
    sector_code: str | None
    unconstrained_value: float
    constrained_value: float
    gap: float                       # unconstrained - constrained
    gap_pct: float                   # gap / unconstrained (0 if unconstrained == 0)
    unit: ConstraintUnit
    description: str


@dataclass(frozen=True)
class ComplianceDiagnostic:
    """A compliance check that doesn't clip output but reports gaps.

    Amendment 5: SAUDIZATION constraints produce diagnostics, not clipping.
    """

    constraint_id: UUID
    constraint_type: ConstraintType
    sector_code: str | None
    target_value: float              # Required value (e.g., Saudi share)
    projected_value: float           # Projected value given unconstrained result
    gap: float                       # target - projected (positive = non-compliant)
    description: str


@dataclass(frozen=True)
class Enabler:
    """A policy action needed to unlock feasibility.

    Derived from binding constraints: what needs to change
    to close the deliverability gap.
    """

    enabler_id: UUID
    binding_constraint_id: UUID
    description: str
    sector_code: str | None
    gap_unlocked: float              # How much output gap this would close
    priority_rank: int               # 1 = most impactful


@dataclass(frozen=True)
class ConstraintConfidenceSummary:
    """Summary of constraint confidence levels for reporting.

    Amendment 9: feeds Data Quality Summary in exports.
    """

    total_constraints: int
    hard_count: int
    estimated_count: int
    assumed_count: int
    binding_confidence_breakdown: dict[str, int]


@dataclass(frozen=True)
class FeasibilityResult:
    """Complete feasibility analysis result."""

    # The two outputs
    unconstrained_delta_x: np.ndarray
    feasible_delta_x: np.ndarray

    # Satellite impacts for both
    unconstrained_satellite: SatelliteResult
    feasible_satellite: SatelliteResult

    # Diagnostics — output constraints
    binding_constraints: list[BindingConstraint]
    non_binding_constraints: list[UUID]

    # Amendment 5: compliance diagnostics (SAUDIZATION etc.)
    compliance_diagnostics: list[ComplianceDiagnostic]

    # Amendment 11: separate enabler lists
    output_enablers: list[Enabler]         # From binding output constraints
    compliance_enablers: list[Enabler]     # From compliance diagnostics

    # Summary
    total_output_gap: float
    total_output_gap_pct: float
    total_jobs_gap: float

    # Amendment 9: confidence summary
    constraint_confidence_summary: ConstraintConfidenceSummary

    # Metadata
    constraint_set_id: UUID
    solver_method: str = "iterative_clipping_v1"
    known_limitations: list[str] = field(default_factory=lambda: [
        "IO accounting identity violated by independent clipping",
        "Ramp constraints use base-to-target growth, not YoY sequential",
    ])


# ---------------------------------------------------------------------------
# Enabler generation templates
# ---------------------------------------------------------------------------

_ENABLER_TEMPLATES: dict[ConstraintType, str] = {
    ConstraintType.CAPACITY_CAP: (
        "Increase {sector} production capacity by {gap_pct:.1f}% "
        "({gap:.1f} {unit})"
    ),
    ConstraintType.RAMP: (
        "Accelerate {sector} growth rate beyond {rate:.1f}% "
        "to accommodate {gap:.1f} {unit} additional output"
    ),
    ConstraintType.LABOR: (
        "Add {gap:.0f} workers to {sector} "
        "(or improve productivity to reduce labor needs)"
    ),
    ConstraintType.IMPORT: (
        "Develop domestic supply for {sector} to reduce import "
        "dependency by {gap:.1f} {unit}"
    ),
}

_COMPLIANCE_ENABLER_TEMPLATES: dict[ConstraintType, str] = {
    ConstraintType.SAUDIZATION: (
        "Train/recruit {gap:.0f} Saudi workers for {sector} "
        "to meet {target:.1f}% Nitaqat target"
    ),
}


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------


class FeasibilitySolver:
    """Applies constraints to unconstrained IO results.

    v1 uses iterative clipping. Each constraint is applied independently.
    The gap between unconstrained and feasible quantifies the deliverability gap.

    Known limitation: Clipping violates IO accounting identities.
    A constrained optimization (LP/QP) approach would maintain consistency
    but is deferred to Phase 3.
    """

    def solve(
        self,
        *,
        unconstrained_delta_x: np.ndarray,
        base_x: np.ndarray,
        satellite_coefficients: SatelliteCoefficients,
        constraint_set: ConstraintSet,
        sector_codes: list[str],
        scenario_year: int | None = None,
    ) -> FeasibilityResult:
        """Apply constraints and produce feasible result with diagnostics.

        Args:
            unconstrained_delta_x: Raw IO model output (delta_x_total).
            base_x: Current gross output vector (for ramp/absolute constraints).
            satellite_coefficients: For computing satellite impacts.
            constraint_set: Collection of constraints to apply.
            sector_codes: Sector code for each vector element.
            scenario_year: Optional year for time-windowed constraints.
        """
        from src.engine.satellites import SatelliteAccounts

        unconstrained = np.asarray(unconstrained_delta_x, dtype=np.float64).copy()
        base = np.asarray(base_x, dtype=np.float64)

        # Start with unconstrained as feasible, then clip
        feasible = unconstrained.copy()

        # Amendment 10: For sector-specific constraints, compute implied
        # delta_x cap per sector, then take the minimum (order-independent)
        sector_caps: dict[int, float] = {}  # sector index → min implied cap

        binding: list[BindingConstraint] = []
        non_binding_ids: list[UUID] = []
        compliance_diags: list[ComplianceDiagnostic] = []

        # Get post-solve clipping constraints
        clipping_constraints = constraint_set.get_post_solve_constraints(
            year=scenario_year,
        )

        # Process each constraint
        for constraint in clipping_constraints:
            self._apply_constraint(
                constraint=constraint,
                feasible=feasible,
                base=base,
                sector_codes=sector_codes,
                unconstrained=unconstrained,
                sector_caps=sector_caps,
                binding=binding,
                non_binding_ids=non_binding_ids,
                satellite_coefficients=satellite_coefficients,
                scenario_year=scenario_year,
            )

        # Apply accumulated sector caps (Amendment 10: order-independent)
        for idx, cap in sector_caps.items():
            if unconstrained[idx] > cap:
                feasible[idx] = cap
            # Contraction is allowed — don't clip below zero for negative delta_x
            # but also don't increase contraction beyond unconstrained
            if unconstrained[idx] < 0:
                feasible[idx] = unconstrained[idx]

        # Amendment 5: Process diagnostic-only constraints (SAUDIZATION)
        diagnostic_constraints = constraint_set.get_diagnostic_constraints(
            year=scenario_year,
        )
        for constraint in diagnostic_constraints:
            self._process_diagnostic(
                constraint=constraint,
                unconstrained=unconstrained,
                base=base,
                sector_codes=sector_codes,
                satellite_coefficients=satellite_coefficients,
                compliance_diags=compliance_diags,
            )

        # Compute satellite impacts for both
        sat_accounts = SatelliteAccounts()
        unconstrained_sat = sat_accounts.compute(
            delta_x=unconstrained,
            coefficients=satellite_coefficients,
        )
        feasible_sat = sat_accounts.compute(
            delta_x=feasible,
            coefficients=satellite_coefficients,
        )

        # Generate enablers (Amendment 11: separate lists)
        output_enablers = self._generate_output_enablers(binding)
        compliance_enablers = self._generate_compliance_enablers(
            compliance_diags,
        )

        # Summary statistics
        output_gap_vec = unconstrained - feasible
        total_output_gap = float(np.sum(np.maximum(output_gap_vec, 0)))
        unconstrained_total = float(np.sum(np.maximum(unconstrained, 0)))
        total_output_gap_pct = (
            total_output_gap / unconstrained_total
            if unconstrained_total > 0 else 0.0
        )
        jobs_gap_vec = unconstrained_sat.delta_jobs - feasible_sat.delta_jobs
        total_jobs_gap = float(np.sum(np.maximum(jobs_gap_vec, 0)))

        # Amendment 9: confidence summary
        confidence_summary = self._compute_confidence_summary(
            constraint_set, binding,
        )

        return FeasibilityResult(
            unconstrained_delta_x=unconstrained,
            feasible_delta_x=feasible,
            unconstrained_satellite=unconstrained_sat,
            feasible_satellite=feasible_sat,
            binding_constraints=binding,
            non_binding_constraints=non_binding_ids,
            compliance_diagnostics=compliance_diags,
            output_enablers=output_enablers,
            compliance_enablers=compliance_enablers,
            total_output_gap=total_output_gap,
            total_output_gap_pct=total_output_gap_pct,
            total_jobs_gap=total_jobs_gap,
            constraint_confidence_summary=confidence_summary,
            constraint_set_id=constraint_set.constraint_set_id,
        )

    def _apply_constraint(
        self,
        *,
        constraint: Constraint,
        feasible: np.ndarray,
        base: np.ndarray,
        sector_codes: list[str],
        unconstrained: np.ndarray,
        sector_caps: dict[int, float],
        binding: list[BindingConstraint],
        non_binding_ids: list[UUID],
        satellite_coefficients: SatelliteCoefficients,
        scenario_year: int | None,
    ) -> None:
        """Apply a single post-solve constraint."""
        scope = constraint.scope
        bound_scope = constraint.effective_bound_scope

        if scope.scope_type in ("sector", "group"):
            # Sector-specific or group constraints
            target_codes = scope.scope_values or []
            indices = [
                i for i, code in enumerate(sector_codes)
                if code in target_codes
            ]
            if not indices:
                non_binding_ids.append(constraint.constraint_id)
                return

            did_bind = False
            for idx in indices:
                bound = self._compute_bound_for_sector(
                    constraint=constraint,
                    base_value=float(base[idx]),
                    unconstrained_value=float(unconstrained[idx]),
                    satellite_coefficients=satellite_coefficients,
                    sector_idx=idx,
                )
                if bound is None:
                    continue

                # Compute implied delta_x cap
                if bound_scope == ConstraintBoundScope.ABSOLUTE_TOTAL:
                    implied_cap = bound - float(base[idx])
                else:
                    implied_cap = bound

                # Track minimum cap per sector (Amendment 10)
                current_unconstrained = float(unconstrained[idx])
                if current_unconstrained > 0 and implied_cap < current_unconstrained:
                    if idx not in sector_caps or implied_cap < sector_caps[idx]:
                        sector_caps[idx] = implied_cap
                    did_bind = True
                    binding.append(BindingConstraint(
                        constraint_id=constraint.constraint_id,
                        constraint_type=constraint.constraint_type,
                        sector_code=sector_codes[idx],
                        unconstrained_value=current_unconstrained,
                        constrained_value=implied_cap,
                        gap=current_unconstrained - implied_cap,
                        gap_pct=(
                            (current_unconstrained - implied_cap) / current_unconstrained
                            if current_unconstrained != 0 else 0.0
                        ),
                        unit=constraint.unit,
                        description=constraint.description,
                    ))

            if not did_bind:
                non_binding_ids.append(constraint.constraint_id)

        elif scope.scope_type == "all":
            # Amendment 4: Economy-wide constraint with allocation
            self._apply_economy_wide(
                constraint=constraint,
                feasible=feasible,
                base=base,
                sector_codes=sector_codes,
                unconstrained=unconstrained,
                sector_caps=sector_caps,
                binding=binding,
                non_binding_ids=non_binding_ids,
                satellite_coefficients=satellite_coefficients,
            )

    def _compute_bound_for_sector(
        self,
        *,
        constraint: Constraint,
        base_value: float,
        unconstrained_value: float,
        satellite_coefficients: SatelliteCoefficients,
        sector_idx: int,
    ) -> float | None:
        """Compute the effective bound value for a sector.

        Returns the bound in the same space as the constraint type.
        """
        ctype = constraint.constraint_type

        if ctype == ConstraintType.CAPACITY_CAP:
            return constraint.upper_bound

        if ctype == ConstraintType.RAMP:
            # Amendment 7: base-to-target growth cap
            if constraint.max_growth_rate is not None:
                return base_value * (1 + constraint.max_growth_rate)
            return constraint.upper_bound

        if ctype == ConstraintType.LABOR:
            # Labor cap: constraint in jobs space → convert back to output
            if constraint.upper_bound is not None:
                jobs_coeff = float(satellite_coefficients.jobs_coeff[sector_idx])
                if jobs_coeff > 0:
                    # max_delta_x = max_jobs / jobs_coeff
                    return constraint.upper_bound / jobs_coeff
            return None

        if ctype == ConstraintType.IMPORT:
            # Import cap: constraint in import space → convert back to output
            if constraint.upper_bound is not None:
                import_ratio = float(satellite_coefficients.import_ratio[sector_idx])
                if import_ratio > 0:
                    return constraint.upper_bound / import_ratio
            return None

        return constraint.upper_bound

    def _apply_economy_wide(
        self,
        *,
        constraint: Constraint,
        feasible: np.ndarray,
        base: np.ndarray,
        sector_codes: list[str],
        unconstrained: np.ndarray,
        sector_caps: dict[int, float],
        binding: list[BindingConstraint],
        non_binding_ids: list[UUID],
        satellite_coefficients: SatelliteCoefficients,
    ) -> None:
        """Apply economy-wide constraint with allocation rule (Amendment 4)."""
        allocation_rule = constraint.scope.allocation_rule or "proportional"
        bound_scope = constraint.effective_bound_scope

        if allocation_rule != "proportional":
            raise NotImplementedError(
                f"Allocation rule '{allocation_rule}' not implemented in v1. "
                "Only 'proportional' is supported."
            )

        ctype = constraint.constraint_type

        # Compute aggregate values
        if ctype == ConstraintType.RAMP and constraint.max_growth_rate is not None:
            # Per-sector ramp: each sector gets the same growth rate cap
            did_bind = False
            for i in range(len(sector_codes)):
                max_total = float(base[i]) * (1 + constraint.max_growth_rate)
                if bound_scope == ConstraintBoundScope.ABSOLUTE_TOTAL:
                    implied_cap = max_total - float(base[i])
                else:
                    implied_cap = max_total

                if float(unconstrained[i]) > 0 and implied_cap < float(unconstrained[i]):
                    if i not in sector_caps or implied_cap < sector_caps[i]:
                        sector_caps[i] = implied_cap
                    did_bind = True
                    binding.append(BindingConstraint(
                        constraint_id=constraint.constraint_id,
                        constraint_type=constraint.constraint_type,
                        sector_code=sector_codes[i],
                        unconstrained_value=float(unconstrained[i]),
                        constrained_value=implied_cap,
                        gap=float(unconstrained[i]) - implied_cap,
                        gap_pct=(
                            (float(unconstrained[i]) - implied_cap) / float(unconstrained[i])
                            if float(unconstrained[i]) != 0 else 0.0
                        ),
                        unit=constraint.unit,
                        description=constraint.description,
                    ))
            if not did_bind:
                non_binding_ids.append(constraint.constraint_id)
            return

        # For aggregate caps (upper_bound on total)
        if constraint.upper_bound is None:
            non_binding_ids.append(constraint.constraint_id)
            return

        cap = constraint.upper_bound

        # Compute aggregate unconstrained value
        if ctype == ConstraintType.LABOR:
            values = satellite_coefficients.jobs_coeff * unconstrained
        elif ctype == ConstraintType.IMPORT:
            values = satellite_coefficients.import_ratio * unconstrained
        else:
            values = unconstrained.copy()

        agg_positive = float(np.sum(np.maximum(values, 0)))

        if agg_positive <= cap:
            non_binding_ids.append(constraint.constraint_id)
            return

        # Proportional scaling
        scale_factor = cap / agg_positive if agg_positive > 0 else 1.0

        did_bind = False
        for i in range(len(sector_codes)):
            if values[i] <= 0:
                continue

            scaled_value = float(values[i]) * scale_factor

            # Convert back to output space
            if ctype == ConstraintType.LABOR:
                jc = float(satellite_coefficients.jobs_coeff[i])
                implied_cap = scaled_value / jc if jc > 0 else float(unconstrained[i])
            elif ctype == ConstraintType.IMPORT:
                ir = float(satellite_coefficients.import_ratio[i])
                implied_cap = scaled_value / ir if ir > 0 else float(unconstrained[i])
            else:
                implied_cap = scaled_value

            if implied_cap < float(unconstrained[i]):
                if i not in sector_caps or implied_cap < sector_caps[i]:
                    sector_caps[i] = implied_cap
                did_bind = True
                binding.append(BindingConstraint(
                    constraint_id=constraint.constraint_id,
                    constraint_type=constraint.constraint_type,
                    sector_code=sector_codes[i],
                    unconstrained_value=float(unconstrained[i]),
                    constrained_value=implied_cap,
                    gap=float(unconstrained[i]) - implied_cap,
                    gap_pct=(
                        (float(unconstrained[i]) - implied_cap) / float(unconstrained[i])
                        if float(unconstrained[i]) != 0 else 0.0
                    ),
                    unit=constraint.unit,
                    description=constraint.description,
                ))

        if not did_bind:
            non_binding_ids.append(constraint.constraint_id)

    def _process_diagnostic(
        self,
        *,
        constraint: Constraint,
        unconstrained: np.ndarray,
        base: np.ndarray,
        sector_codes: list[str],
        satellite_coefficients: SatelliteCoefficients,
        compliance_diags: list[ComplianceDiagnostic],
    ) -> None:
        """Process a diagnostic-only constraint (Amendment 5)."""
        if constraint.constraint_type != ConstraintType.SAUDIZATION:
            return

        target = constraint.lower_bound
        if target is None:
            return

        # Saudization applies per-sector
        scope = constraint.scope
        if scope.scope_type == "all":
            target_indices = list(range(len(sector_codes)))
        elif scope.scope_values:
            target_indices = [
                i for i, code in enumerate(sector_codes)
                if code in scope.scope_values
            ]
        else:
            return

        for idx in target_indices:
            # projected_value: we don't have Saudi share data in the solver,
            # so we report the target vs a projected 0 (gap = full target).
            # Real projected values come from D-4 data via labor_constraints.
            compliance_diags.append(ComplianceDiagnostic(
                constraint_id=constraint.constraint_id,
                constraint_type=constraint.constraint_type,
                sector_code=sector_codes[idx],
                target_value=target,
                projected_value=0.0,  # Placeholder — enriched by labor integration
                gap=target,
                description=constraint.description,
            ))

    def _generate_output_enablers(
        self,
        binding: list[BindingConstraint],
    ) -> list[Enabler]:
        """Generate and rank enablers from binding output constraints."""
        enablers: list[Enabler] = []
        for bc in binding:
            template = _ENABLER_TEMPLATES.get(bc.constraint_type)
            if template is None:
                desc = f"Address {bc.constraint_type.value} constraint on {bc.sector_code}"
            else:
                desc = template.format(
                    sector=bc.sector_code or "economy",
                    gap=bc.gap,
                    gap_pct=bc.gap_pct * 100,
                    unit=bc.unit.value,
                    rate=bc.gap_pct * 100,
                )

            enablers.append(Enabler(
                enabler_id=new_uuid7(),
                binding_constraint_id=bc.constraint_id,
                description=desc,
                sector_code=bc.sector_code,
                gap_unlocked=bc.gap,
                priority_rank=0,  # Will be set after sorting
            ))

        # Rank by gap_unlocked descending
        enablers.sort(key=lambda e: e.gap_unlocked, reverse=True)
        ranked: list[Enabler] = []
        for i, e in enumerate(enablers):
            ranked.append(Enabler(
                enabler_id=e.enabler_id,
                binding_constraint_id=e.binding_constraint_id,
                description=e.description,
                sector_code=e.sector_code,
                gap_unlocked=e.gap_unlocked,
                priority_rank=i + 1,
            ))
        return ranked

    def _generate_compliance_enablers(
        self,
        diagnostics: list[ComplianceDiagnostic],
    ) -> list[Enabler]:
        """Generate enablers from compliance diagnostics (Amendment 11)."""
        enablers: list[Enabler] = []
        for diag in diagnostics:
            if diag.gap <= 0:
                continue  # Compliant

            template = _COMPLIANCE_ENABLER_TEMPLATES.get(diag.constraint_type)
            if template is None:
                desc = f"Address {diag.constraint_type.value} compliance for {diag.sector_code}"
            else:
                desc = template.format(
                    sector=diag.sector_code or "economy",
                    gap=diag.gap,
                    target=diag.target_value * 100,
                )

            enablers.append(Enabler(
                enabler_id=new_uuid7(),
                binding_constraint_id=diag.constraint_id,
                description=desc,
                sector_code=diag.sector_code,
                gap_unlocked=diag.gap,
                priority_rank=0,
            ))

        # Rank by gap descending
        enablers.sort(key=lambda e: e.gap_unlocked, reverse=True)
        ranked: list[Enabler] = []
        for i, e in enumerate(enablers):
            ranked.append(Enabler(
                enabler_id=e.enabler_id,
                binding_constraint_id=e.binding_constraint_id,
                description=e.description,
                sector_code=e.sector_code,
                gap_unlocked=e.gap_unlocked,
                priority_rank=i + 1,
            ))
        return ranked

    def _compute_confidence_summary(
        self,
        constraint_set: ConstraintSet,
        binding: list[BindingConstraint],
    ) -> ConstraintConfidenceSummary:
        """Compute constraint confidence summary (Amendment 9)."""
        all_constraints = constraint_set.constraints
        total = len(all_constraints)
        hard = sum(
            1 for c in all_constraints
            if c.confidence == ConstraintConfidence.HARD
        )
        estimated = sum(
            1 for c in all_constraints
            if c.confidence == ConstraintConfidence.ESTIMATED
        )
        assumed = sum(
            1 for c in all_constraints
            if c.confidence == ConstraintConfidence.ASSUMED
        )

        # Binding constraint confidence breakdown
        binding_ids = {bc.constraint_id for bc in binding}
        binding_breakdown: dict[str, int] = {
            "HARD": 0, "ESTIMATED": 0, "ASSUMED": 0,
        }
        for c in constraint_set.constraints:
            if c.constraint_id in binding_ids:
                binding_breakdown[c.confidence.value] = (
                    binding_breakdown.get(c.confidence.value, 0) + 1
                )

        return ConstraintConfidenceSummary(
            total_constraints=total,
            hard_count=hard,
            estimated_count=estimated,
            assumed_count=assumed,
            binding_confidence_breakdown=binding_breakdown,
        )
