"""Tests for MappingLibraryService (MVP-12).

Token-overlap fuzzy matching, publishing, stats, usage tracking.
Amendment 8: scoring guardrails (min tokens, stopwords, Arabic normalization).
"""

import math

import pytest
from uuid_extensions import uuid7

from src.libraries._text_utils import (
    MIN_MATCH_TOKENS,
    normalize_arabic,
    overlap_score,
    tokenize,
)
from src.models.libraries import (
    EntryStatus,
    MappingLibraryEntry,
)


# ---------------------------------------------------------------------------
# Text Utils
# ---------------------------------------------------------------------------


class TestTokenize:
    def test_basic_tokenization(self) -> None:
        tokens = tokenize("concrete reinforcement works")
        assert "concrete" in tokens
        assert "reinforcement" in tokens
        # "works" is a consulting stopword
        assert "works" not in tokens

    def test_stop_words_removed(self) -> None:
        tokens = tokenize("supply of general items for the project")
        # "supply", "general", "items" are consulting stops
        # "of", "for", "the" are general stops
        assert "supply" not in tokens
        assert "general" not in tokens
        assert "items" not in tokens
        assert "project" in tokens

    def test_min_token_length(self) -> None:
        tokens = tokenize("IT is a big deal")
        # "IT" → "it" (2 chars, below min 3)
        # "is", "a" are stop words and short
        assert "it" not in tokens
        assert "big" in tokens
        assert "deal" in tokens

    def test_empty_input(self) -> None:
        assert tokenize("") == set()

    def test_case_insensitive(self) -> None:
        tokens = tokenize("Concrete WORKS Reinforcement")
        assert "concrete" in tokens
        assert "reinforcement" in tokens

    def test_arabic_normalization(self) -> None:
        """Amendment 8: Arabic normalization hooks."""
        # Alef variants
        assert normalize_arabic("\u0623\u0645\u0631") == "\u0627\u0645\u0631"  # أمر → امر
        # Ya variant
        assert normalize_arabic("\u0639\u0644\u0649") == "\u0639\u0644\u064a"  # على → علي
        # Tatweel removal
        assert normalize_arabic("\u0639\u0640\u0644\u0645") == "\u0639\u0644\u0645"

    def test_arabic_tokens(self) -> None:
        tokens = tokenize("\u0623\u0639\u0645\u0627\u0644 \u0627\u0644\u062e\u0631\u0633\u0627\u0646\u0629")
        # Should produce normalized Arabic tokens
        assert len(tokens) >= 1


class TestOverlapScore:
    def test_exact_match(self) -> None:
        tokens = {"concrete", "reinforcement", "works"}
        score = overlap_score(tokens, tokens)
        assert score == 1.0

    def test_partial_overlap(self) -> None:
        query = {"concrete", "steel", "works"}
        pattern = {"concrete", "reinforcement", "works"}
        score = overlap_score(query, pattern)
        assert abs(score - 2.0 / 3.0) < 1e-6

    def test_no_overlap(self) -> None:
        query = {"electrical", "wiring", "cables"}
        pattern = {"concrete", "reinforcement", "works"}
        score = overlap_score(query, pattern)
        assert score == 0.0

    def test_min_tokens_guard(self) -> None:
        """Amendment 8: min 2 tokens required."""
        query = {"concrete"}
        pattern = {"concrete", "reinforcement", "works"}
        score = overlap_score(query, pattern)
        assert score == 0.0  # query has < MIN_MATCH_TOKENS

    def test_empty_sets(self) -> None:
        assert overlap_score(set(), set()) == 0.0


# ---------------------------------------------------------------------------
# MappingLibraryService
# ---------------------------------------------------------------------------


