# D-4 Workforce Data Foundation

## What MVP-11 Will Find Here

This module provides **curated datasets** for workforce analysis. It does NOT
contain runtime analysis logic — that is MVP-11's job.

### Employment Coefficients
- **Load via**: `satellite_coeff_loader.load_satellite_coefficients()`
- **Feeds**: `SatelliteCoefficients` in `src/engine/satellites.py`
- **Key property**: Denominator is gross output (x), NOT GDP/value-added
- **Units**: Explicitly tracked via `OutputDenomination` enum

### Occupation Bridge
- **Load via**: `build_occupation_bridge.load_occupation_bridge()`
- **Interface**: `bridge.get_occupation_shares(sector_code) -> dict[str, float]`
- **Granularity**: Section-level only (A-T) for v1
- **Note**: Aggregate division-level impacts to sections via `ConcordanceService`
  BEFORE applying the bridge

### Nitaqat / Saudization
- **Layer A (Rules)**: `nitaqat_rules.NitaqatRuleCatalog` — detailed published rules
- **Layer B (Targets)**: `nitaqat_macro_targets.MacroSaudizationTargets` — simplified
- **Build script**: `scripts/build_nitaqat_data.py`

### Nationality Classification
- **Load via**: `build_nationality_classification` module
- **Interface**: `classification_set.get_tier(sector_code, occupation_code)`
- **Output**: Tier-based (saudi_ready / saudi_trainable / expat_reliant)
- **Use ranges, not point estimates**: saudi_ready=0.70-1.00, trainable=0.20-0.60, expat=0.00-0.20
- **Override mechanism**: `classification_set.apply_overrides(overrides)` for Knowledge Flywheel

### Known Gaps and Confidence Levels
- Employment coefficients: ESTIMATED when real data available, ASSUMED for synthetics
- Occupation bridge: ASSUMED (v1, expert judgment; future: ILO cross-tab + RAS)
- Nitaqat rules: HARD (published regulations)
- Nationality classification: ASSUMED (v1, expert judgment)

### How to Update Nitaqat Data
When new MHRSD resolutions are published:
1. Add new `NitaqatRule` entries in `scripts/build_nitaqat_data.py`
2. Re-derive macro targets
3. Run `python -m scripts.build_nitaqat_data`
4. Commit updated curated JSON files
