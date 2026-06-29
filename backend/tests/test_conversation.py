"""Conversation manager orchestration tests."""

import json
from collections.abc import AsyncIterator

import pytest

from app.agents.planner import LLMPlannerAgent
from app.llm.provider import BaseLLMProvider, LLMMessage, LLMResponse
from app.memory.service import InMemoryMemoryService
from app.services.conversation_manager import ConversationManager
from app.tools.factory import get_tool_registry
from app.tools.router import ToolRouter


class ConversationLLM(BaseLLMProvider):
    """Scripted LLM provider for conversation tests."""

    def __init__(self) -> None:
        """Initialize call counter."""
        self.calls = 0

    async def complete(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        """Return planner JSON first, final response second."""
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content=json.dumps(
                    {
                        "goal": "echo",
                        "reasoning": "echo requested",
                        "steps": [],
                        "tools": [{"name": "echo", "arguments": {"text": "done"}, "parallel_group": None}],
                        "needs_memory": True,
                    }
                )
            )
        return LLMResponse(content="The echo tool returned done.")

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        """Stream a deterministic assistant response."""
        for token in ["The ", "stream ", "works."]:
            yield token


@pytest.mark.anyio
async def test_conversation_manager_runs_planner_tools_and_memory() -> None:
    """Conversation manager orchestrates planning, tools, generation, and persistence."""
    llm = ConversationLLM()
    registry = get_tool_registry()
    manager = ConversationManager(
        llm=llm,
        memory_service=InMemoryMemoryService(),
        planner=LLMPlannerAgent(llm, registry),
        tool_registry=registry,
        tool_router=ToolRouter(registry),
    )
    response = await manager.respond("user", "conversation", "echo done")
    assert response == "The echo tool returned done."
