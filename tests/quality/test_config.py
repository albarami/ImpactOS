"""Tests for quality module scoring configuration.

Covers: QualityScoringConfig default values, weight sum, grade thresholds,
vintage thresholds, freshness ratios, and custom weight overrides.
"""

import pytest
from pydantic import ValidationError

from src.quality.config import QualityScoringConfig


# ===================================================================
# QualityScoringConfig defaults
# ===================================================================


class TestQualityScoringConfigDefaults:
    """QualityScoringConfig has correct defaults."""

    def test_default_weights_sum_to_one(self) -> None:
        config = QualityScoringConfig()
        total = sum(config.dimension_weights.values())
        assert abs(total - 1.0) < 1e-9

    def test_default_weights_keys(self) -> None:
        config = QualityScoringConfig()
        expected_keys = {
            "VINTAGE",
            "MAPPING",
            "ASSUMPTIONS",
            "CONSTRAINTS",
            "WORKFORCE",
            "PLAUSIBILITY",
            "FRESHNESS",
        }
        assert set(config.dimension_weights.keys()) == expected_keys

    def test_default_weight_values(self) -> None:
        config = QualityScoringConfig()
        assert config.dimension_weights["VINTAGE"] == 0.15
        assert config.dimension_weights["MAPPING"] == 0.25
        assert config.dimension_weights["ASSUMPTIONS"] == 0.15
        assert config.dimension_weights["CONSTRAINTS"] == 0.10
        assert config.dimension_weights["WORKFORCE"] == 0.10
        assert config.dimension_weights["PLAUSIBILITY"] == 0.15
        assert config.dimension_weights["FRESHNESS"] == 0.10

    def test_default_grade_thresholds(self) -> None:
        config = QualityScoringConfig()
        assert config.grade_thresholds["A"] == 0.85
        assert config.grade_thresholds["B"] == 0.70
        assert config.grade_thresholds["C"] == 0.55
        assert config.grade_thresholds["D"] == 0.40

    def test_default_grade_thresholds_count(self) -> None:
        config = QualityScoringConfig()
        assert len(config.grade_thresholds) == 4

    def test_default_vintage_thresholds_count(self) -> None:
        config = QualityScoringConfig()
        assert len(config.vintage_thresholds) == 4

    def test_default_vintage_thresholds_values(self) -> None:
        config = QualityScoringConfig()
        assert config.vintage_thresholds[0] == (2, 1.0)
        assert config.vintage_thresholds[1] == (4, 0.7)
        assert config.vintage_thresholds[2] == (7, 0.4)
        assert config.vintage_thresholds[3] == (99, 0.2)

    def test_default_freshness_ratio_thresholds_count(self) -> None:
        config = QualityScoringConfig()
        assert len(config.freshness_ratio_thresholds) == 4

    def test_default_freshness_ratio_thresholds_values(self) -> None:
        config = QualityScoringConfig()
        assert config.freshness_ratio_thresholds[0] == (1.0, 1.0)
        assert config.freshness_ratio_thresholds[1] == (1.5, 0.7)
        assert config.freshness_ratio_thresholds[2] == (2.0, 0.4)
        assert config.freshness_ratio_thresholds[3] == (99.0, 0.2)

    def test_default_completeness_caps(self) -> None:
        config = QualityScoringConfig()
        assert config.completeness_cap_50 == "C"
        assert config.completeness_cap_30 == "D"

    def test_default_mapping_spend_thresholds(self) -> None:
        config = QualityScoringConfig()
        assert config.mapping_spend_waiver_pct == 5.0
        assert config.mapping_spend_critical_pct == 1.0


# ===================================================================
# QualityScoringConfig custom overrides
# ===================================================================


class TestQualityScoringConfigCustom:
    """QualityScoringConfig allows custom weight overrides."""

    def test_custom_weights_override(self) -> None:
        custom_weights = {
            "VINTAGE": 0.20,
            "MAPPING": 0.20,
            "ASSUMPTIONS": 0.20,
            "CONSTRAINTS": 0.10,
            "WORKFORCE": 0.10,
            "PLAUSIBILITY": 0.10,
            "FRESHNESS": 0.10,
        }
        config = QualityScoringConfig(dimension_weights=custom_weights)
        assert config.dimension_weights["VINTAGE"] == 0.20
        assert config.dimension_weights["MAPPING"] == 0.20
        total = sum(config.dimension_weights.values())
        assert abs(total - 1.0) < 1e-9

    def test_custom_grade_thresholds(self) -> None:
        custom_thresholds = {"A": 0.90, "B": 0.75, "C": 0.60, "D": 0.45}
        config = QualityScoringConfig(grade_thresholds=custom_thresholds)
        assert config.grade_thresholds["A"] == 0.90
        assert config.grade_thresholds["B"] == 0.75

    def test_custom_completeness_caps(self) -> None:
        config = QualityScoringConfig(
            completeness_cap_50="D",
            completeness_cap_30="F",
        )
        assert config.completeness_cap_50 == "D"
        assert config.completeness_cap_30 == "F"

    def test_custom_mapping_spend_thresholds(self) -> None:
        config = QualityScoringConfig(
            mapping_spend_waiver_pct=10.0,
            mapping_spend_critical_pct=2.0,
        )
        assert config.mapping_spend_waiver_pct == 10.0
        assert config.mapping_spend_critical_pct == 2.0
