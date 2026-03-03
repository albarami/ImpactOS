"""RunSeries delta computation -- Sprint 17.

Deterministic scenario-vs-baseline delta per year per metric per sector.
No LLM calls, no side effects.
"""

from typing import Any


class RunSeriesValidationError(Exception):
    """Structured validation error for RunSeries operations."""

    def __init__(self, *, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


def validate_baseline_has_series(baseline_annual_rows: list[Any]) -> None:
    """Validate that baseline run has annual series rows."""
    if not baseline_annual_rows:
        raise RunSeriesValidationError(
            reason_code="RS_BASELINE_NO_SERIES",
            message="Baseline run has no annual series rows. "
                    "Re-run baseline with Sprint 17+ engine to generate series.",
        )


AnnualData = dict[int, dict[str, dict[str, float]]]
# shape: {year: {metric_type: {sector: value}}}


def compute_delta_series(
    scenario_annual: AnnualData,
    baseline_annual: AnnualData,
) -> AnnualData:
    """Compute scenario - baseline delta for overlapping years and metrics.

    Returns:
        Delta data in same shape as input: {year: {metric: {sector: delta}}}.

    Raises:
        RunSeriesValidationError: If years or metrics don't overlap.
    """
    overlap_years = sorted(set(scenario_annual) & set(baseline_annual))
    if not overlap_years:
        raise RunSeriesValidationError(
            reason_code="RS_YEAR_MISMATCH",
            message=f"No overlapping years between scenario {sorted(scenario_annual)} "
                    f"and baseline {sorted(baseline_annual)}.",
        )

    delta: AnnualData = {}
    for year in overlap_years:
        s_metrics = scenario_annual[year]
        b_metrics = baseline_annual[year]
        overlap_metrics = set(s_metrics) & set(b_metrics)
        if not overlap_metrics:
            raise RunSeriesValidationError(
                reason_code="RS_BASELINE_METRIC_MISMATCH",
                message=f"No overlapping metrics for year {year}: "
                        f"scenario={sorted(s_metrics)}, baseline={sorted(b_metrics)}.",
            )
        delta[year] = {}
        for metric in sorted(overlap_metrics):
            delta[year][metric] = {}
            for sector in s_metrics[metric]:
                s_val = s_metrics[metric].get(sector, 0.0)
                b_val = b_metrics[metric].get(sector, 0.0)
                delta[year][metric][sector] = s_val - b_val
    return delta
