"""WebSocket endpoint /ws/{session_id}.

Handles connection lifecycle. Orchestrates: frontend <-> backend <-> Gemini Live API.
Clean architecture: no pregen, no dispatch, no nudges.
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket

from config import LIVE_API_MODEL
from services import brand_state
from services.gemini_live import build_live_config, create_client
from services.image_generator import ImageGenerator
from services.storage import StorageService
from services.tool_executor import ToolExecutor

from routes.agent_loop import agent_loop, send_json
from routes.receive_loop import receive_loop

logger = logging.getLogger("brand-agent")
router = APIRouter()


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(ws: WebSocket, session_id: str):
    """Main WebSocket handler — bridges frontend and Gemini Live API."""
    await ws.accept()
    logger.info(f"[{session_id}] WebSocket connected")

    session = brand_state.create_session(session_id)
    stop_event = brand_state.register_teardown_event(session_id)

    client = create_client()
    storage = StorageService()
    image_gen = ImageGenerator(client)
    tool_executor = ToolExecutor(image_gen, storage)

    try:
        live_config = build_live_config()
        logger.info(f"[{session_id}] Connecting to Live API | Model: {LIVE_API_MODEL}")

        async with client.aio.live.connect(
            model=LIVE_API_MODEL,
            config=live_config,
        ) as live_session:
            logger.info(f"[{session_id}] Live API connected")

            await send_json(ws, {"type": "session_ready"})

            async def keepalive_loop():
                try:
                    while True:
                        await asyncio.sleep(15)
                        await ws.send_json({"type": "ping"})
                except Exception:
                    pass

            receive_task = asyncio.create_task(
                receive_loop(ws, live_session, session),
                name="receive",
            )
            agent_task = asyncio.create_task(
                agent_loop(ws, live_session, session, tool_executor),
                name="agent",
            )
            keepalive_task = asyncio.create_task(
                keepalive_loop(),
                name="keepalive",
            )

            async def _stop_watcher():
                await stop_event.wait()
                logger.info(f"[{session_id}] Connection superseded")

            stop_task = asyncio.create_task(_stop_watcher(), name="stop_watcher")

            done, pending = await asyncio.wait(
                [receive_task, agent_task, stop_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            keepalive_task.cancel()
            for task in done:
                try:
                    exc = task.exception()
                except asyncio.CancelledError:
                    exc = None
                if exc:
                    logger.error(f"[{session_id}] Task '{task.get_name()}' failed: {exc}")
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    except Exception as e:
        logger.error(f"[{session_id}] Live API connection failed: {e}")
        await send_json(ws, {"type": "error", "message": str(e)})
    finally:
        for task_name, task in list(session.background_tasks.items()):
            if hasattr(task, 'done') and not task.done():
                task.cancel()
                logger.info(f"[{session_id}] Cancelled background task: {task_name}")
        brand_state.clear_teardown_event(session_id, stop_event)
        brand_state.remove_session(session_id)
        logger.info(f"[{session_id}] Session ended")
