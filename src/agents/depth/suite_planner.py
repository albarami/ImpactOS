"""Step 5: Suite Planning — Final Scenario Suite Assembly.

Assembles executable runs from accepted candidates.
The suite plan is directly feedable to the compiler/engine.

RESTRICTED fallback: select top-3 accepted candidates by composite_score,
build executable runs from their required_levers.
"""

import logging
from uuid import UUID

from src.agents.depth.base import DepthStepAgent
from src.agents.depth.prompts.suite import build_prompt
from src.agents.llm_client import LLMClient
from src.models.common import DataClassification, DisclosureTier
from src.models.depth import (
    DepthStepName,
    QualitativeRisk,
    ScenarioSuitePlan,
    SuitePlanningOutput,
    SuiteRun,
)

logger = logging.getLogger(__name__)

# Map direction required_levers to executable lever types
_LEVER_TYPE_MAP = {
    "FINAL_DEMAND_SHOCK": "FINAL_DEMAND_SHOCK",
    "IMPORT_SUBSTITUTION": "IMPORT_SHARE_ADJUSTMENT",
    "LOCAL_CONTENT": "LOCAL_CONTENT_TARGET",
    "CONSTRAINT_OVERRIDE": "CONSTRAINT_SET_TOGGLE",
}

_DEFAULT_OUTPUTS = ["multipliers", "jobs", "imports"]
_MAX_RUNS = 20


def _build_suite_from_scored(context: dict) -> ScenarioSuitePlan:
    """Build suite plan deterministically from scored candidates."""
    scored = context.get("scored", [])
    qualitative_risks_raw = context.get("qualitative_risks", [])
    workspace_id = context.get("workspace_id")
    if isinstance(workspace_id, str):
        workspace_id = UUID(workspace_id)

    # P3-2: configurable max_runs from context (default: _MAX_RUNS)
    max_runs = context.get("max_runs", _MAX_RUNS)

    # Rebuild QualitativeRisk objects from dicts
    risks: list[QualitativeRisk] = []
    for r in qualitative_risks_raw:
        risks.append(QualitativeRisk(
            label=r.get("label", "Unknown"),
            description=r.get("description", ""),
            affected_sectors=r.get("affected_sectors", []),
        ))

    # Filter accepted candidates
    accepted = [s for s in scored if s.get("accepted", False)]
    # Sort by composite score descending
    accepted.sort(key=lambda s: s.get("composite_score", 0), reverse=True)
    # Take top N (P3-2: configurable)
    selected = accepted[:max_runs]

    runs: list[SuiteRun] = []
    has_contrarian = False

    for s in selected:
        direction_id = s.get("direction_id")
        if isinstance(direction_id, str):
            direction_id = UUID(direction_id)

        label = s.get("label", "Unknown")
        is_contrarian = s.get("is_contrarian", False)
        if is_contrarian:
            has_contrarian = True

        # Build executable levers from the context's original direction data
        executable_levers = _build_levers_for_direction(s, context)

        # P3-3: Sensitivity sweeps with parameter ranges (not just strings)
        sensitivities: list[str | dict] = []
        if s.get("novelty_score", 0) >= 7.0:
            sensitivities.append({
                "type": "sensitivity_sweep",
                "range": {"min": 0.8, "max": 1.2, "steps": 5},
            })
        if is_contrarian:
            sensitivities.append({
                "type": "import_share",
                "range": {"min": -0.30, "max": 0.0, "steps": 3},
            })
            sensitivities.append({
                "type": "phasing",
                "values": [0, 1, 2, 3],
            })

        tier = DisclosureTier.TIER0 if is_contrarian else DisclosureTier.TIER1

        runs.append(SuiteRun(
            name=f"Run: {label}",
            direction_id=direction_id,
            executable_levers=executable_levers,
            mode="SANDBOX",
            sensitivities=sensitivities,
            disclosure_tier=tier,
        ))

    # Recommended outputs
    recommended = list(_DEFAULT_OUTPUTS)
    if has_contrarian:
        recommended.append("variance_bridge")

    rationale_parts = [f"Selected {len(runs)} directions from {len(scored)} scored candidates."]
    if has_contrarian:
        rationale_parts.append("Includes contrarian stress test(s).")
    rationale_parts.append(f"{len(risks)} qualitative risks identified (not modeled).")

    return ScenarioSuitePlan(
        workspace_id=workspace_id,
        runs=runs,
        recommended_outputs=recommended,
        qualitative_risks=risks,
        rationale=" ".join(rationale_parts),
        disclosure_tier=DisclosureTier.TIER1,
    )


