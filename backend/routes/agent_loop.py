"""Agent loop — receives from Gemini Live API, forwards to frontend.

Simple loop: receive → process → forward. No dispatch, no phases, no nudges.
The agent is autonomous — this loop just bridges Live API and WebSocket.
"""

import asyncio
import base64
import json
import logging

from fastapi import WebSocket

from models.session import Session
from services.tool_executor import ToolExecutor

logger = logging.getLogger("brand-agent")

# No _SILENCE_FALLBACK_SEC needed anymore


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

                    # Turn complete
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

                    # Clear BEFORE signaling frontend — prevents race condition where
                    # frontend sends audio_playback_done before we clear, causing a
                    # 30-second timeout in delayed_response.
                    session.audio_playback_event.clear()

                    # Break the Frontend-Backend Deadlock:
                    # The frontend event queue waits for `agent_turn_complete` to flush its events
                    # and eventually send the `audio_playback_done` signal back to the server.
                    # BUT the Live API never sends `turn_complete` while waiting for a tool response!
                    # So we manually signal the frontend that the audio generation phase of this turn is complete
                    # the moment we receive the tool call, allowing the frontend to flush and unlock the backend.
                    await send_json(ws, {
                        "type": "agent_turn_complete",
                        "canvas": session.canvas.snapshot(),
                    })

                    for fc in message.tool_call.function_calls:
                        # Notify frontend of tool invocation
                        await send_json(ws, {
                            "type": "tool_invoked",
                            "tool": fc.name,
                            "args": dict(fc.args) if fc.args else {},
                        })

                        # Execute tool (updates canvas internally)
                        fn_response, frontend_events = await tool_executor.execute(
                            session, fc,
                        )
                        all_responses.append(fn_response)
                        all_events.extend(frontend_events)
                        tool_names.append(fc.name)

                    # Send all frontend events
                    for event in all_events:
                        await send_json(ws, event)

                    # CRITICAL FIX for Audio Truncation (Dynamic Wait without blocking):
                    # We must NOT send the tool response back to the Live API until the frontend 
                    # has completely finished playing the agent's audio for the current turn.
                    # HOWEVER, we cannot `await` it here directly, because that blocks this `receive()`
                    # generator, starving the frontend of the remaining audio chunks!
                    # Therefore, we spawn a background task to wait and send the response.
                    async def delayed_response(responses, names) -> None:
                        logger.info(f"[{session.id}] Waiting for frontend audio_playback_done before sending tool response...")
                        try:
                            await asyncio.wait_for(session.audio_playback_event.wait(), timeout=30.0)
                            logger.info(f"[{session.id}] Audio playback finished, proceeding with tool response.")
                        except asyncio.TimeoutError:
                            logger.warning(f"[{session.id}] Timeout waiting for audio_playback_done. Proceeding anyway.")
                        # Clear immediately so the next tool call's delayed_response must wait fresh.
                        session.audio_playback_event.clear()

                        # Return ALL tool results to Live API in one batch.
                        # Canvas context is embedded in each FunctionResponse.response
                        # by tool_executor — no separate send_client_content needed.
                        # Per Live API docs: send_client_content is for conversation
                        # history only, not new messages. Using it after send_tool_response
                        # acts as a second trigger and causes duplicate tool calls.
                        await live_session.send_tool_response(
                            function_responses=responses,
                        )
                        logger.info(f"[{session.id}] Batch tool response | Tools: {names}")
                    
                    # Fire and forget
                    asyncio.create_task(delayed_response(all_responses, tool_names))

                    # The Live API will autonomously generate the next turn 
                    # based on the tool responses.
                    # We NO LONGER force-inject a client context here because 
                    # calling an explicit 'send_client_content' acts as a barge-in,
                    # interrupting any slower audio chunks the server is still sending 
                    # from the sentence immediately preceding this tool call.

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
