"""Prompt template for Step 2: Muraqaba (Bias Register).

Analyzes candidate directions for cognitive biases.
"""


def build_prompt(context: dict) -> str:
    """Build the Muraqaba prompt from candidates context.

    Expected context keys:
    - candidates (list[dict]): CandidateDirection dicts from Step 1
    """
    candidates = context.get("candidates", [])

    lines = [
        "You are the Muraqaba module of the Al-Muhasabi Depth Engine.",
        "Your task is to detect COGNITIVE BIASES in scenario directions.",
        "",
        "CRITICAL RULES:",
        "- You produce STRUCTURED JSON only. Never compute economic numbers.",
        "- Check for: anchoring, availability, optimism, groupthink,",
        "  confirmation bias, representativeness, status quo bias",
        "- Each bias entry must reference which directions it affects",
        "- Overall bias risk score: 0 (no bias) to 10 (severe bias)",
        "",
        f"CANDIDATE DIRECTIONS ({len(candidates)} total):",
    ]

    for i, c in enumerate(candidates, 1):
        label = c.get("label", "Unknown")
        source = c.get("source_type", "?")
        lines.append(f"  {i}. [{source}] {label}")

    lines.extend([
        "",
        "HEURISTIC INDICATORS:",
        "- If only 1 direction: suspect anchoring bias",
        "- If all directions are upside: suspect optimism bias",
        "- If directions cluster in one sector: suspect availability bias",
        "- If all source_types are 'nafs': suspect status quo bias",
        "",
        "Respond with JSON matching this schema:",
        '{"bias_register": {',
        '  "entries": [',
        '    {"bias_type": "anchoring"|"optimism"|...,',
        '     "description": "...",',
        '     "affected_directions": ["uuid1", ...],',
        '     "severity": 0.0-10.0}',
        '  ],',
        '  "overall_bias_risk": 0.0-10.0',
        "}}",
    ])

    return "\n".join(lines)
