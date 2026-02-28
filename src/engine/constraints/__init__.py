"""Feasibility & Constraint Layer — MVP-10.

Applies real-world constraints to unconstrained IO model results,
producing two sets of outputs: unconstrained (theoretical upper bound)
and feasible (constrained to what can actually be delivered).

The difference quantifies the deliverability gap — the Saudi credibility
differentiator.

This module is DETERMINISTIC — no LLM calls.
"""
