"""Receive loop — forwards frontend messages to Gemini Live API.

Simple: receive from WebSocket → inject canvas context → send to Live API.
No name detection, no signal analysis, no feedback gates.
The agent handles all interpretation through its own reasoning.
"""

import base64
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect
from google.genai import types

from models.session import Session
from services.context_injector import build_context_message
from services.gemini_live import image_bytes_to_part

logger = logging.getLogger("brand-agent")


async def receive_loop(
    ws: WebSocket,
    live_session,
    session: Session,
) -> None:
    """Receive messages from frontend and forward to Live API with canvas context."""
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(f"[{session.id}] Malformed JSON from frontend, ignoring")
                continue
            msg_type = msg.get("type")

            if msg_type == "text_input":
                text = msg.get("text", "").strip()
                if not text:
                    continue
                session.add_transcript("user", text)

                # Inject canvas context with the user's message
                context = build_context_message(
                    session,
                    trigger="user_message",
                    details=text,
                )
                await live_session.send_client_content(
                    turns=[types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=context)],
                    )],
                    turn_complete=True,
                )

            elif msg_type == "audio_chunk":
                audio_data = msg.get("data", "")
                if audio_data:
                    audio_bytes = base64.b64decode(audio_data)
                    await live_session.send_realtime_input(
                        audio=types.Blob(
                            data=audio_bytes,
                            mime_type="audio/pcm;rate=16000",
                        ),
                    )

            elif msg_type == "image_upload":
                image_data = msg.get("data", "")
                mime_type = msg.get("mime_type", "image/jpeg")
                context_text = msg.get("context", "")

                if not image_data:
                    continue

                image_bytes = base64.b64decode(image_data)
                session.product_image_bytes = image_bytes
                session.product_image_mime = mime_type

                logger.info(
                    f"[{session.id}] Image upload | Size: {len(image_bytes)} bytes | "
                    f"MIME: {mime_type}"
                )

                canvas_context = build_context_message(
                    session,
                    trigger="session_start",
                    details=f"User uploaded a product image. Context: {context_text}\nCRITICAL: Execute your OPENING SEQUENCE now. Then STOP immediately." if context_text
                            else "User uploaded a product image. CRITICAL: Execute your OPENING SEQUENCE now. Then STOP immediately.",
                )

                # Send image + context to Live API
                image_part = image_bytes_to_part(image_bytes, mime_type)
                await live_session.send_client_content(
                    turns=[types.Content(
                        role="user",
                        parts=[image_part, types.Part.from_text(text=canvas_context)],
                    )],
                    turn_complete=True,
                )

            elif msg_type == "voiceover_playback_done":
                context = build_context_message(
                    session,
                    trigger="voiceover_playback_complete",
                    details="The brand story narration has finished playing. You may finalize the brand kit.",
                )
                await live_session.send_client_content(
                    turns=[types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=context)],
                    )],
                    turn_complete=True,
                )

            elif msg_type == "audio_playback_done":
                # Frontend finished playing agent audio AND rendering queued visual events.
                # Signal agent_loop that it is safe to send block-level tool responses,
                # preventing barge-in aborts.
                logger.info(f"[{session.id}] Received audio_playback_done")
                session.audio_playback_event.set()

            # Ignore ping, keepalive, and unknown message types

    except WebSocketDisconnect:
        logger.info(f"[{session.id}] WebSocket disconnected")
    except Exception as e:
        logger.error(f"[{session.id}] receive_loop error: {e}")
