"""Tests for full WorkforceSatellite pipeline."""


from src.engine.workforce_satellite.satellite import WorkforceSatellite


class TestFullPipeline:
    """Full 4-step pipeline tests."""

    def test_produces_valid_result(
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
        assert len(result.sector_summaries) == 2
        assert result.total_jobs > 0

    def test_total_jobs_matches_sum(
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
        sector_sum = sum(s.total_jobs for s in result.sector_summaries)
        assert abs(result.total_jobs - sector_sum) < 0.01

    def test_economy_wide_aggregates_consistent(
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
        # Tier aggregates should sum to total jobs
        tier_sum = (
            result.total_saudi_ready
            + result.total_saudi_trainable
            + result.total_expat_reliant
        )
        assert abs(tier_sum - result.total_jobs) < 0.01

    def test_known_limitations_present(
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
        assert len(result.known_limitations) >= 4

    def test_confidence_caveats_present(
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
        assert len(result.confidence_caveats) >= 4

    def test_bridge_version_populated(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_satellite_result, coefficient_provenance,
    ) -> None:
        """Amendment 4: provenance from __init__ objects."""
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
            coefficient_provenance=coefficient_provenance,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
        )
        assert result.bridge_version == "2024"
        assert result.classification_version == "2024"
        assert result.coefficient_provenance["employment_coeff_year"] == 2024

    def test_without_nitaqat_all_no_target(
        self, two_sector_bridge, two_sector_classifications,
        two_sector_satellite_result,
    ) -> None:
        ws = WorkforceSatellite(
            occupation_bridge=two_sector_bridge,
            nationality_classifications=two_sector_classifications,
            nitaqat_targets=None,
        )
        result = ws.analyze(
            satellite_result=two_sector_satellite_result,
            sector_codes=["A", "F"],
        )
        assert result.sectors_no_target == 2
