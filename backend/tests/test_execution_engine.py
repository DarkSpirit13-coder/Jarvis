"""Execution engine tests."""

import pytest

from app.agents.planner import Plan, PlannedToolCall, PlanStep
from app.config.settings import Settings
from app.services.execution_engine import CancellationToken, ExecutionEngine, ExecutionEventType, ExecutionStatus
from app.tools.router import RoutedToolResult


class ScriptedToolRouter:
    """Tool router test double preserving the public execute_plan API."""

    def __init__(self, results: list[RoutedToolResult]) -> None:
        """Create a router with scripted results."""
        self.results = results
        self.calls = 0
        self.executed_tool_names: list[str] = []

    async def execute_plan(self, plan: Plan) -> list[RoutedToolResult]:
        """Return the next scripted result for a plan."""
        self.calls += 1
        self.executed_tool_names.extend(tool.name for tool in plan.tools)
        index = min(self.calls - 1, len(self.results) - 1)
        return [self.results[index]]


def settings_with_retries(retries: int) -> Settings:
    """Return settings with a deterministic retry count."""
    return Settings(tool_retries=retries)


def plan_with_steps() -> Plan:
    """Return a plan with conversation and tool-enabled steps."""
    return Plan(
        intent="system.status",
        confidence=0.9,
        required_tools=["time"],
        goal="check status",
        reasoning="time is needed",
        steps=[
            PlanStep(order=1, description="think about request"),
            PlanStep(order=2, description="get time", tool_name="time"),
        ],
        metadata={"test": True},
        tools=[PlannedToolCall(name="time", arguments={"timezone": "UTC"})],
    )


@pytest.mark.anyio
async def test_execution_engine_runs_ordered_steps_and_skips_conversation_only_steps() -> None:
    """Execution engine skips non-tool steps and routes tool-enabled steps."""
    router = ScriptedToolRouter([RoutedToolResult("time", True, {"utc": "now"}, None, 1.0)])
    engine = ExecutionEngine(router, settings=settings_with_retries(0))

    result = await engine.execute(plan_with_steps())

    assert result.status == ExecutionStatus.COMPLETED
    assert [step.order for step in result.completed_steps] == [1, 2]
    assert result.completed_steps[0].tool_name is None
    assert result.tool_outputs[0].output["utc"] == "now"
    assert router.executed_tool_names == ["time"]
    assert [event.type for event in result.events] == [
        ExecutionEventType.STARTED,
        ExecutionEventType.STEP_STARTED,
        ExecutionEventType.STEP_COMPLETED,
        ExecutionEventType.STEP_STARTED,
        ExecutionEventType.STEP_COMPLETED,
        ExecutionEventType.FINISHED,
    ]


@pytest.mark.anyio
async def test_execution_engine_retries_failed_tool_calls() -> None:
    """Execution engine retries failed routed tool results using settings."""
    router = ScriptedToolRouter(
        [
            RoutedToolResult("time", False, {}, "temporary failure", 1.0),
            RoutedToolResult("time", True, {"utc": "now"}, None, 1.0),
        ]
    )
    engine = ExecutionEngine(router, settings=settings_with_retries(1))

    result = await engine.execute(plan_with_steps())

    assert result.status == ExecutionStatus.COMPLETED
    assert router.calls == 2
    assert result.completed_steps[-1].attempts == 2
    assert not result.failed_steps


@pytest.mark.anyio
async def test_execution_engine_reports_failed_steps_after_retries() -> None:
    """Execution engine returns failed status and structured errors after retries are exhausted."""
    router = ScriptedToolRouter([RoutedToolResult("time", False, {}, "still down", 1.0)])
    engine = ExecutionEngine(router, settings=settings_with_retries(1))

    result = await engine.execute(plan_with_steps())

    assert result.status == ExecutionStatus.FAILED
    assert result.failed_steps[0].tool_name == "time"
    assert result.errors == ["still down"]
    assert router.calls == 2


@pytest.mark.anyio
async def test_execution_engine_supports_cancellation_tokens() -> None:
    """Execution engine stops before executing tools when cancellation is requested."""
    router = ScriptedToolRouter([RoutedToolResult("time", True, {"utc": "now"}, None, 1.0)])
    engine = ExecutionEngine(router, settings=settings_with_retries(0))
    token = CancellationToken()
    token.cancel("operator cancelled")

    result = await engine.execute(plan_with_steps(), cancellation_token=token)

    assert result.status == ExecutionStatus.CANCELLED
    assert result.errors == ["operator cancelled"]
    assert router.calls == 0
    assert result.events[-1].type == ExecutionEventType.FINISHED
