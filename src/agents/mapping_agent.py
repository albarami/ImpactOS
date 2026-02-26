"""Mapping suggestion agent — MVP-8.

Given a BoQLineItem text + sector taxonomy, propose sector_code with
confidence score (0-1) and short explanation. Uses the mapping library
for few-shot examples and keyword matching. Batch multiple line items
for efficiency.

CRITICAL: Agent NEVER produces economic numbers. Output is validated
MappingSuggestion objects (Pydantic) — mappings only.
"""

from dataclasses import dataclass, field
from uuid import UUID

from pydantic import BaseModel, Field

from src.models.document import BoQLineItem
from src.models.mapping import MappingLibraryEntry


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------


class MappingSuggestion(BaseModel):
    """A single mapping suggestion for a line item."""

    line_item_id: UUID
    sector_code: str
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str


class MappingSuggestionBatch(BaseModel):
    """Batch of mapping suggestions."""

    suggestions: list[MappingSuggestion] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Tokenization helper
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "for", "in", "to", "on",
    "with", "at", "by", "from", "is", "are", "was", "were",
})


def _tokenize(text: str) -> set[str]:
    """Lowercase tokenize, strip stop words and short tokens."""
    words = set()
    for w in text.lower().split():
        cleaned = "".join(c for c in w if c.isalnum())
        if cleaned and len(cleaned) > 1 and cleaned not in _STOP_WORDS:
            words.add(cleaned)
    return words


def _overlap_score(item_tokens: set[str], pattern_tokens: set[str]) -> float:
    """Compute pattern recall: fraction of pattern tokens found in item.

    Uses recall (not Jaccard) so that an exact pattern match scores 1.0
    even when the item has additional tokens from descriptions.
    """
    if not item_tokens or not pattern_tokens:
        return 0.0
    matched = item_tokens & pattern_tokens
    return len(matched) / len(pattern_tokens)


# ---------------------------------------------------------------------------
# Mapping suggestion agent
# ---------------------------------------------------------------------------


class MappingSuggestionAgent:
    """Propose sector mappings for BoQ line items.

    Uses library pattern matching for deterministic suggestions.
    LLM-assisted mode extends this with AI calls via LLMClient.
    """

    def __init__(
        self,
        library: list[MappingLibraryEntry] | None = None,
    ) -> None:
        self._library = library or []
        self._library_tokens: list[tuple[MappingLibraryEntry, set[str]]] = [
            (entry, _tokenize(entry.pattern))
            for entry in self._library
        ]

    # ----- Single item suggestion -----

    def suggest_one(
        self,
        item: BoQLineItem,
        *,
        taxonomy: list[dict],
    ) -> MappingSuggestion:
        """Suggest a sector mapping for a single line item."""
        item_tokens = _tokenize(item.raw_text) | _tokenize(item.description)

        # Score all library entries by overlap
        scored: list[tuple[MappingLibraryEntry, float]] = []
        for entry, entry_tokens in self._library_tokens:
            overlap = _overlap_score(item_tokens, entry_tokens)
            if overlap > 0:
                # Weight by library confidence
                score = overlap * entry.confidence
                scored.append((entry, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        if scored and scored[0][1] > 0.1:
            best_entry, best_score = scored[0]
            confidence = min(best_score * 1.2, 1.0)  # Scale up slightly
            return MappingSuggestion(
                line_item_id=item.line_item_id,
                sector_code=best_entry.sector_code,
                confidence=round(confidence, 3),
                explanation=f"Matched library pattern '{best_entry.pattern}' → sector {best_entry.sector_code}",
            )

        # No good match — pick first taxonomy entry with low confidence
        fallback_code = taxonomy[0]["sector_code"] if taxonomy else "UNKNOWN"
        return MappingSuggestion(
            line_item_id=item.line_item_id,
            sector_code=fallback_code,
            confidence=0.1,
            explanation="No strong library match found; requires manual review.",
        )

    # ----- Batch suggestion -----

    def suggest_batch(
        self,
        items: list[BoQLineItem],
        *,
        taxonomy: list[dict],
    ) -> MappingSuggestionBatch:
        """Suggest mappings for multiple line items."""
        suggestions = [
            self.suggest_one(item, taxonomy=taxonomy)
            for item in items
        ]
        return MappingSuggestionBatch(suggestions=suggestions)

    # ----- Few-shot examples -----

    def get_few_shot_examples(
        self,
        text: str,
        top_k: int = 5,
    ) -> list[MappingLibraryEntry]:
        """Retrieve top-k library entries most relevant to the given text."""
        text_tokens = _tokenize(text)
        scored: list[tuple[MappingLibraryEntry, float]] = []

        for entry, entry_tokens in self._library_tokens:
            overlap = _overlap_score(text_tokens, entry_tokens)
            if overlap > 0:
                scored.append((entry, overlap))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [entry for entry, _ in scored[:top_k]]

    # ----- LLM prompt construction -----

    def build_mapping_prompt(
        self,
        item: BoQLineItem,
        *,
        taxonomy: list[dict],
    ) -> str:
        """Build a mapping prompt for LLM-assisted suggestion."""
        # Get few-shot examples
        examples = self.get_few_shot_examples(item.raw_text, top_k=3)

        lines = [
            "You are a sector mapping assistant for economic impact modeling.",
            "Given a procurement line item, assign the most appropriate sector code.",
            "",
            "Available sectors:",
        ]

        for sector in taxonomy:
            lines.append(f"  {sector['sector_code']}: {sector['sector_name']}")

        if examples:
            lines.append("")
            lines.append("Examples from mapping library:")
            for ex in examples:
                lines.append(
                    f"  \"{ex.pattern}\" → {ex.sector_code} "
                    f"(confidence: {ex.confidence})"
                )

        lines.append("")
        lines.append(f"Line item text: \"{item.raw_text}\"")
        if item.description and item.description != item.raw_text:
            lines.append(f"Description: \"{item.description}\"")

        lines.append("")
        lines.append(
            "Respond with JSON: "
            '{"sector_code": "X", "confidence": 0.XX, "explanation": "..."}'
        )

        return "\n".join(lines)
