"""Parse World Bank WDI API responses into curated time series.

Transforms raw WDI JSON (2-element array format) into clean
time series for use in deflators, macro benchmarks, etc.

Input: data/raw/worldbank/*.json
Output: data/curated/sau_macro_indicators.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WDIObservation:
    """Single year observation for a WDI indicator."""

    year: int
    value: float | None


@dataclass(frozen=True)
class WDITimeSeries:
    """Parsed time series for a single indicator."""

    indicator_code: str
    indicator_name: str
    country: str
    observations: list[WDIObservation]
    latest_year: int | None
    latest_value: float | None


def parse_wdi_records(
    records: list[dict[str, Any]],
    indicator_code: str = "",
) -> WDITimeSeries:
    """Parse WDI API records into a clean time series.

    Records come from the second element of the WDI API response:
    [metadata, records] where each record has 'date', 'value',
    'indicator', 'country' fields.
    """
    if not records:
        return WDITimeSeries(
            indicator_code=indicator_code,
            indicator_name="",
            country="SAU",
            observations=[],
            latest_year=None,
            latest_value=None,
        )

    # Extract indicator info from first record
    first = records[0]
    ind_info = first.get("indicator", {})
    ind_code = ind_info.get("id", indicator_code)
    ind_name = ind_info.get("value", "")
    country = first.get("country", {}).get("id", "SAU")

    observations: list[WDIObservation] = []
    latest_year: int | None = None
    latest_value: float | None = None

    for rec in records:
        try:
            year = int(rec.get("date", 0))
        except (ValueError, TypeError):
            continue

        value = rec.get("value")
        if value is not None:
            try:
                value = float(value)
            except (ValueError, TypeError):
                value = None

        observations.append(WDIObservation(year=year, value=value))

        if value is not None and (latest_year is None or year > latest_year):
            latest_year = year
            latest_value = value

    # Sort by year descending (WDI default) then ascending for storage
    observations.sort(key=lambda o: o.year)

    return WDITimeSeries(
        indicator_code=ind_code,
        indicator_name=ind_name,
        country=country,
        observations=observations,
        latest_year=latest_year,
        latest_value=latest_value,
    )


def parse_wdi_file(raw_path: str | Path) -> WDITimeSeries:
    """Parse a saved WDI API response file.

    The file should contain the full WDI response: either
    [metadata, records] array or a {records: [...]} wrapper.
    """
    path = Path(raw_path)
    data = json.loads(path.read_text(encoding="utf-8"))

    # Handle both formats:
    # 1. Raw WDI: [metadata_dict, records_list]
    # 2. Our wrapper: {"indicator": ..., "records": [...]}
    if isinstance(data, list) and len(data) >= 2:
        records = data[1] or []
    elif isinstance(data, dict):
        records = data.get("records", [])
    else:
        records = []

    indicator_code = ""
    if isinstance(data, dict):
        indicator_code = data.get("indicator", "")

    return parse_wdi_records(records, indicator_code=indicator_code)


def parse_all_wdi_files(
    raw_dir: str | Path,
) -> dict[str, WDITimeSeries]:
    """Parse all WDI files in a directory.

    Returns {filename_stem: WDITimeSeries}.
    """
    raw = Path(raw_dir)
    results: dict[str, WDITimeSeries] = {}

    for path in sorted(raw.glob("sau_*.json")):
        ts = parse_wdi_file(path)
        results[path.stem] = ts

    return results


def save_curated_macro_indicators(
    series_map: dict[str, WDITimeSeries],
    output_dir: str | Path,
) -> Path:
    """Save all WDI series as a single curated JSON file."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    indicators = []
    for _name, ts in sorted(series_map.items()):
        indicators.append({
            "indicator": ts.indicator_code,
            "name": ts.indicator_name,
            "country": ts.country,
            "latest_year": ts.latest_year,
            "latest_value": ts.latest_value,
            "observation_count": len(ts.observations),
            "series": [
                {"year": o.year, "value": o.value}
                for o in ts.observations
            ],
        })

    output = {
        "source": "World Bank WDI",
        "country": "SAU",
        "indicator_count": len(indicators),
        "indicators": indicators,
    }

    out_path = out_dir / "sau_macro_indicators.json"
    out_path.write_text(json.dumps(output, indent=2))
    return out_path
