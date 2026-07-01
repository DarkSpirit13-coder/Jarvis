"""Chat API schemas for JARVIS conversations."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for a chat turn."""

    message: str = Field(min_length=1, max_length=16000)
    conversation_id: str = Field(default="default", min_length=1, max_length=200)
    user_id: str = Field(default="anonymous", min_length=1, max_length=200)


class ChatResponse(BaseModel):
    """Non-streaming chat response."""

    conversation_id: str
    response: str
    plan: dict | None = None
    tool_results: list[dict] = Field(default_factory=list)
    execution_result: dict | None = None
    relevant_memories: list[str] = Field(default_factory=list)
    history: list[dict] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)


class ToolMetadata(BaseModel):
    """Public tool metadata response."""

    name: str
    description: str
    input_schema: dict
    output_schema: dict
