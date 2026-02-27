"""Step 2: Muraqaba — Bias Register.

Analyzes candidate directions for cognitive biases.

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
from src.models.common import DataClassification
from src.models.depth import (
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


class MuraqabaAgent(DepthStepAgent):
    """Step 2: Detect cognitive biases in candidate directions."""

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
        output = MuraqabaOutput(bias_register=register)
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
        output = MuraqabaOutput(bias_register=register)
        return output.model_dump(mode="json")
