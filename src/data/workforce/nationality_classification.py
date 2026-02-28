"""Three-tier nationality classification (D-4 Task 4).

Classifies sector-occupation pairs as Saudi-ready / Saudi-trainable / Expat-reliant.
This is a DATASET. MVP-11 will later convert tiers to share ranges for analysis.

Amendment 2: No analysis methods — only data lookups and filtered views.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from src.data.workforce.unit_registry import QualityConfidence
from src.models.common import ConstraintConfidence


class NationalityTier(StrEnum):
    """Three-tier nationality feasibility classification."""

    SAUDI_READY = "saudi_ready"
    SAUDI_TRAINABLE = "saudi_trainable"
    EXPAT_RELIANT = "expat_reliant"


@dataclass(frozen=True)
class NationalityClassification:
    """Three-tier nationality feasibility for a sector-occupation pair."""

    sector_code: str
    occupation_code: str
    tier: NationalityTier
    current_saudi_pct: float | None
    rationale: str
    source_confidence: ConstraintConfidence
    quality_confidence: QualityConfidence
    sensitivity_range: tuple[str, str] | None
    source: str


@dataclass(frozen=True)
class ClassificationOverride:
    """Analyst override of a three-tier classification (Knowledge Flywheel hook)."""

    sector_code: str
    occupation_code: str
    original_tier: NationalityTier
    override_tier: NationalityTier
    overridden_by: str
    engagement_id: str | None
    rationale: str
    timestamp: str


@dataclass(frozen=True)
class NationalityClassificationSet:
    """Complete three-tier classification matrix.

    Section (A-T) x ISCO major group (0-9).
    """

    year: int
    classifications: list[NationalityClassification]
    metadata: dict[str, object] = field(default_factory=dict)

    def get_tier(
        self,
        sector_code: str,
        occupation_code: str,
    ) -> NationalityClassification | None:
        """Look up classification for a sector-occupation pair."""
        for c in self.classifications:
            if c.sector_code == sector_code and c.occupation_code == occupation_code:
                return c
        return None

    def get_sector_summary(self, sector_code: str) -> dict[str, int]:
        """Count of each tier for a sector across all occupations."""
        counts: dict[str, int] = {t.value: 0 for t in NationalityTier}
        for c in self.classifications:
            if c.sector_code == sector_code:
                counts[c.tier.value] += 1
        return counts

    def get_trainable_entries(self) -> list[NationalityClassification]:
        """Return all saudi_trainable entries (Amendment 2: pure data query).

        Sorted by current_saudi_pct ascending (largest gap first) where known.
        Entries without current_saudi_pct appear at the end.
        """
        trainable = [
            c for c in self.classifications
            if c.tier == NationalityTier.SAUDI_TRAINABLE
        ]
        return sorted(
            trainable,
            key=lambda c: (c.current_saudi_pct is None, c.current_saudi_pct or 1.0),
        )

    def apply_overrides(
        self,
        overrides: list[ClassificationOverride],
    ) -> NationalityClassificationSet:
        """Apply overrides, producing a NEW set. Original is unchanged.

        This is the Knowledge Flywheel hook for MVP-12.
        """
        override_map: dict[tuple[str, str], ClassificationOverride] = {
            (o.sector_code, o.occupation_code): o for o in overrides
        }

        new_classifications: list[NationalityClassification] = []
        for c in self.classifications:
            key = (c.sector_code, c.occupation_code)
            if key in override_map:
                ov = override_map[key]
                new_classifications.append(
                    NationalityClassification(
                        sector_code=c.sector_code,
                        occupation_code=c.occupation_code,
                        tier=ov.override_tier,
                        current_saudi_pct=c.current_saudi_pct,
                        rationale=f"Override: {ov.rationale}",
                        source_confidence=ConstraintConfidence.ESTIMATED,
                        quality_confidence=c.quality_confidence,
                        sensitivity_range=c.sensitivity_range,
                        source=f"override_by_{ov.overridden_by}",
                    )
                )
            else:
                new_classifications.append(c)

        new_meta = dict(self.metadata)
        new_meta["overrides_applied"] = len(overrides)

        return NationalityClassificationSet(
            year=self.year,
            classifications=new_classifications,
            metadata=new_meta,
        )
