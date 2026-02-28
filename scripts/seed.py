"""Seed script — load sample data into the ImpactOS database.

Creates:
1. A sample workspace (Strategic Gears Demo)
2. A 5x5 Saudi IO model (AGRI, MINING, MANUF, CONSTR, SERVICES)
3. Satellite coefficients (jobs, imports, value-added)
4. Employment coefficients (direct jobs, indirect multiplier)
5. A sample BoQ document with 12 realistic line items

Idempotent: safe to run multiple times — skips if demo workspace already exists.

Usage:
    python -m scripts.seed          # against DATABASE_URL from .env
    pytest tests/scripts/test_seed.py  # against aiosqlite in-memory
"""

import asyncio
import hashlib
import sys
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from src.db.tables import DocumentRow, LineItemRow, ModelDataRow, ModelVersionRow, WorkspaceRow
from src.models.common import utc_now
from src.repositories.documents import DocumentRepository, LineItemRepository
from src.repositories.engine import ModelDataRepository, ModelVersionRepository
from src.repositories.workspace import WorkspaceRepository

# ---------------------------------------------------------------------------
# Original 3x3 IO Model — kept for backward compatibility (Amendment 5)
# Tests depend on these constants and functions.
# Sectors: Agriculture (A), Industry (C+F), Services (G-N)
# Base year 2019 (pre-pandemic baseline)
# Values in SAR billions (intermediate flows)
# ---------------------------------------------------------------------------

SAMPLE_SECTOR_CODES = ["Agriculture", "Industry", "Services"]

# Z matrix (intermediate flows, SAR billions)
# Rows = purchases from sector i; Columns = sales to sector j
SAMPLE_Z_MATRIX = [
    [5.0, 20.0, 10.0],   # Agriculture buys from itself + sells to Industry/Services
    [15.0, 150.0, 80.0],  # Industry is the largest intermediate consumer
    [8.0, 60.0, 120.0],   # Services
]

# x vector (total output per sector, SAR billions)
SAMPLE_X_VECTOR = [100.0, 500.0, 400.0]

# ---------------------------------------------------------------------------
# NEW: 5-sector Saudi IO model — used by _run_seed() for demos
# Sectors: Agriculture, Mining (Oil & Gas), Manufacturing, Construction, Services
# Base year 2022 — values in SAR billions (intermediate flows)
# Spectral radius = 0.2575 (validated < 1.0)
# ---------------------------------------------------------------------------

DEMO_SECTOR_CODES = ["AGRI", "MINING", "MANUF", "CONSTR", "SERVICES"]

# Z matrix (intermediate flows, SAR billions)
# Rows = purchases from sector i; Columns = sales to sector j
DEMO_Z_MATRIX = [
    [5.0,   2.0,  15.0,   3.0,   8.0],    # AGRI
    [3.0,  40.0,  80.0,  20.0,  15.0],    # MINING (oil feeds manufacturing)
    [10.0,  30.0,  90.0,  50.0,  40.0],    # MANUF (largest intermediate flows)
    [2.0,   8.0,  20.0,  30.0,  25.0],    # CONSTR
    [12.0,  25.0,  45.0,  35.0, 100.0],    # SERVICES
]

# x vector (total output per sector, SAR billions)
DEMO_X_VECTOR = [120.0, 600.0, 800.0, 350.0, 900.0]

# Satellite coefficients (per-sector ratios)
DEMO_SATELLITE_COEFFICIENTS = {
    "jobs_coeff": [0.025, 0.004, 0.012, 0.018, 0.020],
    "import_ratio": [0.15, 0.08, 0.35, 0.25, 0.12],
    "va_ratio": [0.45, 0.65, 0.30, 0.35, 0.55],
}

# Employment coefficients
DEMO_EMPLOYMENT_COEFFICIENTS = {
    "direct_jobs_per_sar_million": [12.5, 2.0, 6.0, 9.0, 10.0],
    "indirect_multiplier": [1.8, 2.5, 2.2, 1.9, 1.6],
}

# Demo workspace identifier (used for idempotency check)
DEMO_ENGAGEMENT_CODE = "SG-DEMO-2026"

# ---------------------------------------------------------------------------
# Sample BoQ line items — NEOM Logistics Zone (fictional)
# ---------------------------------------------------------------------------

