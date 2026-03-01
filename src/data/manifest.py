"""Curated data manifest schema + loader (D-5 Task 1).

Single source of truth for which curated datasets are available.
Each dataset entry carries honest classification:

- curated_real: derived from published, verifiable sources
- curated_estimated: mixed/derived data with estimated components
- synthetic: generated for testing or calibration

Functions:
    load_manifest  — parse manifest.json into ManifestData
    get_dataset    — lookup a DatasetEntry by dataset_id
    verify_checksum — SHA-256 file integrity check
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MANIFEST_PATH: Path = Path("data/curated/manifest.json")

# ---------------------------------------------------------------------------
# Schema (frozen dataclasses)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DatasetEntry:
    """A single curated dataset entry in the manifest."""

    dataset_id: str
    description: str
    source: str
    vintage_year: int
    path: str
    checksum_sha256: str
    resolved_source: Literal["curated_real", "curated_estimated", "synthetic"]
    contains_assumed_components: bool
    confidence: str
    notes: str
    sector_count: int | None = None


@dataclass(frozen=True)
class ManifestData:
    """Top-level manifest structure."""

    manifest_version: str
    created_at: str
    datasets: tuple[DatasetEntry, ...]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_manifest(path: Path | None = None) -> ManifestData:
    """Load and parse a manifest.json file into a ManifestData instance.

    Args:
        path: Path to the manifest JSON file.
              Defaults to DEFAULT_MANIFEST_PATH if not provided.

    Returns:
        Parsed ManifestData.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
        KeyError: If required fields are missing.
    """
    resolved = path or DEFAULT_MANIFEST_PATH
    if not resolved.exists():
        msg = f"Manifest file not found: {resolved}"
        raise FileNotFoundError(msg)

    raw = json.loads(resolved.read_text(encoding="utf-8"))

    datasets = tuple(
        DatasetEntry(
            dataset_id=ds["dataset_id"],
            description=ds["description"],
            source=ds["source"],
            vintage_year=ds["vintage_year"],
            path=ds["path"],
            checksum_sha256=ds["checksum_sha256"],
            resolved_source=ds["resolved_source"],
            contains_assumed_components=ds["contains_assumed_components"],
            confidence=ds["confidence"],
            notes=ds["notes"],
            sector_count=ds.get("sector_count"),
        )
        for ds in raw["datasets"]
    )

    return ManifestData(
        manifest_version=raw["manifest_version"],
        created_at=raw["created_at"],
        datasets=datasets,
    )


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


def get_dataset(manifest: ManifestData, dataset_id: str) -> DatasetEntry | None:
    """Look up a dataset entry by its dataset_id.

    Args:
        manifest: Loaded ManifestData.
        dataset_id: Unique identifier to search for.

    Returns:
        The matching DatasetEntry, or None if not found.
    """
    for entry in manifest.datasets:
        if entry.dataset_id == dataset_id:
            return entry
    return None


# ---------------------------------------------------------------------------
# Integrity
# ---------------------------------------------------------------------------


def verify_checksum(file_path: Path, expected_sha256: str) -> bool:
    """Verify that a file's SHA-256 hash matches the expected value.

    Args:
        file_path: Path to the file to check.
        expected_sha256: Expected lowercase hex-digest.

    Returns:
        True if the hash matches, False otherwise.
    """
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest() == expected_sha256
