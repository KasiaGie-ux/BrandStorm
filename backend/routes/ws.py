"""WebSocket endpoint /ws/{session_id}.

Handles connection lifecycle. Event loops are in ws_loops.py.
Orchestrates: frontend <-> backend <-> Gemini Live API.
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket

from config import LIVE_API_MODEL
from services import brand_state
from services.gemini_live import build_live_config, create_client
from services.image_generator import ImageGenerator
from services.pregen import PreGenerator
from services.storage import StorageService
from services.tool_executor import ToolExecutor

from routes.ws_loops import agent_loop, receive_loop, send_json

logger = logging.getLogger("brand-agent")
router = APIRouter()


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(ws: WebSocket, session_id: str):
    """Main WebSocket handler — bridges frontend and Gemini Live API."""
    await ws.accept()
    logger.info(f"[{session_id}] Phase: INIT | Action: websocket_connected")

    session = brand_state.create_session(session_id)
    client = create_client()
    storage = StorageService()
    image_gen = ImageGenerator(client)
    pregen = PreGenerator(image_gen, storage)
    tool_executor = ToolExecutor(image_gen, storage, pregen)

    try:
        live_config = build_live_config()
        tool_count = len(live_config.tools[0].function_declarations) if live_config.tools else 0
        logger.info(
            f"[{session_id}] Phase: INIT | Action: connecting_live_api | "
            f"Model: {LIVE_API_MODEL} | Tools in config: {tool_count}"
        )
        async with client.aio.live.connect(
            model=LIVE_API_MODEL,
            config=live_config,
        ) as live_session:
            logger.info(
                f"[{session_id}] Phase: INIT | Action: live_api_connected | "
                f"Model: {LIVE_API_MODEL} | Tools: {tool_count}"
            )

            # Send session_ready immediately — some Live API models
            # (e.g. gemini-2.0-flash-live-preview-04-09) do NOT emit
            # setup_complete, so we can't wait for it.
            await send_json(ws, {"type": "session_ready"})
            logger.info(
                f"[{session_id}] Phase: INIT | Action: session_ready_sent"
            )

            async def keepalive_loop():
                """Send periodic pings to prevent WebSocket idle timeout."""
                try:
                    while True:
                        await asyncio.sleep(15)
                        await ws.send_json({"type": "ping"})
                except Exception:
                    pass  # WS closed, exit silently

            receive_task = asyncio.create_task(
                receive_loop(ws, live_session, session),
                name="receive",
            )
            agent_task = asyncio.create_task(
                agent_loop(ws, live_session, session, tool_executor, pregen),
                name="agent",
            )
            keepalive_task = asyncio.create_task(
                keepalive_loop(),
                name="keepalive",
            )

            done, pending = await asyncio.wait(
                [receive_task, agent_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            keepalive_task.cancel()
            for task in done:
                try:
                    exc = task.exception()
                except asyncio.CancelledError:
                    exc = None
                if exc:
                    logger.error(
                        f"[{session_id}] Task '{task.get_name()}' failed: {exc}"
                    )
                else:
                    logger.info(
                        f"[{session_id}] Task '{task.get_name()}' completed"
                    )
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    except Exception as e:
        logger.error(
            f"[{session_id}] Phase: {session.phase.value} | "
            f"Action: live_api_connection_failed | Error: {e}"
        )
        await send_json(ws, {"type": "error", "message": str(e)})
    finally:
        # Cancel background pregen/voiceover tasks so they don't outlive the WS connection
        for task_name, task in list(session.pregen_tasks.items()):
            if not task.done():
                task.cancel()
                logger.info(f"[{session_id}] Action: cancelled_pregen_task | Task: {task_name}")
        brand_state.remove_session(session_id)
        logger.info(f"[{session_id}] Action: session_ended")
