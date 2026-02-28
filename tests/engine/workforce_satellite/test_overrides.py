"""Tests for Knowledge Flywheel override mechanism."""

from src.data.workforce.nationality_classification import (
    ClassificationOverride,
    NationalityTier,
)
from src.engine.workforce_satellite.satellite import WorkforceSatellite


class TestClassificationOverrides:
    """Tests for override path."""

    def test_override_changes_tier(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_satellite_result,
    ) -> None:
        """Override changes tier for specific (sector, occupation) pair."""
        overrides = [
            ClassificationOverride(
                sector_code="F",
                occupation_code="8",
                original_tier=NationalityTier.EXPAT_RELIANT,
                override_tier=NationalityTier.SAUDI_TRAINABLE,
                overridden_by="analyst",
                engagement_id="eng-001",
                rationale="New training program available",
                timestamp="2024-06-01",
            ),
        ]
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
            overrides=overrides,
        )
        # F/8 was expat_reliant, now saudi_trainable
        f_summary = result.sector_summaries[1]
        # trainable should increase (F/8 operators = 30% of F jobs = 30 jobs)
        assert f_summary.saudi_trainable_jobs > 0
        # Operators were expat_reliant, now part of trainable
        assert "8" in f_summary.training_gap_occupations

    def test_override_reflected_in_result(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_satellite_result,
    ) -> None:
        overrides = [
            ClassificationOverride(
                sector_code="F",
                occupation_code="8",
                original_tier=NationalityTier.EXPAT_RELIANT,
                override_tier=NationalityTier.SAUDI_TRAINABLE,
                overridden_by="analyst",
                engagement_id="eng-001",
                rationale="Training program",
                timestamp="2024-06-01",
            ),
        ]
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
            overrides=overrides,
        )
        assert len(result.overrides_applied) == 1
        ov = result.overrides_applied[0]
        assert ov.sector_code == "F"
        assert ov.occupation_code == "8"
        assert ov.original_tier == NationalityTier.EXPAT_RELIANT
        assert ov.override_tier == NationalityTier.SAUDI_TRAINABLE

    def test_original_classification_unchanged(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_satellite_result,
    ) -> None:
        """Override produces new set, original unchanged."""
        overrides = [
            ClassificationOverride(
                sector_code="F",
                occupation_code="8",
                original_tier=NationalityTier.EXPAT_RELIANT,
                override_tier=NationalityTier.SAUDI_READY,
                overridden_by="analyst",
                engagement_id=None,
                rationale="Test",
                timestamp="2024-06-01",
            ),
        ]
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
        )
        ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
            overrides=overrides,
        )
        # Original classification should still be expat_reliant
        orig = two_sector_classifications.get_tier("F", "8")
        assert orig is not None
        assert orig.tier == NationalityTier.EXPAT_RELIANT

    def test_override_caveat_added(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_satellite_result,
    ) -> None:
        """Amendment 10: dynamic caveat for override."""
        overrides = [
            ClassificationOverride(
                sector_code="F",
                occupation_code="8",
                original_tier=NationalityTier.EXPAT_RELIANT,
                override_tier=NationalityTier.SAUDI_TRAINABLE,
                overridden_by="analyst",
                engagement_id=None,
                rationale="Test",
                timestamp="2024-06-01",
            ),
        ]
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
            overrides=overrides,
        )
        override_caveats = [
            c for c in result.confidence_caveats
            if "override" in c.lower()
        ]
        assert len(override_caveats) >= 1
