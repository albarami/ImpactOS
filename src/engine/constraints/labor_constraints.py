"""Labor constraint builder — bridges D-4 workforce data to feasibility.

Builds LABOR and SAUDIZATION constraints from D-4 curated data:
- Employment coefficients → labor capacity caps
- Nitaqat macro targets → Saudization floor diagnostics

All derived constraints marked confidence: ESTIMATED (derived from D-4 data,
not direct measurement).

This is DETERMINISTIC — no LLM calls.
"""

from src.engine.constraints.schema import (
    Constraint,
    ConstraintBoundScope,
    ConstraintScope,
    ConstraintType,
    ConstraintUnit,
)
from src.models.common import ConstraintConfidence


def build_labor_constraints_from_d4(
    employment_coefficients: object,
    nitaqat_targets: object | None = None,
    max_employment_growth: float = 1.0,
    sector_codes: list[str] | None = None,
) -> list[Constraint]:
    """Build labor and Saudization constraints from D-4 curated data.

    Args:
        employment_coefficients: EmploymentCoefficientSet from D-4.
        nitaqat_targets: MacroSaudizationTargets from D-4 (optional).
        max_employment_growth: Max employment growth factor (default: 1.0 = 100%).
        sector_codes: If provided, only generate for these sectors.

    Returns:
        List of Constraint objects (LABOR caps + SAUDIZATION diagnostics).
    """
    constraints: list[Constraint] = []

    # Access coefficients list
    coefficients = getattr(employment_coefficients, "coefficients", [])
    available_sectors = sector_codes or [
        c.sector_code for c in coefficients
    ]

    for coeff in coefficients:
        if coeff.sector_code not in available_sectors:
            continue

        total_emp = getattr(coeff, "total_employment", None)
        if total_emp is None or total_emp <= 0:
            continue

        # Labor cap: current_employment * (1 + max_employment_growth)
        max_jobs = total_emp * (1 + max_employment_growth)
        constraints.append(Constraint(
            constraint_type=ConstraintType.LABOR,
            scope=ConstraintScope(
                scope_type="sector",
                scope_values=[coeff.sector_code],
            ),
            description=(
                f"Labor capacity for {coeff.sector_code}: max {max_jobs:.0f} "
                f"jobs ({max_employment_growth:.0%} growth from {total_emp:.0f})"
            ),
            upper_bound=max_jobs,
            bound_scope=ConstraintBoundScope.ABSOLUTE_TOTAL,
            unit=ConstraintUnit.JOBS,
            confidence=ConstraintConfidence.ESTIMATED,
            notes=(
                f"Derived from D-4 employment coefficient: "
                f"{total_emp:.0f} current jobs, max growth {max_employment_growth:.0%}"
            ),
        ))

    # Saudization floors from Nitaqat targets
    if nitaqat_targets is not None:
        targets_dict = getattr(nitaqat_targets, "targets", {})
        for code in available_sectors:
            target = targets_dict.get(code)
            if target is None:
                continue

            effective_pct = getattr(target, "effective_target_pct", None)
            if effective_pct is None or effective_pct <= 0:
                continue

            constraints.append(Constraint(
                constraint_type=ConstraintType.SAUDIZATION,
                scope=ConstraintScope(
                    scope_type="sector",
                    scope_values=[code],
                ),
                description=(
                    f"Saudization target for {code}: "
                    f"{effective_pct:.1%} Saudi employment share"
                ),
                lower_bound=effective_pct,
                bound_scope=ConstraintBoundScope.ABSOLUTE_TOTAL,
                unit=ConstraintUnit.FRACTION,
                confidence=ConstraintConfidence.ESTIMATED,
                notes=(
                    f"Derived from Nitaqat macro targets: "
                    f"{effective_pct:.1%} effective target"
                ),
            ))

    return constraints
