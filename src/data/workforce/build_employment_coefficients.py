"""Build employment coefficients from D-3 data (D-4 Task 1c).

Combines:
- ILO employment by ISIC (numerator: total jobs per sector)
- KAPSARC IO table x vector (denominator: gross output per sector)

Denominator is ALWAYS gross output (x), NOT GDP / value-added.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from src.data.workforce.unit_registry import (
    EmploymentCoefficient,
    EmploymentCoefficientSet,
    OutputDenomination,
    QualityConfidence,
    SectorGranularity,
)
from src.models.common import ConstraintConfidence

# ISIC sections (A-T) in standard order
ISIC_SECTIONS = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
]

# Regional benchmarks: jobs per SAR million of gross output (synthetic fallback)
# Based on KAPSARC/ESCWA benchmarks for Saudi-like economies.
_SYNTHETIC_BENCHMARKS: dict[str, float] = {
    "A": 25.0,    # Agriculture: labor-intensive
    "B": 2.0,     # Mining: capital-intensive (oil)
    "C": 6.5,     # Manufacturing
    "D": 3.0,     # Electricity/gas
    "E": 5.0,     # Water/waste
    "F": 18.0,    # Construction: very labor-intensive
    "G": 12.0,    # Wholesale/retail
    "H": 8.0,     # Transport
    "I": 15.0,    # Accommodation/food
    "J": 4.0,     # ICT
    "K": 3.5,     # Finance
    "L": 2.0,     # Real estate
    "M": 5.0,     # Professional services
    "N": 10.0,    # Admin/support
    "O": 6.0,     # Public admin
    "P": 8.0,     # Education
    "Q": 7.0,     # Health
    "R": 6.0,     # Arts/recreation
    "S": 10.0,    # Other services
    "T": 30.0,    # Households as employers
}


def build_employment_coefficients(
    ilo_data_path: str | Path | None = None,
    io_model_path: str | Path | None = None,
    year: int = 2019,
) -> EmploymentCoefficientSet:
    """Build employment coefficients from ILO + KAPSARC IO data.

    Preference order for denominator:
    1. Real IO gross output x from KAPSARC (confidence: high)
    2. Synthetic estimate from regional benchmarks (confidence: assumed)

    Args:
        ilo_data_path: Path to curated ILO employment JSON.
        io_model_path: Path to curated KAPSARC IO model JSON.
        year: Target year for coefficients.

    Returns:
        EmploymentCoefficientSet with coefficients for all ISIC sections.
    """
    # Load ILO employment data if available
    employment_by_section = _load_ilo_employment(ilo_data_path)

    # Load IO model x-vector if available
    x_by_section, io_denomination = _load_io_output(io_model_path)

    coefficients: list[EmploymentCoefficient] = []

    for section in ISIC_SECTIONS:
        emp = employment_by_section.get(section)
        x_val = x_by_section.get(section)

        if emp is not None and x_val is not None and x_val > 0:
            # Best case: real employment and real gross output
            jobs_per_unit = emp / x_val
            coefficients.append(EmploymentCoefficient(
                sector_code=section,
                granularity=SectorGranularity.SECTION,
                year=year,
                total_employment=emp,
                gross_output=x_val,
                output_denomination=io_denomination,
                jobs_per_unit_output=jobs_per_unit,
                saudi_share=None,
                source=f"ilo+kapsarc_io_{year}",
                denominator_source="kapsarc_io_x_vector",
                source_confidence=ConstraintConfidence.ESTIMATED,
                quality_confidence=QualityConfidence.HIGH,
            ))
        else:
            # Fallback: synthetic benchmark
            benchmark = _SYNTHETIC_BENCHMARKS.get(section, 5.0)
            coefficients.append(EmploymentCoefficient(
                sector_code=section,
                granularity=SectorGranularity.SECTION,
                year=year,
                total_employment=0.0,
                gross_output=0.0,
                output_denomination=OutputDenomination.SAR_MILLIONS,
                jobs_per_unit_output=benchmark,
                saudi_share=None,
                source="synthetic_regional_benchmark",
                denominator_source="synthetic",
                source_confidence=ConstraintConfidence.ASSUMED,
                quality_confidence=QualityConfidence.LOW,
                notes=f"Synthetic: {benchmark} jobs/M SAR from regional benchmarks",
            ))

    return EmploymentCoefficientSet(
        year=year,
        coefficients=coefficients,
        metadata={
            "builder": "build_employment_coefficients",
            "ilo_data_path": str(ilo_data_path) if ilo_data_path else None,
            "io_model_path": str(io_model_path) if io_model_path else None,
        },
    )


def _load_ilo_employment(
    path: str | Path | None,
) -> dict[str, float]:
    """Load ILO employment data aggregated to section level.

    Returns dict of section_code -> total employment (persons).
    """
    if path is None:
        return {}

    path = Path(path)
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    result: dict[str, float] = {}
    observations = data.get("observations", [])
    for obs in observations:
        section = obs.get("sector_code", "")
        value = obs.get("value")
        if section and value is not None:
            # ILO data may be in thousands — check metadata
            multiplier = 1000.0 if data.get("unit") == "thousands" else 1.0
            result[section] = result.get(section, 0.0) + float(value) * multiplier

    return result


def _load_io_output(
    path: str | Path | None,
) -> tuple[dict[str, float], OutputDenomination]:
    """Load gross output x-vector from curated IO model.

    Returns (section_code -> output value, denomination).
    """
    if path is None:
        return {}, OutputDenomination.SAR_MILLIONS

    path = Path(path)
    if not path.exists():
        return {}, OutputDenomination.SAR_MILLIONS

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    denom_str = data.get("denomination", "SAR_MILLIONS")
    try:
        denomination = OutputDenomination(denom_str)
    except ValueError:
        denomination = OutputDenomination.SAR_MILLIONS

    sector_codes = data.get("sector_codes", [])
    x_raw = data.get("x") or data.get("x_vector", [])
    x_arr = np.array(x_raw, dtype=np.float64)

    result: dict[str, float] = {}
    for i, code in enumerate(sector_codes):
        if i < len(x_arr):
            result[code] = float(x_arr[i])

    return result, denomination


def save_employment_coefficients(
    coeff_set: EmploymentCoefficientSet,
    output_dir: str | Path = "data/curated",
) -> Path:
    """Save employment coefficients to curated JSON.

    Includes _provenance block per Amendment 4.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for c in coeff_set.coefficients:
        entry = {
            "sector_code": c.sector_code,
            "granularity": c.granularity.value,
            "year": c.year,
            "total_employment": c.total_employment,
            "gross_output": c.gross_output,
            "output_denomination": c.output_denomination.value,
            "jobs_per_unit_output": c.jobs_per_unit_output,
            "saudi_share": c.saudi_share,
            "source": c.source,
            "denominator_source": c.denominator_source,
            "source_confidence": c.source_confidence.value,
            "quality_confidence": c.quality_confidence.value,
            "notes": c.notes,
        }
        entries.append(entry)

    output = {
        "_provenance": {
            "builder": "build_employment_coefficients.py",
            "builder_version": "d4_v1",
            "build_timestamp": datetime.now(tz=UTC).isoformat(),
            "source_ids": list({c.source for c in coeff_set.coefficients}),
            "method": "ILO employment / KAPSARC IO gross output x-vector",
            "notes": "Denominator is gross output (x), NOT GDP/value-added",
        },
        "year": coeff_set.year,
        "sector_count": len(entries),
        "coefficients": entries,
        "metadata": {
            k: v for k, v in coeff_set.metadata.items()
            if isinstance(v, str | int | float | bool | type(None))
        },
    }

    out_path = out_dir / f"saudi_employment_coefficients_{coeff_set.year}.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    return out_path


def load_employment_coefficients(
    path: str | Path,
) -> EmploymentCoefficientSet:
    """Load employment coefficients from curated JSON."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    coefficients: list[EmploymentCoefficient] = []
    for entry in data.get("coefficients", []):
        coefficients.append(EmploymentCoefficient(
            sector_code=entry["sector_code"],
            granularity=SectorGranularity(entry.get("granularity", "section")),
            year=entry["year"],
            total_employment=entry["total_employment"],
            gross_output=entry["gross_output"],
            output_denomination=OutputDenomination(entry["output_denomination"]),
            jobs_per_unit_output=entry["jobs_per_unit_output"],
            saudi_share=entry.get("saudi_share"),
            source=entry["source"],
            denominator_source=entry["denominator_source"],
            source_confidence=ConstraintConfidence(entry["source_confidence"]),
            quality_confidence=QualityConfidence(entry["quality_confidence"]),
            notes=entry.get("notes"),
        ))

    return EmploymentCoefficientSet(
        year=data.get("year", 0),
        coefficients=coefficients,
        metadata=data.get("metadata", {}),
    )
