"""SAMA (Saudi Central Bank) data — document manual process.

SAMA does not have a confirmed public REST API.
This script documents available access methods and creates metadata.

Usage:
    python -m scripts.fetch_sama
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

OUT_DIR = Path("data/raw/sama")


def main() -> int:
    """Document SAMA data access (manual process)."""
    print("=== SAMA Data — Manual Process Documentation ===\n")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("  SAMA does not have a confirmed public REST API.")
    print("  Data must be downloaded manually from:")
    print("    https://www.sama.gov.sa/en-US/EconomicReports/"
          "pages/database.aspx")
    print()
    print("  Relevant datasets:")
    print("    - Monthly Statistical Bulletin (CPI, money supply)")
    print("    - Annual Statistics (bank credit by ISIC sector)")
    print("    - Balance of Payments (BoP components, FDI)")
    print()
    print("  Format: Excel workbooks, PDF reports")
    print()
    print("  To integrate SAMA data:")
    print("    1. Download Excel files from portal manually")
    print("    2. Place in data/raw/sama/")
    print("    3. Run parser (to be built when data is available)")

    metadata = {
        "source": "SAMA (Saudi Central Bank)",
        "base_url": (
            "https://www.sama.gov.sa/en-US/EconomicReports/"
            "pages/database.aspx"
        ),
        "api_status": "no_rest_api",
        "access_method": "manual_download",
        "fetch_timestamp": datetime.now(datetime.UTC).isoformat(),
        "available_datasets": {
            "monthly_bulletin": {
                "description": "Monthly Statistical Bulletin",
                "contains": "CPI, money supply, interest rates",
                "format": "Excel",
                "status": "manual_download_required",
            },
            "annual_statistics": {
                "description": "Annual Statistics",
                "contains": "Bank credit by ISIC sector",
                "format": "Excel",
                "status": "manual_download_required",
            },
            "balance_of_payments": {
                "description": "Balance of Payments",
                "contains": "BoP components, FDI by sector",
                "format": "Excel",
                "status": "manual_download_required",
            },
        },
        "notes": (
            "SAMA announced API connectivity via open.data.gov.sa "
            "real-time APIs page. No public REST endpoint confirmed. "
            "Monitor for API availability."
        ),
    }

    meta_path = OUT_DIR / "_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, default=str))
    print(f"\nMetadata saved to {meta_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
