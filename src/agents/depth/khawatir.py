"""Step 1: Khawatir — Candidate Direction Generation.

Generates 5-7 candidate scenario directions from workspace context.
Each direction is labeled with Al-Muhasabi source_type.

RESTRICTED fallback: deterministic "Scenario Red Team Library" generates
template-based candidates from sector metadata.
"""

import logging

from src.agents.depth.base import DepthStepAgent
from src.agents.depth.prompts.khawatir import build_prompt
from src.agents.llm_client import LLMClient
from src.models.common import DataClassification, new_uuid7
from src.models.depth import (
    CandidateDirection,
    DepthStepName,
    KhawatirOutput,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Deterministic Red Team Library templates
# ---------------------------------------------------------------------------

_TEMPLATE_DIRECTIONS = [
    {
        "label": "Base case continuation",
        "description": "Continue current spending trajectory with no structural changes",
        "source_type": "nafs",
        "test_plan": "No shocks — run baseline model",
        "required_levers": [],
    },
    {
        "label": "Accelerated local content",
        "description": (
            "Push domestic share targets to 70%+ across "
            "primary construction and services sectors"
        ),
        "source_type": "insight",
        "test_plan": (
            "Apply LOCAL_CONTENT shock to top-3 sectors by spend"
            " with target_domestic_share=0.70"
        ),
        "required_levers": ["LOCAL_CONTENT"],
    },
    {
        "label": "Import substitution stress",
        "description": (
            "Model a scenario where import dependency decreases "
            "by 20% across all sectors"
        ),
        "source_type": "insight",
        "test_plan": (
            "Apply IMPORT_SUBSTITUTION shock with delta_import_share=-0.20"
            " to all sectors with import_share > 0.3"
        ),
        "required_levers": ["IMPORT_SUBSTITUTION"],
    },
    {
        "label": "Demand surge scenario",
        "description": "Model 150% of planned CAPEX injection over the time horizon",
        "source_type": "insight",
        "test_plan": (
            "Apply FINAL_DEMAND_SHOCK at 1.5x baseline for all sectors"
        ),
        "required_levers": ["FINAL_DEMAND_SHOCK"],
    },
    {
        "label": "Capacity-constrained growth",
        "description": (
            "Model growth with hard capacity caps on key sectors "
            "to test feasibility limits"
        ),
        "source_type": "insight",
        "test_plan": (
            "Apply CONSTRAINT_OVERRIDE with cap_output at current+20%"
            " for top-3 sectors by output"
        ),
        "required_levers": ["FINAL_DEMAND_SHOCK", "CONSTRAINT_OVERRIDE"],
    },
]


def _generate_fallback_candidates(context: dict) -> list[CandidateDirection]:
    """Generate deterministic candidates from template library.

    Uses sector codes, time horizon, and key_questions from context
    to customize templates (P3-5: question-calibrated).
    """
    sector_codes = context.get("sector_codes", [])
    key_questions = context.get("key_questions", [])
    candidates: list[CandidateDirection] = []

    for tmpl in _TEMPLATE_DIRECTIONS:
        # Assign sector codes from context if available
        assigned_sectors = sector_codes[:3] if sector_codes else []

        rationale = (
            f"Template-based direction for sectors {assigned_sectors}"
            if assigned_sectors
            else "Generic template direction"
        )

        candidates.append(
            CandidateDirection(
                direction_id=new_uuid7(),
                label=tmpl["label"],
                description=tmpl["description"],
                sector_codes=assigned_sectors,
                rationale=rationale,
                source_type=tmpl["source_type"],
                test_plan=tmpl["test_plan"],
                required_levers=tmpl["required_levers"],
            )
        )

    # P3-5: Generate question-calibrated candidates from key_questions
    if key_questions:
        for question in key_questions[:2]:
            q_sectors = sector_codes[:2] if sector_codes else []
            candidates.append(
                CandidateDirection(
                    direction_id=new_uuid7(),
                    label=f"Question-driven: {question[:50]}",
                    description=(
                        f"Scenario direction calibrated to key_question: {question}"
                    ),
                    sector_codes=q_sectors,
                    rationale=f"Derived from key_question: {question}",
                    source_type="insight",
                    test_plan=f"Run analysis addressing: {question[:80]}",
                    required_levers=["FINAL_DEMAND_SHOCK"],
                )
            )

    return candidates


class KhawatirAgent(DepthStepAgent):
    """Step 1: Generate candidate scenario directions."""

    step_name = DepthStepName.KHAWATIR

    async def run(
        self,
        *,
        context: dict,
        llm_client: LLMClient | None = None,
        classification: DataClassification = DataClassification.INTERNAL,
    ) -> dict:
        """Generate candidate directions.

        Returns KhawatirOutput.model_dump(mode="json").
        """
        if self._can_use_llm(llm_client, classification):
            return await self._run_with_llm(context, llm_client, classification)

        logger.info("Khawatir: using deterministic fallback (RESTRICTED or no LLM)")
        candidates = _generate_fallback_candidates(context)
        output = KhawatirOutput(candidates=candidates)
        return output.model_dump(mode="json")

    async def _run_with_llm(
        self,
        context: dict,
        llm_client: LLMClient,
        classification: DataClassification,
    ) -> dict:
        """Generate candidates using LLM (P3-1: real wiring)."""
        from src.agents.llm_client import LLMRequest

        prompt = build_prompt(context)
        logger.info("Khawatir: LLM mode — prompt built (%d chars)", len(prompt))

        response = await llm_client.call(
            LLMRequest(
                system_prompt=(
                    "You are the Khawatir step of the Al-Muhasabi depth engine. "
                    "Generate 5-7 candidate scenario directions as structured JSON."
                ),
                user_prompt=prompt,
                output_schema=KhawatirOutput,
                max_tokens=2048,
                temperature=0.7,
            ),
            classification=classification,
        )

        if response.parsed is not None:
            return response.parsed.model_dump(mode="json")

        try:
            parsed = llm_client.parse_structured_output(
                raw=response.content, schema=KhawatirOutput,
            )
            return parsed.model_dump(mode="json")
        except ValueError:
            logger.warning("Khawatir: LLM output parse failed, using fallback")
            candidates = _generate_fallback_candidates(context)
            return KhawatirOutput(candidates=candidates).model_dump(mode="json")
