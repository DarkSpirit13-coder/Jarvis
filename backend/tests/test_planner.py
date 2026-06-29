"""Planner agent tests."""

import json
from collections.abc import AsyncIterator

import pytest

from app.agents.planner import LLMPlannerAgent, PlannerContext
from app.llm.provider import BaseLLMProvider, LLMMessage, LLMResponse
from app.tools.factory import get_tool_registry


class PlannerLLM(BaseLLMProvider):
    """Scripted LLM provider for planner tests."""

    async def complete(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        """Return a valid planner JSON response."""
        return LLMResponse(
            content=json.dumps(
                {
                    "goal": "know time",
                    "reasoning": "time tool is relevant",
                    "steps": [{"order": 1, "description": "get time"}],
                    "tools": [{"name": "time", "arguments": {"timezone": "UTC"}, "parallel_group": None}],
                    "needs_memory": False,
                }
            )
        )

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]:
        """Yield no tokens for planner tests."""
        if False:
            yield ""


@pytest.mark.anyio
async def test_planner_uses_registered_tools() -> None:
    """Planner returns structured tool calls selected from registry metadata."""
    planner = LLMPlannerAgent(PlannerLLM(), get_tool_registry())
    plan = await planner.plan("what time is it?", PlannerContext(user_id="u", conversation_id="c"))
    assert plan.goal == "know time"
    assert plan.tools[0].name == "time"
