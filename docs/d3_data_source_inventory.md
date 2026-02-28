# D-3 Data Source Inventory

## Overview

This document catalogs all external data sources relevant to ImpactOS,
their API availability, access requirements, and integration status.
It is the single reference for the data foundation layer.

**Last updated:** 2026-02-28
**Phase:** D-3 (External Data APIs + Data Foundation)

---

## 1. KAPSARC Data Portal

| Field | Value |
|-------|-------|
| **URL** | https://datasource.kapsarc.org |
| **API Base** | `https://datasource.kapsarc.org/api/v2/` |
| **Platform** | OpenDataSoft |
| **Auth** | Anonymous read access (rate-limited) |
| **Formats** | JSON, CSV, Excel |
| **ImpactOS Relevance** | **Core** — IO tables, multipliers, GDP by activity |

### Datasets

| Dataset ID | Description | Records | ImpactOS Use |
|------------|-------------|---------|--------------|
| `input-output-table-at-current-prices` | Saudi IO table (SAR thousands, division-level) | ~2000+ | Z matrix, x vector |
| `input-output-table-type-i-multiplier` | Published Type I output multipliers | ~20 | Benchmark validation |
| `gross-domestic-product-by-kind-of-economic-activity-at-current-prices-2018-100` | GDP by ISIC activity | ~200+ | Sector output weights |
| `main-labor-market-indicators` | Employment, wages, participation | ~500+ | Employment coefficients |
| `gosi-beneficiaries` | GOSI contributor counts | ~100+ | Workforce satellite |
| `labor-force-indicators` | Labor force by nationality, gender | ~200+ | Workforce satellite |

### API Pattern

```
GET /catalog/datasets/{dataset_id}/records?limit=100&offset=0
```

Pagination via `limit` + `offset`. Response includes `total_count` for iteration.

---

## 2. World Bank WDI API

| Field | Value |
|-------|-------|
| **URL** | https://data.worldbank.org |
| **API Base** | `https://api.worldbank.org/v2/` |
| **Auth** | None required |
| **Formats** | JSON, XML |
| **ImpactOS Relevance** | **Core** — GDP deflators, trade ratios, macro benchmarks |

### Indicators

| Indicator Code | Description | ImpactOS Use |
|----------------|-------------|--------------|
| `NY.GDP.MKTP.CD` | GDP (current US$) | GDP cross-validation |
| `NY.GDP.DEFL.ZS.AD` | GDP deflator (base year varies) | Real/nominal conversion |
| `SL.IND.EMPL.ZS` | Employment in industry (% of total) | Employment benchmark |
| `SL.SRV.EMPL.ZS` | Employment in services (% of total) | Employment benchmark |
| `NE.TRD.GNFS.ZS` | Trade (% of GDP) | Import share validation |
| `BX.KLT.DINV.WD.GD.ZS` | FDI net inflows (% of GDP) | Investment context |

### API Pattern

```
GET /country/SAU/indicator/{code}?format=json&per_page=100&date=1990:2025
```

Response is a 2-element array: `[metadata, data_records]`.

---

## 3. ILOSTAT (ILO Statistics)

| Field | Value |
|-------|-------|
| **URL** | https://ilostat.ilo.org |
| **API Base** | `https://www.ilo.org/sdmx/rest/` |
| **Alt** | Bulk CSV at `https://ilostat.ilo.org/data/bulk/` |
| **Auth** | None required |
| **Formats** | SDMX-JSON, CSV |
| **ImpactOS Relevance** | **Important** — Employment by ISIC activity |

### Key Dataflows

| Dataflow | Description | ImpactOS Use |
|----------|-------------|--------------|
| `DF_EMP_TEMP_SEX_ECO_NB` | Employment by economic activity (ISIC4) | Employment-to-output ratios |
| `DF_EMP_TEMP_SEX_OCU_NB` | Employment by occupation (ISCO-08) | Occupation structure |

### API Pattern (SDMX REST)

```
GET /data/ILO,{dataflow},{version}/{country}..{sex}.{activity}?format=jsondata&lastNObservations=5
```