def _build_levers_for_direction(scored: dict, context: dict) -> list[dict]:
    """Build executable lever dicts for a scored direction.

    Looks up the original direction from context to get required_levers.
    """
    direction_id = str(scored.get("direction_id", ""))
    levers: list[dict] = []

    # Try to find original direction in context candidates + contrarians
    original = None
    for c in context.get("candidates", []):
        if str(c.get("direction_id", "")) == direction_id:
            original = c
            break
    if original is None:
        for c in context.get("contrarians", []):
            if str(c.get("direction_id", "")) == direction_id:
                original = c
                # Use quantified_levers if available
                if original.get("quantified_levers"):
                    return original["quantified_levers"]
                break

    if original is None:
        return levers

    # Convert required_levers to executable format
    sector_codes = original.get("sector_codes", [])
    primary_sector = sector_codes[0] if sector_codes else "UNKNOWN"

    for lever_name in original.get("required_levers", []):
        exec_type = _LEVER_TYPE_MAP.get(lever_name, lever_name)
        levers.append({
            "type": exec_type,
            "sector": primary_sector,
            "value": 0,  # Placeholder — analyst fills in actual values
        })

    return levers


class SuitePlannerAgent(DepthStepAgent):
    """Step 5: Assemble the final scenario suite."""

    step_name = DepthStepName.SUITE_PLANNING

    async def run(
        self,
        *,
        context: dict,
        llm_client: LLMClient | None = None,
        classification: DataClassification = DataClassification.INTERNAL,
    ) -> dict:
        """Assemble suite plan from scored candidates.

        Returns SuitePlanningOutput.model_dump(mode="json").
        """
        if self._can_use_llm(llm_client, classification):
            return await self._run_with_llm(context, llm_client, classification)

        logger.info("SuitePlanner: using deterministic assembly (fallback)")
        suite = _build_suite_from_scored(context)
        output = SuitePlanningOutput(suite_plan=suite)
        return output.model_dump(mode="json")

    async def _run_with_llm(
        self,
        context: dict,
        llm_client: LLMClient,
        classification: DataClassification,
    ) -> dict:
        """Assemble suite using LLM (P3-1: real wiring)."""
        from src.agents.llm_client import LLMRequest

        prompt = build_prompt(context)
        logger.info("SuitePlanner: LLM mode — prompt built (%d chars)", len(prompt))

        response = await llm_client.call(
            LLMRequest(
                system_prompt=(
                    "You are the Suite Planner of the Al-Muhasabi depth engine. "
                    "Assemble an executable scenario suite from scored candidates. "
                    "Return structured JSON."
                ),
                user_prompt=prompt,
                output_schema=SuitePlanningOutput,
                max_tokens=2048,
                temperature=0.3,
            ),
            classification=classification,
        )

        if response.parsed is not None:
            return response.parsed.model_dump(mode="json")

        try:
            parsed = llm_client.parse_structured_output(
                raw=response.content, schema=SuitePlanningOutput,
            )
            return parsed.model_dump(mode="json")
        except ValueError:
            logger.warning("SuitePlanner: LLM output parse failed, using deterministic fallback")
            suite = _build_suite_from_scored(context)
            output = SuitePlanningOutput(suite_plan=suite)
            return output.model_dump(mode="json")
