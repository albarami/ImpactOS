"""Tests for export orchestrator (MVP-6).

Covers: NFF gate check first, generate formats, apply watermarks,
compute checksums, create Export record. Block governed exports failing NFF.
"""

import pytest
from uuid_extensions import uuid7

from src.export.orchestrator import (
    ExportOrchestrator,
    ExportRecord,
    ExportRequest,
    ExportStatus,
)
from src.models.common import ClaimStatus, ClaimType, ExportMode
from src.models.governance import Claim


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_ID = uuid7()
WORKSPACE_ID = uuid7()


def _make_supported_claims() -> list[Claim]:
    return [
        Claim(text="GDP impact is SAR 4.2B.", claim_type=ClaimType.MODEL, status=ClaimStatus.SUPPORTED),
        Claim(text="We assume 65%.", claim_type=ClaimType.ASSUMPTION, status=ClaimStatus.REWRITTEN_AS_ASSUMPTION),
    ]


def _make_unresolved_claims() -> list[Claim]:
    return [
        Claim(text="Needs evidence.", claim_type=ClaimType.MODEL, status=ClaimStatus.NEEDS_EVIDENCE),
    ]


def _make_pack_data() -> dict:
    return {
        "run_id": str(RUN_ID),
        "scenario_name": "Test",
        "base_year": 2023,
        "currency": "SAR",
        "model_version_id": str(uuid7()),
        "scenario_version": 1,
        "executive_summary": {"headline_gdp": 4.2e9, "headline_jobs": 21200},
        "sector_impacts": [
            {"sector_code": "C41", "sector_name": "Steel", "direct_impact": 500.0,
             "indirect_impact": 250.0, "total_impact": 750.0, "multiplier": 1.5,
             "domestic_share": 0.65, "import_leakage": 0.35},
        ],
        "input_vectors": {"C41": 1000.0},
        "sensitivity": [],
        "assumptions": [],
        "evidence_ledger": [],
    }


def _make_request(
    mode: ExportMode = ExportMode.SANDBOX,
    formats: list[str] | None = None,
) -> ExportRequest:
    return ExportRequest(
        run_id=RUN_ID,
        workspace_id=WORKSPACE_ID,
        mode=mode,
        export_formats=formats or ["excel"],
        pack_data=_make_pack_data(),
    )


# ===================================================================
# Sandbox exports
# ===================================================================


class TestSandboxExport:
    """Sandbox exports always succeed with watermarks."""

    def test_sandbox_succeeds(self) -> None:
        orch = ExportOrchestrator()
        req = _make_request(mode=ExportMode.SANDBOX)
        record = orch.execute(request=req, claims=[])
        assert record.status == ExportStatus.COMPLETED

    def test_sandbox_has_checksum(self) -> None:
        orch = ExportOrchestrator()
        req = _make_request(mode=ExportMode.SANDBOX)
        record = orch.execute(request=req, claims=[])
        assert record.checksums is not None
        assert len(record.checksums) >= 1
        assert all(c.startswith("sha256:") for c in record.checksums.values())

    def test_sandbox_has_export_id(self) -> None:
        orch = ExportOrchestrator()
        req = _make_request(mode=ExportMode.SANDBOX)
        record = orch.execute(request=req, claims=[])
        assert record.export_id is not None

    def test_sandbox_even_with_unresolved_claims(self) -> None:
        """Sandbox doesn't block on unresolved claims."""
        orch = ExportOrchestrator()
        req = _make_request(mode=ExportMode.SANDBOX)
        record = orch.execute(request=req, claims=_make_unresolved_claims())
        assert record.status == ExportStatus.COMPLETED


# ===================================================================
# Governed exports
# ===================================================================


class TestGovernedExport:
    """Governed exports require NFF pass."""

    def test_governed_passes_with_resolved_claims(self) -> None:
        orch = ExportOrchestrator()
        req = _make_request(mode=ExportMode.GOVERNED)
        record = orch.execute(request=req, claims=_make_supported_claims())
        assert record.status == ExportStatus.COMPLETED

    def test_governed_blocked_with_unresolved(self) -> None:
        orch = ExportOrchestrator()
        req = _make_request(mode=ExportMode.GOVERNED)
        record = orch.execute(request=req, claims=_make_unresolved_claims())
        assert record.status == ExportStatus.BLOCKED

    def test_governed_blocked_has_reasons(self) -> None:
        orch = ExportOrchestrator()
        req = _make_request(mode=ExportMode.GOVERNED)
        record = orch.execute(request=req, claims=_make_unresolved_claims())
        assert len(record.blocking_reasons) >= 1

    def test_governed_empty_claims_passes(self) -> None:
        orch = ExportOrchestrator()
        req = _make_request(mode=ExportMode.GOVERNED)
        record = orch.execute(request=req, claims=[])
        assert record.status == ExportStatus.COMPLETED


# ===================================================================
# Multiple formats
# ===================================================================


class TestMultipleFormats:
    """Generate multiple export formats."""

    def test_excel_format(self) -> None:
        orch = ExportOrchestrator()
        req = _make_request(formats=["excel"])
        record = orch.execute(request=req, claims=[])
        assert "excel" in record.artifacts

    def test_pptx_format(self) -> None:
        orch = ExportOrchestrator()
        req = _make_request(formats=["pptx"])
        record = orch.execute(request=req, claims=[])
        assert "pptx" in record.artifacts

    def test_multiple_formats(self) -> None:
        orch = ExportOrchestrator()
        req = _make_request(formats=["excel", "pptx"])
        record = orch.execute(request=req, claims=[])
        assert "excel" in record.artifacts
        assert "pptx" in record.artifacts

    def test_each_format_has_checksum(self) -> None:
        orch = ExportOrchestrator()
        req = _make_request(formats=["excel", "pptx"])
        record = orch.execute(request=req, claims=[])
        assert "excel" in record.checksums
        assert "pptx" in record.checksums
