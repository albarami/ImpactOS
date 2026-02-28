"""Tests for ISIC Rev.4 division-level taxonomy (D-2).

Validates:
    data/curated/sector_taxonomy_isic4_divisions.json  (97-entry division file)
    data/curated/sector_taxonomy_isic4.json            (updated D-1 section file)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "curated"
DIVISION_TAXONOMY_PATH = DATA_DIR / "sector_taxonomy_isic4_divisions.json"
SECTION_TAXONOMY_PATH = DATA_DIR / "sector_taxonomy_isic4.json"

# The 13 specific inactive codes verified from SG workbook
EXPECTED_INACTIVE = frozenset([
    "04", "12", "34", "40", "44", "48", "54", "57",
    "67", "76", "83", "89", "92",
])

EXPECTED_SECTIONS = frozenset("ABCDEFGHIJKLMNOPQRST")


def _load_division_taxonomy() -> dict:
    with open(DIVISION_TAXONOMY_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_section_taxonomy() -> dict:
    with open(SECTION_TAXONOMY_PATH, encoding="utf-8") as f:
        return json.load(f)


# ===================================================================
# TestDivisionTaxonomy
# ===================================================================


@pytest.mark.skipif(
    not DIVISION_TAXONOMY_PATH.exists(),
    reason="Division taxonomy JSON not generated",
)
class TestDivisionTaxonomy:
    """Validates division-level taxonomy file."""

    def test_code_space_covers_01_to_97(self) -> None:
        """Full range 01-97 present in file."""
        data = _load_division_taxonomy()
        codes = {s["division_code"] for s in data["sectors"]}
        expected = {f"{i:02d}" for i in range(1, 98)}
        assert codes == expected, f"Missing: {expected - codes}, Extra: {codes - expected}"

    def test_active_division_count_is_84(self) -> None:
        """Exactly 84 divisions have is_active=true."""
        data = _load_division_taxonomy()
        active = [s for s in data["sectors"] if s["is_active"]]
        assert len(active) == 84

    def test_inactive_codes_match_sg_gaps(self) -> None:
        """The 13 specific codes are inactive."""
        data = _load_division_taxonomy()
        inactive = {s["division_code"] for s in data["sectors"] if not s["is_active"]}
        assert inactive == EXPECTED_INACTIVE

    def test_every_active_division_has_section(self) -> None:
        """All active divisions map to a valid ISIC section."""
        data = _load_division_taxonomy()
        for s in data["sectors"]:
            if s["is_active"]:
                assert s["section_code"] in EXPECTED_SECTIONS, (
                    f"Division {s['division_code']} has invalid "
                    f"section {s['section_code']}"
                )

    def test_section_coverage_complete(self) -> None:
        """All 20 sections have at least 1 active division."""
        data = _load_division_taxonomy()
        sections_with_active = {
            s["section_code"]
            for s in data["sectors"]
            if s["is_active"]
        }
        assert sections_with_active == EXPECTED_SECTIONS

    def test_arabic_names_present_or_null(self) -> None:
        """Active divisions have AR name; reserved codes have null."""
        data = _load_division_taxonomy()
        for s in data["sectors"]:
            if s["is_active"]:
                assert s["sector_name_ar"] is not None, (
                    f"Active division {s['division_code']} missing Arabic name"
                )
                assert len(s["sector_name_ar"]) > 0
            elif s["sector_name_en"].startswith("(Reserved"):
                assert s["sector_name_ar"] is None, (
                    f"Reserved code {s['division_code']} should have null AR name"
                )

    def test_no_duplicate_codes(self) -> None:
        """No repeated division codes."""
        data = _load_division_taxonomy()
        codes = [s["division_code"] for s in data["sectors"]]
        assert len(codes) == len(set(codes))

    def test_english_names_not_empty(self) -> None:
        """All active divisions have non-empty English names."""
        data = _load_division_taxonomy()
        for s in data["sectors"]:
            if s["is_active"]:
                assert s["sector_name_en"], (
                    f"Division {s['division_code']} has empty EN name"
                )
                # Active names should NOT be reserved placeholders
                assert not s["sector_name_en"].startswith("(Reserved")

    def test_section_taxonomy_updated_with_divisions(self) -> None:
        """D-1 section file now has division references."""
        data = _load_section_taxonomy()
        for sector in data["sectors"]:
            assert "divisions" in sector, (
                f"Section {sector['sector_code']} missing divisions field"
            )
            divs = sector["divisions"]
            assert isinstance(divs, list)
            assert len(divs) >= 1, (
                f"Section {sector['sector_code']} has no divisions"
            )
            # All division codes should be 2-digit strings
            for d in divs:
                assert len(d) == 2 and d.isdigit(), (
                    f"Invalid division code format: {d}"
                )

    def test_metadata_fields_present(self) -> None:
        """Top-level metadata is correct."""
        data = _load_division_taxonomy()
        assert data["classification"] == "ISIC_REV4_DIVISION"
        assert data["code_space"] == "01-97"
        assert data["active_count"] == 84
        assert data["total_codes"] == 97
        assert isinstance(data["inactive_codes"], list)
        assert len(data["inactive_codes"]) == 13

    def test_present_in_sg_template_matches_active(self) -> None:
        """present_in_sg_template == is_active for all entries."""
        data = _load_division_taxonomy()
        for s in data["sectors"]:
            assert s["present_in_sg_template"] == s["is_active"], (
                f"Division {s['division_code']}: active={s['is_active']} "
                f"but sg_template={s['present_in_sg_template']}"
            )

    def test_division_code_ordering(self) -> None:
        """Division codes are in ascending numerical order."""
        data = _load_division_taxonomy()
        codes = [s["division_code"] for s in data["sectors"]]
        assert codes == sorted(codes, key=int)
