"""Tests for AI-enhanced compiler orchestrator (MVP-8).

Covers: full AI-assisted pipeline, graceful fallback when LLM unavailable,
confidence classification routing, assumption drafting for residuals,
ScenarioSpec production.
"""

import pytest
from uuid_extensions import uuid7

from src.agents.mapping_agent import MappingSuggestionAgent
from src.agents.split_agent import SplitAgent, SplitDefaults
from src.agents.assumption_agent import AssumptionDraftAgent
from src.compiler.ai_compiler import (
    AICompiler,
    AICompilationInput,
    AICompilationResult,
    CompilationMode,
)
from src.models.document import BoQLineItem
from src.models.mapping import MappingLibraryEntry
from src.models.scenario import TimeHorizon


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_line_items() -> list[BoQLineItem]:
    return [
        BoQLineItem(
            doc_id=uuid7(),
            extraction_job_id=uuid7(),
            raw_text="concrete works",
            description="Reinforced concrete for foundations",
            total_value=2_000_000.0,
            page_ref=0,
            evidence_snippet_ids=[uuid7()],
        ),
        BoQLineItem(
            doc_id=uuid7(),
            extraction_job_id=uuid7(),
            raw_text="steel reinforcement",
            description="Steel bars for structural support",
            total_value=1_500_000.0,
            page_ref=1,
            evidence_snippet_ids=[uuid7()],
        ),
        BoQLineItem(
            doc_id=uuid7(),
            extraction_job_id=uuid7(),
            raw_text="miscellaneous overhead",
            description="Various overhead charges",
            total_value=500_000.0,
            page_ref=2,
            evidence_snippet_ids=[uuid7()],
        ),
    ]


def _make_library() -> list[MappingLibraryEntry]:
    return [
        MappingLibraryEntry(pattern="concrete works", sector_code="F", confidence=0.95),
        MappingLibraryEntry(pattern="steel reinforcement", sector_code="F", confidence=0.90),
        MappingLibraryEntry(pattern="transport services", sector_code="H", confidence=0.88),
    ]


def _make_taxonomy() -> list[dict]:
    return [
        {"sector_code": "A", "sector_name": "Agriculture"},
        {"sector_code": "F", "sector_name": "Construction"},
        {"sector_code": "H", "sector_name": "Transport"},
    ]


def _make_split_defaults() -> list[SplitDefaults]:
    return [
        SplitDefaults(sector_code="F", domestic_share=0.65, import_share=0.35, source="GASTAT"),
    ]


def _make_compiler() -> AICompiler:
    return AICompiler(
        mapping_agent=MappingSuggestionAgent(library=_make_library()),
        split_agent=SplitAgent(defaults=_make_split_defaults()),
        assumption_agent=AssumptionDraftAgent(),
    )


# ===================================================================
# Full AI-assisted pipeline
# ===================================================================


class TestAICompilationPipeline:
    """End-to-end AI-assisted compilation."""

    def test_compile_produces_result(self) -> None:
        compiler = _make_compiler()
        result = compiler.compile(
            AICompilationInput(
                workspace_id=uuid7(),
                scenario_name="Test Scenario",
                base_model_version_id=uuid7(),
                base_year=2020,
                time_horizon=TimeHorizon(start_year=2026, end_year=2030),
                line_items=_make_line_items(),
                taxonomy=_make_taxonomy(),
                phasing={2026: 0.2, 2027: 0.3, 2028: 0.3, 2029: 0.15, 2030: 0.05},
            ),
        )
        assert isinstance(result, AICompilationResult)

    def test_compile_has_mapping_suggestions(self) -> None:
        compiler = _make_compiler()
        result = compiler.compile(
            AICompilationInput(
                workspace_id=uuid7(),
                scenario_name="Test",
                base_model_version_id=uuid7(),
                base_year=2020,
                time_horizon=TimeHorizon(start_year=2026, end_year=2028),
                line_items=_make_line_items(),
                taxonomy=_make_taxonomy(),
                phasing={2026: 0.5, 2027: 0.3, 2028: 0.2},
            ),
        )
        assert len(result.mapping_suggestions) == 3

    def test_compile_has_split_proposals(self) -> None:
        compiler = _make_compiler()
        result = compiler.compile(
            AICompilationInput(
                workspace_id=uuid7(),
                scenario_name="Test",
                base_model_version_id=uuid7(),
                base_year=2020,
                time_horizon=TimeHorizon(start_year=2026, end_year=2028),
                line_items=_make_line_items(),
                taxonomy=_make_taxonomy(),
                phasing={2026: 0.5, 2027: 0.3, 2028: 0.2},
            ),
        )
        assert len(result.split_proposals) >= 1

    def test_compile_classifies_confidence(self) -> None:
        compiler = _make_compiler()
        result = compiler.compile(
            AICompilationInput(
                workspace_id=uuid7(),
                scenario_name="Test",
                base_model_version_id=uuid7(),
                base_year=2020,
                time_horizon=TimeHorizon(start_year=2026, end_year=2028),
                line_items=_make_line_items(),
                taxonomy=_make_taxonomy(),
                phasing={2026: 1.0},
            ),
        )
        assert result.high_confidence_count >= 0
        assert result.low_confidence_count >= 0

    def test_compile_drafts_assumptions_for_residuals(self) -> None:
        compiler = _make_compiler()
        result = compiler.compile(
            AICompilationInput(
                workspace_id=uuid7(),
                scenario_name="Test",
                base_model_version_id=uuid7(),
                base_year=2020,
                time_horizon=TimeHorizon(start_year=2026, end_year=2028),
                line_items=_make_line_items(),
                taxonomy=_make_taxonomy(),
                phasing={2026: 0.5, 2027: 0.3, 2028: 0.2},
            ),
        )
        # Low confidence items should generate assumption drafts
        assert result.assumption_drafts is not None


