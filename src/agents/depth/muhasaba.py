"""Step 4: Muhasaba — Self-Accounting Scoring.

Scores and ranks ALL candidates (regular + contrarian) on novelty,
feasibility, and data availability. Explicitly accepts or rejects each
with documented rationale.

RESTRICTED fallback: deterministic scoring by rule weights.
"""

import logging
from uuid import UUID

from src.agents.depth.base import DepthStepAgent
from src.agents.depth.prompts.muhasaba import build_prompt
from src.agents.llm_client import LLMClient
from src.models.common import DataClassification
from src.models.depth import (
    DepthStepName,
    MuhasabaOutput,
    ScoredCandidate,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scoring weights for deterministic fallback
# ---------------------------------------------------------------------------

_NOVELTY_WEIGHTS = {
    "nafs": 2.0,      # Comfortable → low novelty
    "waswas": 1.0,     # Noise → very low
    "insight": 7.0,    # Analytically grounded → high novelty
}

_FEASIBILITY_BY_LEVER_COUNT = {
    0: 9.0,   # No levers needed (base case)
    1: 8.0,   # Single lever = very feasible
    2: 7.0,   # Two levers = feasible
    3: 5.5,   # Three levers = moderate
}

_CONTRARIAN_NOVELTY_BONUS = 2.0
_QUANTIFIABLE_FEASIBILITY_BONUS = 1.5
_MIN_COMPOSITE_THRESHOLD = 3.0


def _score_candidate(
    direction: dict,
    is_contrarian: bool,
    rank_offset: int,
) -> ScoredCandidate:
    """Score a single candidate using deterministic rules."""
    direction_id = direction.get("direction_id")
    if isinstance(direction_id, str):
        direction_id = UUID(direction_id)

    label = direction.get("label", "Unknown")
    source_type = direction.get("source_type", "insight")

    # Novelty score
    base_novelty = _NOVELTY_WEIGHTS.get(source_type, 5.0)
    if is_contrarian:
        base_novelty = min(base_novelty + _CONTRARIAN_NOVELTY_BONUS, 10.0)
    novelty = round(base_novelty, 1)

    # Feasibility score
    levers = direction.get("required_levers", [])
    lever_count = len(levers) if isinstance(levers, list) else 0
    base_feasibility = _FEASIBILITY_BY_LEVER_COUNT.get(
        min(lever_count, 3), 4.0,
    )
    if is_contrarian and direction.get("is_quantifiable", False):
        base_feasibility = min(
            base_feasibility + _QUANTIFIABLE_FEASIBILITY_BONUS, 10.0,
        )
    feasibility = round(base_feasibility, 1)

    # Data availability (heuristic: sectors with codes = data likely exists)
    sector_codes = direction.get("sector_codes", [])
    data_avail = 7.0 if sector_codes else 4.0
    data_avail = round(data_avail, 1)

    # Composite (equal weights)
    composite = round((novelty + feasibility + data_avail) / 3.0, 1)

    # Accept/reject
    accepted = composite >= _MIN_COMPOSITE_THRESHOLD
    rejection_reason = None
    if not accepted:
        rejection_reason = (
            f"Composite score {composite} below minimum threshold "
            f"{_MIN_COMPOSITE_THRESHOLD}"
        )

    return ScoredCandidate(
        direction_id=direction_id,
        label=label,
        composite_score=composite,
        novelty_score=novelty,
        feasibility_score=feasibility,
        data_availability_score=data_avail,
        is_contrarian=is_contrarian,
        rank=rank_offset + 1,  # Placeholder — re-ranked below
        accepted=accepted,
        rejection_reason=rejection_reason,
    )


def _score_all_candidates(context: dict) -> list[ScoredCandidate]:
    """Score all regular + contrarian candidates deterministically."""
    candidates = context.get("candidates", [])
    contrarians = context.get("contrarians", [])

    scored: list[ScoredCandidate] = []

    for i, c in enumerate(candidates):
        scored.append(_score_candidate(c, is_contrarian=False, rank_offset=i))

    for i, c in enumerate(contrarians):
        scored.append(_score_candidate(c, is_contrarian=True, rank_offset=len(candidates) + i))

    # Re-rank by composite_score descending
    scored.sort(key=lambda s: s.composite_score, reverse=True)
    for rank, sc in enumerate(scored, 1):
        sc.rank = rank

    return scored


class MuhasabaAgent(DepthStepAgent):
    """Step 4: Score and rank all candidate directions."""

    step_name = DepthStepName.MUHASABA

    def run(
        self,
        *,
        context: dict,
        llm_client: LLMClient | None = None,
        classification: DataClassification = DataClassification.INTERNAL,
    ) -> dict:
        """Score and rank all candidates.

        Returns MuhasabaOutput.model_dump(mode="json").
        """
        if self._can_use_llm(llm_client, classification):
            return self._run_with_llm(context, llm_client, classification)

        logger.info("Muhasaba: using deterministic scoring (fallback)")
        scored = _score_all_candidates(context)
        output = MuhasabaOutput(scored=scored)
        return output.model_dump(mode="json")

    def _run_with_llm(
        self,
        context: dict,
        llm_client: LLMClient,
        classification: DataClassification,
    ) -> dict:
        """Score candidates using LLM."""
        prompt = build_prompt(context)
        logger.info("Muhasaba: LLM mode — prompt built (%d chars)", len(prompt))

        # For MVP, use deterministic scoring
        scored = _score_all_candidates(context)
        output = MuhasabaOutput(scored=scored)
        return output.model_dump(mode="json")
