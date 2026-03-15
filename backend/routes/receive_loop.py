"""Receive loop — forwards frontend messages to Gemini Live API.

Simple: receive from WebSocket → inject canvas context → send to Live API.
Positive affirmations ("yes", "ok", "tak") are enriched with a [NEXT STEP]
instruction derived from the current canvas state, so the agent knows exactly
which tool to call without having to guess.
"""

import base64
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect
from google.genai import types

from models.canvas import ElementStatus
from models.session import Session
from services.context_injector import build_context_message
from services.gemini_live import image_bytes_to_part

logger = logging.getLogger("brand-agent")

_AFFIRMATIONS = {"yes", "ok", "tak", "go", "dalej", "sure", "yep", "yeah", "proceed"}


def _resolve_next_step(session: Session) -> str | None:
    """Return an explicit [NEXT STEP] instruction based on canvas state.

    Returns None when no automatic next step can be determined (e.g. user
    is giving freeform feedback, not approving a pipeline step).
    """
    c = session.canvas
    ready = ElementStatus.READY
    empty = ElementStatus.EMPTY

    # Step 3: names not yet proposed → propose_names
    # Guard: if names were already proposed, wait for user to choose — don't re-propose.
    if c.name.status == empty and not session.names_proposed:
        return (
            "User approved. Call propose_names with 3 creative brand names now. "
            "ONE short sentence first. STOP after the tool call."
        )

    # Step 6: name chosen but identity not set → set_brand_identity
    if c.name.status == ready and c.tagline.status == empty:
        return (
            "User approved. Call set_brand_identity with name, tagline, story, values, "
            "tone_do, and tone_dont now. ONE short sentence first. STOP after the tool call."
        )

    # Step 8: identity ready but palette missing → set_palette
    if c.tagline.status == ready and c.palette.status == empty:
        return (
            "User approved. Call set_palette with 5 colors (hex, role, name) now. "
            "ONE short sentence about the palette mood first. STOP after the tool call."
        )

    # Step 10: palette ready but fonts missing → set_fonts
    if c.palette.status == ready and c.fonts.status == empty:
        return (
            "User approved. Call set_fonts with heading_font and body_font now. "
            "ONE short sentence about typography feel first. STOP after the tool call."
        )

    # Step 12: fonts ready but logo missing → generate_image logo
    if c.fonts.status == ready and c.logo.status == empty:
        return (
            "MANDATORY: You MUST call generate_image(element='logo') RIGHT NOW. "
            "Say max 6 words first. Then call the tool. No exceptions."
        )

    # Step 14: logo ready but hero missing → generate_image hero
    if c.logo.status == ready and c.hero.status == empty:
        return (
            "MANDATORY: You MUST call generate_image(element='hero') RIGHT NOW. "
            "Say max 6 words first. Then call the tool. No exceptions."
        )

    # Step 16: hero ready but instagram missing → generate_image instagram
    if c.hero.status == ready and c.instagram.status == empty:
        return (
            "MANDATORY: You MUST call generate_image(element='instagram') RIGHT NOW. "
            "Say max 6 words first. Then call the tool. No exceptions."
        )

    # Step 18: instagram ready but voiceover missing → generate_voiceover
    if c.instagram.status == ready and c.voiceover.status == empty:
        return (
            "MANDATORY: You MUST call generate_voiceover() RIGHT NOW. "
            "Say max 6 words first. Then call the tool. No exceptions."
        )

    # Step 20: voiceover ready → finalize_brand_kit
    if c.voiceover.status == ready:
        return (
            "MANDATORY: You MUST call finalize_brand_kit() RIGHT NOW. "
            "Say max 6 words first. Then call the tool. No exceptions."
        )

    return None


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

                lower = text.lower().strip()
                if lower.startswith("i choose "):
                    chosen = text[len("i choose "):].strip()
                    # Mark name as READY on canvas immediately so _resolve_next_step
                    # can see it and offer set_brand_identity on the next affirmation.
                    session.canvas.name.set(chosen)
                    details = (
                        f"User chose the brand name: '{chosen}'.\n"
                        f"Say ONE confident sentence about why this name fits — reference the product visuals.\n"
                        f"Then ask: 'Should I build out the full brand identity?' STOP. Do NOT call any tools yet."
                    )
                    trigger = "name_selected"
                    # Disarm propose_names watchdog — name was chosen, narration not needed
                    session.pending_tool_response = None
                elif "user has entered the studio" in lower:
                    details = (
                        "User has entered the Studio. Execute Step 2 of your flow:\n"
                        "Analyze the product in 2 sentences (reference what you SEE).\n"
                        "State your creative direction in 1 sentence.\n"
                        "Ask: 'Ready to explore some name options?' STOP. WAIT. Do NOT call any tools."
                    )
                    trigger = "studio_entry"
                elif lower in _AFFIRMATIONS:
                    next_step = _resolve_next_step(session)
                    if next_step:
                        # Build a fingerprint of current canvas step state
                        c = session.canvas
                        canvas_key = "|".join([
                            c.name.status, c.tagline.status, c.palette.status,
                            c.fonts.status, c.logo.status, c.hero.status,
                            c.instagram.status, c.voiceover.status,
                        ])
                        # Guard: if canvas hasn't changed since last [NEXT STEP] (or since
                        # last generate_image), the user's affirmation is confirming something
                        # else (e.g. palette change, tagline change) — don't inject [NEXT STEP].
                        if (session.pending_next_step is not None
                                and canvas_key == session.pending_next_step_canvas_key):
                            logger.info(
                                f"[{session.id}] Affirmation — same canvas state, "
                                f"sending as user_approved without NEXT STEP (agent is mid-conversation)"
                            )
                            details = f"User said: '{text}'. This confirms your last question or proposal. Act on it now."
                            trigger = "user_approved"
                        else:
                            session.pending_next_step = next_step
                            session.pending_next_step_canvas_key = canvas_key
                            details = f"User said: '{text}'\n[NEXT STEP] {next_step}"
                            trigger = "user_approved"
                            logger.info(
                                f"[{session.id}] Affirmation detected | "
                                f"Canvas next step resolved | Trigger: user_approved"
                            )
                    else:
                        details = text
                        trigger = "user_message"
                else:
                    details = text
                    trigger = "user_message"

                context = build_context_message(
                    session,
                    trigger=trigger,
                    details=details,
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
                        audio=types.Blob(data=audio_bytes, mime_type="audio/pcm;rate=16000"),
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
                # Frontend finished playing agent audio.
                # No action needed — agent decides when to continue.
                pass

            # Ignore ping, keepalive, and unknown message types

    except WebSocketDisconnect:
        logger.info(f"[{session.id}] WebSocket disconnected")
    except Exception as e:
        logger.error(f"[{session.id}] receive_loop error: {e}")
