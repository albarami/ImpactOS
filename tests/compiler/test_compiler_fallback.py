"""Tests for compiler fallback safety when LLM path unavailable (Sprint 9, S9-3).

Covers: AICompiler with LLMClient attempts real LLM-enhanced mapping,
falls back to deterministic library/rule-based behavior when LLM
raises ProviderUnavailableError. Verifies the LLM path is actually
invoked and that fallback output matches manual mode.
"""

from unittest.mock import AsyncMock

import pytest
from uuid_extensions import uuid7

from src.agents.assumption_agent import AssumptionDraftAgent
from src.agents.llm_client import (
    LLMClient,
    LLMProvider,
    LLMResponse,
    ProviderUnavailableError,
    TokenUsage,
)
from src.agents.mapping_agent import MappingSuggestion, MappingSuggestionAgent
from src.agents.split_agent import SplitAgent
from src.compiler.ai_compiler import (
    AICompilationInput,
    AICompilationResult,
    AICompiler,
    CompilationMode,
)
from src.models.common import DataClassification
from src.models.document import BoQLineItem
from src.models.mapping import MappingLibraryEntry
from src.models.scenario import TimeHorizon

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_library() -> list[MappingLibraryEntry]:
    return [
        MappingLibraryEntry(
            pattern="concrete works", sector_code="F", confidence=0.95,
        ),
        MappingLibraryEntry(
            pattern="steel reinforcement", sector_code="F", confidence=0.90,
        ),
    ]


def _make_line_items() -> list[BoQLineItem]:
    return [
        BoQLineItem(
            doc_id=uuid7(), extraction_job_id=uuid7(),
            raw_text="concrete works",
            description="Reinforced concrete for foundations",
            total_value=2_000_000.0, page_ref=0,
            evidence_snippet_ids=[uuid7()],
        ),
        BoQLineItem(
            doc_id=uuid7(), extraction_job_id=uuid7(),
            raw_text="miscellaneous overhead",
            description="Various overhead charges",
            total_value=500_000.0, page_ref=1,
            evidence_snippet_ids=[uuid7()],
        ),
    ]


def _make_input(
    mode: CompilationMode = CompilationMode.AI_ASSISTED,
) -> AICompilationInput:
    return AICompilationInput(
        workspace_id=uuid7(),
        scenario_name="Fallback Test",
        base_model_version_id=uuid7(),
        base_year=2020,
        time_horizon=TimeHorizon(start_year=2026, end_year=2028),
        line_items=_make_line_items(),
        taxonomy=[
            {"sector_code": "A", "sector_name": "Agriculture"},
            {"sector_code": "F", "sector_name": "Construction"},
        ],
        phasing={2026: 0.5, 2027: 0.3, 2028: 0.2},
        mode=mode,
    )


def _build_mock_llm_response(item: BoQLineItem) -> LLMResponse:
    """Build a valid LLMResponse for a line item."""
    suggestion = MappingSuggestion(
        line_item_id=item.line_item_id,
        sector_code="F",
        confidence=0.95,
        explanation="LLM-enhanced mapping",
    )
    return LLMResponse(
        content=suggestion.model_dump_json(),
        parsed=suggestion,
        provider=LLMProvider.ANTHROPIC,
        model="claude-sonnet-4-20250514",
        usage=TokenUsage(input_tokens=50, output_tokens=30),
    )


# ===================================================================
# S9-3: Compiler with no LLM client — library-only
# ===================================================================


class TestCompilerWithoutLLM:
    """No LLM client → library-only path, same as before Sprint 9."""

    @pytest.mark.anyio
    async def test_no_llm_client_uses_library(self) -> None:
        compiler = AICompiler(
            mapping_agent=MappingSuggestionAgent(library=_make_library()),
            split_agent=SplitAgent(defaults=[]),
            assumption_agent=AssumptionDraftAgent(),
        )
        result = await compiler.compile(_make_input())

        assert isinstance(result, AICompilationResult)
        assert len(result.mapping_suggestions) == 2
        assert result.mode == CompilationMode.AI_ASSISTED


# ===================================================================
# S9-3: Compiler with LLM — LLM path actually exercised
# ===================================================================


