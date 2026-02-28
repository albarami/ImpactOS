"""Quality scoring engine — all 7 dimensions (MVP-13, Tasks 2-3).

Deterministic scoring functions that produce DimensionAssessment values
with full provenance (inputs_used, rules_triggered) for every dimension.

Deterministic — no LLM calls.
"""

from __future__ import annotations

from src.quality.config import QualityScoringConfig
from src.quality.models import (
    DimensionAssessment,
    QualityDimension,
    QualitySeverity,
    QualityWarning,
    SourceAge,
    SourceUpdateFrequency,
)

# Cadence mapping: SourceUpdateFrequency -> expected days between updates.
_FREQUENCY_DAYS: dict[SourceUpdateFrequency, int] = {
    SourceUpdateFrequency.QUARTERLY: 90,
    SourceUpdateFrequency.ANNUAL: 365,
    SourceUpdateFrequency.BIENNIAL: 730,
    SourceUpdateFrequency.TRIENNIAL: 1095,
    SourceUpdateFrequency.QUINQUENNIAL: 1825,
}

# Confidence weights for constraints dimension.
_CONSTRAINT_WEIGHTS: dict[str, float] = {
    "HARD": 1.0,
    "ESTIMATED": 0.6,
    "ASSUMED": 0.3,
}

# Workforce confidence label -> score mapping.
_WORKFORCE_SCORES: dict[str, float] = {
    "HIGH": 1.0,
    "MEDIUM": 0.6,
    "LOW": 0.3,
}


