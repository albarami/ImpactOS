"""Prompt template for Step 3: Mujahada (Contrarian Challenge).

Generates contrarian directions that challenge base scenario assumptions.
All outputs default TIER0 (internal only).
"""


def build_prompt(context: dict) -> str:
    """Build the Mujahada prompt from candidates + bias register.

    Expected context keys:
    - candidates (list[dict]): CandidateDirection dicts from Step 1
    - bias_register (dict): BiasRegister from Step 2
    - workspace_description (str): Engagement context
    - sector_codes (list[str]): Available sectors
    """
    candidates = context.get("candidates", [])
    bias = context.get("bias_register", {})
    ws_desc = context.get("workspace_description", "Economic impact assessment")

    lines = [
        "You are the Mujahada module of the Al-Muhasabi Depth Engine.",
        "Your task is to generate CONTRARIAN directions that challenge",
        "the comfortable assumptions underlying the base scenario.",
        "",
        "CRITICAL RULES:",
        "- You produce STRUCTURED JSON only. Never compute economic numbers.",
        "- Each contrarian MUST specify broken_assumption (which specific",
        "  base scenario assumption it challenges)",
        "- Mark is_quantifiable=true if the engine can model this",
        "- If quantifiable, provide quantified_levers (ShockItem-like dicts)",
        "- Generate 2-3 contrarian directions",
        "- Also generate qualitative_risks (risks the engine CANNOT model)",
        "- QualitativeRisk.not_modeled is ALWAYS true",
        "",
        f"WORKSPACE: {ws_desc}",
        "",
        f"EXISTING CANDIDATES ({len(candidates)}):",
    ]

    for c in candidates:
        lines.append(f"  - [{c.get('source_type', '?')}] {c.get('label', '?')}")

    bias_risk = bias.get("overall_bias_risk", 0)
    bias_entries = bias.get("entries", [])
    lines.append(f"\nBIAS REGISTER: risk={bias_risk}, {len(bias_entries)} biases detected")

    lines.extend([
        "",
        "CONTRARIAN TEMPLATES TO CONSIDER:",
        "- Import stress: what if import costs surge?",
        "- Phasing delay: what if project timelines slip 2+ years?",
        "- Local content shortfall: what if domestic capacity is",
        "  overestimated?",
        "- Capacity cap: what if sector capacity limits bind?",
        "- Residual bucket expansion: what if unmapped spend grows?",
        "",
        "Respond with JSON:",
        '{"contrarians": [',
        '  {"label": "...", "description": "...",',
        '   "uncomfortable_truth": "...",',
        '   "sector_codes": [...], "rationale": "...",',
        '   "broken_assumption": "...",',
        '   "is_quantifiable": true|false,',
        '   "quantified_levers": [...] or null}',
        '],',
        ' "qualitative_risks": [',
        '  {"label": "...", "description": "...",',
        '   "not_modeled": true, "affected_sectors": [...]}',
        "]}",
    ])

    return "\n".join(lines)
