# D-4: Workforce & Saudization Data Inventory

> Sprint: D-4 (Data Foundation)
> Status: Complete
> Tests: 77 new (2337 total)
> Confidence: All v1 entries are ASSUMED unless calibrated against GOSI/DataSaudi

---

## Purpose

D-4 produces curated workforce datasets that MVP-11 (Workforce Satellite Service)
will consume at runtime. This sprint is a **data foundation** — it does NOT build
a runtime service. It creates:

1. Employment coefficients (jobs per unit gross output)
2. Sector-to-occupation bridge matrix (ISIC section -> ISCO-08 major group)
3. Nitaqat/Saudization rules (catalog + macro targets)
4. Three-tier nationality classification (saudi_ready / saudi_trainable / expat_reliant)
5. GOSI employment parser (synthetic + real data)
6. Satellite coefficient loader (bridges D-4 data to existing SatelliteCoefficients)

---

## Dataset Summary

| Dataset | Granularity | Sectors | Source | Confidence |
|---------|-------------|---------|--------|------------|
| Employment Coefficients | Section (A-T) | 20 | ILO + KAPSARC IO x-vector | ESTIMATED / ASSUMED |
| Occupation Bridge | Section x ISCO major | 20 x 10 | Expert judgment v1 | ASSUMED |
| Nitaqat Rule Catalog | Rule-level | ~20 rules | MHRSD published regulations | HARD |
| Macro Saudization Targets | Section (A-U) | 21 | Derived from rules | ESTIMATED |
| Nationality Classification | Section x ISCO major | 20 x 10 = 200 | Expert judgment v1 | ASSUMED |
| GOSI Employment | Section (A-T) | 20 | DataSaudi calibrated | ASSUMED |

---

## Confidence Vocabulary (Amendment 1)

Two orthogonal dimensions:

### Source Confidence (`ConstraintConfidence` from `src/models/common.py`)
- **HARD**: Published regulation or official statistics (e.g., Nitaqat rules)
- **ESTIMATED**: Derived from real data with methodology (e.g., ILO/KAPSARC coefficients)
- **ASSUMED**: Expert judgment or synthetic benchmark (e.g., occupation bridge v1)

### Quality Confidence (`QualityConfidence` from `src/data/workforce/unit_registry.py`)
- **high**: Well-calibrated, multiple sources agree
- **medium**: Single credible source, reasonable cross-checks
- **low**: Synthetic, expert judgment, or placeholder

---

## File Inventory

### Source Modules

| File | Purpose |
|------|---------|
| `src/data/workforce/__init__.py` | Package init |
| `src/data/workforce/unit_registry.py` | OutputDenomination, QualityConfidence, EmploymentCoefficient, denomination_factor() |
| `src/data/workforce/occupation_bridge.py` | OccupationBridgeEntry, OccupationBridge with validate() |
| `src/data/workforce/nitaqat_rules.py` | NitaqatRule, NitaqatRuleCatalog with lookups |
| `src/data/workforce/nitaqat_macro_targets.py` | SectorSaudizationTarget, MacroSaudizationTargets |
| `src/data/workforce/nationality_classification.py` | NationalityTier, NationalityClassification, override mechanism |
| `src/data/workforce/satellite_coeff_loader.py` | Bridges D-4 data to SatelliteCoefficients (KEY integration) |
| `src/data/workforce/build_employment_coefficients.py` | Builds coefficients from ILO + KAPSARC IO data |
| `src/data/workforce/build_occupation_bridge.py` | Builds bridge from expert structural patterns |
| `src/data/workforce/build_nationality_classification.py` | Builds 200-cell classification matrix |
| `src/data/parsers/gosi_employment_parser.py` | GOSI employment data parser + synthetic builder |
| `scripts/build_nitaqat_data.py` | Builds Nitaqat rule catalog + macro targets |

### Taxonomy

| File | Purpose |
|------|---------|
| `data/taxonomy/isco08_major_groups.json` | 10 ISCO-08 major occupation groups (codes 0-9) |

### Data Source Registry

`src/data/source_registry.py` updated with 5 new entries:
- `gosi_employment` — GOSI private-sector employment by nationality
- `nitaqat_rule_catalog` — Nitaqat/Saudization published rules
- `nitaqat_macro_targets` — Sector-level Saudization targets
- `occupation_bridge` — ISIC-to-ISCO bridge matrix
- `nationality_classification` — Three-tier nationality classification

---

## Key Design Decisions

### 1. Denominator = Gross Output, NOT GDP

