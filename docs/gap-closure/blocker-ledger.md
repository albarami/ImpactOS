# ImpactOS Gap Closure — Blocker Ledger

**Branch:** `gap-closure-verified`
**Baseline:** `c5eb3d5` (phase3-sprint31)
**Created:** 2026-03-07

---

## Blocker Status Key

| Status | Meaning |
|--------|---------|
| `open` | Known gap, not yet started |
| `reopened` | Previously claimed closed, gaps found on review, reopened |
| `in_progress` | Work underway, not verified |
| `verified_closed` | Implementation complete, tests pass, verified on real paths |
| `blocked_external` | Code ready, awaiting external provisioning |

---

## Phase 0: Security Reset and Truth Baseline

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P0-1 | Exposed API keys in .env (Anthropic, OpenAI, OpenRouter) | verified_closed | Keys blanked in .env, user confirmed rotation complete | pending |
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
| P1-4 | Import ratios default to flat 0.15 for real data | reopened | `satellite_coeff_loader.py` still falls back to flat 0.15 for curated IO import ratios; need real sector-specific ratios for Saudi model | 3e80d44 |
| P1-5 | No real-model regression test proving SAR-scale output | verified_closed | `test_real_model_regression.py`: 1B SAR construction shock -> multiplier 1.0-5.0 verified | 3e80d44 |

---

## Phase 2: Copilot Contract and Orchestration Integrity

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P2-1 | Prompt/tool contract mismatch | verified_closed | build_scenario prompt+tool_def now includes base_model_version_id; create_export uses "excel" not "xlsx"; lookup_data description+_AVAILABLE_DATASETS trimmed to io_tables+models only; model_version_id added to lookup_data params; 8 contract tests | 93ce242 |
| P2-2 | lookup_data is a hardcoded stub | verified_closed | employment_coefficients handler queries EmploymentCoefficientsRepository.get_by_model_version(); returns real coefficients with sector_code, jobs_per_million_sar, confidence; sector filtering; multipliers+macro_indicators removed (no data); 5 tests | pending |
| P2-3 | LLM-mediated cross-turn scenario_spec_id reuse | verified_closed | ChatService._extract_prior_ids() scans prior trace_metadata and injects prior_scenario_spec_id, prior_run_id, prior_model_version_id, prior_export_id into copilot context; build_system_prompt() emits PRIOR CONTEXT section; 3 tests | pending |
| P2-4 | Pending action approval does not execute stored tool intent | verified_closed | _replay_stored_intent skips LLM, replays exact stored args; 4 tests prove copilot NOT re-invoked | 730eec7 |
| P2-5 | narrate_results reads real persisted data | verified_closed | Reads ResultSet rows from DB, workspace-scoped | 730eec7 |
| P2-6 | create_export executes real orchestration | verified_closed | ExportExecutionService handles governance + artifact generation | 730eec7 |

---

## Phase 3: Al-Muhasabi Depth Engine Reality Gap

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P3-1 | Depth engine not in copilot flow | reopened | No depth-suite tool in chat flow; economist_copilot_v1.py and chat_tool_executor.py expose only 5 tools (lookup_data, build_scenario, run_engine, narrate_results, create_export); depth engine only reachable via standalone /depth/plans API | 555de1d |
| P3-2 | Suite planner default too low | reopened | _MAX_RUNS = 5; configurable but product requirement is 20+ default scenarios | 555de1d |
| P3-3 | Sensitivity sweeps not executable | reopened | Sensitivities are metadata dicts on SuiteRun, not materialized as executable scenario variants | 555de1d |
| P3-4 | Polarity guard not question-aware | reopened | polarity_warning only fires when no contrarians exist; does not prevent negative questions from producing upside-dominant scenarios | 555de1d |
| P3-5 | Depth prompts missing denomination; no parsed-LLM tests | reopened | Prompts do not include model denomination; tests only exercise fallback paths, no tests prove structured LLM responses are parsed into output objects | 555de1d |
| P3-6 | Suite planner emits placeholder lever values | reopened | _build_suite_from_scored emits `"value": 0` placeholder lever values; not real executable values | 555de1d |

