"""Tests for compiler fallback safety when LLM path unavailable (Sprint 9, S9-3).

Covers: AICompiler with optional LLMClient falls back to deterministic
library/rule-based behavior when LLM is unavailable or raises
ProviderUnavailableError. Fallback output matches manual mode.
No economic computation occurs in any path.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid_extensions import uuid7

from src.agents.assumption_agent import AssumptionDraftAgent
from src.agents.llm_client import LLMClient, ProviderUnavailableError
from src.agents.mapping_agent import MappingSuggestionAgent
from src.agents.split_agent import SplitAgent, SplitDefaults
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
        MappingLibraryEntry(pattern="concrete works", sector_code="F", confidence=0.95),
        MappingLibraryEntry(pattern="steel reinforcement", sector_code="F", confidence=0.90),
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


def _make_input(mode: CompilationMode = CompilationMode.AI_ASSISTED) -> AICompilationInput:
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


def _make_compiler(
    *,
    llm_client: LLMClient | None = None,
    classification: DataClassification = DataClassification.CONFIDENTIAL,
) -> AICompiler:
    """Build compiler with optional LLM client for fallback testing."""
    return AICompiler(
        mapping_agent=MappingSuggestionAgent(library=_make_library()),
        split_agent=SplitAgent(defaults=[]),
        assumption_agent=AssumptionDraftAgent(),
        llm_client=llm_client,
        classification=classification,
    )


# ===================================================================
# S9-3: Compiler fallback when LLM unavailable
# ===================================================================


class TestCompilerFallbackSafety:
    """Compiler produces valid results even when LLM path fails."""

    def test_compiler_with_no_llm_client_uses_library(self) -> None:
        """No LLM client → library-only path, same as before Sprint 9."""
        compiler = _make_compiler(llm_client=None)
        result = compiler.compile(_make_input())

        assert isinstance(result, AICompilationResult)
        assert len(result.mapping_suggestions) == 2
        assert result.mode == CompilationMode.AI_ASSISTED

    def test_compiler_with_failing_llm_falls_back(self) -> None:
        """LLM client that raises → compiler still produces valid result."""
        failing_client = LLMClient(anthropic_key="sk-test", max_retries=1, base_delay=0.0)

        compiler = _make_compiler(llm_client=failing_client)
        result = compiler.compile(_make_input())

        assert isinstance(result, AICompilationResult)
        assert len(result.mapping_suggestions) == 2

    def test_compiler_fallback_matches_manual_mode(self) -> None:
        """Fallback result is identical in structure to MANUAL mode output."""
        manual_compiler = AICompiler(
            mapping_agent=MappingSuggestionAgent(library=_make_library()),
            split_agent=SplitAgent(defaults=[]),
            assumption_agent=AssumptionDraftAgent(),
        )
        manual_result = manual_compiler.compile(_make_input(mode=CompilationMode.MANUAL))

        failing_client = LLMClient(anthropic_key="sk-test", max_retries=1, base_delay=0.0)
        fallback_compiler = _make_compiler(llm_client=failing_client)
        fallback_result = fallback_compiler.compile(
            _make_input(mode=CompilationMode.AI_ASSISTED),
        )

        # Same number of suggestions (library path produces same output)
        assert len(fallback_result.mapping_suggestions) == len(manual_result.mapping_suggestions)
        assert fallback_result.high_confidence_count == manual_result.high_confidence_count
        assert fallback_result.low_confidence_count == manual_result.low_confidence_count

    def test_compiler_never_returns_partial_result(self) -> None:
        """Even if LLM fails mid-pipeline, result has all expected fields."""
        failing_client = LLMClient(anthropic_key="sk-test", max_retries=1, base_delay=0.0)
        compiler = _make_compiler(llm_client=failing_client)
        result = compiler.compile(_make_input())

        assert result.mapping_suggestions is not None
        assert result.split_proposals is not None
        assert result.assumption_drafts is not None
        assert isinstance(result.high_confidence_count, int)
        assert isinstance(result.medium_confidence_count, int)
        assert isinstance(result.low_confidence_count, int)
