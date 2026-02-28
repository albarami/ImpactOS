"""Tests for IO model loader (D-1).

Covers:
  - JSON loading (valid, malformed, missing fields)
  - Validation engine (spectral radius, non-negativity, VA, multipliers)
  - 20-sector synthetic model properties
  - Satellite coefficient loading and consistency
  - Model registration integration (ModelStore.register)
  - End-to-end seeded run (Amendment 4)
  - Taxonomy file (Amendment 1)
  - Seed idempotency
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.data.io_loader import (
    IOModelData,
    SatelliteData,
    load_from_excel,
    load_from_json,
    load_satellites_from_json,
    validate_model,
)
from src.engine.model_store import ModelStore

# ---------------------------------------------------------------------------
# Paths to curated data files
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "curated"
IO_MODEL_PATH = DATA_DIR / "saudi_io_synthetic_v1.json"
SATELLITES_PATH = DATA_DIR / "saudi_satellites_synthetic_v1.json"
TAXONOMY_PATH = DATA_DIR / "sector_taxonomy_isic4.json"

ISIC_CODES = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_minimal_model_json(tmp_path: Path) -> Path:
    """Write a minimal 2-sector model JSON for unit tests."""
    data = {
        "model_id": "test-2sector",
        "base_year": 2023,
        "source": "unit-test",
        "sector_codes": ["S1", "S2"],
        "sector_names": {"S1": "Sector 1", "S2": "Sector 2"},
        "Z": [[150.0, 500.0], [200.0, 100.0]],
        "x": [1000.0, 2000.0],
    }
    path = tmp_path / "test_model.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _write_minimal_satellites_json(tmp_path: Path) -> Path:
    """Write minimal satellite coefficients JSON."""
    data = {
        "model_id": "test-satellites",
        "base_year": 2023,
        "sector_codes": ["S1", "S2"],
        "employment": {
            "jobs_per_sar_million": [10.0, 5.0],
            "confidence": ["medium", "high"],
        },
        "import_ratios": {
            "values": [0.30, 0.20],
            "confidence": ["medium", "medium"],
        },
        "va_ratios": {
            "values": [0.40, 0.55],
            "confidence": ["high", "high"],
        },
    }
    path = tmp_path / "test_satellites.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ===================================================================
# 1. TestLoadFromJson
# ===================================================================


class TestLoadFromJson:
    """Load curated IO model from JSON file."""

    def test_loads_valid_json(self, tmp_path: Path) -> None:
        """Minimal valid JSON loads as IOModelData."""
        path = _write_minimal_model_json(tmp_path)
        model = load_from_json(path)
        assert isinstance(model, IOModelData)
        assert model.Z.shape == (2, 2)
        assert len(model.x) == 2
        assert model.sector_codes == ["S1", "S2"]
        assert model.base_year == 2023

    def test_missing_z_matrix_raises(self, tmp_path: Path) -> None:
        """JSON without Z field raises ValueError."""
        data = {"x": [100.0], "sector_codes": ["S1"]}
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="Missing.*Z"):
            load_from_json(path)

    def test_missing_x_vector_raises(self, tmp_path: Path) -> None:
        """JSON without x field raises ValueError."""
        data = {"Z": [[10.0]], "sector_codes": ["S1"]}
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="Missing.*x"):
            load_from_json(path)

    def test_mismatched_dimensions_raises(self, tmp_path: Path) -> None:
        """Z rows != x length raises ValueError."""
        data = {
            "Z": [[10.0, 5.0], [5.0, 10.0]],
            "x": [100.0, 200.0, 300.0],
            "sector_codes": ["S1", "S2", "S3"],
        }
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="[Dd]imension"):
            load_from_json(path)

    def test_metadata_preserved(self, tmp_path: Path) -> None:
        """Metadata fields accessible on IOModelData."""
        path = _write_minimal_model_json(tmp_path)
        model = load_from_json(path)
        assert model.source == "unit-test"
        assert "model_id" in model.metadata


# ===================================================================
# 2. TestValidateModel
# ===================================================================


class TestValidateModel:
    """Comprehensive IO model validation."""

    def test_valid_2x2_passes(self) -> None:
        """Known-good 2x2 model passes all checks."""
        Z = np.array([[150.0, 500.0], [200.0, 100.0]])
        x = np.array([1000.0, 2000.0])
        result = validate_model(Z, x, ["S1", "S2"])
        assert result.is_valid
        assert result.spectral_radius < 1.0

    def test_negative_z_detected(self) -> None:
        """Negative Z entry reported in errors."""
        Z = np.array([[10.0, -5.0], [5.0, 10.0]])
        x = np.array([100.0, 100.0])
        result = validate_model(Z, x, ["S1", "S2"])
        assert not result.is_valid
        assert not result.all_z_nonnegative
        assert any("negative" in e.lower() for e in result.errors)

    def test_zero_output_detected(self) -> None:
        """Zero x entry reported in errors."""
        Z = np.array([[10.0, 5.0], [5.0, 10.0]])
        x = np.array([100.0, 0.0])
        result = validate_model(Z, x, ["S1", "S2"])
        assert not result.is_valid
        assert not result.all_x_positive

    def test_high_spectral_radius_detected(self) -> None:
        """Spectral radius >= 1 reported in errors."""
        Z = np.array([[950.0, 500.0], [500.0, 950.0]])
        x = np.array([1000.0, 1000.0])
        result = validate_model(Z, x, ["S1", "S2"])
        assert not result.is_valid
        assert result.spectral_radius >= 1.0
        assert any("spectral" in e.lower() for e in result.errors)

    def test_negative_va_detected(self) -> None:
        """Column sum > 1 (negative VA) reported in errors."""
        # A column with sum > 1 means negative value added
        Z = np.array([[60.0, 5.0], [50.0, 10.0]])
        x = np.array([100.0, 100.0])
        result = validate_model(Z, x, ["S1", "S2"])
        assert not result.all_va_positive

    def test_output_multipliers_computed(self) -> None:
        """Multipliers are column sums of B."""
        Z = np.array([[150.0, 500.0], [200.0, 100.0]])
        x = np.array([1000.0, 2000.0])
        result = validate_model(Z, x, ["S1", "S2"])
        assert "S1" in result.output_multipliers
        assert "S2" in result.output_multipliers
        # Every multiplier should be >= 1
        assert all(m >= 1.0 for m in result.output_multipliers.values())

    def test_invalid_model_detected(self) -> None:
        """Corrupt model (high spectral radius) fails validation."""
        Z = np.array([[800.0, 400.0], [400.0, 800.0]])
        x = np.array([1000.0, 1000.0])
        result = validate_model(Z, x, ["S1", "S2"])
        assert not result.is_valid


# ===================================================================
# 3. TestSyntheticSaudi20Model
# ===================================================================


@pytest.mark.skipif(
    not IO_MODEL_PATH.exists(),
    reason="Synthetic model JSON not generated yet",
)
class TestSyntheticSaudi20Model:
    """Validate the checked-in synthetic 20-sector model."""

    def test_json_loads_successfully(self) -> None:
        """data/curated/saudi_io_synthetic_v1.json loads without error."""
        model = load_from_json(IO_MODEL_PATH)
        assert isinstance(model, IOModelData)

    def test_20_sectors(self) -> None:
        """Model has exactly 20 sectors."""
        model = load_from_json(IO_MODEL_PATH)
        assert len(model.sector_codes) == 20

    def test_isic_sector_codes(self) -> None:
        """Sector codes are ISIC Rev.4 sections A through T."""
        model = load_from_json(IO_MODEL_PATH)
        assert model.sector_codes == ISIC_CODES

    def test_z_matrix_square(self) -> None:
        """Z is 20x20."""
        model = load_from_json(IO_MODEL_PATH)
        assert model.Z.shape == (20, 20)

    def test_z_non_negative(self) -> None:
        """All Z entries >= 0."""
        model = load_from_json(IO_MODEL_PATH)
        result = validate_model(model.Z, model.x, model.sector_codes)
        assert result.all_z_nonnegative

    def test_x_positive(self) -> None:
        """All x entries > 0."""
        model = load_from_json(IO_MODEL_PATH)
        result = validate_model(model.Z, model.x, model.sector_codes)
        assert result.all_x_positive

    def test_spectral_radius_below_one(self) -> None:
        """Spectral radius of A < 1."""
        model = load_from_json(IO_MODEL_PATH)
        result = validate_model(model.Z, model.x, model.sector_codes)
        assert result.spectral_radius < 1.0

    def test_va_positive_all_sectors(self) -> None:
        """Value-added is positive for every sector."""
        model = load_from_json(IO_MODEL_PATH)
        result = validate_model(model.Z, model.x, model.sector_codes)
        assert result.all_va_positive

    def test_b_nonnegative(self) -> None:
        """Leontief inverse B has no negative entries."""
        model = load_from_json(IO_MODEL_PATH)
        result = validate_model(model.Z, model.x, model.sector_codes)
        assert result.b_nonnegative

    def test_multipliers_in_range(self) -> None:
        """All output multipliers between 1.0 and 5.0."""
        model = load_from_json(IO_MODEL_PATH)
        result = validate_model(model.Z, model.x, model.sector_codes)
        for code, m in result.output_multipliers.items():
            assert 1.0 <= m <= 5.0, f"{code} multiplier {m} out of [1.0, 5.0]"

    def test_construction_multiplier_range(self) -> None:
        """Construction (F) multiplier in [1.5, 3.0]."""
        model = load_from_json(IO_MODEL_PATH)
        result = validate_model(model.Z, model.x, model.sector_codes)
        f_mult = result.output_multipliers["F"]
        assert 1.5 <= f_mult <= 3.0, f"F multiplier {f_mult}"

    def test_mining_multiplier_range(self) -> None:
        """Mining (B) multiplier in [1.0, 2.0]."""
        model = load_from_json(IO_MODEL_PATH)
        result = validate_model(model.Z, model.x, model.sector_codes)
        b_mult = result.output_multipliers["B"]
        assert 1.0 <= b_mult <= 2.0, f"B multiplier {b_mult}"

    def test_manufacturing_multiplier_range(self) -> None:
        """Manufacturing (C) multiplier in [1.5, 2.5]."""
        model = load_from_json(IO_MODEL_PATH)
        result = validate_model(model.Z, model.x, model.sector_codes)
        c_mult = result.output_multipliers["C"]
        assert 1.5 <= c_mult <= 2.5, f"C multiplier {c_mult}"

    def test_gdp_order_of_magnitude(self) -> None:
        """Sum of value added within reasonable range for Saudi GDP."""
        model = load_from_json(IO_MODEL_PATH)
        result = validate_model(model.Z, model.x, model.sector_codes)
        # Saudi GDP ~ SAR 2.5-3.5 trillion.
        # Our synthetic model may be lower — we check within 50% of 2.8T
        va_sar_t = result.total_value_added / 1e6
        assert 1.0 < va_sar_t < 4.5, f"Total VA = SAR {va_sar_t:.2f}T"


# ===================================================================
# 4. TestRegistration
# ===================================================================


@pytest.mark.skipif(
    not IO_MODEL_PATH.exists(),
    reason="Synthetic model JSON not generated yet",
)
class TestRegistration:
    """IO loader data can be registered with ModelStore."""

    def test_loaded_model_registers_in_engine(self) -> None:
        """Load JSON -> ModelStore.register() succeeds, B computable."""
        model_data = load_from_json(IO_MODEL_PATH)
        store = ModelStore()
        mv = store.register(
            Z=model_data.Z,
            x=model_data.x,
            sector_codes=model_data.sector_codes,
            base_year=model_data.base_year,
            source=model_data.source,
        )
        loaded = store.get(mv.model_version_id)
        # B should be computable and have correct shape
        assert loaded.B.shape == (20, 20)
        assert np.all(loaded.B >= -1e-10)

    def test_checksum_deterministic(self) -> None:
        """Same JSON produces same checksum on repeated load."""
        model1 = load_from_json(IO_MODEL_PATH)
        model2 = load_from_json(IO_MODEL_PATH)
        store = ModelStore()
        mv1 = store.register(
            Z=model1.Z, x=model1.x, sector_codes=model1.sector_codes,
            base_year=model1.base_year, source="test1",
        )
        store2 = ModelStore()
        mv2 = store2.register(
            Z=model2.Z, x=model2.x, sector_codes=model2.sector_codes,
            base_year=model2.base_year, source="test2",
        )
        assert mv1.checksum == mv2.checksum


# ===================================================================
# 5. TestSeededRunExecution (Amendment 4 — end-to-end)
# ===================================================================


@pytest.mark.skipif(
    not IO_MODEL_PATH.exists(),
    reason="Synthetic model JSON not generated yet",
)
class TestSeededRunExecution:
    """Prove the model is operational, not just loadable."""

    def test_seeded_saudi20_run_executes(self) -> None:
        """Load synthetic model -> register -> shock Construction -> verify output."""
        from src.engine.leontief import LeontiefSolver

        model_data = load_from_json(IO_MODEL_PATH)
        store = ModelStore()
        mv = store.register(
            Z=model_data.Z,
            x=model_data.x,
            sector_codes=model_data.sector_codes,
            base_year=model_data.base_year,
            source=model_data.source,
        )
        loaded = store.get(mv.model_version_id)

        # Create shock: SAR 1 billion final demand increase in Construction (F)
        shock = np.zeros(20)
        f_index = model_data.sector_codes.index("F")
        shock[f_index] = 1000.0  # SAR 1B in millions

        # Run through Leontief solver
        solver = LeontiefSolver()
        result = solver.solve(loaded_model=loaded, delta_d=shock)

        # Verify
        assert result is not None
        assert len(result.delta_x_total) == 20
        # Total output > shock (multiplier > 1)
        assert result.delta_x_total[f_index] > 1000.0
        # Total multiplier in sane range for construction
        total_multiplier = float(np.sum(result.delta_x_total)) / 1000.0
        assert 1.5 < total_multiplier < 3.5, f"Construction multiplier: {total_multiplier}"
        # Direct effect = shock itself
        assert abs(result.delta_x_direct[f_index] - 1000.0) < 1e-6
        # Indirect effect is positive
        assert float(np.sum(result.delta_x_indirect)) > 0


# ===================================================================
# 6. TestLoadSatellites
# ===================================================================


class TestLoadSatellites:
    """Satellite coefficient loading."""

    def test_loads_valid_satellites(self, tmp_path: Path) -> None:
        """Valid satellite JSON loads as SatelliteData."""
        path = _write_minimal_satellites_json(tmp_path)
        sat = load_satellites_from_json(path)
        assert isinstance(sat, SatelliteData)
        assert len(sat.jobs_coeff) == 2
        assert len(sat.import_ratio) == 2
        assert len(sat.va_ratio) == 2

    def test_satellite_import_ratios_valid(self) -> None:
        """All import ratios in [0, 1] for the synthetic model."""
        if not SATELLITES_PATH.exists():
            pytest.skip("Satellites JSON not generated")
        sat = load_satellites_from_json(SATELLITES_PATH)
        assert all(0.0 <= r <= 1.0 for r in sat.import_ratio)

    def test_satellite_va_consistent_with_a(self) -> None:
        """VA ratios in satellites approximately match IO model's 1 - col_sum(A)."""
        if not IO_MODEL_PATH.exists() or not SATELLITES_PATH.exists():
            pytest.skip("Model or satellite JSON not generated")
        model = load_from_json(IO_MODEL_PATH)
        sat = load_satellites_from_json(SATELLITES_PATH)
        result = validate_model(model.Z, model.x, model.sector_codes)
        for i, code in enumerate(model.sector_codes):
            io_va = result.va_ratios[code]
            sat_va = float(sat.va_ratio[i])
            assert abs(io_va - sat_va) < 0.02, (
                f"Sector {code}: IO VA={io_va:.4f}, satellite VA={sat_va:.4f}"
            )

    def test_satellite_dimension_matches_model(self) -> None:
        """Satellite vector length == model sector count."""
        if not IO_MODEL_PATH.exists() or not SATELLITES_PATH.exists():
            pytest.skip("Model or satellite JSON not generated")
        model = load_from_json(IO_MODEL_PATH)
        sat = load_satellites_from_json(SATELLITES_PATH)
        assert len(sat.jobs_coeff) == len(model.sector_codes)
        assert len(sat.import_ratio) == len(model.sector_codes)
        assert len(sat.va_ratio) == len(model.sector_codes)


