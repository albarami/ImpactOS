"""AI-enhanced compiler orchestrator — MVP-8 + Sprint 9 fallback safety.

Chains: extract line items → AI mapping suggestions → confidence
classification → AI split suggestions → assumption drafting for
residuals → produce compilation result ready for ScenarioSpec.

Falls back gracefully if LLM is unavailable (manual-only mode).
Library-based matching always works regardless of LLM availability.
When an optional LLMClient is provided and the AI path fails
(ProviderUnavailableError, timeout, validation error), the compiler
falls back to the deterministic library/rule path automatically.

CRITICAL: Agent-to-Math Boundary enforced. All agent outputs are
Pydantic-validated JSON. The deterministic engine remains untouched.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from src.agents.assumption_agent import AssumptionDraft, AssumptionDraftAgent, ResidualContext
from src.agents.guards import require_llm_backing
from src.agents.mapping_agent import MappingSuggestion, MappingSuggestionAgent
from src.agents.split_agent import SplitAgent, SplitProposal
from src.models.document import BoQLineItem
from src.models.scenario import TimeHorizon

if TYPE_CHECKING:
    from src.agents.llm_client import LLMClient
    from src.models.common import DataClassification

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Compilation mode
# ---------------------------------------------------------------------------


class CompilationMode(StrEnum):
    """Compilation mode."""

    AI_ASSISTED = "AI_ASSISTED"
    MANUAL = "MANUAL"


# ---------------------------------------------------------------------------
# Input / Output
# ---------------------------------------------------------------------------


@dataclass
class AICompilationInput:
    """Inputs for AI-assisted compilation."""

    workspace_id: UUID
    scenario_name: str
    base_model_version_id: UUID
    base_year: int
    time_horizon: TimeHorizon
    line_items: list[BoQLineItem]
    taxonomy: list[dict]
    phasing: dict[int, float] = field(default_factory=dict)
    deflators: dict[int, float] = field(default_factory=dict)
    mode: CompilationMode = CompilationMode.AI_ASSISTED


@dataclass
class AICompilationResult:
    """Result of AI-assisted compilation — ready for HITL review."""

    mapping_suggestions: list[MappingSuggestion]
    split_proposals: list[SplitProposal]
    assumption_drafts: list[AssumptionDraft]
    high_confidence_count: int
    medium_confidence_count: int
    low_confidence_count: int
    mode: CompilationMode


# ---------------------------------------------------------------------------
# Confidence thresholds (Section 9.5)
# ---------------------------------------------------------------------------

_HIGH_THRESHOLD = 0.85
_MEDIUM_THRESHOLD = 0.60


# ---------------------------------------------------------------------------
# AI Compiler
# ---------------------------------------------------------------------------


class AICompiler:
    """Enhanced compilation pipeline with AI-assisted agents.

    When ``llm_client`` is provided the compiler attempts LLM-enhanced
    mapping. In non-dev (staging/prod), LLM failure propagates as error
    (no silent library fallback for governed paths). In dev, library
    fallback is allowed for local workflow ergonomics.
    """

    def __init__(
        self,
        *,
        mapping_agent: MappingSuggestionAgent,
        split_agent: SplitAgent,
        assumption_agent: AssumptionDraftAgent,
        llm_client: LLMClient | None = None,
        classification: DataClassification | None = None,
        environment: str = "dev",
    ) -> None:
        self._mapping_agent = mapping_agent
        self._split_agent = split_agent
        self._assumption_agent = assumption_agent
        self._llm_client = llm_client
        self._classification = classification
        self._environment = environment

    async def compile(self, inp: AICompilationInput) -> AICompilationResult:
        """Run the full AI-assisted compilation pipeline.

        Steps per Section 9.3:
        1. AI mapping suggestions for all line items
           (LLM-enhanced when llm_client available, library fallback per item)
        2. Confidence classification
        3. AI split suggestions for mapped items
        4. Assumption drafting for residuals (low confidence items)
        """
        # Step 1: Mapping suggestions
        suggestions = await self._mapping_step(inp)

        # Step 2: Confidence classification
        high = 0
        medium = 0
        low = 0
        high_suggestions: list[MappingSuggestion] = []
        low_suggestions: list[MappingSuggestion] = []

        for s in suggestions:
            if s.confidence >= _HIGH_THRESHOLD:
                high += 1
                high_suggestions.append(s)
            elif s.confidence >= _MEDIUM_THRESHOLD:
                medium += 1
            else:
                low += 1
                low_suggestions.append(s)

        # Step 3: Split proposals for items with known sectors
        mapped_sectors: set[str] = set()
        split_items: list[tuple[str, str]] = []
        for s in suggestions:
            if s.confidence >= _MEDIUM_THRESHOLD:
                sector = s.sector_code
                if sector not in mapped_sectors:
                    mapped_sectors.add(sector)
                    # Find the line item text for context
                    item_text = ""
                    for item in inp.line_items:
                        if item.line_item_id == s.line_item_id:
                            item_text = item.raw_text
                            break
                    split_items.append((sector, item_text))

        # I17-1: Split agent has no LLM backing — fail closed in non-dev
        require_llm_backing(
            agent_name="SplitAgent",
            environment=self._environment,
            has_llm=False,  # No LLM path exists for split
            reason_code="SPLIT_NO_LLM_BACKING",
        )

        split_proposals = self._split_agent.propose_batch(split_items)

        # I17-1: Assumption agent has no LLM backing — fail closed in non-dev
        require_llm_backing(
            agent_name="AssumptionDraftAgent",
            environment=self._environment,
            has_llm=False,  # No LLM path exists for assumption
            reason_code="ASSUMPTION_NO_LLM_BACKING",
        )

        # Step 4: Assumption drafting for low-confidence / residual items
        assumption_drafts: list[AssumptionDraft] = []
        for s in low_suggestions:
            # Find associated line item
            item_value = 0.0
            for item in inp.line_items:
                if item.line_item_id == s.line_item_id:
                    item_value = item.total_value or 0.0
                    break

            if item_value > 0:
                context = ResidualContext(
                    sector_code=s.sector_code,
                    description=f"Low-confidence mapping for: {s.explanation}",
                    total_value=item_value,
                    coverage_pct=s.confidence,
                )
                draft = self._assumption_agent.draft_import_share(
                    context=context,
                    default_domestic=0.50,  # Conservative default for unknowns
                )
                assumption_drafts.append(draft)

        return AICompilationResult(
            mapping_suggestions=suggestions,
            split_proposals=split_proposals,
            assumption_drafts=assumption_drafts,
            high_confidence_count=high,
            medium_confidence_count=medium,
            low_confidence_count=low,
            mode=inp.mode,
        )

    async def _mapping_step(
        self,
        inp: AICompilationInput,
    ) -> list[MappingSuggestion]:
        """Produce mapping suggestions, trying LLM then library fallback.

        When ``llm_client`` and ``classification`` are set and mode is
        AI_ASSISTED, each line item is sent to the LLM first.  If the
        LLM call fails for any item the library fallback is used for
        that item.  The caller always gets a complete suggestion list.
        """
        from src.agents.llm_client import LLMRequest, ProviderUnavailableError

        use_llm = (
            self._llm_client is not None
            and self._classification is not None
            and inp.mode == CompilationMode.AI_ASSISTED
        )

        if not use_llm:
            batch = self._mapping_agent.suggest_batch(
                inp.line_items, taxonomy=inp.taxonomy,
            )
            return batch.suggestions

        suggestions: list[MappingSuggestion] = []
        for item in inp.line_items:
            try:
                prompt = self._mapping_agent.build_mapping_prompt(
                    item, taxonomy=inp.taxonomy,
                )
                response = await self._llm_client.call(
                    LLMRequest(
                        system_prompt="Map procurement line items to ISIC sectors.",
                        user_prompt=prompt,
                        output_schema=MappingSuggestion,
                        max_tokens=256,
                    ),
                    classification=self._classification,
                )
                suggestion = response.parsed
                if not isinstance(suggestion, MappingSuggestion):
                    suggestion = MappingSuggestion.model_validate(
                        suggestion.model_dump(),
                    )
                if suggestion.line_item_id != item.line_item_id:
                    suggestion = suggestion.model_copy(
                        update={"line_item_id": item.line_item_id},
                    )
                suggestions.append(suggestion)
            except (ProviderUnavailableError, ValueError, Exception) as exc:
                is_non_dev = self._environment in ("staging", "prod")
                if is_non_dev:
                    _logger.error(
                        "LLM mapping failed in %s for item %s: %s",
                        self._environment, item.line_item_id, exc,
                    )
                    raise
                _logger.warning(
                    "LLM mapping failed for item %s, "
                    "falling back to library (dev): %s",
                    item.line_item_id, exc,
                )
                fallback = self._mapping_agent.suggest_one(
                    item, taxonomy=inp.taxonomy,
                )
                suggestions.append(fallback)
        return suggestions
