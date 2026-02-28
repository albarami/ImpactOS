"""Tests for KAPSARC IO table parser (D-3).

Uses saved fixture at tests/fixtures/kapsarc_io_sample.json.
No live API calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data.parsers.kapsarc_io_parser import (
    KapsarcIOParseResult,
    parse_kapsarc_io_file,
    parse_kapsarc_io_records,
    save_curated_io,
)

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "kapsarc_io_sample.json"


@pytest.mark.skipif(
    not FIXTURE_PATH.exists(),
    reason="KAPSARC IO fixture not available",
)
class TestKapsarcIOParser:
    """Parse KAPSARC IO table data from saved fixture."""

    def test_parse_returns_results(self) -> None:
        """Parsing fixture produces non-empty results."""
        results = parse_kapsarc_io_file(FIXTURE_PATH)
        assert len(results) >= 1

    def test_result_is_correct_type(self) -> None:
        """Each result is KapsarcIOParseResult."""
        results = parse_kapsarc_io_file(FIXTURE_PATH)
        assert isinstance(results[0], KapsarcIOParseResult)

    def test_year_detected(self) -> None:
        """Year 2019 is detected from fixture records."""
        results = parse_kapsarc_io_file(FIXTURE_PATH)
        years = {r.year for r in results}
        assert 2019 in years

    def test_sectors_extracted(self) -> None:
        """Sector codes A, B, C extracted from 3x3 fixture."""
        results = parse_kapsarc_io_file(FIXTURE_PATH)
        r = results[0]
        assert set(r.sector_codes) == {"A", "B", "C"}

    def test_z_matrix_shape(self) -> None:
        """Z matrix is 3x3 for 3-sector fixture."""
        results = parse_kapsarc_io_file(FIXTURE_PATH)
        r = results[0]
        assert r.Z.shape == (3, 3)

    def test_z_matrix_values(self) -> None:
        """Z matrix contains expected values from fixture."""
        results = parse_kapsarc_io_file(FIXTURE_PATH)
        r = results[0]
        # A->A = 5000, A->B = 1000, A->C = 2000
        idx_a = r.sector_codes.index("A")
        idx_b = r.sector_codes.index("B")
        assert r.Z[idx_a, idx_a] == pytest.approx(5000.0)
        assert r.Z[idx_a, idx_b] == pytest.approx(1000.0)

    def test_x_vector_length(self) -> None:
        """x vector length matches sector count."""
        results = parse_kapsarc_io_file(FIXTURE_PATH)
        r = results[0]
        assert len(r.x) == len(r.sector_codes)

    def test_total_output_positive(self) -> None:
        """Total output is positive."""
        results = parse_kapsarc_io_file(FIXTURE_PATH)
        assert results[0].total_output > 0

    def test_save_curated_io(self, tmp_path: Path) -> None:
        """Saved curated file can be read back."""
        results = parse_kapsarc_io_file(FIXTURE_PATH)
        out = save_curated_io(results[0], tmp_path)
        assert out.exists()
        assert out.stat().st_size > 100

    def test_empty_records_returns_empty(self) -> None:
        """Empty records list produces empty results."""
        results = parse_kapsarc_io_records([])
        assert len(results) == 0

    def test_record_count_tracked(self) -> None:
        """record_count in result matches input."""
        results = parse_kapsarc_io_file(FIXTURE_PATH)
        assert results[0].record_count == 9
