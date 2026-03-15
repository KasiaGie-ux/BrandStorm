"""WebSocket receive loop — frontend → Live API."""

import asyncio
import base64
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect
from google.genai import types

from models.session import AgentPhase, Session
from services import brand_state
from services.gemini_live import image_bytes_to_part
from routes.ws_helpers import send_json

logger = logging.getLogger("brand-agent")

# Phases where feedback gate is active (user has a brand name in progress)
_active_phases = {
    AgentPhase.AWAITING_INPUT,
    AgentPhase.COMPLETE,
    AgentPhase.REFINING,
    AgentPhase.GENERATING,
    AgentPhase.REVEAL_SPEECH,
    AgentPhase.REVEAL_TOOL,
    AgentPhase.PALETTE_SPEECH,
    AgentPhase.PALETTE_TOOL,
    AgentPhase.FONTS_SPEECH,
    AgentPhase.FONTS_TOOL,
    AgentPhase.IMAGE_SPEECH,
    AgentPhase.IMAGE_TOOL,
    AgentPhase.VOICEOVER_SPEECH,
    AgentPhase.VOICEOVER_TOOL,
}

_pos_signals = [
    "super", "ok", "great", "love", "nice",
    "perfect", "good", "yes", "tak", "dobr",
    "swietn", "fajn", "podoba", "continue",
    "dalej", "kontynuuj", "👍", "👏",
]

