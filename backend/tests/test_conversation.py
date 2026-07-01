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
        self.final_messages: list[LLMMessage] = []

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
        self.final_messages = messages
        return LLMResponse(content="The echo tool returned done.", usage={"total_tokens": 12})

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        """Stream a deterministic assistant response."""
        for token in ["The ", "stream ", "works."]:
            yield token


@pytest.mark.anyio
async def test_conversation_manager_runs_planner_tools_and_memory() -> None:
    """Conversation manager orchestrates planning, tools, generation, and persistence."""
    llm = ConversationLLM()
    registry = get_tool_registry()
    memory = InMemoryMemoryService()
    await memory.save("user", "conversation:conversation", "user: earlier architecture note")
    await memory.save("user", "conversation:conversation", "assistant: previous answer")
    await memory.save("user", "long_term", "architecture preference")
    manager = ConversationManager(
        llm=llm,
        memory_service=memory,
        planner=LLMPlannerAgent(llm, registry),
        tool_registry=registry,
        tool_router=ToolRouter(registry),
    )
    result = await manager.handle_message("user", "conversation", "echo architecture done")
    context = json.loads(llm.final_messages[1].content)
    persisted = await memory.retrieve("user", "conversation:conversation", limit=10)

    assert result.response == "The echo tool returned done."
    assert result.conversation_id == "conversation"
    assert result.plan.goal == "echo"
    assert result.tool_results[0].output["text"] == "done"
    assert result.execution_result.status.value == "completed"
    assert result.relevant_memories
    assert any(turn.role == "user" and turn.content == "earlier architecture note" for turn in result.history)
    assert result.usage["total_tokens"] == 12
    assert any(turn["content"] == "earlier architecture note" for turn in context["conversation_history"])
    assert any(record.content == "assistant: The echo tool returned done." for record in persisted)


@pytest.mark.anyio
async def test_respond_returns_plain_text_for_existing_callers() -> None:
    """Legacy respond method returns only assistant text."""
    llm = ConversationLLM()
    registry = get_tool_registry()
    manager = ConversationManager(
        llm=llm,
        memory_service=InMemoryMemoryService(),
        planner=LLMPlannerAgent(llm, registry),
        tool_registry=registry,
        tool_router=ToolRouter(registry),
    )

    assert await manager.respond("user", "conversation", "echo done") == "The echo tool returned done."