SAMPLE_LINE_ITEMS = [
    {"description": "Structural Steel Supply", "raw_text": "Structural steel supply and delivery — Grade S355", "quantity": 12000.0, "unit": "ton", "unit_price": 3500.0, "total_value": 42_000_000.0, "category_code": "C24"},
    {"description": "Concrete Works (Grade 60)", "raw_text": "Ready-mix concrete grade 60 supply and pour", "quantity": 45000.0, "unit": "m3", "unit_price": 850.0, "total_value": 38_250_000.0, "category_code": "F41"},
    {"description": "MEP — Electrical Systems", "raw_text": "Electrical installation — main distribution and sub-panels", "quantity": 1.0, "unit": "lot", "unit_price": 15_000_000.0, "total_value": 15_000_000.0, "category_code": "F43"},
    {"description": "MEP — HVAC Systems", "raw_text": "HVAC ducting, AHUs, chillers — warehouse zones", "quantity": 1.0, "unit": "lot", "unit_price": 22_000_000.0, "total_value": 22_000_000.0, "category_code": "F43"},
    {"description": "Earthworks and Grading", "raw_text": "Site grading, excavation, fill compaction", "quantity": 250000.0, "unit": "m3", "unit_price": 45.0, "total_value": 11_250_000.0, "category_code": "F42"},
    {"description": "Precast Concrete Panels", "raw_text": "Precast wall panels — insulated sandwich type", "quantity": 8500.0, "unit": "m2", "unit_price": 1200.0, "total_value": 10_200_000.0, "category_code": "C23"},
    {"description": "Road and Pavement Works", "raw_text": "Internal roads — asphalt base + wearing course", "quantity": 35000.0, "unit": "m2", "unit_price": 280.0, "total_value": 9_800_000.0, "category_code": "F42"},
    {"description": "Fire Protection Systems", "raw_text": "Sprinkler system, fire alarm, smoke detection", "quantity": 1.0, "unit": "lot", "unit_price": 8_500_000.0, "total_value": 8_500_000.0, "category_code": "F43"},
    {"description": "Landscape and Irrigation", "raw_text": "External landscaping, drip irrigation, hardscape", "quantity": 12000.0, "unit": "m2", "unit_price": 350.0, "total_value": 4_200_000.0, "category_code": "F43"},
    {"description": "IT and Networking Infrastructure", "raw_text": "Structured cabling, server room, network switches", "quantity": 1.0, "unit": "lot", "unit_price": 6_500_000.0, "total_value": 6_500_000.0, "category_code": "J62"},
    {"description": "Security Systems", "raw_text": "CCTV, access control, perimeter fencing with sensors", "quantity": 1.0, "unit": "lot", "unit_price": 3_800_000.0, "total_value": 3_800_000.0, "category_code": "N80"},
    {"description": "Transport and Logistics Setup", "raw_text": "Material transport, crane rental, logistics coordination", "quantity": 1.0, "unit": "lot", "unit_price": 5_200_000.0, "total_value": 5_200_000.0, "category_code": "H49"},
]


# ---------------------------------------------------------------------------
# Original seed functions — backward compatible (Amendment 5)
# Tests import and call these directly — do NOT modify signatures.
# ---------------------------------------------------------------------------


async def seed_workspace(session: AsyncSession) -> WorkspaceRow:
    """Create a sample workspace."""
    repo = WorkspaceRepository(session)
    return await repo.create(
        workspace_id=uuid7(),
        client_name="Strategic Gears (Demo)",
        engagement_code="SG-DEMO-2026",
        classification="INTERNAL",
        description="Sample workspace for local development and demos.",
        created_by=uuid7(),
    )


async def seed_model(session: AsyncSession) -> tuple[ModelVersionRow, ModelDataRow]:
    """Register a 3x3 simplified Saudi IO model."""
    mv_repo = ModelVersionRepository(session)
    md_repo = ModelDataRepository(session)

    z_arr = np.array(SAMPLE_Z_MATRIX, dtype=np.float64)
    x_arr = np.array(SAMPLE_X_VECTOR, dtype=np.float64)

    # Compute checksum
    hasher = hashlib.sha256()
    hasher.update(z_arr.tobytes())
    hasher.update(x_arr.tobytes())
    checksum = f"sha256:{hasher.hexdigest()}"

    mvid = uuid7()
    mv_row = await mv_repo.create(
        model_version_id=mvid,
        base_year=2019,
        source="GASTAT simplified 3-sector (demo)",
        sector_count=len(SAMPLE_SECTOR_CODES),
        checksum=checksum,
    )
    md_row = await md_repo.create(
        model_version_id=mvid,
        z_matrix_json=SAMPLE_Z_MATRIX,
        x_vector_json=SAMPLE_X_VECTOR,
        sector_codes=SAMPLE_SECTOR_CODES,
    )
    return mv_row, md_row


async def seed_boq_line_items(
    session: AsyncSession, workspace_id: UUID,
) -> tuple[DocumentRow, list[LineItemRow]]:
    """Create a sample BoQ document with 12 line items."""
    doc_repo = DocumentRepository(session)
    li_repo = LineItemRepository(session)

    doc_id = uuid7()
    job_id = uuid7()

    doc_row = await doc_repo.create(
        doc_id=doc_id,
        workspace_id=workspace_id,
        filename="sample_boq_neom_logistics.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=48_000,
        hash_sha256=f"sha256:{'a1b2c3d4' * 8}",
        storage_key=f"workspaces/{workspace_id}/documents/{doc_id}/sample_boq_neom_logistics.xlsx",
        uploaded_by=uuid7(),
        doc_type="BOQ",
        source_type="UPLOAD",
        classification="INTERNAL",
    )

    now = utc_now()
    items_dicts = []
    for li in SAMPLE_LINE_ITEMS:
        items_dicts.append({
            "line_item_id": uuid7(),
            "doc_id": doc_id,
            "extraction_job_id": job_id,
            "raw_text": li["raw_text"],
            "description": li["description"],
            "quantity": li.get("quantity"),
            "unit": li.get("unit"),
            "unit_price": li.get("unit_price"),
            "total_value": li["total_value"],
            "currency_code": "SAR",
            "category_code": li.get("category_code"),
            "page_ref": 1,
            "evidence_snippet_ids": [],
            "created_at": now,
        })

    item_rows = await li_repo.create_many(items_dicts)
    return doc_row, item_rows


