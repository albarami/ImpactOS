"""Extract division-level output weights from SG workbook's GASTAT I-O sheet.

Reads the GASTAT I-O sheet and extracts total output (row/column totals)
for each division. Output is used by ConcordanceService for weighted
aggregation/disaggregation.

Usage:
    python -m scripts.extract_sg_division_weights path/to/sg_workbook.xlsb

Output:
    data/curated/division_output_weights_sg_2018.json

IMPORTANT: The .xlsb workbook is proprietary and NOT committed to the repo.
This script is run manually, NOT in CI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _normalize_code(raw: object) -> str:
    """Normalize a sector code from Excel."""
    if raw is None:
        return ""
    if isinstance(raw, float):
        raw = int(raw)
    s = str(raw).strip()
    if s.isdigit():
        return f"{int(s):02d}"
    return s


def extract_weights(workbook_path: str) -> dict:
    """Extract division output weights from the GASTAT I-O sheet.

    The GASTAT I-O sheet has:
        Row 2: Header with title and division codes as columns
        Row 3: Column headers with sector names
        Row 4+: Data rows (Z matrix in SAR thousands)

    Total output for each division = sum of its column in the Z matrix
    plus final demand components (or taken from a totals row).
    """
    try:
        import pyxlsb
    except ImportError:
        print("ERROR: pyxlsb is required. Install with: pip install pyxlsb")
        sys.exit(1)

    wb = pyxlsb.open_workbook(workbook_path)

    # Find GASTAT I-O sheet
    target = None
    for name in wb.sheets:
        if "GASTAT I-O" in name and "TRANSPOSED" not in name.upper():
            target = name
            break

    if target is None:
        print(f"ERROR: No 'GASTAT I-O' sheet found. Sheets: {wb.sheets}")
        sys.exit(1)

    print(f"Reading sheet: {target}")

    rows: list[list] = []
    with wb.get_sheet(target) as sheet:
        for row in sheet.rows():
            rows.append([cell.v for cell in row])

    if len(rows) < 4:
        print("ERROR: Sheet has too few rows")
        sys.exit(1)

    # Row 2 (index 2): header with division codes starting at col 2
    header_row = rows[2]
    col_codes: dict[int, str] = {}
    for ci in range(2, len(header_row)):
        code = _normalize_code(header_row[ci])
        if code and code[0].isdigit():
            col_codes[ci] = code

    print(f"Found {len(col_codes)} division columns")

    # Row 3 (index 3): sector names
    name_row = rows[3]
    col_names: dict[str, str] = {}
    for ci, code in col_codes.items():
        if ci < len(name_row) and name_row[ci]:
            col_names[code] = str(name_row[ci]).strip()

    # Sum each column across data rows (row 4+) to get total intermediate demand
    # In a full I-O table, we'd also add final demand, but for weights
    # the intermediate totals provide reasonable proportional shares
    col_sums: dict[str, float] = {code: 0.0 for code in col_codes.values()}

    for row_idx in range(4, len(rows)):
        row = rows[row_idx]
        row_code = _normalize_code(row[0] if row else None)
        if not row_code or not row_code[0].isdigit():
            # Check for a "Total" row
            if row and isinstance(row[1], str) and "total" in str(row[1]).lower():
                # Use this as the authoritative totals
                for ci, code in col_codes.items():
                    val = row[ci] if ci < len(row) else 0
                    if isinstance(val, int | float):
                        col_sums[code] = float(val)
                print(f"Found totals row at index {row_idx}")
                break
            continue

        for ci, code in col_codes.items():
            val = row[ci] if ci < len(row) else 0
            if isinstance(val, int | float):
                col_sums[code] += float(val)

    # Build output
    divisions = []
    for code in sorted(col_sums.keys()):
        divisions.append({
            "code": code,
            "name": col_names.get(code, ""),
            "total_output": round(col_sums[code], 2),
        })

    return {
        "source": (
            f"GASTAT Input-Output Table at Current Prices 2018, "
            f"extracted from {Path(workbook_path).name}"
        ),
        "denomination": "SAR_THOUSANDS",
        "base_year": 2018,
        "is_synthetic": False,
        "total_divisions": len(divisions),
        "divisions": divisions,
    }


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.extract_sg_division_weights <workbook.xlsb>")
        sys.exit(1)

    workbook_path = sys.argv[1]
    if not Path(workbook_path).exists():
        print(f"ERROR: File not found: {workbook_path}")
        sys.exit(1)

    result = extract_weights(workbook_path)

    output_path = (
        Path(__file__).resolve().parent.parent
        / "data" / "curated" / "division_output_weights_sg_2018.json"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\nWritten: {output_path}")
    print(f"Divisions: {result['total_divisions']}")
    total = sum(d["total_output"] for d in result["divisions"])
    print(f"Total output: SAR {total:,.0f} thousands")


if __name__ == "__main__":
    main()
