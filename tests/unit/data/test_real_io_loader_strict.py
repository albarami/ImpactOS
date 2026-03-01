"""Tests for DataMode enum, IODataProvenance, and strict IO loader (D-5 Task 2).

Tests the core provenance-aware loading that replaces silent fallback
with explicit, honest data source tracking.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.data.io_loader import IOModelData
from src.data.manifest import DatasetEntry, ManifestData
from src.data.real_io_loader import (
    DataMode,
    IODataProvenance,
    ProvenancedIOData,
    load_real_saudi_io,
    load_real_saudi_io_strict,
)


# ---------------------------------------------------------------------------
# Helper: minimal valid IO model JSON
# ---------------------------------------------------------------------------


def _minimal_io_json(
    *,
    base_year: int = 2019,
    source: str = "KAPSARC test",
) -> dict:
    """Return a minimal valid IO model dict for fixture files."""
    return {
        "sector_codes": ["A", "B"],
        "Z": [[100.0, 50.0], [30.0, 200.0]],
        "x": [500.0, 800.0],
        "base_year": base_year,
        "source": source,
    }


def _write_io_json(path: Path, data: dict | None = None) -> Path:
    """Write a minimal IO JSON file and return its path."""
    if data is None:
        data = _minimal_io_json()
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _sha256_of_file(path: Path) -> str:
    """Compute SHA-256 hex-digest of a file."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


# ===========================================================================
# 1. TestDataMode — verify enum values
# ===========================================================================


class TestDataMode:
    """DataMode enum tests."""

    def test_enum_values(self) -> None:
        """DataMode has exactly 3 values with correct string representations."""
        assert DataMode.STRICT_REAL == "strict_real"
        assert DataMode.PREFER_REAL == "prefer_real"
        assert DataMode.SYNTHETIC_ONLY == "synthetic_only"
        # Exactly 3 members
        assert len(DataMode) == 3

    def test_enum_is_str(self) -> None:
        """DataMode members are also str instances (str, Enum)."""
        for member in DataMode:
            assert isinstance(member, str)


# ===========================================================================
# 2. TestIODataProvenance — construct with all fields, verify
# ===========================================================================


class TestIODataProvenance:
    """IODataProvenance frozen dataclass tests."""

    def test_provenance_fields(self) -> None:
        """Construct IODataProvenance with all fields and verify."""
        prov = IODataProvenance(
            data_mode=DataMode.STRICT_REAL,
            resolved_source="curated_real",
            used_fallback=False,
            dataset_id="kapsarc-io-2019",
            requested_year=2019,
            resolved_year=2019,
            checksum_verified=True,
            fallback_reason=None,
            manifest_entry={"dataset_id": "kapsarc-io-2019"},
        )
        assert prov.data_mode == DataMode.STRICT_REAL
        assert prov.resolved_source == "curated_real"
        assert prov.used_fallback is False
        assert prov.dataset_id == "kapsarc-io-2019"
        assert prov.requested_year == 2019
        assert prov.resolved_year == 2019
        assert prov.checksum_verified is True
        assert prov.fallback_reason is None
        assert prov.manifest_entry is not None

    def test_provenance_is_frozen(self) -> None:
        """IODataProvenance is immutable."""
        prov = IODataProvenance(
            data_mode=DataMode.PREFER_REAL,
            resolved_source="synthetic_fallback",
            used_fallback=True,
            dataset_id=None,
            requested_year=2020,
            resolved_year=None,
            checksum_verified=False,
            fallback_reason="no curated data found",
            manifest_entry=None,
        )
        with pytest.raises(AttributeError):
            prov.used_fallback = False  # type: ignore[misc]


# ===========================================================================
# 3. TestStrictLoader — the main strict loader tests
# ===========================================================================


