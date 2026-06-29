"""Factory for tool registry construction."""

from app.tools.builtin import builtin_tools
from app.tools.registry import ToolRegistry


def get_tool_registry() -> ToolRegistry:
    """Return a registry with built-in tools automatically registered."""
    return ToolRegistry(builtin_tools())
