# Sprint 28 Design: Copilot Real Execution + Post-Execution Narrative

Date: 2026-03-06
Owner: Backend + Frontend + Docs
Status: Approved
Sprint: 28 (`phase3-sprint28-copilot-real-execution`)

## 1. Mission

Close three Sprint 27 deferrals so the chat path executes the real deterministic workflow end-to-end and returns a post-execution narrative grounded in persisted outputs:

1. `run_engine` must call `BatchRunner.run()` and persist `RunSnapshot` + `ResultSet` rows (replacing dry-run validation).
2. `create_export` must invoke `ExportOrchestrator.execute()` through the same governance/provenance gates as the API path (replacing `PENDING`-only row creation).
3. The persisted assistant message must reflect executed results via a post-execution narrative pass, not only pre-execution LLM text.

## 2. Architecture Overview

### Execution model: inline blocking

`ChatService.send_message()` blocks until all requested deterministic tools complete. The frontend shows a loading/progress state during the request. This avoids async polling complexity and provides truthful same-turn status.

### New services

| Service | Module | Responsibility |
|---------|--------|----------------|
| `RunExecutionService` | `src/services/run_execution.py` | Single source of truth for engine execution + persistence |
| `ExportExecutionService` | `src/services/export_execution.py` | Single source of truth for export orchestration + persistence |
| `ChatNarrativeService` | `src/services/chat_narrative.py` | Extract facts from tool results, build baseline narrative |

### Call paths

**Chat path** (Sprint 28):
```
ChatService.send_message()
  -> EconomistCopilot.process_turn()
  -> ChatToolExecutor.execute_all()
       -> _handle_run_engine()   -> RunExecutionService.execute_from_scenario()
       -> _handle_create_export() -> ExportExecutionService.execute()
  -> ChatNarrativeService.extract_facts() -> NarrativeFacts
  -> ChatNarrativeService.build_baseline_narrative() -> baseline text
  -> EconomistCopilot.enrich_narrative() -> final narrative (optional)
  -> persist assistant message with post-execution content
```

**API path** (refactored):
```
POST /v1/workspaces/{ws}/engine/runs
  -> RunExecutionService.execute_from_request()

POST /v1/workspaces/{ws}/exports
  -> ExportExecutionService.execute()
```

Both paths call the same shared service. No internal HTTP self-calls.

### Agent-to-math boundary

Preserved. `RunExecutionService` calls `BatchRunner.run()` (deterministic NumPy). `ExportExecutionService` calls `ExportOrchestrator.execute()` (deterministic). LLM only produces structured JSON for tool dispatch and optional narrative enrichment. LLM never computes economic results.

## 3. S28-0: Shared Service Extraction

### 3.1 RunExecutionService

**Module:** `src/services/run_execution.py`

Two entrypoints, because chat and API arrive with different input shapes:

- `execute_from_scenario(input: RunFromScenarioInput, repos: RunRepositories) -> RunExecutionResult`
  - Chat path: has `scenario_spec_id` + optional `scenario_spec_version`
  - Resolves ScenarioSpec -> model_version_id, shocks, base_year, time_horizon
  - Loads model via existing `_ensure_model_loaded()` pattern (extracted from `src/api/runs.py`)
  - Resolves satellite coefficients via `SatelliteCoefficientResolver` (see Section 4.1)
  - Calls `BatchRunner.run()`, persists `RunSnapshot` + `ResultSet` rows
  - Builds `result_summary` from persisted rows (not parallel in-memory path)

- `execute_from_request(input: RunFromRequestInput, repos: RunRepositories) -> RunExecutionResult`
  - API path: has pre-parsed `model_version_id`, `annual_shocks`, `satellite_coefficients`, etc.
  - Same execution + persistence logic, just different input resolution

**Workspace/ownership checks inside the service**, not at the caller level. The service validates that the scenario and model belong to the workspace before executing.

### 3.2 ExportExecutionService

**Module:** `src/services/export_execution.py`

Single entrypoint:

- `execute(input: ExportExecutionInput, repos: ExportRepositories) -> ExportExecutionResult`
  - Loads claims, quality assessment, model provenance (same as current `src/api/exports.py` `create_export` endpoint)
  - Calls `ExportOrchestrator.execute()`
  - Persists export record with artifact refs, checksums, blocking reasons
  - Stores artifacts via `ExportArtifactStorage`
  - Returns truthful status: `COMPLETED`, `BLOCKED`, or `FAILED`

