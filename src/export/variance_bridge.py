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

from dataclasses import asdict, dataclass
from enum import StrEnum


class DriverType(StrEnum):
    """Variance driver categories per Section 12.4."""

    PHASING = "PHASING"
    IMPORT_SHARE = "IMPORT_SHARE"
    MAPPING = "MAPPING"
    CONSTRAINT = "CONSTRAINT"
    MODEL_VERSION = "MODEL_VERSION"
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
