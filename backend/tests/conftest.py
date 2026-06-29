"""Shared pytest configuration for backend tests."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Run async tests on asyncio only."""
    return "asyncio"
