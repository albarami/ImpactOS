"""Evidence checklist tests for Sprint 14 Saudi data foundation closeout."""

from pathlib import Path


CHECKLIST_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "evidence"
    / "release-readiness-checklist.md"
)


def test_mvp14_checklist_section_present() -> None:
    text = CHECKLIST_PATH.read_text(encoding="utf-8")
    assert "MVP-14 Saudi Data Foundation Evidence" in text


def test_mvp14_checklist_includes_required_artifact_entries() -> None:
    text = CHECKLIST_PATH.read_text(encoding="utf-8")
    required = [
        "final_demand_F",
        "imports_vector",
        "compensation_of_employees",
        "gross_operating_surplus",
        "taxes_less_subsidies",
        "household_consumption_shares",
        "deflator_series",
    ]
    for key in required:
        assert key in text
