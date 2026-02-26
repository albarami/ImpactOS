"""Tests for ImpactOS core Pydantic models.

Covers: immutability, validation, enums, state machines, and version incrementing.
"""

from uuid import UUID

import pytest
from pydantic import ValidationError
from uuid_extensions import uuid7

from src.models.common import (
    AssumptionStatus,
    ClaimStatus,
    ClaimType,
    ConstraintConfidence,
    DataClassification,
    DisclosureTier,
    ExportMode,
    utc_now,
)
from src.models.export import Export, ExportStatus
from src.models.governance import (
    Assumption,
    AssumptionRange,
    BoundingBox,
    Claim,
    EvidenceSnippet,
    ModelRef,
    TableCellRef,
    VALID_CLAIM_TRANSITIONS,
)
from src.models.model_version import ConcordanceVersion, ModelVersion, TaxonomyVersion
from src.models.run import ResultSet, RunRequest, RunSnapshot
from src.models.scenario import (
    ConstraintOverride,
    DataQualitySummary,
    FinalDemandShock,
    ImportSubstitutionShock,
    LocalContentChange,
    MappingConfidence,
    ScenarioSpec,
    TimeHorizon,
)
from src.models.workspace import Workspace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_CHECKSUM = "sha256:" + "a" * 64


def _make_model_version(**overrides: object) -> ModelVersion:
    defaults: dict[str, object] = {
        "base_year": 2023,
        "source": "GASTAT 2023 I-O Tables",
        "sector_count": 45,
        "checksum": VALID_CHECKSUM,
    }
    defaults.update(overrides)
    return ModelVersion(**defaults)  # type: ignore[arg-type]


def _make_run_snapshot(**overrides: object) -> RunSnapshot:
    defaults: dict[str, object] = {
        "run_id": uuid7(),
        "model_version_id": uuid7(),
        "taxonomy_version_id": uuid7(),
        "concordance_version_id": uuid7(),
        "mapping_library_version_id": uuid7(),
        "assumption_library_version_id": uuid7(),
        "prompt_pack_version_id": uuid7(),
    }
    defaults.update(overrides)
    return RunSnapshot(**defaults)  # type: ignore[arg-type]


def _make_workspace(**overrides: object) -> Workspace:
    defaults: dict[str, object] = {
        "client_name": "Test Client",
        "engagement_code": "ENG-001",
        "classification": DataClassification.CONFIDENTIAL,
        "created_by": uuid7(),
    }
    defaults.update(overrides)
    return Workspace(**defaults)  # type: ignore[arg-type]


def _make_assumption(**overrides: object) -> Assumption:
    defaults: dict[str, object] = {
        "type": "IMPORT_SHARE",
        "value": 0.35,
        "units": "fraction",
        "justification": "Based on trade benchmarks.",
        "status": AssumptionStatus.DRAFT,
    }
    defaults.update(overrides)
    return Assumption(**defaults)  # type: ignore[arg-type]


def _make_claim(**overrides: object) -> Claim:
    defaults: dict[str, object] = {
        "text": "Total output increases by SAR 12.4bn.",
        "claim_type": ClaimType.MODEL,
        "status": ClaimStatus.EXTRACTED,
    }
    defaults.update(overrides)
    return Claim(**defaults)  # type: ignore[arg-type]


def _make_scenario_spec(**overrides: object) -> ScenarioSpec:
    defaults: dict[str, object] = {
        "name": "NEOM Logistics Zone - Base",
        "workspace_id": uuid7(),
        "base_model_version_id": uuid7(),
        "base_year": 2023,
        "time_horizon": TimeHorizon(start_year=2026, end_year=2030),
    }
    defaults.update(overrides)
    return ScenarioSpec(**defaults)  # type: ignore[arg-type]


# ===================================================================
# ModelVersion immutability
# ===================================================================


class TestModelVersionImmutability:
    """ModelVersion is frozen=True; field assignment must raise."""

    def test_creation_succeeds(self) -> None:
        mv = _make_model_version()
        assert mv.base_year == 2023
        assert mv.sector_count == 45

    def test_field_assignment_raises(self) -> None:
        mv = _make_model_version()
        with pytest.raises(ValidationError):
            mv.base_year = 2024  # type: ignore[misc]

    def test_uuid_is_generated(self) -> None:
        mv = _make_model_version()
        assert isinstance(mv.model_version_id, UUID)

    def test_timestamp_is_timezone_aware(self) -> None:
        mv = _make_model_version()
        assert mv.created_at.tzinfo is not None


