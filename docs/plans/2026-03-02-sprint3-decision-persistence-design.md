# Sprint 3: Decision Persistence APIs — Design

**Date:** 2026-03-02
**Branch:** `phase3b-sprint3-decision-persistence`
**Scope:** B-4, B-5, B-8, B-17

## Audit Summary

- **MappingDecisionRow** exists in `src/db/tables.py` with all required fields.
- **No MappingDecisionRepository** exists — must create.
- **MappingState** enum and `MappingStateMachine` with transition validation in `src/compiler/mapping_state.py`.
- **HITLService** in `src/compiler/hitl.py` — in-memory bulk operations.
- **CompilationRow** stores `result_json` and `metadata_json`. No `scenario_spec_id` column — use `metadata_json` for linking.
- Baseline: 3392 tests.

## B-4: Per-Line Mapping Decision CRUD

**Endpoints:**
- `GET /v1/workspaces/{ws}/scenarios/{sid}/decisions/{line_item_id}` — current decision state
- `PUT /v1/workspaces/{ws}/scenarios/{sid}/decisions/{line_item_id}` — update decision (validates state transition)

**Design:**
- Create `MappingDecisionRepository` with `get_by_scenario_and_item()`, `create()`, `update_state()`, `list_by_scenario()`.
- PUT validates transition using `VALID_MAPPING_TRANSITIONS` from mapping_state.py.
- Each PUT creates a new `MappingDecisionRow` (append-only audit trail) rather than mutating in place.
- GET returns latest row for (scenario_spec_id, line_item_id).

## B-5: Bulk Threshold Approval

**Endpoint:**
- `POST /v1/workspaces/{ws}/scenarios/{sid}/decisions/bulk-approve`

**Design:**
- Accepts `confidence_threshold` (float, default 0.85) and `actor` (UUID).
- Queries all MappingDecisionRows for scenario where state=AI_SUGGESTED and confidence >= threshold.
- For each, creates new row with state=APPROVED, final_sector_code=suggested_sector_code.
- Returns count of approved decisions.

## B-8: Mapping Audit Trail

**Endpoint:**
- `GET /v1/workspaces/{ws}/scenarios/{sid}/decisions/{line_item_id}/audit`

**Design:**
- Returns all MappingDecisionRow entries for (scenario_spec_id, line_item_id) ordered by created_at asc.
- Each entry IS an audit record (from_state derivable from prior row).
- No separate audit table needed — MappingDecisionRow is append-only.

## B-17: GET Compilation Detail

**Endpoint:**
- `GET /v1/workspaces/{ws}/compiler/{compilation_id}/detail`

**Design:**
- Extends existing `CompilationRepository.get()`.
- Returns full compilation result: suggestions, split proposals, assumption drafts, confidence counts, metadata.
- Workspace scoping: verify compilation belongs to workspace via metadata_json.

## Repository: MappingDecisionRepository

New file: `src/repositories/mapping_decisions.py`

```python
class MappingDecisionRepository:
    get_latest(scenario_spec_id, line_item_id) -> MappingDecisionRow | None
    list_by_scenario(scenario_spec_id) -> list[MappingDecisionRow]
    list_by_scenario_and_state(scenario_spec_id, state) -> list[MappingDecisionRow]
    list_history(scenario_spec_id, line_item_id) -> list[MappingDecisionRow]
    create(**kwargs) -> MappingDecisionRow
    bulk_approve(scenario_spec_id, confidence_threshold, actor) -> list[MappingDecisionRow]
```

## DI Updates

Add `get_mapping_decision_repo` to `src/api/dependencies.py`.

## API Module

New endpoint functions added to `src/api/scenarios.py` (decision routes are scenario-scoped).

## Test Files

- `tests/api/test_decisions.py` — B-4, B-5, B-8
- `tests/api/test_compilation_detail.py` — B-17
