# MVP-12: Knowledge Flywheel

## Overview

The Knowledge Flywheel captures six types of knowledge that accumulate across engagements:

1. **Mapping patterns** -- procurement text to ISIC sector mappings with confidence scores
2. **Assumption defaults** -- sector-level default values (import shares, employment coefficients, phasing, deflators)
3. **Scenario patterns** -- reusable project templates with typical sector shares and parameters
4. **Calibration notes** -- observations about model accuracy (where multipliers diverged from reality)
5. **Engagement memories** -- lessons learned (client challenges, evidence requests, methodology disputes)
6. **Workforce classifications** -- refined nationality tier assignments for sector-occupation pairs

Each knowledge type feeds back into subsequent engagements, reducing setup time and improving accuracy.

## Versioning Model

Mapping libraries, assumption libraries, and workforce bridges use immutable versioned snapshots:

- **Draft/Publish workflow**: Changes are assembled in a mutable `Draft`, reviewed, then frozen into an immutable `Version`.
- **Version numbers are monotonically increasing** (1, 2, 3, ...), managed by `VersionedLibraryManager._next_version_number`.
- **Immutability**: Published versions are Pydantic `frozen=True` models. Once published, they cannot be modified.
- **Parent chaining**: Each version records `parent_version_id` and `changes_from_parent` for audit trail.
- **Active version**: Exactly one version is "active" at a time via `store.set_active()`. Old versions remain accessible by ID.

Scenario patterns, calibration notes, and engagement memories use append-only stores (no versioning, no publish cycle).

## Two-Layer Scope Model

Knowledge items have a `ReuseScopeLevel` controlling visibility:

| Scope | Meaning |
|---|---|
| `WORKSPACE_ONLY` | Private to the originating workspace. Default for new items. |
| `SANITIZED_GLOBAL` | Promoted for cross-workspace reuse after client-identifying data is removed. |
| `GLOBAL_INTERNAL` | Available to all workspaces internally (e.g., benchmark data). |

Items start as `WORKSPACE_ONLY`. Promotion to broader scopes requires setting `sanitized_for_promotion = True` and updating `reuse_scope`.

## Mapping Library Flow

The mapping library improves through analyst overrides captured by `LearningLoop`:

1. **Record overrides**: When an analyst changes a suggested sector mapping, `LearningLoop.record_override()` stores the `OverridePair` (suggested vs. final sector).
2. **Build draft**: `MappingLibraryManager.build_draft(learning_loop=...)` calls:
   - `learning_loop.update_confidence_scores()` -- adjusts existing entry confidence as `(old + override_accuracy) / 2`
   - `learning_loop.extract_new_patterns()` -- groups overrides by `final_sector_code`, extracts patterns appearing >= `min_frequency` times, deduplicates against existing entries
3. **Publish**: The draft is frozen into a `MappingLibraryVersion` and set as active.
4. **Reuse**: Future engagements query the active mapping library for pre-populated suggestions.

Each version tracks `added_entry_ids`, `removed_entry_ids`, and `changed_entries` for full change audit.

## Engagement Patterns to Templates

`ScenarioPatternLibrary` accumulates reusable project templates:

1. **Record**: `record_engagement_pattern()` receives sector shares, project type, and engagement metadata.
2. **Merge or create**: Cosine similarity is computed between the new engagement's sector shares and existing patterns of the same `project_type`. If similarity > 0.8, the pattern is merged via rolling average: `(old * count + new) / (count + 1)`.
3. **Lineage**: `contributing_engagement_ids` tracks which engagements fed the pattern. `merge_history` records each merge with similarity scores.
4. **Confidence**: Automatically upgrades from "low" (1 engagement) to "medium" (3+) to "high" (5+).
5. **Suggest**: `suggest_template(project_type)` returns the pattern with highest `engagement_count`.

## Workforce Bridges

`WorkforceBridgeRefinement` improves nationality tier classifications:

