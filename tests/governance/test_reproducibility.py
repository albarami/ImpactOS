"""Tests for run reproducibility checker (MVP-5).

Covers: verify RunSnapshot can reproduce identical results via hash
comparison within tolerance, detect if referenced versions have changed.
"""

import pytest
from uuid_extensions import uuid7

from src.governance.reproducibility import (
    ReproducibilityChecker,
    ReproducibilityResult,
    VersionDrift,
)
from src.models.run import ResultSet, RunSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_ID = uuid7()
MODEL_V1 = uuid7()
TAX_V1 = uuid7()
CONC_V1 = uuid7()
MAP_V1 = uuid7()
ASSUM_V1 = uuid7()
PROMPT_V1 = uuid7()


def _make_snapshot(**overrides: object) -> RunSnapshot:
    defaults: dict[str, object] = {
        "run_id": RUN_ID,
        "model_version_id": MODEL_V1,
        "taxonomy_version_id": TAX_V1,
        "concordance_version_id": CONC_V1,
        "mapping_library_version_id": MAP_V1,
        "assumption_library_version_id": ASSUM_V1,
        "prompt_pack_version_id": PROMPT_V1,
        "source_checksums": ["sha256:" + "a" * 64],
    }
    defaults.update(overrides)
    return RunSnapshot(**defaults)  # type: ignore[arg-type]


def _make_result_set(
    run_id=RUN_ID,
    metric_type: str = "gdp_impact",
    values: dict[str, float] | None = None,
) -> ResultSet:
    return ResultSet(
        run_id=run_id,
        metric_type=metric_type,
        values=values or {"total": 4200000000.0, "C41": 1500000000.0},
    )


# ===================================================================
# Hash comparison — identical results
# ===================================================================


class TestHashComparison:
    """Verify RunSnapshot reproduces identical results."""

    def test_identical_results_pass(self) -> None:
        checker = ReproducibilityChecker()
        original = [_make_result_set()]
        reproduced = [_make_result_set()]
        result = checker.verify_results(
            original_results=original,
            reproduced_results=reproduced,
        )
        assert result.reproducible is True

    def test_different_values_fail(self) -> None:
        checker = ReproducibilityChecker()
        original = [_make_result_set(values={"total": 4200000000.0})]
        reproduced = [_make_result_set(values={"total": 9999999999.0})]
        result = checker.verify_results(
            original_results=original,
            reproduced_results=reproduced,
        )
        assert result.reproducible is False

    def test_within_tolerance_passes(self) -> None:
        checker = ReproducibilityChecker(tolerance=1e-6)
        original = [_make_result_set(values={"total": 4200000000.0})]
        reproduced = [_make_result_set(values={"total": 4200000000.000001})]
        result = checker.verify_results(
            original_results=original,
            reproduced_results=reproduced,
        )
        assert result.reproducible is True

    def test_outside_tolerance_fails(self) -> None:
        checker = ReproducibilityChecker(tolerance=1e-6)
        original = [_make_result_set(values={"total": 4200000000.0})]
        reproduced = [_make_result_set(values={"total": 4200001000.0})]
        result = checker.verify_results(
            original_results=original,
            reproduced_results=reproduced,
        )
        assert result.reproducible is False

    def test_missing_metric_fails(self) -> None:
        checker = ReproducibilityChecker()
        original = [_make_result_set(metric_type="gdp_impact")]
        reproduced = [_make_result_set(metric_type="jobs")]
        result = checker.verify_results(
            original_results=original,
            reproduced_results=reproduced,
        )
        assert result.reproducible is False

    def test_different_count_fails(self) -> None:
        checker = ReproducibilityChecker()
        original = [_make_result_set(), _make_result_set(metric_type="jobs")]
        reproduced = [_make_result_set()]
        result = checker.verify_results(
            original_results=original,
            reproduced_results=reproduced,
        )
        assert result.reproducible is False

    def test_empty_results_match(self) -> None:
        checker = ReproducibilityChecker()
        result = checker.verify_results(
            original_results=[],
            reproduced_results=[],
        )
        assert result.reproducible is True


