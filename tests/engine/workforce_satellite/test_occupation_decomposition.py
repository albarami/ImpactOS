"""Tests for Step 2: Occupation decomposition."""


from src.engine.workforce_satellite.satellite import WorkforceSatellite


class TestOccupationDecomposition:
    """Tests for _decompose_occupations."""

    def test_shares_sum_preserved(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_satellite_result,
    ) -> None:
        """Total jobs preserved after decomposition."""
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
        )
        for summary in result.sector_summaries:
            occ_total = sum(oi.jobs for oi in summary.occupation_impacts)
            assert abs(occ_total - summary.total_jobs) < 0.01

    def test_agriculture_occupation_shares(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_satellite_result,
    ) -> None:
        """A: 60% elementary, 30% agricultural, 10% managers."""
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
        )
        a_summary = result.sector_summaries[0]
        assert a_summary.sector_code == "A"
        occ_map = {
            oi.occupation_code: oi for oi in a_summary.occupation_impacts
        }
        # A has 50 jobs total
        assert abs(occ_map["9"].jobs - 30.0) < 0.01  # 60% of 50
        assert abs(occ_map["6"].jobs - 15.0) < 0.01  # 30% of 50
        assert abs(occ_map["1"].jobs - 5.0) < 0.01   # 10% of 50

    def test_construction_craft_workers_majority(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_satellite_result,
    ) -> None:
        """F: 50% craft, 30% operators, 20% elementary."""
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
        )
        f_summary = result.sector_summaries[1]
        assert f_summary.sector_code == "F"
        occ_map = {
            oi.occupation_code: oi for oi in f_summary.occupation_impacts
        }
        # F has 100 jobs total. Craft(7) + Operators(8) + Elementary(9) > 60%
        craft_ops_elem = (
            occ_map["7"].jobs + occ_map["8"].jobs + occ_map["9"].jobs
        )
        assert craft_ops_elem == 100.0

    def test_missing_bridge_defaults_to_elementary(
        self, two_sector_classifications,
        two_sector_satellite_result,
    ) -> None:
        """Amendment 9: missing bridge → all jobs to elementary."""
        from src.data.workforce.occupation_bridge import OccupationBridge
        empty_bridge = OccupationBridge(
            year=2024, entries=[], metadata={},
        )
        ws = WorkforceSatellite(
            occupation_bridge=empty_bridge,
            nationality_classifications=two_sector_classifications,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
        )
        for summary in result.sector_summaries:
            assert len(summary.occupation_impacts) == 1
            assert summary.occupation_impacts[0].occupation_code == "9"
            assert summary.occupation_impacts[0].bridge_confidence == "ASSUMED"

    def test_occupation_labels_populated(
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
            for oi in summary.occupation_impacts:
                assert oi.occupation_label != ""

    def test_bridge_confidence_populated(
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
            for oi in summary.occupation_impacts:
                assert oi.bridge_confidence in {
                    "HIGH", "MEDIUM", "LOW", "ASSUMED",
                }
