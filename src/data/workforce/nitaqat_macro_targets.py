"""Nitaqat macro-level Saudization targets — Layer B (D-4 Task 3).

Simplified sector-level targets derived from the rule catalog.
Suitable for macro-level workforce analysis.

Does NOT capture firm-level nuance (company size bands, salary weighting,
disability multipliers). See nitaqat_rules.py for the full catalog.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.data.workforce.unit_registry import QualityConfidence
from src.models.common import ConstraintConfidence


@dataclass(frozen=True)
class SectorSaudizationTarget:
    """Simplified macro-level Saudization target for a sector.

    This is a DERIVED simplification of the rule catalog.
    """

    sector_code: str
    effective_target_pct: float
    target_range_low: float
    target_range_high: float
    derivation: str
    applicable_rules: list[str]
    source_confidence: ConstraintConfidence
    quality_confidence: QualityConfidence
    notes: str | None = None


@dataclass(frozen=True)
class MacroSaudizationTargets:
    """Sector-level Saudization targets for macro analysis.

    Amendment 6: Sectors may have None targets where not applicable.
    """

    targets: dict[str, SectorSaudizationTarget | None]
    effective_as_of: str
    metadata: dict[str, object] = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)

    def get_target(
        self, sector_code: str,
    ) -> SectorSaudizationTarget | None:
        """Get target for a sector. Returns None for not-applicable sectors."""
        return self.targets.get(sector_code)

    def get_all_applicable(self) -> dict[str, SectorSaudizationTarget]:
        """Get only sectors with non-null targets."""
        return {k: v for k, v in self.targets.items() if v is not None}

    @property
    def sector_codes(self) -> list[str]:
        """All sector codes accounted for (including null targets)."""
        return sorted(self.targets.keys())
