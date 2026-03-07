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
| P1-1 | ModelVersion has no denomination field | verified_closed | `model_denomination` field on ModelVersion, LoadedModel, IOModelData; Alembic migration 021; 11 tests pass | 3e80d44 |
| P1-2 | Seed defaults point to 2018 instead of 2023 | verified_closed | `scripts/seed.py` updated: year=2023, denomination propagated | 3e80d44 |
| P1-3 | Engine unit safety not enforced end-to-end | verified_closed | OutputDenomination enum in common.py, denomination_factor() rejects UNKNOWN, re-export in unit_registry | 3e80d44 |
| P1-4 | Import ratios default to flat 0.15 for real data | verified_closed | Real KAPSARC 2023 data loaded with correct denomination; import ratios come from curated JSON | 3e80d44 |
| P1-5 | No real-model regression test proving SAR-scale output | verified_closed | `test_real_model_regression.py`: 1B SAR construction shock → multiplier 1.0-5.0 verified | 3e80d44 |

---

## Phase 2: Copilot Contract and Orchestration Integrity

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P2-1 | Prompt/tool contract mismatch | verified_closed | Audit confirmed: all 5 tools aligned between prompt and executor | 730eec7 |
| P2-2 | lookup_data is a hardcoded stub | verified_closed | Real data queries: io_tables returns sector_codes/output/denomination, models lists versions; 7 tests | 730eec7 |
| P2-3 | LLM-mediated cross-turn scenario_spec_id reuse | verified_closed | Stored intent replay: _find_pending_intent retrieves from DB, executes directly | 730eec7 |
| P2-4 | Pending action approval does not execute stored tool intent | verified_closed | _replay_stored_intent skips LLM, replays exact stored args; 4 tests prove copilot NOT re-invoked | 730eec7 |
| P2-5 | narrate_results reads real persisted data | verified_closed | Audit confirmed: reads ResultSet rows from DB, not hardcoded | 730eec7 |
| P2-6 | create_export executes real orchestration | verified_closed | Audit confirmed: ExportExecutionService handles governance + artifact generation | 730eec7 |

---

## Phase 3: Al-Muhasabi Depth Engine Reality Gap

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P3-1 | LLM mode dead-lettered (all 5 agents) | verified_closed | All 5 agents async, call llm_client.call() with structured output; fallback on parse failure; 12 tests | 555de1d |
| P3-2 | Suite planner hard cap at 5 | verified_closed | max_runs read from context, default 5; 3 tests prove configurable | 555de1d |
| P3-3 | No sensitivity sweep expansion | verified_closed | Sensitivities are dicts with type+range/values, not strings; 2 tests | 555de1d |
| P3-4 | No polarity guard in Muhasaba | verified_closed | model_validator on MuhasabaOutput sets polarity_warning when all-upside; 2 tests | 555de1d |
| P3-5 | Candidate generation is generic, not question-calibrated | verified_closed | _generate_fallback_candidates reads key_questions, generates question-driven CandidateDirections; 1 test | 555de1d |
| P3-6 | Munazara (step 6) decision: include or defer | verified_closed | Deferred by design — Munazara is a future step; documented | 555de1d |

---

## Phase 4: Governance Autowiring and Disclosure Enforcement

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P4-1 | Claims not auto-created post-run | verified_closed | create_claims_from_results() generates MODEL claims from result_summary; 6 tests | 92838eb |
| P4-2 | Draft assumptions not auto-created on scenario build | verified_closed | draft_compilation_assumptions() creates IMPORT_SHARE/PHASING/DEFLATOR; compile() sets assumptions_count; 7 tests | 92838eb |
| P4-3 | Publication gate is claim-only (should also block on assumptions) | verified_closed | PublicationGate.check() accepts assumptions kwarg; DRAFT blocks publication; 6 tests | 92838eb |
| P4-4 | Tiered disclosure not enforced in exports | verified_closed | ExportOrchestrator filters TIER0 from pack_data in GOVERNED mode; ExportRecord.filtered_tier0_count; 3 tests | 92838eb |
| P4-5 | Workspace isolation gaps in repositories | verified_closed | ClaimRepository.list_by_workspace() with pagination+status filter via RunSnapshot join; 2 tests | 92838eb |

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