Employment coefficients use **gross output (x-vector)** as the denominator,
not GDP or value-added. This is correct for Leontief IO analysis because:
- `delta_jobs = jobs_coeff * delta_x` where delta_x is the output change
- Using GDP would double-count intermediate flows
- The x-vector comes from KAPSARC IO model (D-3)

### 2. Pure Data Objects (Amendment 2)

All data classes are frozen dataclasses with NO analysis methods.
Queries like `get_trainable_entries()` return filtered data — they don't compute.
Analysis belongs in MVP-11's service layer.

### 3. Section-Level Only for v1

All datasets use ISIC Rev.4 **section** granularity (20 sectors, A-T).
Division-level (84 sectors) is deferred to v2 when ConcordanceService
can aggregate properly.

### 4. Provenance Blocks (Amendment 4)

Every curated JSON output includes a `_provenance` block:
```json
{
  "_provenance": {
    "builder": "build_employment_coefficients.py",
    "builder_version": "d4_v1",
    "build_timestamp": "2026-02-28T...",
    "source_ids": ["ilo+kapsarc_io_2019"],
    "method": "ILO employment / KAPSARC IO gross output x-vector",
    "notes": "Denominator is gross output (x), NOT GDP/value-added"
  }
}
```

### 5. Nullable Macro Targets (Amendment 6)

Section U (extraterritorial organizations) has `target = None`,
signaling "not applicable" rather than zero.

### 6. Knowledge Flywheel Override Mechanism

`NationalityClassificationSet.apply_overrides()` produces a NEW set
without mutating the original. Overrides carry analyst_id, rationale,
and timestamp for audit trail.

---

## How MVP-11 Will Use This Data

### Loading Employment Coefficients
```python
from src.data.workforce.satellite_coeff_loader import load_satellite_coefficients

loaded = load_satellite_coefficients()
# loaded.coefficients -> SatelliteCoefficients (compatible with SatelliteAccounts)
# loaded.provenance -> CoefficientProvenance (source years, fallback flags)
```

### Loading Occupation Bridge
```python
from src.data.workforce.build_occupation_bridge import (
    build_occupation_bridge, load_occupation_bridge,
)

bridge = build_occupation_bridge()
shares = bridge.get_occupation_shares("F")  # Construction
# {"7": 0.35, "8": 0.15, "9": 0.30, ...}
```

### Loading Nitaqat Rules
```python
from scripts.build_nitaqat_data import build_rule_catalog

catalog = build_rule_catalog()
health_rules = catalog.get_rules_for_sector("Q")
quota_rules = catalog.get_rules_by_type(NitaqatRuleType.SECTOR_QUOTA)
```

### Loading Nationality Classification
```python
from src.data.workforce.build_nationality_classification import (
    build_nationality_classification,
)

classification = build_nationality_classification()
summary = classification.get_sector_summary("F")
# {"saudi_ready": 0, "saudi_trainable": 3, "expat_reliant": 7}
```

---

## Test Coverage

| Test File | Tests | Covers |
|-----------|-------|--------|
| `test_unit_registry.py` | 11 | Denomination conversion, coefficient creation, satellite array builder |
| `test_employment_coefficients.py` | 10 | Building, synthetic fallback, denominator verification, save/load |
| `test_occupation_bridge.py` | 10 | Validation, shares sum, structural patterns, save/load |
| `test_nitaqat_rules.py` | 10 | All rules, HARD confidence, lookups, phased rules, counting rules |
| `test_nitaqat_macro_targets.py` | 8 | All sections, U=null, range consistency, rule references |
| `test_nationality_classification.py` | 13 | 200 cells, tiers, overrides, immutability, save/load |
| `test_gosi_parser.py` | 7 | Calibration, sector totals, saudi_share range, save |
| `test_satellite_coeff_loader.py` | 8 | SatelliteCoefficients compatibility, provenance, fallback |
| **Total** | **77** | |

---

## Upgrade Path

### From Synthetic to Real Data
1. Obtain GOSI micro-data → replace `build_synthetic_gosi_data()` with `parse_gosi_employment_file()`
2. Obtain ILO cross-tab (activity x occupation) → replace expert bridge with RAS-balanced matrix
3. Obtain GASTAT IO tables → replace synthetic x-vector with official gross output

### From Section to Division Level
1. Build division-level (84-sector) employment coefficients
2. Use ConcordanceService for 84→20 aggregation
3. Update SectorGranularity to DIVISION in coefficient metadata

### From Expert to Empirical Classification
1. Calibrate nationality tiers against GOSI nationality breakdowns
2. Use Knowledge Flywheel overrides to refine per analyst feedback
3. Promote ASSUMED → ESTIMATED as data quality improves