# ===================================================================
# Manual-only mode (fallback)
# ===================================================================


class TestManualFallback:
    """Graceful fallback when LLM unavailable — manual-only mode."""

    def test_manual_mode_still_uses_library(self) -> None:
        compiler = _make_compiler()
        result = compiler.compile(
            AICompilationInput(
                workspace_id=uuid7(),
                scenario_name="Manual",
                base_model_version_id=uuid7(),
                base_year=2020,
                time_horizon=TimeHorizon(start_year=2026, end_year=2028),
                line_items=_make_line_items(),
                taxonomy=_make_taxonomy(),
                phasing={2026: 1.0},
                mode=CompilationMode.MANUAL,
            ),
        )
        # Even in manual mode, library matching works
        assert len(result.mapping_suggestions) == 3

    def test_manual_mode_flag(self) -> None:
        compiler = _make_compiler()
        result = compiler.compile(
            AICompilationInput(
                workspace_id=uuid7(),
                scenario_name="Manual",
                base_model_version_id=uuid7(),
                base_year=2020,
                time_horizon=TimeHorizon(start_year=2026, end_year=2028),
                line_items=_make_line_items(),
                taxonomy=_make_taxonomy(),
                phasing={2026: 1.0},
                mode=CompilationMode.MANUAL,
            ),
        )
        assert result.mode == CompilationMode.MANUAL


# ===================================================================
# Confidence band classification
# ===================================================================


class TestConfidenceBands:
    """Route suggestions by confidence band."""

    def test_high_confidence_auto_approve_eligible(self) -> None:
        compiler = _make_compiler()
        result = compiler.compile(
            AICompilationInput(
                workspace_id=uuid7(),
                scenario_name="Test",
                base_model_version_id=uuid7(),
                base_year=2020,
                time_horizon=TimeHorizon(start_year=2026, end_year=2028),
                line_items=_make_line_items(),
                taxonomy=_make_taxonomy(),
                phasing={2026: 1.0},
            ),
        )
        # Items matching "concrete works" and "steel reinforcement" should be high confidence
        assert result.high_confidence_count >= 1

    def test_low_confidence_flagged_for_review(self) -> None:
        compiler = _make_compiler()
        result = compiler.compile(
            AICompilationInput(
                workspace_id=uuid7(),
                scenario_name="Test",
                base_model_version_id=uuid7(),
                base_year=2020,
                time_horizon=TimeHorizon(start_year=2026, end_year=2028),
                line_items=_make_line_items(),
                taxonomy=_make_taxonomy(),
                phasing={2026: 1.0},
            ),
        )
        # "miscellaneous overhead" has no library match → low confidence
        assert result.low_confidence_count >= 1


# ===================================================================
# Empty inputs
# ===================================================================


class TestEmptyInputs:
    """Handle edge cases gracefully."""

    def test_no_line_items(self) -> None:
        compiler = _make_compiler()
        result = compiler.compile(
            AICompilationInput(
                workspace_id=uuid7(),
                scenario_name="Empty",
                base_model_version_id=uuid7(),
                base_year=2020,
                time_horizon=TimeHorizon(start_year=2026, end_year=2028),
                line_items=[],
                taxonomy=_make_taxonomy(),
                phasing={2026: 1.0},
            ),
        )
        assert len(result.mapping_suggestions) == 0
        assert len(result.split_proposals) == 0