class QualityScorer:
    """Scores all 7 quality dimensions with configurable thresholds.

    Each scoring method returns a DimensionAssessment with:
    - score (0.0-1.0)
    - applicable flag
    - inputs_used (provenance: what data was fed in)
    - rules_triggered (provenance: which scoring rules fired)
    - warnings (materiality or quality warnings)
    """

    def __init__(self, config: QualityScoringConfig | None = None) -> None:
        self._config = config or QualityScoringConfig()

    # ---------------------------------------------------------------
    # Dimension 1: Vintage
    # ---------------------------------------------------------------

    def score_vintage(
        self,
        base_year: int,
        current_year: int,
    ) -> DimensionAssessment:
        """Score the vintage (age) of the I-O table.

        Walks config.vintage_thresholds to find the first bracket
        where age <= max_age and returns the corresponding score.
        """
        age = current_year - base_year

        score = 0.0
        rule = "vintage_fallback"
        for max_age, bracket_score in self._config.vintage_thresholds:
            if age <= max_age:
                score = bracket_score
                rule = f"vintage_decay_0_{max_age}yr"
                break

        return DimensionAssessment(
            dimension=QualityDimension.VINTAGE,
            score=score,
            applicable=True,
            inputs_used={
                "base_year": base_year,
                "current_year": current_year,
                "age_years": age,
            },
            rules_triggered=[rule],
        )

    # ---------------------------------------------------------------
    # Dimension 2: Mapping
    # ---------------------------------------------------------------

    def score_mapping(
        self,
        coverage_pct: float,
        confidence_dist: dict[str, float],
        residual_pct: float,
        unresolved_pct: float,
        unresolved_spend_pct: float,
    ) -> DimensionAssessment:
        """Score the sector mapping quality.

        Weighted formula:
            0.4 * coverage + 0.3 * HIGH_confidence + 0.2 * (1-residual) + 0.1 * (1-unresolved)

        Generates materiality warnings based on unresolved_spend_pct.
        """
        high_conf = confidence_dist.get("HIGH", 0.0)
        score = (
            0.4 * coverage_pct
            + 0.3 * high_conf
            + 0.2 * (1.0 - residual_pct)
            + 0.1 * (1.0 - unresolved_pct)
        )
        # Clamp to [0, 1] for safety.
        score = max(0.0, min(1.0, score))

        rules: list[str] = ["mapping_weighted_score"]
        warnings: list[QualityWarning] = []

        # Materiality warnings based on unresolved spend percentage.
        if unresolved_spend_pct > self._config.mapping_spend_waiver_pct:
            warnings.append(
                QualityWarning(
                    dimension=QualityDimension.MAPPING,
                    severity=QualitySeverity.WAIVER_REQUIRED,
                    message=(
                        f"Unresolved spend {unresolved_spend_pct:.1f}% exceeds "
                        f"waiver threshold ({self._config.mapping_spend_waiver_pct}%)"
                    ),
                    recommendation="Obtain formal waiver before publication.",
                )
            )
            rules.append("materiality_waiver_required")
        elif unresolved_spend_pct > self._config.mapping_spend_critical_pct:
            warnings.append(
                QualityWarning(
                    dimension=QualityDimension.MAPPING,
                    severity=QualitySeverity.CRITICAL,
                    message=(
                        f"Unresolved spend {unresolved_spend_pct:.1f}% exceeds "
                        f"critical threshold ({self._config.mapping_spend_critical_pct}%)"
                    ),
                    recommendation="Review and resolve unmapped sectors.",
                )
            )
            rules.append("materiality_critical")
        elif unresolved_spend_pct > 0.0:
            warnings.append(
                QualityWarning(
                    dimension=QualityDimension.MAPPING,
                    severity=QualitySeverity.WARNING,
                    message=(
                        f"Unresolved spend {unresolved_spend_pct:.1f}% detected"
                    ),
                    recommendation="Consider mapping remaining sectors.",
                )
            )
            rules.append("materiality_warning")

        return DimensionAssessment(
            dimension=QualityDimension.MAPPING,
            score=score,
            applicable=True,
            inputs_used={
                "coverage_pct": coverage_pct,
                "confidence_dist": confidence_dist,
                "residual_pct": residual_pct,
                "unresolved_pct": unresolved_pct,
                "unresolved_spend_pct": unresolved_spend_pct,
            },
            rules_triggered=rules,
            warnings=warnings,
        )

    # ---------------------------------------------------------------
    # Dimension 3: Assumptions
    # ---------------------------------------------------------------

    def score_assumptions(
        self,
        ranges_coverage_pct: float,
        approval_rate: float,
    ) -> DimensionAssessment:
        """Score assumption quality from coverage and approval rate.

        Score = 0.5 * ranges_coverage_pct + 0.5 * approval_rate
        """
        score = 0.5 * ranges_coverage_pct + 0.5 * approval_rate

        return DimensionAssessment(
            dimension=QualityDimension.ASSUMPTIONS,
            score=score,
            applicable=True,
            inputs_used={
                "ranges_coverage_pct": ranges_coverage_pct,
                "approval_rate": approval_rate,
            },
            rules_triggered=["assumptions_blend"],
        )

    # ---------------------------------------------------------------
    # Dimension 4: Constraints
    # ---------------------------------------------------------------

    def score_constraints(
        self,
        confidence_summary: dict[str, int] | None,
    ) -> DimensionAssessment:
        """Score constraint confidence from HARD/ESTIMATED/ASSUMED counts.

        Weighted average: HARD*1.0 + ESTIMATED*0.6 + ASSUMED*0.3.
        Returns not-applicable when confidence_summary is None or empty.
        """
        if confidence_summary is None or not confidence_summary:
            return DimensionAssessment(
                dimension=QualityDimension.CONSTRAINTS,
                score=0.0,
                applicable=False,
                inputs_used={"confidence_summary": confidence_summary},
                rules_triggered=["constraints_not_applicable"],
            )

        total = sum(confidence_summary.values())
        if total == 0:
            return DimensionAssessment(
                dimension=QualityDimension.CONSTRAINTS,
                score=0.0,
                applicable=False,
                inputs_used={"confidence_summary": confidence_summary},
                rules_triggered=["constraints_not_applicable"],
            )

        weighted_sum = sum(
            count * _CONSTRAINT_WEIGHTS.get(label, 0.0)
            for label, count in confidence_summary.items()
        )
        score = weighted_sum / total

        return DimensionAssessment(
            dimension=QualityDimension.CONSTRAINTS,
            score=score,
            applicable=True,
            inputs_used={"confidence_summary": confidence_summary},
            rules_triggered=["constraints_weighted_average"],
        )

    # ---------------------------------------------------------------
    # Dimension 5: Workforce
    # ---------------------------------------------------------------

    def score_workforce(
        self,
        overall_confidence: str | None,
    ) -> DimensionAssessment:
        """Score workforce data confidence.

        Maps HIGH->1.0, MEDIUM->0.6, LOW->0.3.
        Returns not-applicable when overall_confidence is None.
        """
        if overall_confidence is None:
            return DimensionAssessment(
                dimension=QualityDimension.WORKFORCE,
                score=0.0,
                applicable=False,
                inputs_used={"overall_confidence": overall_confidence},
                rules_triggered=["workforce_not_applicable"],
            )

        score = _WORKFORCE_SCORES.get(overall_confidence, 0.0)

        return DimensionAssessment(
            dimension=QualityDimension.WORKFORCE,
            score=score,
            applicable=True,
            inputs_used={"overall_confidence": overall_confidence},
            rules_triggered=[f"workforce_confidence_{overall_confidence.lower()}"],
        )

    # ---------------------------------------------------------------
    # Dimension 6: Plausibility
    # ---------------------------------------------------------------

    def score_plausibility(
        self,
        multipliers_in_range_pct: float,
        flagged_count: int,
    ) -> DimensionAssessment:
        """Score plausibility from multiplier range check results.

        Score = multipliers_in_range_pct / 100.0
        """
        score = multipliers_in_range_pct / 100.0

        return DimensionAssessment(
            dimension=QualityDimension.PLAUSIBILITY,
            score=score,
            applicable=True,
            inputs_used={
                "multipliers_in_range_pct": multipliers_in_range_pct,
                "flagged_count": flagged_count,
            },
            rules_triggered=["plausibility_range_check"],
        )

    # ---------------------------------------------------------------
    # Dimension 7: Freshness
    # ---------------------------------------------------------------

    def score_freshness(
        self,
        source_ages: list[SourceAge],
    ) -> DimensionAssessment:
        """Score data freshness across all time-scored sources.

        Filters out PER_ENGAGEMENT sources, computes age/cadence ratios,
        walks freshness_ratio_thresholds for each, then averages.
        """
        # Filter out PER_ENGAGEMENT sources.
        time_scored = [
            sa
            for sa in source_ages
            if sa.expected_frequency != SourceUpdateFrequency.PER_ENGAGEMENT
        ]

        if not time_scored:
            return DimensionAssessment(
                dimension=QualityDimension.FRESHNESS,
                score=0.0,
                applicable=False,
                inputs_used={"source_ratios": []},
                rules_triggered=["freshness_no_time_scored_sources"],
            )

        source_ratios: list[dict[str, object]] = []
        scores: list[float] = []

        for sa in time_scored:
            cadence_days = _FREQUENCY_DAYS[sa.expected_frequency]
            ratio = sa.age_days / cadence_days

            # Walk thresholds to find the score for this ratio.
            source_score = 0.0
            rule = "freshness_fallback"
            for max_ratio, bracket_score in self._config.freshness_ratio_thresholds:
                if ratio <= max_ratio:
                    source_score = bracket_score
                    rule = f"freshness_ratio_le_{max_ratio}"
                    break

            scores.append(source_score)
            source_ratios.append(
                {
                    "source_name": sa.source_name,
                    "ratio": round(ratio, 4),
                    "score": source_score,
                    "rule": rule,
                }
            )

        avg_score = sum(scores) / len(scores)

        return DimensionAssessment(
            dimension=QualityDimension.FRESHNESS,
            score=avg_score,
            applicable=True,
            inputs_used={"source_ratios": source_ratios},
            rules_triggered=["freshness_ratio_average"],
        )
