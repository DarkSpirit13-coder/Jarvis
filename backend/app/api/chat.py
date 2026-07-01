"""Chat and tool discovery endpoints."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.conversation_manager import ConversationManager, get_conversation_manager
from app.tools.factory import get_tool_registry
from app.tools.registry import ToolRegistry

router = APIRouter(tags=["chat"])
ConversationManagerDependency = Annotated[ConversationManager, Depends(get_conversation_manager)]
ToolRegistryDependency = Annotated[ToolRegistry, Depends(get_tool_registry)]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    manager: ConversationManagerDependency,
) -> ChatResponse:
    """Run a complete chat turn and return the final assistant response."""
    result = await manager.handle_message(payload.user_id, payload.conversation_id, payload.message)
    return ChatResponse(**result.model_dump())


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    manager: ConversationManagerDependency,
) -> StreamingResponse:
    """Stream a chat response as server-sent events."""

    async def events():
        """Yield SSE token events from the conversation manager."""
        async for token in manager.stream_response(payload.user_id, payload.conversation_id, payload.message):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/tools")
async def tools(registry: ToolRegistryDependency) -> list[dict]:
    """Return dynamically discoverable tool metadata."""
    return [tool.metadata() for tool in registry.list_tools()]
