"""Portfolio optimization engine — deterministic binary knapsack.

Pure deterministic solver. No LLM calls, no external solver dependencies.
Given the same inputs, ALWAYS produces the same outputs.
"""

from __future__ import annotations

import itertools
from collections import Counter
from dataclasses import dataclass
from uuid import UUID


class PortfolioError(Exception):
    """Base for all portfolio optimization domain errors."""


class PortfolioConfigError(PortfolioError):
    """Invalid portfolio optimization configuration."""

    def __init__(self, message: str, *, reason_code: str = "PORTFOLIO_INVALID_CONFIG") -> None:
        self.message = message
        self.reason_code = reason_code
        super().__init__(message)


class PortfolioInfeasibleError(PortfolioError):
    """No feasible subset exists under given constraints."""

    def __init__(self, message: str, *, reason_code: str = "PORTFOLIO_INFEASIBLE") -> None:
        self.message = message
        self.reason_code = reason_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateRun:
    """A single candidate scenario run for portfolio selection."""

    run_id: UUID
    objective_value: float
    cost: float
    group_key: str | None = None


@dataclass(frozen=True)
class PortfolioResult:
    """Immutable result of portfolio optimization."""

    selected_run_ids: list[UUID]
    total_objective: float
    total_cost: float
    solver_method: str
    candidates_evaluated: int
    feasible_count: int


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_CANDIDATES = 25


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------


def _validate_inputs(
    candidates: list[CandidateRun],
    budget: float,
    min_selected: int,
    max_selected: int | None,
    group_caps: dict[str, int] | None,
) -> None:
    """Validate all inputs in the specified order, raising on first failure."""
    if not candidates:
        raise PortfolioConfigError(
            "No candidates provided.",
            reason_code="PORTFOLIO_NO_CANDIDATES",
        )

    run_ids = [c.run_id for c in candidates]
    if len(run_ids) != len(set(run_ids)):
        raise PortfolioConfigError(
            "Duplicate run_ids in candidates.",
            reason_code="PORTFOLIO_DUPLICATE_CANDIDATES",
        )

    if len(candidates) > MAX_CANDIDATES:
        raise PortfolioConfigError(
            f"Too many candidates ({len(candidates)} > {MAX_CANDIDATES}).",
            reason_code="PORTFOLIO_CANDIDATE_LIMIT_EXCEEDED",
        )

    if budget <= 0:
        raise PortfolioConfigError(
            f"Budget must be positive, got {budget}.",
            reason_code="PORTFOLIO_INVALID_CONFIG",
        )

    if min_selected < 1:
        raise PortfolioConfigError(
            f"min_selected must be >= 1, got {min_selected}.",
            reason_code="PORTFOLIO_INVALID_CONFIG",
        )

    if max_selected is not None and max_selected < 1:
        raise PortfolioConfigError(
            f"max_selected must be >= 1, got {max_selected}.",
            reason_code="PORTFOLIO_INVALID_CONFIG",
        )

    if max_selected is not None and max_selected < min_selected:
        raise PortfolioConfigError(
            f"max_selected ({max_selected}) < min_selected ({min_selected}).",
            reason_code="PORTFOLIO_INVALID_CONFIG",
        )

    if group_caps is not None:
        for key, cap in group_caps.items():
            if cap < 1:
                raise PortfolioConfigError(
                    f"Group cap for '{key}' must be >= 1, got {cap}.",
                    reason_code="PORTFOLIO_INVALID_CONFIG",
                )


def _passes_group_caps(
    subset: tuple[CandidateRun, ...],
    group_caps: dict[str, int],
) -> bool:
    """Check whether a subset satisfies all group cap constraints."""
    counts: Counter[str] = Counter()
    for c in subset:
        if c.group_key is not None and c.group_key in group_caps:
            counts[c.group_key] += 1
            if counts[c.group_key] > group_caps[c.group_key]:
                return False
    return True


def optimize_portfolio(
    candidates: list[CandidateRun],
    budget: float,
    *,
    min_selected: int = 1,
    max_selected: int | None = None,
    group_caps: dict[str, int] | None = None,
) -> PortfolioResult:
    """Solve exact binary knapsack over candidate scenario runs.

    Enumerates all 2^n subsets (n <= 25) to find the subset that
    maximizes total objective_value subject to budget, cardinality,
    and group-cap constraints. Deterministic: same inputs always
    produce the same output.

    Args:
        candidates: Scenario runs to choose from.
        budget: Maximum total cost allowed.
        min_selected: Minimum number of runs to select (>= 1).
        max_selected: Maximum number of runs to select (None = no limit).
        group_caps: Per-group maximum selection counts.

    Returns:
        PortfolioResult with the optimal selection.

    Raises:
        PortfolioConfigError: Invalid inputs.
        PortfolioInfeasibleError: No feasible subset exists.
    """
    _validate_inputs(candidates, budget, min_selected, max_selected, group_caps)

    # Sort candidates by run_id ASC for deterministic traversal
    sorted_candidates = sorted(candidates, key=lambda c: str(c.run_id))

    n = len(sorted_candidates)
    effective_max = max_selected if max_selected is not None else n
    resolved_group_caps = group_caps if group_caps is not None else {}

    best_objective: float | None = None
    best_subset: tuple[CandidateRun, ...] | None = None
    feasible_count = 0

    for size in range(min_selected, effective_max + 1):
        for combo in itertools.combinations(sorted_candidates, size):
            total_cost = sum(c.cost for c in combo)
            if total_cost > budget:
                continue

            if resolved_group_caps and not _passes_group_caps(combo, resolved_group_caps):
                continue

            feasible_count += 1
            total_obj = sum(c.objective_value for c in combo)

            if best_objective is None or total_obj > best_objective:
                best_objective = total_obj
                best_subset = combo
            elif total_obj == best_objective:
                # Tie-break: lexicographically smallest sorted run_id tuple
                combo_ids = tuple(str(c.run_id) for c in combo)
                best_ids = tuple(str(c.run_id) for c in best_subset)  # type: ignore[union-attr]
                if combo_ids < best_ids:
                    best_subset = combo

    if best_subset is None:
        raise PortfolioInfeasibleError(
            "No feasible portfolio found under the given constraints.",
            reason_code="PORTFOLIO_INFEASIBLE",
        )

    selected_ids = [c.run_id for c in best_subset]
    return PortfolioResult(
        selected_run_ids=selected_ids,
        total_objective=sum(c.objective_value for c in best_subset),
        total_cost=sum(c.cost for c in best_subset),
        solver_method="exact_binary_knapsack_v1",
        candidates_evaluated=n,
        feasible_count=feasible_count,
    )
