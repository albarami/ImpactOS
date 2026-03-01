"""Parse KAPSARC IO table data into IOModelData format.

Transforms raw KAPSARC API JSON (OpenDataSoft format) into the
curated IO model structure compatible with the engine.

The KAPSARC IO table is division-level (84 sectors). This parser:
1. Extracts the Z matrix (intermediate transactions)
2. Extracts the x vector (gross output)
3. Maps KAPSARC sector names to ISIC Rev.4 codes
4. Produces IOModelData-compatible JSON

Input: data/raw/kapsarc/io_current_prices.json
Output: data/curated/saudi_io_kapsarc_{year}.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class KapsarcIOParseResult:
    """Result of parsing KAPSARC IO table data."""

    year: int
    sector_codes: list[str]
    sector_names: dict[str, str]
    Z: np.ndarray
    x: np.ndarray
    total_output: float
    record_count: int
    warnings: list[str]


def _extract_sector_mapping(records: list[dict]) -> dict[str, str]:
    """Extract unique sector codes and names from records.

    KAPSARC records have fields like 'sector', 'sector_code', or 'activity'.
    This function discovers the actual field names dynamically.
    """
    sector_map: dict[str, str] = {}

    # Try common field name patterns for sector identifier
    code_fields = [
        "sector_code", "code", "isic_code", "activity_code",
        "sector", "economic_activity",
    ]
    name_fields = [
        "sector_name", "name", "activity_name", "description",
        "economic_activity_name",
    ]

    if not records:
        return sector_map

    # Discover field names from first record
    sample = records[0]
    available = set(sample.keys())

    code_field = None
    for f in code_fields:
        if f in available:
            code_field = f
            break

    name_field = None
    for f in name_fields:
        if f in available:
            name_field = f
            break

    if code_field:
        for rec in records:
            code = str(rec.get(code_field, "")).strip()
            name = str(rec.get(name_field, "")).strip() if name_field else code
            if code:
                sector_map[code] = name

    return sector_map


# Non-sector labels that appear in IO tables as accounting rows/columns
_NON_SECTOR_LABELS = {
    "Change in inventories",
    "Compensation of employees",
    "Consumption of fixed capital formation",
    "Export of goods",
    "Export of services",
    "Final Demand",
    "Final consumption expenditures",
    "Fixed capital Formation",
    "Government final consumption expenditures",
    "Gross Value Added",
    "Gross capital formation",
    "Gross operating surplus",
    "Households final consumption expenditures",
    "Net operating Surplus",
    "Net tax on products",
    "Non profit institutions serving household final consumption expenditures",
    "Other subsidies on production",
    "Other taxes on production",
    "Petroleum Exports",
    "Primary inputs at Purchaser prices",
    "Primary inputs at basic prices",
    "Total Export",
    "Total Inputs",
    "Total Intermediate Consumption",
    "Total Output",
    "Total imports",
    # Duplicate sector name (without comma variant has zero output)
    "Manufacture of woods, wood products and cork except furniture",
}


def _is_economic_sector(name: str) -> bool:
    """Return True if name is an economic activity sector, not an accounting row."""
    return name not in _NON_SECTOR_LABELS


def parse_kapsarc_io_records(
    records: list[dict[str, Any]],
) -> list[KapsarcIOParseResult]:
    """Parse KAPSARC IO table records into structured results.

    Records are from the 'input-output-table-at-current-prices' dataset.
    Each record represents a cell in the IO table (from-sector, to-sector, value).

    Returns one KapsarcIOParseResult per available year.
    """
    if not records:
        return []

    warnings: list[str] = []

    # Discover field names
    sample = records[0]
    available_fields = set(sample.keys())

    # Common field patterns in KAPSARC IO data
    year_fields = ["year", "date", "period", "time_period", "reference_period"]
    from_fields = ["from_sector", "row_sector", "input_sector", "from_activity", "economic_activities_input"]
    to_fields = ["to_sector", "column_sector", "output_sector", "to_activity", "economic_activities_output"]
    value_fields = ["value", "amount", "flow", "transaction"]

    def _find_field(candidates: list[str]) -> str | None:
        for f in candidates:
            if f in available_fields:
                return f
        return None

    year_field = _find_field(year_fields)
    from_field = _find_field(from_fields)
    to_field = _find_field(to_fields)
    value_field = _find_field(value_fields)

    if not value_field:
        warnings.append(
            f"Could not identify value field. Available: {sorted(available_fields)}"
        )
        return []

    # Group records by year
    year_groups: dict[int, list[dict]] = {}
    for rec in records:
        yr_raw = rec.get(year_field) if year_field else None
        try:
            yr = int(str(yr_raw)[:4]) if yr_raw else 0
        except (ValueError, TypeError):
            yr = 0
        if 1900 < yr < 2100:
            year_groups.setdefault(yr, []).append(rec)

    if not year_groups:
        # All records might be for a single year
        year_groups[0] = records
        warnings.append("Could not determine year from records")

    results: list[KapsarcIOParseResult] = []

    for year, yr_records in sorted(year_groups.items()):
        # Collect unique economic sectors (exclude accounting rows)
        sectors: set[str] = set()
        if from_field:
            for rec in yr_records:
                s = str(rec.get(from_field, "")).strip()
                if s and _is_economic_sector(s):
                    sectors.add(s)
        if to_field:
            for rec in yr_records:
                s = str(rec.get(to_field, "")).strip()
                if s and _is_economic_sector(s):
                    sectors.add(s)

        sector_list = sorted(sectors)
        n = len(sector_list)

        if n == 0:
            warnings.append(f"Year {year}: no sectors found")
            continue

        sector_idx = {s: i for i, s in enumerate(sector_list)}

        # Build Z matrix (standard IO notation)
        Z = np.zeros((n, n), dtype=np.float64)  # noqa: N806
        if from_field and to_field:
            for rec in yr_records:
                from_s = str(rec.get(from_field, "")).strip()
                to_s = str(rec.get(to_field, "")).strip()
                val = rec.get(value_field, 0)
                try:
                    v = float(val) if val is not None else 0.0
                except (ValueError, TypeError):
                    v = 0.0

                if from_s in sector_idx and to_s in sector_idx:
                    Z[sector_idx[from_s], sector_idx[to_s]] = v

        # Extract x (gross output) from "Total Output" records if available
        x = np.zeros(n, dtype=np.float64)
        x_from_total = False
        if from_field and to_field:
            for rec in yr_records:
                to_s = str(rec.get(to_field, "")).strip()
                from_s = str(rec.get(from_field, "")).strip()
                if to_s == "Total Output" and from_s in sector_idx:
                    val = rec.get(value_field, 0)
                    try:
                        x[sector_idx[from_s]] = float(val) if val is not None else 0.0
                    except (ValueError, TypeError):
                        pass
                    x_from_total = True

        if not x_from_total or np.sum(x) < 1e-6:
            # Fallback: estimate from column sums of Z
            x = np.sum(Z, axis=0)
            if np.sum(x) < 1e-6:
                warnings.append(
                    f"Year {year}: Z matrix appears empty, x estimated from data"
                )

        sector_names = {s: s for s in sector_list}  # Names = codes if not mapped

        results.append(KapsarcIOParseResult(
            year=year,
            sector_codes=sector_list,
            sector_names=sector_names,
            Z=Z,
            x=x,
            total_output=float(np.sum(x)),
            record_count=len(yr_records),
            warnings=warnings.copy(),
        ))

    return results


def parse_kapsarc_io_file(raw_path: str | Path) -> list[KapsarcIOParseResult]:
    """Parse a KAPSARC IO table JSON file.

    Args:
        raw_path: Path to data/raw/kapsarc/io_current_prices.json

    Returns:
        List of KapsarcIOParseResult, one per year.
    """
    path = Path(raw_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("records", [])
    return parse_kapsarc_io_records(records)


def save_curated_io(
    result: KapsarcIOParseResult,
    output_dir: str | Path,
) -> Path:
    """Save a parsed IO result as curated JSON compatible with load_from_json.

    Output matches the schema expected by src.data.io_loader.load_from_json.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    output = {
        "model_id": f"kapsarc-io-{result.year}",
        "base_year": result.year,
        "source": "KAPSARC Data Portal",
        "denomination": "SAR_THOUSANDS",
        "sector_count": len(result.sector_codes),
        "sector_codes": result.sector_codes,
        "sector_names": result.sector_names,
        "Z": result.Z.tolist(),
        "x": result.x.tolist(),
        "metadata": {
            "origin": "kapsarc_io_parser",
            "dataset": "input-output-table-at-current-prices",
            "record_count": result.record_count,
            "total_output": result.total_output,
            "warnings": result.warnings,
        },
    }

    filename = f"saudi_io_kapsarc_{result.year}.json"
    out_path = out_dir / filename
    out_path.write_text(json.dumps(output, indent=2))
    return out_path


