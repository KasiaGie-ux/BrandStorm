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
from services.pregen import PreGenerator
from services.storage import StorageService
from services.text_parser import parse_agent_text
from services.tool_executor import ToolExecutor
from services.voiceover import _tts_generate  # used by bg pre-gen task

logger = logging.getLogger("brand-agent")


def _store_event_on_session(
    session: Session,
    event: dict,
    pregen: PreGenerator | None = None,
    emit_cb=None,
) -> None:
    """Persist structured event data on the session for downstream tools.

    When brand_name_reveal is detected, fires the pre-generation pipeline
    (palette → images) in the background.
    """
    etype = event.get("type", "")
    if etype == "brand_name_reveal" and event.get("name"):
        old_name = session.brand_name
        session.brand_name = event["name"]
        # If name changed mid-flow, reset all downstream state
        if old_name and old_name != event["name"]:
            logger.info(
                f"[{session.id}] Action: name_change_reset | "
                f"Old: {old_name} → New: {event['name']} | "
                f"Resetting: {session.completed_assets}"
            )
            session.completed_assets.clear()
            session.asset_urls.clear()
            session.palette = None
            session.font_suggestion = None
            session.logo_image_bytes = None
            session.audio_url = None
            session.auto_continue_count = 0
        # Fire (or restart) the pre-generation pipeline
        if pregen:
            pregen.start(session)
    elif etype == "palette_reveal" and event.get("colors"):
        session.palette = event["colors"]
    elif etype == "font_suggestion":
        session.font_suggestion = {
            "heading": event.get("heading"),
            "body": event.get("body"),
        }
    elif etype == "tagline_reveal" and event.get("tagline"):
        session.tagline = event["tagline"]
    elif etype == "brand_story" and event.get("story"):
        session.brand_story = event["story"]
        # Background pre-generate the brand story narration (Anna's voice)
        # so it's ready when generate_voiceover is called.
        # This is ONLY the story — the greeting is generated fresh at tool call
        # time from the agent's narration_text.
        if not session.audio_url:
            _storage = StorageService()

            async def _bg_voiceover():
                try:
                    from config import NARRATOR_VOICE
                    from services.voiceover import _tts_generate
                    wav = await _tts_generate(
                        session_id=session.id,
                        text=event["story"],
                        voice=NARRATOR_VOICE,
                        label="bg_voiceover_story",
                    )
                    if wav:
                        url = await _storage.upload_image(
                            session_id=session.id,
                            asset_type="voiceover_story",
                            image_bytes=wav,
                            mime_type="audio/wav",
                        )
                        session.audio_url = url
                        logger.info(
                            f"[{session.id}] Action: bg_voiceover_done | URL: {url}"
                        )
                except Exception as e:
                    logger.warning(
                        f"[{session.id}] Action: bg_voiceover_failed | Error: {e}"
                    )

            task = asyncio.create_task(_bg_voiceover(), name="bg-voiceover")
            session.pregen_tasks["voiceover"] = task
    elif etype == "brand_values" and event.get("values"):
        session.brand_values = event["values"]
    elif etype == "tone_of_voice" and event.get("tone_of_voice"):
        session.tone_of_voice = event["tone_of_voice"]


# Short delay between consecutive structured events in _flush_and_emit.
# Kept small because the frontend's useEventQueue handles the real visual
# stagger while audio is playing.  This is just a safety gap so
# the WebSocket doesn't batch multiple events into a single frame.
_EVENT_STAGGER_DELAY = 0.3   # seconds


