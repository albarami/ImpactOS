"""Prompt template for Step 5: Suite Planning.

Assembles the final scenario suite from scored/accepted candidates.
Produces executable SuiteRuns that can be fed to the compiler/engine.
"""


def build_prompt(context: dict) -> str:
    """Build the Suite Planning prompt from scored candidates + risks.

    Expected context keys:
    - scored (list[dict]): ScoredCandidate dicts from Step 4
    - qualitative_risks (list[dict]): QualitativeRisk dicts from Step 3
    - workspace_id (str): Workspace UUID
    - sector_codes (list[str]): Available sectors
    """
    scored = context.get("scored", [])
    risks = context.get("qualitative_risks", [])
    workspace_id = context.get("workspace_id", "unknown")

    accepted = [s for s in scored if s.get("accepted", False)]
    rejected = [s for s in scored if not s.get("accepted", False)]

    lines = [
        "You are the Suite Planner of the Al-Muhasabi Depth Engine.",
        "Your task is to assemble the FINAL scenario suite from",
        "accepted candidates into executable runs.",
        "",
        "CRITICAL RULES:",
        "- You produce STRUCTURED JSON only. Never compute economic numbers.",
        "- Each run must have executable_levers with valid types:",
        "  FINAL_DEMAND_SHOCK, IMPORT_SHARE_ADJUSTMENT,",
        "  LOCAL_CONTENT_TARGET, PHASING_SHIFT,",
        "  CONSTRAINT_SET_TOGGLE, SENSITIVITY_SWEEP",
        "- Include recommended_outputs: what metrics to compute",
        "  (multipliers, jobs, imports, variance_bridge, etc.)",
        "- Suite plan disclosure_tier defaults to TIER1",
        "- Qualitative risks carry over (not_modeled=true always)",
        "",
        f"ACCEPTED DIRECTIONS ({len(accepted)}):",
    ]

    for s in accepted:
        label = s.get("label", "?")
        score = s.get("composite_score", 0)
        contrarian = s.get("is_contrarian", False)
        lines.append(f"  - {label} (score: {score}, contrarian: {contrarian})")

    if rejected:
        lines.append(f"\nREJECTED ({len(rejected)}):")
        for s in rejected:
            lines.append(f"  - {s.get('label', '?')}: {s.get('rejection_reason', '?')}")

    if risks:
        lines.append(f"\nQUALITATIVE RISKS ({len(risks)}):")
        for r in risks:
            lines.append(f"  - {r.get('label', '?')}: {r.get('description', '?')}")

    lines.extend([
        "",
        "Respond with JSON:",
        '{"suite_plan": {',
        f'  "workspace_id": "{workspace_id}",',
        '  "runs": [',
        '    {"name": "...", "direction_id": "uuid",',
        '     "executable_levers": [',
        '       {"type": "FINAL_DEMAND_SHOCK", "sector": "...",',
        '        "value": 100000}',
        '     ],',
        '     "mode": "SANDBOX",',
        '     "sensitivities": ["import_share", ...],',
        '     "disclosure_tier": "TIER1"}',
        '  ],',
        '  "recommended_outputs": ["multipliers", "jobs", ...],',
        '  "qualitative_risks": [...],',
        '  "rationale": "...",',
        '  "disclosure_tier": "TIER1"',
        "}}",
    ])

    return "\n".join(lines)
