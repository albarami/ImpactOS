"""Prompt template for Step 4: Muhasaba (Self-Accounting Scoring).

Scores and ranks ALL candidates (regular + contrarian) on
novelty, feasibility, and data availability. Explicitly accepts
or rejects each with documented rationale.
"""


def build_prompt(context: dict) -> str:
    """Build the Muhasaba prompt from all candidates.

    Expected context keys:
    - candidates (list[dict]): CandidateDirection dicts from Step 1
    - contrarians (list[dict]): ContrarianDirection dicts from Step 3
    """
    candidates = context.get("candidates", [])
    contrarians = context.get("contrarians", [])

    lines = [
        "You are the Muhasaba module of the Al-Muhasabi Depth Engine.",
        "Your task is to SCORE and RANK all candidate directions.",
        "",
        "CRITICAL RULES:",
        "- You produce STRUCTURED JSON only. Never compute economic numbers.",
        "- Score each direction on 3 axes (0-10):",
        "  novelty_score: How novel/non-obvious is this direction?",
        "  feasibility_score: Can it be modeled with available engine levers?",
        "  data_availability_score: Is the data available to parameterize it?",
        "- composite_score = weighted average (you decide weights)",
        "- Rank from 1 (best) to N",
        "- EXPLICITLY accept or reject each direction:",
        "  accepted=true: direction proceeds to suite planning",
        "  accepted=false: must include rejection_reason",
        "- Threshold guidance: novelty >= 7.0 flags high-novelty",
        "- Reject directions with composite_score < 3.0 as low-quality",
        "",
        f"REGULAR CANDIDATES ({len(candidates)}):",
    ]

    for i, c in enumerate(candidates, 1):
        label = c.get("label", "?")
        source = c.get("source_type", "?")
        levers = c.get("required_levers", [])
        lines.append(f"  {i}. [{source}] {label} (levers: {levers})")

    lines.append(f"\nCONTRARIAN CANDIDATES ({len(contrarians)}):")
    for i, c in enumerate(contrarians, 1):
        label = c.get("label", "?")
        quant = c.get("is_quantifiable", False)
        lines.append(f"  {i}. {label} (quantifiable: {quant})")

    lines.extend([
        "",
        "Respond with JSON:",
        '{"scored": [',
        '  {"direction_id": "uuid",',
        '   "label": "...",',
        '   "composite_score": 0.0-10.0,',
        '   "novelty_score": 0.0-10.0,',
        '   "feasibility_score": 0.0-10.0,',
        '   "data_availability_score": 0.0-10.0,',
        '   "is_contrarian": true|false,',
        '   "rank": 1,',
        '   "accepted": true|false,',
        '   "rejection_reason": "..." or null}',
        "]}",
    ])

    return "\n".join(lines)
