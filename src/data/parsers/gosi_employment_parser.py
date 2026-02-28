"""GOSI employment data parser (D-4 Task 1d).

Parses GOSI employment data for Saudi vs non-Saudi counts by sector.
If real data not available, provides synthetic reference dataset
calibrated against DataSaudi published totals.

All synthetic entries carry confidence: ASSUMED.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.data.workforce.unit_registry import QualityConfidence
from src.models.common import ConstraintConfidence


@dataclass(frozen=True)
class GOSIEmploymentEntry:
    """Employment count for a sector with nationality breakdown."""

    sector_code: str
    sector_name: str
    total_employees: int
    saudi_employees: int
    non_saudi_employees: int
    saudi_share: float
    year: int
    source: str
    source_confidence: ConstraintConfidence
    quality_confidence: QualityConfidence
    notes: str | None = None


@dataclass(frozen=True)
class GOSIEmploymentData:
    """Complete GOSI employment dataset."""

    entries: list[GOSIEmploymentEntry]
    year: int
    total_employees: int
    total_saudi: int
    total_non_saudi: int
    metadata: dict[str, object]

    def get_entry(self, sector_code: str) -> GOSIEmploymentEntry | None:
        """Look up by sector code."""
        for e in self.entries:
            if e.sector_code == sector_code:
                return e
        return None


# DataSaudi calibration targets (2022-2025 published figures)
# Source: datasaudi.sa workforce statistics
_DATASAUDI_CALIBRATION: dict[str, dict[str, object]] = {
    "A": {"name": "Agriculture", "total": 285_000, "saudi_share": 0.08},
    "B": {"name": "Mining", "total": 195_000, "saudi_share": 0.45},
    "C": {"name": "Manufacturing", "total": 820_000, "saudi_share": 0.18},
    "D": {"name": "Electricity/gas", "total": 95_000, "saudi_share": 0.55},
    "E": {"name": "Water/waste", "total": 120_000, "saudi_share": 0.25},
    "F": {"name": "Construction", "total": 2_460_000, "saudi_share": 0.08},
    "G": {"name": "Wholesale/retail", "total": 1_630_000, "saudi_share": 0.22},
    "H": {"name": "Transport", "total": 450_000, "saudi_share": 0.20},
    "I": {"name": "Accommodation/food", "total": 680_000, "saudi_share": 0.12},
    "J": {"name": "ICT", "total": 180_000, "saudi_share": 0.50},
    "K": {"name": "Finance", "total": 165_000, "saudi_share": 0.75},
    "L": {"name": "Real estate", "total": 85_000, "saudi_share": 0.30},
    "M": {"name": "Professional services", "total": 280_000, "saudi_share": 0.25},
    "N": {"name": "Admin/support", "total": 520_000, "saudi_share": 0.15},
    "O": {"name": "Public admin", "total": 380_000, "saudi_share": 0.90},
    "P": {"name": "Education", "total": 420_000, "saudi_share": 0.70},
    "Q": {"name": "Health", "total": 380_000, "saudi_share": 0.35},
    "R": {"name": "Arts/recreation", "total": 75_000, "saudi_share": 0.25},
    "S": {"name": "Other services", "total": 310_000, "saudi_share": 0.15},
    "T": {"name": "Households", "total": 442_298, "saudi_share": 0.02},
}


def build_synthetic_gosi_data(year: int = 2022) -> GOSIEmploymentData:
    """Build synthetic GOSI employment data calibrated to DataSaudi totals.

    All entries marked as ASSUMED confidence.
    """
    entries: list[GOSIEmploymentEntry] = []
    total_emp = 0
    total_saudi = 0

    for code, info in sorted(_DATASAUDI_CALIBRATION.items()):
        total = int(info["total"])
        share = float(info["saudi_share"])
        saudi = int(total * share)
        non_saudi = total - saudi

        entries.append(GOSIEmploymentEntry(
            sector_code=code,
            sector_name=str(info["name"]),
            total_employees=total,
            saudi_employees=saudi,
            non_saudi_employees=non_saudi,
            saudi_share=round(share, 4),
            year=year,
            source="synthetic_datasaudi_calibrated",
            source_confidence=ConstraintConfidence.ASSUMED,
            quality_confidence=QualityConfidence.LOW,
            notes="Synthetic estimate calibrated to DataSaudi published totals",
        ))
        total_emp += total
        total_saudi += saudi

    return GOSIEmploymentData(
        entries=entries,
        year=year,
        total_employees=total_emp,
        total_saudi=total_saudi,
        total_non_saudi=total_emp - total_saudi,
        metadata={
            "source": "synthetic_datasaudi_calibrated",
            "calibration_note": "2022 total ~9.07M employees (DataSaudi)",
        },
    )


def parse_gosi_employment_file(
    path: str | Path,
) -> GOSIEmploymentData:
    """Parse real GOSI employment data from JSON.

    Expected format: list of {sector_code, total, saudi, non_saudi, ...}
    """
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    entries: list[GOSIEmploymentEntry] = []
    records = data.get("records", data.get("entries", []))

    for rec in records:
        code = str(rec.get("sector_code", ""))
        total = int(rec.get("total_employees", rec.get("total", 0)))
        saudi = int(rec.get("saudi_employees", rec.get("saudi", 0)))
        non_saudi = total - saudi
        share = saudi / total if total > 0 else 0.0

        entries.append(GOSIEmploymentEntry(
            sector_code=code,
            sector_name=str(rec.get("sector_name", code)),
            total_employees=total,
            saudi_employees=saudi,
            non_saudi_employees=non_saudi,
            saudi_share=round(share, 4),
            year=int(rec.get("year", data.get("year", 0))),
            source="gosi_contributor_data",
            source_confidence=ConstraintConfidence.HARD,
            quality_confidence=QualityConfidence.HIGH,
        ))

    total_emp = sum(e.total_employees for e in entries)
    total_saudi = sum(e.saudi_employees for e in entries)

    return GOSIEmploymentData(
        entries=entries,
        year=data.get("year", 0),
        total_employees=total_emp,
        total_saudi=total_saudi,
        total_non_saudi=total_emp - total_saudi,
        metadata=data.get("metadata", {}),
    )


def save_gosi_data(
    gosi_data: GOSIEmploymentData,
    output_dir: str | Path = "data/curated",
) -> Path:
    """Save GOSI employment data to curated JSON with provenance."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    output = {
        "_provenance": {
            "builder": "gosi_employment_parser.py",
            "builder_version": "d4_v1",
            "build_timestamp": datetime.now(tz=UTC).isoformat(),
            "source_ids": list({e.source for e in gosi_data.entries}),
            "method": "DataSaudi calibrated synthetic estimates",
        },
        "year": gosi_data.year,
        "total_employees": gosi_data.total_employees,
        "total_saudi": gosi_data.total_saudi,
        "total_non_saudi": gosi_data.total_non_saudi,
        "entries": [
            {
                "sector_code": e.sector_code,
                "sector_name": e.sector_name,
                "total_employees": e.total_employees,
                "saudi_employees": e.saudi_employees,
                "non_saudi_employees": e.non_saudi_employees,
                "saudi_share": e.saudi_share,
                "year": e.year,
                "source": e.source,
                "source_confidence": e.source_confidence.value,
                "quality_confidence": e.quality_confidence.value,
                "notes": e.notes,
            }
            for e in gosi_data.entries
        ],
        "metadata": dict(gosi_data.metadata),
    }

    out_path = out_dir / f"gosi_employment_{gosi_data.year}.json"
    out_path.write_text(json.dumps(output, indent=2))
    return out_path