# ===================================================================
# RunSnapshot immutability
# ===================================================================


class TestRunSnapshotImmutability:
    """RunSnapshot is frozen=True; captures all version refs."""

    def test_creation_succeeds(self) -> None:
        snap = _make_run_snapshot()
        assert isinstance(snap.run_id, UUID)

    def test_field_assignment_raises(self) -> None:
        snap = _make_run_snapshot()
        with pytest.raises(ValidationError):
            snap.run_id = uuid7()  # type: ignore[misc]

    def test_optional_constraint_set_defaults_none(self) -> None:
        snap = _make_run_snapshot()
        assert snap.constraint_set_version_id is None


# ===================================================================
# ResultSet immutability
# ===================================================================


class TestResultSetImmutability:
    """ResultSet is frozen=True."""

    def test_field_assignment_raises(self) -> None:
        rs = ResultSet(
            run_id=uuid7(),
            metric_type="total_output",
            values={"C41": 1_500_000_000.0},
        )
        with pytest.raises(ValidationError):
            rs.metric_type = "changed"  # type: ignore[misc]


# ===================================================================
# ScenarioSpec version incrementing
# ===================================================================


class TestScenarioSpecVersioning:
    """ScenarioSpec.next_version() increments version correctly."""

    def test_initial_version_is_one(self) -> None:
        spec = _make_scenario_spec()
        assert spec.version == 1

    def test_next_version_increments(self) -> None:
        spec = _make_scenario_spec()
        v2 = spec.next_version()
        assert v2.version == 2
        assert v2.scenario_spec_id == spec.scenario_spec_id

    def test_next_version_chain(self) -> None:
        spec = _make_scenario_spec()
        v3 = spec.next_version().next_version()
        assert v3.version == 3

    def test_next_version_updates_timestamp(self) -> None:
        spec = _make_scenario_spec()
        v2 = spec.next_version()
        assert v2.updated_at >= spec.updated_at


# ===================================================================
# ShockItem validation
# ===================================================================


class TestShockItemValidation:
    """Each ShockItem variant validates its required fields."""

    def test_final_demand_shock_valid(self) -> None:
        shock = FinalDemandShock(
            sector_code="C41-C43",
            year=2027,
            amount_real_base_year=1_500_000_000,
            domestic_share=0.65,
            import_share=0.35,
        )
        assert shock.type == "FINAL_DEMAND_SHOCK"

    def test_final_demand_shock_shares_must_sum_to_one(self) -> None:
        with pytest.raises(ValidationError, match="domestic_share.*import_share"):
            FinalDemandShock(
                sector_code="C41",
                year=2027,
                amount_real_base_year=100,
                domestic_share=0.5,
                import_share=0.3,
            )

    def test_import_substitution_requires_assumption_ref(self) -> None:
        with pytest.raises(ValidationError):
            ImportSubstitutionShock(
                sector_code="C24",
                year=2028,
                delta_import_share=-0.10,
                # missing assumption_ref
            )

    def test_import_substitution_valid(self) -> None:
        shock = ImportSubstitutionShock(
            sector_code="C24",
            year=2028,
            delta_import_share=-0.10,
            assumption_ref=uuid7(),
        )
        assert shock.type == "IMPORT_SUBSTITUTION"

    def test_local_content_requires_assumption_ref(self) -> None:
        with pytest.raises(ValidationError):
            LocalContentChange(
                sector_code="C33",
                year=2029,
                target_domestic_share=0.60,
                # missing assumption_ref
            )

    def test_local_content_valid(self) -> None:
        shock = LocalContentChange(
            sector_code="C33",
            year=2029,
            target_domestic_share=0.60,
            assumption_ref=uuid7(),
        )
        assert shock.type == "LOCAL_CONTENT"

    def test_constraint_override_requires_confidence(self) -> None:
        with pytest.raises(ValidationError):
            ConstraintOverride(
                sector_code="F",
                year=2028,
                cap_output=0.12,
                # missing confidence
            )

    def test_constraint_override_valid(self) -> None:
        shock = ConstraintOverride(
            sector_code="F",
            year=2028,
            cap_output=0.12,
            cap_jobs=15_000,
            confidence=ConstraintConfidence.ESTIMATED,
        )
        assert shock.type == "CONSTRAINT_OVERRIDE"


