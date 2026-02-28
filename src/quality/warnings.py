"""Warning engine — severity-based checks across quality dimensions (MVP-13).

Examines DimensionAssessments produced by the QualityScorer and generates
QualityWarnings at calibrated severity levels (INFO, WARNING, CRITICAL,
WAIVER_REQUIRED).

Deterministic -- no LLM calls.
"""

from __future__ import annotations

from collections import Counter

from src.quality.config import QualityScoringConfig
from src.quality.models import (
    DimensionAssessment,
    QualityDimension,
    QualitySeverity,
    QualityWarning,
)


class WarningEngine:
    """Generates severity-calibrated warnings from dimension assessments.

    Each ``check_*`` method inspects a single DimensionAssessment's
    ``inputs_used`` dict and returns zero or more QualityWarning objects.
    ``check_all`` orchestrates routing across all dimensions.
    """

    def __init__(self, config: QualityScoringConfig | None = None) -> None:
        self._config = config or QualityScoringConfig()

    # ---------------------------------------------------------------
    # Dimension checks
    # ---------------------------------------------------------------

    def check_vintage(self, da: DimensionAssessment) -> list[QualityWarning]:
        """Check model vintage age and produce warnings.

        * age >= 8 -> CRITICAL
        * age >= 5 -> WARNING
        * age < 5  -> no warning

        Recommendation: update to a more recent IO table.
        """
        warnings: list[QualityWarning] = []
        age: int = int(da.inputs_used["age_years"])  # type: ignore[arg-type]
        recommendation = "Consider updating to a more recent IO table"

        if age >= 8:
            warnings.append(
                QualityWarning(
                    dimension=QualityDimension.VINTAGE,
                    severity=QualitySeverity.CRITICAL,
                    message=f"Model vintage is {age} years old",
                    recommendation=recommendation,
                )
            )
        elif age >= 5:
            warnings.append(
                QualityWarning(
                    dimension=QualityDimension.VINTAGE,
                    severity=QualitySeverity.WARNING,
                    message=f"Model vintage is {age} years old",
                    recommendation=recommendation,
                )
            )

        return warnings

    def check_mapping(self, da: DimensionAssessment) -> list[QualityWarning]:
        """Check mapping quality and produce warnings.

        Unresolved spend percentage thresholds:
        * >5.0% -> WAIVER_REQUIRED
        * >1.0% -> CRITICAL
        * >0.0% -> WARNING

        Coverage check:
        * coverage_pct < 0.8 -> WARNING
        """
        warnings: list[QualityWarning] = []
        unresolved_spend_pct: float = float(da.inputs_used["unresolved_spend_pct"])  # type: ignore[arg-type]
        coverage_pct: float = float(da.inputs_used["coverage_pct"])  # type: ignore[arg-type]

        # Spend-based warnings (mutually exclusive tiers).
        if unresolved_spend_pct > 5.0:
            warnings.append(
                QualityWarning(
                    dimension=QualityDimension.MAPPING,
                    severity=QualitySeverity.WAIVER_REQUIRED,
                    message=f"Unresolved mapping covers {unresolved_spend_pct}% of spend",
                )
            )
        elif unresolved_spend_pct > 1.0:
            warnings.append(
                QualityWarning(
                    dimension=QualityDimension.MAPPING,
                    severity=QualitySeverity.CRITICAL,
                    message=f"Unresolved mapping covers {unresolved_spend_pct}% of spend",
                )
            )
        elif unresolved_spend_pct > 0.0:
            warnings.append(
                QualityWarning(
                    dimension=QualityDimension.MAPPING,
                    severity=QualitySeverity.WARNING,
                    message=f"Minor unresolved mapping ({unresolved_spend_pct}% of spend)",
                )
            )

        # Coverage-based warning.
        if coverage_pct < 0.8:
            pct_display = coverage_pct * 100
            warnings.append(
                QualityWarning(
                    dimension=QualityDimension.MAPPING,
                    severity=QualitySeverity.WARNING,
                    message=f"Mapping coverage is only {pct_display}%",
                )
            )

        return warnings

    def check_assumptions(self, da: DimensionAssessment) -> list[QualityWarning]:
        """Check assumption ranges coverage and produce warnings.

        * ranges_coverage_pct < 0.5 -> WARNING with recommendation
        """
        warnings: list[QualityWarning] = []
        ranges_coverage_pct: float = float(da.inputs_used["ranges_coverage_pct"])  # type: ignore[arg-type]

        if ranges_coverage_pct < 0.5:
            pct_display = ranges_coverage_pct * 100
            warnings.append(
                QualityWarning(
                    dimension=QualityDimension.ASSUMPTIONS,
                    severity=QualitySeverity.WARNING,
                    message=f"Only {pct_display}% of assumptions have sensitivity ranges",
                    recommendation="Add ranges to enable sensitivity analysis",
                )
            )

        return warnings

    def check_constraints(self, da: DimensionAssessment) -> list[QualityWarning]:
        """Check constraint confidence distribution and produce warnings.

        Returns empty if dimension is not applicable.
        * >50% ASSUMED -> WARNING
        """
        if not da.applicable:
            return []

        warnings: list[QualityWarning] = []
        confidence_summary: dict[str, int] = da.inputs_used["confidence_summary"]  # type: ignore[assignment]

        if not confidence_summary:
            return []

        total = sum(confidence_summary.values())
        if total == 0:
            return []

        assumed_count = confidence_summary.get("ASSUMED", 0)
        assumed_pct = assumed_count / total * 100

        if assumed_pct > 50:
            warnings.append(
                QualityWarning(
                    dimension=QualityDimension.CONSTRAINTS,
                    severity=QualitySeverity.WARNING,
                    message="Over 50% of constraints are assumed",
                )
            )

        return warnings

    def check_freshness(self, da: DimensionAssessment) -> list[QualityWarning]:
        """Check data source freshness ratios and produce warnings.

        Returns empty if dimension is not applicable.
        For each source:
        * ratio > 2.0 -> CRITICAL "{source} is significantly overdue for update"
        * ratio > 1.5 -> WARNING "{source} is overdue for update"
        """
        if not da.applicable:
            return []

        warnings: list[QualityWarning] = []
        source_ratios: list[dict[str, object]] = da.inputs_used.get("source_ratios", [])  # type: ignore[assignment]

        for entry in source_ratios:
            source_name: str = str(entry["source_name"])
            ratio: float = float(entry["ratio"])  # type: ignore[arg-type]

            if ratio > 2.0:
                warnings.append(
                    QualityWarning(
                        dimension=QualityDimension.FRESHNESS,
                        severity=QualitySeverity.CRITICAL,
                        message=f"{source_name} is significantly overdue for update",
                    )
                )
            elif ratio > 1.5:
                warnings.append(
                    QualityWarning(
                        dimension=QualityDimension.FRESHNESS,
                        severity=QualitySeverity.WARNING,
                        message=f"{source_name} is overdue for update",
                    )
                )

        return warnings

    def check_nowcast(self, model_source: str | None) -> list[QualityWarning]:
        """Check if model source is a nowcast or balanced estimate.

        * Contains "nowcast" or "balanced" (case-insensitive) -> INFO
        """
        if model_source is None:
            return []

        lower = model_source.lower()
        if "nowcast" in lower or "balanced" in lower:
            return [
                QualityWarning(
                    dimension=QualityDimension.VINTAGE,
                    severity=QualitySeverity.INFO,
                    message="Model is a nowcast/balanced estimate",
                )
            ]

        return []

    # ---------------------------------------------------------------
    # Aggregation
    # ---------------------------------------------------------------

    def check_all(
        self,
        dimension_assessments: list[DimensionAssessment],
        model_source: str | None = None,
    ) -> list[QualityWarning]:
        """Run all applicable check methods and aggregate warnings.

        Routes each DimensionAssessment to the appropriate check by
        ``da.dimension``, then runs ``check_nowcast``.
        """
        # Dimension -> check method routing table.
        dispatch: dict[
            QualityDimension,
            type[object],
        ] = {
            QualityDimension.VINTAGE: self.check_vintage,  # type: ignore[dict-item]
            QualityDimension.MAPPING: self.check_mapping,  # type: ignore[dict-item]
            QualityDimension.ASSUMPTIONS: self.check_assumptions,  # type: ignore[dict-item]
            QualityDimension.CONSTRAINTS: self.check_constraints,  # type: ignore[dict-item]
            QualityDimension.FRESHNESS: self.check_freshness,  # type: ignore[dict-item]
        }

        all_warnings: list[QualityWarning] = []

        for da in dimension_assessments:
            check_fn = dispatch.get(da.dimension)
            if check_fn is not None:
                all_warnings.extend(check_fn(da))  # type: ignore[operator]

        # Always run nowcast check.
        all_warnings.extend(self.check_nowcast(model_source))

        return all_warnings

    @staticmethod
    def count_by_severity(warnings: list[QualityWarning]) -> dict[str, int]:
        """Return counts keyed by severity value.

        Example: {"CRITICAL": 1, "WARNING": 2, "INFO": 1}
        """
        counter: Counter[str] = Counter()
        for w in warnings:
            counter[w.severity.value] += 1
        return dict(counter)
