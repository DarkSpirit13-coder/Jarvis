"""WebSocket routes for real-time JARVIS sessions."""

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.logging import get_logger
from app.services.conversation_manager import get_conversation_manager

logger = get_logger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/conversations/{conversation_id}")
async def conversation_socket(websocket: WebSocket, conversation_id: str) -> None:
    """Maintain a real-time streaming conversation channel with cancellation."""
    await websocket.accept()
    await websocket.send_json({"type": "connected", "conversation_id": conversation_id})
    manager = get_conversation_manager()
    active_task = None
    try:
        while True:
            message = json.loads(await websocket.receive_text())
            if message.get("type") == "cancel" and active_task:
                active_task.cancel()
                await websocket.send_json({"type": "cancelled"})
                continue
            user_id = message.get("user_id", "anonymous")
            content = message.get("message", "")
            if not content:
                await websocket.send_json({"type": "error", "error": "message is required"})
                continue

            async def stream_turn(turn_user_id: str = user_id, turn_content: str = content) -> None:
                """Stream one assistant turn to the websocket."""
                try:
                    async for token in manager.stream_response(turn_user_id, conversation_id, turn_content):
                        await websocket.send_json({"type": "token", "token": token})
                    await websocket.send_json({"type": "done"})
                except Exception as exc:
                    logger.exception("websocket_stream_error", extra={"conversation_id": conversation_id})
                    await websocket.send_json({"type": "error", "error": str(exc)})

            active_task = asyncio.create_task(stream_turn())
    except WebSocketDisconnect:
        if active_task:
            active_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await active_task
        logger.info("websocket_disconnected", extra={"conversation_id": conversation_id})