async def _wait_and_nudge(
    session: "Session",
    live_session: object,
    nudge: str,
    label: str,
    timeout: float = 30.0,
) -> None:
    """Wait for frontend to signal it finished showing the current turn's
    visual events + audio, then send the next auto-continue nudge.

    The frontend sends ``audio_playback_done`` after its event-queue flush
    completes, which sets ``session.frontend_ready``.  If no audio was
    played for the turn the frontend fires a fallback after 800 ms.

    Guards against stale nudges: if the user interrupted (barge-in) or
    the session is awaiting feedback we silently drop the nudge.
    """
    if not hasattr(session, "frontend_ready"):
        session.frontend_ready = asyncio.Event()
    session.frontend_ready.clear()

    try:
        await asyncio.wait_for(session.frontend_ready.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(
            f"[{session.id}] {label}: frontend_ready timeout ({timeout}s), proceeding"
        )

    # Stale-nudge guard
    if session.interrupt_text or session.awaiting_feedback:
        logger.info(f"[{session.id}] {label}: cancelled (interrupt/feedback)")
        return

    await live_session.send_client_content(
        turns=[types.Content(
            role="user",
            parts=[types.Part.from_text(text=nudge)],
        )],
        turn_complete=True,
    )

async def _flush_and_emit(
    ws: WebSocket, session: Session,
    text: str, seen_types: set[str],
    pregen: PreGenerator | None = None,
    emit_cb=None,
) -> None:
    """Parse structured tags from text, emit events + narration to frontend.

    Sends a final agent_text with partial=False to replace the accumulated
    partial chunks (which may contain raw tags). The frontend replaces the
    last partial agent_text with this cleaned version, eliminating duplicates.

    When multiple structured events are emitted at once we now pause briefly
    between each one. This is the backend fix for the bug where the UI would
    render the entire brand reveal in a single frame.
    """
    if not text or not text.strip():
        return
    session.add_transcript("agent", text)
    events, narration = parse_agent_text(text, seen_types=seen_types)

    if events:
        # Replace partial agent_text with cleaned narration BEFORE events,
        # so structured event cards aren't interleaved with duplicate text.
        await send_json(ws, {
            "type": "agent_text",
            "text": narration or "",
            "partial": False,
        })
        # Pause so the narration text is visible before structured cards appear
        await asyncio.sleep(1.0)
        for ev in events:
            await send_json(ws, ev)
            _store_event_on_session(session, ev, pregen=pregen, emit_cb=emit_cb)
            # little gap so frontend <App> can schedule a reveal animation
            await asyncio.sleep(_EVENT_STAGGER_DELAY)
    else:
        # No structured events — send the full text as final
        await send_json(ws, {
            "type": "agent_text",
            "text": text,
            "partial": False,
        })


async def send_json(ws: WebSocket, data: dict) -> None:
    """Send JSON to frontend, silently ignore if closed."""
    try:
        await ws.send_json(data)
        if data.get("type") in ("image_generated", "palette_reveal", "generation_complete", "voiceover_handoff", "voiceover_greeting", "voiceover_story"):
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
                logger.info(f"[{session.id}] Action: text_input | Text: {text[:80]} | Phase: {session.phase.value}")
                session.add_transcript("user", text)

                # Detect name selection ("I choose Aurum") and store
                # brand_name early so auto-continue can fire after turn
                _lower = text.lower().strip()
                if _lower.startswith("i choose "):
                    chosen = text[len("I choose "):].strip()
                    if chosen and not session.brand_name:
                        session.brand_name = chosen
                        logger.info(
                            f"[{session.id}] Action: name_selected_early | "
                            f"Name: {chosen}"
                        )

                # Always send feedback immediately — even during GENERATING.
                # Also queue as interrupt_text so agent_loop can relay it
                # between tool calls if needed (belt and suspenders).
                if session.phase == AgentPhase.GENERATING:
                    session.interrupt_text = text
                    session.awaiting_feedback = True
                    logger.info(
                        f"[{session.id}] Action: interrupt_immediate | "
                        f"Text: {text[:80]} | Phase: GENERATING"
                    )
                # Fall through to wrapping + send below (no else!)
                if True:
                    # Check for positive signals to clear feedback gate
                    _pos_signals = [
                        "super", "ok", "great", "love", "nice",
                        "perfect", "good", "yes", "tak", "dobr",
                        "swietn", "fajn", "podoba", "continue",
                        "dalej", "kontynuuj", "👍", "👏",
                    ]
                    if session.awaiting_feedback and any(s in _lower for s in _pos_signals):
                        session.awaiting_feedback = False
                        session.pending_regen = False
                        session.pending_regen_target = None
                        # Something was regenerated — clear zip so re-finalize is possible
                        if session.zip_url:
                            session.zip_url = None
                            logger.info(f"[{session.id}] Action: zip_cleared_for_regen")
                        logger.info(f"[{session.id}] Action: feedback_gate_cleared | Text: {text[:40]}")

                    # --- Detect feedback type and set pending_regen ---
                    # This tells auto-continue to back off until the agent
                    # actually executes the corrective tool call.
                    _feedback_keywords = {
                        "tagline": ["tagline", "slogan", "haslo", "hasło", "motto"],
                        "logo": ["logo", "logotyp", "znak"],
                        "palette": ["color", "colour", "palette", "kolor", "paleta", "darker", "lighter", "ciemn", "jasn"],
                        "fonts": ["font", "czcionk", "typograph", "heading", "nagłów"],
                        "hero_lifestyle": ["hero", "lifestyle", "zdjęcie", "zdj"],
                        "instagram_post": ["instagram", "insta", "post"],
                        "name": ["name", "nazwa", "rename", "zmień nazw"],
                    }
                    if (not session.pending_regen
                            and not session.awaiting_feedback
                            and session.brand_name
                            and not any(s in _lower for s in _pos_signals)):
                        for target, kws in _feedback_keywords.items():
                            if any(kw in _lower for kw in kws):
                                session.pending_regen = True
                                session.pending_regen_target = target
                                session.awaiting_feedback = True
                                logger.info(
                                    f"[{session.id}] Action: feedback_detected | "
                                    f"Target: {target} | Text: {text[:60]}"
                                )
                                break

                    # --- Detect delegation signals ---
                    # User says "decide" / "zdecyduj" / "you choose" = let agent decide.
                    # If pending_regen is set, agent must execute the fix NOW.
                    _delegation_signals = [
                        "decide", "zdecyduj", "you choose", "ty zdecyduj",
                        "sam zdecyduj", "your call", "up to you",
                        "wybierz", "sam wybierz",
                    ]
                    _is_delegation = any(s in _lower for s in _delegation_signals)

                    # During active brand flow (any phase after name chosen),
                    # wrap user text so agent classifies feedback properly
                    _feedback_phases = {
                        AgentPhase.AWAITING_INPUT,
                        AgentPhase.COMPLETE,
                        AgentPhase.REFINING,
                        AgentPhase.GENERATING,
                    }
                    if session.phase in _feedback_phases and session.brand_name:
                        # Build context about what exists
                        _done = ", ".join(session.completed_assets) if session.completed_assets else "none"
                        _has_palette = "yes" if session.palette else "no"
                        _has_fonts = "yes" if session.font_suggestion else "no"
                        _is_finalized = "yes" if session.zip_url else "no"
                        _ctx = (
                            f"[Session context: brand='{session.brand_name}', "
                            f"completed_assets=[{_done}], palette={_has_palette}, "
                            f"fonts={_has_fonts}, finalized={_is_finalized}]"
                        )

                        if _is_delegation and session.pending_regen:
                            # User delegated the decision — agent must fix NOW
                            _target = session.pending_regen_target or "the thing they complained about"
                            _tool_map = {
                                "tagline": "reveal_brand_identity with a NEW, DIFFERENT tagline (keep name, story, values unchanged)",
                                "logo": "generate_image with asset_type 'logo' and a COMPLETELY DIFFERENT prompt",
                                "palette": "generate_palette with DIFFERENT colors",
                                "fonts": "suggest_fonts with DIFFERENT font pairing",
                                "hero_lifestyle": "generate_image with asset_type 'hero_lifestyle' and a new prompt",
                                "instagram_post": "generate_image with asset_type 'instagram_post' and a new prompt",
                                "name": "propose_names with 3 new names",
                            }
                            _tool_hint = _tool_map.get(_target, f"the appropriate tool to fix {_target}")
                            wrapped = (
                                f"USER INPUT: {text}\n{_ctx}\n"
                                f"The user wants YOU to decide. They previously asked to change the {_target}. "
                                f"You MUST call {_tool_hint} RIGHT NOW with your own creative choice. "
                                f"Do NOT ask more questions. Do NOT skip ahead to palette/fonts/images. "
                                f"Fix the {_target} FIRST, then STOP and ask if they like it."
                            )
                        elif session.awaiting_feedback:
                            # Still in feedback loop — responding to a regen
                            wrapped = (
                                f"USER INPUT: {text}\n{_ctx}\n"
                                "The user is responding to a regenerated asset. "
                                "If positive → acknowledge briefly, then continue. "
                                "If the regenerated asset was the LOGO and user approves it, "
                                "you MUST also regenerate hero_lifestyle and instagram_post "
                                "since they contain the old logo. Announce this and do it. "
                                "If still negative → fix ONLY that specific thing again. "
                                "ASK if they like the new version."
                            )
                        else:
                            wrapped = (
                                f"USER INPUT: {text}\n{_ctx}\n"
                                "Classify the feedback:\n"
                                "- LOGO complaint → call generate_image with asset_type 'logo' "
                                "and a COMPLETELY DIFFERENT prompt. Do NOT change name, palette, or fonts.\n"
                                "- COLOR/PALETTE complaint → call generate_palette with new colors. Keep everything else.\n"
                                "- FONT/HEADING complaint → call suggest_fonts with different fonts. Keep everything else.\n"
                                "- TAGLINE complaint → call reveal_brand_identity with a new tagline only. Keep name, story, values.\n"
                                "- IMAGE complaint (hero, instagram) → regenerate ONLY that specific image.\n"
                                "- VAGUE NEGATIVE → ASK what specifically to change. Do NOT guess.\n"
                                "- NAME complaint (ONLY if they explicitly mention the name) → propose 3 new names.\n"
                                "CRITICAL: Fix ONLY the thing complained about. Do NOT restart. Do NOT re-analyze. "
                                "Do NOT change the name unless explicitly asked. Logo ≠ name. Colors ≠ name.\n"
                                "After regenerating, ASK the user if they like the new version. STOP and WAIT."
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
                logger.info(f"[{session.id}] Action: image_upload | Size: {len(image_bytes)} bytes | MIME: {mime_type}")

                if len(image_bytes) < 100:
                    logger.error(f"[{session.id}] Action: image_too_small | Size: {len(image_bytes)}")
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

                # --- Parallel text call for LaunchSequence display ---
                # Live API audio transcription is unreliable for the opening.
                # Fire a fast text-only call in the background to get reliable
                # opener words + intro. Voice still comes from Live API.
                async def _opening_text_call(
                    _ws=ws, _session=session,
                    _image_bytes=image_bytes, _mime_type=mime_type,
                ):
                    try:
                        from services.gemini_live import create_client as _cc
                        _tc = _cc()
                        _opening_prompt = (
                            "You are Brand Architect, an elite creative director. "
                            "Look at this product photo and respond with EXACTLY this JSON:\n"
                            '{"words": ["Word1", "Word2", "Word3"], '
                            '"intro": "I\'m Charon, your creative director. ...(one sentence)..."}\n'
                            "Rules:\n"
                            "- words: EXACTLY 3 dramatic single-word adjectives describing the product\n"
                            "- intro: ONE sentence introducing yourself as Charon. Confident and warm.\n"
                            "Respond with ONLY the JSON. No markdown, no backticks."
                        )
                        _img_part = types.Part.from_bytes(
                            data=_image_bytes, mime_type=_mime_type,
                        )
                        _resp = await _tc.aio.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=[_img_part, _opening_prompt],
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                            ),
                        )
                        _text = _resp.text.strip()
                        if _text.startswith("```"):
                            _text = _text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                        _data = json.loads(_text)
                        _words = _data.get("words", [])
                        _intro = _data.get("intro", "")
                        if len(_words) >= 2 and _intro:
                            await send_json(_ws, {
                                "type": "opening_sequence",
                                "words": _words[:3],
                                "intro": _intro,
                            })
                            logger.info(
                                f"[{_session.id}] Action: opening_text_ready | "
                                f"Words: {_words[:3]} | Intro: {_intro[:60]}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"[{_session.id}] Action: opening_text_failed | Error: {e}"
                        )

                asyncio.create_task(_opening_text_call(), name="opening-text")

                logger.info(f"[{session.id}] Action: sending_image_to_live_api | Size: {len(image_bytes)} bytes | Prompt: {prompt[:80]}")
                await live_session.send_client_content(
                    turns=[types.Content(
                        role="user",
                        parts=[image_part, types.Part.from_text(text=prompt)],
                    )],
                    turn_complete=True,
                )
                logger.info(f"[{session.id}] Action: image_sent_to_live_api | Initial prompt delivered")
                session.add_transcript("user", f"[product image uploaded] {prompt}")
                brand_state.transition_phase(session, AgentPhase.ANALYZING)
                logger.info(f"[{session.id}] Action: image_forwarded | {len(image_bytes)} bytes | Phase: ANALYZING")

            elif msg_type == "audio_playback_done":
                logger.info(f"[{session.id}] Action: audio_playback_done (frontend flush complete)")
                # Unblock any pending auto-continue nudges
                if hasattr(session, "frontend_ready"):
                    session.frontend_ready.set()

            elif msg_type == "voiceover_playback_done":
                # Frontend signals Anna's story narration finished playing.
                session.voiceover_playing = False
                logger.info(f"[{session.id}] Action: voiceover_playback_done")
                # Send finalize nudge directly to Live API from here
                if session.audio_url and not session.zip_url and session.brand_name:
                    finalize_nudge = (
                        "Anna's narration has finished. Now call finalize_brand_kit "
                        "to package everything. Say ONE closing sentence, then call "
                        "finalize_brand_kit."
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

            elif msg_type == "stop_session":
                logger.info(f"[{session.id}] Action: stop_requested")
                await send_json(ws, {"type": "session_stopped"})
                return  # Exit receive_loop cleanly, triggers task cancellation

            else:
                logger.warning(
                    f"[{session.id}] Unknown message type: {msg_type}"
                )

    except WebSocketDisconnect:
        logger.info(f"[{session.id}] Action: client_disconnected")
    except Exception as e:
        logger.error(f"[{session.id}] Action: receive_loop_error | Error: {e}")


async def agent_loop(
    ws: WebSocket,
    live_session: object,
    session: Session,
    tool_executor: ToolExecutor,
    pregen: PreGenerator | None = None,
) -> None:
    """Receive messages from Live API and forward to frontend."""
    agent_text_buffer: list[str] = []
    seen_event_types: set[str] = set()  # dedup across turns
    msg_count = 0
    turn_count = 0
    session_active = True
    # Track pending background tool tasks — prevents auto-continue
    # from firing while tool_response hasn't been sent yet.
    _pending_tool_bg = [0]  # mutable container to avoid nonlocal issues

    async def _emit_cb(ev: dict):
        """Direct emit for pregen pipeline and _flush_and_emit."""
        await send_json(ws, ev)
        _store_event_on_session(session, ev, pregen=pregen, emit_cb=None)

    try:
        async with asyncio.timeout(SESSION_TIMEOUT_SEC):
            logger.info(f"[{session.id}] Action: agent_loop_started | Timeout: {SESSION_TIMEOUT_SEC}s")

            while session_active:
                turn_count += 1
                logger.info(f"[{session.id}] Action: waiting_for_live_api_message | Turn: {turn_count}")

                async for message in live_session.receive():
                    msg_count += 1

                    logger.info(
                        f"[{session.id}] Raw msg #{msg_count} | "
                        f"server_content={message.server_content is not None} | "
                        f"tool_call={message.tool_call is not None} | "
                        f"setup_complete={message.setup_complete is not None}"
                    )

                    # Server content: audio, text, transcription
                    if message.server_content:
                        sc = message.server_content
                        _got_text_this_msg = False

                        if sc.model_turn and sc.model_turn.parts:
                            for part in sc.model_turn.parts:
                                if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
                                    # Suppress agent audio while Anna is narrating
                                    if session.voiceover_playing:
                                        logger.info(
                                            f"[{session.id}] Action: suppress_audio_during_voiceover"
                                        )
                                    else:
                                        await send_json(ws, {
                                            "type": "agent_audio",
                                            "data": base64.b64encode(part.inline_data.data).decode(),
                                            "mime_type": part.inline_data.mime_type,
                                        })
                                elif hasattr(part, "text") and part.text:
                                    _got_text_this_msg = True
                                    agent_text_buffer.append(part.text)
                                    await send_json(ws, {
                                        "type": "agent_text",
                                        "text": part.text,
                                        "partial": True,
                                    })

                        # output_transcription is the textual version of audio.
                        # Only use it if we didn't already get text from model_turn
                        # to avoid duplicating the same content.
                        if (sc.output_transcription and sc.output_transcription.text
                                and not _got_text_this_msg):
                            text = sc.output_transcription.text
                            agent_text_buffer.append(text)
                            await send_json(ws, {
                                "type": "agent_text",
                                "text": text,
                                "partial": True,
                            })

                        if sc.turn_complete:
                            full_text = " ".join(chunk for chunk in agent_text_buffer if chunk.strip())
                            logger.info(
                                f"[{session.id}] Action: turn_text_flush | "
                                f"Turn: {turn_count} | Text length: {len(full_text)} | "
                                f"Preview: {full_text[:120]}"
                            )

                            if session.phase == AgentPhase.ANALYZING:
                                # Send buffered text as final so frontend can use
                                # transcription as fallback if opening_sequence is slow.
                                if full_text.strip():
                                    await send_json(ws, {
                                        "type": "agent_text",
                                        "text": full_text,
                                        "partial": False,
                                    })
                                    session.add_transcript("agent", full_text)
                                else:
                                    await send_json(ws, {
                                        "type": "agent_text",
                                        "text": "",
                                        "partial": False,
                                    })
                            elif full_text.strip():
                                await _flush_and_emit(
                                    ws, session, full_text, seen_event_types,
                                    pregen=pregen, emit_cb=_emit_cb,
                                )
                            else:
                                # Close any dangling partial on frontend
                                await send_json(ws, {
                                    "type": "agent_text",
                                    "text": "",
                                    "partial": False,
                                })
                            agent_text_buffer.clear()

                            if session.phase == AgentPhase.ANALYZING:
                                # Opening sequence done → nudge for analysis speech (NO tool call yet)
                                brand_state.transition_phase(session, AgentPhase.PROPOSING)
                                logger.info(f"[{session.id}] Action: turn_complete_opening | Turn: {turn_count}")
                                await send_json(ws, {
                                    "type": "agent_turn_complete",
                                    "phase": session.phase.value,
                                })
                                # Turn A: speak analysis + direction + transition line — NO tool call
                                nudge = (
                                    "Now analyze the product photo. "
                                    "Say what you see (2 sentences, cite specific visual evidence). "
                                    "Then pick ONE creative direction (1 sentence). "
                                    "Then say a creative transition line for the names (1 sentence, varied). "
                                    "Do NOT call any tool yet. Just speak."
                                )
                                session._propose_nudge_pending = True
                                logger.info(f"[{session.id}] Action: auto_nudge_analysis_speech | Turn: {turn_count}")
                                await live_session.send_client_content(
                                    turns=[types.Content(
                                        role="user",
                                        parts=[types.Part.from_text(text=nudge)],
                                    )],
                                    turn_complete=True,
                                )
                                break
                            elif getattr(session, '_propose_nudge_pending', False):
                                # Turn B: agent finished speaking analysis → now call the tool
                                session._propose_nudge_pending = False
                                logger.info(f"[{session.id}] Action: auto_nudge_propose_tool (queued) | Turn: {turn_count}")
                                asyncio.create_task(_wait_and_nudge(
                                    session, live_session,
                                    "Now call propose_names with 3 brand name options.",
                                    "propose_names",
                                ))
                                break
                            elif session.phase in (AgentPhase.GENERATING, AgentPhase.PROPOSING):
                                brand_state.transition_phase(session, AgentPhase.AWAITING_INPUT)

                            logger.info(f"[{session.id}] Action: turn_complete | Turn: {turn_count} | Msgs: {msg_count}")
                            await send_json(ws, {
                                "type": "agent_turn_complete",
                                "phase": session.phase.value,
                            })

                            # --- Pending-regen nudge ---
                            # Agent finished a text-only turn but hasn't executed the
                            # corrective tool call yet. Nudge it to actually do the fix.
                            if (session.pending_regen
                                    and session.phase == AgentPhase.AWAITING_INPUT
                                    and session.auto_continue_count < 3
                                    and _pending_tool_bg[0] == 0):
                                _target = session.pending_regen_target or "the asset"
                                _tool_map = {
                                    "tagline": "reveal_brand_identity with a NEW tagline (keep name, story, values)",
                                    "logo": "generate_image with asset_type 'logo' and a COMPLETELY DIFFERENT prompt",
                                    "palette": "generate_palette with DIFFERENT colors",
                                    "fonts": "suggest_fonts with a DIFFERENT font pairing",
                                    "hero_lifestyle": "generate_image with asset_type 'hero_lifestyle' and a new prompt",
                                    "instagram_post": "generate_image with asset_type 'instagram_post' and a new prompt",
                                    "name": "propose_names with 3 new names",
                                }
                                _tool_hint = _tool_map.get(_target, f"the appropriate tool to change {_target}")
                                session.auto_continue_count += 1
                                regen_nudge = (
                                    f"You MUST call {_tool_hint} NOW. "
                                    f"The user asked you to change the {_target}. "
                                    f"Do NOT talk about it — just call the tool with your creative choice. "
                                    f"Do NOT skip ahead to palette, fonts, or images. Fix the {_target} FIRST."
                                )
                                logger.info(
                                    f"[{session.id}] Action: pending_regen_nudge | "
                                    f"Target: {_target} | Attempt: {session.auto_continue_count}"
                                )
                                brand_state.transition_phase(session, AgentPhase.GENERATING)
                                await live_session.send_client_content(
                                    turns=[types.Content(
                                        role="user",
                                        parts=[types.Part.from_text(text=regen_nudge)],
                                    )],
                                    turn_complete=True,
                                )
                                break

                            # Auto-continue: nudge agent to keep going whenever
                            # it finishes a text turn but the brand kit isn't done.
                            # Three cases:
                            #   A) No palette yet → nudge to call generate_palette
                            #   B) Palette exists, images remaining → nudge to generate images
                            #   C) All images done, not finalized → nudge voiceover + finalize
                            _MAX_AUTO_CONTINUE = 8
                            remaining = session.total_assets - len(session.completed_assets)
                            should_continue = (
                                session.phase == AgentPhase.AWAITING_INPUT
                                and session.auto_continue_count < _MAX_AUTO_CONTINUE
                                and session.brand_name  # at minimum we need a brand name
                                and not session.awaiting_feedback  # wait for user approval after regen
                                and not session.pending_regen  # wait for agent to fix what user complained about
                                and not session.zip_url  # brand kit done — wait for user feedback, don't auto-nudge
                                and _pending_tool_bg[0] == 0  # wait for background tool tasks to finish
                            )
                            if _pending_tool_bg[0] > 0:
                                logger.info(
                                    f"[{session.id}] Action: auto_continue_deferred | "
                                    f"Pending tools: {_pending_tool_bg[0]} | "
                                    f"Waiting for background tool tasks to complete"
                                )

                            if should_continue and not session.tagline and session.brand_name:
                                # Case A0: name chosen but brand identity not revealed yet
                                session.auto_continue_count += 1
                                nudge = (
                                    f"The user chose the name '{session.brand_name}'. "
                                    "Say a confident, product-specific comment about why this name fits "
                                    "(reference what you see in the product photo). "
                                    "Then announce what's next — e.g. 'Let me build out the full brand identity for you.' "
                                    "Then IMMEDIATELY call reveal_brand_identity with brand_name, tagline, brand_story, "
                                    "brand_values, and tone_of_voice_do/dont. "
                                    "Do NOT propose new names. Do NOT ask questions."
                                )
                                logger.info(f"[{session.id}] Action: auto_continue_reveal (queued) | Attempt: {session.auto_continue_count}/{_MAX_AUTO_CONTINUE}")
                                brand_state.transition_phase(session, AgentPhase.GENERATING)
                                asyncio.create_task(_wait_and_nudge(session, live_session, nudge, "reveal"))
                            elif should_continue and not session.palette:
                                # Case A1: brand identity revealed but no palette yet
                                session.auto_continue_count += 1
                                nudge = (
                                    "Say ONE sentence about the colors you see in the product and the palette direction you're taking — "
                                    "be specific, mention a dominant hue or mood. Do NOT use generic phrases like 'Now let me craft your color palette.' "
                                    "Then call generate_palette with 5 colors. "
                                    "After palette returns, say 1 sentence commenting on the RESULT — mention a specific color or the overall feel it creates. "
                                    "Then HARD STOP — say nothing more. Do NOT mention fonts, logo, or images."
                                )
                                logger.info(f"[{session.id}] Action: auto_continue_palette (queued) | Attempt: {session.auto_continue_count}/{_MAX_AUTO_CONTINUE}")
                                brand_state.transition_phase(session, AgentPhase.GENERATING)
                                asyncio.create_task(_wait_and_nudge(session, live_session, nudge, "palette"))
                            elif should_continue and session.palette and not session.font_suggestion:
                                # Case A2: palette done but no fonts yet
                                session.auto_continue_count += 1
                                nudge = (
                                    "Say ONE sentence connecting typography to this brand's personality — "
                                    "mention the feeling you want or how it complements the palette. "
                                    "Do NOT use generic phrases like 'Time to pair the perfect fonts.' "
                                    "Then call suggest_fonts with heading and body fonts. "
                                    "After fonts return, say 1 sentence about what THIS specific pairing achieves for the brand. "
                                    "Then HARD STOP — say nothing more. Do NOT mention logo, images, or visuals."
                                )
                                logger.info(f"[{session.id}] Action: auto_continue_fonts (queued) | Attempt: {session.auto_continue_count}/{_MAX_AUTO_CONTINUE}")
                                brand_state.transition_phase(session, AgentPhase.GENERATING)
                                asyncio.create_task(_wait_and_nudge(session, live_session, nudge, "fonts"))
                            elif should_continue and session.palette and remaining > 0:
                                # Case B: palette done, images remaining
                                session.auto_continue_count += 1
                                remaining_types = [
                                    a for a in ["logo", "hero_lifestyle", "instagram_post"]
                                    if a not in session.completed_assets
                                ]
                                next_asset = remaining_types[0] if remaining_types else "logo"
                                asset_label = {"logo": "logo", "hero_lifestyle": "lifestyle hero", "instagram_post": "Instagram post"}.get(next_asset, next_asset)
                                nudge = (
                                    f"Say ONE sentence hinting at the creative direction for the {asset_label} — "
                                    f"reference the brand's palette, mood, or identity. Do NOT say generic phrases like "
                                    f"'Now let me create your {asset_label}.' Be a creative director teasing a specific vision. "
                                    f"Finish speaking your full sentence, then call generate_image "
                                    f"with asset_type '{next_asset}'. "
                                    f"The image is pre-generated and returns instantly. "
                                    f"Say NOTHING after the tool call — stop and wait."
                                )
                                logger.info(f"[{session.id}] Action: auto_continue (queued) | Attempt: {session.auto_continue_count}/{_MAX_AUTO_CONTINUE} | Next: {next_asset}")
                                brand_state.transition_phase(session, AgentPhase.GENERATING)
                                asyncio.create_task(_wait_and_nudge(session, live_session, nudge, f"image:{next_asset}"))
                            elif (session.phase == AgentPhase.AWAITING_INPUT
                                    and session.auto_continue_count < _MAX_AUTO_CONTINUE
                                    and session.brand_name
                                    and session.palette and remaining == 0 and not session.zip_url
                                    and not session.voiceover_playing):
                                # Case C: all images done — voiceover + finalize
                                session.awaiting_feedback = False
                                session.auto_continue_count += 1
                                nudge = (
                                    "All images are done. Say ONE sentence that ties the whole creative journey together — "
                                    "reference something specific about the brand (a color, the name's meaning, the mood). "
                                    "Do NOT use generic phrases like 'Let me bring it all together.' "
                                    "Then call generate_voiceover with ALL FOUR parameters:\n"
                                    "- handoff_text: your 1-sentence handoff introducing Anna (e.g. 'Let me hand you over to Anna.')\n"
                                    "- greeting_text: Anna's short self-introduction, 1-2 sentences (e.g. \"Hi, I'm Anna. Let me tell you the story of [brand].\")\n"
                                    "- narration_text: Anna's full brand story narration — the story ONLY, without the greeting\n"
                                    "- mood: brand mood\n"
                                    "After voiceover returns, STOP. Say nothing more. "
                                    "Do NOT call finalize_brand_kit — the system will handle it after Anna finishes."
                                )
                                logger.info(f"[{session.id}] Action: auto_continue_finalize (queued) | Attempt: {session.auto_continue_count}/{_MAX_AUTO_CONTINUE}")
                                brand_state.transition_phase(session, AgentPhase.GENERATING)
                                asyncio.create_task(_wait_and_nudge(session, live_session, nudge, "voiceover"))
                            elif (session.brand_name
                                    and (remaining > 0 or not session.zip_url)
                                    and session.auto_continue_count >= _MAX_AUTO_CONTINUE):
                                logger.warning(
                                    f"[{session.id}] Action: auto_continue_exhausted | "
                                    f"Attempts: {session.auto_continue_count} | "
                                    f"Agent not responding — waiting for user"
                                )

                            break

                    # Tool calls from agent
                    if message.tool_call:
                        for fc in message.tool_call.function_calls:
                            # ── 1. Flush any buffered agent text ──
                            buffered = " ".join(chunk for chunk in agent_text_buffer if chunk.strip())
                            if buffered:
                                await _flush_and_emit(
                                    ws, session, buffered, seen_event_types,
                                    pregen=pregen, emit_cb=_emit_cb,
                                )
                                agent_text_buffer.clear()

                            brand_state.infer_phase_from_tool(session, fc.name)

                            # ── 2. Send spinner immediately (frontend queues if audio playing) ──
                            await send_json(ws, {
                                "type": "tool_invoked",
                                "tool": fc.name,
                                "args": dict(fc.args) if fc.args else {},
                                "phase": session.phase.value,
                            })

                            # Set voiceover flag immediately to prevent
                            # auto-continue Case C from re-triggering before
                            # background task sets it.
                            if fc.name == "generate_voiceover":
                                session.voiceover_playing = True

                            # ── 3. Execute tool + send response in BACKGROUND ──
                            # Tool execution (esp. image gen) can take 5-15s.
                            # Background task keeps agent_loop free for Live API keepalive.
                            _pending_tool_bg[0] += 1

                            async def _tool_background(
                                _fc=fc, _ls=live_session,
                            ):
                                try:
                                    fn_response, event = await tool_executor.execute(
                                        session, _fc, emit_cb=_emit_cb
                                    )
                                    logger.info(
                                        f"[{session.id}] Action: tool_done | Tool: {_fc.name}"
                                    )

                                    # Set voiceover flag BEFORE sending tool_response
                                    # to prevent race condition where auto-continue
                                    # fires Case C again before flag is set.
                                    if _fc.name == "generate_voiceover":
                                        session.voiceover_playing = True

                                    # Send tool_response to Live API
                                    await _ls.send_tool_response(
                                        function_responses=[fn_response]
                                    )
                                    logger.info(f"[{session.id}] Action: tool_response_sent | Tool: {_fc.name}")
                                    session.auto_continue_count = 0

                                    # Send results to frontend IMMEDIATELY
                                    if event:
                                        await send_json(ws, event)
                                        _store_event_on_session(session, event, pregen=pregen, emit_cb=None)

                                    # Voiceover safety timeout
                                    if _fc.name == "generate_voiceover" and event:
                                        async def _voiceover_safety_timeout(
                                            sid=session.id, __ls=_ls,
                                        ):
                                            await asyncio.sleep(90)
                                            if session.voiceover_playing:
                                                session.voiceover_playing = False
                                                logger.warning(f"[{sid}] Action: voiceover_safety_timeout")
                                                if not session.zip_url and session.brand_name:
                                                    try:
                                                        await __ls.send_client_content(
                                                            turns=[types.Content(
                                                                role="user",
                                                                parts=[types.Part.from_text(
                                                                    text="Voiceover playback timed out. "
                                                                    "Call finalize_brand_kit now."
                                                                )],
                                                            )],
                                                            turn_complete=True,
                                                        )
                                                    except Exception:
                                                        pass
                                        asyncio.create_task(_voiceover_safety_timeout())

                                except Exception as e:
                                    logger.error(
                                        f"[{session.id}] Action: tool_bg_error | "
                                        f"Tool: {_fc.name} | Error: {e}"
                                    )
                                finally:
                                    _pending_tool_bg[0] -= 1

                            asyncio.create_task(_tool_background(), name=f"tool-bg-{fc.name}")

                            # Clear pending_regen — agent executed a corrective tool call.
                            # The tool call IS the fix the user asked for.
                            if session.pending_regen:
                                logger.info(
                                    f"[{session.id}] Action: pending_regen_cleared | "
                                    f"Tool: {fc.name} | Target was: {session.pending_regen_target}"
                                )
                                session.pending_regen = False
                                session.pending_regen_target = None

                            # --- Interrupt check ---
                            # If user sent feedback during generation, stop auto-continuing.
                            # receive_loop already forwarded the text to Live API.
                            # Transition to AWAITING_INPUT so should_continue = False.
                            if session.interrupt_text or session.awaiting_feedback:
                                logger.info(
                                    f"[{session.id}] Action: interrupt_break | "
                                    f"Tool: {fc.name} | "
                                    f"Text: {(session.interrupt_text or '')[:80]} | "
                                    f"awaiting_feedback: {session.awaiting_feedback} | "
                                    f"Stopping auto-continue, waiting for user"
                                )
                                session.interrupt_text = None
                                brand_state.transition_phase(session, AgentPhase.AWAITING_INPUT)
                                await send_json(ws, {
                                    "type": "agent_turn_complete",
                                    "phase": session.phase.value,
                                })
                                break  # exit tool call loop — let agent process user feedback

                            if fc.name == "finalize_brand_kit":
                                logger.info(f"[{session.id}] Action: finalize_complete | Staying alive for feedback")
                                brand_state.transition_phase(session, AgentPhase.AWAITING_INPUT)
                                session.awaiting_feedback = False
                                await send_json(ws, {
                                    "type": "agent_turn_complete",
                                    "phase": session.phase.value,
                                })

                    if message.setup_complete:
                        logger.debug(f"[{session.id}] setup_complete (ignored)")

                else:
                    logger.warning(f"[{session.id}] Action: receive_stream_ended | Turn: {turn_count}")

            logger.info(f"[{session.id}] Action: agent_loop_finished | Turns: {turn_count} | Msgs: {msg_count}")

    except TimeoutError:
        logger.error(f"[{session.id}] Action: session_timeout | {SESSION_TIMEOUT_SEC}s | Turns: {turn_count}")
        await send_json(ws, {"type": "session_timeout", "message": f"Session timed out after {SESSION_TIMEOUT_SEC}s"})
    except Exception as e:
        logger.error(f"[{session.id}] Action: agent_loop_error | Error: {e} | Turns: {turn_count}")
        await send_json(ws, {"type": "error", "message": str(e)})
    finally:
        pass  # background tool tasks will finish on their own
