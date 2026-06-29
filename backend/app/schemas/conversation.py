"""Conversation API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    """Inbound user message request."""

    content: str = Field(min_length=1, max_length=16000)


class MessageRead(BaseModel):
    """Message projection returned to clients."""

    id: UUID
    role: str
    content: str
    created_at: datetime


class ConversationRead(BaseModel):
    """Conversation projection returned to clients."""

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
