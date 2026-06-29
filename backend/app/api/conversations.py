"""Conversation orchestration endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.conversation import MessageCreate
from app.services.conversation_manager import ConversationManager, get_conversation_manager

router = APIRouter(tags=["conversations"])
ConversationManagerDependency = Annotated[ConversationManager, Depends(get_conversation_manager)]


@router.post("/{conversation_id}/messages")
async def create_message(
    conversation_id: str,
    payload: MessageCreate,
    manager: ConversationManagerDependency,
) -> dict[str, str]:
    """Submit a message to a conversation and receive the assistant response."""
    response = await manager.respond(user_id="anonymous", conversation_id=conversation_id, content=payload.content)
    return {"response": response}
