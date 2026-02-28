"""Tests for GOSI employment parser (D-4 Task 1d)."""

from __future__ import annotations

from pathlib import Path

from src.data.parsers.gosi_employment_parser import (
    build_synthetic_gosi_data,
    save_gosi_data,
)
from src.models.common import ConstraintConfidence


class TestSyntheticGOSI:
    """Synthetic GOSI data calibrated to DataSaudi."""

    def test_all_sections_covered(self) -> None:
        data = build_synthetic_gosi_data()
        assert len(data.entries) == 20

    def test_total_calibration(self) -> None:
        """Total ~9.07M employees (DataSaudi 2022 calibration)."""
        data = build_synthetic_gosi_data()
        assert 8_000_000 < data.total_employees < 11_000_000

    def test_construction_largest(self) -> None:
        """Construction should be the largest sector (~2.46M)."""
        data = build_synthetic_gosi_data()
        f_entry = data.get_entry("F")
        assert f_entry is not None
        assert f_entry.total_employees == 2_460_000

    def test_saudi_share_range(self) -> None:
        """All Saudi shares between 0 and 1."""
        data = build_synthetic_gosi_data()
        for e in data.entries:
            assert 0.0 <= e.saudi_share <= 1.0

    def test_saudi_non_saudi_add_up(self) -> None:
        """saudi + non_saudi = total for each entry."""
        data = build_synthetic_gosi_data()
        for e in data.entries:
            assert e.saudi_employees + e.non_saudi_employees == e.total_employees

    def test_synthetic_confidence(self) -> None:
        """All synthetic entries have ASSUMED confidence."""
        data = build_synthetic_gosi_data()
        for e in data.entries:
            assert e.source_confidence == ConstraintConfidence.ASSUMED

    def test_save(self, tmp_path: Path) -> None:
        data = build_synthetic_gosi_data()
        path = save_gosi_data(data, tmp_path)
        assert path.exists()
