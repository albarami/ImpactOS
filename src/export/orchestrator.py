"""Export orchestrator — MVP-6 Section 12.2.

Coordinate the full export pipeline:
1. Check NFF gate first (governed mode only)
2. Check synthetic-fallback provenance (governed mode only)
3. Generate requested formats (Excel/PPTX)
4. Apply watermarks (sandbox or governed)
5. Compute checksums (SHA-256)
6. Create Export record

Block governed exports that fail NFF or use synthetic fallback data.
Deterministic — no LLM calls.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from src.export.excel_export import ExcelExporter
from src.export.pptx_export import PptxExporter
from src.export.watermark import WatermarkService
from src.governance.publication_gate import PublicationGate
from src.models.common import ExportMode, new_uuid7, utc_now
from src.models.governance import Claim
from src.quality.models import RunQualityAssessment


class ExportStatus(StrEnum):
    """Export lifecycle status."""

    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass
class ExportRequest:
    """Request to generate export artifacts."""

    run_id: UUID
    workspace_id: UUID
    mode: ExportMode
    export_formats: list[str]
    pack_data: dict


@dataclass
class ExportRecord:
    """Record of a completed or blocked export."""

    export_id: UUID
    run_id: UUID
    mode: ExportMode
    status: ExportStatus
    artifacts: dict[str, bytes] = field(default_factory=dict)
    checksums: dict[str, str] = field(default_factory=dict)
    blocking_reasons: list[str] = field(default_factory=list)


class ExportOrchestrator:
    """Coordinate the full export pipeline."""

    def __init__(self) -> None:
        self._gate = PublicationGate()
        self._excel = ExcelExporter()
        self._pptx = PptxExporter()
        self._watermark = WatermarkService()

    def execute(
        self,
        *,
        request: ExportRequest,
        claims: list[Claim],
        quality_assessment: RunQualityAssessment | None = None,
    ) -> ExportRecord:
        """Execute the export pipeline.

        For governed mode: check NFF gate first, block if any claim is unresolved.
        Then check synthetic-fallback provenance, block if run used synthetic data.
        For sandbox mode: always proceed with watermarks.
        """
        export_id = new_uuid7()

        # 1. NFF gate check (governed only)
        if request.mode == ExportMode.GOVERNED:
            gate_result = self._gate.check(claims)
            if not gate_result.passed:
                return ExportRecord(
                    export_id=export_id,
                    run_id=request.run_id,
                    mode=request.mode,
                    status=ExportStatus.BLOCKED,
                    blocking_reasons=[br.reason for br in gate_result.blocking_reasons],
                )

        # 2. Synthetic-fallback check (governed only)
        if (
            request.mode == ExportMode.GOVERNED
            and quality_assessment is not None
            and quality_assessment.used_synthetic_fallback
        ):
            return ExportRecord(
                export_id=export_id,
                run_id=request.run_id,
                mode=request.mode,
                status=ExportStatus.BLOCKED,
                blocking_reasons=[
                    "Governed export blocked: run used synthetic fallback data. "
                    "Re-run with curated real data or obtain explicit waiver."
                ],
            )

        # 3. Generate formats
        artifacts: dict[str, bytes] = {}
        now = utc_now()

        for fmt in request.export_formats:
            if fmt == "excel":
                raw = self._excel.export(request.pack_data)
                if request.mode == ExportMode.SANDBOX:
                    raw = self._watermark.apply_sandbox_excel(raw)
                else:
                    raw = self._watermark.apply_governed_excel(
                        raw, run_id=request.run_id, timestamp=now,
                    )
                artifacts["excel"] = raw

            elif fmt == "pptx":
                raw = self._pptx.export(request.pack_data)
                if request.mode == ExportMode.SANDBOX:
                    raw = self._watermark.apply_sandbox_pptx(raw)
                else:
                    raw = self._watermark.apply_governed_pptx(
                        raw, run_id=request.run_id, timestamp=now,
                    )
                artifacts["pptx"] = raw

        # 4. Compute checksums
        checksums: dict[str, str] = {}
        for fmt_name, data in artifacts.items():
            h = hashlib.sha256(data).hexdigest()
            checksums[fmt_name] = f"sha256:{h}"

        return ExportRecord(
            export_id=export_id,
            run_id=request.run_id,
            mode=request.mode,
            status=ExportStatus.COMPLETED,
            artifacts=artifacts,
            checksums=checksums,
        )
