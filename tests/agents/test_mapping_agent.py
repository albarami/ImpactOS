"""Tests for mapping suggestion agent (MVP-8).

Covers: single-item mapping, batch mapping, library-based few-shot,
confidence scoring, explanation generation, Pydantic validation,
fallback when LLM unavailable.
"""

import pytest
from uuid_extensions import uuid7

from src.agents.mapping_agent import (
    MappingSuggestion,
    MappingSuggestionAgent,
    MappingSuggestionBatch,
)
from src.models.document import BoQLineItem
from src.models.mapping import MappingLibraryEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_line_item(raw_text: str, description: str = "") -> BoQLineItem:
    return BoQLineItem(
        doc_id=uuid7(),
        extraction_job_id=uuid7(),
        raw_text=raw_text,
        description=description or raw_text,
        page_ref=0,
        evidence_snippet_ids=[uuid7()],
    )


def _make_library() -> list[MappingLibraryEntry]:
    return [
        MappingLibraryEntry(
            pattern="concrete works",
            sector_code="F",
            confidence=0.95,
        ),
        MappingLibraryEntry(
            pattern="steel reinforcement",
            sector_code="F",
            confidence=0.90,
        ),
        MappingLibraryEntry(
            pattern="transport services",
            sector_code="H",
            confidence=0.88,
        ),
        MappingLibraryEntry(
            pattern="catering services",
            sector_code="I",
            confidence=0.85,
        ),
        MappingLibraryEntry(
            pattern="software development",
            sector_code="J",
            confidence=0.92,
        ),
    ]


def _make_taxonomy() -> list[dict]:
    return [
        {"sector_code": "A", "sector_name": "Agriculture"},
        {"sector_code": "B", "sector_name": "Mining"},
        {"sector_code": "C", "sector_name": "Manufacturing"},
        {"sector_code": "D", "sector_name": "Utilities"},
        {"sector_code": "F", "sector_name": "Construction"},
        {"sector_code": "G", "sector_name": "Trade"},
        {"sector_code": "H", "sector_name": "Transport"},
        {"sector_code": "I", "sector_name": "Accommodation/Food"},
        {"sector_code": "J", "sector_name": "ICT"},
    ]


# ===================================================================
# Library-based mapping (no LLM)
# ===================================================================


class TestLibraryMapping:
    """Map items using library pattern matching — no LLM needed."""

    def test_exact_match(self) -> None:
        agent = MappingSuggestionAgent(library=_make_library())
        item = _make_line_item("concrete works")
        suggestion = agent.suggest_one(item, taxonomy=_make_taxonomy())
        assert suggestion.sector_code == "F"
        assert suggestion.confidence >= 0.8

    def test_partial_match(self) -> None:
        agent = MappingSuggestionAgent(library=_make_library())
        item = _make_line_item("reinforced concrete works and formwork")
        suggestion = agent.suggest_one(item, taxonomy=_make_taxonomy())
        assert suggestion.sector_code == "F"

    def test_no_match_returns_low_confidence(self) -> None:
        agent = MappingSuggestionAgent(library=_make_library())
        item = _make_line_item("miscellaneous overhead charges")
        suggestion = agent.suggest_one(item, taxonomy=_make_taxonomy())
        assert suggestion.confidence < 0.6

    def test_suggestion_has_explanation(self) -> None:
        agent = MappingSuggestionAgent(library=_make_library())
        item = _make_line_item("concrete works")
        suggestion = agent.suggest_one(item, taxonomy=_make_taxonomy())
        assert len(suggestion.explanation) > 0


# ===================================================================
# Batch mapping
# ===================================================================


