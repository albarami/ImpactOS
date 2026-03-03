"""Tests for Sprint 16 closure evidence in release-readiness checklist."""

from pathlib import Path

_CHECKLIST = Path("docs/evidence/release-readiness-checklist.md")


class TestSprint16Evidence:
    def test_checklist_file_exists(self) -> None:
        assert _CHECKLIST.exists()

    def test_sprint16_section_present(self) -> None:
        content = _CHECKLIST.read_text(encoding="utf-8")
        assert "Sprint 16" in content

    def test_value_measures_listed(self) -> None:
        content = _CHECKLIST.read_text(encoding="utf-8")
        assert "gdp_basic_price" in content
        assert "balance_of_trade" in content
        assert "government_non_oil_revenue" in content

    def test_validation_reason_codes_listed(self) -> None:
        content = _CHECKLIST.read_text(encoding="utf-8")
        assert "VM_MISSING_GOS" in content
        assert "VM_MISSING_FINAL_DEMAND" in content
        assert "VM_MISSING_DEFLATOR" in content

    def test_go_nogo_criteria(self) -> None:
        content = _CHECKLIST.read_text(encoding="utf-8")
        assert "value measures" in content.lower()
