# MVP-12: Knowledge Flywheel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Knowledge Flywheel — 6 types of versioned, reusable knowledge that compound across engagements.

**Architecture:** Generic `VersionedLibraryManager[TEntry, TDraft, TVersion]` base class with ABC stores + InMemory implementations. Two-layer scope model (private vs promoted). Draft/Version separation. All flywheel logic is deterministic (no LLM).

**Tech Stack:** Python 3.11+, Pydantic v2, frozen dataclasses for workforce types, pytest for TDD.

**Design doc:** `docs/plans/2026-02-28-knowledge-flywheel-design.md`

**Existing test count:** 682 tests. All must continue passing after every task.

---

## Task 0: Copy Workforce Data Files

**Files:**
- Create: `src/data/__init__.py`
- Create: `src/data/workforce/__init__.py`
- Create: `src/data/workforce/unit_registry.py` (copy from xenodochial-ardinghelli)
- Create: `src/data/workforce/nationality_classification.py` (copy from xenodochial-ardinghelli)
- Create: `src/data/workforce/occupation_bridge.py` (copy from xenodochial-ardinghelli)

**Step 1:** Copy the three workforce files and their `__init__.py` files from `C:\Projects\ImpactOS\.claude\worktrees\xenodochial-ardinghelli\src\data\` into our worktree's `src/data/`. Copy `src/data/__init__.py`, `src/data/workforce/__init__.py`, `src/data/workforce/unit_registry.py`, `src/data/workforce/nationality_classification.py`, `src/data/workforce/occupation_bridge.py`.

**Step 2:** Run `pytest tests/ -x -q` to verify no regressions from adding files.

**Step 3:** Commit: `[data] copy D-4 workforce data files from xenodochial-ardinghelli`

---

## Task 1: Shared Foundation — Enums and Models

**Files:**
- Create: `src/flywheel/__init__.py`
- Create: `src/flywheel/models.py`
- Test: `tests/flywheel/test_models.py`

**Step 1: Write failing tests for flywheel enums**

```python
# tests/flywheel/__init__.py — empty
# tests/flywheel/test_models.py
"""Tests for flywheel shared enums and models."""
from src.flywheel.models import (
    AssumptionValueType,
    DraftStatus,
    PromotionStatus,
    ReuseScopeLevel,
)


class TestReuseScopeLevel:
    def test_values(self) -> None:
        assert ReuseScopeLevel.WORKSPACE_ONLY == "WORKSPACE_ONLY"
        assert ReuseScopeLevel.SANITIZED_GLOBAL == "SANITIZED_GLOBAL"
        assert ReuseScopeLevel.GLOBAL_INTERNAL == "GLOBAL_INTERNAL"

    def test_default_is_workspace_only(self) -> None:
        """WORKSPACE_ONLY is the safe default for all flywheel objects."""
        assert list(ReuseScopeLevel)[0] == ReuseScopeLevel.WORKSPACE_ONLY


class TestDraftStatus:
    def test_values(self) -> None:
        assert DraftStatus.DRAFT == "DRAFT"
        assert DraftStatus.REVIEW == "REVIEW"
        assert DraftStatus.REJECTED == "REJECTED"


class TestPromotionStatus:
    def test_values(self) -> None:
        assert PromotionStatus.RAW == "RAW"
        assert PromotionStatus.REVIEWED == "REVIEWED"
        assert PromotionStatus.PROMOTED == "PROMOTED"
        assert PromotionStatus.DISMISSED == "DISMISSED"


class TestAssumptionValueType:
    def test_values(self) -> None:
        assert AssumptionValueType.NUMERIC == "NUMERIC"
        assert AssumptionValueType.CATEGORICAL == "CATEGORICAL"
```

**Step 2:** Run `pytest tests/flywheel/test_models.py -v` — expect FAIL (import error).

**Step 3: Implement enums**

```python
# src/flywheel/__init__.py — empty
# src/flywheel/models.py
"""Shared enums and types for the Knowledge Flywheel (MVP-12)."""

from enum import StrEnum


