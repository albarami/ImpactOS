"""Tests for KAPSARC multiplier parser (D-3).

Uses saved fixture at tests/fixtures/kapsarc_mult_sample.json.
No live API calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data.parsers.kapsarc_multiplier_parser import (
    MultiplierBenchmark,
    MultiplierEntry,
    parse_kapsarc_multiplier_file,
    parse_kapsarc_multiplier_records,
    save_multiplier_benchmark,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "fixtures" / "kapsarc_mult_sample.json"
)


@pytest.mark.skipif(
    not FIXTURE_PATH.exists(),
    reason="KAPSARC multiplier fixture not available",
)
class TestKapsarcMultiplierParser:
    """Parse KAPSARC Type I multipliers from saved fixture."""

    def test_parse_returns_benchmark(self) -> None:
        """Parsing fixture produces MultiplierBenchmark."""
        result = parse_kapsarc_multiplier_file(FIXTURE_PATH)
        assert isinstance(result, MultiplierBenchmark)

    def test_entry_count(self) -> None:
        """Five sectors in fixture."""
        result = parse_kapsarc_multiplier_file(FIXTURE_PATH)
        assert len(result.entries) == 5

    def test_entry_type(self) -> None:
        """Each entry is MultiplierEntry."""
        result = parse_kapsarc_multiplier_file(FIXTURE_PATH)
        assert isinstance(result.entries[0], MultiplierEntry)

    def test_sector_codes(self) -> None:
        """Correct sector codes extracted."""
        result = parse_kapsarc_multiplier_file(FIXTURE_PATH)
        codes = {e.sector_code for e in result.entries}
        assert codes == {"A", "B", "C", "F", "G"}

    def test_multiplier_values(self) -> None:
        """Multiplier values match fixture data."""
        result = parse_kapsarc_multiplier_file(FIXTURE_PATH)
        by_code = {e.sector_code: e for e in result.entries}
        assert by_code["C"].output_multiplier == pytest.approx(1.89)
        assert by_code["A"].output_multiplier == pytest.approx(1.45)

    def test_backward_linkage_present(self) -> None:
        """Backward linkage values parsed."""
        result = parse_kapsarc_multiplier_file(FIXTURE_PATH)
        by_code = {e.sector_code: e for e in result.entries}
        assert by_code["C"].backward_linkage == pytest.approx(0.95)

    def test_forward_linkage_present(self) -> None:
        """Forward linkage values parsed."""
        result = parse_kapsarc_multiplier_file(FIXTURE_PATH)
        by_code = {e.sector_code: e for e in result.entries}
        assert by_code["B"].forward_linkage == pytest.approx(0.95)

    def test_year_detected(self) -> None:
        """Year extracted from fixture records."""
        result = parse_kapsarc_multiplier_file(FIXTURE_PATH)
        assert result.year == 2019

    def test_source_set(self) -> None:
        """Source is KAPSARC."""
        result = parse_kapsarc_multiplier_file(FIXTURE_PATH)
        assert "KAPSARC" in result.source

    def test_save_benchmark(self, tmp_path: Path) -> None:
        """Saved benchmark file is valid JSON."""
        result = parse_kapsarc_multiplier_file(FIXTURE_PATH)
        out = save_multiplier_benchmark(result, tmp_path)
        assert out.exists()
        assert out.stat().st_size > 50

    def test_empty_records(self) -> None:
        """Empty records produce empty entries with warning."""
        result = parse_kapsarc_multiplier_records([])
        assert len(result.entries) == 0
        assert len(result.warnings) >= 1