---

## Phase 4: Governance Autowiring and Disclosure Enforcement

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P4-1 | Claims not auto-created on real run path | reopened | create_claims_from_results() helper exists but RunExecutionService.execute_from_scenario() does not call it; claims never auto-created on real engine run | 92838eb |
| P4-2 | Draft assumptions not auto-created on real build path | reopened | draft_compilation_assumptions() helper exists but build_scenario executor does not call it; assumptions never auto-created on real scenario build | 92838eb |
| P4-3 | Publication gate not receiving assumptions on real export path | reopened | Gate accepts assumptions kwarg but chat and API export paths do not load or pass assumptions | 92838eb |
| P4-4 | Tiered disclosure not enforced in exports | verified_closed | ExportOrchestrator filters TIER0 from pack_data in GOVERNED mode; ExportRecord.filtered_tier0_count; 3 tests | 92838eb |
| P4-5 | Workspace isolation gaps in repositories | verified_closed | ClaimRepository.list_by_workspace() with pagination+status filter via RunSnapshot join; 2 tests | 92838eb |

---

## Phase 5: Main Run Path Completeness

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P5-1 | Sector breakdowns not fully populated | verified_closed | BatchRunner populates sector_breakdowns on total_output; 5 tests | d5a5b91 |
| P5-2 | Workforce satellite not on main run path | reopened | Chat path loads curated coefficients but API path accepts from request body — workforce is not auto-loaded and persisted on the main run path | d5a5b91 |
| P5-3 | Feasibility layer not on main run path | reopened | ClippingSolver exists as standalone API; not integrated into the main run path; must be invoked and results persisted | — |
| P5-4 | Report data not packaged for UI consumption | verified_closed | ResultPackager converts ResultSet rows -> pack_data; 6 tests | d5a5b91 |

---

## Phase 6: Frontend Decision Pack and Product Surface

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P6-1 | Raw JSON in chat messages | verified_closed | Structured result summary; raw JSON behind toggle; 3 tests | 33588e0 |
| P6-2 | Executive summary missing | verified_closed | KPI cards (Total Output, GDP Impact, Jobs Created); 3 tests | 33588e0 |
| P6-3 | KPI cards missing denomination scaling | reopened | Hardcoded "SAR" label appended; not wired from backend denomination metadata; invalid aggregate Total Impact calculation | 33588e0 |
| P6-4 | Suite list, risks, workforce, sector breakdown missing | open | Frontend does not model sector_breakdowns, workforce, feasibility, suite outputs, or depth artifacts | — |
| P6-5 | Markdown not rendered in chat | verified_closed | react-markdown; assistant=markdown, user=plain; 3 tests | 33588e0 |
| P6-6 | Download flow incomplete | verified_closed | Download buttons per format; 2 tests | 33588e0 |

---

## Phase 7: Infrastructure and Live End-to-End Proof

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P7-1 | External IdP not provisioned | blocked_external | Code ready (dual-mode JWT, OIDC frontend); awaiting IdP provisioning | — |
| P7-2 | Strong SECRET_KEY not generated | blocked_external | Validation enforced at startup; awaiting generation | — |
| P7-3 | Staging database not provisioned | blocked_external | 22 Alembic migrations ready; awaiting DBA | — |
| P7-4 | Staging Redis not provisioned | blocked_external | Optional, graceful degradation; awaiting provisioning | — |
| P7-5 | Staging object storage not provisioned | blocked_external | S3-compatible design; awaiting provisioning | — |
| P7-6 | LLM API keys not configured for staging | blocked_external | Optional; awaiting key generation | — |
| P7-7 | Staging DNS/URL not allocated | blocked_external | Env-driven; awaiting allocation | — |
| P7-8 | Full E2E harness never executed on live staging | blocked_external | 15-stage pipeline ready; awaiting P7-1 through P7-7 | — |
