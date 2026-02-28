"""Scenario Pattern Library Service — MVP-12.

Stores reusable scenario templates from engagement learnings.
Finding uses sector/shock type overlap scoring.
"""

from collections import Counter
from uuid import UUID

from src.models.libraries import LibraryStats, ScenarioPattern


class ScenarioPatternService:
    """In-memory scenario pattern service."""

    def __init__(self, patterns: list[ScenarioPattern]) -> None:
        self._patterns: list[ScenarioPattern] = list(patterns)

    def add_pattern(
        self, pattern: ScenarioPattern,
    ) -> ScenarioPattern:
        """Add a scenario pattern to the library."""
        self._patterns.append(pattern)
        return pattern

    def find_patterns(
        self,
        *,
        sector_codes: list[str] | None = None,
        shock_types: list[str] | None = None,
        tags: list[str] | None = None,
        top_k: int = 10,
    ) -> list[ScenarioPattern]:
        """Find patterns matching filters.

        Score by sector overlap + shock type overlap + tag overlap.
        If no filters, return all (up to top_k).
        """
        no_filter = (
            sector_codes is None
            and shock_types is None
            and tags is None
        )
        if no_filter:
            return self._patterns[:top_k]

        sector_set = set(sector_codes) if sector_codes else set()
        shock_set = set(shock_types) if shock_types else set()
        tag_set = set(tags) if tags else set()

        scored: list[tuple[ScenarioPattern, float]] = []
        for p in self._patterns:
            score = 0.0
            if sector_set:
                overlap = len(sector_set & set(p.sector_focus))
                if overlap == 0:
                    continue
                score += overlap / len(sector_set)
            if shock_set:
                overlap = len(shock_set & set(p.typical_shock_types))
                if overlap == 0 and not sector_set:
                    continue
                score += overlap / len(shock_set) if shock_set else 0
            if tag_set:
                overlap = len(tag_set & set(p.tags))
                score += overlap / len(tag_set) if tag_set else 0

            if score > 0:
                scored.append((p, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [p for p, _ in scored[:top_k]]

    def get_stats(self) -> LibraryStats:
        """Compute aggregate statistics."""
        if not self._patterns:
            return LibraryStats()

        total_usage = sum(p.usage_count for p in self._patterns)
        sector_counts: Counter[str] = Counter()
        for p in self._patterns:
            for s in p.sector_focus:
                sector_counts[s] += 1

        return LibraryStats(
            total_entries=len(self._patterns),
            total_usage=total_usage,
            top_sectors=[s for s, _ in sector_counts.most_common(10)],
        )

    def increment_usage(
        self, pattern_id: UUID,
    ) -> ScenarioPattern | None:
        """Increment usage_count on a pattern."""
        for i, p in enumerate(self._patterns):
            if p.pattern_id == pattern_id:
                updated = p.model_copy(
                    update={"usage_count": p.usage_count + 1},
                )
                self._patterns[i] = updated
                return updated
        return None
