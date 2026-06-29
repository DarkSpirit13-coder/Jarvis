"""Conversation, session, and long-term memory services."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4


@dataclass(frozen=True)
class MemoryRecord:
    """A memory item available to JARVIS agents."""

    id: str
    user_id: str
    scope: str
    content: str
    created_at: datetime
    relevance: float = 1.0


class MemoryService(ABC):
    """Interface for retrieving, storing, and summarizing memory."""

    @abstractmethod
    async def save(self, user_id: str, scope: str, content: str) -> MemoryRecord:
        """Persist a memory item."""

    @abstractmethod
    async def search(self, user_id: str, query: str, limit: int = 10) -> list[MemoryRecord]:
        """Search memories relevant to a query."""

    @abstractmethod
    async def retrieve(self, user_id: str, scope: str, limit: int = 20) -> list[MemoryRecord]:
        """Retrieve recent memories for a scope."""

    @abstractmethod
    async def summarize(self, user_id: str, scope: str) -> str:
        """Summarize memories for a user and scope."""


class InMemoryMemoryService(MemoryService):
    """Process-local memory engine suitable for development and tests."""

    def __init__(self) -> None:
        """Initialize empty memory buckets."""
        self._records: dict[str, list[MemoryRecord]] = defaultdict(list)

    async def save(self, user_id: str, scope: str, content: str) -> MemoryRecord:
        """Persist a memory item in process memory."""
        record = MemoryRecord(
            id=str(uuid4()),
            user_id=user_id,
            scope=scope,
            content=content,
            created_at=datetime.now(UTC),
        )
        self._records[user_id].append(record)
        return record

    async def search(self, user_id: str, query: str, limit: int = 10) -> list[MemoryRecord]:
        """Return memories ranked by simple term overlap until a vector backend is configured."""
        terms = {term.lower() for term in query.split() if term.strip()}
        scored: list[MemoryRecord] = []
        for record in self._records[user_id]:
            content_terms = set(record.content.lower().split())
            relevance = len(terms & content_terms) / max(len(terms), 1)
            if relevance > 0:
                scored.append(
                    MemoryRecord(
                        id=record.id,
                        user_id=record.user_id,
                        scope=record.scope,
                        content=record.content,
                        created_at=record.created_at,
                        relevance=relevance,
                    )
                )
        return sorted(scored, key=lambda item: item.relevance, reverse=True)[:limit]

    async def retrieve(self, user_id: str, scope: str, limit: int = 20) -> list[MemoryRecord]:
        """Retrieve recent memories by scope."""
        scoped = [record for record in self._records[user_id] if record.scope == scope]
        return sorted(scoped, key=lambda item: item.created_at, reverse=True)[:limit]

    async def summarize(self, user_id: str, scope: str) -> str:
        """Create a compact deterministic summary of recent scoped memories."""
        records = await self.retrieve(user_id, scope, limit=10)
        if not records:
            return "No prior memory is available."
        return "\n".join(f"- {record.content[:500]}" for record in records)


_memory_service = InMemoryMemoryService()


def get_memory_service() -> MemoryService:
    """Return the configured memory service implementation."""
    return _memory_service
