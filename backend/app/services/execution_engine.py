"""Execution engine for Planner V2 plans."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.agents.planner import Plan, PlannedToolCall
from app.config.settings import Settings, get_settings
from app.core.logging import get_logger
from app.tools.router import RoutedToolResult, ToolRouter

logger = get_logger(__name__)


class ExecutionEventType(StrEnum):
    """Structured execution event names emitted by the engine."""

    STARTED = "STARTED"
    STEP_STARTED = "STEP_STARTED"
    STEP_COMPLETED = "STEP_COMPLETED"
    STEP_FAILED = "STEP_FAILED"
    FINISHED = "FINISHED"


class ExecutionStatus(StrEnum):
    """Final execution result status."""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CancellationToken:
    """Cooperative cancellation token for plan execution."""

    reason: str | None = None
    _cancelled: bool = False

    def cancel(self, reason: str | None = None) -> None:
        """Request cancellation for the running execution."""
        self._cancelled = True
        self.reason = reason

    @property
    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        return self._cancelled


@dataclass(frozen=True)
class ExecutionEvent:
    """Structured event emitted during execution."""

    type: ExecutionEventType
    step_order: int | None = None
    step_description: str | None = None
    tool_name: str | None = None
    status: str | None = None
    latency_ms: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionStepRecord:
    """Record of a completed or failed execution step."""

    order: int
    description: str
    tool_name: str | None
    attempts: int
    latency_ms: float


@dataclass(frozen=True)
class ExecutionResult:
    """Result returned after executing a plan."""

    status: ExecutionStatus
    completed_steps: list[ExecutionStepRecord]
    failed_steps: list[ExecutionStepRecord]
    tool_outputs: list[RoutedToolResult]
    latency_ms: float
    errors: list[str]
    events: list[ExecutionEvent] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        """Return a JSON-serializable execution result."""
        return {
            "status": self.status.value,
            "completed_steps": [step.__dict__ for step in self.completed_steps],
            "failed_steps": [step.__dict__ for step in self.failed_steps],
            "tool_outputs": [output.__dict__ for output in self.tool_outputs],
            "latency_ms": self.latency_ms,
            "errors": self.errors,
            "events": [
                {
                    "type": event.type.value,
                    "step_order": event.step_order,
                    "step_description": event.step_description,
                    "tool_name": event.tool_name,
                    "status": event.status,
                    "latency_ms": event.latency_ms,
                    "error": event.error,
                    "metadata": event.metadata,
                }
                for event in self.events
            ],
        }


class ExecutionEngine:
    """Executes Planner V2 plans without changing ToolRouter semantics."""

    def __init__(self, tool_router: ToolRouter, settings: Settings | None = None) -> None:
        """Create an execution engine with a router and retry configuration."""
        self.tool_router = tool_router
        self.settings = settings or get_settings()

    async def execute(self, plan: Plan, cancellation_token: CancellationToken | None = None) -> ExecutionResult:
        """Execute ordered plan steps and return structured execution output."""
        token = cancellation_token or CancellationToken()
        started = time.perf_counter()
        events: list[ExecutionEvent] = []
        completed_steps: list[ExecutionStepRecord] = []
        failed_steps: list[ExecutionStepRecord] = []
        tool_outputs: list[RoutedToolResult] = []
        errors: list[str] = []

        self._emit(events, ExecutionEvent(type=ExecutionEventType.STARTED, metadata={"intent": plan.intent}))
        for order, description, tool_call in self._ordered_work(plan):
            if token.is_cancelled:
                errors.append(token.reason or "Execution cancelled")
                break

            step_started = time.perf_counter()
            self._emit(
                events,
                ExecutionEvent(
                    type=ExecutionEventType.STEP_STARTED,
                    step_order=order,
                    step_description=description,
                    tool_name=tool_call.name if tool_call else None,
                ),
            )

            if tool_call is None:
                latency_ms = self._elapsed_ms(step_started)
                completed_steps.append(ExecutionStepRecord(order, description, None, attempts=0, latency_ms=latency_ms))
                self._emit(
                    events,
                    ExecutionEvent(
                        type=ExecutionEventType.STEP_COMPLETED,
                        step_order=order,
                        step_description=description,
                        status="skipped_tool_execution",
                        latency_ms=latency_ms,
                    ),
                )
                continue

            result, attempts = await self._execute_tool_step(tool_call, token)
            latency_ms = self._elapsed_ms(step_started)
            if result:
                tool_outputs.append(result)
            if result and result.success:
                completed_steps.append(
                    ExecutionStepRecord(order, description, tool_call.name, attempts=attempts, latency_ms=latency_ms)
                )
                self._emit(
                    events,
                    ExecutionEvent(
                        type=ExecutionEventType.STEP_COMPLETED,
                        step_order=order,
                        step_description=description,
                        tool_name=tool_call.name,
                        status="tool_completed",
                        latency_ms=latency_ms,
                    ),
                )
            else:
                error = result.error if result and result.error else f"Tool failed: {tool_call.name}"
                errors.append(error)
                failed_steps.append(
                    ExecutionStepRecord(order, description, tool_call.name, attempts=attempts, latency_ms=latency_ms)
                )
                self._emit(
                    events,
                    ExecutionEvent(
                        type=ExecutionEventType.STEP_FAILED,
                        step_order=order,
                        step_description=description,
                        tool_name=tool_call.name,
                        status="tool_failed",
                        latency_ms=latency_ms,
                        error=error,
                    ),
                )

        status = self._status(token, failed_steps)
        latency_ms = self._elapsed_ms(started)
        self._emit(events, ExecutionEvent(type=ExecutionEventType.FINISHED, status=status.value, latency_ms=latency_ms))
        return ExecutionResult(status, completed_steps, failed_steps, tool_outputs, latency_ms, errors, events)

    async def _execute_tool_step(
        self, tool_call: PlannedToolCall, token: CancellationToken
    ) -> tuple[RoutedToolResult | None, int]:
        """Execute a single tool call through ToolRouter with engine-level retries."""
        result: RoutedToolResult | None = None
        attempts = 0
        for attempt in range(self.settings.tool_retries + 1):
            if token.is_cancelled:
                return result, attempts
            attempts = attempt + 1
            routed_results = await self.tool_router.execute_plan(
                Plan(
                    intent="conversation.chat",
                    confidence=1.0,
                    required_tools=[tool_call.name],
                    steps=[],
                    metadata={"execution_engine": "single_tool_step"},
                    goal=f"Execute tool {tool_call.name}",
                    reasoning="Execution engine isolated a single tool-enabled step.",
                    tools=[tool_call],
                )
            )
            result = routed_results[0] if routed_results else None
            if result and result.success:
                return result, attempts
            if result and result.error:
                logger.warning(
                    "execution_tool_retry",
                    extra={"tool": tool_call.name, "attempt": attempt, "error": result.error},
                )
        return result, attempts

    def _ordered_work(self, plan: Plan) -> list[tuple[int, str, PlannedToolCall | None]]:
        """Return ordered execution work from plan steps and tool calls."""
        if not plan.steps:
            return [(index, f"Execute tool {tool.name}", tool) for index, tool in enumerate(plan.tools, start=1)] or [
                (1, "Conversation-only response", None)
            ]

        remaining_tools = list(plan.tools)
        work: list[tuple[int, str, PlannedToolCall | None]] = []
        for step in sorted(plan.steps, key=lambda item: item.order):
            tool_call = self._pop_matching_tool(remaining_tools, step.tool_name)
            work.append((step.order, step.description, tool_call))
        for index, tool in enumerate(remaining_tools, start=len(work) + 1):
            work.append((index, f"Execute tool {tool.name}", tool))
        return work

    def _pop_matching_tool(self, tool_calls: list[PlannedToolCall], tool_name: str | None) -> PlannedToolCall | None:
        """Remove and return the first tool call matching a step tool name."""
        if not tool_name:
            return None
        for index, tool_call in enumerate(tool_calls):
            if tool_call.name == tool_name:
                return tool_calls.pop(index)
        return None

    def _emit(self, events: list[ExecutionEvent], event: ExecutionEvent) -> None:
        """Store and log an execution event."""
        events.append(event)
        logger.info(
            "execution_event",
            extra={
                "event": event.type.value,
                "step_order": event.step_order,
                "tool_name": event.tool_name,
                "status": event.status,
                "latency_ms": event.latency_ms,
                "error": event.error,
            },
        )

    def _status(self, token: CancellationToken, failed_steps: list[ExecutionStepRecord]) -> ExecutionStatus:
        """Compute final execution status."""
        if token.is_cancelled:
            return ExecutionStatus.CANCELLED
        if failed_steps:
            return ExecutionStatus.FAILED
        return ExecutionStatus.COMPLETED

    def _elapsed_ms(self, started: float) -> float:
        """Return elapsed milliseconds from a perf-counter start."""
        return round((time.perf_counter() - started) * 1000, 2)
