"""Prompt template for Step 1: Khawatir (Candidate Direction Generation).

Generates 3-7 candidate scenario directions from workspace context.
Each direction is labeled with Al-Muhasabi source_type: nafs/waswas/insight.
"""


def build_prompt(context: dict) -> str:
    """Build the Khawatir prompt from scenario context.

    Expected context keys:
    - workspace_description (str): What the workspace/engagement is about
    - sector_codes (list[str]): Available sector codes in the model
    - existing_shocks (list[dict]): Current shock items in the scenario
    - time_horizon (dict): start_year, end_year
    - import_share (float, optional): Current average import share
    - capex_profile (str, optional): e.g. "heavy_infrastructure"
    """
    ws_desc = context.get("workspace_description", "Economic impact assessment")
    sectors = context.get("sector_codes", [])
    shocks = context.get("existing_shocks", [])
    horizon = context.get("time_horizon", {})

    lines = [
        "You are the Khawatir module of the Al-Muhasabi Depth Engine.",
        "Your task is to generate 5-7 CANDIDATE scenario directions.",
        "",
        "CRITICAL RULES:",
        "- You produce STRUCTURED JSON only. Never compute economic numbers.",
        "- Each direction MUST have a source_type label:",
        '  "nafs" = ego-driven/comfortable (the easy option)',
        '  "waswas" = noise/distraction (not analytically grounded)',
        '  "insight" = analytically grounded (novel, testable)',
        "- Each direction MUST have a test_plan explaining HOW to model it",
        "- Each direction MUST list required_levers from:",
        "  FINAL_DEMAND_SHOCK, IMPORT_SUBSTITUTION, LOCAL_CONTENT,",
        "  CONSTRAINT_OVERRIDE",
        "",
        f"WORKSPACE CONTEXT: {ws_desc}",
    ]

    if sectors:
        lines.append(f"AVAILABLE SECTORS: {', '.join(sectors[:20])}")

    if shocks:
        lines.append(f"EXISTING SHOCKS ({len(shocks)} items): "
                      f"{str(shocks[:3])}...")

    if horizon:
        lines.append(
            f"TIME HORIZON: {horizon.get('start_year', '?')}"
            f" - {horizon.get('end_year', '?')}"
        )

    lines.extend([
        "",
        "Generate directions that span the range from comfortable to",
        "challenging. Include at least 1 'nafs' and 1 'insight' direction.",
        "",
        "Respond with JSON matching this schema:",
        '{"candidates": [',
        '  {"label": "...", "description": "...",',
        '   "sector_codes": ["SEC01", ...],',
        '   "rationale": "...",',
        '   "source_type": "nafs"|"waswas"|"insight",',
        '   "test_plan": "How to model this with engine levers",',
        '   "required_levers": ["FINAL_DEMAND_SHOCK", ...]}',
        "]}",
    ])

    return "\n".join(lines)
