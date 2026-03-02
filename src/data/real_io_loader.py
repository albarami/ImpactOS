"""Load real Saudi IO model from curated external data.

Provides:
  load_real_saudi_io()        — backward-compatible loader (PREFER_REAL)
  load_real_saudi_io_strict() — provenance-aware loader with explicit DataMode
  list_available_io_models()  — enumerate available datasets

D-5 Task 2: DataMode enum + IODataProvenance + strict loader.
Replaces silent fallback with explicit provenance tracking.
"""

from __future__ import annotations

import hashlib
import warnings
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from src.data.io_loader import IOModelData, load_from_json
from src.data.manifest import ManifestData

# Default paths (relative to project root)
CURATED_DIR = Path("data/curated")
SYNTHETIC_DIR = Path("data/synthetic")
SYNTHETIC_PATH = SYNTHETIC_DIR / "saudi_io_synthetic_v1.json"


# ---------------------------------------------------------------------------
# DataMode enum
# ---------------------------------------------------------------------------


class DataMode(str, Enum):
    """Controls how the IO loader resolves data sources.

    STRICT_REAL is the only mode permitted in runtime API flows.
    PREFER_REAL and SYNTHETIC_ONLY exist for offline dev/test tooling
    only and must never be used by API-driven execution paths.
    """

    STRICT_REAL = "strict_real"
    PREFER_REAL = "prefer_real"          # Non-runtime: dev/test only
    SYNTHETIC_ONLY = "synthetic_only"    # Non-runtime: dev/test only


# ---------------------------------------------------------------------------
# Provenance dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IODataProvenance:
    """Tracks exactly where IO data came from and how it was resolved.

    Modeled after CoefficientProvenance in satellite_coeff_loader.py
    but specific to IO model loading.
    """

    data_mode: DataMode
    resolved_source: str        # "curated_real" | "curated_estimated" | "synthetic" | "synthetic_fallback" | "synthetic_only"
    used_fallback: bool
    dataset_id: str | None      # From manifest
    requested_year: int | None  # What caller asked for
    resolved_year: int | None   # What was actually loaded
    checksum_verified: bool
    fallback_reason: str | None
    manifest_entry: dict | None  # Full manifest entry if available


@dataclass(frozen=True)
class ProvenancedIOData:
    """IO model data bundled with its provenance."""

    io_data: IOModelData
    provenance: IODataProvenance


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_curated_file(base: Path, year: int) -> tuple[Path, int] | None:
    """Search for curated kapsarc file: exact year first, then +/- 4.

    Returns (path, resolved_year) or None if not found.
    """
    # Exact year first
    exact = base / f"saudi_io_kapsarc_{year}.json"
    if exact.exists():
        return exact, year

    # Nearby years (offset 1..4, alternating before/after)
    for offset in range(1, 5):
        for candidate_year in (year - offset, year + offset):
            candidate = base / f"saudi_io_kapsarc_{candidate_year}.json"
            if candidate.exists():
                return candidate, candidate_year

    return None


def _find_synthetic_file(base: Path, curated_dir_provided: bool) -> Path | None:
    """Locate the synthetic fallback file.

    When curated_dir is explicitly provided, only look inside that dir.
    Otherwise check the default SYNTHETIC_PATH.
    """
    if curated_dir_provided:
        synth = base / "saudi_io_synthetic_v1.json"
    else:
        synth = SYNTHETIC_PATH
    return synth if synth.exists() else None