class TestMappingLibraryService:
    def _make_entry(
        self,
        pattern: str = "concrete works reinforcement",
        sector: str = "F",
        confidence: float = 0.9,
        tags: list[str] | None = None,
        usage: int = 0,
        status: EntryStatus = EntryStatus.PUBLISHED,
    ) -> MappingLibraryEntry:
        return MappingLibraryEntry(
            workspace_id=uuid7(),
            pattern=pattern,
            sector_code=sector,
            confidence=confidence,
            tags=tags or [],
            usage_count=usage,
            status=status,
        )

    def test_add_entry(self) -> None:
        from src.libraries.mapping_library import MappingLibraryService

        svc = MappingLibraryService([])
        entry = self._make_entry()
        result = svc.add_entry(entry)
        assert result.entry_id == entry.entry_id
        assert len(svc._entries) == 1

    def test_add_duplicate_pattern_increments_usage(self) -> None:
        from src.libraries.mapping_library import MappingLibraryService

        e1 = self._make_entry(pattern="concrete reinforcement", sector="F")
        svc = MappingLibraryService([e1])
        e2 = self._make_entry(pattern="concrete reinforcement", sector="F")
        result = svc.add_entry(e2)
        # Should increment existing rather than add new
        assert len(svc._entries) == 1
        assert svc._entries[0].usage_count == 1

    def test_find_matches_basic(self) -> None:
        from src.libraries.mapping_library import MappingLibraryService

        entries = [
            self._make_entry("concrete reinforcement steel", "F", 0.9, usage=5),
            self._make_entry("electrical wiring installation", "D", 0.85, usage=3),
        ]
        svc = MappingLibraryService(entries)
        matches = svc.find_matches("concrete reinforcement building")
        assert len(matches) >= 1
        assert matches[0][0].sector_code == "F"

    def test_find_matches_empty_library(self) -> None:
        from src.libraries.mapping_library import MappingLibraryService

        svc = MappingLibraryService([])
        assert svc.find_matches("concrete works") == []

    def test_find_matches_no_results(self) -> None:
        from src.libraries.mapping_library import MappingLibraryService

        entries = [self._make_entry("concrete reinforcement steel", "F")]
        svc = MappingLibraryService(entries)
        # Completely unrelated query
        matches = svc.find_matches("financial consulting advisory")
        assert all(score < 0.01 for _, score in matches) or len(matches) == 0

    def test_find_matches_top_k_limit(self) -> None:
        from src.libraries.mapping_library import MappingLibraryService

        entries = [
            self._make_entry(f"concrete type variant {i}", "F")
            for i in range(20)
        ]
        svc = MappingLibraryService(entries)
        matches = svc.find_matches("concrete type variant", top_k=3)
        assert len(matches) <= 3

    def test_find_matches_min_score_filter(self) -> None:
        from src.libraries.mapping_library import MappingLibraryService

        entries = [
            self._make_entry("concrete reinforcement steel", "F"),
        ]
        svc = MappingLibraryService(entries)
        matches = svc.find_matches(
            "concrete steel pipes", min_score=0.99,
        )
        # Very high threshold should filter out partial matches
        assert len(matches) == 0

    def test_find_matches_scoring_order(self) -> None:
        from src.libraries.mapping_library import MappingLibraryService

        entries = [
            self._make_entry("electrical wiring cables", "D", 0.7, usage=1),
            self._make_entry(
                "concrete reinforcement steel", "F", 0.95, usage=10,
            ),
        ]
        svc = MappingLibraryService(entries)
        matches = svc.find_matches("concrete reinforcement building")
        if len(matches) >= 2:
            assert matches[0][1] >= matches[1][1]

    def test_find_by_sector(self) -> None:
        from src.libraries.mapping_library import MappingLibraryService

        entries = [
            self._make_entry("concrete reinforcement", "F"),
            self._make_entry("electrical wiring", "D"),
            self._make_entry("steel fabrication", "F"),
        ]
        svc = MappingLibraryService(entries)
        results = svc.find_by_sector("F")
        assert len(results) == 2
        assert all(e.sector_code == "F" for e in results)

    def test_find_by_sector_not_found(self) -> None:
        from src.libraries.mapping_library import MappingLibraryService

        svc = MappingLibraryService([self._make_entry()])
        assert svc.find_by_sector("Z") == []

    def test_find_by_tags(self) -> None:
        from src.libraries.mapping_library import MappingLibraryService

        entries = [
            self._make_entry("concrete works", "F", tags=["construction"]),
            self._make_entry("IT consulting", "J", tags=["IT", "consulting"]),
        ]
        svc = MappingLibraryService(entries)
        results = svc.find_by_tags(["construction"])
        assert len(results) == 1
        assert results[0].sector_code == "F"

    def test_find_by_tags_no_match(self) -> None:
        from src.libraries.mapping_library import MappingLibraryService

        entries = [self._make_entry(tags=["construction"])]
        svc = MappingLibraryService(entries)
        assert svc.find_by_tags(["automotive"]) == []

    def test_publish_version_captures_published_entries(self) -> None:
        """Amendment 7: Only PUBLISHED entries in version snapshot."""
        from src.libraries.mapping_library import MappingLibraryService

        ws = uuid7()
        entries = [
            self._make_entry(
                "concrete", "F", status=EntryStatus.PUBLISHED,
            ),
            self._make_entry(
                "electrical", "D", status=EntryStatus.DRAFT,
            ),
        ]
        # Force same workspace
        for e in entries:
            e.workspace_id = ws
        svc = MappingLibraryService(entries)
        version = svc.publish_version(workspace_id=ws)
        assert version.entry_count == 1  # Only PUBLISHED
        assert len(version.entry_ids) == 1

    def test_publish_version_immutable(self) -> None:
        from src.libraries.mapping_library import MappingLibraryService

        ws = uuid7()
        svc = MappingLibraryService([])
        version = svc.publish_version(workspace_id=ws)
        with pytest.raises(Exception):
            version.version = 99  # type: ignore[misc]

    def test_get_stats_empty(self) -> None:
        from src.libraries.mapping_library import MappingLibraryService

        svc = MappingLibraryService([])
        stats = svc.get_stats()
        assert stats.total_entries == 0
        assert stats.total_usage == 0
        assert stats.avg_confidence == 0.0

    def test_get_stats_populated(self) -> None:
        from src.libraries.mapping_library import MappingLibraryService

        entries = [
            self._make_entry("concrete", "F", 0.9, usage=10),
            self._make_entry("steel", "F", 0.8, usage=5),
            self._make_entry("electrical", "D", 0.7, usage=2),
        ]
        svc = MappingLibraryService(entries)
        stats = svc.get_stats()
        assert stats.total_entries == 3
        assert stats.total_usage == 17
        assert abs(stats.avg_confidence - 0.8) < 0.01
        assert stats.top_sectors[0] == "F"  # Most entries

    def test_increment_usage_existing(self) -> None:
        from src.libraries.mapping_library import MappingLibraryService

        entry = self._make_entry(usage=5)
        svc = MappingLibraryService([entry])
        result = svc.increment_usage(entry.entry_id)
        assert result is not None
        assert result.usage_count == 6
        assert result.last_used_at is not None

    def test_increment_usage_nonexistent(self) -> None:
        from src.libraries.mapping_library import MappingLibraryService

        svc = MappingLibraryService([])
        assert svc.increment_usage(uuid7()) is None
