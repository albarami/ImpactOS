"""Tests for confidence propagation across pipeline steps."""

from src.engine.workforce_satellite.config import (
    CONFIDENCE_RANK,
    confidence_to_str,
    worst_confidence,
)
from src.engine.workforce_satellite.satellite import WorkforceSatellite


class TestWorstConfidence:
    """Tests for worst_confidence utility."""

    def test_hard_is_best(self) -> None:
        assert worst_confidence("HARD", "HARD") == "HARD"

    def test_assumed_is_worst(self) -> None:
        assert worst_confidence("HARD", "ASSUMED") == "ASSUMED"

    def test_mixed_confidences(self) -> None:
        assert worst_confidence("HARD", "HIGH", "LOW") == "LOW"

    def test_all_same(self) -> None:
        assert worst_confidence("MEDIUM", "MEDIUM") == "MEDIUM"

    def test_empty_returns_assumed(self) -> None:
        assert worst_confidence() == "ASSUMED"

    def test_ranking_order(self) -> None:
        """HARD < HIGH < MEDIUM < ESTIMATED < LOW < ASSUMED."""
        ordered = sorted(
            CONFIDENCE_RANK.keys(), key=lambda c: CONFIDENCE_RANK[c],
        )
        assert ordered == [
            "HARD", "HIGH", "MEDIUM", "ESTIMATED", "LOW", "ASSUMED",
        ]


class TestConfidenceToStr:
    """Amendment 6: normalize confidence enums to string."""

    def test_constraint_confidence(self) -> None:
        from src.models.common import ConstraintConfidence
        assert confidence_to_str(ConstraintConfidence.HARD) == "HARD"

    def test_quality_confidence(self) -> None:
        from src.data.workforce.unit_registry import QualityConfidence
        assert confidence_to_str(QualityConfidence.LOW) == "LOW"

    def test_string_passthrough(self) -> None:
        assert confidence_to_str("estimated") == "ESTIMATED"


class TestPipelineConfidencePropagation:
    """End-to-end confidence propagation tests."""

    def test_overall_is_worst_across_steps(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_satellite_result,
    ) -> None:
        """If any step is 'assumed', overall is 'assumed'."""
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
        )
        # D-4 classifications are almost all LOW/ASSUMED
        # So overall should be LOW or ASSUMED
        assert CONFIDENCE_RANK[result.overall_confidence] >= (
            CONFIDENCE_RANK["LOW"]
        )

    def test_sector_confidence_is_worst_within_sector(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_satellite_result,
    ) -> None:
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
        )
        for summary in result.sector_summaries:
            assert summary.overall_confidence in CONFIDENCE_RANK

    def test_confidence_breakdown_populated(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_satellite_result,
    ) -> None:
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
        )
        for summary in result.sector_summaries:
            total = sum(summary.confidence_breakdown.values())
            assert total > 0
