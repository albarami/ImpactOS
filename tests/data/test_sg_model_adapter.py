"""Tests for SG model adapter — layout detection and IO model extraction.

Sprint 18: SG workbook → IOModelData extraction.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.data.sg_model_adapter import (
    SGImportError,
    SGSheetLayout,
    detect_sg_layout,
    extract_io_model,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
FIXTURE_XLSX = FIXTURE_DIR / "sg_3sector_model.xlsx"

# Expected data from fixture generator
EXPECTED_Z = np.array(
    [[150.0, 500.0, 100.0], [200.0, 100.0, 300.0], [50.0, 200.0, 50.0]],
    dtype=np.float64,
)
EXPECTED_X = np.array([1000.0, 2000.0, 1500.0], dtype=np.float64)
EXPECTED_CODES = ["01", "02", "03"]
EXPECTED_NAMES = {"01": "Agriculture", "02": "Manufacturing", "03": "Services"}


class TestDetectSGLayout:
    """Tests for detect_sg_layout()."""

    def test_detect_layout_xlsx(self) -> None:
        """Detects layout from fixture; sector_count=3, z_sheet='IO_MODEL'."""
        layout = detect_sg_layout(FIXTURE_XLSX)

        assert isinstance(layout, SGSheetLayout)
        assert layout.z_sheet == "IO_MODEL"
        assert layout.sector_count == 3
        assert layout.sector_codes_row == 3  # row 3 has CODE header
        assert layout.code_col == 0
        assert layout.name_col == 1
        assert layout.sector_col == 2  # first sector data column
        assert layout.data_start_row == 4  # first data row after header
        assert layout.base_year == 2024
        assert layout.final_demand_sheet == "FINAL_DEMAND"
        assert layout.imports_sheet == "IMPORTS"
        assert layout.value_added_sheet == "VALUE_ADDED"

    def test_detect_layout_missing_sheet_raises(self, tmp_path: Path) -> None:
        """Workbook without required sheets raises SG_LAYOUT_DETECTION_FAILED."""
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "RandomSheet"
        ws.append(["nothing", "useful", "here"])
        bad_path = tmp_path / "bad_workbook.xlsx"
        wb.save(bad_path)
        wb.close()

        with pytest.raises(SGImportError, match="SG_LAYOUT_DETECTION_FAILED"):
            detect_sg_layout(bad_path)


class TestExtractIOModel:
    """Tests for extract_io_model()."""

    def test_extract_returns_io_model_data(self) -> None:
        """Returns IOModelData with correct shape."""
        from src.data.io_loader import IOModelData

        result = extract_io_model(FIXTURE_XLSX)
        assert isinstance(result, IOModelData)
        assert result.Z.shape == (3, 3)
        assert result.x.shape == (3,)
        assert len(result.sector_codes) == 3

    def test_extract_z_matrix_values(self) -> None:
        """Z matches expected values."""
        result = extract_io_model(FIXTURE_XLSX)
        np.testing.assert_array_almost_equal(result.Z, EXPECTED_Z)

    def test_extract_x_vector_values(self) -> None:
        """x matches expected values."""
        result = extract_io_model(FIXTURE_XLSX)
        np.testing.assert_array_almost_equal(result.x, EXPECTED_X)

    def test_extract_sector_names(self) -> None:
        """Sector names dict populated correctly."""
        result = extract_io_model(FIXTURE_XLSX)
        assert result.sector_codes == EXPECTED_CODES
        assert result.sector_names == EXPECTED_NAMES

    def test_extract_extended_artifacts_when_present(self) -> None:
        """Extended artifacts: final_demand_F, imports, compensation, gos, taxes."""
        result = extract_io_model(FIXTURE_XLSX)

        # final_demand_F shape = (3, 2) -- 3 sectors, 2 demand categories
        assert result.final_demand_F is not None
        assert result.final_demand_F.shape == (3, 2)
        np.testing.assert_array_almost_equal(
            result.final_demand_F,
            np.array([[100.0, 50.0], [200.0, 150.0], [300.0, 100.0]]),
        )

        # imports_vector
        assert result.imports_vector is not None
        np.testing.assert_array_almost_equal(
            result.imports_vector,
            np.array([120.0, 350.0, 80.0]),
        )

        # compensation_of_employees
        assert result.compensation_of_employees is not None
        np.testing.assert_array_almost_equal(
            result.compensation_of_employees,
            np.array([200.0, 400.0, 500.0]),
        )

        # gross_operating_surplus
        assert result.gross_operating_surplus is not None
        np.testing.assert_array_almost_equal(
            result.gross_operating_surplus,
            np.array([150.0, 300.0, 350.0]),
        )

        # taxes_less_subsidies
        assert result.taxes_less_subsidies is not None
        np.testing.assert_array_almost_equal(
            result.taxes_less_subsidies,
            np.array([50.0, 100.0, 70.0]),
        )

    def test_extract_provenance_metadata(self) -> None:
        """metadata['sg_provenance'] has correct fields."""
        result = extract_io_model(FIXTURE_XLSX)
        prov = result.metadata["sg_provenance"]

        assert isinstance(prov, dict)
        assert prov["import_mode"] == "sg_workbook"
        assert prov["source_filename"] == FIXTURE_XLSX.name
        assert prov["workbook_sha256"].startswith("sha256:")
        assert len(prov["workbook_sha256"]) == len("sha256:") + 64
        assert "imported_at" in prov

    def test_extract_workbook_hash_is_deterministic(self) -> None:
        """Same file produces same hash."""
        r1 = extract_io_model(FIXTURE_XLSX)
        r2 = extract_io_model(FIXTURE_XLSX)

        h1 = r1.metadata["sg_provenance"]["workbook_sha256"]
        h2 = r2.metadata["sg_provenance"]["workbook_sha256"]
        assert h1 == h2

    def test_extract_corrupt_matrix_raises(self, tmp_path: Path) -> None:
        """Bad workbook raises SG_PARSE_MATRIX_FAILED or SG_LAYOUT_DETECTION_FAILED."""
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "IO_MODEL"
        ws.append(["CODE", "SECTOR", "01", "02", "03"])
        # Data rows with non-numeric values
        ws.append(["01", "Agriculture", "bad", "data", "here"])
        ws.append(["02", "Manufacturing", None, None, None])
        ws.append(["03", "Services", "x", "y", "z"])
        ws.append([])
        ws.append(["TOTAL_OUTPUT", "Total Output", "not", "a", "number"])
        corrupt_path = tmp_path / "corrupt.xlsx"
        wb.save(corrupt_path)
        wb.close()

        with pytest.raises(SGImportError) as exc_info:
            extract_io_model(corrupt_path)
        assert exc_info.value.reason_code in (
            "SG_PARSE_MATRIX_FAILED",
            "SG_LAYOUT_DETECTION_FAILED",
        )

    def test_extract_file_not_found_raises(self, tmp_path: Path) -> None:
        """Nonexistent file raises SG_FILE_UNREADABLE."""
        bad_path = tmp_path / "nonexistent.xlsx"

        with pytest.raises(SGImportError, match="SG_FILE_UNREADABLE"):
            extract_io_model(bad_path)

    def test_xlsb_file_not_found_raises(self, tmp_path: Path) -> None:
        """Nonexistent .xlsb file raises SG_FILE_UNREADABLE (not SG_UNSUPPORTED_FORMAT)."""
        bad_path = tmp_path / "nonexistent.xlsb"

        with pytest.raises(SGImportError, match="SG_FILE_UNREADABLE"):
            extract_io_model(bad_path)
