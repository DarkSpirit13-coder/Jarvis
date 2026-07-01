"""Planner agent tests."""

import json
from collections.abc import AsyncIterator

import pytest
from pydantic import BaseModel

from app.agents.planner import LLMPlannerAgent, Plan, PlannerContext
from app.llm.provider import BaseLLMProvider, LLMMessage, LLMResponse
from app.tools.factory import get_tool_registry
from app.tools.registry import BaseTool, ToolRegistry, ToolResult


class PlannerLLM(BaseLLMProvider):
    """Scripted LLM provider for planner tests."""

    def __init__(self, content: dict | None = None) -> None:
        """Create a scripted planner LLM response."""
        self.content = content

    async def complete(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        """Return a valid planner JSON response."""
        if self.content:
            return LLMResponse(content=json.dumps(self.content))
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
    """Planner normalizes legacy output while preserving tool calls."""
    planner = LLMPlannerAgent(PlannerLLM(), get_tool_registry())
    plan = await planner.plan("what time is it?", PlannerContext(user_id="u", conversation_id="c"))
    assert plan.goal == "know time"
    assert plan.intent == "system.status"
    assert plan.confidence == 0.5
    assert plan.required_tools == ["time"]
    assert plan.tools[0].name == "time"


@pytest.mark.anyio
async def test_planner_returns_v2_plan_schema() -> None:
    """Planner returns a structured Planner V2 plan."""
    planner = LLMPlannerAgent(
        PlannerLLM(
            {
                "intent": "browser.search",
                "confidence": 0.91,
                "required_tools": ["browser"],
                "goal": "research docs",
                "reasoning": "external information is required",
                "steps": [
                    {
                        "order": 1,
                        "description": "search the web",
                        "tool_name": "browser",
                        "metadata": {"query_type": "documentation"},
                    }
                ],
                "metadata": {"planner_version": "v2"},
                "tools": [
                    {
                        "name": "browser",
                        "arguments": {"url": "https://example.com"},
                        "parallel_group": None,
                    }
                ],
                "needs_memory": True,
            }
        ),
        get_tool_registry(),
    )

    plan = await planner.plan("search docs", PlannerContext(user_id="u", conversation_id="c"))

    assert isinstance(plan, Plan)
    assert plan.intent == "browser.search"
    assert plan.confidence == 0.91
    assert plan.required_tools == ["browser"]
    assert plan.steps[0].tool_name == "browser"
    assert plan.metadata["planner_version"] == "v2"


@pytest.mark.parametrize(
    "intent",
    [
        "conversation.chat",
        "browser.search",
        "filesystem.read",
        "filesystem.write",
        "email.send",
        "calendar.create",
        "task.create",
        "system.status",
    ],
)
def test_plan_supports_required_intents(intent: str) -> None:
    """Plan schema accepts every supported intent."""
    plan = Plan.model_validate(
        {
            "intent": intent,
            "confidence": 0.7,
            "required_tools": [],
            "goal": "goal",
            "reasoning": "reasoning",
            "steps": [{"order": 1, "description": "decide"}],
            "metadata": {"source": "test"},
        }
    )
    assert plan.intent == intent


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_plan_rejects_confidence_outside_range(confidence: float) -> None:
    """Plan confidence must always be between zero and one."""
    with pytest.raises(ValueError):
        Plan.model_validate(
            {
                "intent": "conversation.chat",
                "confidence": confidence,
                "required_tools": [],
                "goal": "goal",
                "reasoning": "reasoning",
                "metadata": {},
            }
        )


def test_plan_rejects_unknown_intent() -> None:
    """Plan schema rejects unsupported intents."""
    with pytest.raises(ValueError):
        Plan.model_validate(
            {
                "intent": "unsupported.intent",
                "confidence": 0.5,
                "required_tools": [],
                "goal": "goal",
                "reasoning": "reasoning",
                "metadata": {},
            }
        )


@pytest.mark.anyio
async def test_planner_rejects_unknown_required_tools() -> None:
    """Planner rejects plans that require tools outside the registry."""
    planner = LLMPlannerAgent(
        PlannerLLM(
            {
                "intent": "email.send",
                "confidence": 0.8,
                "required_tools": ["email"],
                "goal": "send email",
                "reasoning": "email requested",
                "steps": [{"order": 1, "description": "send email", "tool_name": "email"}],
                "metadata": {},
                "tools": [],
                "needs_memory": False,
            }
        ),
        get_tool_registry(),
    )

    with pytest.raises(ValueError, match="unknown tools"):
        await planner.plan("send email", PlannerContext(user_id="u", conversation_id="c"))


class ExecutingToolInput(BaseModel):
    """Input model for the non-executed test tool."""


class ExecutingTool(BaseTool):
    """Tool that fails if the planner attempts execution."""

    name = "executing_tool"
    description = "Fails if executed by the planner."
    input_model = ExecutingToolInput
    executed = False

    async def run(self, payload: ExecutingToolInput) -> ToolResult:
        """Mark execution and fail."""
        self.executed = True
        raise AssertionError("Planner must not execute tools")


@pytest.mark.anyio
async def test_planner_does_not_execute_tools() -> None:
    """Planner only creates plans and never invokes tool execution."""
    tool = ExecutingTool()
    registry = ToolRegistry([tool])
    planner = LLMPlannerAgent(
        PlannerLLM(
            {
                "intent": "conversation.chat",
                "confidence": 1.0,
                "required_tools": [],
                "goal": "chat",
                "reasoning": "no tool required",
                "steps": [{"order": 1, "description": "answer directly"}],
                "metadata": {},
                "tools": [],
                "needs_memory": False,
            }
        ),
        registry,
    )

    plan = await planner.plan("hello", PlannerContext(user_id="u", conversation_id="c"))

    assert plan.intent == "conversation.chat"
    assert tool.executed is False
