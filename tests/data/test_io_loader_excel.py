"""Tests for load_from_excel() — delegation and extension routing."""

from pathlib import Path

import pytest

from src.data.io_loader import load_from_excel
from src.data.sg_model_adapter import SGImportError

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
XLSX_FIXTURE = FIXTURE_DIR / "sg_3sector_model.xlsx"

pytestmark = pytest.mark.skipif(
    not XLSX_FIXTURE.exists(),
    reason="SG fixture not generated",
)


class TestLoadFromExcelRouting:
    def test_xlsx_returns_io_model_data(self) -> None:
        model = load_from_excel(XLSX_FIXTURE)
        assert model.Z.shape == (3, 3)
        assert len(model.sector_codes) == 3

    def test_unsupported_extension_raises(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "model.csv"
        bad_file.write_text("dummy")
        with pytest.raises(SGImportError) as exc_info:
            load_from_excel(bad_file)
        assert exc_info.value.reason_code == "SG_UNSUPPORTED_FORMAT"

    def test_nonexistent_xlsx_raises(self) -> None:
        with pytest.raises(SGImportError) as exc_info:
            load_from_excel(Path("/nonexistent/model.xlsx"))
        assert exc_info.value.reason_code == "SG_FILE_UNREADABLE"

    def test_xlsb_extension_accepted(self) -> None:
        """Even if file doesn't exist, .xlsb is a valid extension (not UNSUPPORTED_FORMAT)."""
        with pytest.raises(SGImportError) as exc_info:
            load_from_excel(Path("/nonexistent/model.xlsb"))
        assert exc_info.value.reason_code == "SG_FILE_UNREADABLE"

    def test_config_param_accepted(self) -> None:
        """Config parameter is accepted (reserved for future GASTAT)."""
        model = load_from_excel(XLSX_FIXTURE, config=None)
        assert model.Z.shape == (3, 3)

    def test_txt_extension_raises(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "model.txt"
        bad_file.write_text("dummy")
        with pytest.raises(SGImportError) as exc_info:
            load_from_excel(bad_file)
        assert exc_info.value.reason_code == "SG_UNSUPPORTED_FORMAT"
