"""Tests for ConcordanceService (D-2).

Validates:
    src/data/concordance.py — bidirectional section/division mapping + aggregation
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from src.data.concordance import ConcordanceService

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "curated"
CONCORDANCE_PATH = DATA_DIR / "concordance_section_division.json"
WEIGHTS_PATH = DATA_DIR / "division_output_weights_sg_2018.json"

SKIP_NO_DATA = pytest.mark.skipif(
    not CONCORDANCE_PATH.exists(),
    reason="Concordance JSON not generated",
)


# ===================================================================
# TestConcordanceService — basic mapping
# ===================================================================


@SKIP_NO_DATA
class TestConcordanceService:
    """Basic division/section mapping tests."""

    def test_division_to_section_basic(self) -> None:
        """'06' -> 'B' (oil extraction is Mining)."""
        svc = ConcordanceService(str(CONCORDANCE_PATH))
        assert svc.division_to_section("06") == "B"

    def test_division_to_section_all_mapped(self) -> None:
        """Every active division maps to a section."""
        svc = ConcordanceService(str(CONCORDANCE_PATH))
        with open(CONCORDANCE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        all_divs = set()
        for m in data["mappings"]:
            all_divs.update(m["division_codes"])
        for div_code in all_divs:
            result = svc.division_to_section(div_code)
            assert result in "ABCDEFGHIJKLMNOPQRST"

    def test_section_to_divisions_mining(self) -> None:
        """'B' -> ['05','06','07','08','09']."""
        svc = ConcordanceService(str(CONCORDANCE_PATH))
        divs = svc.section_to_divisions("B")
        assert divs == ["05", "06", "07", "08", "09"]

    def test_section_to_divisions_complete(self) -> None:
        """Every section returns at least 1 division."""
        svc = ConcordanceService(str(CONCORDANCE_PATH))
        for section in "ABCDEFGHIJKLMNOPQRST":
            divs = svc.section_to_divisions(section)
            assert len(divs) >= 1, f"Section {section} has no divisions"

    def test_unknown_division_raises(self) -> None:
        """Inactive code '04' or unknown '99' -> KeyError."""
        svc = ConcordanceService(str(CONCORDANCE_PATH))
        with pytest.raises(KeyError):
            svc.division_to_section("04")
        with pytest.raises(KeyError):
            svc.division_to_section("99")

    def test_unknown_section_raises(self) -> None:
        """'Z' -> KeyError."""
        svc = ConcordanceService(str(CONCORDANCE_PATH))
        with pytest.raises(KeyError):
            svc.section_to_divisions("Z")

    def test_manufacturing_has_23_divisions(self) -> None:
        """Section C (Manufacturing) has exactly 23 active divisions."""
        svc = ConcordanceService(str(CONCORDANCE_PATH))
        divs = svc.section_to_divisions("C")
        assert len(divs) == 23

    def test_total_active_divisions_is_84(self) -> None:
        """Union of all section divisions == 84."""
        svc = ConcordanceService(str(CONCORDANCE_PATH))
        all_divs = set()
        for section in "ABCDEFGHIJKLMNOPQRST":
            all_divs.update(svc.section_to_divisions(section))
        assert len(all_divs) == 84


# ===================================================================
# TestAggregation — vector aggregation/disaggregation
# ===================================================================


@SKIP_NO_DATA
class TestAggregation:
    """Aggregation and disaggregation tests."""

    def test_aggregate_sum_basic(self) -> None:
        """Sum divisions within a section."""
        svc = ConcordanceService(str(CONCORDANCE_PATH))
        # Give mining divisions some values
        div_values = {"05": 100.0, "06": 5000.0, "07": 50.0, "08": 200.0, "09": 300.0}
        result = svc.aggregate_division_vector(div_values, method="sum")
        assert abs(result["B"] - 5650.0) < 1e-6

    def test_aggregate_all_divisions(self) -> None:
        """Full 84-division -> 20-section aggregation."""
        svc = ConcordanceService(str(CONCORDANCE_PATH))
        # Load all active division codes
        with open(CONCORDANCE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        all_divs: dict[str, float] = {}
        for m in data["mappings"]:
            for code in m["division_codes"]:
                all_divs[code] = 1.0  # uniform
        result = svc.aggregate_division_vector(all_divs, method="sum")
        assert len(result) == 20
        # All sections should have value >= 1.0
        for section, value in result.items():
            assert value >= 1.0, f"Section {section} has value {value}"

    def test_aggregate_preserves_total(self) -> None:
        """sum(input) == sum(output) for method='sum'."""
        svc = ConcordanceService(str(CONCORDANCE_PATH))
        with open(CONCORDANCE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        div_values: dict[str, float] = {}
        for m in data["mappings"]:
            for i, code in enumerate(m["division_codes"]):
                div_values[code] = float(i + 1) * 100.0
        result = svc.aggregate_division_vector(div_values, method="sum")
        input_total = sum(div_values.values())
        output_total = sum(result.values())
        assert abs(input_total - output_total) < 1e-6

    def test_disaggregate_proportional(self) -> None:
        """Uses weights for proportional split."""
        svc = ConcordanceService(str(CONCORDANCE_PATH), str(WEIGHTS_PATH))
        section_values = {"B": 1000.0}
        result = svc.disaggregate_section_vector(section_values)
        # Should produce values for all B divisions (05,06,07,08,09)
        b_divs = {"05", "06", "07", "08", "09"}
        result_divs = {k for k, v in result.items() if v > 0}
        assert result_divs == b_divs
        # Sum should equal input
        assert abs(sum(result.values()) - 1000.0) < 1e-6
        # Division 06 (oil) should get the largest share
        assert result["06"] > result["05"]
        assert result["06"] > result["07"]

    def test_roundtrip_section_preserving(self) -> None:
        """aggregate(disaggregate(section_v)) ~ section_v."""
        svc = ConcordanceService(str(CONCORDANCE_PATH), str(WEIGHTS_PATH))
        section_values = {"A": 100.0, "B": 500.0, "C": 300.0, "F": 200.0}
        disagg = svc.disaggregate_section_vector(section_values)
        reagg = svc.aggregate_division_vector(disagg, method="sum")
        for section, original in section_values.items():
            assert abs(reagg.get(section, 0.0) - original) < 1e-6, (
                f"Section {section}: {reagg.get(section, 0.0)} != {original}"
            )

    def test_disaggregate_without_weights_warns(self) -> None:
        """Equal split with warning when no weights loaded."""
        svc = ConcordanceService(str(CONCORDANCE_PATH))  # no weights
        section_values = {"B": 1000.0}
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = svc.disaggregate_section_vector(section_values)
            # Should have issued a warning about equal distribution
            assert any("equal" in str(warning.message).lower() for warning in w)
        # 5 B divisions, each gets 200.0
        assert abs(result["05"] - 200.0) < 1e-6
        assert abs(result["06"] - 200.0) < 1e-6
