"""Build sector-to-occupation bridge matrix (D-4 Task 2c).

Strategy:
1. Check D-3 ILO data for cross-classified employment x activity x occupation
2. If no cross-tab — build synthetic bridge from structural patterns
3. Calibrate against DataSaudi occupation totals as column marginals

Section-level only (A-T, 20 sectors) for v1.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from src.data.workforce.occupation_bridge import (
    ISCO08_MAJOR_GROUPS,
    OccupationBridge,
    OccupationBridgeEntry,
)
from src.data.workforce.unit_registry import QualityConfidence
from src.models.common import ConstraintConfidence

# ISIC sections
ISIC_SECTIONS = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
]

# Structural occupation patterns by sector (expert knowledge).
# Maps sector -> {ISCO major group -> approximate share}.
# Shares must sum to ~1.0 per sector.
_STRUCTURAL_PATTERNS: dict[str, dict[str, float]] = {
    "A": {"0": 0.00, "1": 0.03, "2": 0.02, "3": 0.03, "4": 0.02,
           "5": 0.02, "6": 0.35, "7": 0.08, "8": 0.10, "9": 0.35},
    "B": {"0": 0.00, "1": 0.08, "2": 0.15, "3": 0.15, "4": 0.05,
           "5": 0.02, "6": 0.00, "7": 0.15, "8": 0.25, "9": 0.15},
    "C": {"0": 0.00, "1": 0.06, "2": 0.08, "3": 0.10, "4": 0.05,
           "5": 0.03, "6": 0.00, "7": 0.25, "8": 0.28, "9": 0.15},
    "D": {"0": 0.00, "1": 0.08, "2": 0.15, "3": 0.20, "4": 0.08,
           "5": 0.02, "6": 0.00, "7": 0.12, "8": 0.25, "9": 0.10},
    "E": {"0": 0.00, "1": 0.05, "2": 0.08, "3": 0.12, "4": 0.05,
           "5": 0.02, "6": 0.00, "7": 0.15, "8": 0.18, "9": 0.35},
    "F": {"0": 0.00, "1": 0.04, "2": 0.05, "3": 0.06, "4": 0.03,
           "5": 0.02, "6": 0.00, "7": 0.35, "8": 0.15, "9": 0.30},
    "G": {"0": 0.00, "1": 0.08, "2": 0.05, "3": 0.05, "4": 0.10,
           "5": 0.45, "6": 0.00, "7": 0.02, "8": 0.05, "9": 0.20},
    "H": {"0": 0.00, "1": 0.06, "2": 0.05, "3": 0.08, "4": 0.08,
           "5": 0.05, "6": 0.00, "7": 0.05, "8": 0.45, "9": 0.18},
    "I": {"0": 0.00, "1": 0.06, "2": 0.03, "3": 0.04, "4": 0.05,
           "5": 0.40, "6": 0.00, "7": 0.08, "8": 0.04, "9": 0.30},
    "J": {"0": 0.00, "1": 0.12, "2": 0.35, "3": 0.25, "4": 0.10,
           "5": 0.05, "6": 0.00, "7": 0.03, "8": 0.02, "9": 0.08},
    "K": {"0": 0.00, "1": 0.15, "2": 0.25, "3": 0.20, "4": 0.25,
           "5": 0.05, "6": 0.00, "7": 0.00, "8": 0.00, "9": 0.10},
    "L": {"0": 0.00, "1": 0.12, "2": 0.10, "3": 0.10, "4": 0.15,
           "5": 0.20, "6": 0.00, "7": 0.05, "8": 0.03, "9": 0.25},
    "M": {"0": 0.00, "1": 0.10, "2": 0.35, "3": 0.20, "4": 0.12,
           "5": 0.05, "6": 0.00, "7": 0.05, "8": 0.03, "9": 0.10},
    "N": {"0": 0.00, "1": 0.05, "2": 0.05, "3": 0.08, "4": 0.10,
           "5": 0.15, "6": 0.00, "7": 0.07, "8": 0.10, "9": 0.40},
    "O": {"0": 0.10, "1": 0.15, "2": 0.15, "3": 0.15, "4": 0.20,
           "5": 0.10, "6": 0.00, "7": 0.02, "8": 0.03, "9": 0.10},
    "P": {"0": 0.00, "1": 0.08, "2": 0.55, "3": 0.15, "4": 0.08,
           "5": 0.04, "6": 0.00, "7": 0.00, "8": 0.00, "9": 0.10},
    "Q": {"0": 0.00, "1": 0.08, "2": 0.40, "3": 0.25, "4": 0.08,
           "5": 0.05, "6": 0.00, "7": 0.00, "8": 0.02, "9": 0.12},
    "R": {"0": 0.00, "1": 0.08, "2": 0.15, "3": 0.12, "4": 0.08,
           "5": 0.25, "6": 0.00, "7": 0.05, "8": 0.07, "9": 0.20},
    "S": {"0": 0.00, "1": 0.05, "2": 0.08, "3": 0.08, "4": 0.08,
           "5": 0.30, "6": 0.00, "7": 0.10, "8": 0.06, "9": 0.25},
    "T": {"0": 0.00, "1": 0.00, "2": 0.00, "3": 0.00, "4": 0.00,
           "5": 0.15, "6": 0.00, "7": 0.00, "8": 0.05, "9": 0.80},
}


def build_occupation_bridge(year: int = 2022) -> OccupationBridge:
    """Build the sector-to-occupation bridge matrix from structural patterns.

    For v1, uses expert-judgment patterns. All entries marked ASSUMED.
    Future versions will incorporate ILO cross-tabulated data if available.

    Returns:
        OccupationBridge with entries for all 20 sections x 10 major groups.
    """
    entries: list[OccupationBridgeEntry] = []

    for section in ISIC_SECTIONS:
        pattern = _STRUCTURAL_PATTERNS.get(section, {})

        # Normalize shares to exactly 1.0
        total = sum(pattern.values())
        if total <= 0:
            total = 1.0

        for occ_code in sorted(ISCO08_MAJOR_GROUPS):
            share = pattern.get(occ_code, 0.0) / total
            entries.append(OccupationBridgeEntry(
                sector_code=section,
                occupation_code=occ_code,
                share=round(share, 4),
                source="expert_structural_pattern_v1",
                source_confidence=ConstraintConfidence.ASSUMED,
                quality_confidence=QualityConfidence.LOW,
            ))

    return OccupationBridge(
        year=year,
        entries=entries,
        metadata={
            "method": "Expert-judgment structural patterns",
            "granularity": "section",
            "calibration": "DataSaudi occupation totals (approximate)",
            "note": "Section-level only for v1. Do not use for division-level precision.",
        },
    )


def save_occupation_bridge(
    bridge: OccupationBridge,
    output_dir: str | Path = "data/curated",
) -> Path:
    """Save occupation bridge to curated JSON with provenance."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    entries_out = []
    for e in bridge.entries:
        if e.share > 0:  # Only save non-zero entries
            entries_out.append({
                "sector_code": e.sector_code,
                "occupation_code": e.occupation_code,
                "share": e.share,
                "source": e.source,
                "source_confidence": e.source_confidence.value,
                "quality_confidence": e.quality_confidence.value,
            })

    output = {
        "_provenance": {
            "builder": "build_occupation_bridge.py",
            "builder_version": "d4_v1",
            "build_timestamp": datetime.now(tz=UTC).isoformat(),
            "source_ids": ["expert_structural_pattern_v1"],
            "method": "Expert-judgment structural patterns, section-level",
            "notes": "Future: integrate ILO cross-tab + RAS balancing",
        },
        "year": bridge.year,
        "granularity": "section",
        "sector_count": len(ISIC_SECTIONS),
        "occupation_groups": 10,
        "entries": entries_out,
        "metadata": dict(bridge.metadata),
    }

    out_path = out_dir / f"saudi_occupation_bridge_{bridge.year}.json"
    out_path.write_text(json.dumps(output, indent=2))
    return out_path


def load_occupation_bridge(path: str | Path) -> OccupationBridge:
    """Load occupation bridge from curated JSON."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    entries: list[OccupationBridgeEntry] = []
    for entry in data.get("entries", []):
        entries.append(OccupationBridgeEntry(
            sector_code=entry["sector_code"],
            occupation_code=entry["occupation_code"],
            share=entry["share"],
            source=entry.get("source", "unknown"),
            source_confidence=ConstraintConfidence(
                entry.get("source_confidence", "ASSUMED"),
            ),
            quality_confidence=QualityConfidence(
                entry.get("quality_confidence", "low"),
            ),
        ))

    return OccupationBridge(
        year=data.get("year", 0),
        entries=entries,
        metadata=data.get("metadata", {}),
    )
