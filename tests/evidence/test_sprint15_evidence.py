"""Tests for Sprint 15 Type II Induced Effects evidence in release-readiness checklist."""

from pathlib import Path

_CHECKLIST = Path("docs/evidence/release-readiness-checklist.md")


class TestSprint15Evidence:
    def test_checklist_file_exists(self) -> None:
        assert _CHECKLIST.exists(), f"{_CHECKLIST} must exist"

    def test_sprint15_section_present(self) -> None:
        content = _CHECKLIST.read_text(encoding="utf-8")
        assert "Sprint 15" in content, "Sprint 15 section required in checklist"

    def test_type_ii_metrics_documented(self) -> None:
        content = _CHECKLIST.read_text(encoding="utf-8")
        assert "type_ii_total_output" in content
        assert "induced_effect" in content
        assert "type_ii_employment" in content

    def test_validation_reason_codes_documented(self) -> None:
        content = _CHECKLIST.read_text(encoding="utf-8")
        assert "TYPE_II_MISSING_COMPENSATION" in content
        assert "TYPE_II_MISSING_HOUSEHOLD_SHARES" in content
        assert "TYPE_II_DIMENSION_MISMATCH" in content
        assert "TYPE_II_NEGATIVE_VALUES" in content
        assert "TYPE_II_INVALID_SHARE_SUM" in content
        assert "TYPE_II_NONFINITE_WAGE_COEFFICIENTS" in content

    def test_confidence_labels_present(self) -> None:
        content = _CHECKLIST.read_text(encoding="utf-8")
        assert "MEASURED" in content
        assert "ESTIMATED" in content

    def test_go_nogo_criteria_includes_type_ii(self) -> None:
        content = _CHECKLIST.read_text(encoding="utf-8")
        assert "Type II induced = Type II total - Type I total" in content
        assert "Non-dev fail-closed" in content