class ReuseScopeLevel(StrEnum):
    """Two-layer scope model for flywheel knowledge (Amendment 1)."""
    WORKSPACE_ONLY = "WORKSPACE_ONLY"
    SANITIZED_GLOBAL = "SANITIZED_GLOBAL"
    GLOBAL_INTERNAL = "GLOBAL_INTERNAL"


class DraftStatus(StrEnum):
    """Draft lifecycle status (Amendment 2)."""
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    REJECTED = "REJECTED"


class PromotionStatus(StrEnum):
    """Promotion path status for calibration notes and engagement memories (Amendment 8)."""
    RAW = "RAW"
    REVIEWED = "REVIEWED"
    PROMOTED = "PROMOTED"
    DISMISSED = "DISMISSED"


class AssumptionValueType(StrEnum):
    """Assumption value type — numeric or categorical (Amendment 3)."""
    NUMERIC = "NUMERIC"
    CATEGORICAL = "CATEGORICAL"
```

**Step 4:** Run `pytest tests/flywheel/test_models.py -v` — expect PASS.

**Step 5:** Commit: `[flywheel] shared enums: ReuseScopeLevel, DraftStatus, PromotionStatus, AssumptionValueType`

---

## Task 2: Store ABCs and InMemory Implementations

**Files:**
- Create: `src/flywheel/stores.py`
- Test: `tests/flywheel/test_stores.py`

**Step 1: Write failing tests**

Test the `InMemoryVersionedLibraryStore` with a simple frozen Pydantic model as the version type. Tests: save/get, get_active/set_active, list_versions, get nonexistent returns None. Test `InMemoryAppendOnlyStore`: append/get, list_all, get nonexistent returns None.

**Step 2:** Run tests — expect FAIL.

**Step 3: Implement stores**

```python
# src/flywheel/stores.py
"""Store ABCs and InMemory implementations for flywheel libraries."""
from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

T = TypeVar("T")
TVersion = TypeVar("TVersion")


class VersionedLibraryStore(ABC, Generic[TVersion]):
    """ABC for storing versioned library snapshots."""

    @abstractmethod
    def save_version(self, version: TVersion) -> None: ...
    @abstractmethod
    def get_version(self, version_id: UUID) -> TVersion | None: ...
    @abstractmethod
    def get_active(self) -> TVersion | None: ...
    @abstractmethod
    def set_active(self, version_id: UUID) -> None: ...
    @abstractmethod
    def list_versions(self) -> list[TVersion]: ...


class InMemoryVersionedLibraryStore(VersionedLibraryStore[TVersion]):
    """InMemory implementation for tests."""

    def __init__(self) -> None:
        self._versions: dict[UUID, TVersion] = {}
        self._active_id: UUID | None = None

    def save_version(self, version: TVersion) -> None:
        vid = getattr(version, "version_id")
        self._versions[vid] = version

    def get_version(self, version_id: UUID) -> TVersion | None:
        return self._versions.get(version_id)

    def get_active(self) -> TVersion | None:
        if self._active_id is None:
            return None
        return self._versions.get(self._active_id)

    def set_active(self, version_id: UUID) -> None:
        if version_id not in self._versions:
            msg = f"Version {version_id} not found."
            raise KeyError(msg)
        self._active_id = version_id

    def list_versions(self) -> list[TVersion]:
        return list(self._versions.values())


class AppendOnlyStore(ABC, Generic[T]):
    """ABC for append-only stores (calibration notes, engagement memories)."""

    @abstractmethod
    def append(self, item: T) -> None: ...
    @abstractmethod
    def get(self, item_id: UUID) -> T | None: ...
    @abstractmethod
    def list_all(self) -> list[T]: ...


class InMemoryAppendOnlyStore(AppendOnlyStore[T]):
    """InMemory implementation for tests."""

    def __init__(self, id_field: str = "note_id") -> None:
        self._items: list[T] = []
        self._by_id: dict[UUID, T] = {}
        self._id_field = id_field

    def append(self, item: T) -> None:
        item_id = getattr(item, self._id_field)
        self._items.append(item)
        self._by_id[item_id] = item

    def get(self, item_id: UUID) -> T | None:
        return self._by_id.get(item_id)

    def list_all(self) -> list[T]:
        return list(self._items)
