# MVP-12: Knowledge Flywheel Design

## Overview

The Knowledge Flywheel captures 6 types of knowledge across engagements, creating compounding value. Each engagement refines mapping patterns, assumption defaults, scenario templates, calibration observations, client interaction history, and workforce bridges.

All flywheel logic is deterministic (no LLM calls). The MappingAgent (MVP-8) uses LLM for suggestions, but versioning, publishing, and learning are pure code.

## Key Design Decisions

1. **Module location**: `src/flywheel/`
2. **Persistence**: ABC store interfaces + InMemory implementations for tests
3. **Generic base**: `VersionedLibraryManager[TEntry, TDraft, TVersion]` for shared draft/publish lifecycle
4. **Two-layer scope**: All flywheel objects carry `ReuseScopeLevel` (WORKSPACE_ONLY vs SANITIZED_GLOBAL vs GLOBAL_INTERNAL)
5. **Draft/Version separation**: Mutable drafts are a distinct type from frozen published versions
6. **RunSnapshot fields**: New version IDs added as `Optional[UUID]` to avoid breaking 2573 existing tests
7. **Workforce data**: Copy from xenodochial-ardinghelli worktree into `src/data/workforce/`

## Module Structure

```
src/flywheel/
    __init__.py
    models.py                  # Shared enums: ReuseScopeLevel, PromotionStatus, DraftStatus, AssumptionValueType
    base.py                    # VersionedLibraryManager generic base
    stores.py                  # ABC store interfaces + InMemory implementations
    mapping_library.py         # MappingLibraryDraft, MappingLibraryVersion, MappingLibraryManager
    assumption_library.py      # AssumptionDefault, AssumptionLibraryDraft/Version, AssumptionLibraryManager
    scenario_patterns.py       # ScenarioPattern, ScenarioPatternLibrary
    calibration.py             # CalibrationNote (append-only)
    engagement_memory.py       # EngagementMemory (append-only)
    workforce_refinement.py    # WorkforceBridgeRefinement, OccupationBridgeVersion, NationalityClassificationVersion
    publication.py             # FlywheelPublicationService, PublicationQualityGate, PublicationResult
    health.py                  # FlywheelHealth metrics

src/data/workforce/            # Copied from xenodochial-ardinghelli
    __init__.py
    nationality_classification.py
    occupation_bridge.py
```

## 1. Shared Foundation

### Enums (`models.py`)

```python
class ReuseScopeLevel(StrEnum):
    WORKSPACE_ONLY = "WORKSPACE_ONLY"         # Private to this engagement
    SANITIZED_GLOBAL = "SANITIZED_GLOBAL"     # Reviewed, safe to share
    GLOBAL_INTERNAL = "GLOBAL_INTERNAL"       # Internal SG knowledge

class PromotionStatus(StrEnum):
    RAW = "RAW"
    REVIEWED = "REVIEWED"
    PROMOTED = "PROMOTED"
    DISMISSED = "DISMISSED"

class DraftStatus(StrEnum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    REJECTED = "REJECTED"

class AssumptionValueType(StrEnum):
    NUMERIC = "NUMERIC"
    CATEGORICAL = "CATEGORICAL"
```

### Common Flywheel Fields

All major flywheel objects carry:
- `workspace_id: UUID` -- isolation boundary
- `source_engagement_id: UUID | None` -- which engagement produced this
- `reuse_scope: ReuseScopeLevel = WORKSPACE_ONLY`
- `sanitized_for_promotion: bool = False`

### Generic Base (`base.py`)

`VersionedLibraryManager[TEntry, TDraft, TVersion]` provides the shared lifecycle:

- `get_active_version() -> TVersion` -- current published version
- `get_version(version_id) -> TVersion` -- any historical version
- `list_versions() -> list[TVersion]` -- all published versions
- `create_draft(base_version_id?) -> TDraft` -- start building a new version
- `publish(draft, published_by, quality_gate?) -> TVersion` -- publish draft, assign version number, set as active

Version numbers are monotonically increasing. Published versions are frozen (immutable). The active version pointer is updated on publish; old versions remain accessible by version_id.

### Store ABCs (`stores.py`)