_delegation_signals = [
    "decide", "zdecyduj", "you choose", "ty zdecyduj",
    "sam zdecyduj", "your call", "up to you",
    "wybierz", "sam wybierz",
]


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
                    f"[{session.id}] Action: text_input | "
                    f"Text: {text[:80]} | Phase: {session.phase.value}"
                )
                session.add_transcript("user", text)

                _lower = text.lower().strip()

                # Detect name selection ("I choose Aurum") and store brand_name early
                if _lower.startswith("i choose "):
                    chosen = text[len("I choose "):].strip()
                    if chosen and not session.brand_name:
                        session.brand_name = chosen
                        logger.info(
                            f"[{session.id}] Action: name_selected_early | "
                            f"Name: {chosen}"
                        )
                # Always send feedback immediately — even during GENERATING.
                if session.phase == AgentPhase.GENERATING:
                    session.interrupt_text = text
                    session.awaiting_feedback = True
                    logger.info(
                        f"[{session.id}] Action: interrupt_immediate | "
                        f"Text: {text[:80]} | Phase: GENERATING"
                    )

                # FIX 6: Simplified positive signal handler
                if session.awaiting_feedback and any(s in _lower for s in _pos_signals):
                    session.awaiting_feedback = False
                    session.pending_regen = False
                    session.pending_regen_target = None
                    if session.zip_url:
                        session.zip_url = None
                        logger.info(f"[{session.id}] Action: zip_cleared_for_regen")
                    logger.info(
                        f"[{session.id}] Action: feedback_gate_cleared | "
                        f"Text: {text[:40]}"
                    )

                # FIX 5: Simplified feedback gate
                if (not session.awaiting_feedback
                        and session.brand_name
                        and session.phase in _active_phases
                        and not any(s in _lower for s in _pos_signals)):
                    session.awaiting_feedback = True
                    logger.info(
                        f"[{session.id}] Action: feedback_gate_set | "
                        f"Text: {text[:60]}"
                    )

                _is_delegation = any(s in _lower for s in _delegation_signals)

                # Detect "give me new names / change name" signals — applies at ANY phase
                _new_name_signals = [
                    "new name", "new names", "change name", "different name",
                    "nowa nazwa", "nowe nazwy", "zmień nazwę", "zmien nazwe",
                    "give me names", "give me new name", "give me new names",
                ]
                _restart_signals = [
                    "everything", "all of it", "start over", "wszystko",
                    "od nowa", "zacznij od nowa", "całość", "calosc",
                ]
                _wants_new_names = any(s in _lower for s in _new_name_signals)
                _wants_restart = any(s in _lower for s in _restart_signals)

                # Always clear pregen cache when user asks for new names,
                # regardless of which phase the request arrives in.
                if _wants_new_names or _wants_restart:
                    session._pregen_names = None
                    session._pregen_names_sent = False
                    logger.info(
                        f"[{session.id}] Action: pregen_cleared_for_new_names | "
                        f"Phase: {session.phase.value} | Text: {text[:60]}"
                    )

                # User just chose a name → agent must speak comment, no tools
                _name_chosen_phases = {
                    AgentPhase.AWAITING_NAME,
                    AgentPhase.AWAITING_INPUT,
                    AgentPhase.PROPOSING,
                }
                if (
                    session.brand_name
                    and not session.tagline
                    and session.phase in _name_chosen_phases
                ):
                    session.awaiting_feedback = False
                    brand_state.transition_phase(session, AgentPhase.REVEAL_SPEECH)
                    wrapped = (
                        f"USER INPUT: {text}\n"
                        f"The user chose the brand name '{session.brand_name}'. "
                        f"Say a confident, specific comment about why this name fits — "
                        f"reference what you see in the product photo. Max 2 sentences. "
                        f"End with something like 'Let me build out the full brand identity for you.' "
                        f"CRITICAL: Do NOT call any tools. Do NOT call reveal_brand_identity. "
                        f"Just speak your comment, then STOP."
                    )

                # User asked for new names during name-selection phases
                # (AWAITING_NAME, ANALYSIS_SPEECH, PROPOSING — before a name is chosen)
                elif (_wants_new_names or _wants_restart) and not session.brand_name:
                    brand_state.transition_phase(session, AgentPhase.AWAITING_NAME)
                    session.awaiting_feedback = False
                    wrapped = (
                        f"USER INPUT: {text}\n"
                        "The user wants completely new brand name options. "
                        "Say ONE brief sentence acknowledging this (max 8 words). "
                        "Then IMMEDIATELY call propose_names with 3 completely fresh options. "
                        "Do NOT ask questions. Call the tool now."
                    )
                    logger.info(
                        f"[{session.id}] Action: new_names_wrapped_early | "
                        f"Phase: {session.phase.value} | Text: {text[:60]}"
                    )

                # User rejected names in AWAITING_NAME → force immediate propose_names call
                elif (session.phase == AgentPhase.AWAITING_NAME and not session.brand_name):
                    wrapped = (
                        f"USER INPUT: {text}\n"
                        "The user rejected the name proposals. "
                        "Say ONE brief acknowledgement sentence (max 10 words). "
                        "Then IMMEDIATELY call propose_names with 3 completely fresh brand name options. "
                        "Do NOT ask questions. Do NOT wait. Call the tool now."
                    )
                    logger.info(
                        f"[{session.id}] Action: name_rejection_wrapped | Text: {text[:60]}"
                    )

                # During active brand flow, wrap with session context
                elif session.phase in {
                    AgentPhase.AWAITING_INPUT,
                    AgentPhase.COMPLETE,
                    AgentPhase.REFINING,
                    AgentPhase.GENERATING,
                } and session.brand_name:

                    if _wants_new_names or _wants_restart:
                        # Reset brand state so pipeline restarts from names
                        session.brand_name = None
                        session.tagline = None
                        session.brand_story = None
                        session.brand_values = None
                        session.tone_of_voice = None
                        session.palette = None
                        session.font_suggestion = None
                        session.completed_assets.clear()
                        session.asset_urls.clear()
                        session.logo_image_bytes = None
                        session.audio_url = None
                        session.zip_url = None
                        session.voiceover_sent = False
                        session.voiceover_playing = False
                        session.auto_continue_count = 0
                        brand_state.transition_phase(session, AgentPhase.AWAITING_NAME)
                        wrapped = (
                            f"USER INPUT: {text}\n"
                            "The user wants completely new brand name options. "
                            "Say ONE brief sentence acknowledging this (max 8 words). "
                            "Then IMMEDIATELY call propose_names with 3 completely fresh options. "
                            "Do NOT ask questions. Call the tool now."
                        )
                        logger.info(
                            f"[{session.id}] Action: full_restart_wrapped | Text: {text[:60]}"
                        )
                    else:
                        _done = ", ".join(session.completed_assets) if session.completed_assets else "none"
                        _has_palette = "yes" if session.palette else "no"
                        _has_fonts = "yes" if session.font_suggestion else "no"
                        _is_finalized = "yes" if session.zip_url else "no"
                        _ctx = (
                            f"[Session context: brand='{session.brand_name}', "
                            f"completed_assets=[{_done}], palette={_has_palette}, "
                            f"fonts={_has_fonts}, finalized={_is_finalized}]"
                        )
                        if _is_delegation:
                            wrapped = (
                                f"USER INPUT: {text}\n{_ctx}\n"
                                "The user wants you to decide. Make your own creative "
                                "choice and act on it. Call the appropriate tool immediately."
                            )
                        else:
                            wrapped = (
                                f"USER INPUT: {text}\n{_ctx}\n"
                                "Handle this per your system prompt feedback rules. "
                                "If the user wants something changed, acknowledge briefly "
                                "then call the appropriate tool. "
                                "If they're asking a question, answer it."
                            )
                else:
                    wrapped = text

                await live_session.send_client_content(
                    turns=[types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=wrapped)],
                    )],
                    turn_complete=True,
                )
                logger.info(f"[{session.id}] Action: text_sent_to_live_api")

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
                    logger.error(f"[{session.id}] Action: image_upload_empty")
                    await send_json(ws, {
                        "type": "error",
                        "message": "Image upload failed: no image data received.",
                    })
                    continue

                if image_b64.startswith("data:"):
                    _, image_b64 = image_b64.split(",", 1)

                image_bytes = base64.b64decode(image_b64)
                logger.info(
                    f"[{session.id}] Action: image_upload | "
                    f"Size: {len(image_bytes)} bytes | MIME: {mime_type}"
                )

                if len(image_bytes) < 100:
                    logger.error(
                        f"[{session.id}] Action: image_too_small | Size: {len(image_bytes)}"
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
                    "Here is the product photo. Start with your OPENING SEQUENCE only:\n"
                    "Line 1 — Say EXACTLY 3 dramatic words. Not 2, not 4 — THREE words. "
                    "Each word ends with a period. Each word on its own. "
                    "Pattern: '[Word1]. [Word2]. [Word3].' — e.g. 'Golden. Sculpted. Iconic.' "
                    "WRONG (only 2 words): 'Luminous. Fluid.' — you MUST say 3 words.\n"
                    "Line 2 — introduce yourself in one sentence (your name is Charon, creative director).\n"
                    "Then STOP. Say nothing more. Do NOT analyze the product yet. "
                    "Do NOT mention names, brands, or call any tools. Just the 3-word opener + intro."
                )
                if user_context:
                    prompt += f"\n\nAdditional context from the client: {user_context}"

                logger.info(
                    f"[{session.id}] Action: sending_image_to_live_api | "
                    f"Size: {len(image_bytes)} bytes | Prompt: {prompt[:80]}"
                )
                await live_session.send_client_content(
                    turns=[types.Content(
                        role="user",
                        parts=[image_part, types.Part.from_text(text=prompt)],
                    )],
                    turn_complete=True,
                )
                logger.info(
                    f"[{session.id}] Action: image_sent_to_live_api | "
                    f"Initial prompt delivered"
                )
                session.add_transcript("user", f"[product image uploaded] {prompt}")
                brand_state.transition_phase(session, AgentPhase.ANALYZING)
                logger.info(
                    f"[{session.id}] Action: image_forwarded | "
                    f"{len(image_bytes)} bytes | Phase: ANALYZING"
                )

            elif msg_type == "audio_playback_done":
                logger.info(
                    f"[{session.id}] Action: audio_playback_done (frontend flush complete)"
                )
                session.frontend_ready.set()

            elif msg_type == "voiceover_playback_done":
                logger.info(f"[{session.id}] Action: voiceover_playback_done")
                if session.audio_url and not session.zip_url and session.brand_name:
                    finalize_nudge = (
                        "Anna's narration has finished. "
                        "Call finalize_brand_kit now, then say ONE warm closing sentence. "
                        "Do NOT generate another voiceover."
                    )
                    try:
                        await live_session.send_client_content(
                            turns=[types.Content(
                                role="user",
                                parts=[types.Part.from_text(text=finalize_nudge)],
                            )],
                            turn_complete=True,
                        )
                        brand_state.transition_phase(session, AgentPhase.GENERATING)
                        logger.info(
                            f"[{session.id}] Action: voiceover_done_finalize_nudge | "
                            f"Sent finalize nudge from receive_loop"
                        )
                    except Exception as e:
                        logger.error(
                            f"[{session.id}] Action: voiceover_finalize_nudge_failed | "
                            f"Error: {e}"
                        )
                else:
                    session.voiceover_playing = False

            elif msg_type == "stop_session":
                logger.info(f"[{session.id}] Action: stop_requested")
                await send_json(ws, {"type": "session_stopped"})
                return

            else:
                logger.warning(
                    f"[{session.id}] Unknown message type: {msg_type}"
                )

    except WebSocketDisconnect:
        logger.info(f"[{session.id}] Action: client_disconnected")
    except Exception as e:
        logger.error(f"[{session.id}] Action: receive_loop_error | Error: {e}")