SDMX-JSON is complex — nested structure with dimensions and observations.
Bulk CSV fallback: download full dataset and filter for SAU.

---

## 4. SAMA (Saudi Central Bank)

| Field | Value |
|-------|-------|
| **URL** | https://www.sama.gov.sa |
| **Portal** | `https://www.sama.gov.sa/en-US/EconomicReports/pages/database.aspx` |
| **Auth** | Manual download (no confirmed REST API yet) |
| **Formats** | Excel, PDF |
| **ImpactOS Relevance** | **Core** — CPI deflators, bank credit by sector, BoP |

### Available Data (Manual Download)

| Dataset | Description | ImpactOS Use |
|---------|-------------|--------------|
| Monthly Statistical Bulletin | CPI, money supply, interest rates | Deflators |
| Annual Statistics | Bank credit by ISIC sector | Sector financing validation |
| Balance of Payments | BoP components, FDI | Trade/import validation |

### API Status

SAMA announced API connectivity via the open.data.gov.sa real-time APIs page.
Current access is primarily through Excel/PDF downloads from the portal.
Programmatic access may require the Saudi Open Data Portal as intermediary.

---

## 5. Saudi Open Data Portal (open.data.gov.sa)

### National Open Data Ecosystem

The Saudi national open data platform, managed by SDAIA (Saudi Data and
Artificial Intelligence Authority), represents a major data landscape asset:

- **11,439+ datasets** from 289 government organizations
- **Formats:** CSV, JSON, XML
- **API access** for many datasets; no registration required for downloads
- **Open Data License** for reuse
- **URL:** https://open.data.gov.sa/en/datasets

### Real-Time APIs

The portal's real-time API page (`open.data.gov.sa/en/pages/real-time-api`)
lists APIs from government providers relevant to ImpactOS:

| API Provider | What It Offers | ImpactOS Relevance |
|-------------|----------------|-------------------|
| **GASTAT** | Population, housing, health, education, training, labor market, GDP, economic indicators | **Core** — GDP, employment, sector data |
| **SAMA** | Financial data with standardized connection modes | **Core** — Bank credits by ISIC4, BoP, FDI, deflators |
| **KAPSARC Energy Data Portal** | Energy usage, production, distribution | **Core** — IO tables, multipliers, GDP by activity |
| **KAPSARC Data Hub** | Fuel sources, process groups, regions | Supporting — Energy sector detail |
| **MHRSD** | Human resources and social development data | **Important** — Labor regulations, Nitaqat data |
| **Saudi Business Center** | Financial statements by fiscal year | Supporting — Sector revenue validation |
| **Ministry of Commerce** | Commercial registration, certificates of origin | Supporting — Business establishment data |
| **Saudi Geological Survey** | Mining sites, licenses, geological maps | Supporting — Mining sector data |
| **Royal Commission for Riyadh City** | Infrastructure, establishments, transportation | Supporting — Regional analysis |
| **MEWA** | Agricultural data (camels, bees, fishermen, farms) | Supporting — Agriculture sector |
| **Council of Health Insurance** | Health insurance coverage verification | Supporting — Healthcare sector |
| **Saudi Post** | National Address APIs, location data | Not directly relevant |
| **National Center of Meteorology** | Air quality monitoring data | Not directly relevant |

### Portal API (CKAN-based)

```
Base: https://open.data.gov.sa/api/3/
GET /action/package_list
GET /action/package_search?q=GASTAT
```

**Note:** The portal may block automated requests (403 responses observed).
Direct API access to individual provider APIs is more reliable.

---

## 6. GOSI Open Data Platform

### Major Discovery (Launched October 2024)

| Field | Value |
|-------|-------|
| **URL** | https://gosi.gov.sa (Statistics and Data section) |
| **Mirror** | KAPSARC Data Portal (with API access) |
| **Auth** | Free access, open data license |
| **Formats** | Multiple download/share formats |
| **ImpactOS Relevance** | **Important** — Employment by sector + nationality |

### Available Data

