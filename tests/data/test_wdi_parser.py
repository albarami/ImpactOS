"""Tests for WDI parser (D-3).

Uses saved fixture at tests/fixtures/wdi_gdp_sample.json.
No live API calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data.parsers.wdi_parser import (
    WDIObservation,
    WDITimeSeries,
    parse_wdi_file,
    parse_wdi_records,
    save_curated_macro_indicators,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "fixtures" / "wdi_gdp_sample.json"
)


@pytest.mark.skipif(
    not FIXTURE_PATH.exists(),
    reason="WDI fixture not available",
)
class TestWDIParser:
    """Parse World Bank WDI data from saved fixture."""

    def test_parse_returns_time_series(self) -> None:
        """Parsing fixture produces WDITimeSeries."""
        result = parse_wdi_file(FIXTURE_PATH)
        assert isinstance(result, WDITimeSeries)

    def test_indicator_code(self) -> None:
        """Indicator code extracted."""
        result = parse_wdi_file(FIXTURE_PATH)
        assert result.indicator_code == "NY.GDP.MKTP.CD"

    def test_country(self) -> None:
        """Country is SAU."""
        result = parse_wdi_file(FIXTURE_PATH)
        assert result.country == "SAU"

    def test_observation_count(self) -> None:
        """5 observations in fixture."""
        result = parse_wdi_file(FIXTURE_PATH)
        assert len(result.observations) == 5

    def test_observation_type(self) -> None:
        """Each observation is WDIObservation."""
        result = parse_wdi_file(FIXTURE_PATH)
        assert isinstance(result.observations[0], WDIObservation)

    def test_years_sorted_ascending(self) -> None:
        """Observations sorted by year ascending."""
        result = parse_wdi_file(FIXTURE_PATH)
        years = [o.year for o in result.observations]
        assert years == sorted(years)

    def test_latest_year(self) -> None:
        """Latest year is 2023."""
        result = parse_wdi_file(FIXTURE_PATH)
        assert result.latest_year == 2023

    def test_latest_value(self) -> None:
        """Latest value is 2023 GDP."""
        result = parse_wdi_file(FIXTURE_PATH)
        assert result.latest_value is not None
        # 2023 GDP approximately 1.06 trillion USD
        assert result.latest_value > 1e12

    def test_null_values_handled(self) -> None:
        """Records with null values produce None observations."""
        records = [
            {
                "indicator": {"id": "TEST", "value": "Test"},
                "country": {"id": "SAU", "value": "Saudi Arabia"},
                "date": "2023",
                "value": None,
            },
        ]
        result = parse_wdi_records(records)
        assert result.observations[0].value is None

    def test_save_curated(self, tmp_path: Path) -> None:
        """Save macro indicators file."""
        ts = parse_wdi_file(FIXTURE_PATH)
        series_map = {"gdp": ts}
        out = save_curated_macro_indicators(series_map, tmp_path)
        assert out.exists()
        assert out.stat().st_size > 50

    def test_empty_records(self) -> None:
        """Empty records produce empty series."""
        result = parse_wdi_records([])
        assert len(result.observations) == 0
        assert result.latest_year is None