# ---------------------------------------------------------------------------
# ISIC Rev.4 division-to-section mapping (for 20-sector aggregation)
# ---------------------------------------------------------------------------

# Maps KAPSARC descriptive sector names to ISIC Rev.4 section letters
_KAPSARC_TO_ISIC_SECTION: dict[str, str] = {
    # A: Agriculture, forestry and fishing
    "Crop and animal production, hunting and related service activities": "A",
    "Forestry and logging": "A",
    "Fishing and aquaculture": "A",
    # B: Mining and quarrying
    "Mining of coal and lignite": "B",
    "Extraction of crude petroleum and natural gas": "B",
    "Mining of metal ores": "B",
    "Other mining and quarrying activities": "B",
    "Mining support service activities": "B",
    # C: Manufacturing
    "Manufacture of food products": "C",
    "Manufacture of beverages": "C",
    "Manufacture of textiles": "C",
    "Manufacture of wearing apparel": "C",
    "Manufacture of leather and related products": "C",
    "Manufacture of woods, wood products and cork, except furniture": "C",
    "Manufacture of paper and paper products": "C",
    "Printing and reproduction of recorded media": "C",
    "Manufacture of coke and refined petroleum products": "C",
    "Manufacture of chemicals and chemical products": "C",
    "Manufacture of basic pharmaceutical products and pharmaceutical preparations": "C",
    "Manufacture of rubber and plastics products": "C",
    "Manufacture of other non-metallic mineral products": "C",
    "Manufacture of basic metals": "C",
    "Manufacture of fabricated metal products, except machinery and equipment": "C",
    "Manufacture of computer, electronic and optical products": "C",
    "Manufacture of electrical equipment": "C",
    "Manufacture of machinery and equipment n.e.c.": "C",
    "Manufacture of motor vehicles, trailers and semi-trailers": "C",
    "Manufacture of other transport equipment": "C",
    "Manufacture of furniture": "C",
    "Other manufacturing": "C",
    "Repair and installation of machinery and equipment": "C",
    # D: Electricity, gas, steam and air conditioning supply
    "Electricity, gas, steam and air conditioning supply": "D",
    # E: Water supply; sewerage, waste management
    "Water collection, treatment and supply": "E",
    "Sewerage": "E",
    "Waste collection, treatment and disposal activities; materials recovery": "E",
    "Remediation activities and other waste management services": "E",
    # F: Construction
    "Construction of buildings": "F",
    "Civil engineering": "F",
    "Specialized construction activities": "F",
    # G: Wholesale and retail trade
    "Wholesale and retail trade and repair of motor vehicles and motorcycles": "G",
    "Wholesale trade, except of motor vehicles and motorcycles": "G",
    "Retail trade, except of motor vehicles and motorcycles": "G",
    # H: Transportation and storage
    "Land transport and transport via pipelines": "H",
    "Water transport": "H",
    "Air transport": "H",
    "Warehousing and support activities for transportation": "H",
    "Postal and courier activities": "H",
    # I: Accommodation and food service activities
    "Accommodation": "I",
    "Food and beverage service activities": "I",
    # J: Information and communication
    "Publishing activities": "J",
    "Motion picture, video and television programme production, sound recording and music publishing activities": "J",
    "Programming and broadcasting activities": "J",
    "Telecommunications": "J",
    "Computer programming, consultancy and related activities": "J",
    "Information service activities": "J",
    # K: Financial and insurance activities
    "Financial service activities, except insurance and pension funding": "K",
    "Insurance, reinsurance and pension funding, except compulsory social security": "K",
    "Activities auxiliary to financial service and insurance activities": "K",
    # L: Real estate activities
    "Real estate activities": "L",
    # M: Professional, scientific and technical activities
    "Legal and accounting activities": "M",
    "Activities of head offices; management consultancy activities": "M",
    "Architectural and engineering activities; technical testing and analysis": "M",
    "Scientific research and development": "M",
    "Advertising and market research": "M",
    "Other professional, scientific and technical activities": "M",
    "Veterinary activities": "M",
    # N: Administrative and support service activities
    "Rental and leasing activities": "N",
    "Employment activities": "N",
    "Travel agency, tour operator, reservation service and related activities": "N",
    "Security and investigation activities": "N",
    "Services to buildings and landscape activities": "N",
    "Office administrative, office support and other business support activities": "N",
    # O: Public administration and defence
    "Public administration and defence; compulsory social security": "O",
    # P: Education
    "Education": "P",
    # Q: Human health and social work activities
    "Human health activities": "Q",
    "Residential care activities": "Q",
    "Social work activities without accommodation": "Q",
    # R: Arts, entertainment and recreation
    "Creative, arts and entertainment activities": "R",
    "Libraries, archives, museums and other cultural activities": "R",
    "Sports activities and amusement and recreation activities": "R",
    # S: Other service activities
    "Activities of membership organizations": "S",
    "Repair of computers and personal and household goods": "S",
    "Other personal service activities": "S",
    # T: Activities of households as employers
    "Activities of households as employers of domestic personnel": "T",
}