```

**Step 4:** Run tests — expect PASS.

**Step 5:** Commit: `[flywheel] store ABCs and InMemory implementations`

---

## Task 3: Generic VersionedLibraryManager Base

**Files:**
- Create: `src/flywheel/base.py`
- Test: `tests/flywheel/test_base.py`

**Step 1: Write failing tests**

Create a concrete test subclass of `VersionedLibraryManager` using simple test types (a `_TestEntry`, `_TestDraft`, `_TestVersion`). Tests:
- `create_draft` with no base version returns empty draft
- `create_draft` with base version copies entries from parent
- `publish` creates frozen version with monotonic version_number
- `publish` sets new version as active
- `get_active_version` returns latest published
- `get_version` returns specific historical version
- `list_versions` returns all published versions
- `publish` with REJECTED draft raises ValueError
- Version numbers are monotonically increasing (1, 2, 3...)

**Step 2:** Run tests — expect FAIL.

**Step 3: Implement base**

The `VersionedLibraryManager` is generic over `TEntry`, `TDraft`, `TVersion`. It takes a `VersionedLibraryStore[TVersion]` and provides:
- `create_draft(base_version_id?)` — creates draft from base or empty
- `publish(draft, published_by)` — validates draft status is DRAFT or REVIEW, creates frozen version, saves to store, sets as active
- `get_active_version()`, `get_version(id)`, `list_versions()`

Subclasses must implement:
- `_make_draft(entries, parent_version_id)` — construct a TDraft
- `_make_version(draft, version_number, published_by)` — construct a TVersion
- `_get_draft_entries(draft)` — extract entries from draft
- `_get_draft_status(draft)` — get draft status
- `_get_version_entries(version)` — extract entries from version

**Step 4:** Run tests — expect PASS.

**Step 5:** Commit: `[flywheel] generic VersionedLibraryManager base class`

---

## Task 4: Mapping Library Models

**Files:**
- Create: `src/flywheel/mapping_library.py`
- Test: `tests/flywheel/test_mapping_library.py`

**Step 1: Write failing tests for models**

Test `MappingLibraryDraft`:
- Creates with default DRAFT status
- Has machine-readable diff fields (added/removed/changed)

Test `MappingLibraryVersion`:
- Is frozen (immutable)
- `entry_count` matches len(entries)
- Has provenance fields (parent_version_id, accuracy_at_publish)

**Step 2:** Run tests — expect FAIL.

**Step 3: Implement models**

```python
# src/flywheel/mapping_library.py
class MappingLibraryDraft(ImpactOSBase):
    draft_id: UUIDv7 = Field(default_factory=new_uuid7)
    parent_version_id: UUID | None = None
    entries: list[MappingLibraryEntry] = Field(default_factory=list)
    status: DraftStatus = DraftStatus.DRAFT
    changes_from_parent: list[str] = Field(default_factory=list)
    added_entry_ids: list[UUID] = Field(default_factory=list)
    removed_entry_ids: list[UUID] = Field(default_factory=list)
    changed_entries: list[dict] = Field(default_factory=list)
    workspace_id: UUID | None = None
    reuse_scope: ReuseScopeLevel = ReuseScopeLevel.WORKSPACE_ONLY

class MappingLibraryVersion(ImpactOSBase, frozen=True):
    version_id: UUIDv7 = Field(default_factory=new_uuid7)
    version_number: int
    published_at: UTCTimestamp = Field(default_factory=utc_now)
    published_by: UUID
    entries: list[MappingLibraryEntry] = Field(default_factory=list)
    entry_count: int = 0
    parent_version_id: UUID | None = None
    changes_from_parent: list[str] = Field(default_factory=list)
    added_entry_ids: list[UUID] = Field(default_factory=list)
    removed_entry_ids: list[UUID] = Field(default_factory=list)
    changed_entries: list[dict] = Field(default_factory=list)
    total_overrides_ingested: int = 0
    accuracy_at_publish: float | None = None
