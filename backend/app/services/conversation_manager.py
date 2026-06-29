"""Conversation orchestration service for JARVIS intelligence."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator

from app.agents.planner import LLMPlannerAgent, PlannerContext, PlannerOutput
from app.core.logging import get_logger
from app.llm.factory import get_llm_provider
from app.llm.provider import BaseLLMProvider, LLMMessage
from app.memory.service import MemoryService, get_memory_service
from app.tools.factory import get_tool_registry
from app.tools.registry import ToolRegistry
from app.tools.router import RoutedToolResult, ToolRouter

logger = get_logger(__name__)


class ConversationManager:
    """Coordinates memory retrieval, planning, tools, final generation, and persistence."""

    def __init__(
        self,
        llm: BaseLLMProvider,
        memory_service: MemoryService,
        planner: LLMPlannerAgent,
        tool_registry: ToolRegistry,
        tool_router: ToolRouter,
    ) -> None:
        """Create a conversation manager with explicit dependencies."""
        self.llm = llm
        self.memory_service = memory_service
        self.planner = planner
        self.tool_registry = tool_registry
        self.tool_router = tool_router

    async def respond(self, user_id: str, conversation_id: str, content: str) -> str:
        """Generate and store a final response for a user message."""
        started = time.perf_counter()
        plan, tool_results, messages = await self._prepare(user_id, conversation_id, content)
        response = await self.llm.complete(
            messages, tools=[tool.to_openai_tool() for tool in self.tool_registry.list_tools()]
        )
        await self._persist(user_id, conversation_id, content, response.content, plan, tool_results)
        logger.info(
            "conversation_response",
            extra={"conversation_id": conversation_id, "latency_ms": round((time.perf_counter() - started) * 1000, 2)},
        )
        return response.content

    async def stream_response(self, user_id: str, conversation_id: str, content: str) -> AsyncIterator[str]:
        """Stream a final response while storing the complete assistant message."""
        plan, tool_results, messages = await self._prepare(user_id, conversation_id, content)
        chunks: list[str] = []
        async for token in self.llm.stream(
            messages, tools=[tool.to_openai_tool() for tool in self.tool_registry.list_tools()]
        ):
            chunks.append(token)
            yield token
        assistant = "".join(chunks)
        await self._persist(user_id, conversation_id, content, assistant, plan, tool_results)

    async def _prepare(
        self, user_id: str, conversation_id: str, content: str
    ) -> tuple[PlannerOutput, list[RoutedToolResult], list[LLMMessage]]:
        """Load memory, ask the planner, execute tools, and build final LLM messages."""
        await self.memory_service.save(user_id, f"conversation:{conversation_id}", f"user: {content}")
        memories = await self.memory_service.search(user_id, content, limit=8)
        memory_lines = [record.content for record in memories]
        plan = await self.planner.plan(
            content,
            PlannerContext(user_id=user_id, conversation_id=conversation_id, memory=memory_lines),
        )
        tool_results = await self.tool_router.execute_plan(plan)
        messages = self._messages(content, plan, memory_lines, tool_results)
        return plan, tool_results, messages

    def _messages(
        self,
        content: str,
        plan: PlannerOutput,
        memories: list[str],
        tool_results: list[RoutedToolResult],
    ) -> list[LLMMessage]:
        """Build final answer messages from memory, plan, and tool outputs."""
        system = (
            "You are JARVIS, an AI operating system. Answer the user directly, use tool results faithfully, "
            "state uncertainty when external systems fail, and never claim a tool ran when it did not."
        )
        context = {
            "plan": plan.model_dump(),
            "memory": memories,
            "tool_results": [result.__dict__ for result in tool_results],
        }
        return [
            LLMMessage(role="system", content=system),
            LLMMessage(role="system", content=json.dumps(context, default=str)),
            LLMMessage(role="user", content=content),
        ]

    async def _persist(
        self,
        user_id: str,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        plan: PlannerOutput,
        tool_results: list[RoutedToolResult],
    ) -> None:
        """Persist conversation memory and execution trace."""
        scope = f"conversation:{conversation_id}"
        await self.memory_service.save(user_id, scope, f"assistant: {assistant_message}")
        await self.memory_service.save(
            user_id,
            "long_term",
            json.dumps(
                {
                    "conversation_id": conversation_id,
                    "user": user_message,
                    "assistant": assistant_message,
                    "goal": plan.goal,
                    "tools": [result.name for result in tool_results],
                },
                default=str,
            ),
        )


def get_conversation_manager() -> ConversationManager:
    """Return a conversation manager dependency with configured services."""
    llm = get_llm_provider()
    registry = get_tool_registry()
    planner = LLMPlannerAgent(llm=llm, tool_registry=registry)
    router = ToolRouter(registry=registry)
    return ConversationManager(
        llm=llm,
        memory_service=get_memory_service(),
        planner=planner,
        tool_registry=registry,
        tool_router=router,
    )
