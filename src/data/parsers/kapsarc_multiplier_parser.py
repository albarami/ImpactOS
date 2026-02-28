"""Parse KAPSARC Type I multiplier data into benchmark format.

Transforms raw KAPSARC API JSON into a benchmark dataset for
validating our engine's computed multipliers.

Input: data/raw/kapsarc/type1_multipliers.json
Output: data/curated/saudi_type1_multipliers_benchmark.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MultiplierEntry:
    """Single sector's benchmark multiplier data."""

    sector_code: str
    sector_name: str
    output_multiplier: float
    backward_linkage: float | None = None
    forward_linkage: float | None = None


@dataclass(frozen=True)
class MultiplierBenchmark:
    """Complete benchmark multiplier dataset."""

    source: str
    year: int
    entries: list[MultiplierEntry]
    warnings: list[str]


def parse_kapsarc_multiplier_records(
    records: list[dict[str, Any]],
) -> MultiplierBenchmark:
    """Parse KAPSARC Type I multiplier records.

    Records are from 'input-output-table-type-i-multiplier' dataset.
    Each record contains a sector and its multiplier value(s).
    """
    if not records:
        return MultiplierBenchmark(
            source="KAPSARC",
            year=0,
            entries=[],
            warnings=["No records provided"],
        )

    warnings: list[str] = []

    # Discover field names
    sample = records[0]
    available = set(sample.keys())

    # Common patterns
    sector_fields = [
        "sector", "sector_name", "economic_activity", "activity",
        "name", "description",
    ]
    code_fields = [
        "sector_code", "code", "isic_code", "activity_code",
    ]
    mult_fields = [
        "output_multiplier", "multiplier", "type_i_multiplier",
        "total_multiplier", "value",
    ]
    backward_fields = [
        "backward_linkage", "backward", "bl",
    ]
    forward_fields = [
        "forward_linkage", "forward", "fl",
    ]

    def _find(candidates: list[str]) -> str | None:
        for f in candidates:
            if f in available:
                return f
        return None

    sector_field = _find(sector_fields)
    code_field = _find(code_fields)
    mult_field = _find(mult_fields)
    bl_field = _find(backward_fields)
    fl_field = _find(forward_fields)

    if not mult_field:
        warnings.append(
            f"Could not find multiplier field. Available: {sorted(available)}"
        )

    # Detect year
    year_field = _find(["year", "date", "period", "reference_period"])
    year = 0
    if year_field and records:
        try:
            year = int(str(records[0].get(year_field, ""))[:4])
        except (ValueError, TypeError):
            pass

    entries: list[MultiplierEntry] = []
    for rec in records:
        name = str(rec.get(sector_field, "")).strip() if sector_field else ""
        code = str(rec.get(code_field, "")).strip() if code_field else name

        mult_val = 0.0
        if mult_field:
            try:
                mult_val = float(rec.get(mult_field, 0) or 0)
            except (ValueError, TypeError):
                mult_val = 0.0

        bl_val = None
        if bl_field:
            try:
                bl_val = float(rec.get(bl_field, 0) or 0)
            except (ValueError, TypeError):
                pass

        fl_val = None
        if fl_field:
            try:
                fl_val = float(rec.get(fl_field, 0) or 0)
            except (ValueError, TypeError):
                pass

        if code or name:
            entries.append(MultiplierEntry(
                sector_code=code or name,
                sector_name=name or code,
                output_multiplier=mult_val,
                backward_linkage=bl_val,
                forward_linkage=fl_val,
            ))

    return MultiplierBenchmark(
        source="KAPSARC Data Portal",
        year=year,
        entries=entries,
        warnings=warnings,
    )


def parse_kapsarc_multiplier_file(
    raw_path: str | Path,
) -> MultiplierBenchmark:
    """Parse a KAPSARC multiplier JSON file.

    Args:
        raw_path: Path to data/raw/kapsarc/type1_multipliers.json
    """
    path = Path(raw_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("records", [])
    return parse_kapsarc_multiplier_records(records)


def save_multiplier_benchmark(
    benchmark: MultiplierBenchmark,
    output_dir: str | Path,
) -> Path:
    """Save benchmark as curated JSON."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    output = {
        "benchmark_id": "kapsarc-type1-multipliers",
        "source": benchmark.source,
        "year": benchmark.year,
        "multiplier_type": "type_i",
        "sector_count": len(benchmark.entries),
        "sectors": [
            {
                "sector_code": e.sector_code,
                "sector_name": e.sector_name,
                "output_multiplier": e.output_multiplier,
                "backward_linkage": e.backward_linkage,
                "forward_linkage": e.forward_linkage,
            }
            for e in benchmark.entries
        ],
        "warnings": benchmark.warnings,
    }

    out_path = out_dir / "saudi_type1_multipliers_benchmark.json"
    out_path.write_text(json.dumps(output, indent=2))
    return out_path