# ===================================================================
# Version drift detection
# ===================================================================


class TestVersionDrift:
    """Detect if referenced versions have changed since the run."""

    def test_no_drift(self) -> None:
        checker = ReproducibilityChecker()
        snapshot = _make_snapshot()
        current_versions = {
            "model_version_id": MODEL_V1,
            "taxonomy_version_id": TAX_V1,
            "concordance_version_id": CONC_V1,
            "mapping_library_version_id": MAP_V1,
            "assumption_library_version_id": ASSUM_V1,
            "prompt_pack_version_id": PROMPT_V1,
        }
        drifts = checker.detect_version_drift(snapshot, current_versions)
        assert len(drifts) == 0

    def test_model_version_drifted(self) -> None:
        checker = ReproducibilityChecker()
        snapshot = _make_snapshot()
        current_versions = {
            "model_version_id": uuid7(),  # Different!
            "taxonomy_version_id": TAX_V1,
            "concordance_version_id": CONC_V1,
            "mapping_library_version_id": MAP_V1,
            "assumption_library_version_id": ASSUM_V1,
            "prompt_pack_version_id": PROMPT_V1,
        }
        drifts = checker.detect_version_drift(snapshot, current_versions)
        assert len(drifts) == 1
        assert drifts[0].field_name == "model_version_id"

    def test_multiple_drifts(self) -> None:
        checker = ReproducibilityChecker()
        snapshot = _make_snapshot()
        current_versions = {
            "model_version_id": uuid7(),
            "taxonomy_version_id": uuid7(),
            "concordance_version_id": CONC_V1,
            "mapping_library_version_id": MAP_V1,
            "assumption_library_version_id": ASSUM_V1,
            "prompt_pack_version_id": PROMPT_V1,
        }
        drifts = checker.detect_version_drift(snapshot, current_versions)
        assert len(drifts) == 2

    def test_drift_contains_old_and_new(self) -> None:
        checker = ReproducibilityChecker()
        new_model = uuid7()
        snapshot = _make_snapshot()
        current_versions = {
            "model_version_id": new_model,
            "taxonomy_version_id": TAX_V1,
            "concordance_version_id": CONC_V1,
            "mapping_library_version_id": MAP_V1,
            "assumption_library_version_id": ASSUM_V1,
            "prompt_pack_version_id": PROMPT_V1,
        }
        drifts = checker.detect_version_drift(snapshot, current_versions)
        assert drifts[0].snapshot_value == MODEL_V1
        assert drifts[0].current_value == new_model

    def test_source_checksum_drift(self) -> None:
        checker = ReproducibilityChecker()
        snapshot = _make_snapshot(source_checksums=["sha256:" + "a" * 64])
        current_checksums = ["sha256:" + "b" * 64]
        has_drift = checker.detect_checksum_drift(snapshot, current_checksums)
        assert has_drift is True

    def test_source_checksum_no_drift(self) -> None:
        checker = ReproducibilityChecker()
        snapshot = _make_snapshot(source_checksums=["sha256:" + "a" * 64])
        current_checksums = ["sha256:" + "a" * 64]
        has_drift = checker.detect_checksum_drift(snapshot, current_checksums)
        assert has_drift is False


# ===================================================================
# ReproducibilityResult summary
# ===================================================================


class TestReproducibilityResult:
    """Result provides summary information."""

    def test_result_has_mismatches(self) -> None:
        checker = ReproducibilityChecker()
        original = [_make_result_set(values={"total": 100.0})]
        reproduced = [_make_result_set(values={"total": 200.0})]
        result = checker.verify_results(
            original_results=original,
            reproduced_results=reproduced,
        )
        assert len(result.mismatches) >= 1

    def test_result_no_mismatches_when_identical(self) -> None:
        checker = ReproducibilityChecker()
        original = [_make_result_set()]
        reproduced = [_make_result_set()]
        result = checker.verify_results(
            original_results=original,
            reproduced_results=reproduced,
        )
        assert len(result.mismatches) == 0
