"""Satellite accounts — MVP-3 Section 7.5.

Employment impacts, import leakage, and value-added computed as
linear transforms of Δx. All coefficients versioned for traceability.

Pure deterministic functions — no LLM calls.
"""

from dataclasses import dataclass
from uuid import UUID

import numpy as np


@dataclass(frozen=True)
class SatelliteCoefficients:
    """Versioned satellite coefficient vectors.

    All vectors are length n (number of sectors).
    Coefficients are per-unit-output ratios.
    """

    jobs_coeff: np.ndarray     # jobs_i / output_i
    import_ratio: np.ndarray   # imports_i / output_i
    va_ratio: np.ndarray       # value_added_i / output_i
    version_id: UUID


@dataclass(frozen=True)
class SatelliteResult:
    """Result of satellite account computation."""

    delta_jobs: np.ndarray             # Δjobs = diag(jobs_coeff) · Δx
    delta_imports: np.ndarray          # Δimports = diag(import_ratio) · Δx
    delta_domestic_output: np.ndarray  # Δdomestic = Δx - Δimports
    delta_va: np.ndarray               # ΔVA = diag(va_ratio) · Δx
    coefficients_version_id: UUID


class SatelliteAccounts:
    """Deterministic satellite impact calculator (Section 7.5)."""

    def compute(
        self,
        *,
        delta_x: np.ndarray,
        coefficients: SatelliteCoefficients,
    ) -> SatelliteResult:
        """Compute all satellite impacts from output change vector.

        Args:
            delta_x: Total output change vector (n).
            coefficients: Versioned satellite coefficient vectors.

        Returns:
            SatelliteResult with employment, import, domestic, and VA impacts.

        Raises:
            ValueError: If dimension mismatch between delta_x and coefficients.
        """
        delta_x = np.asarray(delta_x, dtype=np.float64)
        n = len(delta_x)

        if (
            len(coefficients.jobs_coeff) != n
            or len(coefficients.import_ratio) != n
            or len(coefficients.va_ratio) != n
        ):
            msg = (
                f"dimension mismatch: delta_x has {n} elements but "
                f"coefficients have {len(coefficients.jobs_coeff)} sectors."
            )
            raise ValueError(msg)

        # Section 7.5: all satellite impacts are element-wise products
        delta_jobs = coefficients.jobs_coeff * delta_x
        delta_imports = coefficients.import_ratio * delta_x
        delta_domestic_output = delta_x - delta_imports
        delta_va = coefficients.va_ratio * delta_x

        return SatelliteResult(
            delta_jobs=delta_jobs,
            delta_imports=delta_imports,
            delta_domestic_output=delta_domestic_output,
            delta_va=delta_va,
            coefficients_version_id=coefficients.version_id,
        )