class TestCompilerLLMPathExercised:
    """When LLM client is provided, compile() actually calls it."""

    @pytest.mark.anyio
    async def test_llm_call_is_invoked_for_each_item(self) -> None:
        """Verify LLMClient.call() is invoked once per line item."""
        mock_client = AsyncMock(spec=LLMClient)
        items = _make_line_items()

        responses = [_build_mock_llm_response(item) for item in items]
        mock_client.call = AsyncMock(side_effect=responses)

        compiler = AICompiler(
            mapping_agent=MappingSuggestionAgent(library=_make_library()),
            split_agent=SplitAgent(defaults=[]),
            assumption_agent=AssumptionDraftAgent(),
            llm_client=mock_client,
            classification=DataClassification.CONFIDENTIAL,
        )
        result = await compiler.compile(_make_input())

        assert mock_client.call.call_count == len(items)
        assert len(result.mapping_suggestions) == len(items)

    @pytest.mark.anyio
    async def test_llm_success_uses_llm_explanation(self) -> None:
        """When LLM succeeds, the suggestion carries the LLM explanation."""
        mock_client = AsyncMock(spec=LLMClient)
        items = _make_line_items()

        responses = [_build_mock_llm_response(item) for item in items]
        mock_client.call = AsyncMock(side_effect=responses)

        compiler = AICompiler(
            mapping_agent=MappingSuggestionAgent(library=_make_library()),
            split_agent=SplitAgent(defaults=[]),
            assumption_agent=AssumptionDraftAgent(),
            llm_client=mock_client,
            classification=DataClassification.CONFIDENTIAL,
        )
        result = await compiler.compile(_make_input())

        assert any(
            "LLM-enhanced" in s.explanation
            for s in result.mapping_suggestions
        )


# ===================================================================
# S9-3: Compiler fallback when LLM fails
# ===================================================================


class TestCompilerFallbackOnLLMFailure:
    """When LLM call raises, compiler falls back to library per item."""

    @pytest.mark.anyio
    async def test_all_items_fail_falls_back_to_library(self) -> None:
        """Every LLM call fails → all items use library fallback."""
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.call = AsyncMock(
            side_effect=ProviderUnavailableError("no key"),
        )

        compiler = AICompiler(
            mapping_agent=MappingSuggestionAgent(library=_make_library()),
            split_agent=SplitAgent(defaults=[]),
            assumption_agent=AssumptionDraftAgent(),
            llm_client=mock_client,
            classification=DataClassification.CONFIDENTIAL,
        )
        result = await compiler.compile(_make_input())

        assert isinstance(result, AICompilationResult)
        assert len(result.mapping_suggestions) == 2
        assert mock_client.call.call_count == 2

    @pytest.mark.anyio
    async def test_partial_failure_mixed_sources(self) -> None:
        """First item LLM succeeds, second fails → mixed sources."""
        mock_client = AsyncMock(spec=LLMClient)
        items = _make_line_items()

        mock_client.call = AsyncMock(
            side_effect=[
                _build_mock_llm_response(items[0]),
                ProviderUnavailableError("timeout"),
            ],
        )

        compiler = AICompiler(
            mapping_agent=MappingSuggestionAgent(library=_make_library()),
            split_agent=SplitAgent(defaults=[]),
            assumption_agent=AssumptionDraftAgent(),
            llm_client=mock_client,
            classification=DataClassification.CONFIDENTIAL,
        )
        result = await compiler.compile(_make_input())

        assert len(result.mapping_suggestions) == 2
        assert result.mapping_suggestions[0].explanation == "LLM-enhanced mapping"
        assert "LLM-enhanced" not in result.mapping_suggestions[1].explanation

    @pytest.mark.anyio
    async def test_fallback_matches_manual_mode_output(self) -> None:
        """Fallback result has same structure as MANUAL mode output."""
        library = _make_library()

        manual_compiler = AICompiler(
            mapping_agent=MappingSuggestionAgent(library=library),
            split_agent=SplitAgent(defaults=[]),
            assumption_agent=AssumptionDraftAgent(),
        )
        manual_result = await manual_compiler.compile(
            _make_input(mode=CompilationMode.MANUAL),
        )

        mock_client = AsyncMock(spec=LLMClient)
        mock_client.call = AsyncMock(
            side_effect=ProviderUnavailableError("no key"),
        )
        fallback_compiler = AICompiler(
            mapping_agent=MappingSuggestionAgent(library=library),
            split_agent=SplitAgent(defaults=[]),
            assumption_agent=AssumptionDraftAgent(),
            llm_client=mock_client,
            classification=DataClassification.CONFIDENTIAL,
        )
        fallback_result = await fallback_compiler.compile(_make_input())

        assert len(fallback_result.mapping_suggestions) == len(
            manual_result.mapping_suggestions,
        )
        assert (
            fallback_result.high_confidence_count
            == manual_result.high_confidence_count
        )
        assert (
            fallback_result.low_confidence_count
            == manual_result.low_confidence_count
        )

    @pytest.mark.anyio
    async def test_never_returns_partial_result(self) -> None:
        """Even with mixed LLM failures, result has all expected fields."""
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.call = AsyncMock(
            side_effect=ProviderUnavailableError("err"),
        )

        compiler = AICompiler(
            mapping_agent=MappingSuggestionAgent(library=_make_library()),
            split_agent=SplitAgent(defaults=[]),
            assumption_agent=AssumptionDraftAgent(),
            llm_client=mock_client,
            classification=DataClassification.CONFIDENTIAL,
        )
        result = await compiler.compile(_make_input())

        assert result.mapping_suggestions is not None
        assert result.split_proposals is not None
        assert result.assumption_drafts is not None
        assert isinstance(result.high_confidence_count, int)
        assert isinstance(result.medium_confidence_count, int)
        assert isinstance(result.low_confidence_count, int)
