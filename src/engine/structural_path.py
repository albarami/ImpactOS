"""Structural Path Analysis -- power series decomposition engine.

Decomposes the Leontief inverse B = (I - A)^{-1} into its power series
B = I + A + A^2 + ... + A^k, attributing impact contributions to individual
structural paths (i, j, k) and scoring chokepoint sectors via Rasmussen
linkage indices.

Pure deterministic functions. No LLM calls, no side effects.
Given the same inputs, ALWAYS produces the same outputs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.linalg import norm as frobenius_norm

# ---------------------------------------------------------------------------
# Domain errors (Task 1)
# ---------------------------------------------------------------------------


class SPAError(Exception):
    """Base for all SPA domain errors."""


class SPAConfigError(SPAError):
    """Invalid SPA configuration (max_depth/top_k out of bounds)."""

    def __init__(self, message: str, *, reason_code: str = "SPA_INVALID_CONFIG") -> None:
        self.message = message
        self.reason_code = reason_code
        super().__init__(message)


class SPADimensionError(SPAError):
    """Matrix/vector dimension mismatch."""

    def __init__(self, message: str, *, reason_code: str = "SPA_DIMENSION_MISMATCH") -> None:
        self.message = message
        self.reason_code = reason_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Result dataclasses (Task 2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PathContribution:
    """A single (source_sector, target_sector, depth) path contribution."""

    source_sector: int  # j
    source_sector_code: str
    target_sector: int  # i
    target_sector_code: str
    depth: int  # k (0 = direct)
    coefficient: float  # (A^k)[i, j]
    contribution: float  # (A^k)[i, j] * delta_d[j]


@dataclass(frozen=True)
class DepthContrib:
    """Aggregated contribution at a single depth level."""

    signed: float
    absolute: float


@dataclass(frozen=True)
class ChokePointScore:
    """Rasmussen-convention chokepoint score for a single sector."""

    sector_index: int
    sector_code: str
    forward_linkage: float
    backward_linkage: float
    norm_forward: float
    norm_backward: float
    chokepoint_score: float
    is_chokepoint: bool


@dataclass(frozen=True)
class SPAResult:
    """Complete result of a structural path analysis."""

    top_paths: list[PathContribution]
    chokepoints: list[ChokePointScore]
    depth_contributions: dict[int, DepthContrib]
    coverage_ratio: float  # Frobenius-norm, [0, 1]
    max_depth: int
    top_k: int


# ---------------------------------------------------------------------------
# Core computation (Task 2)
# ---------------------------------------------------------------------------


def compute_spa(
    A: np.ndarray,
    B: np.ndarray,
    delta_d: np.ndarray,
    sector_codes: list[str],
    *,
    max_depth: int = 6,
    top_k: int = 20,
) -> SPAResult:
    """Decompose Leontief inverse via power series and score structural paths.

    Args:
        A: Technical coefficients matrix (n, n).
        B: Leontief inverse (I - A)^{-1} (n, n).
        delta_d: Final demand shock vector (n,).
        sector_codes: Sector code labels, length n.
        max_depth: Maximum power series depth, 0..12 inclusive.
        top_k: Number of top path contributions to return, 1..100 inclusive.

    Returns:
        SPAResult with top paths, chokepoints, depth contributions, and
        coverage ratio.

    Raises:
        SPADimensionError: If matrix/vector dimensions are inconsistent.
        SPAConfigError: If max_depth or top_k are out of bounds.
    """
    A = np.asarray(A, dtype=np.float64)
    B = np.asarray(B, dtype=np.float64)
    delta_d = np.asarray(delta_d, dtype=np.float64)

    # ------------------------------------------------------------------
    # 1. Validate dimensions
    # ------------------------------------------------------------------
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise SPADimensionError(
            f"A must be square, got shape {A.shape}",
            reason_code="SPA_DIMENSION_MISMATCH",
        )

    n = A.shape[0]

    if B.shape != (n, n):
        raise SPADimensionError(
            f"B must be ({n},{n}), got shape {B.shape}",
            reason_code="SPA_DIMENSION_MISMATCH",
        )

    if delta_d.shape != (n,):
        raise SPADimensionError(
            f"delta_d must be ({n},), got shape {delta_d.shape}",
            reason_code="SPA_DIMENSION_MISMATCH",
        )

    if len(sector_codes) != n:
        raise SPADimensionError(
            f"sector_codes length {len(sector_codes)} != n={n}",
            reason_code="SPA_DIMENSION_MISMATCH",
        )

    # ------------------------------------------------------------------
    # 2. Validate config
    # ------------------------------------------------------------------
    if not (0 <= max_depth <= 12):
        raise SPAConfigError(
            f"max_depth must be in [0, 12], got {max_depth}",
            reason_code="SPA_INVALID_CONFIG",
        )

    if not (1 <= top_k <= 100):
        raise SPAConfigError(
            f"top_k must be in [1, 100], got {top_k}",
            reason_code="SPA_INVALID_CONFIG",
        )

    # ------------------------------------------------------------------
    # 3-5. Power series: A^0, A^1, ..., A^max_depth
    # ------------------------------------------------------------------
    # Collect all path tuples and depth-level aggregates.
    all_paths: list[tuple[float, int, int, int, float]] = []  # (|c|, k, i, j, c)
    depth_contributions: dict[int, DepthContrib] = {}
    B_hat = np.zeros((n, n), dtype=np.float64)
    A_k = np.eye(n, dtype=np.float64)  # A^0 = I

    for k in range(max_depth + 1):
        # 4. Contribution matrix: C_k[i, j] = A_k[i, j] * delta_d[j]
        C_k = A_k * delta_d[np.newaxis, :]

        # 5. Accumulate B_hat
        B_hat += A_k

        # 8. Depth contributions
        signed = float(np.sum(C_k))
        absolute = float(np.sum(np.abs(C_k)))
        depth_contributions[k] = DepthContrib(signed=signed, absolute=absolute)

        # 7. Collect all (i, j, k) tuples with nonzero contribution
        for i in range(n):
            for j in range(n):
                c = float(C_k[i, j])
                if c != 0.0:
                    all_paths.append((abs(c), k, i, j, c))

        # Advance: A^{k+1} = A^k @ A
        if k < max_depth:
            A_k = A_k @ A

    # ------------------------------------------------------------------
    # 6. Coverage ratio
    # ------------------------------------------------------------------
    norm_B = frobenius_norm(B)
    if norm_B == 0.0:
        coverage_ratio = 1.0
    else:
        coverage_ratio = max(0.0, min(1.0, 1.0 - frobenius_norm(B - B_hat) / norm_B))

    # ------------------------------------------------------------------
    # 7. Sort and take top_k
    # ------------------------------------------------------------------
    # Sort by (|contribution| DESC, k ASC, i ASC, j ASC)
    # Negate |contribution| for ascending sort to get descending.
    all_paths.sort(key=lambda t: (-t[0], t[1], t[2], t[3]))

    top_paths_raw = all_paths[:top_k]

    top_paths: list[PathContribution] = []
    for _abs_c, k, i, j, c in top_paths_raw:
        # Recover coefficient: contribution = coeff * delta_d[j]
        # coeff = A_k[i, j] — but we didn't store A_k per depth.
        # coeff = c / delta_d[j] when delta_d[j] != 0, else coeff = 0
        # However, if c != 0 then delta_d[j] != 0 by construction.
        if delta_d[j] != 0.0:
            coeff = c / delta_d[j]
        else:
            coeff = 0.0

        top_paths.append(
            PathContribution(
                source_sector=j,
                source_sector_code=sector_codes[j],
                target_sector=i,
                target_sector_code=sector_codes[i],
                depth=k,
                coefficient=coeff,
                contribution=c,
            )
        )

    # ------------------------------------------------------------------
    # 9. Chokepoints (Rasmussen convention)
    # ------------------------------------------------------------------
    # backward_linkage[j] = sum_i(B[i, j])  — column sum
    backward_linkage = np.sum(B, axis=0)
    # forward_linkage[i] = sum_j(B[i, j])   — row sum
    forward_linkage = np.sum(B, axis=1)

    # Normalise by cross-sector mean
    mean_bl = float(np.mean(backward_linkage))
    mean_fl = float(np.mean(forward_linkage))

    # Guard against zero mean (degenerate)
    if mean_bl == 0.0:
        norm_bl = np.ones(n, dtype=np.float64)
    else:
        norm_bl = backward_linkage / mean_bl

    if mean_fl == 0.0:
        norm_fl = np.ones(n, dtype=np.float64)
    else:
        norm_fl = forward_linkage / mean_fl

    # Score and flag
    chokepoint_scores: list[tuple[float, int]] = []
    for s in range(n):
        score = float(np.sqrt(norm_fl[s] * norm_bl[s]))
        chokepoint_scores.append((score, s))

    # Rank by score DESC then index ASC
    chokepoint_scores.sort(key=lambda t: (-t[0], t[1]))

    chokepoints: list[ChokePointScore] = []
    for score, s in chokepoint_scores[:top_k]:
        chokepoints.append(
            ChokePointScore(
                sector_index=s,
                sector_code=sector_codes[s],
                forward_linkage=float(forward_linkage[s]),
                backward_linkage=float(backward_linkage[s]),
                norm_forward=float(norm_fl[s]),
                norm_backward=float(norm_bl[s]),
                chokepoint_score=score,
                is_chokepoint=bool(norm_fl[s] > 1.0 and norm_bl[s] > 1.0),
            )
        )

    # ------------------------------------------------------------------
    # 10. Return
    # ------------------------------------------------------------------
    return SPAResult(
        top_paths=top_paths,
        chokepoints=chokepoints,
        depth_contributions=depth_contributions,
        coverage_ratio=coverage_ratio,
        max_depth=max_depth,
        top_k=top_k,
    )
