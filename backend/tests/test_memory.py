"""Memory engine tests."""

import pytest

from app.memory.service import InMemoryMemoryService


@pytest.mark.anyio
async def test_memory_save_search_retrieve_and_summarize() -> None:
    """Memory service supports all required operations."""
    memory = InMemoryMemoryService()
    await memory.save("user", "conversation:one", "JARVIS remembers project architecture")
    results = await memory.search("user", "architecture", limit=5)
    retrieved = await memory.retrieve("user", "conversation:one")
    summary = await memory.summarize("user", "conversation:one")
    assert results
    assert retrieved[0].content.startswith("JARVIS")
    assert "architecture" in summary
