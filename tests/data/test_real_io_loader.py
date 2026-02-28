"""Tests for real IO loader with fallback (D-3).

Tests load_real_saudi_io() — falls back to synthetic when
curated data is not available.
"""

from __future__ import annotations

import json
import warnings as python_warnings
from pathlib import Path

import pytest

from src.data.io_loader import IOModelData
from src.data.real_io_loader import (
    list_available_io_models,
    load_real_saudi_io,
)

CURATED_DIR = Path("data/curated")


class TestRealIOLoader:
    """Real IO loader with synthetic fallback."""

    @pytest.mark.skipif(
        not (CURATED_DIR / "saudi_io_synthetic_v1.json").exists(),
        reason="Synthetic model not available",
    )
    def test_fallback_to_synthetic(self) -> None:
        """No curated data -> falls back to synthetic model."""
        with python_warnings.catch_warnings():
            python_warnings.simplefilter("ignore")
            model = load_real_saudi_io(year=2099)
        assert isinstance(model, IOModelData)
        assert "synthetic" in model.source.lower()

    @pytest.mark.skipif(
        not (CURATED_DIR / "saudi_io_synthetic_v1.json").exists(),
        reason="Synthetic model not available",
    )
    def test_fallback_warns(self) -> None:
        """Fallback emits a warning."""
        with python_warnings.catch_warnings(record=True) as w:
            python_warnings.simplefilter("always")
            load_real_saudi_io(year=2099)
            assert len(w) >= 1

    def test_loads_curated_if_exists(self, tmp_path: Path) -> None:
        """If curated file exists, loads it instead of synthetic."""
        # Create a minimal curated IO file
        io_data = {
            "model_id": "kapsarc-io-2019",
            "base_year": 2019,
            "source": "KAPSARC Data Portal",
            "denomination": "SAR_THOUSANDS",
            "sector_count": 2,
            "sector_codes": ["A", "B"],
            "sector_names": {"A": "Agriculture", "B": "Mining"},
            "Z": [[100.0, 50.0], [30.0, 200.0]],
            "x": [500.0, 800.0],
            "metadata": {"origin": "test"},
        }
        curated = tmp_path / "saudi_io_kapsarc_2019.json"
        curated.write_text(json.dumps(io_data))

        model = load_real_saudi_io(year=2019, curated_dir=tmp_path)
        assert isinstance(model, IOModelData)
        assert model.base_year == 2019
        assert "KAPSARC" in model.source

    def test_tries_nearby_years(self, tmp_path: Path) -> None:
        """If exact year not available, tries nearby years."""
        io_data = {
            "model_id": "kapsarc-io-2018",
            "base_year": 2018,
            "source": "KAPSARC test",
            "denomination": "SAR_THOUSANDS",
            "sector_count": 2,
            "sector_codes": ["A", "B"],
            "sector_names": {"A": "Agriculture", "B": "Mining"},
            "Z": [[100.0, 50.0], [30.0, 200.0]],
            "x": [500.0, 800.0],
            "metadata": {"origin": "test"},
        }
        curated = tmp_path / "saudi_io_kapsarc_2018.json"
        curated.write_text(json.dumps(io_data))

        # Request 2019, should find 2018
        model = load_real_saudi_io(year=2019, curated_dir=tmp_path)
        assert model.base_year == 2018

    def test_list_available_models(self) -> None:
        """Lists at least the synthetic model."""
        models = list_available_io_models()
        if (CURATED_DIR / "saudi_io_synthetic_v1.json").exists():
            assert len(models) >= 1
            assert any(m["type"] == "synthetic" for m in models)

    def test_no_data_raises(self, tmp_path: Path) -> None:
        """No curated or synthetic -> FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_real_saudi_io(year=2019, curated_dir=tmp_path)