# ===================================================================
# Claim status state machine
# ===================================================================


class TestClaimStatusTransitions:
    """Claim.transition_to() follows the valid state machine."""

    def test_extracted_to_needs_evidence(self) -> None:
        claim = _make_claim(status=ClaimStatus.EXTRACTED)
        updated = claim.transition_to(ClaimStatus.NEEDS_EVIDENCE)
        assert updated.status == ClaimStatus.NEEDS_EVIDENCE

    def test_extracted_to_supported(self) -> None:
        claim = _make_claim(status=ClaimStatus.EXTRACTED)
        updated = claim.transition_to(ClaimStatus.SUPPORTED)
        assert updated.status == ClaimStatus.SUPPORTED

    def test_extracted_to_deleted(self) -> None:
        claim = _make_claim(status=ClaimStatus.EXTRACTED)
        updated = claim.transition_to(ClaimStatus.DELETED)
        assert updated.status == ClaimStatus.DELETED

    def test_needs_evidence_to_supported(self) -> None:
        claim = _make_claim(status=ClaimStatus.NEEDS_EVIDENCE)
        updated = claim.transition_to(ClaimStatus.SUPPORTED)
        assert updated.status == ClaimStatus.SUPPORTED

    def test_needs_evidence_to_rewritten(self) -> None:
        claim = _make_claim(status=ClaimStatus.NEEDS_EVIDENCE)
        updated = claim.transition_to(ClaimStatus.REWRITTEN_AS_ASSUMPTION)
        assert updated.status == ClaimStatus.REWRITTEN_AS_ASSUMPTION

    def test_supported_to_approved(self) -> None:
        claim = _make_claim(status=ClaimStatus.SUPPORTED)
        updated = claim.transition_to(ClaimStatus.APPROVED_FOR_EXPORT)
        assert updated.status == ClaimStatus.APPROVED_FOR_EXPORT

    def test_invalid_transition_raises(self) -> None:
        claim = _make_claim(status=ClaimStatus.EXTRACTED)
        with pytest.raises(ValueError, match="Cannot transition"):
            claim.transition_to(ClaimStatus.APPROVED_FOR_EXPORT)

    def test_deleted_is_terminal(self) -> None:
        claim = _make_claim(status=ClaimStatus.DELETED)
        with pytest.raises(ValueError, match="Cannot transition"):
            claim.transition_to(ClaimStatus.EXTRACTED)

    def test_approved_is_terminal(self) -> None:
        claim = _make_claim(status=ClaimStatus.APPROVED_FOR_EXPORT)
        with pytest.raises(ValueError, match="Cannot transition"):
            claim.transition_to(ClaimStatus.NEEDS_EVIDENCE)

    def test_transition_updates_timestamp(self) -> None:
        claim = _make_claim(status=ClaimStatus.EXTRACTED)
        updated = claim.transition_to(ClaimStatus.NEEDS_EVIDENCE)
        assert updated.updated_at >= claim.updated_at


# ===================================================================
# Assumption validation
# ===================================================================


class TestAssumptionValidation:
    """Approved assumptions require a range; draft does not."""

    def test_draft_without_range_succeeds(self) -> None:
        assumption = _make_assumption(status=AssumptionStatus.DRAFT)
        assert assumption.range is None

    def test_approved_without_range_fails(self) -> None:
        with pytest.raises(ValidationError, match="sensitivity range"):
            _make_assumption(status=AssumptionStatus.APPROVED)

    def test_approved_with_range_succeeds(self) -> None:
        assumption = _make_assumption(
            status=AssumptionStatus.APPROVED,
            range=AssumptionRange(min=0.25, max=0.45),
            approved_by=uuid7(),
        )
        assert assumption.range is not None
        assert assumption.range.min == 0.25

    def test_range_max_less_than_min_fails(self) -> None:
        with pytest.raises(ValidationError, match="max must be >= min"):
            AssumptionRange(min=0.5, max=0.2)


# ===================================================================
# Workspace classification enum
# ===================================================================


class TestWorkspaceClassification:
    """Workspace classification validates correctly."""

    @pytest.mark.parametrize(
        "classification",
        [
            DataClassification.PUBLIC,
            DataClassification.INTERNAL,
            DataClassification.CONFIDENTIAL,
            DataClassification.RESTRICTED,
        ],
    )
    def test_valid_classifications(self, classification: DataClassification) -> None:
        ws = _make_workspace(classification=classification)
        assert ws.classification == classification

    def test_invalid_classification_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_workspace(classification="TOP_SECRET")


