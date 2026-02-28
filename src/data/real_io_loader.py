"""Load real Saudi IO model from curated external data.

Provides load_real_saudi_io() which attempts to load a real IO model
from curated KAPSARC data, falling back to the synthetic model if
curated data is not available.

This does NOT replace the synthetic model — it provides an alternative.
The engine works with either.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from src.data.io_loader import IOModelData, load_from_json

# Default paths (relative to project root)
CURATED_DIR = Path("data/curated")
SYNTHETIC_PATH = CURATED_DIR / "saudi_io_synthetic_v1.json"


def load_real_saudi_io(
    year: int = 2019,
    curated_dir: str | Path | None = None,
) -> IOModelData:
    """Load real Saudi IO model from curated KAPSARC data.

    Falls back to synthetic model if curated data not available.

    Args:
        year: Target year for the IO model (tries nearest available).
        curated_dir: Override curated data directory.

    Returns:
        IOModelData instance (real or synthetic).
    """
    base = Path(curated_dir) if curated_dir else CURATED_DIR

    # Try exact year first, then nearby years
    candidates = [
        base / f"saudi_io_kapsarc_{year}.json",
    ]
    for offset in range(1, 5):
        candidates.append(base / f"saudi_io_kapsarc_{year - offset}.json")
        candidates.append(base / f"saudi_io_kapsarc_{year + offset}.json")

    for path in candidates:
        if path.exists():
            try:
                model = load_from_json(str(path))
                return model
            except Exception as e:
                warnings.warn(
                    f"Failed to load real IO model from {path}: {e}. "
                    "Falling back to synthetic.",
                    stacklevel=2,
                )

    # Fallback to synthetic
    # When curated_dir is explicitly provided, only look there (+ global).
    # When curated_dir is None, only check the default SYNTHETIC_PATH.
    synthetic_candidates = []
    if curated_dir:
        # Check for synthetic in the overridden directory only —
        # don't fall back to global when caller constrains the directory
        synthetic_candidates.append(base / "saudi_io_synthetic_v1.json")
    else:
        synthetic_candidates.append(SYNTHETIC_PATH)

    for synth_path in synthetic_candidates:
        if synth_path.exists():
            warnings.warn(
                f"No curated IO model found for year {year}. "
                "Using synthetic model.",
                stacklevel=2,
            )
            return load_from_json(str(synth_path))

    raise FileNotFoundError(
        f"No IO model available: neither curated (year={year}) "
        f"nor synthetic found."
    )


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
