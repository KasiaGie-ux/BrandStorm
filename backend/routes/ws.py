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

            async def tool_watchdog():
                """Independent task — polls every second, nudges agent if silent after tool."""
                from google.genai import types as _t
                from models.canvas import ElementStatus
                from services.context_injector import build_context_message as _build_ctx

                _CANVAS_AWARE_NUDGE = (
                    "Check [CANVAS STATE] above. Find the first STALE or EMPTY element in the pipeline "
                    "(name → tagline → palette → fonts → logo → hero → instagram → voiceover). "
                    "Do NOT ask about elements already READY. "
                    "Say ONE sentence reacting to the result, then ask about that specific next element. STOP. WAIT."
                )
                _NUDGE_PER_TOOL = {
                    "set_brand_identity": _CANVAS_AWARE_NUDGE,
                    "set_palette":        _CANVAS_AWARE_NUDGE,
                    "set_fonts":          _CANVAS_AWARE_NUDGE,
                    "generate_image": (
                        "The image is ready. React in ONE sentence. "
                        "Ask: 'What do you think?' or 'Happy with it?' STOP. WAIT. "
                        "DO NOT call any tool. DO NOT generate the next image. "
                        "Wait for the user to respond."
                    ),
                    "propose_names":      "Narrate each name: ONE sentence per name. End third with 'That's my pick.' STOP. WAIT.",
                }
                _DEFAULT_NUDGE = "ONE sentence reacting. Ask user for feedback. STOP. WAIT."

                try:
                    while True:
                        await asyncio.sleep(1)
                        if session.pending_tool_response is None:
                            continue
                        tools = session.pending_tool_response
                        timeout = 5.0
                        elapsed = 0.0
                        while elapsed < timeout:
                            await asyncio.sleep(1)
                            elapsed += 1.0
                            if session.pending_tool_response is None:
                                break
                        if session.pending_tool_response is None:
                            continue
                        tool_name = tools[0] if tools else ""
                        # These tools handle their own flow — watchdog must NOT nudge.
                        if tool_name in ("generate_voiceover", "propose_names", "finalize_brand_kit"):
                            session.pending_tool_response = None
                            logger.info(f"[{session_id}] Watchdog skipped for {tool_name}")
                            continue
                        nudge_instruction = _NUDGE_PER_TOOL.get(tool_name, _DEFAULT_NUDGE)
                        nudge_text = _build_ctx(
                            session,
                            trigger="tool_result",
                            details=f"Tool '{tool_name}' result delivered. {nudge_instruction}",
                        )
                        logger.info(
                            f"[{session_id}] Tool watchdog fired | Tool: {tool_name} | Elapsed: {timeout}s"
                        )
                        session.pending_tool_response = None
                        try:
                            await live_session.send_client_content(
                                turns=[_t.Content(
                                    role="user",
                                    parts=[_t.Part.from_text(text=nudge_text)],
                                )],
                                turn_complete=True,
                            )
                        except Exception as ne:
                            logger.warning(f"[{session_id}] Watchdog nudge failed: {ne}")
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"[{session_id}] Tool watchdog error: {e}")

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
            watchdog_task = asyncio.create_task(
                tool_watchdog(),
                name="tool_watchdog",
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
            watchdog_task.cancel()
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
