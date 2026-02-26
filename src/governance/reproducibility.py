"""Run reproducibility checker — MVP-5 Section 12.1.

Verify a RunSnapshot can reproduce identical results (hash comparison
within tolerance). Detect if any referenced version has changed since
the run.

Deterministic — no LLM calls.
"""

from dataclasses import dataclass, field
from uuid import UUID

from src.models.run import ResultSet, RunSnapshot


# ---------------------------------------------------------------------------
# Version drift
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VersionDrift:
    """A single version field that has drifted since the run."""

    field_name: str
    snapshot_value: UUID
    current_value: UUID


# ---------------------------------------------------------------------------
# Reproducibility result
# ---------------------------------------------------------------------------


@dataclass
class ReproducibilityResult:
    """Result of verifying reproducibility."""

    reproducible: bool
    mismatches: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Version fields to compare
# ---------------------------------------------------------------------------

_VERSION_FIELDS = (
    "model_version_id",
    "taxonomy_version_id",
    "concordance_version_id",
    "mapping_library_version_id",
    "assumption_library_version_id",
    "prompt_pack_version_id",
)


# ---------------------------------------------------------------------------
# Reproducibility checker
# ---------------------------------------------------------------------------


class ReproducibilityChecker:
    """Verify that a run can be reproduced identically.

    Compares result sets value-by-value within tolerance, and detects
    if any version references have drifted since the snapshot.
    """

    def __init__(self, tolerance: float = 0.0) -> None:
        self._tolerance = tolerance

    def verify_results(
        self,
        *,
        original_results: list[ResultSet],
        reproduced_results: list[ResultSet],
    ) -> ReproducibilityResult:
        """Compare original and reproduced result sets.

        Each ResultSet is matched by metric_type. Values are compared
        within the configured tolerance.
        """
        mismatches: list[str] = []

        # Check count match
        if len(original_results) != len(reproduced_results):
            mismatches.append(
                f"Result count mismatch: original={len(original_results)}, "
                f"reproduced={len(reproduced_results)}"
            )
            return ReproducibilityResult(reproducible=False, mismatches=mismatches)

        # Index by metric_type
        orig_by_metric = {rs.metric_type: rs for rs in original_results}
        repro_by_metric = {rs.metric_type: rs for rs in reproduced_results}

        # Check metric types match
        if set(orig_by_metric.keys()) != set(repro_by_metric.keys()):
            missing = set(orig_by_metric.keys()) - set(repro_by_metric.keys())
            extra = set(repro_by_metric.keys()) - set(orig_by_metric.keys())
            if missing:
                mismatches.append(f"Missing metrics in reproduced: {missing}")
            if extra:
                mismatches.append(f"Extra metrics in reproduced: {extra}")
            return ReproducibilityResult(reproducible=False, mismatches=mismatches)

        # Compare values within tolerance
        for metric_type, orig_rs in orig_by_metric.items():
            repro_rs = repro_by_metric[metric_type]
            self._compare_values(metric_type, orig_rs.values, repro_rs.values, mismatches)

        return ReproducibilityResult(
            reproducible=len(mismatches) == 0,
            mismatches=mismatches,
        )

    def _compare_values(
        self,
        metric_type: str,
        original: dict[str, float],
        reproduced: dict[str, float],
        mismatches: list[str],
    ) -> None:
        """Compare value dicts within tolerance."""
        all_keys = set(original.keys()) | set(reproduced.keys())
        for key in sorted(all_keys):
            orig_val = original.get(key)
            repro_val = reproduced.get(key)
            if orig_val is None or repro_val is None:
                mismatches.append(
                    f"{metric_type}.{key}: missing in {'original' if orig_val is None else 'reproduced'}"
                )
                continue
            if abs(orig_val - repro_val) > self._tolerance:
                mismatches.append(
                    f"{metric_type}.{key}: original={orig_val}, reproduced={repro_val}, "
                    f"diff={abs(orig_val - repro_val)}"
                )

    def detect_version_drift(
        self,
        snapshot: RunSnapshot,
        current_versions: dict[str, UUID],
    ) -> list[VersionDrift]:
        """Detect if any referenced versions have changed since the run.

        Compares snapshot fields against current version IDs.
        """
        drifts: list[VersionDrift] = []
        for field_name in _VERSION_FIELDS:
            snapshot_val = getattr(snapshot, field_name)
            current_val = current_versions.get(field_name)
            if current_val is not None and snapshot_val != current_val:
                drifts.append(
                    VersionDrift(
                        field_name=field_name,
                        snapshot_value=snapshot_val,
                        current_value=current_val,
                    )
                )
        return drifts

    @staticmethod
    def detect_checksum_drift(
        snapshot: RunSnapshot,
        current_checksums: list[str],
    ) -> bool:
        """Detect if source document checksums have changed."""
        return set(snapshot.source_checksums) != set(current_checksums)
