"""Step 3: Mujahada — Contrarian Challenge.

Generates contrarian directions that challenge base scenario assumptions.
All contrarian outputs default TIER0 (internal only).

RESTRICTED fallback: deterministic contrarian templates:
- Import stress (what if import costs surge)
- Phasing delay (what if timelines slip 2+ years)
- Local content shortfall (what if domestic capacity overestimated)
- Capacity cap (what if sector capacity limits bind)
"""

import logging

from src.agents.depth.base import DepthStepAgent
from src.agents.depth.prompts.mujahada import build_prompt
from src.agents.llm_client import LLMClient
from src.models.common import DataClassification, new_uuid7
from src.models.depth import (
    ContrarianDirection,
    DepthStepName,
    MujahadaOutput,
    QualitativeRisk,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Deterministic contrarian templates
# ---------------------------------------------------------------------------

_CONTRARIAN_TEMPLATES = [
    {
        "label": "Import cost surge",
        "description": (
            "What if import costs surge 30-50% due to supply chain disruption,"
            " currency depreciation, or trade policy changes?"
        ),
        "uncomfortable_truth": (
            "Current import share assumptions are based on stable trade conditions"
            " that may not hold over the project horizon"
        ),
        "broken_assumption": "Stable import share and import cost structure",
        "is_quantifiable": True,
        "quantified_levers": [
            {
                "type": "IMPORT_SHARE_ADJUSTMENT",
                "description": "Increase import share by 15-20% across all sectors",
            },
        ],
    },
    {
        "label": "Phasing delay stress test",
        "description": (
            "What if project timelines slip by 2+ years due to regulatory,"
            " permitting, or execution delays?"
        ),
        "uncomfortable_truth": (
            "Mega-project timelines almost always overrun."
            " Current phasing assumes on-time delivery."
        ),
        "broken_assumption": "Project phasing follows planned timeline",
        "is_quantifiable": True,
        "quantified_levers": [
            {
                "type": "PHASING_SHIFT",
                "description": "Shift all spending 2 years later",
            },
        ],
    },
    {
        "label": "Local content capacity shortfall",
        "description": (
            "What if domestic capacity is overestimated and local content targets"
            " cannot be met, forcing greater import reliance?"
        ),
        "uncomfortable_truth": (
            "Achieving high local content requires workforce and manufacturing"
            " capacity that may not exist yet"
        ),
        "broken_assumption": "Domestic capacity sufficient for local content targets",
        "is_quantifiable": True,
        "quantified_levers": [
            {
                "type": "LOCAL_CONTENT_TARGET",
                "description": "Reduce domestic share targets by 20%",
            },
        ],
    },
]

_QUALITATIVE_RISK_TEMPLATES = [
    {
        "label": "Regulatory environment uncertainty",
        "description": (
            "Changes in regulatory framework or enforcement could"
            " fundamentally alter project economics"
        ),
        "affected_sectors": [],
    },
    {
        "label": "Workforce skill gap",
        "description": (
            "Required skilled labor may not be available domestically,"
            " creating a dependency on foreign workers that conflicts"
            " with localization targets"
        ),
        "affected_sectors": [],
    },
]


def _generate_fallback_contrarians(
    context: dict,
) -> tuple[list[ContrarianDirection], list[QualitativeRisk]]:
    """Generate deterministic contrarian directions from template library."""
    sector_codes = context.get("sector_codes", [])
    assigned = sector_codes[:3] if sector_codes else []

    contrarians: list[ContrarianDirection] = []
    for tmpl in _CONTRARIAN_TEMPLATES:
        contrarians.append(
            ContrarianDirection(
                direction_id=new_uuid7(),
                label=tmpl["label"],
                description=tmpl["description"],
                uncomfortable_truth=tmpl["uncomfortable_truth"],
                sector_codes=assigned,
                rationale=(
                    f"Deterministic stress test template for {assigned}"
                    if assigned
                    else "Generic contrarian template"
                ),
                broken_assumption=tmpl["broken_assumption"],
                is_quantifiable=tmpl["is_quantifiable"],
                quantified_levers=tmpl.get("quantified_levers"),
            )
        )

    risks: list[QualitativeRisk] = []
    for tmpl in _QUALITATIVE_RISK_TEMPLATES:
        risks.append(
            QualitativeRisk(
                risk_id=new_uuid7(),
                label=tmpl["label"],
                description=tmpl["description"],
                affected_sectors=assigned,
            )
        )

    return contrarians, risks


class MujahadaAgent(DepthStepAgent):
    """Step 3: Generate contrarian challenges to base assumptions."""

    step_name = DepthStepName.MUJAHADA

    def run(
        self,
        *,
        context: dict,
        llm_client: LLMClient | None = None,
        classification: DataClassification = DataClassification.INTERNAL,
    ) -> dict:
        """Generate contrarian directions + qualitative risks.

        Returns MujahadaOutput.model_dump(mode="json").
        """
        if self._can_use_llm(llm_client, classification):
            return self._run_with_llm(context, llm_client, classification)

        logger.info("Mujahada: using deterministic contrarian templates (fallback)")
        contrarians, risks = _generate_fallback_contrarians(context)
        output = MujahadaOutput(contrarians=contrarians, qualitative_risks=risks)
        return output.model_dump(mode="json")

    def _run_with_llm(
        self,
        context: dict,
        llm_client: LLMClient,
        classification: DataClassification,
    ) -> dict:
        """Generate contrarians using LLM."""
        prompt = build_prompt(context)
        logger.info("Mujahada: LLM mode — prompt built (%d chars)", len(prompt))

        # For MVP, use deterministic templates
        contrarians, risks = _generate_fallback_contrarians(context)
        output = MujahadaOutput(contrarians=contrarians, qualitative_risks=risks)
        return output.model_dump(mode="json")