1. **Record**: `record_engagement_overrides()` accumulates `ClassificationOverride` objects across engagements.
2. **Coverage tracking**: `get_refinement_coverage()` reports unique (sector, occupation) pairs calibrated and per-engagement breakdowns.
3. **Refine**: `build_refined_classifications(base)` applies all overrides to a `NationalityClassificationSet`, producing a new set where overridden cells have updated tiers.

Overrides are additive -- later overrides for the same cell replace earlier ones during `apply_overrides`.

## RunSnapshot Reproducibility

`RunSnapshot` (frozen, immutable) pins exact library states at run time:

```
mapping_library_version_id: UUID
assumption_library_version_id: UUID
occupation_bridge_version_id: UUID | None
nationality_classification_version_id: UUID | None
```

To reproduce a run years later: load each version by ID from the store. Because versions are immutable, the exact same inputs are guaranteed.

## Publication Cycle

`FlywheelPublicationService.publish_new_cycle()` orchestrates a full cycle:

1. Build mapping draft (incorporating `LearningLoop` overrides if provided)
2. Build assumption draft (from current active version)
3. Validate mapping draft against `PublicationQualityGate`:
   - Steward review requirement
   - Duplicate entry detection (same pattern + sector_code)
   - Conflict detection (same pattern, different sector_codes)
4. Publish if content differs from active version
5. Return `PublicationResult` with version references, pattern counts, workforce coverage

**Idempotency**: If a draft has identical content to the active version (compared by entry IDs, patterns, sector codes, and confidences), no new version is created. This prevents version inflation from no-op publication cycles.

## Promotion Paths

### Calibration Note to Assumption Default

1. `CalibrationNote` is created with `promotion_status = RAW`
2. After review: set `promotion_status = REVIEWED`
3. After promotion: set `promotion_status = PROMOTED` and `promoted_to = assumption_default_id`
4. The target assumption default in the assumption library is updated in the next publication cycle

### Engagement Memory to Pattern/Rule

1. `EngagementMemory` is created with `promotion_status = RAW`
2. After review: set `promotion_status = REVIEWED`
3. After promotion: set `promotion_status = PROMOTED` and `promoted_to = pattern_id` or governance rule ID

Both paths use `PromotionStatus` enum: `RAW -> REVIEWED -> PROMOTED` (or `DISMISSED`).

## The Lock-In Effect

After 20-30 engagements, the flywheel creates a compounding proprietary asset:

- **Mapping library**: Hundreds of validated procurement-to-sector mappings with calibrated confidences, replacing manual lookup
- **Assumption defaults**: Sector-specific defaults calibrated against actual outcomes, not generic benchmarks
- **Scenario templates**: Ready-made project structures with rolling-average sector shares from real projects
- **Calibration corpus**: Documented where the model was wrong and by how much, feeding continuous improvement
- **Engagement memory**: Institutional knowledge of client objections and evidence requirements
- **Workforce tiers**: Empirically refined nationality classifications replacing assumed values

Each new engagement both benefits from and contributes to this asset. The gap between ImpactOS and a fresh competitor widens with every project completed.

## Health Metrics

`FlywheelHealthService.compute_health()` returns a `FlywheelHealth` snapshot:

| Metric | Source |
|---|---|
| `mapping_library_version` | Active mapping version number |
| `mapping_entry_count` | Number of entries in active mapping library |
| `mapping_accuracy` | Accuracy at publish time |
| `assumption_default_count` | Number of defaults in active assumption library |
| `assumption_library_version` | Active assumption version number |
| `scenario_pattern_count` | Total patterns in pattern library |
| `calibration_note_count` | Total calibration notes |
| `engagement_memory_count` | Total engagement memories |
| `workforce_coverage_pct` | % of (sector, occupation) cells calibrated |
| `last_publication` | Timestamp of most recent publication |

Backlog metrics (Amendment 10) track `override_backlog_count`, `avg_days_since_last_publication`, `draft_count_pending_review`, and `pct_entries_assumed_vs_calibrated` for operational monitoring.
