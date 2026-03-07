# ImpactOS Gap Closure — Blocker Ledger

**Branch:** `gap-closure-verified`
**Baseline:** `c5eb3d5` (phase3-sprint31)
**Created:** 2026-03-07

---

## Blocker Status Key

| Status | Meaning |
|--------|---------|
| `open` | Known gap, not yet started |
| `in_progress` | Work underway, not verified |
| `verified_closed` | Implementation complete, tests pass, verified |

---

## Phase 0: Security Reset and Truth Baseline

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P0-1 | Exposed API keys in .env (Anthropic, OpenAI, OpenRouter) | verified_closed | Keys blanked in .env, user notified to rotate on provider dashboards | pending |
| P0-2 | Blocker ledger does not exist | verified_closed | This file | pending |
| P0-3 | Isolated worktree for closure work | verified_closed | `gap-closure-verified` branch at `.claude/worktrees/gap-closure` | pending |
| P0-4 | Readiness claims in docs/evidence not frozen | open | — | — |

---

## Phase 1: Data Integrity and Denomination Safety

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P1-1 | ModelVersion has no denomination field | open | — | — |
| P1-2 | Seed defaults point to 2018 instead of 2023 | open | — | — |
| P1-3 | Engine unit safety not enforced end-to-end | open | — | — |
| P1-4 | Import ratios default to flat 0.15 for real data | open | — | — |
| P1-5 | No real-model regression test proving SAR-scale output | open | — | — |

---

## Phase 2: Copilot Contract and Orchestration Integrity

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P2-1 | Prompt/tool contract mismatch | open | — | — |
| P2-2 | lookup_data is a hardcoded stub | open | — | — |
| P2-3 | LLM-mediated cross-turn scenario_spec_id reuse | open | — | — |
| P2-4 | Pending action approval does not execute stored tool intent | open | — | — |
| P2-5 | narrate_results reads real persisted data | open | — | — |
| P2-6 | create_export executes real orchestration | open | — | — |

---

## Phase 3: Al-Muhasabi Depth Engine Reality Gap

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P3-1 | LLM mode dead-lettered (all 5 agents) | open | — | — |
| P3-2 | Suite planner hard cap at 5 | open | — | — |
| P3-3 | No sensitivity sweep expansion | open | — | — |
| P3-4 | No polarity guard in Muhasaba | open | — | — |
| P3-5 | Candidate generation is generic, not question-calibrated | open | — | — |
| P3-6 | Munazara (step 6) decision: include or defer | open | — | — |

---

## Phase 4: Governance Autowiring and Disclosure Enforcement

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P4-1 | Claims not auto-created post-run | open | — | — |
| P4-2 | Draft assumptions not auto-created on scenario build | open | — | — |
| P4-3 | Publication gate is claim-only (should also block on assumptions) | open | — | — |
| P4-4 | Tiered disclosure not enforced in exports | open | — | — |
| P4-5 | Workspace isolation gaps in repositories | open | — | — |

---

## Phase 5: Main Run Path Completeness

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P5-1 | Sector breakdowns not fully populated | open | — | — |
| P5-2 | Workforce satellite not on main run path | open | — | — |
| P5-3 | Feasibility layer not on main run path | open | — | — |
| P5-4 | Report data not packaged for UI consumption | open | — | — |

---

## Phase 6: Frontend Decision Pack and Product Surface

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P6-1 | Raw JSON in chat messages | open | — | — |
| P6-2 | Executive summary missing | open | — | — |
| P6-3 | KPI cards missing denomination scaling | open | — | — |
| P6-4 | Suite list, risks, workforce, sector breakdown missing | open | — | — |
| P6-5 | Markdown not rendered in chat | open | — | — |
| P6-6 | Download flow incomplete | open | — | — |

---

## Phase 7: Infrastructure and Live End-to-End Proof

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P7-1 | External IdP not provisioned | open | — | — |
| P7-2 | Strong SECRET_KEY not generated | open | — | — |
| P7-3 | Staging database not provisioned | open | — | — |
| P7-4 | Staging Redis not provisioned | open | — | — |
| P7-5 | Staging object storage not provisioned | open | — | — |
| P7-6 | LLM API keys not configured for staging | open | — | — |
| P7-7 | Staging DNS/URL not allocated | open | — | — |
| P7-8 | Full E2E harness never executed on live staging | open | — | — |
