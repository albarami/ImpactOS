"""Tests for Step 4: Nitaqat compliance check."""

from uuid import uuid4

import numpy as np

from src.engine.satellites import SatelliteResult
from src.engine.workforce_satellite.satellite import WorkforceSatellite
from src.engine.workforce_satellite.schemas import BaselineSectorWorkforce


class TestNitaqatCompliance:
    """Tests for _check_compliance."""

    def test_compliant_with_baseline(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_nitaqat, two_sector_satellite_result,
    ) -> None:
        """Sector meets target at mid-point → COMPLIANT or AT_RISK."""
        # Create baseline where A already has high Saudi share
        baseline = [
            BaselineSectorWorkforce(
                sector_code="A",
                total_employment=1000.0,
                saudi_employment=200.0,  # 20% (target 10%)
                saudi_share=0.20,
                source="GOSI", year=2023,
            ),
            BaselineSectorWorkforce(
                sector_code="F",
                total_employment=5000.0,
                saudi_employment=1000.0,  # 20% (target 12%)
                saudi_share=0.20,
                source="GOSI", year=2023,
            ),
        ]
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
            nitaqat_targets=two_sector_nitaqat,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
            baseline_workforce=baseline,
        )
        # Both sectors have high existing Saudi share
        for s in result.sector_summaries:
            assert s.nitaqat_compliance_status in {
                "COMPLIANT", "AT_RISK",
            }

    def test_non_compliant_sector(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_nitaqat,
    ) -> None:
        """Sector far below target → NON_COMPLIANT."""
        # Very large workforce + near-zero Saudi + small incremental
        # Even high_saudi_pct of increment can't reach target_low
        baseline = [
            BaselineSectorWorkforce(
                sector_code="F",
                total_employment=100000.0,
                saudi_employment=10.0,  # 0.01%
                saudi_share=0.0001,
                source="GOSI", year=2023,
            ),
        ]
        sat = SatelliteResult(
            delta_jobs=np.array([100.0]),
            delta_imports=np.array([0.0]),
            delta_domestic_output=np.array([100.0]),
            delta_va=np.array([40.0]),
            coefficients_version_id=uuid4(),
        )
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
            nitaqat_targets=two_sector_nitaqat,
        )
        result = ws.analyze(
            satellite_result=sat,
            sector_codes=["F"],
            baseline_workforce=baseline,
        )
        f = result.sector_summaries[0]
        assert f.nitaqat_compliance_status == "NON_COMPLIANT"
        assert f.nitaqat_gap_jobs is not None
        assert f.nitaqat_gap_jobs > 0

    def test_no_target_sector(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_satellite_result,
    ) -> None:
        """Sector with no Nitaqat target → NO_TARGET."""
        from src.data.workforce.nitaqat_macro_targets import (
            MacroSaudizationTargets,
        )
        # Targets only for A, not F
        targets = MacroSaudizationTargets(
            targets={"A": None, "F": None},
            effective_as_of="2024-01-01",
        )
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
            nitaqat_targets=targets,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
        )
        for s in result.sector_summaries:
            assert s.nitaqat_compliance_status == "NO_TARGET"

    def test_insufficient_data_without_baseline(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_nitaqat, two_sector_satellite_result,
    ) -> None:
        """Amendment 1: no baseline → INSUFFICIENT_DATA."""
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
            nitaqat_targets=two_sector_nitaqat,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
            # No baseline_workforce!
        )
        for s in result.sector_summaries:
            assert s.nitaqat_compliance_status == "INSUFFICIENT_DATA"

    def test_compliance_is_diagnostic_only(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_nitaqat, two_sector_satellite_result,
        two_sector_baseline,
    ) -> None:
        """Compliance does NOT modify job counts."""
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
            nitaqat_targets=two_sector_nitaqat,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
            baseline_workforce=two_sector_baseline,
        )
        # Total jobs should match satellite result, not be clipped
        assert abs(result.total_jobs - 150.0) < 0.01  # 50 + 100

    def test_total_gap_is_sum_of_sector_gaps(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_nitaqat, two_sector_satellite_result,
        two_sector_baseline,
    ) -> None:
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
            nitaqat_targets=two_sector_nitaqat,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
            baseline_workforce=two_sector_baseline,
        )
        sector_gap_sum = sum(
            s.nitaqat_gap_jobs or 0.0 for s in result.sector_summaries
        )
        assert abs(result.total_nitaqat_gap_jobs - sector_gap_sum) < 0.01

    def test_nitaqat_target_range_preserved(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_nitaqat, two_sector_satellite_result,
        two_sector_baseline,
    ) -> None:
        """Amendment 2: target_range_low and target_range_high preserved."""
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
            nitaqat_targets=two_sector_nitaqat,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
            baseline_workforce=two_sector_baseline,
        )
        for s in result.sector_summaries:
            assert s.nitaqat_target_range is not None
            low, high = s.nitaqat_target_range
            assert low <= high
