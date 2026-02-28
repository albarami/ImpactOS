"""Quality assessment orchestrator service (MVP-13 Task 9).

Collects inputs, delegates to QualityScorer for per-dimension scoring,
runs WarningEngine for cross-cutting checks, and produces a versioned
RunQualityAssessment with merged warnings.

Deterministic -- no LLM calls.
"""

from __future__ import annotations

from uuid import UUID

from src.quality.config import QualityScoringConfig
from src.quality.models import (
    DimensionAssessment,
    QualityWarning,
    RunQualityAssessment,
    SourceAge,
)
from src.quality.scorer import QualityScorer
from src.quality.warnings import WarningEngine


class QualityAssessmentService:
    """Orchestrates a full quality assessment across all 7 dimensions.

    Collects raw inputs, decides which dimensions are assessable based
    on input completeness, delegates scoring to ``QualityScorer``, runs
    ``WarningEngine`` for additional warnings, and returns a versioned
    ``RunQualityAssessment``.

    Version tracking (Amendment 5): if a ``run_id`` is provided, the
    service tracks how many assessments have been produced for that run
    and increments the ``assessment_version`` accordingly.
    """

    def __init__(self, config: QualityScoringConfig | None = None) -> None:
        self._config = config or QualityScoringConfig()
        self._scorer = QualityScorer(config=self._config)
        self._warning_engine = WarningEngine(config=self._config)
        self._version_tracker: dict[UUID, int] = {}  # run_id -> current version

    def assess(
        self,
        *,
        base_year: int,
        current_year: int,
        # Mapping inputs (all None = not applicable)
        mapping_coverage_pct: float | None = None,
        mapping_confidence_dist: dict[str, float] | None = None,
        mapping_residual_pct: float | None = None,
        mapping_unresolved_pct: float | None = None,
        mapping_unresolved_spend_pct: float | None = None,
        # Assumption inputs
        assumption_ranges_coverage_pct: float | None = None,
        assumption_approval_rate: float | None = None,
        # Constraint inputs
        constraint_confidence_summary: dict[str, int] | None = None,
        # Workforce inputs
        workforce_overall_confidence: str | None = None,
        # Plausibility inputs
        plausibility_in_range_pct: float | None = None,
        plausibility_flagged_count: int | None = None,
        # Freshness inputs
        source_ages: list[SourceAge] | None = None,
        # Run context
        run_id: UUID | None = None,
        model_source: str | None = None,
    ) -> RunQualityAssessment:
        """Perform a full quality assessment.

        Steps:
        1. Always score vintage (required inputs: base_year, current_year).
        2. Score mapping only if ALL 5 mapping inputs are provided.
        3. Score assumptions only if BOTH assumption inputs are provided.
        4. Score constraints — pass through (scorer handles None -> not applicable).
        5. Score workforce — pass through (scorer handles None -> not applicable).
        6. Score plausibility only if BOTH plausibility inputs are provided.
        7. Score freshness only if source_ages is not None and not empty.
        8. Collect all dimension assessments.
        9. Compute composite score via scorer.
        10. Run warning engine for additional warnings.
        11. Merge warnings (avoiding duplicates by using warning_id).
        12. Handle versioning via run_id tracker.
        """
        dimension_assessments: list[DimensionAssessment] = []

        # 1. Vintage — always scored.
        dimension_assessments.append(
            self._scorer.score_vintage(base_year, current_year)
        )

        # 2. Mapping — only if ALL 5 inputs are provided.
        mapping_inputs = [
            mapping_coverage_pct,
            mapping_confidence_dist,
            mapping_residual_pct,
            mapping_unresolved_pct,
            mapping_unresolved_spend_pct,
        ]
        if all(v is not None for v in mapping_inputs):
            dimension_assessments.append(
                self._scorer.score_mapping(
                    coverage_pct=mapping_coverage_pct,  # type: ignore[arg-type]
                    confidence_dist=mapping_confidence_dist,  # type: ignore[arg-type]
                    residual_pct=mapping_residual_pct,  # type: ignore[arg-type]
                    unresolved_pct=mapping_unresolved_pct,  # type: ignore[arg-type]
                    unresolved_spend_pct=mapping_unresolved_spend_pct,  # type: ignore[arg-type]
                )
            )

        # 3. Assumptions — only if BOTH inputs are provided.
        if (
            assumption_ranges_coverage_pct is not None
            and assumption_approval_rate is not None
        ):
            dimension_assessments.append(
                self._scorer.score_assumptions(
                    ranges_coverage_pct=assumption_ranges_coverage_pct,
                    approval_rate=assumption_approval_rate,
                )
            )

        # 4. Constraints — pass through (scorer handles None -> not applicable).
        dimension_assessments.append(
            self._scorer.score_constraints(
                confidence_summary=constraint_confidence_summary,
            )
        )

        # 5. Workforce — pass through (scorer handles None -> not applicable).
        dimension_assessments.append(
            self._scorer.score_workforce(
                overall_confidence=workforce_overall_confidence,
            )
        )

        # 6. Plausibility — only if BOTH inputs are provided.
        if (
            plausibility_in_range_pct is not None
            and plausibility_flagged_count is not None
        ):
            dimension_assessments.append(
                self._scorer.score_plausibility(
                    multipliers_in_range_pct=plausibility_in_range_pct,
                    flagged_count=plausibility_flagged_count,
                )
            )

        # 7. Freshness — only if source_ages is not None and not empty.
        if source_ages is not None and len(source_ages) > 0:
            dimension_assessments.append(
                self._scorer.score_freshness(source_ages=source_ages)
            )

        # 8-9. Compute composite score from all dimension assessments.
        assessment = self._scorer.composite_score(dimension_assessments)

        # 10. Run warning engine for additional cross-cutting warnings.
        engine_warnings = self._warning_engine.check_all(
            dimension_assessments, model_source
        )

        # 11. Merge warnings — collect existing warning_ids to avoid duplicates.
        existing_ids = {w.warning_id for w in assessment.warnings}
        merged_warnings = list(assessment.warnings)
        for w in engine_warnings:
            if w.warning_id not in existing_ids:
                merged_warnings.append(w)
                existing_ids.add(w.warning_id)

        # Recount severity totals after merge.
        from src.quality.models import QualitySeverity

        waiver_required_count = sum(
            1 for w in merged_warnings if w.severity == QualitySeverity.WAIVER_REQUIRED
        )
        critical_count = sum(
            1 for w in merged_warnings if w.severity == QualitySeverity.CRITICAL
        )
        warning_count = sum(
            1 for w in merged_warnings if w.severity == QualitySeverity.WARNING
        )
        info_count = sum(
            1 for w in merged_warnings if w.severity == QualitySeverity.INFO
        )

        # 12. Handle versioning (Amendment 5).
        if run_id is not None:
            current_version = self._version_tracker.get(run_id, 0) + 1
            self._version_tracker[run_id] = current_version
        else:
            current_version = 1

        # Since RunQualityAssessment is frozen, create a new instance
        # with updated version, run_id, and merged warnings.
        return assessment.model_copy(
            update={
                "assessment_version": current_version,
                "run_id": run_id,
                "warnings": merged_warnings,
                "waiver_required_count": waiver_required_count,
                "critical_count": critical_count,
                "warning_count": warning_count,
                "info_count": info_count,
            }
        )
