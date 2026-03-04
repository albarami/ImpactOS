"""Tests for curated data manifest schema + loader (D-5 Task 1).

Covers:
  - load_manifest returns ManifestData with correct version and dataset count
  - get_dataset finds entry by ID
  - get_dataset returns None for missing ID
  - verify_checksum returns True for correct hash
  - verify_checksum returns False for wrong hash
  - Dataset entry classification values (curated_estimated + contains_assumed_components)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.data.manifest import (
    DatasetEntry,
    ManifestData,
    get_dataset,
    load_manifest,
    verify_checksum,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_MANIFEST = {
    "manifest_version": "1.0",
    "created_at": "2026-03-01T00:00:00Z",
    "datasets": [
        {
            "dataset_id": "saudi_io_kapsarc_2018",
            "description": "Saudi 20-sector IO model derived from KAPSARC/GASTAT data",
            "source": "KAPSARC via D-3 API + GASTAT structure from D-1",
            "vintage_year": 2018,
            "sector_count": 20,
            "path": "data/curated/saudi_io_kapsarc_2018.json",
            "checksum_sha256": "",
            "resolved_source": "curated_real",
            "contains_assumed_components": False,
            "confidence": "HIGH",
            "notes": "Sanitized aggregate",
        },
        {
            "dataset_id": "saudi_type1_multipliers_benchmark",
            "description": "Type I output multiplier benchmarks",
            "source": "KAPSARC benchmark data via D-3",
            "vintage_year": 2018,
            "path": "data/curated/saudi_type1_multipliers_benchmark.json",
            "checksum_sha256": "",
            "resolved_source": "curated_real",
            "contains_assumed_components": False,
            "confidence": "HIGH",
            "notes": "Benchmark multipliers",
        },
        {
            "dataset_id": "saudi_employment_coefficients_2019",
            "description": "Employment coefficients by ISIC section",
            "source": "ILOSTAT + GASTAT labor force data via D-3/D-4",
            "vintage_year": 2019,
            "sector_count": 20,
            "path": "data/curated/saudi_employment_coefficients_2019.json",
            "checksum_sha256": "",
            "resolved_source": "curated_estimated",
            "contains_assumed_components": True,
            "confidence": "ESTIMATED",
            "notes": "Contains synthetic regional benchmark fallback rows",
        },
    ],
}


@pytest.fixture()
def manifest_path(tmp_path: Path) -> Path:
    """Write sample manifest to a temp file and return its path."""
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(SAMPLE_MANIFEST), encoding="utf-8")
    return p


@pytest.fixture()
def manifest(manifest_path: Path) -> ManifestData:
    """Load sample manifest."""
    return load_manifest(manifest_path)


# ---------------------------------------------------------------------------
# load_manifest
# ---------------------------------------------------------------------------


class TestLoadManifest:
    """Tests for load_manifest()."""

    def test_returns_manifest_data_with_correct_version(
        self, manifest: ManifestData
    ) -> None:
        assert manifest.manifest_version == "1.0"

    def test_returns_correct_dataset_count(self, manifest: ManifestData) -> None:
        assert len(manifest.datasets) == 3

    def test_created_at_preserved(self, manifest: ManifestData) -> None:
        assert manifest.created_at == "2026-03-01T00:00:00Z"

    def test_datasets_are_dataset_entry_instances(
        self, manifest: ManifestData
    ) -> None:
        for ds in manifest.datasets:
            assert isinstance(ds, DatasetEntry)

    def test_raises_file_not_found_for_missing_path(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_manifest(Path("/nonexistent/manifest.json"))


# ---------------------------------------------------------------------------
# get_dataset
# ---------------------------------------------------------------------------


class TestGetDataset:
    """Tests for get_dataset()."""

    def test_finds_entry_by_id(self, manifest: ManifestData) -> None:
        entry = get_dataset(manifest, "saudi_io_kapsarc_2018")
        assert entry is not None
        assert entry.dataset_id == "saudi_io_kapsarc_2018"
        assert entry.vintage_year == 2018
        assert entry.sector_count == 20

    def test_returns_none_for_missing_id(self, manifest: ManifestData) -> None:
        result = get_dataset(manifest, "nonexistent_dataset")
        assert result is None

    def test_finds_dataset_without_sector_count(
        self, manifest: ManifestData
    ) -> None:
        entry = get_dataset(manifest, "saudi_type1_multipliers_benchmark")
        assert entry is not None
        assert entry.sector_count is None


# ---------------------------------------------------------------------------
# verify_checksum
# ---------------------------------------------------------------------------


class TestVerifyChecksum:
    """Tests for verify_checksum()."""

    def test_returns_true_for_correct_hash(self, tmp_path: Path) -> None:
        content = b"hello world"
        expected_hash = hashlib.sha256(content).hexdigest()

        f = tmp_path / "test_file.bin"
        f.write_bytes(content)

        assert verify_checksum(f, expected_hash) is True

    def test_returns_false_for_wrong_hash(self, tmp_path: Path) -> None:
        content = b"hello world"
        wrong_hash = "0" * 64

        f = tmp_path / "test_file.bin"
        f.write_bytes(content)

        assert verify_checksum(f, wrong_hash) is False


# ---------------------------------------------------------------------------
# Dataset entry classification
# ---------------------------------------------------------------------------


class TestDatasetClassification:
    """Tests for dataset entry classification values."""

    def test_curated_real_entry(self, manifest: ManifestData) -> None:
        entry = get_dataset(manifest, "saudi_io_kapsarc_2018")
        assert entry is not None
        assert entry.resolved_source == "curated_real"
        assert entry.contains_assumed_components is False

    def test_curated_estimated_entry(self, manifest: ManifestData) -> None:
        entry = get_dataset(manifest, "saudi_employment_coefficients_2019")
        assert entry is not None
        assert entry.resolved_source == "curated_estimated"
        assert entry.contains_assumed_components is True

    def test_confidence_levels(self, manifest: ManifestData) -> None:
        io_entry = get_dataset(manifest, "saudi_io_kapsarc_2018")
        assert io_entry is not None
        assert io_entry.confidence == "HIGH"

        emp_entry = get_dataset(manifest, "saudi_employment_coefficients_2019")
        assert emp_entry is not None
        assert emp_entry.confidence == "ESTIMATED"


# ---------------------------------------------------------------------------
# DatasetEntry frozen behavior
# ---------------------------------------------------------------------------


class TestDatasetEntryFrozen:
    """DatasetEntry should be immutable (frozen dataclass)."""

    def test_frozen_prevents_mutation(self, manifest: ManifestData) -> None:
        entry = get_dataset(manifest, "saudi_io_kapsarc_2018")
        assert entry is not None
        with pytest.raises(AttributeError):
            entry.dataset_id = "tampered"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ManifestData frozen behavior
# ---------------------------------------------------------------------------


class TestManifestDataFrozen:
    """ManifestData should be immutable (frozen dataclass)."""

    def test_frozen_prevents_mutation(self, manifest: ManifestData) -> None:
        with pytest.raises(AttributeError):
            manifest.manifest_version = "9.9"  # type: ignore[misc]
