"""Built-in JARVIS tool implementations."""

from __future__ import annotations

import asyncio
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.tools.registry import BaseTool, ToolResult


class EchoInput(BaseModel):
    """Input for echoing text through the tool layer."""

    text: str = Field(min_length=1, max_length=4000)


class EchoTool(BaseTool):
    """Return the supplied text."""

    name = "echo"
    description = "Return text exactly as supplied for connectivity checks."
    input_model = EchoInput

    async def run(self, payload: EchoInput) -> ToolResult:
        """Return the input text."""
        return ToolResult(success=True, output={"text": payload.text})


class TimeInput(BaseModel):
    """Input for requesting current time."""

    timezone: str = "UTC"


class TimeTool(BaseTool):
    """Return the current server time."""

    name = "time"
    description = "Return the current server time in ISO-8601 format."
    input_model = TimeInput

    async def run(self, payload: TimeInput) -> ToolResult:
        """Return current UTC time and requested timezone label."""
        return ToolResult(success=True, output={"timezone": payload.timezone, "utc": datetime.now(UTC).isoformat()})


class SystemInfoInput(BaseModel):
    """Input for system information requests."""

    include_environment: bool = False


class SystemInfoTool(BaseTool):
    """Return safe runtime system metadata."""

    name = "system_info"
    description = "Return safe operating system and Python runtime metadata."
    input_model = SystemInfoInput

    async def run(self, payload: SystemInfoInput) -> ToolResult:
        """Return non-secret platform metadata."""
        return ToolResult(
            success=True,
            output={
                "system": platform.system(),
                "release": platform.release(),
                "python": platform.python_version(),
                "environment_included": payload.include_environment,
            },
        )


class BrowserInput(BaseModel):
    """Input for fetching an HTTP resource."""

    url: str = Field(pattern="^https?://", max_length=2048)
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=30.0)


class BrowserTool(BaseTool):
    """Fetch text content from an HTTP URL."""

    name = "browser"
    description = "Fetch an HTTP or HTTPS URL and return status, content type, and a text excerpt."
    input_model = BrowserInput

    async def run(self, payload: BrowserInput) -> ToolResult:
        """Fetch a URL using an async HTTP client."""
        async with httpx.AsyncClient(timeout=payload.timeout_seconds, follow_redirects=True) as client:
            response = await client.get(payload.url)
        response.raise_for_status()
        text = response.text[:8000]
        return ToolResult(
            success=True,
            output={
                "url": str(response.url),
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "text": text,
            },
        )


class FileInput(BaseModel):
    """Input for workspace file operations."""

    operation: Literal["read", "write"]
    path: str = Field(min_length=1, max_length=500)
    content: str | None = Field(default=None, max_length=50000)


class FileTool(BaseTool):
    """Read or write files inside the configured workspace root."""

    name = "file"
    description = "Read or write a UTF-8 text file within the configured workspace root."
    input_model = FileInput

    async def run(self, payload: FileInput) -> ToolResult:
        """Execute a safe workspace-scoped file operation."""
        root = Path(get_settings().workspace_root).resolve()
        target = (root / payload.path).resolve()
        if root != target and root not in target.parents:
            raise PermissionError("File access outside the workspace root is not allowed")
        if payload.operation == "read":
            return ToolResult(success=True, output={"path": str(target), "content": target.read_text(encoding="utf-8")})
        if payload.content is None:
            raise ValueError("content is required for write operations")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload.content, encoding="utf-8")
        return ToolResult(success=True, output={"path": str(target), "bytes": len(payload.content.encode("utf-8"))})


class TerminalInput(BaseModel):
    """Input for bounded terminal execution."""

    command: str = Field(min_length=1, max_length=2000)
    timeout_seconds: float | None = Field(default=None, ge=1.0, le=60.0)


class TerminalTool(BaseTool):
    """Execute a bounded shell command in the configured workspace root."""

    name = "terminal"
    description = "Execute a bounded terminal command in the configured workspace root."
    input_model = TerminalInput

    async def run(self, payload: TerminalInput) -> ToolResult:
        """Run a command asynchronously with timeout and captured output."""
        settings = get_settings()
        process = await asyncio.create_subprocess_shell(
            payload.command,
            cwd=str(Path(settings.workspace_root).resolve()),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timeout = payload.timeout_seconds or settings.terminal_timeout_seconds
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        return ToolResult(
            success=process.returncode == 0,
            output={
                "return_code": process.returncode,
                "stdout": stdout.decode(errors="replace")[-12000:],
                "stderr": stderr.decode(errors="replace")[-12000:],
            },
            error=None if process.returncode == 0 else "Command exited with non-zero status",
        )


def builtin_tools() -> list[BaseTool]:
    """Return all built-in tool instances."""
    return [BrowserTool(), EchoTool(), FileTool(), SystemInfoTool(), TerminalTool(), TimeTool()]
