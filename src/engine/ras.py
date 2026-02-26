"""RAS matrix balancing — MVP-3 Section 7.7.

Iterative bi-proportional matrix balancing (RAS method) to update
an older Z matrix to match new row/column totals while preserving
structural zeros.

Pure deterministic — no LLM calls.
"""

from dataclasses import dataclass
from uuid import UUID

import numpy as np

from src.engine.model_store import ModelStore
from src.models.model_version import ModelVersion


@dataclass(frozen=True)
class RASResult:
    """Result of RAS balancing iteration."""

    Z_balanced: np.ndarray
    converged: bool
    iterations: int
    final_error: float


class RASBalancer:
    """Bi-proportional (RAS) matrix balancing.

    Iteratively scales rows and columns of Z0 until row sums match r
    and column sums match c, within tolerance.
    """

    def balance(
        self,
        *,
        Z0: np.ndarray,
        target_row_totals: np.ndarray,
        target_col_totals: np.ndarray,
        tolerance: float = 1e-8,
        max_iterations: int = 1000,
    ) -> RASResult:
        """Run RAS iteration.

        Args:
            Z0: Baseline intermediate transactions matrix (n×n).
            target_row_totals: Target row sums (n).
            target_col_totals: Target column sums (n).
            tolerance: Convergence threshold (max absolute error).
            max_iterations: Safety limit on iterations.

        Returns:
            RASResult with balanced Z and convergence info.

        Raises:
            ValueError: If dimensions mismatch or targets are negative.
        """
        Z0 = np.asarray(Z0, dtype=np.float64)
        r = np.asarray(target_row_totals, dtype=np.float64)
        c = np.asarray(target_col_totals, dtype=np.float64)

        n = Z0.shape[0]

        # Validation
        if Z0.ndim != 2 or Z0.shape[0] != Z0.shape[1]:
            msg = "Z0 must be a square matrix."
            raise ValueError(msg)

        if r.shape != (n,):
            msg = f"dimension mismatch: Z0 is {n}×{n} but target_row_totals has {r.shape[0]} elements."
            raise ValueError(msg)

        if c.shape != (n,):
            msg = f"dimension mismatch: Z0 is {n}×{n} but target_col_totals has {c.shape[0]} elements."
            raise ValueError(msg)

        if np.any(r < 0):
            msg = "target_row_totals must be non-negative."
            raise ValueError(msg)

        if np.any(c < 0):
            msg = "target_col_totals must be non-negative."
            raise ValueError(msg)

        Z = Z0.copy()
        converged = False
        final_error = float("inf")

        for iteration in range(1, max_iterations + 1):
            # Step 1: Row scaling
            row_sums = Z.sum(axis=1)
            # Avoid division by zero for empty rows
            row_factors = np.where(row_sums > 0, r / row_sums, 0.0)
            Z = Z * row_factors[:, np.newaxis]

            # Step 2: Column scaling
            col_sums = Z.sum(axis=0)
            col_factors = np.where(col_sums > 0, c / col_sums, 0.0)
            Z = Z * col_factors[np.newaxis, :]

            # Check convergence
            row_error = float(np.max(np.abs(Z.sum(axis=1) - r)))
            col_error = float(np.max(np.abs(Z.sum(axis=0) - c)))
            final_error = max(row_error, col_error)

            if final_error <= tolerance:
                converged = True
                return RASResult(
                    Z_balanced=Z,
                    converged=converged,
                    iterations=iteration,
                    final_error=final_error,
                )

        return RASResult(
            Z_balanced=Z,
            converged=converged,
            iterations=max_iterations,
            final_error=final_error,
        )

    def to_model_version(
        self,
        *,
        ras_result: RASResult,
        x_new: np.ndarray,
        sector_codes: list[str],
        base_year: int,
        store: ModelStore,
    ) -> ModelVersion:
        """Register the balanced Z as a new ModelVersion.

        Labels it as "balanced-nowcast" per Section 7.7 spec.

        Args:
            ras_result: Balanced Z from RAS.
            x_new: New gross output vector matching balanced Z.
            sector_codes: Sector code list.
            base_year: Target (nowcast) year.
            store: ModelStore to register with.

        Returns:
            Immutable ModelVersion labeled "balanced-nowcast".
        """
        return store.register(
            Z=ras_result.Z_balanced,
            x=np.asarray(x_new, dtype=np.float64),
            sector_codes=sector_codes,
            base_year=base_year,
            source="balanced-nowcast",
        )
