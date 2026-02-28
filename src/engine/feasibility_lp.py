"""LP-based shadow price solver — MVP-10 Section 7.8.

Amendment 7: LP is used for shadow prices ONLY. The clipping solver
produces the feasible vector (composition-preserving). LP should NOT
reallocate across sectors.

Uses scipy.optimize.linprog to solve:
    max  Σ y_i
    s.t. 0 ≤ y_i ≤ unconstrained_i  (for each sector)
         constraint inequalities

Shadow prices are extracted from the LP dual variables.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

import numpy as np
from scipy.optimize import linprog

from src.engine.feasibility import ConstraintSpec
from src.engine.satellites import SatelliteCoefficients

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LPShadowPriceResult:
    """Result from LP solver — shadow prices only (Amendment 7)."""

    shadow_prices: np.ndarray  # One per constraint
    constraint_ids: list[UUID]  # Parallel to shadow_prices
    status: str  # "optimal", "infeasible", "unbounded", "error"
    lp_objective: float  # Optimal objective value


class LPFeasibilitySolver:
    """LP-based solver for computing exact shadow prices.

    Amendment 7: This solver does NOT produce a feasible vector.
    Use ClippingSolver for the composition-preserving feasible vector.

    Shadow prices are the dual values (marginal value of relaxing each
    constraint by one unit).
    """

    def compute_shadow_prices(
        self,
        *,
        unconstrained_delta_x: np.ndarray,
        constraints: list[ConstraintSpec],
        satellite_coefficients: SatelliteCoefficients | None = None,
        sector_codes: list[str],
    ) -> LPShadowPriceResult:
        """Compute exact shadow prices via LP dual variables.

        Formulation (linprog minimizes, so we negate):
            min  -Σ y_i
            s.t. A_ub @ y <= b_ub   (constraint inequalities)
                 0 <= y <= unconstrained_delta_x  (bounds)

        Args:
            unconstrained_delta_x: n-vector of unconstrained output changes.
            constraints: List of constraint specifications.
            satellite_coefficients: Needed for LABOR/IMPORT constraints.
            sector_codes: Ordered sector codes (length n).

        Returns:
            LPShadowPriceResult with shadow prices and LP status.
        """
        n = len(sector_codes)
        constraint_ids = [spec.constraint_id for spec in constraints]

        if not constraints:
            return LPShadowPriceResult(
                shadow_prices=np.array([]),
                constraint_ids=[],
                status="optimal",
                lp_objective=float(np.sum(unconstrained_delta_x)),
            )

        # Objective: maximize Σ y_i → minimize -Σ y_i
        c = -np.ones(n)

        # Bounds: 0 <= y_i <= unconstrained_i
        bounds = [(0.0, float(unconstrained_delta_x[i])) for i in range(n)]

        # Build inequality constraints: A_ub @ y <= b_ub
        A_ub_rows: list[np.ndarray] = []
        b_ub_vals: list[float] = []

        for spec in constraints:
            if spec.constraint_type == "CAPACITY_CAP" and spec.sector_index is not None:
                # y[sector_index] <= bound_value
                row = np.zeros(n)
                row[spec.sector_index] = 1.0
                A_ub_rows.append(row)
                b_ub_vals.append(spec.bound_value)

            elif spec.constraint_type == "LABOR_AVAILABILITY" and spec.sector_index is None:
                if satellite_coefficients is None:
                    raise ValueError(
                        "LABOR_AVAILABILITY constraint requires satellite_coefficients"
                    )
                # jobs_coeff @ y <= bound_value
                A_ub_rows.append(satellite_coefficients.jobs_coeff.copy())
                b_ub_vals.append(spec.bound_value)

            elif spec.constraint_type == "IMPORT_BOTTLENECK" and spec.sector_index is None:
                if satellite_coefficients is None:
                    raise ValueError(
                        "IMPORT_BOTTLENECK constraint requires satellite_coefficients"
                    )
                # import_ratio @ y <= bound_value
                A_ub_rows.append(satellite_coefficients.import_ratio.copy())
                b_ub_vals.append(spec.bound_value)

            elif spec.constraint_type == "BUDGET_CEILING" and spec.sector_index is None:
                # Σ y_i <= bound_value
                A_ub_rows.append(np.ones(n))
                b_ub_vals.append(spec.bound_value)

        if not A_ub_rows:
            return LPShadowPriceResult(
                shadow_prices=np.zeros(len(constraints)),
                constraint_ids=constraint_ids,
                status="optimal",
                lp_objective=float(np.sum(unconstrained_delta_x)),
            )

        A_ub = np.array(A_ub_rows)
        b_ub = np.array(b_ub_vals)

        try:
            result = linprog(
                c,
                A_ub=A_ub,
                b_ub=b_ub,
                bounds=bounds,
                method="highs",
            )
        except Exception as exc:
            logger.exception("LP solver failed: %s", exc)
            return LPShadowPriceResult(
                shadow_prices=np.zeros(len(constraints)),
                constraint_ids=constraint_ids,
                status="error",
                lp_objective=0.0,
            )

        if not result.success:
            logger.warning("LP solver did not converge: %s", result.message)
            return LPShadowPriceResult(
                shadow_prices=np.zeros(len(constraints)),
                constraint_ids=constraint_ids,
                status="infeasible",
                lp_objective=0.0,
            )

        # Extract shadow prices from dual variables (ineqlin)
        # Shadow prices are the dual values (negative of scipy's convention
        # since we minimized the negative objective)
        dual = result.ineqlin.marginals if hasattr(result, "ineqlin") else np.zeros(len(A_ub_rows))

        # Map back to constraint ordering (A_ub rows are in constraint order)
        shadow_prices = np.zeros(len(constraints))
        row_idx = 0
        for i, spec in enumerate(constraints):
            if spec.constraint_type in ("CAPACITY_CAP",) and spec.sector_index is not None:
                shadow_prices[i] = abs(float(dual[row_idx]))
                row_idx += 1
            elif spec.sector_index is None and spec.constraint_type in (
                "LABOR_AVAILABILITY", "IMPORT_BOTTLENECK", "BUDGET_CEILING",
            ):
                shadow_prices[i] = abs(float(dual[row_idx]))
                row_idx += 1

        return LPShadowPriceResult(
            shadow_prices=shadow_prices,
            constraint_ids=constraint_ids,
            status="optimal",
            lp_objective=float(-result.fun),
        )