### 3.3 Normalized dataclasses

```python
# --- Run inputs ---

@dataclass(frozen=True)
class RunFromScenarioInput:
    """Chat path: resolve scenario into engine inputs."""
    workspace_id: UUID
    scenario_spec_id: UUID
    scenario_spec_version: int | None = None  # None = latest

@dataclass(frozen=True)
class RunFromRequestInput:
    """API path: pre-parsed engine inputs."""
    workspace_id: UUID
    model_version_id: UUID
    annual_shocks: dict[int, np.ndarray]
    base_year: int
    satellite_coefficients: SatelliteCoefficients
    deflators: dict[int, float] | None = None
    baseline_run_id: UUID | None = None
    scenario_spec_id: UUID | None = None
    scenario_spec_version: int | None = None

# --- Run result ---

@dataclass(frozen=True)
class RunExecutionResult:
    status: Literal["COMPLETED", "FAILED"]
    run_id: UUID | None = None
    model_version_id: UUID | None = None
    scenario_spec_id: UUID | None = None
    scenario_spec_version: int | None = None
    result_summary: dict | None = None  # derived from persisted rows
    error: str | None = None

# --- Export inputs ---

@dataclass(frozen=True)
class ExportExecutionInput:
    workspace_id: UUID
    run_id: UUID
    mode: ExportMode
    export_formats: list[str]
    pack_data: dict

# --- Export result ---

@dataclass(frozen=True)
class ExportExecutionResult:
    status: Literal["COMPLETED", "BLOCKED", "FAILED"]
    export_id: UUID | None = None
    checksums: dict[str, str] = field(default_factory=dict)
    blocking_reasons: list[str] = field(default_factory=list)
    artifact_refs: dict[str, str] = field(default_factory=dict)
    error: str | None = None

# --- Repository bundles ---

@dataclass
class RunRepositories:
    """All repos needed for a run execution."""
    scenario_repo: ScenarioVersionRepository
    mv_repo: ModelVersionRepository
    md_repo: ModelDataRepository
    snap_repo: RunSnapshotRepository
    rs_repo: ResultSetRepository

@dataclass
class ExportRepositories:
    """All repos needed for an export execution."""
    export_repo: ExportRepository
    claim_repo: ClaimRepository
    quality_repo: DataQualityRepository
    snap_repo: RunSnapshotRepository
    mv_repo: ModelVersionRepository
    artifact_store: ExportArtifactStorage
```

### 3.4 API route refactoring

After extraction, `src/api/runs.py::create_run()` calls `RunExecutionService.execute_from_request()` and maps the result to `RunResponse`. `src/api/exports.py::create_export()` calls `ExportExecutionService.execute()` and maps the result to `CreateExportResponse`.

Helper functions currently inline in API modules (`_ensure_model_loaded`, `_enforce_model_provenance`, `_make_satellite_coefficients`, `_persist_run_result`, etc.) move into the shared service or a shared helper module. The API routes become thin wrappers.

### 3.5 FAILED status

`RunExecutionResult.status = "FAILED"` is returned when:
- Scenario not found in workspace
- Model not found or provenance check fails
- `BatchRunner.run()` raises an exception (TypeIIValidationError, ValueMeasuresValidationError, RunSeriesValidationError, etc.)
- Any other unhandled exception during execution

The `error` field contains the reason string (capped at 200 chars, no secrets).

### 3.6 No new Alembic migration

All required tables (`run_snapshots`, `result_sets`, `exports`, `chat_sessions`, `chat_messages`) already exist. No schema changes needed.

## 4. S28-1: Real `run_engine` Execution from Chat

### 4.1 SatelliteCoefficientResolver

Chat path does NOT receive satellite coefficients in the tool arguments (unlike the API path which gets them in the request body). The chat handler must resolve default coefficients deterministically.

**Resolution path:** Use `load_satellite_coefficients()` from `src/data/workforce/satellite_coeff_loader.py` with the scenario's `base_year` and the model's `sector_codes`. This is the existing curated loader path that resolves D-4 employment coefficients and D-3 IO model ratios.

**Provenance preservation:** The `CoefficientProvenance` returned by the loader is attached to the execution result metadata, so the narrative and trace can report which year and data source backed the coefficients. If `used_synthetic_fallback` is true, this flows through to export gate decisions.

