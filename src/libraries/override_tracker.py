"""Override Tracker — MVP-12.

Wraps existing OverridePair from src/compiler/learning.py.
Computes accuracy metrics, override frequency, and promotes
high-confidence overrides to mapping library entries.
"""

from collections import Counter, defaultdict
from uuid import UUID

from src.compiler.learning import OverridePair
from src.models.libraries import (
    EntryStatus,
    MappingLibraryEntry,
    OverrideAccuracyReport,
)


class OverrideTracker:
    """Track override frequency and compute suggestion accuracy."""

    def __init__(self, overrides: list[OverridePair]) -> None:
        self._overrides = list(overrides)

    def compute_accuracy(self) -> OverrideAccuracyReport:
        """Compute overall and per-sector accuracy."""
        if not self._overrides:
            return OverrideAccuracyReport()

        total = len(self._overrides)
        correct = sum(1 for p in self._overrides if p.was_correct)
        incorrect = total - correct

        # Per-sector breakdown
        by_sector: dict[str, dict] = {}
        sector_groups: dict[str, list[OverridePair]] = defaultdict(list)
        for p in self._overrides:
            sector_groups[p.suggested_sector_code].append(p)

        for sector, pairs in sector_groups.items():
            s_total = len(pairs)
            s_correct = sum(1 for p in pairs if p.was_correct)
            by_sector[sector] = {
                "total": s_total,
                "correct": s_correct,
                "accuracy": round(s_correct / s_total, 4) if s_total else 0.0,
            }

        # High-confidence overrides (text→final seen multiple times)
        hc = self.get_high_confidence_overrides(min_count=3)
        hc_list = [
            {"pattern": text, "final_sector": sector, "count": count}
            for text, sector, count in hc
        ]

        return OverrideAccuracyReport(
            total_suggestions=total,
            accepted_count=correct,
            overridden_count=incorrect,
            accuracy_pct=round(correct / total, 4),
            by_sector=by_sector,
            high_confidence_overrides=hc_list,
        )

    def get_high_confidence_overrides(
        self,
        *,
        min_count: int = 3,
    ) -> list[tuple[str, str, int]]:
        """Overrides seen >= min_count times.

        Returns (line_item_text, final_sector, count).
        Only includes actual overrides (not correct suggestions).
        """
        counter: Counter[tuple[str, str]] = Counter()
        for p in self._overrides:
            if not p.was_correct:
                counter[(p.line_item_text, p.final_sector_code)] += 1

        return [
            (text, sector, count)
            for (text, sector), count in counter.most_common()
            if count >= min_count
        ]

    def get_override_frequency(self) -> dict[str, dict[str, int]]:
        """suggested_sector → {final_sector → count}."""
        result: dict[str, dict[str, int]] = {}
        for p in self._overrides:
            if not p.was_correct:
                if p.suggested_sector_code not in result:
                    result[p.suggested_sector_code] = {}
                bucket = result[p.suggested_sector_code]
                bucket[p.final_sector_code] = (
                    bucket.get(p.final_sector_code, 0) + 1
                )
        return result

    def promote_to_mapping_library(
        self,
        *,
        min_count: int = 3,
        workspace_id: UUID,
    ) -> list[MappingLibraryEntry]:
        """Generate library entries from high-confidence repeat overrides.

        Confidence = min(0.95, 0.7 + 0.05 * count).
        Entries start as DRAFT (Amendment 7).
        """
        hc = self.get_high_confidence_overrides(min_count=min_count)
        entries: list[MappingLibraryEntry] = []
        for text, sector, count in hc:
            confidence = min(0.95, 0.7 + 0.05 * count)
            entry = MappingLibraryEntry(
                workspace_id=workspace_id,
                pattern=text,
                sector_code=sector,
                confidence=round(confidence, 4),
                usage_count=count,
                status=EntryStatus.DRAFT,
            )
            entries.append(entry)
        return entries
