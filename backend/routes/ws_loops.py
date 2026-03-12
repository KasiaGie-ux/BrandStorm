"""WebSocket event loops — receive (frontend→Live API) and agent (Live API→frontend).

Extracted from ws.py to keep files under 300 lines.
"""

import asyncio
import base64
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect
from google.genai import types

from config import SESSION_TIMEOUT_SEC
from models.session import AgentPhase, Session
from services import brand_state
from services.gemini_live import image_bytes_to_part
from services.text_parser import parse_agent_text
from services.tool_executor import ToolExecutor

logger = logging.getLogger("brand-agent")


async def send_json(ws: WebSocket, data: dict) -> None:
    """Send JSON to frontend, silently ignore if closed."""
    try:
        await ws.send_json(data)
        if data.get("type") in ("image_generated", "palette_ready", "generation_complete"):
            logger.info(f"[WS→FE] Sent {data['type']} | keys={list(data.keys())}")
    except Exception as e:
        logger.warning(f"WebSocket send failed: {e} | type={data.get('type')}")


async def receive_loop(
    ws: WebSocket,
    live_session: object,
    session: Session,
) -> None:
    """Receive messages from frontend and forward to Live API."""
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "text_input":
                text = msg.get("text", "")
                logger.info(
                    f"[{session.id}] Phase: {session.phase.value} | "
                    f"Action: text_input_received | Text: {text[:80]}"
                )
                session.add_transcript("user", text)
                await live_session.send_client_content(
                    turns=[types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=text)],
                    )],
                    turn_complete=True,
                )
                logger.info(
                    f"[{session.id}] Phase: {session.phase.value} | "
                    f"Action: text_forwarded_to_live_api"
                )

            elif msg_type == "audio_chunk":
                audio_b64 = msg.get("data", "")
                audio_bytes = base64.b64decode(audio_b64)
                await live_session.send_realtime_input(
                    audio=types.Blob(data=audio_bytes, mime_type="audio/pcm;rate=16000"),
                )

            elif msg_type == "image_upload":
                image_b64 = msg.get("data", "")
                mime_type = msg.get("mime_type", "image/jpeg")

                if not image_b64:
                    logger.error(
                        f"[{session.id}] Phase: {session.phase.value} | "
                        f"Action: image_upload_empty | Error: base64 data field is empty"
                    )
                    await send_json(ws, {
                        "type": "error",
                        "message": "Image upload failed: no image data received.",
                    })
                    continue

                # Strip data-URL prefix if frontend accidentally includes it
                if image_b64.startswith("data:"):
                    logger.warning(
                        f"[{session.id}] Phase: {session.phase.value} | "
                        f"Action: stripping_data_url_prefix | "
                        f"Prefix: {image_b64[:50]}"
                    )
                    # data:image/jpeg;base64,/9j/4AAQ...
                    _, image_b64 = image_b64.split(",", 1)

                image_bytes = base64.b64decode(image_b64)
                header_hex = image_bytes[:8].hex()
                logger.info(
                    f"[{session.id}] Phase: {session.phase.value} | "
                    f"Action: image_upload_received | "
                    f"Size: {len(image_bytes)} bytes ({len(image_bytes) / 1024:.0f}KB) | "
                    f"MIME: {mime_type} | Base64 length: {len(image_b64)} | "
                    f"Header: {header_hex}"
                )

                if len(image_bytes) < 100:
                    logger.error(
                        f"[{session.id}] Phase: {session.phase.value} | "
                        f"Action: image_too_small | Size: {len(image_bytes)} bytes | "
                        f"Error: decoded image suspiciously small, likely corrupt"
                    )
                    await send_json(ws, {
                        "type": "error",
                        "message": "Image upload failed: image data appears corrupt.",
                    })
                    continue

                session.product_image_bytes = image_bytes
                session.product_image_mime = mime_type

                image_part = image_bytes_to_part(image_bytes, mime_type)
                user_context = msg.get("context", "")
                prompt = (
                    "Here is the product photo. Start immediately — analyze what you see, "
                    "propose your creative directions, recommend your top pick, then start "
                    "generating the full brand kit. Go."
                )
                if user_context:
                    prompt += f"\n\nAdditional context from the client: {user_context}"

                await live_session.send_client_content(
                    turns=[types.Content(
                        role="user",
                        parts=[image_part, types.Part.from_text(text=prompt)],
                    )],
                    turn_complete=True,
                )
                session.add_transcript("user", f"[product image uploaded] {prompt}")
                brand_state.transition_phase(session, AgentPhase.ANALYZING)
                logger.info(
                    f"[{session.id}] Phase: {session.phase.value} | "
                    f"Action: image_forwarded_to_live_api | "
                    f"Image: {len(image_bytes)} bytes | MIME: {mime_type}"
                )

            elif msg_type == "stop_session":
                logger.info(
                    f"[{session.id}] Phase: {session.phase.value} | "
                    f"Action: stop_requested_by_client"
                )
                await send_json(ws, {"type": "session_stopped"})
                return  # Exit receive_loop cleanly, triggers task cancellation

            else:
                logger.warning(
                    f"[{session.id}] Unknown message type: {msg_type}"
                )

    except WebSocketDisconnect:
        logger.info(
            f"[{session.id}] Phase: {session.phase.value} | Action: client_disconnected"
        )
    except Exception as e:
        logger.error(
            f"[{session.id}] Phase: {session.phase.value} | "
            f"Action: receive_loop_error | Error: {e}"
        )


