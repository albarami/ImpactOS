"""Variance bridge — MVP-6 Section 12.4.

Compare two runs and decompose changes into drivers:
- Phasing adjustments
- Import share revisions
- Mapping updates
- Constraint activation
- Model version changes

Output as waterfall dataset for reporting.
Deterministic — no LLM calls.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum


class DriverType(StrEnum):
    """Variance driver categories per Section 12.4."""

    PHASING = "PHASING"
    IMPORT_SHARE = "IMPORT_SHARE"
    MAPPING = "MAPPING"
    CONSTRAINT = "CONSTRAINT"
    MODEL_VERSION = "MODEL_VERSION"
    FEASIBILITY = "FEASIBILITY"
    RESIDUAL = "RESIDUAL"


@dataclass
class VarianceDriver:
    """Single driver contribution to the variance."""

    driver_type: DriverType
    description: str
    impact: float


@dataclass
class WaterfallDataset:
    """Complete waterfall dataset for reporting."""

    start_value: float
    end_value: float
    total_variance: float
    drivers: list[VarianceDriver]

    def to_dict(self) -> dict:
        return {
            "start_value": self.start_value,
            "end_value": self.end_value,
            "total_variance": self.total_variance,
            "drivers": [asdict(d) for d in self.drivers],
        }


class VarianceBridge:
    """Compare two runs and decompose changes into contributing factors."""

    def compare(self, *, run_a: dict, run_b: dict) -> WaterfallDataset:
        """Decompose variance between two runs into drivers.

        The total variance is allocated proportionally to detected changes.
        When no specific driver is detected, variance goes to RESIDUAL.
        """
        start = run_a["total_impact"]
        end = run_b["total_impact"]
        total_variance = end - start

        drivers: list[VarianceDriver] = []
        allocated = 0.0

        # Detect changed dimensions
        changes: list[tuple[DriverType, str, float]] = []

        # 1. Phasing changes
        phasing_a = run_a.get("phasing", {})
        phasing_b = run_b.get("phasing", {})
        if phasing_a != phasing_b:
            changes.append((DriverType.PHASING, "Phasing schedule adjusted", 1.0))

        # 2. Import share changes
        imports_a = run_a.get("import_shares", {})
        imports_b = run_b.get("import_shares", {})
        if imports_a != imports_b:
            changes.append((DriverType.IMPORT_SHARE, "Import share assumptions revised", 1.0))

        # 3. Mapping changes
        map_a = run_a.get("mapping_count", 0)
        map_b = run_b.get("mapping_count", 0)
        if map_a != map_b:
            changes.append((DriverType.MAPPING, f"Mapping updates ({map_a} → {map_b})", 1.0))

        # 4. Constraint changes
        con_a = run_a.get("constraints_active", 0)
        con_b = run_b.get("constraints_active", 0)
        if con_a != con_b:
            changes.append((DriverType.CONSTRAINT, f"Constraint activation ({con_a} → {con_b})", 1.0))

        # 5. Model version changes
        mv_a = run_a.get("model_version", "")
        mv_b = run_b.get("model_version", "")
        if mv_a != mv_b:
            changes.append((DriverType.MODEL_VERSION, f"Model version change ({mv_a} → {mv_b})", 1.0))

        # Allocate variance proportionally across detected changes
        if changes:
            total_weight = sum(c[2] for c in changes)
            for driver_type, description, weight in changes:
                if abs(total_variance) > 1e-12:
                    impact = total_variance * (weight / total_weight)
                else:
                    impact = 0.0
                drivers.append(VarianceDriver(
                    driver_type=driver_type,
                    description=description,
                    impact=impact,
                ))
                allocated += impact

        # Residual (rounding or unattributed)
        residual = total_variance - allocated
        if abs(residual) > 1e-12:
            drivers.append(VarianceDriver(
                driver_type=DriverType.RESIDUAL,
                description="Unattributed variance",
                impact=residual,
            ))

        return WaterfallDataset(
            start_value=start,
            end_value=end,
            total_variance=total_variance,
            drivers=drivers,
        )


# ---------------------------------------------------------------------------
# Sprint 23: Advanced artifact-linked variance bridge
# ---------------------------------------------------------------------------


@dataclass
class AdvancedVarianceDriver:
    """Single driver contribution with metadata."""

    driver_type: DriverType
    description: str
    impact: float
    raw_magnitude: float = 0.0
    weight: float = 0.0
    source_field: str | None = None
    diff_summary: str | None = None


@dataclass
class BridgeDiagnostics:
    """Structured diagnostics for audit trail."""

    checksum: str = ""
    tolerance_used: float = 1e-9
    identity_verified: bool = False
    driver_details: list[dict] = field(default_factory=list)


@dataclass
class BridgeResult:
    """Complete bridge output."""

    start_value: float
    end_value: float
    total_variance: float
    drivers: list[AdvancedVarianceDriver]
    diagnostics: BridgeDiagnostics


class AdvancedVarianceBridge:
    """Compute deterministic variance bridge from artifact diffs.

    Sprint 23: Artifact-linked attribution engine.
    Deterministic — no LLM calls.
    """

    TOLERANCE = 1e-9

    @staticmethod
    def compute_from_artifacts(
        *,
        run_a_snapshot: dict,
        run_b_snapshot: dict,
        result_a: dict,
        result_b: dict,
        spec_a: dict | None = None,
        spec_b: dict | None = None,
        aggregate_key: str = "total",
    ) -> BridgeResult:
        """Decompose variance between two runs using real artifact diffs."""
        tolerance = AdvancedVarianceBridge.TOLERANCE

        # 1. Compute total variance
        start = result_a["values"][aggregate_key]
        end = result_b["values"][aggregate_key]
        total_variance = end - start

        # 2. Extract per-driver raw magnitudes from artifact diffs
        changes: list[tuple[DriverType, str, float, str, str]] = []

        # PHASING: time_horizon diff
        if spec_a and spec_b:
            th_a = spec_a.get("time_horizon", {})
            th_b = spec_b.get("time_horizon", {})
            if th_a != th_b:
                mag = _count_diffs(th_a, th_b)
                changes.append((
                    DriverType.PHASING,
                    "Phasing schedule adjusted",
                    mag,
                    "time_horizon",
                    f"{th_a} -> {th_b}",
                ))

        # IMPORT_SHARE: ImportSubstitution shock diffs
        if spec_a and spec_b:
            imp_a = [s for s in spec_a.get("shock_items", [])
                     if s.get("type") == "ImportSubstitution"]
            imp_b = [s for s in spec_b.get("shock_items", [])
                     if s.get("type") == "ImportSubstitution"]
            if imp_a != imp_b:
                mag = float(max(len(imp_a), len(imp_b), 1))
                changes.append((
                    DriverType.IMPORT_SHARE,
                    "Import share assumptions revised",
                    mag,
                    "shock_items[ImportSubstitution]",
                    f"{len(imp_a)} -> {len(imp_b)} shocks",
                ))

        # MAPPING: mapping_library_version_id diff
        ml_a = run_a_snapshot.get("mapping_library_version_id")
        ml_b = run_b_snapshot.get("mapping_library_version_id")
        if ml_a != ml_b:
            changes.append((
                DriverType.MAPPING,
                f"Mapping library updated ({ml_a} -> {ml_b})",
                1.0,
                "mapping_library_version_id",
                f"{ml_a} -> {ml_b}",
            ))

        # CONSTRAINT: constraint_set_version_id diff
        cs_a = run_a_snapshot.get("constraint_set_version_id")
        cs_b = run_b_snapshot.get("constraint_set_version_id")
        if cs_a != cs_b:
            changes.append((
                DriverType.CONSTRAINT,
                f"Constraint set updated ({cs_a} -> {cs_b})",
                1.0,
                "constraint_set_version_id",
                f"{cs_a} -> {cs_b}",
            ))

        # MODEL_VERSION: model_version_id diff
        mv_a = run_a_snapshot.get("model_version_id")
        mv_b = run_b_snapshot.get("model_version_id")
        if mv_a != mv_b:
            changes.append((
                DriverType.MODEL_VERSION,
                f"Model version changed ({mv_a} -> {mv_b})",
                1.0,
                "model_version_id",
                f"{mv_a} -> {mv_b}",
            ))

        # FEASIBILITY: ConstraintOverride shock diffs
        if spec_a and spec_b:
            co_a = [s for s in spec_a.get("shock_items", [])
                    if s.get("type") == "ConstraintOverride"]
            co_b = [s for s in spec_b.get("shock_items", [])
                    if s.get("type") == "ConstraintOverride"]
            if co_a != co_b:
                mag = float(max(len(co_a), len(co_b), 1))
                changes.append((
                    DriverType.FEASIBILITY,
                    "Feasibility/constraint override effects",
                    mag,
                    "shock_items[ConstraintOverride]",
                    f"{len(co_a)} -> {len(co_b)} overrides",
                ))

        # 3. Compute attribution
        drivers: list[AdvancedVarianceDriver] = []
        total_magnitude = sum(c[2] for c in changes)

        if total_magnitude < tolerance and abs(total_variance) > tolerance:
            # All zero magnitudes + nonzero variance -> 100% RESIDUAL
            drivers.append(AdvancedVarianceDriver(
                driver_type=DriverType.RESIDUAL,
                description="Unattributed variance (no detectable artifact diffs)",
                impact=total_variance,
                raw_magnitude=0.0,
                weight=1.0,
                source_field="residual",
            ))
        elif total_magnitude > 0:
            allocated = 0.0
            for dtype, desc, mag, src, diff in changes:
                w = mag / total_magnitude
                impact = total_variance * w
                drivers.append(AdvancedVarianceDriver(
                    driver_type=dtype,
                    description=desc,
                    impact=impact,
                    raw_magnitude=mag,
                    weight=w,
                    source_field=src,
                    diff_summary=diff,
                ))
                allocated += impact
            # Residual for strict identity
            residual = total_variance - allocated
            if abs(residual) > tolerance:
                drivers.append(AdvancedVarianceDriver(
                    driver_type=DriverType.RESIDUAL,
                    description="Rounding residual",
                    impact=residual,
                    raw_magnitude=0.0,
                    weight=0.0,
                    source_field="residual",
                ))

        # 4. Deterministic sort: enum order, then abs(impact) desc
        enum_order = list(DriverType)
        drivers.sort(key=lambda d: (enum_order.index(d.driver_type), -abs(d.impact)))

        # 5. Diagnostics
        driver_sum = sum(d.impact for d in drivers)
        identity_ok = abs(driver_sum - total_variance) < tolerance

        canonical = json.dumps(
            {
                "start": start,
                "end": end,
                "total_variance": total_variance,
                "drivers": [
                    {"type": d.driver_type.value, "impact": d.impact}
                    for d in drivers
                ],
            },
            sort_keys=True,
        )
        checksum = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()

        diagnostics = BridgeDiagnostics(
            checksum=checksum,
            tolerance_used=tolerance,
            identity_verified=identity_ok,
            driver_details=[
                {
                    "type": d.driver_type.value,
                    "magnitude": d.raw_magnitude,
                    "weight": d.weight,
                    "source": d.source_field,
                }
                for d in drivers
            ],
        )

        return BridgeResult(
            start_value=start,
            end_value=end,
            total_variance=total_variance,
            drivers=drivers,
            diagnostics=diagnostics,
        )


def _count_diffs(a: dict, b: dict) -> float:
    """Count differing keys between two dicts."""
    all_keys = set(a.keys()) | set(b.keys())
    return float(sum(1 for k in all_keys if a.get(k) != b.get(k))) or 1.0
