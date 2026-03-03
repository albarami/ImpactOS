"""Sprint 17 evidence: release-readiness-checklist references RunSeries."""
from pathlib import Path

CHECKLIST = Path("docs/evidence/release-readiness-checklist.md")


def test_sprint17_section_exists() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    assert "Sprint 17" in text


def test_runseries_storage_shape_documented() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    assert "series_kind" in text
    assert "annual" in text
    assert "peak" in text
    assert "delta" in text


def test_reason_codes_documented() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    for code in ("RS_BASELINE_NOT_FOUND", "RS_BASELINE_NO_SERIES",
                 "RS_YEAR_MISMATCH", "RS_BASELINE_METRIC_MISMATCH"):
        assert code in text, f"Missing reason code: {code}"


def test_go_no_go_criteria() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    assert "go / no-go" in text.lower() or "Go / No-Go" in text
