"""Built-in tool and router tests."""

import pytest

from app.agents.planner import PlannedToolCall, PlannerOutput
from app.tools.factory import get_tool_registry
from app.tools.router import ToolRouter


@pytest.mark.anyio
async def test_echo_tool_executes_with_validation() -> None:
    """Echo tool validates input and returns structured output."""
    registry = get_tool_registry()
    result = await registry.execute("echo", {"text": "hello"})
    assert result.success is True
    assert result.output["text"] == "hello"


@pytest.mark.anyio
async def test_router_executes_planned_tool() -> None:
    """Tool router executes planner-selected tools and returns metadata."""
    plan = PlannerOutput(
        goal="echo",
        reasoning="verify route",
        steps=[],
        tools=[PlannedToolCall(name="echo", arguments={"text": "routed"})],
    )
    results = await ToolRouter(get_tool_registry()).execute_plan(plan)
    assert results[0].success is True
    assert results[0].output["text"] == "routed"