# ===================================================================
# 7. TestSeedSaudi20
# ===================================================================


class TestSeedSaudi20:
    """Seed script functions for 20-sector model."""

    @pytest.mark.anyio
    async def test_seed_saudi20_idempotent(self, db_session) -> None:  # noqa: ANN001
        """Run seed_saudi20_demo twice -> second returns created=False."""
        from scripts.seed import seed_saudi20_demo

        result1 = await seed_saudi20_demo(db_session)
        assert result1["created"] is True
        assert result1["model_sector_count"] == 20

        result2 = await seed_saudi20_demo(db_session)
        assert result2["created"] is False

    @pytest.mark.anyio
    async def test_seed_saudi20_model_queryable(self, db_session) -> None:  # noqa: ANN001
        """After seed -> query model -> 20 sectors."""
        from scripts.seed import seed_saudi20_model

        mv_row, md_row = await seed_saudi20_model(db_session)
        assert mv_row.sector_count == 20
        assert len(md_row.sector_codes) == 20
        assert md_row.sector_codes == ISIC_CODES


# ===================================================================
# 8. TestTaxonomyFile (Amendment 1)
# ===================================================================


@pytest.mark.skipif(
    not TAXONOMY_PATH.exists(),
    reason="Taxonomy JSON not generated yet",
)
class TestTaxonomyFile:
    """Sector taxonomy ISIC Rev.4 JSON."""

    def test_taxonomy_json_loads_and_has_20_sectors(self) -> None:
        """data/curated/sector_taxonomy_isic4.json has 20 ISIC sections."""
        with TAXONOMY_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["classification"] == "ISIC_REV4_SECTION"
        assert len(data["sectors"]) == 20
        codes = [s["sector_code"] for s in data["sectors"]]
        assert codes == ISIC_CODES


# ===================================================================
# 9. TestLoadFromExcel (stub)
# ===================================================================


class TestLoadFromExcel:
    """Excel loader stub."""

    def test_raises_not_implemented(self) -> None:
        """Excel loader raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="Excel loading"):
            load_from_excel("dummy.xlsx")
