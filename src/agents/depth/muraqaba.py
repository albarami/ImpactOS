"""Step 2: Muraqaba — Bias Register.

The Al-Muhasabi structured reasoning methodology and framework are the
intellectual property of Salim Al-Barami, licensed to Strategic Gears
for use within ImpactOS. The software implementation, prompt engineering,
and system integration are part of the ImpactOS platform.

Analyzes candidate directions for cognitive biases.

MVP-9 Enhancement: generates AssumptionDraft objects from detected biases,
surfacing implicit assumptions that need formal governance review.

RESTRICTED fallback: heuristic bias detection based on candidate patterns:
- Anchoring if only 1 candidate
- Optimism if all candidates are upside
- Availability if candidates cluster in one sector
- Status quo if all source_types are 'nafs'
"""

import logging
from uuid import UUID

from src.agents.depth.base import DepthStepAgent
from src.agents.depth.prompts.muraqaba import build_prompt
from src.agents.llm_client import LLMClient
from src.models.common import AssumptionType, DataClassification
from src.models.depth import (
    AssumptionDraft,
    BiasEntry,
    BiasRegister,
    DepthStepName,
    MuraqabaOutput,
)

logger = logging.getLogger(__name__)


def _detect_biases_heuristically(candidates: list[dict]) -> BiasRegister:
    """Detect cognitive biases using deterministic heuristics.

    Rules:
    - Anchoring: only 1 candidate direction
    - Optimism: all candidates are 'nafs' or 'insight' with no stress tests
    - Availability: >60% of candidates share the same primary sector
    - Status quo: all source_types are 'nafs'
    - Groupthink: all candidates use the same required_levers
    """
    entries: list[BiasEntry] = []
    direction_ids = [
        UUID(c["direction_id"]) if isinstance(c.get("direction_id"), str) else c.get("direction_id")
        for c in candidates
        if c.get("direction_id")
    ]

    # Anchoring: exactly 1 candidate (0 candidates is not a bias — it's empty input)
    if len(candidates) == 1:
        entries.append(BiasEntry(
            bias_type="anchoring",
            description="Only 1 candidate direction — risk of anchoring to a single view",
            affected_directions=direction_ids,
            severity=8.0,
        ))

    # Status quo: all nafs
    source_types = [c.get("source_type", "") for c in candidates]
    if candidates and all(s == "nafs" for s in source_types):
        entries.append(BiasEntry(
            bias_type="status_quo",
            description=(
                "All candidate directions are 'nafs' (comfortable/ego-driven)"
                " — no analytically grounded alternatives"
            ),
            affected_directions=direction_ids,
            severity=7.0,
        ))

    # Optimism: no stress directions
    has_stress = any(
        "stress" in c.get("label", "").lower()
        or "constraint" in c.get("label", "").lower()
        or "delay" in c.get("label", "").lower()
        for c in candidates
    )
    if candidates and not has_stress and len(candidates) > 1:
        entries.append(BiasEntry(
            bias_type="optimism",
            description=(
                "No stress test or downside scenarios in candidate directions"
                " — risk of optimism bias"
            ),
            affected_directions=direction_ids,
            severity=6.0,
        ))

    # Availability: sector clustering
    if candidates:
        all_sectors: list[str] = []
        for c in candidates:
            all_sectors.extend(c.get("sector_codes", []))
        if all_sectors:
            from collections import Counter
            sector_counts = Counter(all_sectors)
            most_common_count = sector_counts.most_common(1)[0][1]
            if most_common_count > len(candidates) * 0.6:
                entries.append(BiasEntry(
                    bias_type="availability",
                    description=(
                        "Over 60% of candidates reference the same sector"
                        " — risk of availability bias"
                    ),
                    affected_directions=direction_ids,
                    severity=5.0,
                ))

    # Groupthink: identical lever sets
    if len(candidates) > 2:
        lever_sets = [
            frozenset(c.get("required_levers", []))
            for c in candidates
        ]
        unique_lever_sets = set(lever_sets)
        if len(unique_lever_sets) == 1 and lever_sets[0]:
            entries.append(BiasEntry(
                bias_type="groupthink",
                description=(
                    "All candidates use identical engine levers"
                    " — consider diversifying modeling approaches"
                ),
                affected_directions=direction_ids,
                severity=4.0,
            ))

    # Overall risk
    if entries:
        overall = min(max(e.severity for e in entries), 10.0)
    else:
        overall = 0.0

    return BiasRegister(entries=entries, overall_bias_risk=overall)