```

**Step 4:** Run tests — expect PASS.

**Step 5:** Commit: `[flywheel] MappingLibraryDraft and MappingLibraryVersion models`

---

## Task 5: MappingLibraryManager

**Files:**
- Modify: `src/flywheel/mapping_library.py`
- Test: `tests/flywheel/test_mapping_library.py` (extend)

**Step 1: Write failing tests for manager**

Tests:
- `build_draft` with no base creates empty draft
- `build_draft` with base copies entries from parent version
- `publish` creates immutable version, sets as active
- `publish` increments version_number monotonically
- Old versions remain accessible by version_id after new publish
- `get_active_version` returns latest published
- Cannot modify published version (frozen)

**Step 2:** Run tests — expect FAIL.

**Step 3: Implement MappingLibraryManager**

Extends `VersionedLibraryManager`. Implements `_make_draft`, `_make_version`, `_get_draft_entries`, `_get_draft_status`, `_get_version_entries`. Adds `build_draft(base_version_id?, include_overrides_since?)` which uses LearningLoop.

**Step 4:** Run tests — expect PASS.

**Step 5:** Commit: `[flywheel] MappingLibraryManager with draft/publish lifecycle`

---

## Task 6: Learning Loop Integration

**Files:**
- Modify: `src/compiler/learning.py` (add 2 methods)
- Test: `tests/flywheel/test_mapping_learning.py`

**Step 1: Write failing tests**

Test `extract_new_patterns`:
- Groups overrides by final_sector_code
- Patterns appearing >= min_frequency become new entries
- New entries do NOT duplicate existing library entries
- Confidence reflects override accuracy for that pattern
- Empty overrides returns empty list

Test `update_confidence_scores`:
- Consistently approved patterns get confidence increase
- Consistently overridden patterns get confidence decrease
- Patterns with no matching overrides remain unchanged
- Returns updated copies (originals unchanged)

**Step 2:** Run tests — expect FAIL.

**Step 3: Implement**

Add `extract_new_patterns(overrides, existing_library, min_frequency=2)` and `update_confidence_scores(overrides, existing_library)` to `LearningLoop`.

- `extract_new_patterns`: groups by final_sector_code, finds common text among line_item_text, creates MappingLibraryEntry for groups with count >= min_frequency, deduplicates against existing.
- `update_confidence_scores`: for each existing entry, counts how many overrides matched that pattern's sector_code. If most were accepted (was_correct), increase confidence. Otherwise decrease. Returns new list of entries with updated confidences.

**Step 4:** Run tests — expect PASS. Also run `pytest tests/compiler/ -v` to verify no regressions.

**Step 5:** Commit: `[flywheel] learning loop integration: extract_new_patterns, update_confidence_scores`

---

## Task 7: Assumption Library

**Files:**
- Create: `src/flywheel/assumption_library.py`
- Test: `tests/flywheel/test_assumption_library.py`

**Step 1: Write failing tests**

Test `AssumptionDefault`:
- Numeric type: default_numeric_value and default_numeric_range set, default_text_value is None
- Categorical type: default_text_value and allowed_values set, default_numeric_value is None
- Reuses AssumptionType from common.py

Test `AssumptionLibraryDraft` / `AssumptionLibraryVersion`:
- Same draft/version pattern as mapping library
- Version is frozen

Test `AssumptionLibraryManager`:
- `get_defaults_for_sector("F")` returns sector-specific + economy-wide defaults
- `get_defaults_for_sector("F", IMPORT_SHARE)` filters by type
- `build_draft` and `publish` lifecycle
- Active version updates after publish
- Old versions accessible

**Step 2:** Run tests — expect FAIL.

**Step 3: Implement**

AssumptionDefault with `value_type: AssumptionValueType`, split numeric/text fields (Amendment 3). Draft/Version split. Manager extends VersionedLibraryManager, adds `get_defaults_for_sector()`.

**Step 4:** Run tests — expect PASS.

**Step 5:** Commit: `[flywheel] assumption library: defaults, versioning, sector lookup`

---

## Task 8: Seed Assumption Defaults Script

**Files:**
- Create: `scripts/seed_assumption_library.py`
- Test: `tests/flywheel/test_assumption_library.py` (extend with seed validation)

**Step 1: Write failing tests**

Test that seed data produces valid AssumptionDefault objects:
- IMPORT_SHARE Construction 0.35, range (0.25, 0.50)
- IMPORT_SHARE Manufacturing 0.45, range (0.30, 0.60)
- IMPORT_SHARE Economy-wide 0.30 (sector_code=None), range (0.20, 0.45)
- JOBS_COEFF Construction 18.5, range (12, 25)
- JOBS_COEFF Finance 5.2, range (3, 8)
- PHASING Default — categorical, value "even", allowed_values ["front", "even", "back"]
- DEFLATOR Default 0.02, range (0.01, 0.04)

**Step 2:** Run tests — expect FAIL.

**Step 3: Implement seed function**

`build_seed_defaults() -> list[AssumptionDefault]` that returns the 7 defaults above.

**Step 4:** Run tests — expect PASS.

**Step 5:** Commit: `[flywheel] seed assumption defaults from D-3/D-4 data`

---

## Task 9: Scenario Pattern Library

**Files:**
- Create: `src/flywheel/scenario_patterns.py`
- Test: `tests/flywheel/test_scenario_patterns.py`

**Step 1: Write failing tests**

Test `ScenarioPattern` model:
- Has lineage fields (contributing_engagement_ids, contributing_scenario_ids, merge_history)
- Has sector shares, phasing, project_type

Test `ScenarioPatternLibrary`:
- `find_patterns(project_type="logistics_zone")` returns matching patterns
- `find_patterns(sector_focus="F")` filters by sector
- `record_engagement_pattern` creates new pattern if none similar exists
- `record_engagement_pattern` merges with existing if similarity > 0.8
- Merge increments engagement_count, records merge_history
- Merge uses rolling average on sector shares
- `suggest_template` returns pattern with highest engagement_count for project_type
- `suggest_template` returns None if no patterns for project_type

**Step 2:** Run tests — expect FAIL.

**Step 3: Implement**

ScenarioPattern model. ScenarioPatternLibrary with in-memory list storage. Similarity computed as cosine similarity on sector share vectors. Merge policy: only merge if similarity > 0.8.

**Step 4:** Run tests — expect PASS.

**Step 5:** Commit: `[flywheel] scenario pattern library with lineage and merge policy`

---

## Task 10: Calibration Notes

**Files:**
- Create: `src/flywheel/calibration.py`
- Test: `tests/flywheel/test_calibration_notes.py`

**Step 1: Write failing tests**

Tests:
- CalibrationNote model has all fields including promotion path (Amendment 8)
- CalibrationNote has scope fields (workspace_id, reuse_scope)
- Append-only: notes can be added but not modified
- Search by sector_code
- Search by metric_affected
- Search by engagement_id
- Validated vs unvalidated distinction
- promotion_status defaults to RAW

**Step 2:** Run tests — expect FAIL.

**Step 3: Implement**

CalibrationNote model with all fields. `CalibrationNoteStore` subclass of `InMemoryAppendOnlyStore` with search methods (filter by sector, metric, engagement, validated status).

**Step 4:** Run tests — expect PASS.

**Step 5:** Commit: `[flywheel] calibration notes: model, append-only store, search`

---

## Task 11: Engagement Memory

**Files:**
- Create: `src/flywheel/engagement_memory.py`
- Test: `tests/flywheel/test_engagement_memory.py`

**Step 1: Write failing tests**

Tests:
- EngagementMemory model has all fields including promotion path
- Has scope fields
- Append-only store
- Search by category ("challenge", "acceptance", "evidence_request", "methodology_dispute")
- Search by sector_code
- Search by tags
- promotion_status defaults to RAW

**Step 2:** Run tests — expect FAIL.

**Step 3: Implement**

EngagementMemory model. `EngagementMemoryStore` subclass of `InMemoryAppendOnlyStore` with search methods.

**Step 4:** Run tests — expect PASS.

**Step 5:** Commit: `[flywheel] engagement memory: model, append-only store, search`

---

## Task 12: Workforce Bridge Refinement

**Files:**
- Create: `src/flywheel/workforce_refinement.py`
- Test: `tests/flywheel/test_workforce_refinement.py`

**Step 1: Write failing tests**

Test versioned models:
- `OccupationBridgeVersion` is frozen, has version_id/version_number
- `NationalityClassificationVersion` is frozen, has overrides_incorporated

Test `WorkforceBridgeRefinement`:
- `record_engagement_overrides` accumulates overrides
- `get_all_overrides` returns all accumulated
- `get_refinement_coverage` returns correct counts (total_cells, assumed_cells, engagement_calibrated_cells)
- `build_refined_classifications` applies all overrides to base set
- Coverage increases after recording overrides

**Step 2:** Run tests — expect FAIL.

**Step 3: Implement**

OccupationBridgeVersion/NationalityClassificationVersion frozen models. WorkforceBridgeRefinement manages override accumulation and coverage.

**Step 4:** Run tests — expect PASS.

**Step 5:** Commit: `[flywheel] workforce bridge refinement: versioned artifacts, coverage reporting`

---

## Task 13: Publication Quality Gates

**Files:**
- Create: `src/flywheel/publication.py`
- Test: `tests/flywheel/test_publication.py`

**Step 1: Write failing tests**

Test `PublicationQualityGate`:
- Validates min_override_frequency (pattern must appear >= 2 times)
- Validates no duplicate entries
- Validates no conflicting entries
- Returns list of failure messages (empty = pass)
- require_steward_review flag

**Step 2:** Run tests — expect FAIL.

**Step 3: Implement**

```python
class PublicationQualityGate(ImpactOSBase):
    min_override_frequency: int = 2
    min_accuracy_delta: float = 0.0
    require_steward_review: bool = True
    duplicate_check: bool = True
    conflict_check: bool = True

    def validate_mapping_draft(self, draft: MappingLibraryDraft) -> list[str]: ...