### 4.2 Chat handler changes

`ChatToolExecutor._handle_run_engine()` changes:

1. Remove `scenario_validated_dry_run` reason code and synthetic `run_id` generation.
2. Resolve scenario (existing version-pinning logic preserved).
3. Call `RunExecutionService.execute_from_scenario()` with the resolved scenario.
4. Return the real `RunExecutionResult` fields: `run_id`, `scenario_spec_id`, `scenario_spec_version`, `model_version_id`, `result_summary`.
5. On failure, return `reason_code: "run_failed"` with the error message.

### 4.3 result_summary

The `result_summary` dict in `RunExecutionResult` is derived from persisted `ResultSet` rows after they are written to the database, not from a parallel in-memory path. This guarantees the summary matches what a subsequent `narrate_results` tool call or API read would return.

Structure: `{metric_type: values_dict}` (same shape as existing `_handle_narrate_results` output).

### 4.4 Trace metadata changes

After Sprint 28, `run_engine` always produces a real `run_id` (backed by a persisted `RunSnapshot`). The conditional suppression of `run_id` for `scenario_validated_dry_run` is removed from `ChatService.send_message()`.

## 5. S28-2: Real `create_export` Orchestration from Chat

### 5.1 Chat handler changes

`ChatToolExecutor._handle_create_export()` changes:

1. Remove `PENDING`-only row creation and `TODO(S28+)` comment.
2. Call `ExportExecutionService.execute()` with workspace-scoped input.
3. Return truthful status: `COMPLETED`, `BLOCKED`, or `FAILED`.
4. For `COMPLETED`: return `export_id`, `checksums`, `artifact_refs`.
5. For `BLOCKED`: return `export_id`, `blocking_reasons` (NFF gate, provenance, quality).
6. For `FAILED`: return error message.

### 5.2 Governance parity

The chat export path loads the same inputs as the API export path:
- `ClaimRepository.get_by_run(run_id)` -> NFF claims
- `DataQualityRepository.get_by_run(run_id)` -> quality assessment
- `_check_model_provenance(run_id, snap_repo, mv_repo)` -> provenance flag

These checks happen inside `ExportExecutionService.execute()`, ensuring both chat and API paths enforce identical governance gates.

## 6. S28-3: Post-Execution Narrative

### 6.1 ChatNarrativeService

**Module:** `src/services/chat_narrative.py`

A first-class service (not inline on ChatService) responsible for:

1. **`extract_facts(tool_results: list[ToolExecutionResult]) -> NarrativeFacts`**
   - Normalizes raw tool execution results into domain-specific facts
   - Decoupled from the transport shape of `ToolExecutionResult`
   - Extracts: run status, metric summaries, export status, blocking reasons, error messages

2. **`build_baseline_narrative(facts: NarrativeFacts) -> str`**
   - Deterministic template-based narrative from persisted outputs
   - No LLM call, no hallucination risk
   - Grounded only in what `NarrativeFacts` contains (which came from persisted rows)
   - Example templates:
     - Success: "Engine run completed. Total output: {total_output} SAR. Employment impact: {jobs} jobs. Export {export_id} generated successfully."
     - Blocked: "Engine run completed. Export blocked: {blocking_reasons}."
     - Failed: "Engine run failed: {error}."

### 6.2 NarrativeFacts dataclass

```python
@dataclass(frozen=True)
class NarrativeFacts:
    """Normalized domain facts extracted from tool execution results."""
    run_completed: bool = False
    run_id: str | None = None
    scenario_name: str | None = None
    model_version_id: str | None = None
    result_summary: dict | None = None  # metric_type -> values
    export_completed: bool = False
    export_id: str | None = None
    export_status: str | None = None  # COMPLETED, BLOCKED, FAILED
    export_blocking_reasons: list[str] = field(default_factory=list)
    export_checksums: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    has_meaningful_results: bool = False  # at least one tool produced results
```

### 6.3 Optional LLM enrichment

After the baseline narrative is built, `ChatService` optionally calls:

```python
EconomistCopilot.enrich_narrative(baseline: str, context: dict) -> str
```

- Turns the template narrative into economist-quality prose
- Receives **sanitized, bounded context only**: the baseline text and a limited set of metadata (scenario name, metric types present, run status). No raw DB rows, no full result payloads.
- If LLM enrichment fails or is disabled, the baseline narrative is used as-is
- LLM never invents numbers -- it rephrases the baseline which was built from persisted facts

