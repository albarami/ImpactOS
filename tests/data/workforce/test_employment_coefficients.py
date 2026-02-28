"""Tests for employment coefficients building (D-4 Task 1c)."""

from __future__ import annotations

from pathlib import Path

from src.data.workforce.build_employment_coefficients import (
    build_employment_coefficients,
    load_employment_coefficients,
    save_employment_coefficients,
)
from src.data.workforce.unit_registry import (
    OutputDenomination,
    QualityConfidence,
    SectorGranularity,
)
from src.models.common import ConstraintConfidence

FIXTURE_PATH = Path("tests/fixtures/workforce/sample_employment_coefficients.json")


class TestBuildEmploymentCoefficients:
    """Build from ILO + KAPSARC IO data."""

    def test_builds_all_sections(self) -> None:
        """Without data, builds synthetic for all 20 sections."""
        result = build_employment_coefficients()
        assert len(result.coefficients) == 20

    def test_synthetic_fallback_confidence(self) -> None:
        """Synthetic coefficients have ASSUMED source confidence."""
        result = build_employment_coefficients()
        for c in result.coefficients:
            if "synthetic" in c.source:
                assert c.source_confidence == ConstraintConfidence.ASSUMED
                assert c.quality_confidence == QualityConfidence.LOW

    def test_denominator_is_gross_output(self) -> None:
        """Denominator source is documented (most critical requirement)."""
        result = build_employment_coefficients()
        for c in result.coefficients:
            assert c.denominator_source in (
                "kapsarc_io_x_vector",
                "gdp_converted_via_va_ratio",
                "synthetic",
            )

    def test_all_positive(self) -> None:
        """All jobs_per_unit_output values are positive."""
        result = build_employment_coefficients()
        for c in result.coefficients:
            assert c.jobs_per_unit_output > 0

    def test_reasonable_range(self) -> None:
        """Coefficients in range ~1-100 jobs/M SAR for SAR_MILLIONS denomination."""
        result = build_employment_coefficients()
        for c in result.coefficients:
            if c.output_denomination == OutputDenomination.SAR_MILLIONS:
                assert 0.5 <= c.jobs_per_unit_output <= 100

    def test_granularity_set(self) -> None:
        """All have section-level granularity."""
        result = build_employment_coefficients()
        for c in result.coefficients:
            assert c.granularity == SectorGranularity.SECTION

    def test_year_propagated(self) -> None:
        """Year is set correctly."""
        result = build_employment_coefficients(year=2020)
        assert result.year == 2020


class TestSaveLoadCoefficients:
    """Round-trip serialization."""

    def test_save_and_load(self, tmp_path: Path) -> None:
        result = build_employment_coefficients()
        path = save_employment_coefficients(result, tmp_path)
        assert path.exists()

        loaded = load_employment_coefficients(path)
        assert len(loaded.coefficients) == len(result.coefficients)
        assert loaded.year == result.year

    def test_load_fixture(self) -> None:
        loaded = load_employment_coefficients(FIXTURE_PATH)
        assert len(loaded.coefficients) == 3
        assert loaded.get_coefficient("A") is not None
        assert loaded.get_coefficient("A").jobs_per_unit_output == 25.0  # type: ignore[union-attr]

    def test_provenance_in_output(self, tmp_path: Path) -> None:
        """Saved JSON includes _provenance block (Amendment 4)."""
        import json

        result = build_employment_coefficients()
        path = save_employment_coefficients(result, tmp_path)
        data = json.loads(path.read_text())
        assert "_provenance" in data
        assert "builder" in data["_provenance"]
        assert "gross output" in data["_provenance"]["notes"].lower()