ISIC_SECTIONS = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
]

ISIC_SECTION_NAMES = {
    "A": "Agriculture, forestry and fishing",
    "B": "Mining and quarrying",
    "C": "Manufacturing",
    "D": "Electricity, gas, steam and air conditioning supply",
    "E": "Water supply; sewerage, waste management",
    "F": "Construction",
    "G": "Wholesale and retail trade",
    "H": "Transportation and storage",
    "I": "Accommodation and food service activities",
    "J": "Information and communication",
    "K": "Financial and insurance activities",
    "L": "Real estate activities",
    "M": "Professional, scientific and technical activities",
    "N": "Administrative and support service activities",
    "O": "Public administration and defence",
    "P": "Education",
    "Q": "Human health and social work activities",
    "R": "Arts, entertainment and recreation",
    "S": "Other service activities",
    "T": "Activities of households as employers",
}


def aggregate_to_sections(
    result: KapsarcIOParseResult,
) -> KapsarcIOParseResult:
    """Aggregate an 84-division IO table to 20 ISIC sections.

    Maps each KAPSARC division name to its ISIC Rev.4 section letter,
    then sums Z and x by section.

    Unmapped divisions are dropped with a warning.
    """
    n_orig = len(result.sector_codes)
    n_sec = len(ISIC_SECTIONS)
    sec_idx = {s: i for i, s in enumerate(ISIC_SECTIONS)}

    # Build mapping: original index -> section index
    orig_to_sec = np.full(n_orig, -1, dtype=int)
    unmapped = []
    for i, code in enumerate(result.sector_codes):
        section = _KAPSARC_TO_ISIC_SECTION.get(code)
        if section is not None and section in sec_idx:
            orig_to_sec[i] = sec_idx[section]
        else:
            unmapped.append(code)

    warnings = list(result.warnings)
    if unmapped:
        warnings.append(f"Unmapped divisions dropped: {unmapped}")

    # Build aggregation matrix M (n_sec x n_orig): M[s, d] = 1 if div d -> section s
    M = np.zeros((n_sec, n_orig), dtype=np.float64)  # noqa: N806
    for i in range(n_orig):
        if orig_to_sec[i] >= 0:
            M[orig_to_sec[i], i] = 1.0

    # Aggregate: Z_sec = M @ Z_orig @ M.T, x_sec = M @ x_orig
    Z_sec = M @ result.Z @ M.T
    x_sec = M @ result.x

    return KapsarcIOParseResult(
        year=result.year,
        sector_codes=ISIC_SECTIONS,
        sector_names=ISIC_SECTION_NAMES,
        Z=Z_sec,
        x=x_sec,
        total_output=float(np.sum(x_sec)),
        record_count=result.record_count,
        warnings=warnings,
    )
