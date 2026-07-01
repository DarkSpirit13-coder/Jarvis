"""Conversation orchestration service for JARVIS intelligence."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.agents.planner import LLMPlannerAgent, PlannerContext, PlannerOutput
from app.core.logging import get_logger
from app.llm.factory import get_llm_provider
from app.llm.provider import BaseLLMProvider, LLMMessage
from app.memory.service import MemoryService, get_memory_service
from app.services.execution_engine import ExecutionEngine, ExecutionResult
from app.tools.factory import get_tool_registry
from app.tools.registry import ToolRegistry
from app.tools.router import RoutedToolResult, ToolRouter

logger = get_logger(__name__)


@dataclass(frozen=True)
class ConversationTurn:
    """A normalized conversation message loaded from memory."""

    role: str
    content: str


@dataclass(frozen=True)
class ConversationResponse:
    """Structured response returned by the conversation manager."""

    conversation_id: str
    response: str
    plan: PlannerOutput
    tool_results: list[RoutedToolResult]
    execution_result: ExecutionResult
    relevant_memories: list[str]
    history: list[ConversationTurn]
    usage: dict[str, int] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of the response."""
        return {
            "conversation_id": self.conversation_id,
            "response": self.response,
            "plan": self.plan.model_dump(),
            "tool_results": [result.__dict__ for result in self.tool_results],
            "execution_result": self.execution_result.model_dump(),
            "relevant_memories": self.relevant_memories,
            "history": [turn.__dict__ for turn in self.history],
            "usage": self.usage,
        }


class ConversationManager:
    """Coordinates memory retrieval, planning, tools, final generation, and persistence."""

    def __init__(
        self,
        llm: BaseLLMProvider,
        memory_service: MemoryService,
        planner: LLMPlannerAgent,
        tool_registry: ToolRegistry,
        tool_router: ToolRouter,
        execution_engine: ExecutionEngine | None = None,
    ) -> None:
        """Create a conversation manager with explicit dependencies."""
        self.llm = llm
        self.memory_service = memory_service
        self.planner = planner
        self.tool_registry = tool_registry
        self.tool_router = tool_router
        self.execution_engine = execution_engine or ExecutionEngine(tool_router)

    async def respond(self, user_id: str, conversation_id: str, content: str) -> str:
        """Generate and store a final response for a user message."""
        result = await self.handle_message(user_id, conversation_id, content)
        return result.response

    async def handle_message(self, user_id: str, conversation_id: str, content: str) -> ConversationResponse:
        """Process a user message and return a structured conversation result."""
        started = time.perf_counter()
        plan, execution_result, messages, relevant_memories, history = await self._prepare(
            user_id, conversation_id, content
        )
        tool_results = execution_result.tool_outputs
        response = await self.llm.complete(
            messages, tools=[tool.to_openai_tool() for tool in self.tool_registry.list_tools()]
        )
        await self._persist(user_id, conversation_id, content, response.content, plan, tool_results)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "conversation_response",
            extra={
                "conversation_id": conversation_id,
                "latency_ms": latency_ms,
                "memory_count": len(relevant_memories),
                "history_count": len(history),
                "tool_count": len(tool_results),
                "execution_status": execution_result.status.value,
                "usage": response.usage,
            },
        )
        return ConversationResponse(
            conversation_id=conversation_id,
            response=response.content,
            plan=plan,
            tool_results=tool_results,
            execution_result=execution_result,
            relevant_memories=relevant_memories,
            history=history,
            usage=response.usage,
        )

    async def stream_response(self, user_id: str, conversation_id: str, content: str) -> AsyncIterator[str]:
        """Stream a final response while storing the complete assistant message."""
        plan, execution_result, messages, _, _ = await self._prepare(user_id, conversation_id, content)
        tool_results = execution_result.tool_outputs
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
    ) -> tuple[PlannerOutput, ExecutionResult, list[LLMMessage], list[str], list[ConversationTurn]]:
        """Load memory, ask the planner, execute tools, and build final LLM messages."""
        scope = f"conversation:{conversation_id}"
        history = await self._load_history(user_id, scope)
        memories = await self.memory_service.search(user_id, content, limit=8)
        relevant_memories = [record.content for record in memories]
        await self.memory_service.save(user_id, scope, f"user: {content}")
        plan = await self.planner.plan(
            content,
            PlannerContext(user_id=user_id, conversation_id=conversation_id, memory=relevant_memories),
        )
        logger.info(
            "conversation_plan_ready",
            extra={
                "conversation_id": conversation_id,
                "goal": plan.goal,
                "tool_count": len(plan.tools),
                "memory_count": len(relevant_memories),
                "history_count": len(history),
            },
        )
        execution_result = await self.execution_engine.execute(plan)
        tool_results = execution_result.tool_outputs
        messages = self._messages(content, plan, relevant_memories, history, tool_results)
        return plan, execution_result, messages, relevant_memories, history

    def _messages(
        self,
        content: str,
        plan: PlannerOutput,
        memories: list[str],
        history: list[ConversationTurn],
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
            "conversation_history": [turn.__dict__ for turn in history],
            "tool_results": [result.__dict__ for result in tool_results],
        }
        return [
            LLMMessage(role="system", content=system),
            LLMMessage(role="system", content=json.dumps(context, default=str)),
            LLMMessage(role="user", content=content),
        ]

    async def _load_history(self, user_id: str, scope: str) -> list[ConversationTurn]:
        """Load previous conversation history from memory."""
        records = await self.memory_service.retrieve(user_id, scope, limit=20)
        turns: list[ConversationTurn] = []
        for record in reversed(records):
            role, separator, body = record.content.partition(": ")
            if separator and role in {"user", "assistant"}:
                turns.append(ConversationTurn(role=role, content=body))
        return turns

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
    execution_engine = ExecutionEngine(tool_router=router)
    return ConversationManager(
        llm=llm,
        memory_service=get_memory_service(),
        planner=planner,
        tool_registry=registry,
        tool_router=router,
        execution_engine=execution_engine,
    )
