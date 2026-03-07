"""Phase 1 verification: denomination safety and real-model regression.

These tests prove:
1. IOModelData reads denomination from JSON
2. ModelVersion carries denomination
3. LoadedModel exposes denomination
4. OutputDenomination enum is importable from src.models.common
5. A real 20-sector Saudi shock produces plausible SAR_THOUSANDS-scale output
6. Backward compat: OutputDenomination still importable from unit_registry
"""

from pathlib import Path

import numpy as np
import pytest

DATA_DIR = Path("data/curated")
KAPSARC_2023 = DATA_DIR / "saudi_io_kapsarc_2023.json"


@pytest.fixture()
def kapsarc_data():
    """Load KAPSARC 2023 curated IO data."""
    from src.data.io_loader import load_from_json

    return load_from_json(str(KAPSARC_2023))


@pytest.fixture()
def registered_model(kapsarc_data):
    """Register the KAPSARC 2023 model in ModelStore."""
    from src.engine.model_store import ModelStore

    store = ModelStore()
    mv = store.register(
        Z=kapsarc_data.Z,
        x=kapsarc_data.x,
        sector_codes=kapsarc_data.sector_codes,
        base_year=kapsarc_data.base_year,
        source="KAPSARC 2023 regression",
        model_denomination=kapsarc_data.model_denomination,
    )
    loaded = store.get(mv.model_version_id)
    return mv, loaded


class TestIOModelDataDenomination:
    """IOModelData must read denomination from JSON."""

    def test_io_data_carries_denomination(self, kapsarc_data):
        assert kapsarc_data.model_denomination == "SAR_THOUSANDS"

    def test_unknown_for_legacy_json(self, tmp_path):
        """JSON files without denomination field get UNKNOWN."""
        from src.data.io_loader import load_from_json

        legacy = {
            "Z": [[1, 2], [3, 4]],
            "x": [10, 20],
            "sector_codes": ["S1", "S2"],
            "base_year": 2020,
        }
        p = tmp_path / "legacy.json"
        import json

        p.write_text(json.dumps(legacy))
        data = load_from_json(str(p))
        assert data.model_denomination == "UNKNOWN"


class TestModelVersionDenomination:
    """ModelVersion must carry the denomination."""

    def test_denomination_on_model_version(self, registered_model):
        mv, _ = registered_model
        assert mv.model_denomination == "SAR_THOUSANDS"

    def test_denomination_default_is_unknown(self):
        from src.models.model_version import ModelVersion

        mv = ModelVersion(
            base_year=2020,
            source="test",
            sector_count=2,
            checksum="sha256:" + "a" * 64,
        )
        assert mv.model_denomination == "UNKNOWN"


class TestLoadedModelDenomination:
    """LoadedModel must expose the denomination property."""

    def test_loaded_model_denomination(self, registered_model):
        _, loaded = registered_model
        assert loaded.model_denomination == "SAR_THOUSANDS"


class TestOutputDenominationEnum:
    """OutputDenomination must be importable from src.models.common."""

    def test_enum_in_common(self):
        from src.models.common import OutputDenomination

        assert OutputDenomination.SAR == "SAR"
        assert OutputDenomination.SAR_THOUSANDS == "SAR_THOUSANDS"
        assert OutputDenomination.SAR_MILLIONS == "SAR_MILLIONS"
        assert OutputDenomination.UNKNOWN == "UNKNOWN"

    def test_backward_compat_import(self):
        from src.data.workforce.unit_registry import OutputDenomination

        assert OutputDenomination.SAR_THOUSANDS == "SAR_THOUSANDS"


class TestRealModelRegression:
    """Regression: a real shock on the 20-sector model produces plausible output."""

    def test_sector_codes_are_real_isic(self, kapsarc_data):
        expected = list("ABCDEFGHIJKLMNOPQRST")
        assert kapsarc_data.sector_codes == expected

    def test_twenty_sectors(self, registered_model):
        _, loaded = registered_model
        assert loaded.n == 20

    def test_construction_shock_output_scale(self, registered_model):
        """A 1 billion SAR shock in sector F (Construction) must produce
        plausible output in the same denomination (SAR_THOUSANDS).

        1 billion SAR = 1,000,000 in SAR_THOUSANDS.
        """
        from src.engine.leontief import LeontiefSolver

        _, loaded = registered_model
        solver = LeontiefSolver()

        # Construct shock vector: 1 billion SAR in Construction (F)
        # In SAR_THOUSANDS: 1B = 1,000,000 thousands
        delta_d = np.zeros(loaded.n)
        f_idx = loaded.sector_codes.index("F")
        delta_d[f_idx] = 1_000_000.0  # 1B SAR in thousands

        result = solver.solve(loaded_model=loaded, delta_d=delta_d)

        # Total output change should be > shock (multiplier > 1)
        total_output = float(np.sum(result.delta_x_total))
        assert total_output > 1_000_000.0, (
            f"Total output {total_output} should exceed the shock of 1,000,000 "
            f"(multiplier should be > 1.0)"
        )

        # Output should be in the same denomination as the shock (SAR_THOUSANDS)
        # A reasonable Type I multiplier for construction is 1.2 - 3.0
        multiplier = total_output / 1_000_000.0
        assert 1.0 < multiplier < 5.0, (
            f"Construction multiplier {multiplier:.2f} should be between 1.0 and 5.0"
        )

        # The denomination should be recorded
        assert loaded.model_denomination == "SAR_THOUSANDS"

    def test_denomination_factor_rejects_unknown(self):
        """denomination_factor() must raise ValueError for UNKNOWN."""
        from src.data.workforce.unit_registry import OutputDenomination, denomination_factor

        with pytest.raises(ValueError, match="UNKNOWN"):
            denomination_factor(OutputDenomination.UNKNOWN, OutputDenomination.SAR)

        with pytest.raises(ValueError, match="UNKNOWN"):
            denomination_factor(OutputDenomination.SAR, OutputDenomination.UNKNOWN)