def _resolve_manifest_info(
    manifest: ManifestData | None,
    resolved_path: Path,
    base: Path,
) -> tuple[str | None, bool, dict | None]:
    """Look up dataset_id from manifest and verify checksum.

    Returns (dataset_id, checksum_verified, manifest_entry_dict).
    """
    if manifest is None:
        return None, False, None

    # Match by path (relative to base dir)
    rel = resolved_path.name
    for entry in manifest.datasets:
        entry_filename = Path(entry.path).name
        if entry_filename == rel:
            # Verify checksum
            sha = hashlib.sha256()
            with open(resolved_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha.update(chunk)
            checksum_ok = sha.hexdigest() == entry.checksum_sha256

            entry_dict = {
                "dataset_id": entry.dataset_id,
                "description": entry.description,
                "source": entry.source,
                "vintage_year": entry.vintage_year,
                "path": entry.path,
                "checksum_sha256": entry.checksum_sha256,
                "resolved_source": entry.resolved_source,
                "contains_assumed_components": entry.contains_assumed_components,
                "confidence": entry.confidence,
                "notes": entry.notes,
            }
            return entry.dataset_id, checksum_ok, entry_dict

    return None, False, None


# ---------------------------------------------------------------------------
# Strict (provenance-aware) loader
# ---------------------------------------------------------------------------


def load_real_saudi_io_strict(
    mode: DataMode,
    year: int = 2019,
    curated_dir: str | Path | None = None,
    manifest: ManifestData | None = None,
) -> ProvenancedIOData:
    """Load Saudi IO model with explicit provenance tracking.

    Args:
        mode: DataMode controlling fallback behavior.
        year: Target year for the IO model.
        curated_dir: Override curated data directory.
        manifest: Optional manifest for dataset_id lookup and checksum.

    Returns:
        ProvenancedIOData with the loaded model and its provenance.

    Raises:
        FileNotFoundError: In STRICT_REAL mode if no curated data found.
        FileNotFoundError: In PREFER_REAL mode if neither curated nor synthetic found.
        FileNotFoundError: In SYNTHETIC_ONLY mode if synthetic file missing.
    """
    base = Path(curated_dir) if curated_dir else CURATED_DIR
    curated_dir_provided = curated_dir is not None

    # -- SYNTHETIC_ONLY: skip curated entirely --
    if mode == DataMode.SYNTHETIC_ONLY:
        synth_path = _find_synthetic_file(base, curated_dir_provided)
        if synth_path is None:
            raise FileNotFoundError(
                f"No synthetic IO model found (looked in {base})."
            )
        io_data = load_from_json(str(synth_path))
        provenance = IODataProvenance(
            data_mode=DataMode.SYNTHETIC_ONLY,
            resolved_source="synthetic_only",
            used_fallback=False,
            dataset_id=None,
            requested_year=year,
            resolved_year=io_data.base_year,
            checksum_verified=False,
            fallback_reason=None,
            manifest_entry=None,
        )
        return ProvenancedIOData(io_data=io_data, provenance=provenance)

    # -- STRICT_REAL or PREFER_REAL: try curated first --
    found = _find_curated_file(base, year)

    if found is not None:
        curated_path, resolved_year = found
        try:
            io_data = load_from_json(str(curated_path))
        except Exception as e:
            # If loading fails, treat as not found for fallback logic
            if mode == DataMode.STRICT_REAL:
                raise FileNotFoundError(
                    f"Curated IO model at {curated_path} exists but failed to load: {e}"
                ) from e
            # PREFER_REAL: fall through to synthetic
            warnings.warn(
                f"Failed to load curated IO model from {curated_path}: {e}. "
                "Falling back to synthetic.",
                stacklevel=2,
            )
            found = None  # Force fallback below

    if found is not None:
        curated_path, resolved_year = found
        # Manifest lookup
        dataset_id, checksum_ok, manifest_dict = _resolve_manifest_info(
            manifest, curated_path, base,
        )
        # Determine resolved_source from manifest if available
        resolved_source = "curated_real"
        if manifest_dict and manifest_dict.get("resolved_source"):
            resolved_source = manifest_dict["resolved_source"]

        provenance = IODataProvenance(
            data_mode=mode,
            resolved_source=resolved_source,
            used_fallback=False,
            dataset_id=dataset_id,
            requested_year=year,
            resolved_year=resolved_year,
            checksum_verified=checksum_ok,
            fallback_reason=None,
            manifest_entry=manifest_dict,
        )
        return ProvenancedIOData(io_data=io_data, provenance=provenance)

    # -- Curated not found --
    if mode == DataMode.STRICT_REAL:
        raise FileNotFoundError(
            f"STRICT_REAL: No curated IO model found for year={year} "
            f"(searched {base}/saudi_io_kapsarc_*.json, years {year-4}..{year+4})."
        )

    # PREFER_REAL: fall back to synthetic
    synth_path = _find_synthetic_file(base, curated_dir_provided)
    if synth_path is None:
        raise FileNotFoundError(
            f"No IO model available: neither curated (year={year}) "
            f"nor synthetic found."
        )

    warnings.warn(
        f"No curated IO model found for year {year}. "
        "Using synthetic model.",
        stacklevel=2,
    )
    io_data = load_from_json(str(synth_path))
    provenance = IODataProvenance(
        data_mode=DataMode.PREFER_REAL,
        resolved_source="synthetic_fallback",
        used_fallback=True,
        dataset_id=None,
        requested_year=year,
        resolved_year=io_data.base_year,
        checksum_verified=False,
        fallback_reason=f"No curated IO model found for year {year}",
        manifest_entry=None,
    )
    return ProvenancedIOData(io_data=io_data, provenance=provenance)


# ---------------------------------------------------------------------------
# Backward-compatible loader (wraps strict loader)
# ---------------------------------------------------------------------------


def load_real_saudi_io(
    year: int = 2019,
    curated_dir: str | Path | None = None,
) -> IOModelData:
    """Load real Saudi IO model from curated KAPSARC data.

    NON-RUNTIME: This backward-compatible wrapper uses PREFER_REAL
    mode with synthetic fallback. It must NOT be called from API
    runtime paths. Use load_real_saudi_io_strict(STRICT_REAL) instead.

    Args:
        year: Target year for the IO model (tries nearest available).
        curated_dir: Override curated data directory.

    Returns:
        IOModelData instance (real or synthetic).
    """
    result = load_real_saudi_io_strict(
        mode=DataMode.PREFER_REAL,
        year=year,
        curated_dir=curated_dir,
    )
    return result.io_data


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def list_available_io_models(
    curated_dir: str | Path | None = None,
) -> list[dict]:
    """List all available IO models (real and synthetic).

    Returns list of {source, year, path, type} dicts.
    """
    base = Path(curated_dir) if curated_dir else CURATED_DIR
    models: list[dict] = []

    # Synthetic model
    if SYNTHETIC_PATH.exists():
        models.append({
            "source": "synthetic",
            "year": 2018,
            "path": str(SYNTHETIC_PATH),
            "type": "synthetic",
        })

    # KAPSARC curated models
    for path in sorted(base.glob("saudi_io_kapsarc_*.json")):
        try:
            year_str = path.stem.split("_")[-1]
            year = int(year_str)
            models.append({
                "source": "kapsarc",
                "year": year,
                "path": str(path),
                "type": "real",
            })
        except (ValueError, IndexError):
            pass

    return models
