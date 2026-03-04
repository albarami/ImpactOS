"""Tests for workshop slider → shocks transform — Sprint 22."""
# ruff: noqa: S101, ANN201

import pytest

from src.engine.workshop_transform import (
    SliderInput,
    WorkshopDuplicateSectorError,
    WorkshopInvalidConfigError,
    WorkshopUnknownSectorError,
    transform_sliders,
    validate_base_shocks,
    validate_sliders,
    workshop_config_hash,
)

SECTOR_CODES = ["A", "B", "C"]

BASE_SHOCKS = {
    "2025": [100_000.0, 200_000.0, 50_000.0],
    "2026": [120_000.0, 250_000.0, 60_000.0],
}


class TestValidateSliders:
    def test_valid_sliders(self):
        sliders = [SliderInput(sector_code="A", pct_delta=10.0)]
        validate_sliders(sliders, SECTOR_CODES)

    def test_empty_sliders_valid(self):
        validate_sliders([], SECTOR_CODES)

    def test_duplicate_sector_raises(self):
        sliders = [
            SliderInput(sector_code="A", pct_delta=10.0),
            SliderInput(sector_code="A", pct_delta=20.0),
        ]
        with pytest.raises(WorkshopDuplicateSectorError) as exc_info:
            validate_sliders(sliders, SECTOR_CODES)
        assert exc_info.value.reason_code == "WORKSHOP_DUPLICATE_SECTOR"
        assert "'A'" in exc_info.value.message

    def test_unknown_sector_raises(self):
        sliders = [SliderInput(sector_code="Z", pct_delta=5.0)]
        with pytest.raises(WorkshopUnknownSectorError) as exc_info:
            validate_sliders(sliders, SECTOR_CODES)
        assert exc_info.value.reason_code == "WORKSHOP_UNKNOWN_SECTOR"
        assert "'Z'" in exc_info.value.message

    def test_duplicate_checked_before_unknown(self):
        sliders = [
            SliderInput(sector_code="Z", pct_delta=5.0),
            SliderInput(sector_code="Z", pct_delta=10.0),
        ]
        with pytest.raises(WorkshopDuplicateSectorError):
            validate_sliders(sliders, SECTOR_CODES)


class TestValidateBaseShocks:
    def test_valid_base_shocks(self):
        validate_base_shocks(BASE_SHOCKS, SECTOR_CODES)

    def test_empty_base_shocks_raises(self):
        with pytest.raises(WorkshopInvalidConfigError) as exc_info:
            validate_base_shocks({}, SECTOR_CODES)
        assert "must not be empty" in exc_info.value.message

    def test_wrong_length_raises(self):
        bad = {"2025": [100.0, 200.0]}
        with pytest.raises(WorkshopInvalidConfigError) as exc_info:
            validate_base_shocks(bad, SECTOR_CODES)
        assert "2 values" in exc_info.value.message
        assert "expected 3" in exc_info.value.message


class TestTransformSliders:
    def test_no_sliders_returns_base_unchanged(self):
        result = transform_sliders(BASE_SHOCKS, [], SECTOR_CODES)
        assert result == BASE_SHOCKS

    def test_single_sector_adjustment(self):
        sliders = [SliderInput(sector_code="A", pct_delta=10.0)]
        result = transform_sliders(BASE_SHOCKS, sliders, SECTOR_CODES)
        assert result["2025"][0] == pytest.approx(110_000.0)
        assert result["2025"][1] == pytest.approx(200_000.0)
        assert result["2025"][2] == pytest.approx(50_000.0)
        assert result["2026"][0] == pytest.approx(132_000.0)
        assert result["2026"][1] == pytest.approx(250_000.0)
        assert result["2026"][2] == pytest.approx(60_000.0)

    def test_multiple_sector_adjustments(self):
        sliders = [
            SliderInput(sector_code="A", pct_delta=10.0),
            SliderInput(sector_code="C", pct_delta=-20.0),
        ]
        result = transform_sliders(BASE_SHOCKS, sliders, SECTOR_CODES)
        assert result["2025"][0] == pytest.approx(110_000.0)
        assert result["2025"][1] == pytest.approx(200_000.0)
        assert result["2025"][2] == pytest.approx(40_000.0)

    def test_zero_percent_delta_no_change(self):
        sliders = [SliderInput(sector_code="B", pct_delta=0.0)]
        result = transform_sliders(BASE_SHOCKS, sliders, SECTOR_CODES)
        assert result == BASE_SHOCKS

    def test_negative_percent_delta(self):
        sliders = [SliderInput(sector_code="A", pct_delta=-50.0)]
        result = transform_sliders(BASE_SHOCKS, sliders, SECTOR_CODES)
        assert result["2025"][0] == pytest.approx(50_000.0)

    def test_hundred_percent_increase(self):
        sliders = [SliderInput(sector_code="B", pct_delta=100.0)]
        result = transform_sliders(BASE_SHOCKS, sliders, SECTOR_CODES)
        assert result["2025"][1] == pytest.approx(400_000.0)

    def test_all_years_transformed(self):
        sliders = [SliderInput(sector_code="A", pct_delta=15.0)]
        result = transform_sliders(BASE_SHOCKS, sliders, SECTOR_CODES)
        assert set(result.keys()) == {"2025", "2026"}

    def test_deterministic_repeated_calls(self):
        sliders = [SliderInput(sector_code="A", pct_delta=10.0)]
        r1 = transform_sliders(BASE_SHOCKS, sliders, SECTOR_CODES)
        r2 = transform_sliders(BASE_SHOCKS, sliders, SECTOR_CODES)
        assert r1 == r2


class TestWorkshopConfigHash:
    def test_hash_format(self):
        h = workshop_config_hash("run-1", BASE_SHOCKS, [])
        assert h.startswith("sha256:")
        assert len(h) == 7 + 64

    def test_same_input_same_hash(self):
        sliders = [SliderInput(sector_code="A", pct_delta=10.0)]
        h1 = workshop_config_hash("run-1", BASE_SHOCKS, sliders)
        h2 = workshop_config_hash("run-1", BASE_SHOCKS, sliders)
        assert h1 == h2

    def test_different_sliders_different_hash(self):
        s1 = [SliderInput(sector_code="A", pct_delta=10.0)]
        s2 = [SliderInput(sector_code="A", pct_delta=20.0)]
        h1 = workshop_config_hash("run-1", BASE_SHOCKS, s1)
        h2 = workshop_config_hash("run-1", BASE_SHOCKS, s2)
        assert h1 != h2

    def test_different_baseline_different_hash(self):
        h1 = workshop_config_hash("run-1", BASE_SHOCKS, [])
        h2 = workshop_config_hash("run-2", BASE_SHOCKS, [])
        assert h1 != h2

    def test_slider_order_independent(self):
        s1 = [
            SliderInput(sector_code="A", pct_delta=10.0),
            SliderInput(sector_code="B", pct_delta=20.0),
        ]
        s2 = [
            SliderInput(sector_code="B", pct_delta=20.0),
            SliderInput(sector_code="A", pct_delta=10.0),
        ]
        h1 = workshop_config_hash("run-1", BASE_SHOCKS, s1)
        h2 = workshop_config_hash("run-1", BASE_SHOCKS, s2)
        assert h1 == h2

    def test_year_order_independent(self):
        shocks_ordered = {"2025": [100.0], "2026": [200.0]}
        shocks_reversed = {"2026": [200.0], "2025": [100.0]}
        h1 = workshop_config_hash("run-1", shocks_ordered, [])
        h2 = workshop_config_hash("run-1", shocks_reversed, [])
        assert h1 == h2
