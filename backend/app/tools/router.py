"""Tool router for executing planner-selected tools."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from app.agents.planner import PlannedToolCall, PlannerOutput
from app.config.settings import Settings, get_settings
from app.core.logging import get_logger
from app.tools.registry import ToolRegistry, ToolResult

logger = get_logger(__name__)


@dataclass(frozen=True)
class RoutedToolResult:
    """Tool execution result with routing metadata."""

    name: str
    success: bool
    output: dict[str, Any]
    error: str | None
    latency_ms: float


class ToolRouter:
    """Executes planned tools sequentially or by parallel group."""

    def __init__(self, registry: ToolRegistry, settings: Settings | None = None) -> None:
        """Create a tool router with retry and timeout settings."""
        self.registry = registry
        self.settings = settings or get_settings()

    async def execute_plan(self, plan: PlannerOutput) -> list[RoutedToolResult]:
        """Execute all tools selected by a plan."""
        results: list[RoutedToolResult] = []
        index = 0
        while index < len(plan.tools):
            current = plan.tools[index]
            if current.parallel_group:
                group = [tool for tool in plan.tools[index:] if tool.parallel_group == current.parallel_group]
                results.extend(await asyncio.gather(*(self._execute(tool) for tool in group)))
                index += len(group)
            else:
                results.append(await self._execute(current))
                index += 1
        return results

    async def _execute(self, call: PlannedToolCall) -> RoutedToolResult:
        """Execute one planned tool with retries, timeout, and structured errors."""
        started = time.perf_counter()
        last_error: str | None = None
        for attempt in range(self.settings.tool_retries + 1):
            try:
                result = await asyncio.wait_for(
                    self.registry.execute(call.name, call.arguments),
                    timeout=self.settings.tool_timeout_seconds,
                )
                latency_ms = (time.perf_counter() - started) * 1000
                logger.info(
                    "tool_execution",
                    extra={"tool": call.name, "success": result.success, "latency_ms": round(latency_ms, 2)},
                )
                return self._routed(call.name, result, latency_ms)
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "tool_execution_error", extra={"tool": call.name, "attempt": attempt, "error": last_error}
                )
        latency_ms = (time.perf_counter() - started) * 1000
        return RoutedToolResult(call.name, False, {}, last_error or "Tool execution failed", latency_ms)

    def _routed(self, name: str, result: ToolResult, latency_ms: float) -> RoutedToolResult:
        """Convert a tool result into routed metadata."""
        return RoutedToolResult(name, result.success, result.output, result.error, latency_ms)