| Dataset | Description | Frequency |
|---------|-------------|-----------|
| Saudi vs non-Saudi active contributor counts | Employment by nationality | Quarterly |
| Establishment counts by size | Small (1-5), Micro (6-49), Medium (50-249), Large (250+) | Quarterly |
| Beneficiary/pension data by sector | Public vs private sector | Quarterly |
| Regional employment by gender | Geographic employment distribution | Quarterly |
| Suggested Salary Calculator | Salary ranges by sector | Live |

### Key Statistics (Q3 2025 Reference)

- 1.73M female GOSI employees
- 11.5M male GOSI employees
- AI-powered virtual assistant for data queries

### Significance

This partially closes our gap on GOSI employment by sector + nationality.
Data is accessible via the KAPSARC Data Portal API for programmatic access.

---

## 7. National Data Bank (data.gov.sa)

| Field | Value |
|-------|-------|
| **URL** | https://data.gov.sa |
| **Type** | Government Secure Network (GSN) platform |
| **Access** | Restricted — government entities |
| **ImpactOS Relevance** | Not accessible for external integration |

Central polyglot data repository consolidating national data assets.
Separate from open.data.gov.sa — this is the internal government data lake.
Data sharing and monetization platform for inter-government use.

---

## 8. MHRSD / Nitaqat Data

### Publicly Available Saudization Data

**Nitaqat Mutawar** (updated May 2021):
- Consolidated sectors with 3-year Saudization plans
- Smooth relationship between worker count and required Saudization rate

**Sector-Specific Saudization Rates** (from published regulations):

| Sector | Rate | Effective |
|--------|------|-----------|
| Healthcare — Medical labs | 70% | Current |
| Healthcare — Hospitals | 65% | Current |
| Healthcare — Pharmacies | 35-55% | Current |
| Engineering | 30% | July 2025 |
| Accounting | 40% → 70% (+10%/year) | October 2025 |
| Tourism | 41 professions localized | April 2025 |

**Qiwa platform:** Real-time Saudization monitoring at company level
(not public aggregate). Classification reviewed every 26 weeks by MHRSD.

---

## 9. Revised Gap Analysis

| Requirement | Previous Status | New Status | What Changed |
|-------------|----------------|------------|--------------|
| GOSI employment by sector + nationality | Not available | Partially available | GOSI open data has Saudi/non-Saudi contributor counts; need to verify ISIC-level granularity |
| SAMA financial data | Download only | API confirmed | Real-time API listed on open.data.gov.sa |
| GASTAT labor/GDP via API | Portal only | API confirmed | API listed on open.data.gov.sa |
| MHRSD Saudization data | Not available | Partial | API exists on open.data.gov.sa; sector quotas published in regulations |
| Salary/wage by sector | Not available | Proxy available | GOSI Suggested Salary Calculator has sector salary ranges |
| Nitaqat rates by sector | Not available | Rules published | Sector-specific quotas in MHRSD regulations, codifiable as constraint data |

### Coverage Assessment

**Previous coverage:** ~60% of moat module data requirements

**Updated coverage:** ~80-85% of moat module data requirements

**Remaining gaps** are genuinely proprietary methodology:
- Three-tier nationality classification (SG intellectual property)
- Capacity caps by sector (consulting judgment + client data)
- These get built through the Knowledge Flywheel, not external APIs

---

## 10. Integration Status

| Source | API Tested | Fetch Script | Parser | Curated Output |
|--------|-----------|--------------|--------|----------------|
| KAPSARC IO Table | Pending | Pending | Pending | Pending |
| KAPSARC Multipliers | Pending | Pending | Pending | Pending |
| KAPSARC GDP by Activity | Pending | Pending | Pending | Pending |
| World Bank WDI | Pending | Pending | Pending | Pending |
| ILOSTAT Employment | Pending | Pending | Pending | Pending |
| SAMA | Pending | Pending | Pending | Pending |
| GOSI (via KAPSARC) | Pending | Pending | Pending | Pending |
| Open Data Portal | Pending | Pending | Pending | Pending |

This table will be updated as D-3 implementation proceeds.