# ===================================================================
# Invalid data rejection
# ===================================================================


class TestInvalidDataRejection:
    """Pydantic rejects malformed inputs across models."""

    def test_model_version_bad_checksum(self) -> None:
        with pytest.raises(ValidationError, match="checksum"):
            _make_model_version(checksum="md5:abc")

    def test_model_version_negative_sector_count(self) -> None:
        with pytest.raises(ValidationError):
            _make_model_version(sector_count=-1)

    def test_workspace_empty_client_name(self) -> None:
        with pytest.raises(ValidationError):
            _make_workspace(client_name="")

    def test_time_horizon_end_before_start(self) -> None:
        with pytest.raises(ValidationError, match="end_year"):
            TimeHorizon(start_year=2030, end_year=2026)

    def test_final_demand_shock_invalid_share(self) -> None:
        with pytest.raises(ValidationError):
            FinalDemandShock(
                sector_code="C41",
                year=2027,
                amount_real_base_year=100,
                domestic_share=1.5,
                import_share=-0.5,
            )

    def test_evidence_snippet_bad_checksum(self) -> None:
        with pytest.raises(ValidationError, match="checksum"):
            EvidenceSnippet(
                source_id=uuid7(),
                page=0,
                bbox=BoundingBox(x0=0.1, y0=0.4, x1=0.9, y1=0.5),
                extracted_text="Some text",
                checksum="bad",
            )

    def test_evidence_snippet_is_immutable(self) -> None:
        snippet = EvidenceSnippet(
            source_id=uuid7(),
            page=0,
            bbox=BoundingBox(x0=0.1, y0=0.4, x1=0.9, y1=0.5),
            extracted_text="CAPEX: SAR 10,000,000,000",
            checksum=VALID_CHECKSUM,
        )
        with pytest.raises(ValidationError):
            snippet.page = 5  # type: ignore[misc]

    def test_export_invalid_mode(self) -> None:
        with pytest.raises(ValidationError):
            Export(
                run_id=uuid7(),
                template_version="SG-PACK-2026.1",
                mode="INVALID",
            )

    def test_claim_empty_text_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_claim(text="")

    def test_run_request_invalid_version(self) -> None:
        with pytest.raises(ValidationError):
            RunRequest(
                scenario_spec_id=uuid7(),
                scenario_spec_version=0,
                mode=ExportMode.SANDBOX,
            )


# ===================================================================
# Taxonomy and concordance
# ===================================================================


class TestTaxonomyAndConcordance:
    """TaxonomyVersion and ConcordanceVersion are frozen."""

    def test_taxonomy_creation(self) -> None:
        tv = TaxonomyVersion(sector_codes=["A", "B", "C"])
        assert len(tv.sector_codes) == 3

    def test_taxonomy_immutable(self) -> None:
        tv = TaxonomyVersion(sector_codes=["A", "B"])
        with pytest.raises(ValidationError):
            tv.sector_codes = ["X"]  # type: ignore[misc]

    def test_concordance_creation(self) -> None:
        cv = ConcordanceVersion(
            from_taxonomy=uuid7(),
            to_taxonomy=uuid7(),
            mappings={"A01": "SG-01", "A02": "SG-02"},
        )
        assert len(cv.mappings) == 2

    def test_concordance_immutable(self) -> None:
        cv = ConcordanceVersion(
            from_taxonomy=uuid7(),
            to_taxonomy=uuid7(),
            mappings={"A01": "SG-01"},
        )
        with pytest.raises(ValidationError):
            cv.from_taxonomy = uuid7()  # type: ignore[misc]


# ===================================================================
# Disclosure tier and export mode enums
# ===================================================================


class TestEnums:
    """Enum values round-trip correctly."""

    def test_disclosure_tiers(self) -> None:
        assert DisclosureTier.TIER0 == "TIER0"
        assert DisclosureTier.TIER1 == "TIER1"
        assert DisclosureTier.TIER2 == "TIER2"

    def test_export_modes(self) -> None:
        assert ExportMode.SANDBOX == "SANDBOX"
        assert ExportMode.GOVERNED == "GOVERNED"

    def test_export_status_values(self) -> None:
        assert ExportStatus.PENDING == "PENDING"
        assert ExportStatus.BLOCKED == "BLOCKED"
