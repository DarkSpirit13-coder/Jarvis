"""LLM-backed planner agent for intent analysis and tool selection."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.core.logging import get_logger
from app.llm.provider import BaseLLMProvider, LLMMessage
from app.tools.registry import ToolRegistry

logger = get_logger(__name__)


class PlannedToolCall(BaseModel):
    """Tool request selected by the planner."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    parallel_group: str | None = None


class PlanStep(BaseModel):
    """A single planner step."""

    order: int
    description: str


class PlannerOutput(BaseModel):
    """Structured planner decision consumed by the tool router."""

    goal: str
    reasoning: str
    steps: list[PlanStep] = Field(default_factory=list)
    tools: list[PlannedToolCall] = Field(default_factory=list)
    needs_memory: bool = False


@dataclass(frozen=True)
class PlannerContext:
    """Context available while planning a user request."""

    user_id: str
    conversation_id: str
    memory: list[str] = field(default_factory=list)


class PlannerAgent(ABC):
    """Interface implemented by planner agents."""

    @abstractmethod
    async def plan(self, message: str, context: PlannerContext) -> PlannerOutput:
        """Analyze a user message and return an executable plan."""


class LLMPlannerAgent(PlannerAgent):
    """Planner that asks the configured LLM for structured JSON decisions."""

    def __init__(self, llm: BaseLLMProvider, tool_registry: ToolRegistry) -> None:
        """Create a planner with an LLM and dynamic tool registry."""
        self.llm = llm
        self.tool_registry = tool_registry

    async def plan(self, message: str, context: PlannerContext) -> PlannerOutput:
        """Use the LLM to decide whether tools or memory are needed."""
        tool_manifest = [tool.to_openai_tool() for tool in self.tool_registry.list_tools()]
        system_prompt = (
            "You are the JARVIS planner. Return only JSON with keys goal, reasoning, steps, tools, "
            "and needs_memory. Choose tools only from the supplied manifest. Do not invent tool names."
        )
        prompt = {
            "user_message": message,
            "conversation_id": context.conversation_id,
            "available_tools": tool_manifest,
            "memory": context.memory,
            "schema": {
                "goal": "string",
                "reasoning": "string",
                "steps": [{"order": 1, "description": "string"}],
                "tools": [{"name": "string", "arguments": {}, "parallel_group": "string|null"}],
                "needs_memory": "boolean",
            },
        }
        response = await self.llm.complete(
            [LLMMessage(role="user", content=json.dumps(prompt))],
            json_mode=True,
            system_prompt=system_prompt,
        )
        try:
            plan = PlannerOutput.model_validate_json(response.content)
        except ValidationError as exc:
            logger.error("planner_invalid_json", extra={"error": str(exc), "content": response.content})
            raise ValueError("Planner returned invalid JSON") from exc
        registered = {tool.name for tool in self.tool_registry.list_tools()}
        unknown_tools = [tool.name for tool in plan.tools if tool.name not in registered]
        if unknown_tools:
            raise ValueError(f"Planner selected unknown tools: {', '.join(unknown_tools)}")
        logger.info(
            "planner_decision",
            extra={"goal": plan.goal, "tool_count": len(plan.tools), "needs_memory": plan.needs_memory},
        )
        return plan