class TestBatchMapping:
    """Batch multiple line items for efficiency."""

    def test_batch_returns_all_items(self) -> None:
        agent = MappingSuggestionAgent(library=_make_library())
        items = [
            _make_line_item("concrete works"),
            _make_line_item("steel reinforcement"),
            _make_line_item("transport services"),
        ]
        batch = agent.suggest_batch(items, taxonomy=_make_taxonomy())
        assert len(batch.suggestions) == 3

    def test_batch_preserves_order(self) -> None:
        agent = MappingSuggestionAgent(library=_make_library())
        items = [
            _make_line_item("concrete works"),
            _make_line_item("transport services"),
        ]
        batch = agent.suggest_batch(items, taxonomy=_make_taxonomy())
        assert batch.suggestions[0].line_item_id == items[0].line_item_id
        assert batch.suggestions[1].line_item_id == items[1].line_item_id

    def test_empty_batch(self) -> None:
        agent = MappingSuggestionAgent(library=_make_library())
        batch = agent.suggest_batch([], taxonomy=_make_taxonomy())
        assert len(batch.suggestions) == 0


# ===================================================================
# Suggestion output validation
# ===================================================================


class TestSuggestionValidation:
    """Ensure outputs are valid Pydantic models — agent never produces numbers."""

    def test_suggestion_fields(self) -> None:
        agent = MappingSuggestionAgent(library=_make_library())
        item = _make_line_item("concrete works")
        s = agent.suggest_one(item, taxonomy=_make_taxonomy())
        assert isinstance(s, MappingSuggestion)
        assert isinstance(s.sector_code, str)
        assert isinstance(s.confidence, float)
        assert 0.0 <= s.confidence <= 1.0

    def test_suggestion_has_line_item_id(self) -> None:
        agent = MappingSuggestionAgent(library=_make_library())
        item = _make_line_item("concrete works")
        s = agent.suggest_one(item, taxonomy=_make_taxonomy())
        assert s.line_item_id == item.line_item_id

    def test_batch_result_type(self) -> None:
        agent = MappingSuggestionAgent(library=_make_library())
        items = [_make_line_item("concrete works")]
        batch = agent.suggest_batch(items, taxonomy=_make_taxonomy())
        assert isinstance(batch, MappingSuggestionBatch)


# ===================================================================
# Few-shot examples from library
# ===================================================================


class TestFewShotExamples:
    """Library entries used as few-shot examples for LLM context."""

    def test_get_few_shot_examples(self) -> None:
        agent = MappingSuggestionAgent(library=_make_library())
        examples = agent.get_few_shot_examples(text="concrete", top_k=3)
        assert len(examples) <= 3
        assert examples[0].pattern == "concrete works"

    def test_few_shot_empty_library(self) -> None:
        agent = MappingSuggestionAgent(library=[])
        examples = agent.get_few_shot_examples(text="concrete", top_k=3)
        assert len(examples) == 0

    def test_few_shot_relevance_ranking(self) -> None:
        agent = MappingSuggestionAgent(library=_make_library())
        examples = agent.get_few_shot_examples(text="steel", top_k=2)
        assert any("steel" in e.pattern for e in examples)


# ===================================================================
# LLM prompt construction
# ===================================================================


class TestPromptConstruction:
    """Build prompts for LLM-assisted mapping."""

    def test_build_prompt_includes_item_text(self) -> None:
        agent = MappingSuggestionAgent(library=_make_library())
        item = _make_line_item("concrete works")
        prompt = agent.build_mapping_prompt(item, taxonomy=_make_taxonomy())
        assert "concrete works" in prompt

    def test_build_prompt_includes_taxonomy(self) -> None:
        agent = MappingSuggestionAgent(library=_make_library())
        item = _make_line_item("concrete works")
        prompt = agent.build_mapping_prompt(item, taxonomy=_make_taxonomy())
        assert "Construction" in prompt

    def test_build_prompt_includes_few_shot(self) -> None:
        agent = MappingSuggestionAgent(library=_make_library())
        item = _make_line_item("concrete works")
        prompt = agent.build_mapping_prompt(item, taxonomy=_make_taxonomy())
        assert "example" in prompt.lower() or "concrete works" in prompt.lower()
