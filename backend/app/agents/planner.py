"""LLM-backed planner agent for intent analysis and tool selection."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.core.logging import get_logger
from app.llm.provider import BaseLLMProvider, LLMMessage
from app.tools.registry import ToolRegistry

logger = get_logger(__name__)

PlannerIntent = Literal[
    "conversation.chat",
    "browser.search",
    "filesystem.read",
    "filesystem.write",
    "email.send",
    "calendar.create",
    "task.create",
    "system.status",
]


class PlannedToolCall(BaseModel):
    """Tool request selected by the planner."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    parallel_group: str | None = None


class PlanStep(BaseModel):
    """A single planner step."""

    order: int = Field(ge=1)
    description: str
    tool_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    """Planner V2 structured execution plan."""

    intent: PlannerIntent
    confidence: float = Field(ge=0.0, le=1.0)
    required_tools: list[str] = Field(default_factory=list)
    steps: list[PlanStep] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    goal: str
    reasoning: str
    tools: list[PlannedToolCall] = Field(default_factory=list)
    needs_memory: bool = False

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_plan(cls, value: Any) -> Any:
        """Normalize Sprint 2 planner JSON into the Planner V2 shape."""
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if "intent" not in normalized:
            normalized["intent"] = cls._infer_intent(normalized)
        if "confidence" not in normalized:
            normalized["confidence"] = 0.5
        if "required_tools" not in normalized:
            normalized["required_tools"] = [
                tool.get("name") for tool in normalized.get("tools", []) if isinstance(tool, dict) and tool.get("name")
            ]
        if "metadata" not in normalized:
            normalized["metadata"] = {}
        normalized.setdefault("goal", normalized["intent"])
        normalized.setdefault("reasoning", "No planner reasoning supplied.")
        return normalized

    @field_validator("required_tools")
    @classmethod
    def deduplicate_required_tools(cls, value: list[str]) -> list[str]:
        """Return required tool names once while preserving planner order."""
        return list(dict.fromkeys(value))

    @staticmethod
    def _infer_intent(value: dict[str, Any]) -> PlannerIntent:
        """Infer a V2 intent for legacy planner responses."""
        tool_names = {
            tool.get("name")
            for tool in value.get("tools", [])
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
        }
        if "browser" in tool_names:
            return "browser.search"
        if "file" in tool_names:
            operation = next(
                (
                    tool.get("arguments", {}).get("operation")
                    for tool in value.get("tools", [])
                    if isinstance(tool, dict) and tool.get("name") == "file"
                ),
                None,
            )
            return "filesystem.write" if operation == "write" else "filesystem.read"
        if "system_info" in tool_names or "time" in tool_names:
            return "system.status"
        return "conversation.chat"


PlannerOutput = Plan


@dataclass(frozen=True)
class PlannerContext:
    """Context available while planning a user request."""

    user_id: str
    conversation_id: str
    memory: list[str] = field(default_factory=list)


class PlannerAgent(ABC):
    """Interface implemented by planner agents."""

    @abstractmethod
    async def plan(self, message: str, context: PlannerContext) -> Plan:
        """Analyze a user message and return an executable plan."""


class LLMPlannerAgent(PlannerAgent):
    """Planner that asks the configured LLM for structured JSON decisions."""

    def __init__(self, llm: BaseLLMProvider, tool_registry: ToolRegistry) -> None:
        """Create a planner with an LLM and dynamic tool registry."""
        self.llm = llm
        self.tool_registry = tool_registry

    async def plan(self, message: str, context: PlannerContext) -> Plan:
        """Use the LLM to decide whether tools or memory are needed."""
        tool_manifest = [tool.to_openai_tool() for tool in self.tool_registry.list_tools()]
        system_prompt = (
            "You are Planner V2 for JARVIS. Return only JSON. You create execution plans and never execute tools. "
            "Choose intent from: conversation.chat, browser.search, filesystem.read, filesystem.write, email.send, "
            "calendar.create, task.create, system.status. Confidence must be 0.0 through 1.0. Choose tools only "
            "from the supplied manifest. Do not invent tool names."
        )
        prompt = {
            "user_message": message,
            "conversation_id": context.conversation_id,
            "available_tools": tool_manifest,
            "memory": context.memory,
            "schema": {
                "intent": "one supported intent string",
                "confidence": "number between 0.0 and 1.0",
                "required_tools": ["registered tool name"],
                "metadata": {"key": "value"},
                "goal": "string",
                "reasoning": "string",
                "steps": [{"order": 1, "description": "string", "tool_name": "string|null", "metadata": {}}],
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
            plan = Plan.model_validate_json(response.content)
        except ValidationError as exc:
            logger.error("planner_invalid_json", extra={"error": str(exc), "content": response.content})
            raise ValueError("Planner returned invalid JSON") from exc
        registered = {tool.name for tool in self.tool_registry.list_tools()}
        unknown_tools = [tool.name for tool in plan.tools if tool.name not in registered]
        unknown_required_tools = [tool for tool in plan.required_tools if tool not in registered]
        unknown_step_tools = [
            step.tool_name for step in plan.steps if step.tool_name and step.tool_name not in registered
        ]
        unknown_tools.extend(unknown_required_tools)
        unknown_tools.extend(unknown_step_tools)
        if unknown_tools:
            raise ValueError(f"Planner selected unknown tools: {', '.join(sorted(set(unknown_tools)))}")
        logger.info(
            "planner_decision",
            extra={
                "intent": plan.intent,
                "confidence": plan.confidence,
                "goal": plan.goal,
                "tool_count": len(plan.tools),
                "required_tools": plan.required_tools,
                "needs_memory": plan.needs_memory,
            },
        )
        return plan