### 6.4 Content policy

The content of the persisted assistant message depends on tool execution outcomes:

| Condition | Persisted content |
|-----------|------------------|
| At least one tool produced meaningful results | Post-execution narrative (baseline or enriched) replaces pre-execution LLM text |
| All tools failed or blocked | Original pre-execution LLM content preserved + failure summary appended |
| No tools executed (e.g., pending confirmation) | Original LLM content unchanged |

"Meaningful results" = `NarrativeFacts.has_meaningful_results` is true, meaning at least one tool returned `status="success"` with a non-empty result payload.

This prevents silently discarding the original assistant content when every tool call fails, which would leave the user with no useful information.

## 7. S28-4: Frontend Completion

### 7.1 Status badge mapping

Tool execution results render with status-specific badges:

| `ToolExecutionResult.status` | Badge | Color |
|------------------------------|-------|-------|
| `"success"` | Success | Green |
| `"blocked"` | Blocked | Amber |
| `"error"` | Error | Red |

**Critical:** `BLOCKED` maps to `status="blocked"` and renders amber. It is NOT routed through `_ERROR_REASON_CODES` (which would show red). A blocked export is a valid governance outcome, not a system failure.

### 7.2 Deep links

- `run_id` links to `/workspaces/{ws}/engine/runs/{run_id}` -- only when backed by a real persisted `RunSnapshot`
- `export_id` links to `/workspaces/{ws}/exports/{export_id}` -- only when status is `COMPLETED`
- No artifact download links for `BLOCKED` or `FAILED` exports

### 7.3 Post-execution narrative rendering

The assistant message bubble displays the post-execution narrative content alongside the tool call result badges. The narrative text is the primary content; tool call details are collapsible supplementary information.

### 7.4 Component changes

- `message-bubble.tsx`: Add amber badge for `status="blocked"`, render blocking reasons list, conditional download link
- `chat-interface.tsx`: Handle loading state during blocking execution, display post-execution narrative
- `useChat.ts`: No structural changes needed (blocking request already supported)

## 8. S28-5: Prompt, Contracts, and Evidence

### 8.1 Copilot prompt updates

Update `src/agents/prompts/economist_copilot_v1.py`:
- `run_engine` tool description: "Executes a real engine run and persists results" (remove "validates scenario" / dry-run language)
- `create_export` tool description: "Generates export artifacts through governance gates" (remove "creates PENDING row" language)
- Add `enrich_narrative()` method description to copilot class

### 8.2 OpenAPI regeneration

Regenerate `openapi.json` from the FastAPI app after API route refactoring. Validate JSON structure.

### 8.3 Evidence updates

- `docs/evidence/sprint25-copilot-evidence.md`: Add Sprint 28 section with test counts, merge evidence, real execution proof
- `docs/ImpactOS_Master_Build_Plan_v2.md`: Add S28 row
- `docs/plans/2026-03-03-full-system-completion-master-plan.md`: Add S28 to completion table

## 9. Hard Constraints (from Sprint 28 prompt)

1. Agent-to-math boundary preserved (LLM never computes economics).
2. Existing workspace auth semantics (401/403/404) unchanged.
3. Existing API behavior preserved (additive changes only via shared service extraction).
4. Confirmation gate remains mandatory for `build_scenario` and `run_engine`.
5. No secret leakage in chat content, trace metadata, logs, or error payloads.
6. Non-dev fail-closed for invalid runtime config/provider.
7. Every executed tool call persisted with arguments, status, latency, result/error summary.
8. No internal HTTP self-calls. Chat calls shared Python services directly.
9. `run_engine` honors `scenario_spec_version` when provided (version pinning from S27).
10. Export uses same governance/provenance gates as normal export path.

## 10. Scope boundaries

**In scope:**
- S28-0 through S28-5 as described above
- Shared service extraction for run and export
- Real engine execution and export orchestration from chat
- Post-execution narrative with facts extraction and baseline builder
- Frontend status badges and deep links
- Prompt and evidence sync

**Out of scope:**
- Background job architecture changes (execution remains inline blocking)
- New Alembic migrations
- Portfolio optimization features (MVP-29+)
- UI redesign beyond status badges and narrative rendering
- Multi-model or multi-workspace batch runs from chat
