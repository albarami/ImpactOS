"""Quality scoring configuration (MVP-13).

Provides configurable weights, thresholds, and caps for the composite
quality scoring engine. All defaults are tuned for Saudi I-O modeling
engagements and can be overridden per workspace or engagement.

Deterministic -- no LLM calls.
"""

from __future__ import annotations

from pydantic import Field

from src.models.common import ImpactOSBase


class QualityScoringConfig(ImpactOSBase):
    """Configuration for the quality scoring engine.

    Controls how dimension scores are weighted into a composite grade,
    how vintage and freshness are scored, and completeness caps.
    """

    dimension_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "VINTAGE": 0.15,
            "MAPPING": 0.25,
            "ASSUMPTIONS": 0.15,
            "CONSTRAINTS": 0.10,
            "WORKFORCE": 0.10,
            "PLAUSIBILITY": 0.15,
            "FRESHNESS": 0.10,
        },
    )

    grade_thresholds: dict[str, float] = Field(
        default_factory=lambda: {
            "A": 0.85,
            "B": 0.70,
            "C": 0.55,
            "D": 0.40,
        },
    )

    vintage_thresholds: list[tuple[int, float]] = Field(
        default_factory=lambda: [
            (2, 1.0),
            (4, 0.7),
            (7, 0.4),
            (99, 0.2),
        ],
    )

    freshness_ratio_thresholds: list[tuple[float, float]] = Field(
        default_factory=lambda: [
            (1.0, 1.0),
            (1.5, 0.7),
            (2.0, 0.4),
            (99.0, 0.2),
        ],
    )

    completeness_cap_50: str = "C"
    completeness_cap_30: str = "D"

    mapping_spend_waiver_pct: float = 5.0
    mapping_spend_critical_pct: float = 1.0
    mapping_coverage_warning_pct: float = 0.8

    vintage_warning_age: int = 5
    vintage_critical_age: int = 8
