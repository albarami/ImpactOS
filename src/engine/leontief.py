"""Core Leontief solver — MVP-3 Sections 7.2, 7.3, 7.4.

Pure deterministic functions: Δx = B·Δd with direct/indirect decomposition,
multi-year phasing with deflation. No LLM calls, no side effects.

Given the same inputs, ALWAYS produces the same outputs.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy import linalg as scipy_linalg

from src.engine.model_store import LoadedModel


@dataclass(frozen=True)
class SolveResult:
    """Result of a single Leontief solve: total, direct, indirect effects."""

    delta_x_total: np.ndarray
    delta_x_direct: np.ndarray
    delta_x_indirect: np.ndarray
    delta_x_type_ii_total: np.ndarray | None = None
    delta_x_induced: np.ndarray | None = None


@dataclass(frozen=True)
class PhasedResult:
    """Result of a multi-year phased solve."""

    annual_results: dict[int, SolveResult]
    cumulative_delta_x: np.ndarray
    peak_year: int
    peak_delta_x: np.ndarray
    cumulative_delta_x_type_ii: np.ndarray | None = None
    cumulative_delta_x_induced: np.ndarray | None = None


class LeontiefSolver:
    """Deterministic Leontief I-O solver.

    All computations use the cached Leontief inverse B from LoadedModel.
    Uses B · Δd (matrix-vector product) rather than solving a linear system
    per shock, since B is already computed and cached per ModelVersion.
    """

    def solve(
        self,
        *,
        loaded_model: LoadedModel,
        delta_d: np.ndarray,
    ) -> SolveResult:
        """Compute output effects for a single final-demand shock.

        Args:
            loaded_model: Model with cached B matrix.
            delta_d: Final demand shock vector (n).

        Returns:
            SolveResult with total, direct, and indirect effects.

        Raises:
            ValueError: If delta_d dimension doesn't match model.
        """
        delta_d = np.asarray(delta_d, dtype=np.float64)
        n = loaded_model.n

        if delta_d.shape != (n,):
            msg = f"dimension mismatch: delta_d has {delta_d.shape[0]} elements, model has {n} sectors."
            raise ValueError(msg)

        B = loaded_model.B

        # Section 7.2: Δx_total = B · Δd
        delta_x_total = B @ delta_d

        # Section 7.3: decomposition
        delta_x_direct = delta_d.copy()
        delta_x_indirect = delta_x_total - delta_x_direct  # (B - I) · Δd

        return SolveResult(
            delta_x_total=delta_x_total,
            delta_x_direct=delta_x_direct,
            delta_x_indirect=delta_x_indirect,
        )

    def solve_type_ii(
        self,
        *,
        loaded_model: LoadedModel,
        delta_d: np.ndarray,
        compensation_of_employees: np.ndarray,
        household_consumption_shares: np.ndarray,
    ) -> SolveResult:
        """Compute Type II effects with household closure.

        Constructs augmented (n+1)x(n+1) matrix internally.
        Returns n-vectors only -- household pseudo-sector stays internal.
        induced = type_ii_total - type_i_total

        Args:
            loaded_model: Model with cached A and B matrices.
            delta_d: Final demand shock vector (n).
            compensation_of_employees: Compensation per sector (n).
            household_consumption_shares: Household consumption shares (n).

        Returns:
            SolveResult with Type I fields plus Type II total and induced.

        Raises:
            ValueError: If any input dimension doesn't match model.
        """
        delta_d = np.asarray(delta_d, dtype=np.float64)
        comp = np.asarray(compensation_of_employees, dtype=np.float64)
        hh_shares = np.asarray(household_consumption_shares, dtype=np.float64)
        n = loaded_model.n

        if delta_d.shape != (n,):
            raise ValueError(
                f"dimension mismatch: delta_d has {delta_d.shape[0]} elements, "
                f"model has {n} sectors."
            )
        if comp.shape != (n,):
            raise ValueError(
                f"dimension mismatch: compensation_of_employees has {comp.shape[0]} elements, "
                f"model has {n} sectors."
            )
        if hh_shares.shape != (n,):
            raise ValueError(
                f"dimension mismatch: household_consumption_shares has {hh_shares.shape[0]} elements, "
                f"model has {n} sectors."
            )

        # Type I solve
        type_i = self.solve(loaded_model=loaded_model, delta_d=delta_d)

        # Wage coefficients: w_i = comp_i / x_i
        w = comp / loaded_model.x

        # Augmented (n+1)x(n+1) matrix A*
        A = loaded_model.A
        A_star = np.zeros((n + 1, n + 1))
        A_star[:n, :n] = A
        A_star[n, :n] = w           # household income row
        A_star[:n, n] = hh_shares   # household consumption column

        # B* = (I - A*)^{-1}
        I_star = np.eye(n + 1)
        B_star = scipy_linalg.solve(I_star - A_star, I_star)

        # Augmented demand: [delta_d, 0]
        delta_d_aug = np.zeros(n + 1)
        delta_d_aug[:n] = delta_d

        # Type II total: trim to n sectors
        delta_x_star = B_star @ delta_d_aug
        type_ii_total = delta_x_star[:n]

        # Induced = Type II - Type I
        induced = type_ii_total - type_i.delta_x_total

        return SolveResult(
            delta_x_total=type_i.delta_x_total,
            delta_x_direct=type_i.delta_x_direct,
            delta_x_indirect=type_i.delta_x_indirect,
            delta_x_type_ii_total=type_ii_total,
            delta_x_induced=induced,
        )

    def solve_phased(
        self,
        *,
        loaded_model: LoadedModel,
        annual_shocks: dict[int, np.ndarray],
        base_year: int,
        deflators: dict[int, float] | None = None,
    ) -> PhasedResult:
        """Compute phased multi-year impacts (Section 7.4).

        Args:
            loaded_model: Model with cached B matrix.
            annual_shocks: Year → nominal final-demand shock vector.
            base_year: Base year for the model (used with deflators).
            deflators: Optional year → cumulative deflator. The real shock
                is nominal / deflator. If None, no deflation applied.

        Returns:
            PhasedResult with annual, cumulative, and peak-year results.
        """
        if deflators is None:
            deflators = {}

        annual_results: dict[int, SolveResult] = {}
        n = loaded_model.n
        cumulative = np.zeros(n)
        peak_year = -1
        peak_total = -np.inf
        peak_delta_x = np.zeros(n)

        for year in sorted(annual_shocks.keys()):
            nominal = np.asarray(annual_shocks[year], dtype=np.float64)

            # Deflate: real = nominal / deflator
            deflator = deflators.get(year, 1.0)
            real_shock = nominal / deflator

            result = self.solve(loaded_model=loaded_model, delta_d=real_shock)
            annual_results[year] = result

            cumulative = cumulative + result.delta_x_total

            year_total = float(np.sum(result.delta_x_total))
            if year_total > peak_total:
                peak_total = year_total
                peak_year = year
                peak_delta_x = result.delta_x_total.copy()

        return PhasedResult(
            annual_results=annual_results,
            cumulative_delta_x=cumulative,
            peak_year=peak_year,
            peak_delta_x=peak_delta_x,
        )