class TestStrictLoader:
    """Tests for load_real_saudi_io_strict()."""

    # ---- STRICT_REAL mode ----

    def test_strict_real_loads_curated(self, tmp_path: Path) -> None:
        """STRICT_REAL loads curated file, provenance says curated_real."""
        curated_file = tmp_path / "saudi_io_kapsarc_2019.json"
        _write_io_json(curated_file, _minimal_io_json(base_year=2019, source="KAPSARC"))

        result = load_real_saudi_io_strict(
            mode=DataMode.STRICT_REAL,
            year=2019,
            curated_dir=tmp_path,
        )

        assert isinstance(result, ProvenancedIOData)
        assert isinstance(result.io_data, IOModelData)
        assert result.io_data.base_year == 2019
        assert result.provenance.resolved_source == "curated_real"
        assert result.provenance.used_fallback is False
        assert result.provenance.data_mode == DataMode.STRICT_REAL
        assert result.provenance.requested_year == 2019
        assert result.provenance.resolved_year == 2019

    def test_strict_real_raises_on_missing(self, tmp_path: Path) -> None:
        """STRICT_REAL raises FileNotFoundError when no curated data exists."""
        with pytest.raises(FileNotFoundError):
            load_real_saudi_io_strict(
                mode=DataMode.STRICT_REAL,
                year=2019,
                curated_dir=tmp_path,
            )

    def test_strict_real_never_uses_synthetic(self, tmp_path: Path) -> None:
        """STRICT_REAL does NOT fall back to synthetic even if it exists."""
        synthetic = tmp_path / "saudi_io_synthetic_v1.json"
        _write_io_json(synthetic, _minimal_io_json(source="synthetic"))

        with pytest.raises(FileNotFoundError):
            load_real_saudi_io_strict(
                mode=DataMode.STRICT_REAL,
                year=2019,
                curated_dir=tmp_path,
            )

    # ---- PREFER_REAL mode ----

    def test_prefer_real_uses_curated_when_available(self, tmp_path: Path) -> None:
        """PREFER_REAL picks curated over synthetic when both present."""
        curated = tmp_path / "saudi_io_kapsarc_2019.json"
        _write_io_json(curated, _minimal_io_json(base_year=2019, source="KAPSARC"))
        synthetic = tmp_path / "saudi_io_synthetic_v1.json"
        _write_io_json(synthetic, _minimal_io_json(source="synthetic"))

        result = load_real_saudi_io_strict(
            mode=DataMode.PREFER_REAL,
            year=2019,
            curated_dir=tmp_path,
        )

        assert result.provenance.resolved_source == "curated_real"
        assert result.provenance.used_fallback is False
        assert result.io_data.base_year == 2019

    def test_prefer_real_falls_back_to_synthetic(self, tmp_path: Path) -> None:
        """PREFER_REAL falls back to synthetic with honest provenance."""
        synthetic = tmp_path / "saudi_io_synthetic_v1.json"
        _write_io_json(synthetic, _minimal_io_json(source="synthetic"))

        result = load_real_saudi_io_strict(
            mode=DataMode.PREFER_REAL,
            year=2019,
            curated_dir=tmp_path,
        )

        assert result.provenance.resolved_source == "synthetic_fallback"
        assert result.provenance.used_fallback is True
        assert result.provenance.fallback_reason is not None
        assert result.provenance.data_mode == DataMode.PREFER_REAL

    # ---- SYNTHETIC_ONLY mode ----

    def test_synthetic_only_always_uses_synthetic(self, tmp_path: Path) -> None:
        """SYNTHETIC_ONLY skips curated even when it exists."""
        curated = tmp_path / "saudi_io_kapsarc_2019.json"
        _write_io_json(curated, _minimal_io_json(base_year=2019, source="KAPSARC"))
        synthetic = tmp_path / "saudi_io_synthetic_v1.json"
        _write_io_json(synthetic, _minimal_io_json(source="synthetic"))

        result = load_real_saudi_io_strict(
            mode=DataMode.SYNTHETIC_ONLY,
            year=2019,
            curated_dir=tmp_path,
        )

        assert result.provenance.resolved_source == "synthetic_only"
        assert result.provenance.used_fallback is False
        assert result.provenance.dataset_id is None
        assert "synthetic" in result.io_data.source.lower()

    # ---- Year resolution ----

    def test_requested_vs_resolved_year(self, tmp_path: Path) -> None:
        """Request year=2019, only 2018 exists => requested=2019, resolved=2018."""
        curated_2018 = tmp_path / "saudi_io_kapsarc_2018.json"
        _write_io_json(curated_2018, _minimal_io_json(base_year=2018, source="KAPSARC"))

        result = load_real_saudi_io_strict(
            mode=DataMode.STRICT_REAL,
            year=2019,
            curated_dir=tmp_path,
        )

        assert result.provenance.requested_year == 2019
        assert result.provenance.resolved_year == 2018
        assert result.io_data.base_year == 2018

    # ---- Manifest integration ----

    def test_manifest_lookup_and_checksum(self, tmp_path: Path) -> None:
        """When manifest is provided, dataset_id and checksum are used."""
        curated = tmp_path / "saudi_io_kapsarc_2019.json"
        _write_io_json(curated, _minimal_io_json(base_year=2019, source="KAPSARC"))
        file_checksum = _sha256_of_file(curated)

        manifest = ManifestData(
            manifest_version="1.0",
            created_at="2026-03-01",
            datasets=(
                DatasetEntry(
                    dataset_id="kapsarc-io-2019",
                    description="KAPSARC IO 2019",
                    source="KAPSARC",
                    vintage_year=2019,
                    path="saudi_io_kapsarc_2019.json",
                    checksum_sha256=file_checksum,
                    resolved_source="curated_real",
                    contains_assumed_components=False,
                    confidence="high",
                    notes="test fixture",
                ),
            ),
        )

        result = load_real_saudi_io_strict(
            mode=DataMode.STRICT_REAL,
            year=2019,
            curated_dir=tmp_path,
            manifest=manifest,
        )

        assert result.provenance.dataset_id == "kapsarc-io-2019"
        assert result.provenance.checksum_verified is True
        assert result.provenance.manifest_entry is not None

    # ---- Backward compatibility ----

    def test_backward_compat_load_real_saudi_io(self, tmp_path: Path) -> None:
        """Existing load_real_saudi_io() still returns IOModelData."""
        curated = tmp_path / "saudi_io_kapsarc_2019.json"
        _write_io_json(curated, _minimal_io_json(base_year=2019, source="KAPSARC"))

        model = load_real_saudi_io(year=2019, curated_dir=tmp_path)

        assert isinstance(model, IOModelData)
        assert model.base_year == 2019
