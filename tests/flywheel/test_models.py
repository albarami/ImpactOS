"""Tests for flywheel shared enums (Task 1)."""

from __future__ import annotations

import pytest

from src.flywheel.models import (
    AssumptionValueType,
    DraftStatus,
    PromotionStatus,
    ReuseScopeLevel,
)


class TestReuseScopeLevel:
    """ReuseScopeLevel enum has exactly three members with correct values."""

    def test_workspace_only(self) -> None:
        assert ReuseScopeLevel.WORKSPACE_ONLY == "WORKSPACE_ONLY"
        assert ReuseScopeLevel.WORKSPACE_ONLY.value == "WORKSPACE_ONLY"

    def test_sanitized_global(self) -> None:
        assert ReuseScopeLevel.SANITIZED_GLOBAL == "SANITIZED_GLOBAL"
        assert ReuseScopeLevel.SANITIZED_GLOBAL.value == "SANITIZED_GLOBAL"

    def test_global_internal(self) -> None:
        assert ReuseScopeLevel.GLOBAL_INTERNAL == "GLOBAL_INTERNAL"
        assert ReuseScopeLevel.GLOBAL_INTERNAL.value == "GLOBAL_INTERNAL"

    def test_member_count(self) -> None:
        assert len(ReuseScopeLevel) == 3

    def test_all_values(self) -> None:
        values = {m.value for m in ReuseScopeLevel}
        assert values == {"WORKSPACE_ONLY", "SANITIZED_GLOBAL", "GLOBAL_INTERNAL"}

    def test_is_str(self) -> None:
        for member in ReuseScopeLevel:
            assert isinstance(member, str)


class TestDraftStatus:
    """DraftStatus enum has exactly three members with correct values."""

    def test_draft(self) -> None:
        assert DraftStatus.DRAFT == "DRAFT"
        assert DraftStatus.DRAFT.value == "DRAFT"

    def test_review(self) -> None:
        assert DraftStatus.REVIEW == "REVIEW"
        assert DraftStatus.REVIEW.value == "REVIEW"

    def test_rejected(self) -> None:
        assert DraftStatus.REJECTED == "REJECTED"
        assert DraftStatus.REJECTED.value == "REJECTED"

    def test_member_count(self) -> None:
        assert len(DraftStatus) == 3

    def test_all_values(self) -> None:
        values = {m.value for m in DraftStatus}
        assert values == {"DRAFT", "REVIEW", "REJECTED"}

    def test_is_str(self) -> None:
        for member in DraftStatus:
            assert isinstance(member, str)


class TestPromotionStatus:
    """PromotionStatus enum has exactly four members with correct values."""

    def test_raw(self) -> None:
        assert PromotionStatus.RAW == "RAW"
        assert PromotionStatus.RAW.value == "RAW"

    def test_reviewed(self) -> None:
        assert PromotionStatus.REVIEWED == "REVIEWED"
        assert PromotionStatus.REVIEWED.value == "REVIEWED"

    def test_promoted(self) -> None:
        assert PromotionStatus.PROMOTED == "PROMOTED"
        assert PromotionStatus.PROMOTED.value == "PROMOTED"

    def test_dismissed(self) -> None:
        assert PromotionStatus.DISMISSED == "DISMISSED"
        assert PromotionStatus.DISMISSED.value == "DISMISSED"

    def test_member_count(self) -> None:
        assert len(PromotionStatus) == 4

    def test_all_values(self) -> None:
        values = {m.value for m in PromotionStatus}
        assert values == {"RAW", "REVIEWED", "PROMOTED", "DISMISSED"}

    def test_is_str(self) -> None:
        for member in PromotionStatus:
            assert isinstance(member, str)


class TestAssumptionValueType:
    """AssumptionValueType enum has exactly two members with correct values."""

    def test_numeric(self) -> None:
        assert AssumptionValueType.NUMERIC == "NUMERIC"
        assert AssumptionValueType.NUMERIC.value == "NUMERIC"

    def test_categorical(self) -> None:
        assert AssumptionValueType.CATEGORICAL == "CATEGORICAL"
        assert AssumptionValueType.CATEGORICAL.value == "CATEGORICAL"

    def test_member_count(self) -> None:
        assert len(AssumptionValueType) == 2

    def test_all_values(self) -> None:
        values = {m.value for m in AssumptionValueType}
        assert values == {"NUMERIC", "CATEGORICAL"}

    def test_is_str(self) -> None:
        for member in AssumptionValueType:
            assert isinstance(member, str)


class TestEnumFromString:
    """All enums can be constructed from their string values."""

    @pytest.mark.parametrize("value", ["WORKSPACE_ONLY", "SANITIZED_GLOBAL", "GLOBAL_INTERNAL"])
    def test_reuse_scope_from_string(self, value: str) -> None:
        assert ReuseScopeLevel(value) == value

    @pytest.mark.parametrize("value", ["DRAFT", "REVIEW", "REJECTED"])
    def test_draft_status_from_string(self, value: str) -> None:
        assert DraftStatus(value) == value

    @pytest.mark.parametrize("value", ["RAW", "REVIEWED", "PROMOTED", "DISMISSED"])
    def test_promotion_status_from_string(self, value: str) -> None:
        assert PromotionStatus(value) == value

    @pytest.mark.parametrize("value", ["NUMERIC", "CATEGORICAL"])
    def test_assumption_value_type_from_string(self, value: str) -> None:
        assert AssumptionValueType(value) == value

    def test_invalid_reuse_scope_raises(self) -> None:
        with pytest.raises(ValueError):
            ReuseScopeLevel("INVALID")

    def test_invalid_draft_status_raises(self) -> None:
        with pytest.raises(ValueError):
            DraftStatus("INVALID")

    def test_invalid_promotion_status_raises(self) -> None:
        with pytest.raises(ValueError):
            PromotionStatus("INVALID")

    def test_invalid_assumption_value_type_raises(self) -> None:
        with pytest.raises(ValueError):
            AssumptionValueType("INVALID")