def _surface_assumption_drafts(
    bias_register: BiasRegister,
    candidates: list[dict],
) -> list[AssumptionDraft]:
    """Surface implicit assumptions from detected biases.

    MVP-9 Amendment 5: each detected bias generates a draft assumption
    that can be promoted into the formal AssumptionRegister for governance.

    Rules:
    - anchoring  -> STRUCTURAL assumption about limited exploration
    - status_quo -> BEHAVIORAL assumption about comfort-zone thinking
    - optimism   -> BEHAVIORAL assumption about upside-only framing
    - availability -> STRUCTURAL assumption about sector concentration
    - groupthink -> BEHAVIORAL assumption about lever homogeneity
    """
    drafts: list[AssumptionDraft] = []

    # Map bias types to assumption templates.
    # AssumptionType uses governed economic categories (IMPORT_SHARE, PHASING, etc.)
    # We use CAPACITY_CAP for structural constraints and PHASING for temporal assumptions.
    bias_to_assumption: dict[str, tuple[AssumptionType, str, str]] = {
        "anchoring": (
            AssumptionType.CAPACITY_CAP,
            "Limited scenario exploration",
            "Only one candidate direction was explored, risking anchoring "
            "to a single analytical perspective.",
        ),
        "status_quo": (
            AssumptionType.PHASING,
            "Status quo bias in direction generation",
            "All candidate directions are ego-driven (nafs), suggesting "
            "the analysis stays within comfortable/familiar territory.",
        ),
        "optimism": (
            AssumptionType.PHASING,
            "Optimism bias — no downside scenarios",
            "No stress test or downside scenarios were generated, risking "
            "systematic under-estimation of adverse outcomes.",
        ),
        "availability": (
            AssumptionType.IMPORT_SHARE,
            "Sector concentration in scenario directions",
            "Candidate directions cluster heavily in a single sector, "
            "potentially missing cross-sector spillover effects.",
        ),
        "groupthink": (
            AssumptionType.CAPACITY_CAP,
            "Homogeneous modeling approach",
            "All candidates use identical engine levers, suggesting "
            "insufficient diversity in analytical methodology.",
        ),
    }

    for entry in bias_register.entries:
        template = bias_to_assumption.get(entry.bias_type)
        if template is None:
            continue

        assumption_type, name, description = template
        drafts.append(AssumptionDraft(
            name=name,
            description=description,
            assumption_type=assumption_type,
            proposed_value=f"severity={entry.severity:.1f}",
            rationale=entry.description,
        ))

    return drafts


def _assess_framing(candidates: list[dict]) -> str | None:
    """Assess the overall framing of candidate directions.

    Returns a brief framing assessment string or None if no candidates.
    """
    if not candidates:
        return None

    source_types = [c.get("source_type", "") for c in candidates]
    insight_count = sum(1 for s in source_types if s == "insight")
    nafs_count = sum(1 for s in source_types if s == "nafs")
    total = len(candidates)

    if nafs_count == total:
        return "All directions are ego-driven (nafs) — consider adding analytical alternatives."
    if insight_count == total:
        return "All directions are insight-driven — well-grounded but may lack creative stretch."
    if insight_count / total >= 0.6:
        return f"Mostly analytical ({insight_count}/{total} insight) — good analytical grounding."

    return f"Mixed framing: {insight_count} insight, {nafs_count} nafs out of {total} total."


def _identify_missing_perspectives(candidates: list[dict]) -> list[str]:
    """Identify analytical perspectives not covered by current candidates.

    Checks for common gaps: demand-side only, no supply disruption,
    no regulatory scenarios, no technology change, no workforce impacts.
    """
    missing: list[str] = []
    if not candidates:
        return missing

    labels_lower = " ".join(c.get("label", "").lower() for c in candidates)
    descriptions_lower = " ".join(c.get("description", "").lower() for c in candidates)
    all_text = labels_lower + " " + descriptions_lower

    # Check for common missing perspectives
    if "supply" not in all_text and "disruption" not in all_text:
        missing.append("Supply-side disruption scenarios")
    if "regul" not in all_text and "policy" not in all_text:
        missing.append("Regulatory or policy change scenarios")
    if "tech" not in all_text and "innov" not in all_text and "digital" not in all_text:
        missing.append("Technology or innovation scenarios")
    if "workforce" not in all_text and "labor" not in all_text and "employ" not in all_text:
        missing.append("Workforce and employment impact scenarios")

    return missing


class MuraqabaAgent(DepthStepAgent):
    """Step 2: Detect cognitive biases in candidate directions.

    MVP-9 enhancements:
    - Generates AssumptionDraft objects from detected biases
    - Assesses overall framing of directions
    - Identifies missing analytical perspectives
    """

    step_name = DepthStepName.MURAQABA

    def run(
        self,
        *,
        context: dict,
        llm_client: LLMClient | None = None,
        classification: DataClassification = DataClassification.INTERNAL,
    ) -> dict:
        """Analyze candidates for biases.

        Returns MuraqabaOutput.model_dump(mode="json").
        """
        candidates = context.get("candidates", [])

        if self._can_use_llm(llm_client, classification):
            return self._run_with_llm(context, llm_client, classification)

        logger.info("Muraqaba: using heuristic bias detection (fallback)")
        register = _detect_biases_heuristically(candidates)
        assumption_drafts = _surface_assumption_drafts(register, candidates)
        framing = _assess_framing(candidates)
        missing = _identify_missing_perspectives(candidates)
        output = MuraqabaOutput(
            bias_register=register,
            assumption_drafts=assumption_drafts,
            framing_assessment=framing,
            missing_perspectives=missing,
        )
        return output.model_dump(mode="json")

    def _run_with_llm(
        self,
        context: dict,
        llm_client: LLMClient,
        classification: DataClassification,
    ) -> dict:
        """Detect biases using LLM."""
        prompt = build_prompt(context)
        logger.info("Muraqaba: LLM mode — prompt built (%d chars)", len(prompt))

        # For MVP, use heuristic fallback + LLM prompt ready
        candidates = context.get("candidates", [])
        register = _detect_biases_heuristically(candidates)
        assumption_drafts = _surface_assumption_drafts(register, candidates)
        framing = _assess_framing(candidates)
        missing = _identify_missing_perspectives(candidates)
        output = MuraqabaOutput(
            bias_register=register,
            assumption_drafts=assumption_drafts,
            framing_assessment=framing,
            missing_perspectives=missing,
        )
        return output.model_dump(mode="json")
