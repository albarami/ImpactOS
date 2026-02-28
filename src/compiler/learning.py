"""Learning loop — MVP-8 Section 9.6.

Store analyst override pairs (suggested → final) with context.
Retrieve relevant overrides as few-shot examples for future mapping
suggestions. Track suggestion accuracy over time.

Analyst overrides are training signals — used to improve mapping
suggestions in later engagements.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from uuid import UUID

from pydantic import BaseModel, Field
from uuid_extensions import uuid7

from src.models.common import utc_now
from src.models.mapping import MappingLibraryEntry


# ---------------------------------------------------------------------------
# Tokenization (reuse pattern from mapping agent)
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "for", "in", "to", "on",
    "with", "at", "by", "from", "is", "are", "was", "were",
})


def _tokenize(text: str) -> set[str]:
    words = set()
    for w in text.lower().split():
        cleaned = "".join(c for c in w if c.isalnum())
        if cleaned and len(cleaned) > 1 and cleaned not in _STOP_WORDS:
            words.add(cleaned)
    return words


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class OverridePair(BaseModel):
    """An analyst override pair: suggested → final with context."""

    override_id: UUID = Field(default_factory=uuid7)
    engagement_id: UUID
    line_item_id: UUID
    line_item_text: str
    suggested_sector_code: str
    final_sector_code: str
    project_type: str = ""
    actor: UUID | None = None

    @property
    def was_correct(self) -> bool:
        """Was the AI suggestion correct (accepted without change)?"""
        return self.suggested_sector_code == self.final_sector_code


@dataclass
class AccuracyMetrics:
    """Accuracy metrics for suggestion quality."""

    total: int = 0
    correct: int = 0
    incorrect: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total > 0 else 0.0


# ---------------------------------------------------------------------------
# Learning loop
# ---------------------------------------------------------------------------


class LearningLoop:
    """Store and retrieve analyst overrides for continuous improvement."""

    def __init__(self) -> None:
        self._overrides: list[OverridePair] = []
        self._override_tokens: list[tuple[OverridePair, set[str]]] = []

    def record_override(self, pair: OverridePair) -> None:
        """Record an analyst override pair."""
        self._overrides.append(pair)
        self._override_tokens.append((pair, _tokenize(pair.line_item_text)))

    def total_overrides(self) -> int:
        return len(self._overrides)

    # ----- Retrieval -----

    def get_relevant_examples(
        self,
        text: str,
        *,
        top_k: int = 5,
        project_type: str | None = None,
    ) -> list[OverridePair]:
        """Retrieve top-k override pairs most relevant to given text."""
        query_tokens = _tokenize(text)
        if not query_tokens:
            return []

        scored: list[tuple[OverridePair, float]] = []
        for pair, pair_tokens in self._override_tokens:
            if not pair_tokens:
                continue
            matched = query_tokens & pair_tokens
            score = len(matched) / len(pair_tokens)
            # Boost if project type matches
            if project_type and pair.project_type == project_type:
                score += 0.2
            if score > 0:
                scored.append((pair, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [pair for pair, _ in scored[:top_k]]

    # ----- Accuracy tracking -----

    def compute_accuracy(self) -> AccuracyMetrics:
        """Compute overall suggestion accuracy."""
        total = len(self._overrides)
        correct = sum(1 for p in self._overrides if p.was_correct)
        return AccuracyMetrics(
            total=total,
            correct=correct,
            incorrect=total - correct,
        )

    def accuracy_by_sector(self) -> dict[str, AccuracyMetrics]:
        """Compute accuracy broken down by suggested sector."""
        by_sector: dict[str, list[OverridePair]] = defaultdict(list)
        for p in self._overrides:
            by_sector[p.suggested_sector_code].append(p)

        result: dict[str, AccuracyMetrics] = {}
        for sector, pairs in by_sector.items():
            total = len(pairs)
            correct = sum(1 for p in pairs if p.was_correct)
            result[sector] = AccuracyMetrics(
                total=total,
                correct=correct,
                incorrect=total - correct,
            )
        return result

    # ----- Flywheel integration (Task 6) -----

    def extract_new_patterns(
        self,
        overrides: list[OverridePair],
        existing_library: list[MappingLibraryEntry],
        min_frequency: int = 2,
    ) -> list[MappingLibraryEntry]:
        """Extract new mapping patterns from analyst overrides.

        Logic:
        - Group overrides by final_sector_code
        - For each group, use the most common line_item_text as the pattern
        - Patterns appearing >= min_frequency become new entries
        - Confidence = fraction of correct suggestions in that group
        - New entries must NOT duplicate existing library entries
          (check by pattern text + sector_code)
        """
        if not overrides:
            return []

        # Build set of existing (pattern, sector_code) for dedup
        existing_keys: set[tuple[str, str]] = {
            (e.pattern, e.sector_code) for e in existing_library
        }

        # Group overrides by final_sector_code
        by_sector: dict[str, list[OverridePair]] = defaultdict(list)
        for ovr in overrides:
            by_sector[ovr.final_sector_code].append(ovr)

        new_entries: list[MappingLibraryEntry] = []
        for sector_code, group in by_sector.items():
            if len(group) < min_frequency:
                continue

            # Most common line_item_text as the pattern
            text_counts: Counter[str] = Counter(ovr.line_item_text for ovr in group)
            most_common_text, _count = text_counts.most_common(1)[0]

            # Skip if this (pattern, sector) already exists
            if (most_common_text, sector_code) in existing_keys:
                continue

            # Confidence = fraction of correct suggestions in this group
            correct = sum(1 for ovr in group if ovr.was_correct)
            confidence = correct / len(group)

            new_entries.append(
                MappingLibraryEntry(
                    pattern=most_common_text,
                    sector_code=sector_code,
                    confidence=confidence,
                )
            )

        return new_entries

    def update_confidence_scores(
        self,
        overrides: list[OverridePair],
        existing_entries: list[MappingLibraryEntry],
    ) -> list[MappingLibraryEntry]:
        """Update confidence scores for existing patterns based on override accuracy.

        For each existing entry:
        - Find overrides where the suggestion matched this entry's sector_code
        - If >= 1 relevant override: new_confidence = (old_confidence + override_accuracy) / 2
        - If no relevant overrides: keep original confidence
        - Return NEW list of entries (don't modify originals)
        """
        # Group overrides by suggested_sector_code for fast lookup
        by_suggested: dict[str, list[OverridePair]] = defaultdict(list)
        for ovr in overrides:
            by_suggested[ovr.suggested_sector_code].append(ovr)

        updated: list[MappingLibraryEntry] = []
        for entry in existing_entries:
            relevant = by_suggested.get(entry.sector_code, [])
            if relevant:
                correct = sum(1 for ovr in relevant if ovr.was_correct)
                override_accuracy = correct / len(relevant)
                new_confidence = (entry.confidence + override_accuracy) / 2.0
                updated.append(
                    MappingLibraryEntry(
                        entry_id=entry.entry_id,
                        pattern=entry.pattern,
                        sector_code=entry.sector_code,
                        confidence=new_confidence,
                        usage_count=entry.usage_count,
                        created_at=entry.created_at,
                    )
                )
            else:
                # No relevant overrides, copy with same values (new object)
                updated.append(
                    MappingLibraryEntry(
                        entry_id=entry.entry_id,
                        pattern=entry.pattern,
                        sector_code=entry.sector_code,
                        confidence=entry.confidence,
                        usage_count=entry.usage_count,
                        created_at=entry.created_at,
                    )
                )

        return updated
