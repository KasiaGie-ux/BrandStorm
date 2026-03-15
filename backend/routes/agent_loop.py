"""Agent loop — receives from Gemini Live API, forwards to frontend.

Simple loop: receive → process → forward. No dispatch, no phases, no nudges.
The agent is autonomous — this loop just bridges Live API and WebSocket.
"""

import asyncio
import base64
import logging

from fastapi import WebSocket
from google.genai import types

from config import SESSION_TIMEOUT_SEC
from models.session import Session
from services.tool_executor import ToolExecutor

logger = logging.getLogger("brand-agent")



async def send_json(ws: WebSocket, data: dict) -> None:
    """Send JSON to frontend WebSocket, silently ignoring closed connections."""
    try:
        await ws.send_json(data)
    except Exception:
        pass



async def agent_loop(
    ws: WebSocket,
    live_session,
    session: Session,
    tool_executor: ToolExecutor,
) -> None:
    """Receive Live API messages and forward to frontend.

    The agent is autonomous. This loop:
    1. Receives audio/text/tool_call from Live API
    2. Forwards audio/text to frontend
    3. Executes tool calls and returns results
    4. Injects updated canvas context after tool results
    """


    try:
        while True:
            async for message in live_session.receive():
                # -- Server content: audio, text, transcription --
                if message.server_content:
                    sc = message.server_content

                    # Barge-in: agent was interrupted by user
                    if getattr(sc, "interrupted", False):
                        await send_json(ws, {"type": "agent_audio_interrupted"})
                        continue

                    # Forward audio chunks
                    if sc.model_turn and sc.model_turn.parts:
                        for part in sc.model_turn.parts:
                            if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
                                await send_json(ws, {
                                    "type": "agent_audio",
                                    "data": base64.b64encode(part.inline_data.data).decode(),
                                    "mime_type": part.inline_data.mime_type,
                                })

                    # Input transcription (user speech)
                    if getattr(sc, "input_transcription", None):
                        text = getattr(sc.input_transcription, "text", "")
                        if text and text.strip():
                            session.add_transcript("user", text.strip())
                            await send_json(ws, {"type": "user_voice_text", "text": text.strip()})

                    # Output transcription (agent speech)
                    if getattr(sc, "output_transcription", None):
                        text = getattr(sc.output_transcription, "text", "")
                        if text:
                            await send_json(ws, {
                                "type": "agent_text",
                                "text": text,
                                "partial": not getattr(sc, "turn_complete", False),
                            })
                            # Clear watchdog flag — agent is speaking
                            if text.strip() and session.pending_tool_response is not None:
                                logger.info(
                                    f"[{session.id}] Watchdog cleared — agent spoke: '{text[:40]}'"
                                )
                                session.pending_tool_response = None

                    # Turn complete — always send agent_turn_complete
                    if getattr(sc, "turn_complete", False):
                        await send_json(ws, {
                            "type": "agent_turn_complete",
                            "canvas": session.canvas.snapshot(),
                        })

                # -- Tool calls from agent --
                if message.tool_call:
                    all_responses = []
                    all_events = []
                    tool_names = []

                    for fc in message.tool_call.function_calls:
                        await send_json(ws, {
                            "type": "tool_invoked",
                            "tool": fc.name,
                            "args": dict(fc.args) if fc.args else {},
                        })

                        # For long-running tools (image generation), send silent PCM
                        # chunks every 8s to keep the Live API session alive.
                        # 480 bytes of silence = 15ms at 16kHz 16-bit mono — below VAD threshold.
                        _LONG_RUNNING = {"generate_image", "generate_voiceover"}
                        if fc.name in _LONG_RUNNING:
                            _SILENCE = b"\x00" * 480
                            execute_task = asyncio.create_task(
                                tool_executor.execute(session, fc)
                            )
                            while not execute_task.done():
                                try:
                                    await asyncio.wait_for(
                                        asyncio.shield(execute_task), timeout=8.0
                                    )
                                except asyncio.TimeoutError:
                                    try:
                                        await live_session.send_realtime_input(
                                            audio=types.Blob(
                                                data=_SILENCE,
                                                mime_type="audio/pcm;rate=16000",
                                            )
                                        )
                                        logger.debug(
                                            f"[{session.id}] Live API keepalive | Tool: {fc.name}"
                                        )
                                    except Exception as ke:
                                        logger.warning(
                                            f"[{session.id}] Keepalive failed: {ke}"
                                        )
                            fn_response, frontend_events = execute_task.result()
                        else:
                            fn_response, frontend_events = await tool_executor.execute(
                                session, fc,
                            )

                        all_responses.append(fn_response)
                        all_events.extend(frontend_events)
                        tool_names.append(fc.name)

                    for event in all_events:
                        await send_json(ws, event)

                    try:
                        await live_session.send_tool_response(
                            function_responses=all_responses,
                        )
                    except Exception as tre:
                        logger.error(f"[{session.id}] send_tool_response failed: {tre}")
                        raise
                    logger.info(f"[{session.id}] Batch tool response | Tools: {tool_names}")

                    # Mark pending — tool_watchdog (in ws.py) will nudge if agent stays silent
                    session.pending_tool_response = tool_names[:]
                    # Clear next-step dedup guard — tool fired, canvas state will change
                    session.pending_next_step = None
                    session.pending_next_step_canvas_key = None
                    logger.info(f"[{session.id}] Watchdog armed | Tools: {tool_names}")


        # If we reach here the Live API stream ended (server closed it)
        logger.warning(f"[{session.id}] Live API stream ended (receive generator exhausted)")

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[{session.id}] agent_loop error: {e}")
        await send_json(ws, {"type": "error", "message": str(e)})
        raise
    finally:
        pass