```python
class VersionedLibraryStore(ABC, Generic[TVersion]):
    def save_version(self, version: TVersion) -> None: ...
    def get_version(self, version_id: UUID) -> TVersion | None: ...
    def get_active(self) -> TVersion | None: ...
    def set_active(self, version_id: UUID) -> None: ...
    def list_versions(self) -> list[TVersion]: ...

class AppendOnlyStore(ABC, Generic[T]):
    def append(self, item: T) -> None: ...
    def get(self, item_id: UUID) -> T | None: ...
    def list_all(self, **filters) -> list[T]: ...
```

InMemory implementations use dict-backed storage for tests.

## 2. Mapping Library

### Models

**MappingLibraryDraft** (mutable):
- `draft_id: UUIDv7`
- `parent_version_id: UUID | None`
- `entries: list[MappingLibraryEntry]`
- `status: DraftStatus`
- `changes_from_parent: list[str]` -- human-readable
- `added_entry_ids: list[UUID]` -- machine-readable diff (Amendment 12)
- `removed_entry_ids: list[UUID]`
- `changed_entries: list[dict]` -- `[{entry_id, field, old, new}]`

**MappingLibraryVersion** (frozen):
- `version_id: UUIDv7`
- `version_number: int` -- monotonically increasing
- `published_at: UTCTimestamp`
- `published_by: UUID`
- `entries: list[MappingLibraryEntry]` -- complete library at this version
- `entry_count: int`
- `parent_version_id: UUID | None`
- `changes_from_parent: list[str] | None`
- `added_entry_ids: list[UUID]`
- `removed_entry_ids: list[UUID]`
- `changed_entries: list[dict]`
- `total_overrides_ingested: int`
- `accuracy_at_publish: float | None` -- measured on HOLDOUT set (Amendment 6)

### Manager

`MappingLibraryManager` extends `VersionedLibraryManager`. Adds:

- `build_draft(base_version_id?, include_overrides_since?)` -- uses LearningLoop to:
  - Extract new patterns from overrides (min_frequency threshold)
  - Update confidence scores for existing patterns
  - Record machine-readable diffs
- Integration with `PublicationQualityGate`

### Learning Loop Integration

Enhance existing `LearningLoop` in `src/compiler/learning.py` with two new methods:

- `extract_new_patterns(overrides, existing_library, min_frequency=2)` -- groups overrides by final_sector_code, extracts common text patterns, creates new MappingLibraryEntry objects. Deduplicates against existing library.
- `update_confidence_scores(overrides, existing_library)` -- for each existing pattern, measures override accuracy. Consistently approved = confidence increase. Consistently overridden = confidence decrease.

## 3. Assumption Library

### Models

**AssumptionDefault** -- supports numeric AND categorical (Amendment 3):
- `assumption_default_id: UUIDv7`
- `assumption_type: AssumptionType` -- reuses common.py enum
- `sector_code: str | None` -- None = economy-wide
- `name: str`
- `value_type: AssumptionValueType` -- NUMERIC or CATEGORICAL
- `default_numeric_value: float | None`
- `default_text_value: str | None`
- `default_numeric_range: tuple[float, float] | None`
- `allowed_values: list[str] | None` -- for CATEGORICAL: ["front", "even", "back"]
- `unit: str`
- `rationale: str`
- `source: str`
- `usage_count: int = 0`
- `last_validated_at: UTCTimestamp | None`
- `confidence: str`

**AssumptionLibraryDraft** / **AssumptionLibraryVersion** -- same Draft/Version pattern as mapping.

### Manager

Extends `VersionedLibraryManager`. Adds:
- `get_defaults_for_sector(sector_code, assumption_type?)` -- returns sector-specific + economy-wide defaults
- `build_draft(base_version_id?, calibration_updates?)` -- incorporates calibration notes

### Seed Data

`scripts/seed_assumption_library.py` creates initial defaults:
- IMPORT_SHARE: Construction 0.35, Manufacturing 0.45, Economy-wide 0.30
- JOBS_COEFF: Construction 18.5, Finance 5.2
- PHASING: Default "even" (categorical, allowed: front/even/back)
- DEFLATOR: Default 0.02

## 4. Scenario Pattern Library

**ScenarioPattern** includes lineage (Amendment 7):
- Standard fields: name, description, sector shares, phasing, import share, local content
- `project_type: str` -- "logistics_zone", "giga_project", etc.
- `engagement_count: int`
- `confidence: str`
- `contributing_engagement_ids: list[UUID]` -- which engagements built this
- `contributing_scenario_ids: list[UUID]`
- `merge_history: list[dict] | None` -- `[{merged_from, similarity_score, date}]`

