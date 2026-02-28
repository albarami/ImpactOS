"""Sector-to-occupation bridge matrix (D-4 Task 2).

Maps ISIC Rev.4 sections (A-T) to ISCO-08 major occupation groups (0-9).
Section-level only for v1 — do not accept division codes.

This is a DATASET for MVP-11 to consume. It does not perform
runtime workforce analysis.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.data.workforce.unit_registry import QualityConfidence
from src.models.common import ConstraintConfidence

# Valid ISCO-08 major group codes
ISCO08_MAJOR_GROUPS = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9"}


@dataclass(frozen=True)
class OccupationBridgeEntry:
    """Share of occupation within a sector's total employment."""

    sector_code: str
    occupation_code: str
    share: float
    source: str
    source_confidence: ConstraintConfidence
    quality_confidence: QualityConfidence


@dataclass(frozen=True)
class OccupationBridge:
    """Complete sector-to-occupation bridge matrix (20 sections x 10 major groups).

    Section-level only (A-T) for v1.
    """

    year: int
    entries: list[OccupationBridgeEntry]
    metadata: dict[str, object]

    def get_occupation_shares(self, sector_code: str) -> dict[str, float]:
        """Get occupation distribution for a sector. Shares sum to ~1.0."""
        return {
            e.occupation_code: e.share
            for e in self.entries
            if e.sector_code == sector_code
        }

    def get_sectors(self) -> list[str]:
        """Get unique sector codes present in the bridge."""
        seen: set[str] = set()
        result: list[str] = []
        for e in self.entries:
            if e.sector_code not in seen:
                seen.add(e.sector_code)
                result.append(e.sector_code)
        return result

    def validate(self) -> list[str]:
        """Check all sectors have shares summing to ~1.0 (tolerance 0.001).

        Also validates occupation codes are valid ISCO-08 major groups.
        Returns list of validation error messages (empty = valid).
        """
        errors: list[str] = []

        # Check occupation codes
        for e in self.entries:
            if e.occupation_code not in ISCO08_MAJOR_GROUPS:
                errors.append(
                    f"Invalid ISCO-08 code '{e.occupation_code}' "
                    f"for sector {e.sector_code}"
                )

        # Check share sums
        sector_sums: dict[str, float] = {}
        for e in self.entries:
            sector_sums[e.sector_code] = (
                sector_sums.get(e.sector_code, 0.0) + e.share
            )

        for sector, total in sorted(sector_sums.items()):
            if abs(total - 1.0) > 0.001:
                errors.append(
                    f"Sector {sector}: shares sum to {total:.4f}, expected ~1.0"
                )

        return errors
