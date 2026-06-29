"""Tool abstractions, registration, and execution metadata."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ValidationError


class ToolExecutionError(Exception):
    """Raised when a tool cannot validate input or complete execution."""


class ToolResult(BaseModel):
    """Structured result returned by a tool execution."""

    success: bool
    output: dict[str, Any]
    error: str | None = None


class BaseTool(ABC):
    """Base class for every JARVIS tool."""

    name: str
    description: str
    input_model: type[BaseModel]

    @abstractmethod
    async def run(self, payload: BaseModel) -> ToolResult:
        """Execute validated tool input asynchronously."""

    async def execute(self, payload: dict[str, Any]) -> ToolResult:
        """Validate raw input and run the tool."""
        try:
            validated = self.input_model.model_validate(payload)
        except ValidationError as exc:
            raise ToolExecutionError(str(exc)) from exc
        return await self.run(validated)

    def to_openai_tool(self) -> dict[str, Any]:
        """Return provider-compatible tool metadata."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_model.model_json_schema(),
            },
        }

    def metadata(self) -> dict[str, Any]:
        """Return public metadata for API discovery."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
            "output_schema": ToolResult.model_json_schema(),
        }


class ToolRegistry:
    """Registry of available JARVIS tools."""

    def __init__(self, tools: list[BaseTool] | None = None) -> None:
        """Initialize a registry and register optional tools."""
        self._tools: dict[str, BaseTool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: BaseTool) -> None:
        """Register a tool implementation by name."""
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def list_tools(self) -> list[BaseTool]:
        """Return all registered tools in deterministic order."""
        return [self._tools[name] for name in sorted(self._tools)]

    def get(self, name: str) -> BaseTool:
        """Return a tool by name."""
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    async def execute(self, name: str, payload: dict[str, Any]) -> ToolResult:
        """Execute a named tool with validated input."""
        return await self.get(name).execute(payload)
