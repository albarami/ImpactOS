"""Mapping Library Service — MVP-12.

Token-overlap fuzzy matching for line-item → sector mappings.
Deterministic, no LLM calls. Uses _text_utils for tokenization.

Key operations:
- add_entry: add or reinforce an existing mapping
- find_matches: fuzzy text match ranked by overlap * confidence * log(usage+1)
- publish_version: snapshot PUBLISHED entries into immutable version (Amendment 7)
- get_stats: aggregate statistics
"""

import math
from collections import Counter
from uuid import UUID

from src.libraries._text_utils import overlap_score, tokenize
from src.models.common import utc_now
from src.models.libraries import (
    EntryStatus,
    LibraryStats,
    MappingLibraryEntry,
    MappingLibraryVersion,
)


class MappingLibraryService:
    """In-memory mapping library service.

    Pre-tokenizes patterns for fast matching.
    """

    def __init__(self, entries: list[MappingLibraryEntry]) -> None:
        self._entries: list[MappingLibraryEntry] = list(entries)
        self._token_cache: list[tuple[MappingLibraryEntry, set[str]]] = [
            (e, tokenize(e.pattern)) for e in self._entries
        ]

    def add_entry(
        self, entry: MappingLibraryEntry,
    ) -> MappingLibraryEntry:
        """Add entry or increment usage if same pattern+sector exists."""
        for i, existing in enumerate(self._entries):
            if (
                existing.pattern.lower() == entry.pattern.lower()
                and existing.sector_code == entry.sector_code
            ):
                # Reinforce existing — only mutable fields (Amendment 2)
                updated = existing.model_copy(
                    update={
                        "usage_count": existing.usage_count + 1,
                        "last_used_at": utc_now(),
                    },
                )
                self._entries[i] = updated
                self._token_cache[i] = (updated, self._token_cache[i][1])
                return updated

        self._entries.append(entry)
        self._token_cache.append((entry, tokenize(entry.pattern)))
        return entry

    def find_matches(
        self,
        text: str,
        *,
        top_k: int = 10,
        min_score: float = 0.1,
    ) -> list[tuple[MappingLibraryEntry, float]]:
        """Token-overlap search.

        Score = overlap_recall * confidence * log2(usage_count + 2).
        Returns (entry, score) sorted descending by score.
        """
        query_tokens = tokenize(text)
        if not query_tokens:
            return []

        scored: list[tuple[MappingLibraryEntry, float]] = []
        for entry, pattern_tokens in self._token_cache:
            raw_overlap = overlap_score(query_tokens, pattern_tokens)
            if raw_overlap <= 0:
                continue
            # Weight by confidence and usage
            score = (
                raw_overlap
                * entry.confidence
                * math.log2(entry.usage_count + 2)
            )
            if score >= min_score:
                scored.append((entry, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def find_by_sector(
        self, sector_code: str,
    ) -> list[MappingLibraryEntry]:
        """Filter entries by sector code."""
        return [e for e in self._entries if e.sector_code == sector_code]

    def find_by_tags(
        self, tags: list[str],
    ) -> list[MappingLibraryEntry]:
        """Filter entries that have any of the given tags."""
        tag_set = set(tags)
        return [
            e for e in self._entries
            if tag_set & set(e.tags)
        ]

    def publish_version(
        self,
        *,
        workspace_id: UUID,
        published_by: UUID | None = None,
    ) -> MappingLibraryVersion:
        """Snapshot PUBLISHED entries into an immutable version.

        Amendment 7: Only entries with status=PUBLISHED are included.
        """
        published_entries = [
            e for e in self._entries
            if e.status == EntryStatus.PUBLISHED
        ]
        return MappingLibraryVersion(
            workspace_id=workspace_id,
            entry_ids=[e.entry_id for e in published_entries],
            entry_count=len(published_entries),
            published_by=published_by,
        )

    def get_stats(self) -> LibraryStats:
        """Compute aggregate statistics."""
        if not self._entries:
            return LibraryStats()

        total_usage = sum(e.usage_count for e in self._entries)
        avg_conf = sum(e.confidence for e in self._entries) / len(
            self._entries,
        )

        # Top sectors by entry count
        sector_counts: Counter[str] = Counter(
            e.sector_code for e in self._entries
        )
        top_sectors = [s for s, _ in sector_counts.most_common(10)]

        return LibraryStats(
            total_entries=len(self._entries),
            total_usage=total_usage,
            avg_confidence=round(avg_conf, 4),
            top_sectors=top_sectors,
        )

    def increment_usage(
        self, entry_id: UUID,
    ) -> MappingLibraryEntry | None:
        """Increment usage_count and update last_used_at (Amendment 2)."""
        for i, entry in enumerate(self._entries):
            if entry.entry_id == entry_id:
                updated = entry.model_copy(
                    update={
                        "usage_count": entry.usage_count + 1,
                        "last_used_at": utc_now(),
                    },
                )
                self._entries[i] = updated
                self._token_cache[i] = (updated, self._token_cache[i][1])
                return updated
        return None
