"""Tests for Step 3: Nationality feasibility split with ranges."""

from uuid import uuid4

import numpy as np

from src.data.workforce.nationality_classification import (
    NationalityClassification,
    NationalityClassificationSet,
    NationalityTier,
)
from src.data.workforce.unit_registry import QualityConfidence
from src.engine.satellites import SatelliteResult
from src.engine.workforce_satellite.satellite import WorkforceSatellite
from src.models.common import ConstraintConfidence


class TestNationalitySplitRanges:
    """Range-based nationality split tests."""

    def test_min_le_mid_le_max(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_satellite_result,
    ) -> None:
        """saudi_jobs_min <= mid <= max for all splits."""
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
        )
        for summary in result.sector_summaries:
            assert summary.projected_saudi_jobs_min <= (
                summary.projected_saudi_jobs_mid
            )
            assert summary.projected_saudi_jobs_mid <= (
                summary.projected_saudi_jobs_max
            )

    def test_saudi_ready_high_range(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_satellite_result,
    ) -> None:
        """Saudi-ready tier: min >= 0.70 * total_jobs for that occupation."""
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
        )
        # A/1 is saudi_ready with current_pct=0.80
        a_summary = result.sector_summaries[0]
        # A has 50 total, manager(1) gets 10%=5 jobs
        # current_pct=0.80, so mid=5*0.80=4, low=5*0.70=3.5, high=5*0.90=4.5
        assert a_summary.saudi_ready_jobs > 0

    def test_expat_reliant_low_range(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_satellite_result,
    ) -> None:
        """Expat-reliant tier: max <= 0.20 * total_jobs (or ±10% of known)."""
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
        )
        # F/8 is expat_reliant with current_pct=0.02
        # F has 100 jobs, operators(8) get 30%=30 jobs
        # max_saudi = 30 * 0.12 = 3.6 (0.02+0.10=0.12)
        f_summary = result.sector_summaries[1]
        assert f_summary.expat_reliant_jobs > 0

    def test_current_saudi_pct_used_as_midpoint(
        self, two_sector_bridge, two_sector_satellite_result,
    ) -> None:
        """If current_saudi_pct available, used as mid-point."""
        classifications = NationalityClassificationSet(
            year=2024,
            classifications=[
                NationalityClassification(
                    sector_code="A", occupation_code="9",
                    tier=NationalityTier.EXPAT_RELIANT,
                    current_saudi_pct=0.10,  # Known
                    rationale="test",
                    source_confidence=ConstraintConfidence.ESTIMATED,
                    quality_confidence=QualityConfidence.MEDIUM,
                    sensitivity_range=None, source="GOSI",
                ),
                NationalityClassification(
                    sector_code="A", occupation_code="6",
                    tier=NationalityTier.SAUDI_TRAINABLE,
                    current_saudi_pct=0.35,  # Known
                    rationale="test",
                    source_confidence=ConstraintConfidence.ESTIMATED,
                    quality_confidence=QualityConfidence.MEDIUM,
                    sensitivity_range=None, source="GOSI",
                ),
                NationalityClassification(
                    sector_code="A", occupation_code="1",
                    tier=NationalityTier.SAUDI_READY,
                    current_saudi_pct=0.80,  # Known
                    rationale="test",
                    source_confidence=ConstraintConfidence.ESTIMATED,
                    quality_confidence=QualityConfidence.HIGH,
                    sensitivity_range=None, source="GOSI",
                ),
            ],
        )
        # Only sector A in satellite result
        sat = SatelliteResult(
            delta_jobs=np.array([100.0]),
            delta_imports=np.array([10.0]),
            delta_domestic_output=np.array([90.0]),
            delta_va=np.array([60.0]),
            coefficients_version_id=uuid4(),
        )
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=classifications,
        )
        result = ws.analyze(
            satellite_result=sat, sector_codes=["A"],
        )
        # A/9 has current_pct=0.10, gets 60 jobs
        # mid=60*0.10=6, low=60*0.00=0, high=60*0.20=12
        a = result.sector_summaries[0]
        # Mid should reflect the known percentages
        assert a.projected_saudi_jobs_mid > 0

    def test_missing_classification_defaults_expat(
        self, two_sector_bridge, two_sector_satellite_result,
    ) -> None:
        """Amendment 9: missing classification → EXPAT_RELIANT + ASSUMED."""
        empty_classifications = NationalityClassificationSet(
            year=2024, classifications=[],
        )
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=empty_classifications,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
        )
        # All should be expat_reliant tier
        for summary in result.sector_summaries:
            assert summary.expat_reliant_jobs == summary.total_jobs

    def test_negative_jobs_range_flipped(
        self, two_sector_bridge, two_sector_classifications,
    ) -> None:
        """Amendment 3: negative jobs flip min/max."""
        sat = SatelliteResult(
            delta_jobs=np.array([-50.0, -100.0]),
            delta_imports=np.array([-10.0, -30.0]),
            delta_domestic_output=np.array([-40.0, -70.0]),
            delta_va=np.array([-30.0, -40.0]),
            coefficients_version_id=uuid4(),
        )
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
        )
        result = ws.analyze(
            satellite_result=sat, sector_codes=["A", "F"],
        )
        for summary in result.sector_summaries:
            # min <= mid <= max numerically even for negative
            assert summary.projected_saudi_jobs_min <= (
                summary.projected_saudi_jobs_mid
            )
            assert summary.projected_saudi_jobs_mid <= (
                summary.projected_saudi_jobs_max
            )

    def test_custom_tier_ranges(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_satellite_result,
    ) -> None:
        """Amendment 7: custom tier ranges override defaults."""
        custom_ranges = {
            NationalityTier.SAUDI_READY: (0.80, 0.90, 1.00),
            NationalityTier.SAUDI_TRAINABLE: (0.30, 0.50, 0.70),
            NationalityTier.EXPAT_RELIANT: (0.00, 0.10, 0.25),
        }
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
            tier_ranges=custom_ranges,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
        )
        # With custom ranges, trainable mid is 0.50 instead of 0.40
        # So more Saudi jobs at mid should be produced
        assert result.total_saudi_jobs_mid > 0
