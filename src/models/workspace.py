"""Workspace model — isolation boundary for data, permissions, and audit."""

from uuid import UUID

from pydantic import Field

from src.models.common import (
    DataClassification,
    ImpactOSBase,
    UTCTimestamp,
    UUIDv7,
    new_uuid7,
    utc_now,
)


class Workspace(ImpactOSBase):
    """Workspace is the top-level isolation boundary per Section 5.3.

    Each engagement gets its own workspace with scoped RBAC, audit logging,
    and data classification that controls AI routing (Section 4.3).
    """

    workspace_id: UUIDv7 = Field(default_factory=new_uuid7)
    client_name: str = Field(..., min_length=1, max_length=255)
    engagement_code: str = Field(..., min_length=1, max_length=100)
    classification: DataClassification = Field(
        default=DataClassification.CONFIDENTIAL,
        description="Data classification controlling AI routing and access.",
    )
    description: str = Field(default="", max_length=2000)
    created_by: UUID
    created_at: UTCTimestamp = Field(default_factory=utc_now)
    updated_at: UTCTimestamp = Field(default_factory=utc_now)
