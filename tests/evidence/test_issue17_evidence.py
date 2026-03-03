"""Tests for Issue #17 closure evidence in release-readiness checklist."""

from pathlib import Path

_CHECKLIST = Path("docs/evidence/release-readiness-checklist.md")


class TestIssue17Evidence:
    def test_checklist_file_exists(self) -> None:
        assert _CHECKLIST.exists(), f"{_CHECKLIST} must exist"

    def test_issue17_section_present(self) -> None:
        content = _CHECKLIST.read_text(encoding="utf-8")
        assert "Issue #17" in content, "Issue #17 section required in checklist"

    def test_fail_closed_agents_listed(self) -> None:
        content = _CHECKLIST.read_text(encoding="utf-8")
        assert "SPLIT_NO_LLM_BACKING" in content
        assert "ASSUMPTION_NO_LLM_BACKING" in content
        assert "DEPTH_STEP_NO_LLM_BACKING" in content

    def test_go_nogo_criteria_includes_issue17(self) -> None:
        content = _CHECKLIST.read_text(encoding="utf-8")
        assert "No deterministic fallback success in non-dev" in content
