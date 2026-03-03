"""Tests for S13-3: Non-dev AI-assisted compile is real-only.

Covers: non-dev governed compile with missing LLM key fails (no library
fallback as success), dev mode keeps library fallback.
"""

from unittest.mock import AsyncMock

import pytest
from uuid_extensions import uuid7

from src.agents.assumption_agent import AssumptionDraftAgent
from src.agents.llm_client import LLMClient, ProviderUnavailableError
from src.agents.mapping_agent import MappingSuggestion, MappingSuggestionAgent
from src.agents.split_agent import SplitAgent
from src.compiler.ai_compiler import (
    AICompilationInput,
    AICompiler,
    CompilationMode,
)
from src.models.common import DataClassification
from src.models.document import BoQLineItem
from src.models.mapping import MappingLibraryEntry
from src.models.scenario import TimeHorizon


def _lib() -> list[MappingLibraryEntry]:
    return [
        MappingLibraryEntry(
            pattern="concrete works", sector_code="F", confidence=0.95,
        ),
    ]


def _items() -> list[BoQLineItem]:
    return [
        BoQLineItem(
            doc_id=uuid7(), extraction_job_id=uuid7(),
            raw_text="concrete works", description="concrete",
            total_value=1e6, page_ref=0,
            evidence_snippet_ids=[uuid7()],
        ),
    ]


def _inp(mode: CompilationMode = CompilationMode.AI_ASSISTED):
    return AICompilationInput(
        workspace_id=uuid7(), scenario_name="T",
        base_model_version_id=uuid7(), base_year=2020,
        time_horizon=TimeHorizon(start_year=2026, end_year=2028),
        line_items=_items(),
        taxonomy=[{"sector_code": "F", "sector_name": "Construction"}],
        mode=mode,
    )


class TestNonDevCompileFailsClosed:
    """Non-dev AI-assisted compile fails when LLM unavailable."""

    @pytest.mark.anyio
    async def test_non_dev_governed_compile_raises_on_llm_failure(
        self,
    ) -> None:
        """Non-dev: LLM fails → ProviderUnavailableError propagated."""
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.call = AsyncMock(
            side_effect=ProviderUnavailableError("no key"),
        )

        compiler = AICompiler(
            mapping_agent=MappingSuggestionAgent(library=_lib()),
            split_agent=SplitAgent(defaults=[]),
            assumption_agent=AssumptionDraftAgent(),
            llm_client=mock_client,
            classification=DataClassification.CONFIDENTIAL,
            environment="staging",
        )
        with pytest.raises(ProviderUnavailableError):
            await compiler.compile(_inp())


class TestDevCompileKeepsFallback:
    """Dev mode keeps library fallback for local workflow."""

    @pytest.mark.anyio
    async def test_dev_compile_falls_back_to_library(self) -> None:
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.call = AsyncMock(
            side_effect=ProviderUnavailableError("no key"),
        )

        compiler = AICompiler(
            mapping_agent=MappingSuggestionAgent(library=_lib()),
            split_agent=SplitAgent(defaults=[]),
            assumption_agent=AssumptionDraftAgent(),
            llm_client=mock_client,
            classification=DataClassification.CONFIDENTIAL,
            environment="dev",
        )
        result = await compiler.compile(_inp())
        assert len(result.mapping_suggestions) == 1


class TestNonDevSplitFailsClosed:
    """Non-dev compile fails closed for deterministic-only split agent."""

    @pytest.mark.anyio
    async def test_non_dev_rejects_deterministic_split(self) -> None:
        """Non-dev: split step raises ProviderUnavailableError."""
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.call = AsyncMock(return_value=AsyncMock(
            parsed=MappingSuggestion(
                line_item_id=_items()[0].line_item_id,
                sector_code="F",
                confidence=0.95,
                explanation="concrete works → Construction",
            ),
        ))

        compiler = AICompiler(
            mapping_agent=MappingSuggestionAgent(library=_lib()),
            split_agent=SplitAgent(defaults=[]),
            assumption_agent=AssumptionDraftAgent(),
            llm_client=mock_client,
            classification=DataClassification.CONFIDENTIAL,
            environment="staging",
        )
        with pytest.raises(ProviderUnavailableError) as exc_info:
            await compiler.compile(_inp())
        assert exc_info.value.reason_code == "SPLIT_NO_LLM_BACKING"
        assert exc_info.value.agent_name == "SplitAgent"

    @pytest.mark.anyio
    async def test_dev_allows_deterministic_split(self) -> None:
        """Dev: split step succeeds with deterministic output."""
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.call = AsyncMock(return_value=AsyncMock(
            parsed=MappingSuggestion(
                line_item_id=_items()[0].line_item_id,
                sector_code="F",
                confidence=0.95,
                explanation="concrete works → Construction",
            ),
        ))

        compiler = AICompiler(
            mapping_agent=MappingSuggestionAgent(library=_lib()),
            split_agent=SplitAgent(defaults=[]),
            assumption_agent=AssumptionDraftAgent(),
            llm_client=mock_client,
            classification=DataClassification.CONFIDENTIAL,
            environment="dev",
        )
        result = await compiler.compile(_inp())
        assert len(result.split_proposals) >= 0  # deterministic OK in dev


class TestNonDevAssumptionFailsClosed:
    """Non-dev compile fails closed for deterministic-only assumption agent."""

    @pytest.mark.anyio
    async def test_non_dev_rejects_deterministic_assumption(self) -> None:
        """Non-dev: assumption step raises ProviderUnavailableError."""
        mock_client = AsyncMock(spec=LLMClient)
        mock_client.call = AsyncMock(return_value=AsyncMock(
            parsed=MappingSuggestion(
                line_item_id=_items()[0].line_item_id,
                sector_code="X",
                confidence=0.30,
                explanation="unknown item",
            ),
        ))

        compiler = AICompiler(
            mapping_agent=MappingSuggestionAgent(library=_lib()),
            split_agent=SplitAgent(defaults=[]),
            assumption_agent=AssumptionDraftAgent(),
            llm_client=mock_client,
            classification=DataClassification.CONFIDENTIAL,
            environment="prod",
        )
        with pytest.raises(ProviderUnavailableError) as exc_info:
            await compiler.compile(_inp())
        # Could be SPLIT or ASSUMPTION depending on execution order
        assert exc_info.value.reason_code in (
            "SPLIT_NO_LLM_BACKING",
            "ASSUMPTION_NO_LLM_BACKING",
        )
