"""Tests for ILO employment parser (D-3).

Uses saved fixture at tests/fixtures/ilo_employment_sample.json.
No live API calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data.parsers.ilo_employment_parser import (
    EmploymentObservation,
    ILOEmploymentData,
    parse_ilo_employment_file,
    save_curated_employment,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "fixtures" / "ilo_employment_sample.json"
)


@pytest.mark.skipif(
    not FIXTURE_PATH.exists(),
    reason="ILO fixture not available",
)
class TestILOParser:
    """Parse ILOSTAT employment data from saved fixture."""

    def test_parse_returns_data(self) -> None:
        """Parsing fixture produces ILOEmploymentData."""
        result = parse_ilo_employment_file(FIXTURE_PATH)
        assert isinstance(result, ILOEmploymentData)

    def test_country_is_sau(self) -> None:
        """Country is SAU."""
        result = parse_ilo_employment_file(FIXTURE_PATH)
        assert result.country == "SAU"

    def test_observations_not_empty(self) -> None:
        """Fixture produces observations."""
        result = parse_ilo_employment_file(FIXTURE_PATH)
        assert result.total_observations > 0

    def test_observation_type(self) -> None:
        """Each observation is EmploymentObservation."""
        result = parse_ilo_employment_file(FIXTURE_PATH)
        assert isinstance(result.observations[0], EmploymentObservation)

    def test_years_detected(self) -> None:
        """Years 2021-2023 detected from fixture."""
        result = parse_ilo_employment_file(FIXTURE_PATH)
        assert 2021 in result.years
        assert 2023 in result.years

    def test_sections_detected(self) -> None:
        """ISIC sections A, B, C, TOTAL detected."""
        result = parse_ilo_employment_file(FIXTURE_PATH)
        assert "TOTAL" in result.sections
        assert "A" in result.sections
        assert "B" in result.sections
        assert "C" in result.sections

    def test_values_positive(self) -> None:
        """Employment values are positive."""
        result = parse_ilo_employment_file(FIXTURE_PATH)
        for obs in result.observations:
            assert obs.value > 0

    def test_total_gt_parts(self) -> None:
        """Total employment exceeds individual sectors."""
        result = parse_ilo_employment_file(FIXTURE_PATH)
        for year in result.years:
            total = sum(
                o.value for o in result.observations
                if o.year == year and o.section_code == "TOTAL"
            )
            parts = sum(
                o.value for o in result.observations
                if o.year == year and o.section_code != "TOTAL"
            )
            if total > 0:
                assert total > parts  # Total includes other sectors

    def test_save_curated(self, tmp_path: Path) -> None:
        """Save curated employment file."""
        result = parse_ilo_employment_file(FIXTURE_PATH)
        out = save_curated_employment(result, tmp_path)
        assert out.exists()
        assert out.stat().st_size > 50
