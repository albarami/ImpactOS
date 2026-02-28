"""Parse ILOSTAT SDMX-JSON employment data.

Transforms SDMX-JSON responses from the ILO API into employment
time series by ISIC Rev.4 economic activity for Saudi Arabia.

Input: data/raw/ilo/sau_employment_by_activity.json
Output: data/curated/sau_employment_by_isic_division.json

SDMX-JSON Structure:
    {
        "dataSets": [{"series": {"0:0:0:0": {"observations": {"0": [value]}}}}],
        "structure": {"dimensions": {"series": [...], "observation": [...]}}
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Mapping from ILO ISIC4 activity codes to ISIC Rev.4 section codes
ILO_ISIC4_TO_SECTION: dict[str, str] = {
    "ECO_ISIC4_A": "A",
    "ECO_ISIC4_B": "B",
    "ECO_ISIC4_C": "C",
    "ECO_ISIC4_D": "D",
    "ECO_ISIC4_E": "E",
    "ECO_ISIC4_F": "F",
    "ECO_ISIC4_G": "G",
    "ECO_ISIC4_H": "H",
    "ECO_ISIC4_I": "I",
    "ECO_ISIC4_J": "J",
    "ECO_ISIC4_K": "K",
    "ECO_ISIC4_L": "L",
    "ECO_ISIC4_M": "M",
    "ECO_ISIC4_N": "N",
    "ECO_ISIC4_O": "O",
    "ECO_ISIC4_P": "P",
    "ECO_ISIC4_Q": "Q",
    "ECO_ISIC4_R": "R",
    "ECO_ISIC4_S": "S",
    "ECO_ISIC4_T": "T",
    "ECO_ISIC4_U": "U",
    "ECO_ISIC4_X": "X",  # Not elsewhere classified
    "ECO_ISIC4_TOTAL": "TOTAL",
}


@dataclass(frozen=True)
class EmploymentObservation:
    """Single observation of employment for a sector-year."""

    section_code: str
    section_name: str
    year: int
    value: float  # Thousands of persons
    confidence: str  # "official", "estimated", "modelled"


@dataclass(frozen=True)
class ILOEmploymentData:
    """Parsed ILO employment data for Saudi Arabia."""

    country: str
    observations: list[EmploymentObservation]
    years: list[int]
    sections: list[str]
    total_observations: int
    warnings: list[str]


def _parse_sdmx_json(data: dict[str, Any]) -> list[EmploymentObservation]:
    """Parse SDMX-JSON into flat observation list.

    Navigates the SDMX structure: dimensions define the key structure,
    dataSets contain the actual values.
    """
    observations: list[EmploymentObservation] = []

    structure = data.get("structure", {})
    dims = structure.get("dimensions", {})
    series_dims = dims.get("series", [])
    obs_dims = dims.get("observation", [])

    # Build dimension value lookups
    series_dim_values: list[list[dict]] = []
    for dim in series_dims:
        series_dim_values.append(dim.get("values", []))

    obs_dim_values: list[list[dict]] = []
    for dim in obs_dims:
        obs_dim_values.append(dim.get("values", []))

    # Find which dimension is classif1 (economic activity)
    activity_dim_idx: int | None = None
    time_dim_idx: int | None = None

    for i, dim in enumerate(series_dims):
        dim_id = dim.get("id", "")
        if dim_id in ("CLASSIF1", "classif1"):
            activity_dim_idx = i
    for i, dim in enumerate(obs_dims):
        dim_id = dim.get("id", "")
        if dim_id in ("TIME_PERIOD", "time"):
            time_dim_idx = i

    datasets = data.get("dataSets", [])
    if not datasets:
        return observations

    series_data = datasets[0].get("series", {})

    for series_key, series_val in series_data.items():
        # series_key = "0:0:0:0" — indices into series dimensions
        key_parts = series_key.split(":")
        key_indices = [int(k) for k in key_parts]

        # Get activity code
        activity_code = ""
        if activity_dim_idx is not None and activity_dim_idx < len(key_indices):
            idx = key_indices[activity_dim_idx]
            vals = series_dim_values[activity_dim_idx]
            if idx < len(vals):
                activity_code = vals[idx].get("id", "")

        section = ILO_ISIC4_TO_SECTION.get(activity_code, "")
        section_name = ""
        if activity_dim_idx is not None:
            idx = key_indices[activity_dim_idx]
            vals = series_dim_values[activity_dim_idx]
            if idx < len(vals):
                section_name = vals[idx].get("name", "")

        # Parse observations
        obs_data = series_val.get("observations", {})
        for obs_key, obs_val in obs_data.items():
            obs_idx = int(obs_key)

            # Get year from observation dimension
            year = 0
            if time_dim_idx is not None and obs_dim_values:
                vals = obs_dim_values[time_dim_idx]
                if obs_idx < len(vals):
                    yr_str = vals[obs_idx].get("id", "")
                    try:
                        year = int(yr_str[:4])
                    except (ValueError, TypeError):
                        pass

            # Value is first element of array
            value = 0.0
            if isinstance(obs_val, list) and obs_val:
                try:
                    value = float(obs_val[0])
                except (ValueError, TypeError):
                    pass

            if section and year:
                observations.append(EmploymentObservation(
                    section_code=section,
                    section_name=section_name,
                    year=year,
                    value=value,
                    confidence="official",
                ))

    return observations


def parse_ilo_employment_file(
    raw_path: str | Path,
) -> ILOEmploymentData:
    """Parse a saved ILOSTAT employment JSON file.

    Handles both single SDMX response and batched format.
    """
    path = Path(raw_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    warnings: list[str] = []

    all_obs: list[EmploymentObservation] = []

    # Handle batched format (from fetch_ilostat.py batching)
    if "dataSets" in data:
        # Single SDMX response
        all_obs = _parse_sdmx_json(data)
    elif any(k.startswith("batch_") for k in data.keys()):
        # Batched responses
        for batch_key in sorted(data.keys()):
            batch_data = data[batch_key]
            if isinstance(batch_data, dict) and "dataSets" in batch_data:
                obs = _parse_sdmx_json(batch_data)
                all_obs.extend(obs)
    else:
        warnings.append(
            f"Unrecognized format. Keys: {sorted(data.keys())[:10]}"
        )

    years = sorted({o.year for o in all_obs})
    sections = sorted({o.section_code for o in all_obs})

    return ILOEmploymentData(
        country="SAU",
        observations=all_obs,
        years=years,
        sections=sections,
        total_observations=len(all_obs),
        warnings=warnings,
    )


def save_curated_employment(
    employment: ILOEmploymentData,
    output_dir: str | Path,
) -> Path:
    """Save parsed employment data as curated JSON."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    output = {
        "source": "ILOSTAT",
        "country": employment.country,
        "unit": "thousands_of_persons",
        "year_range": (
            f"{min(employment.years)}-{max(employment.years)}"
            if employment.years
            else "none"
        ),
        "section_count": len(employment.sections),
        "observation_count": employment.total_observations,
        "observations": [
            {
                "section_code": o.section_code,
                "section_name": o.section_name,
                "year": o.year,
                "value": o.value,
                "confidence": o.confidence,
            }
            for o in employment.observations
        ],
        "warnings": employment.warnings,
    }

    out_path = out_dir / "sau_employment_by_isic_division.json"
    out_path.write_text(json.dumps(output, indent=2))
    return out_path
