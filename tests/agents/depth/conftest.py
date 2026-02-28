"""Shared fixtures for depth engine tests."""

import pytest
from uuid import uuid4

from src.models.common import new_uuid7


@pytest.fixture
def workspace_id():
    return uuid4()


@pytest.fixture
def plan_id():
    return new_uuid7()


@pytest.fixture
def scenario_spec_id():
    return uuid4()