async def agent_loop(
    ws: WebSocket,
    live_session: object,
    session: Session,
    tool_executor: ToolExecutor,
) -> None:
    """Receive messages from Live API and forward to frontend.

    Live API's session.receive() yields messages for ONE turn only.
    After turn_complete the iterator ends. We must call receive() again
    in an outer loop for multi-turn conversations.

    Only exit the outer loop on: finalize_brand_kit, session timeout,
    or explicit error.
    """
    agent_text_buffer: list[str] = []
    seen_event_types: set[str] = set()  # dedup across turns
    msg_count = 0
    turn_count = 0
    session_active = True

    try:
        async with asyncio.timeout(SESSION_TIMEOUT_SEC):
            logger.info(
                f"[{session.id}] Phase: {session.phase.value} | "
                f"Action: agent_loop_started | Timeout: {SESSION_TIMEOUT_SEC}s"
            )

            while session_active:
                turn_count += 1
                logger.info(
                    f"[{session.id}] Phase: {session.phase.value} | "
                    f"Action: receive_turn_start | Turn: {turn_count}"
                )

                async for message in live_session.receive():
                    msg_count += 1

                    logger.info(
                        f"[{session.id}] Raw msg #{msg_count} | "
                        f"server_content={message.server_content is not None} | "
                        f"tool_call={message.tool_call is not None} | "
                        f"setup_complete={getattr(message, 'setup_complete', None)}"
                    )

                    # Server content: audio, text, transcription
                    if message.server_content:
                        sc = message.server_content
                        has_turn = sc.model_turn is not None
                        has_parts = has_turn and sc.model_turn.parts
                        has_transcript = sc.output_transcription and sc.output_transcription.text
                        logger.info(
                            f"[{session.id}] ServerContent | "
                            f"model_turn={has_turn} | "
                            f"parts={len(sc.model_turn.parts) if has_parts else 0} | "
                            f"turn_complete={sc.turn_complete} | "
                            f"transcription={bool(has_transcript)}"
                        )

                        if sc.model_turn and sc.model_turn.parts:
                            for part in sc.model_turn.parts:
                                if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
                                    await send_json(ws, {
                                        "type": "agent_audio",
                                        "data": base64.b64encode(part.inline_data.data).decode(),
                                        "mime_type": part.inline_data.mime_type,
                                    })
                                elif hasattr(part, "text") and part.text:
                                    agent_text_buffer.append(part.text)
                                    await send_json(ws, {
                                        "type": "agent_text",
                                        "text": part.text,
                                        "partial": True,
                                    })

                        if sc.output_transcription and sc.output_transcription.text:
                            text = sc.output_transcription.text
                            agent_text_buffer.append(text)
                            await send_json(ws, {
                                "type": "agent_text",
                                "text": text,
                                "partial": True,
                            })

                        if sc.turn_complete:
                            full_text = "".join(agent_text_buffer)
                            if full_text:
                                session.add_transcript("agent", full_text)

                                # Parse structured tags and emit typed events
                                structured_events, narration = parse_agent_text(
                                    full_text, seen_types=seen_event_types
                                )
                                for event in structured_events:
                                    await send_json(ws, event)

                                    # Store brand name on session if revealed
                                    if event["type"] == "brand_name_reveal" and event.get("name"):
                                        session.brand_name = event["name"]

                                    # Store palette on session if revealed
                                    if event["type"] == "palette_reveal" and event.get("colors"):
                                        session.palette = event["colors"]

                                # Send cleaned narration text (tags stripped)
                                if narration:
                                    await send_json(ws, {
                                        "type": "agent_narration",
                                        "text": narration,
                                    })

                                # Also send full text for backwards compat
                                await send_json(ws, {
                                    "type": "agent_text",
                                    "text": full_text,
                                    "partial": False,
                                })
                            agent_text_buffer.clear()

                            if session.phase == AgentPhase.ANALYZING:
                                brand_state.transition_phase(session, AgentPhase.PROPOSING)
                                brand_state.transition_phase(session, AgentPhase.AWAITING_INPUT)
                            elif session.phase == AgentPhase.GENERATING:
                                brand_state.transition_phase(session, AgentPhase.AWAITING_INPUT)

                            logger.info(
                                f"[{session.id}] Phase: {session.phase.value} | "
                                f"Action: agent_turn_complete | Turn: {turn_count} | "
                                f"Messages so far: {msg_count}"
                            )
                            await send_json(ws, {
                                "type": "agent_turn_complete",
                                "phase": session.phase.value,
                            })
                            break

                    # Tool calls from agent
                    if message.tool_call:
                        for fc in message.tool_call.function_calls:
                            buffered = "".join(agent_text_buffer)
                            if buffered:
                                session.add_transcript("agent", buffered)
                                # Parse structured events from pre-tool text
                                mid_events, mid_narration = parse_agent_text(
                                    buffered, seen_types=seen_event_types
                                )
                                for me in mid_events:
                                    await send_json(ws, me)
                                    if me.get("type") == "brand_name_reveal" and me.get("name"):
                                        session.brand_name = me["name"]
                                if mid_narration:
                                    await send_json(ws, {
                                        "type": "agent_narration",
                                        "text": mid_narration,
                                    })
                                agent_text_buffer.clear()

                            brand_state.infer_phase_from_tool(session, fc.name)
                            await send_json(ws, {
                                "type": "tool_invoked",
                                "tool": fc.name,
                                "args": dict(fc.args) if fc.args else {},
                                "phase": session.phase.value,
                            })

                            fn_response, event = await tool_executor.execute(session, fc)

                            if event:
                                await send_json(ws, event)

                            await live_session.send_tool_response(
                                function_responses=[fn_response]
                            )
                            logger.info(
                                f"[{session.id}] Phase: {session.phase.value} | "
                                f"Action: tool_response_sent | Tool: {fc.name}"
                            )

                            if fc.name == "finalize_brand_kit":
                                logger.info(
                                    f"[{session.id}] Phase: {session.phase.value} | "
                                    f"Action: finalize_complete | Ending agent loop"
                                )
                                session_active = False

                    if message.setup_complete:
                        logger.info(f"[{session.id}] Phase: INIT | Action: setup_complete (ignored, session_ready already sent)")

                else:
                    logger.warning(
                        f"[{session.id}] Phase: {session.phase.value} | "
                        f"Action: receive_stream_ended | Turn: {turn_count} | "
                        f"Messages: {msg_count}"
                    )

            logger.info(
                f"[{session.id}] Phase: {session.phase.value} | "
                f"Action: agent_loop_finished | Turns: {turn_count} | "
                f"Messages: {msg_count}"
            )

    except TimeoutError:
        logger.error(
            f"[{session.id}] Phase: {session.phase.value} | "
            f"Action: session_timeout | Timeout: {SESSION_TIMEOUT_SEC}s | "
            f"Turns: {turn_count} | Messages: {msg_count}"
        )
        await send_json(ws, {
            "type": "session_timeout",
            "message": f"Session timed out after {SESSION_TIMEOUT_SEC}s",
        })
    except Exception as e:
        logger.error(
            f"[{session.id}] Phase: {session.phase.value} | "
            f"Action: agent_loop_error | Error: {e} | "
            f"Turns: {turn_count} | Messages: {msg_count}"
        )
        await send_json(ws, {"type": "error", "message": str(e)})
