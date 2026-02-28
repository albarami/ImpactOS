"""Tests for EngagementMemory model and EngagementMemoryStore (Task 11)."""

from __future__ import annotations

from uuid import UUID

from src.flywheel.engagement_memory import EngagementMemory, EngagementMemoryStore
from src.flywheel.models import PromotionStatus, ReuseScopeLevel
from src.models.common import new_uuid7


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_memory(
    category: str = "challenge",
    description: str = "Client challenged import share for steel fabrication",
    sector_code: str | None = "F",
    resolution: str | None = "Provided customs data evidence",
    time_to_resolve: str | None = "3 days",
    lesson_learned: str | None = "Always prepare customs data upfront",
    tags: list[str] | None = None,
    engagement_id: UUID | None = None,
    workspace_id: UUID | None = None,
) -> EngagementMemory:
    return EngagementMemory(
        engagement_id=engagement_id or new_uuid7(),
        category=category,
        description=description,
        sector_code=sector_code,
        resolution=resolution,
        time_to_resolve=time_to_resolve,
        lesson_learned=lesson_learned,
        created_by=new_uuid7(),
        tags=tags or [],
        workspace_id=workspace_id or new_uuid7(),
    )


# ---------------------------------------------------------------------------
# EngagementMemory model tests
# ---------------------------------------------------------------------------


class TestEngagementMemoryModel:
    """EngagementMemory has all required fields including promotion path."""

    def test_has_all_fields_including_promotion_path(self) -> None:
        memory = _make_memory()
        # Core fields
        assert isinstance(memory.memory_id, UUID)
        assert isinstance(memory.engagement_id, UUID)
        assert memory.category == "challenge"
        assert memory.description == "Client challenged import share for steel fabrication"
        assert memory.sector_code == "F"
        assert memory.resolution == "Provided customs data evidence"
        assert memory.time_to_resolve == "3 days"
        assert memory.lesson_learned == "Always prepare customs data upfront"
        assert isinstance(memory.created_by, UUID)
        assert memory.created_at is not None
        assert memory.tags == []
        # Promotion path (Amendment 8)
        assert memory.promoted_to is None
        assert memory.promotion_status == PromotionStatus.RAW

    def test_has_scope_fields(self) -> None:
        ws_id = new_uuid7()
        eng_id = new_uuid7()
        src_eng_id = new_uuid7()
        memory = EngagementMemory(
            engagement_id=eng_id,
            category="acceptance",
            description="Test",
            created_by=new_uuid7(),
            workspace_id=ws_id,
            source_engagement_id=src_eng_id,
            reuse_scope=ReuseScopeLevel.GLOBAL_INTERNAL,
            sanitized_for_promotion=True,
        )
        assert memory.workspace_id == ws_id
        assert memory.source_engagement_id == src_eng_id
        assert memory.reuse_scope == ReuseScopeLevel.GLOBAL_INTERNAL
        assert memory.sanitized_for_promotion is True

    def test_promotion_status_defaults_to_raw(self) -> None:
        memory = _make_memory()
        assert memory.promotion_status == PromotionStatus.RAW

    def test_scope_defaults(self) -> None:
        memory = _make_memory()
        assert memory.reuse_scope == ReuseScopeLevel.WORKSPACE_ONLY
        assert memory.sanitized_for_promotion is False
        assert memory.source_engagement_id is None

    def test_optional_fields_can_be_none(self) -> None:
        memory = EngagementMemory(
            engagement_id=new_uuid7(),
            category="methodology_dispute",
            description="Minimal memory",
            created_by=new_uuid7(),
            workspace_id=new_uuid7(),
        )
        assert memory.sector_code is None
        assert memory.resolution is None
        assert memory.time_to_resolve is None
        assert memory.lesson_learned is None
        assert memory.tags == []


# ---------------------------------------------------------------------------
# EngagementMemoryStore tests
# ---------------------------------------------------------------------------


class TestEngagementMemoryStore:
    """EngagementMemoryStore is append-only with search methods."""

    def test_append_and_get_by_id(self) -> None:
        store = EngagementMemoryStore()
        memory = _make_memory()
        store.append(memory)
        retrieved = store.get(memory.memory_id)
        assert retrieved is memory

    def test_find_by_category_returns_matching(self) -> None:
        store = EngagementMemoryStore()
        m_challenge = _make_memory(category="challenge")
        m_acceptance = _make_memory(category="acceptance")
        store.append(m_challenge)
        store.append(m_acceptance)

        result = store.find_by_category("challenge")
        assert len(result) == 1
        assert result[0].category == "challenge"

    def test_find_by_sector_returns_matching(self) -> None:
        store = EngagementMemoryStore()
        m_f = _make_memory(sector_code="F")
        m_c = _make_memory(sector_code="C")
        store.append(m_f)
        store.append(m_c)

        result = store.find_by_sector("F")
        assert len(result) == 1
        assert result[0].sector_code == "F"

    def test_find_by_engagement_returns_matching(self) -> None:
        store = EngagementMemoryStore()
        eng_id = new_uuid7()
        m_with = _make_memory(engagement_id=eng_id)
        m_other = _make_memory(engagement_id=new_uuid7())
        store.append(m_with)
        store.append(m_other)

        result = store.find_by_engagement(eng_id)
        assert len(result) == 1
        assert result[0].engagement_id == eng_id

    def test_find_by_tags_returns_memories_with_any_matching_tag(self) -> None:
        store = EngagementMemoryStore()
        m_steel = _make_memory(tags=["steel", "import"])
        m_concrete = _make_memory(tags=["concrete", "local_content"])
        m_both = _make_memory(tags=["steel", "concrete"])
        store.append(m_steel)
        store.append(m_concrete)
        store.append(m_both)

        # Search for "steel" — should match m_steel and m_both
        result = store.find_by_tags(["steel"])
        assert len(result) == 2

        # Search for "import" or "concrete" — should match all three
        result = store.find_by_tags(["import", "concrete"])
        assert len(result) == 3

    def test_find_by_tags_no_match_returns_empty(self) -> None:
        store = EngagementMemoryStore()
        m = _make_memory(tags=["steel"])
        store.append(m)

        result = store.find_by_tags(["nonexistent"])
        assert result == []

    def test_list_all_returns_all_memories(self) -> None:
        store = EngagementMemoryStore()
        memories = [_make_memory(category=f"cat_{i}") for i in range(5)]
        for m in memories:
            store.append(m)

        result = store.list_all()
        assert len(result) == 5

    def test_get_nonexistent_returns_none(self) -> None:
        store = EngagementMemoryStore()
        result = store.get(new_uuid7())
        assert result is None