```

**Step 4:** Run tests — expect PASS.

**Step 5:** Commit: `[flywheel] publication quality gates`

---

## Task 14: Publication Service and Result Models

**Files:**
- Modify: `src/flywheel/publication.py`
- Test: `tests/flywheel/test_publication.py` (extend)

**Step 1: Write failing tests**

Test `FlywheelPublicationService`:
- `publish_new_cycle` builds drafts, validates, publishes all libraries
- Returns `PublicationResult` with version details
- Idempotent: no new data = no new versions created
- `PublicationResult` captures new/updated pattern counts

**Step 2:** Run tests — expect FAIL.

**Step 3: Implement**

FlywheelPublicationService takes all managers in constructor. `publish_new_cycle()` orchestrates. PublicationResult model.

**Step 4:** Run tests — expect PASS.

**Step 5:** Commit: `[flywheel] publication service: full cycle orchestration`

---

## Task 15: RunSnapshot Integration

**Files:**
- Modify: `src/models/run.py`
- Test: `tests/flywheel/test_runsnapshot_integration.py`

**Step 1: Write failing tests**

Tests:
- RunSnapshot can be created with new optional fields (occupation_bridge_version_id, nationality_classification_version_id, nitaqat_target_version_id)
- Default values are None (backward compatible)
- Existing RunSnapshot creation (without new fields) still works

**Step 2:** Run tests — expect FAIL.

**Step 3: Add optional fields to RunSnapshot**

```python
# Add to RunSnapshot:
occupation_bridge_version_id: UUID | None = None
nationality_classification_version_id: UUID | None = None
nitaqat_target_version_id: UUID | None = None
```

**Step 4:** Run tests — expect PASS. Also run `pytest tests/ -x -q` to verify ALL 682 existing tests pass.

**Step 5:** Commit: `[flywheel] RunSnapshot: add workforce version references (Amendment 5)`

---

## Task 16: Flywheel Health Metrics

**Files:**
- Create: `src/flywheel/health.py`
- Test: `tests/flywheel/test_flywheel_health.py`

**Step 1: Write failing tests**

Test `FlywheelHealth` model:
- Has all standard metrics (total_engagements, library versions, entry counts)
- Has backlog metrics (Amendment 10): override_backlog_count, avg_days_since_last_publication, draft_count_pending_review, pct_entries_assumed_vs_calibrated, pct_shared_knowledge_sanitized

Test `FlywheelHealthService`:
- Computes health from all library managers and stores
- Counts are accurate
- workforce_coverage_pct computed correctly

**Step 2:** Run tests — expect FAIL.

**Step 3: Implement**

FlywheelHealth model. FlywheelHealthService takes all managers/stores and computes metrics.

**Step 4:** Run tests — expect PASS.

**Step 5:** Commit: `[flywheel] health metrics with backlog reporting`

---

## Task 17: Integration Tests

**Files:**
- Test: `tests/flywheel/test_integration.py`

**Step 1: Write end-to-end integration tests**

Tests:
- Full lifecycle: create mapping overrides → build draft → publish → RunSnapshot references version → get_version loads correct data
- Publication cycle with no changes is idempotent
- Assumption library: sector lookup returns sector-specific + economy-wide defaults
- Scenario pattern: record 3 similar engagements → suggest_template returns merged pattern
- Calibration note → promote to assumption default
- Engagement memory → promote to pattern

**Step 2:** Run tests — expect PASS (all implementations already exist).

**Step 3:** Run full test suite: `pytest tests/ -x -q`. Expect ALL tests pass (682 existing + 60+ new).

**Step 4:** Commit: `[flywheel] integration tests: full lifecycle verification`

---

## Task 18: Documentation

**Files:**
- Create: `docs/mvp12_knowledge_flywheel.md`

**Step 1:** Write documentation covering:
- The 6 knowledge types
- Versioning model (immutable versions, draft/publish workflow)
- Two-layer scope model (private vs promoted)
- Override → mapping library flow
- Engagement patterns → templates flow
- Workforce bridge improvement over time
- RunSnapshot reproducibility with library versions
- Publication cycle workflow
- The lock-in effect (20-30 engagements → proprietary asset)

**Step 2:** Commit: `[flywheel] MVP-12 documentation`

---

## Task 19: Final Verification

**Step 1:** Run `pytest tests/ -v --tb=short` — ALL tests must pass.

**Step 2:** Verify test count increased by 60+ from baseline 682.

**Step 3:** Run `pytest tests/flywheel/ -v --tb=short` — all flywheel tests pass.

**Step 4:** Use `superpowers:verification-before-completion` to confirm everything works.

**Step 5:** Use `superpowers:requesting-code-review` for pre-review quality check.

---

## Dependency Graph

```
Task 0 (workforce files) ─┐
Task 1 (enums) ───────────┤
Task 2 (stores) ──────────┤
Task 3 (generic base) ────┤
                           ├── Task 4,5,6 (mapping) ──────────┐
                           ├── Task 7,8 (assumption) ─────────┤
                           ├── Task 9 (scenario patterns) ────┤
                           ├── Task 10 (calibration) ─────────┤
                           ├── Task 11 (engagement memory) ───┤
                           └── Task 12 (workforce refinement) ┤
                                                               ├── Task 13,14 (publication)
                                                               ├── Task 15 (RunSnapshot)
                                                               ├── Task 16 (health)
                                                               ├── Task 17 (integration tests)
                                                               ├── Task 18 (docs)
                                                               └── Task 19 (verification)
```

**Parallelizable:** Tasks 4-6, 7-8, 9, 10, 11, 12 can all run in parallel after Tasks 0-3 complete.

---

## Amendments Checklist

- [x] Amendment 1: ReuseScopeLevel on all flywheel objects (Task 1)
- [x] Amendment 2: Draft/Version separation (Tasks 4, 7)
- [x] Amendment 3: Non-numeric assumption values (Task 7)
- [x] Amendment 4: Versioned workforce artifacts (Task 12)
- [x] Amendment 5: Extended RunSnapshot (Task 15)
- [x] Amendment 6: Publication quality gates (Task 13)
- [x] Amendment 7: Scenario pattern lineage (Task 9)
- [x] Amendment 8: Promotion paths for calibration/memory (Tasks 10, 11)
- [x] Amendment 9: Normalized DB storage — deferred to DB implementation
- [x] Amendment 10: Backlog health metrics (Task 16)
- [x] Amendment 11: UUID for actor fields (all models use UUID)
- [x] Amendment 12: Machine-readable diffs (Tasks 4, 7)
