"""Parity benchmark gate -- Sprint 18.

Standalone deterministic module. Takes a LoadedModel, runs a golden scenario
through LeontiefSolver.solve(), compares outputs against expected values.
Pure function -- no DB, no side effects.

No LLM calls. Agent-to-Math boundary: this is engine code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np

from src.engine.leontief import LeontiefSolver
from src.engine.model_store import LoadedModel


@dataclass(frozen=True)
class ParityMetric:
    """Result of comparing one metric against its expected value."""

    metric_name: str
    expected: float
    actual: float
    relative_error: float
    tolerance: float = 0.001
    passed: bool = True
    reason_code: str | None = None


@dataclass(frozen=True)
class ParityResult:
    """Aggregate result of a parity benchmark check."""

    passed: bool
    benchmark_id: str
    tolerance: float
    metrics: list[ParityMetric]
    reason_code: str | None
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _compute_relative_error(actual: float, expected: float) -> float:
    """Compute relative error, handling zero expected with absolute comparison."""
    if abs(expected) < 1e-10:
        return abs(actual - expected)
    return abs(actual - expected) / abs(expected)


def run_parity_check(
    *,
    model: LoadedModel,
    benchmark_scenario: dict,
    tolerance: float = 0.001,
) -> ParityResult:
    """Run parity check comparing model solver output against benchmark values.

    NEVER raises. Returns ParityResult with appropriate reason_code on failure.

    Args:
        model: A LoadedModel to test.
        benchmark_scenario: Dict with benchmark_id, scenario, expected_outputs.
        tolerance: Maximum allowed relative error (default 0.1%).

    Returns:
        ParityResult -- always returned, never raises.
    """
    benchmark_id = benchmark_scenario.get("benchmark_id", "unknown")
    now = datetime.now(UTC)

    # Check for missing baseline
    expected_outputs = benchmark_scenario.get("expected_outputs")
    if not expected_outputs:
        return ParityResult(
            passed=False,
            benchmark_id=benchmark_id,
            tolerance=tolerance,
            metrics=[],
            reason_code="PARITY_MISSING_BASELINE",
            checked_at=now,
        )

    # Run solver -- catch any exception
    try:
        scenario = benchmark_scenario["scenario"]
        shock_vector = np.array(scenario["shock_vector"], dtype=np.float64)
        solver = LeontiefSolver()
        result = solver.solve(loaded_model=model, delta_d=shock_vector)
    except Exception:
        return ParityResult(
            passed=False,
            benchmark_id=benchmark_id,
            tolerance=tolerance,
            metrics=[],
            reason_code="PARITY_ENGINE_ERROR",
            checked_at=now,
        )

    # Compute actual outputs
    actuals: dict[str, float] = {}
    actuals["total_output"] = float(np.sum(result.delta_x_total))

    scenario = benchmark_scenario["scenario"]
    if "jobs_coeff" in scenario:
        jobs_coeff = np.array(scenario["jobs_coeff"], dtype=np.float64)
        actuals["employment"] = float(np.sum(result.delta_x_total * jobs_coeff))

    # Compare each expected metric against actuals
    metrics: list[ParityMetric] = []
    for metric_name, expected_val in expected_outputs.items():
        expected_val = float(expected_val)

        if metric_name not in actuals:
            metrics.append(
                ParityMetric(
                    metric_name=metric_name,
                    expected=expected_val,
                    actual=0.0,
                    relative_error=float("inf"),
                    tolerance=tolerance,
                    passed=False,
                    reason_code="PARITY_METRIC_MISSING",
                )
            )
            continue

        actual_val = actuals[metric_name]
        rel_err = _compute_relative_error(actual_val, expected_val)
        passed = rel_err <= tolerance

        metrics.append(
            ParityMetric(
                metric_name=metric_name,
                expected=expected_val,
                actual=actual_val,
                relative_error=rel_err,
                tolerance=tolerance,
                passed=passed,
                reason_code=None if passed else "PARITY_TOLERANCE_BREACH",
            )
        )

    all_passed = all(m.passed for m in metrics)
    if all_passed:
        summary_reason = None
    elif any(m.reason_code == "PARITY_METRIC_MISSING" for m in metrics):
        summary_reason = "PARITY_METRIC_MISSING"
    else:
        summary_reason = "PARITY_TOLERANCE_BREACH"

    return ParityResult(
        passed=all_passed,
        benchmark_id=benchmark_id,
        tolerance=tolerance,
        metrics=metrics,
        reason_code=summary_reason,
        checked_at=now,
    )