# ---------------------------------------------------------------------------
# NEW: 5-sector seed functions
# ---------------------------------------------------------------------------


async def seed_5sector_model(
    session: AsyncSession,
) -> tuple[ModelVersionRow, ModelDataRow]:
    """Register the 5-sector Saudi IO model."""
    mv_repo = ModelVersionRepository(session)
    md_repo = ModelDataRepository(session)

    z_arr = np.array(DEMO_Z_MATRIX, dtype=np.float64)
    x_arr = np.array(DEMO_X_VECTOR, dtype=np.float64)

    hasher = hashlib.sha256()
    hasher.update(z_arr.tobytes())
    hasher.update(x_arr.tobytes())
    checksum = f"sha256:{hasher.hexdigest()}"

    mvid = uuid7()
    mv_row = await mv_repo.create(
        model_version_id=mvid,
        base_year=2022,
        source="GASTAT simplified 5-sector Saudi IO (demo)",
        sector_count=len(DEMO_SECTOR_CODES),
        checksum=checksum,
    )
    md_row = await md_repo.create(
        model_version_id=mvid,
        z_matrix_json=DEMO_Z_MATRIX,
        x_vector_json=DEMO_X_VECTOR,
        sector_codes=DEMO_SECTOR_CODES,
    )
    return mv_row, md_row


async def seed_demo(session: AsyncSession) -> dict:
    """Idempotent demo seed: workspace + 5-sector model + BoQ.

    Returns dict with keys: created (bool), workspace_id, model_version_id.
    If workspace already exists, returns created=False and skips.
    """
    # Idempotency check: look for existing demo workspace
    result = await session.execute(
        select(WorkspaceRow).where(WorkspaceRow.engagement_code == DEMO_ENGAGEMENT_CODE),
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return {
            "created": False,
            "workspace_id": existing.workspace_id,
            "model_version_id": None,
        }

    # Create workspace
    ws = await seed_workspace(session)

    # Create 5-sector model
    mv, _md = await seed_5sector_model(session)

    # Create BoQ line items
    _doc, items = await seed_boq_line_items(session, ws.workspace_id)

    return {
        "created": True,
        "workspace_id": ws.workspace_id,
        "model_version_id": mv.model_version_id,
        "model_sector_count": mv.sector_count,
        "boq_item_count": len(items),
    }


# ---------------------------------------------------------------------------
# CLI entry point: python -m scripts.seed
# ---------------------------------------------------------------------------


async def _run_seed() -> None:
    """Run the full seed against the real database (5-sector, idempotent)."""
    from src.db.session import async_session_factory

    async with async_session_factory() as session:
        result = await seed_demo(session)

        if not result["created"]:
            print("Demo data already seeded (workspace SG-DEMO-2026 exists). Skipping.")
            print(f"  Workspace: {result['workspace_id']}")
            return

        await session.commit()

        print("Seed complete.")
        print(f"  Workspace:    {result['workspace_id']}")
        print(f"  Model:        {result['model_version_id']}"
              f" ({result['model_sector_count']} sectors)")
        print(f"  BoQ items:    {result['boq_item_count']}")
        print()
        _print_summary()


def _print_summary() -> None:
    """Print a table of the 5-sector model data."""
    print("5-sector Saudi IO model:")
    print(f"  {'Sector':<12} {'Output (SAR B)':>15} {'Jobs coeff':>12}"
          f" {'Import %':>10} {'VA %':>8}")
    print(f"  {'─' * 12} {'─' * 15} {'─' * 12} {'─' * 10} {'─' * 8}")
    for i, code in enumerate(DEMO_SECTOR_CODES):
        jobs = DEMO_SATELLITE_COEFFICIENTS["jobs_coeff"][i]
        imp = DEMO_SATELLITE_COEFFICIENTS["import_ratio"][i]
        va = DEMO_SATELLITE_COEFFICIENTS["va_ratio"][i]
        print(f"  {code:<12} {DEMO_X_VECTOR[i]:>15,.1f} {jobs:>12.3f}"
              f" {imp:>9.0%} {va:>7.0%}")
    total_output = sum(DEMO_X_VECTOR)
    print(f"  {'TOTAL':<12} {total_output:>15,.1f}")


if __name__ == "__main__":
    asyncio.run(_run_seed())


def __getattr__(name: str):  # type: ignore[misc]
    """Allow `python -m scripts.seed` to work."""
    if name == "__main__":
        asyncio.run(_run_seed())
        sys.exit(0)
    raise AttributeError(name)
