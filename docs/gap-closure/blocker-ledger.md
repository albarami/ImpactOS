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
| P1-4 | Import ratios default to flat 0.15 for real data | verified_closed | Curated saudi_import_ratios.json with 20 sector-specific ratios (A=0.18..T=0.03); _load_curated_import_ratios() loads before flat fallback; IO imports_vector supported if present; 4 tests | 370b1cb |
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
| P3-1 | Depth engine not in copilot flow | verified_closed | Depth suite reachable from chat: run_depth_suite added as 6th copilot tool (valid+gated); handler creates DepthPlan row and calls run_depth_plan() inline; prompt text+tool definition+confirmation gate all wired; 15 tests (7 prompt/definition + 4 handler × 2 backends). NOTE: chat handler creates plan row but does not yet execute real runs — see P3-1b | 7dcfefd |
| P3-2 | Suite planner default too low | verified_closed | _MAX_RUNS changed from 5 to 20; still configurable via context["max_runs"]; tests verify default=20 with override and lower tests | 35c279c |
| P3-3 | Sensitivity sweeps not executable | verified_closed | _materialize_multipliers() converts sweep range metadata to float lists; sensitivity_multipliers field on SuiteRun bridges to BatchRunner.ScenarioInput; 2 tests verify materialization and empty case | 080b83e |
| P3-4 | Polarity guard not question-aware | verified_closed | _has_negative_polarity() keyword detector + _check_polarity validator warns when contrarian ratio < 30% for negative questions; key_questions field on MuhasabaOutput; MuhasabaAgent wires key_questions in both fallback+LLM paths; 4 tests | 1d76f83 |
| P3-5 | Depth prompts missing denomination; no parsed-LLM tests | verified_closed | Khawatir/Mujahada/Suite prompts include denomination (SAR_MILLIONS) + key_questions; 7 LLM parse tests (parsed, fallback, ValueError) + 4 prompt content tests; 18 new test instances | d651cf8 |
| P3-6 | Suite planner emits placeholder lever values | verified_closed | _derive_shock_value() produces real values from existing_shocks or heuristics (FD=avg shock/100M, IS=-0.05, LC=0.40, CST=1.0); quantified_levers pass through; 5 tests | 6fb7957 |
| P3-1b | Depth suite runs not executed after plan completion | verified_closed | DepthSuiteExecutionService converts ScenarioSuitePlan→BatchRequest; _execute_depth_suite_runs() loads SUITE_PLANNING artifact, resolves model, executes via BatchRunner; chat handler returns real run_ids; 10 tests (4 service + 1 handler × 2 backends) | pending |

---

## Phase 4: Governance Autowiring and Disclosure Enforcement

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P4-1 | Claims not auto-created on real run path | verified_closed | execute_from_scenario() calls create_claims_from_results() + persists via claim_repo.create(); claim_repo on RunRepositories; 2 tests | 25d30b4 |
| P4-2 | Draft assumptions not auto-created on real build path | verified_closed | _handle_build_scenario() calls draft_compilation_assumptions() + persists via assumption_repo.create(); 2 tests | 25d30b4 |
| P4-3 | Publication gate not receiving assumptions on real export path | verified_closed | ExportExecutionService.execute() loads via assumption_repo.list_by_workspace() + passes to orchestrator; assumption_repo on ExportRepositories; 2 tests | 25d30b4 |
| P4-4 | Tiered disclosure not enforced in exports | verified_closed | ExportOrchestrator filters TIER0 from pack_data in GOVERNED mode; ExportRecord.filtered_tier0_count; 3 tests | 92838eb |
| P4-5 | Workspace isolation gaps in repositories | verified_closed | ClaimRepository.list_by_workspace() with pagination+status filter via RunSnapshot join; 2 tests | 92838eb |

---

## Phase 4b: Export Governance Correctness

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P4b-1 | Export assumption scope too broad (workspace instead of scenario/run) | verified_closed | list_linked_to() on AssumptionRepository; ExportExecutionService scopes to scenario_spec_id via AssumptionLinkRow; _handle_build_scenario links assumptions; legacy fallback to workspace scope; 3 new tests + 1 updated | pending |

---

## Phase 5: Main Run Path Completeness

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P5-1 | Sector breakdowns not fully populated | verified_closed | BatchRunner populates sector_breakdowns on total_output; 5 tests | d5a5b91 |
| P5-2 | Workforce satellite not on main run path | verified_closed | WorkforceSatellite wired into BatchRunner._emit_saudization_results(); emits saudization_saudi_ready, saudization_saudi_trainable, saudization_expat_reliant ResultSets; graceful degradation when D-4 data unavailable; load_workforce_data() builds D-4 in-memory from expert patterns; 5 tests | pending |
| P5-3 | Feasibility layer not on main run path | verified_closed | feasible_output and constraint_gap ALWAYS emitted; when no constraints: feasible=unconstrained, gap=0; ClippingSolver still runs when constraints provided; 4 new tests + 1 updated; 5502 passed | pending |
| P5-4 | Report data not packaged for UI consumption | verified_closed | ResultPackager converts ResultSet rows -> pack_data; 6 tests | d5a5b91 |

---

## Phase 6: Frontend Decision Pack and Product Surface

| ID | Blocker | Status | Verification | Commit |
|----|---------|--------|--------------|--------|
| P6-1 | Raw JSON in chat messages | verified_closed | Structured result summary; raw JSON behind toggle; 3 tests | 33588e0 |
| P6-2 | Executive summary missing | verified_closed | KPI cards (Total Output, GDP Impact, Jobs Created); 3 tests | 33588e0 |
| P6-3 | KPI cards missing denomination scaling | verified_closed | model_denomination flows ModelVersion→RunSnapshot→API→frontend; formatDenomination() renders "SAR (Millions)"; Total Impact sums only total_output (not all metrics); DB round-trip verified with SAR_THOUSANDS; 4 backend + 2 frontend tests | 3afcdd3 |
| P6-4 | Suite list, risks, workforce, sector breakdown missing | verified_closed | All 7 panels implemented: SectorBreakdownsPanel, WorkforcePanel, FeasibilityPanel, ScenarioSuitePanel, QualitativeRisksPanel, SensitivityEnvelopePanel, DepthEngineTracePanel; results-display.tsx wires depth_engine data (suite_runs, qualitative_risks, sensitivity_runs, trace_steps); 21 frontend panel tests pass; 394 total frontend tests pass | pending |
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