**ScenarioPatternLibrary** (not using generic base -- different lifecycle):
- `find_patterns(project_type?, sector_focus?)` -- search/filter
- `record_engagement_pattern(engagement_id, scenario_spec, project_type)` -- merge if similar above threshold, create if new
- `suggest_template(project_type)` -- return most-used matching pattern

Merge policy: only merge patterns with cosine similarity above 0.8 on sector shares. Keep enough lineage to re-split later.

## 5. Calibration Notes (Append-Only)

**CalibrationNote**:
- Standard fields: sector_code, engagement_id, observation, likely_cause, metric_affected, direction, magnitude_estimate
- `validated: bool = False`
- `promoted_to: UUID | None` -- assumption_default_id if promoted (Amendment 8)
- `promotion_status: PromotionStatus = RAW`
- Scope fields: workspace_id, reuse_scope

Uses `AppendOnlyStore` ABC. Search by sector, metric, engagement.

## 6. Engagement Memory (Append-Only)

**EngagementMemory**:
- Standard fields: engagement_id, category, description, sector_code, resolution, time_to_resolve, lesson_learned, tags
- `promoted_to: UUID | None` -- pattern_id or governance rule (Amendment 8)
- `promotion_status: PromotionStatus = RAW`
- Scope fields: workspace_id, reuse_scope

Uses `AppendOnlyStore` ABC. Search by category, sector, tags.

## 7. Workforce Bridge Refinement

### Versioned Artifacts (Amendment 4)

**OccupationBridgeVersion** (frozen):
- `version_id, version_number, published_at`
- `bridge_data: OccupationBridge`
- `parent_version_id: UUID | None`

**NationalityClassificationVersion** (frozen):
- `version_id, version_number, published_at`
- `classifications: NationalityClassificationSet`
- `overrides_incorporated: list[UUID]`
- `parent_version_id: UUID | None`

### WorkforceBridgeRefinement

- `record_engagement_overrides(engagement_id, overrides)` -- accumulate
- `get_all_overrides()` -- all accumulated overrides
- `get_refinement_coverage()` -- report assumed vs calibrated cells
- `build_refined_classifications(base)` -- apply all overrides to produce improved set

## 8. Publication Service

### PublicationQualityGate (Amendment 6)

```python
class PublicationQualityGate:
    min_override_frequency: int = 2
    min_accuracy_delta: float = 0.0
    require_steward_review: bool = True
    duplicate_check: bool = True
    conflict_check: bool = True

    def validate(self, draft, ...) -> list[str]:  # Empty = pass
```

Accuracy must be measured on a holdout set, not the training overrides.

### FlywheelPublicationService

Orchestrates publication across all libraries:
- `publish_new_cycle(published_by, include_overrides_since?)` -- builds drafts, validates, publishes
- `get_flywheel_health()` -- aggregate metrics
- Idempotent: no new data = no new versions

### PublicationResult

- References to new versions created (or None if no changes)
- Pattern counts (new + updated)
- Workforce coverage
- Summary

## 9. RunSnapshot Integration

Add optional fields to `RunSnapshot` (Amendment 5):
```python
occupation_bridge_version_id: UUID | None = None
nationality_classification_version_id: UUID | None = None
nitaqat_target_version_id: UUID | None = None
```

Existing `mapping_library_version_id` and `assumption_library_version_id` are already present and required. The new fields default to None for backward compatibility.

## 10. FlywheelHealth Metrics

Includes backlog metrics (Amendment 10):
- Standard counts: engagements, library versions, entry counts, pattern counts
- `mapping_accuracy: float | None`
- `workforce_coverage_pct: float`
- `override_backlog_count: int`
- `avg_days_since_last_publication: float`
- `draft_count_pending_review: int`
- `pct_entries_assumed_vs_calibrated: float`
- `pct_shared_knowledge_sanitized: float`

## Test Strategy

60+ new tests across `tests/flywheel/`:
- Mapping: version creation, publish immutability, active version updates, override integration, confidence scoring
- Assumption: sector lookup, numeric + categorical support, seed data validation
- Scenario Pattern: extraction, merging, similarity threshold, suggestion
- Calibration: append-only, search, promotion paths
- Engagement Memory: append-only, search, promotion paths
- Workforce: override accumulation, coverage, versioned publication
- Publication: full cycle, idempotency, quality gates
- Health: accurate metrics, backlog counts
- RunSnapshot: version references, historical reproducibility

All 2573 existing tests must continue passing.
