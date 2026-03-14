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

                    # --- User just chose a name → agent must speak comment, no tools ---
                    # Applies when brand_name is set but tagline isn't yet (post-name-choice),
                    # and the phase is AWAITING_NAME / AWAITING_INPUT / PROPOSING.
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

                    # During active brand flow (any phase after full brand exists),
                    # wrap user text so agent classifies feedback properly
                    elif session.phase in {
                        AgentPhase.AWAITING_INPUT,
                        AgentPhase.COMPLETE,
                        AgentPhase.REFINING,
                        AgentPhase.GENERATING,
                    } and session.brand_name:
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
                            # Agent should ONLY speak — acknowledge what changed and why.
                            # The pending_regen_nudge in turn_complete fires the actual tool call.
                            # This prevents the speech+tool combined turn that cuts off audio.
                            wrapped = (
                                f"USER INPUT: {text}\n{_ctx}\n"
                                "The user has feedback. Acknowledge it briefly (1-2 sentences). "
                                "Say what you'll change and why. "
                                "CRITICAL: Do NOT call any tools. Just speak, then STOP. "
                                "The system will trigger the correct tool automatically."
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


async def _dispatch_next_step(
    session: "Session",
    live_session: object,
    ws: "WebSocket",
    turn_count: int,
    _pending_tool_bg: list,
) -> None:
    """State-machine driven auto-continue.

    Speech and tool calls are always dispatched as SEPARATE turns so the model
    never speaks and calls a tool simultaneously (which cuts off audio when the
    fast tool_response arrives before audio generation finishes).

    Each _SPEECH phase tells the agent: "speak X, do NOT call any tools, STOP."
    Each _TOOL phase tells the agent: "call X tool, do NOT speak."
    """
    # Guards
    if session.interrupt_text or session.awaiting_feedback or session.pending_regen:
        return
    if _pending_tool_bg[0] > 0:
        logger.info(f"[{session.id}] Action: dispatch_deferred | Pending tools: {_pending_tool_bg[0]}")
        return
    if session.voiceover_playing:
        logger.info(f"[{session.id}] Action: dispatch_deferred | Voiceover playing")
        return
    if session.zip_url:
        return

    phase = session.phase
    _MAX = 8

    if session.auto_continue_count >= _MAX:
        if session.brand_name and not session.zip_url:
            logger.warning(f"[{session.id}] Action: dispatch_exhausted | Attempts: {session.auto_continue_count}")
        return

    # ── ANALYSIS_SPEECH → AWAITING_NAME (pregen) or PROPOSING (fallback) ────
    if phase == AgentPhase.ANALYSIS_SPEECH:
        session.auto_continue_count += 1
        pregen_names = getattr(session, "_pregen_names", None)
        if pregen_names:
            # Names were pre-generated in parallel. Tell Live API what they are
            # for conversation context, then wait for user choice.
            brand_state.transition_phase(session, AgentPhase.AWAITING_NAME)
            names_text = ", ".join(f"'{n['name']}'" for n in pregen_names)
            nudge = (
                f"You proposed these brand names: {names_text}. "
                f"The user is choosing now. Wait for their selection. "
                f"Do NOT speak. Do NOT call any tools."
            )
            logger.info(f"[{session.id}] Action: dispatch_awaiting_name_pregen | Turn: {turn_count}")
        else:
            # Fallback: pre-gen failed, ask Live API to call propose_names tool
            brand_state.transition_phase(session, AgentPhase.PROPOSING)
            nudge = (
                "Now call propose_names with 3 brand name options. "
                "Do NOT speak. Just call the tool immediately."
            )
            logger.info(f"[{session.id}] Action: dispatch_propose_names_fallback | Turn: {turn_count}")
        asyncio.create_task(_wait_and_nudge(session, live_session, nudge, "post_analysis"))

    # ── AWAITING_NAME: name chosen, no tagline yet → REVEAL_SPEECH ───────────
    # Guard: if the user already chose a name (brand_name set) and propose_names
    # completed late (after user input), skip dispatching here entirely.
    # The user-input path already set phase=REVEAL_SPEECH and sent a speech nudge,
    # which will advance to REVEAL_TOOL on turn_complete. Adding another nudge here
    # would cause duplicate speech or a skipped REVEAL_SPEECH turn.
    elif phase == AgentPhase.AWAITING_NAME and session.brand_name and not session.tagline:
        logger.info(
            f"[{session.id}] Action: dispatch_awaiting_name_skip | "
            f"Brand already chosen: {session.brand_name} | "
            f"REVEAL_TOOL nudge already in-flight from user-input path"
        )

    # ── REVEAL_SPEECH done → call reveal_brand_identity ──────────────────────
    elif phase == AgentPhase.REVEAL_SPEECH:
        brand_state.transition_phase(session, AgentPhase.REVEAL_TOOL)
        session.auto_continue_count += 1
        nudge = (
            "Now call reveal_brand_identity with brand_name, tagline, brand_story, "
            "brand_values, and tone_of_voice_do/dont. Do NOT speak. Just call the tool."
        )
        logger.info(f"[{session.id}] Action: dispatch_reveal_tool | Turn: {turn_count}")
        asyncio.create_task(_wait_and_nudge(session, live_session, nudge, "reveal_tool"))

    # ── REVEAL_TOOL done, no palette → PALETTE_SPEECH + PALETTE_TOOL (combined) ─
    # Send both nudges as a single turn: speak about palette, then immediately
    # call the tool. This avoids the double-empty-turn race where two consecutive
    # turn_complete events cause palette_speech and palette_tool nudges to be
    # dispatched back-to-back before the agent processes either.
    elif phase == AgentPhase.REVEAL_TOOL and session.tagline and not session.palette:
        brand_state.transition_phase(session, AgentPhase.PALETTE_TOOL)
        session.auto_continue_count += 1
        nudge = (
            "Say ONE sentence about the palette direction for this brand — mention a specific hue or mood. "
            "Then immediately call generate_palette with 5 colors. Do NOT wait."
        )
        logger.info(f"[{session.id}] Action: dispatch_palette_combined | Turn: {turn_count}")
        asyncio.create_task(_wait_and_nudge(session, live_session, nudge, "palette_combined"))

    # ── PALETTE_SPEECH done → call generate_palette ───────────────────────────
    elif phase == AgentPhase.PALETTE_SPEECH:
        brand_state.transition_phase(session, AgentPhase.PALETTE_TOOL)
        session.auto_continue_count += 1
        nudge = (
            "Now call generate_palette with 5 colors. "
            "Do NOT speak. Just call the tool."
        )
        logger.info(f"[{session.id}] Action: dispatch_palette_tool | Turn: {turn_count}")
        asyncio.create_task(_wait_and_nudge(session, live_session, nudge, "palette_tool"))

    # ── PALETTE_TOOL done, no fonts → FONTS_SPEECH ───────────────────────────
    elif phase == AgentPhase.PALETTE_TOOL and session.palette and not session.font_suggestion:
        brand_state.transition_phase(session, AgentPhase.FONTS_SPEECH)
        session.auto_continue_count += 1
        nudge = (
            "Say ONE sentence connecting typography to this brand's personality — "
            "mention the feeling you want or how it complements the palette. "
            "Do NOT use generic phrases. Do NOT call any tools. Just speak, then STOP."
        )
        logger.info(f"[{session.id}] Action: dispatch_fonts_speech | Turn: {turn_count}")
        asyncio.create_task(_wait_and_nudge(session, live_session, nudge, "fonts_speech"))

    # ── FONTS_SPEECH done → call suggest_fonts ────────────────────────────────
    elif phase == AgentPhase.FONTS_SPEECH:
        brand_state.transition_phase(session, AgentPhase.FONTS_TOOL)
        session.auto_continue_count += 1
        nudge = (
            "Now call suggest_fonts with heading and body fonts. "
            "Do NOT speak. Just call the tool."
        )
        logger.info(f"[{session.id}] Action: dispatch_fonts_tool | Turn: {turn_count}")
        asyncio.create_task(_wait_and_nudge(session, live_session, nudge, "fonts_tool"))

    # ── FONTS_TOOL or IMAGE_TOOL done → next image or closing ─────────────────
    elif phase in (AgentPhase.FONTS_TOOL, AgentPhase.IMAGE_TOOL):
        remaining_types = [
            a for a in ["logo", "hero_lifestyle", "instagram_post"]
            if a not in session.completed_assets
        ]
        if remaining_types:
            next_asset = remaining_types[0]
            label = {"logo": "logo", "hero_lifestyle": "lifestyle hero",
                     "instagram_post": "Instagram post"}.get(next_asset, next_asset)
            brand_state.transition_phase(session, AgentPhase.IMAGE_SPEECH)
            session.auto_continue_count += 1
            nudge = (
                f"Say ONE sentence teasing the creative direction for the {label} — "
                f"reference the brand's palette or mood. Be specific. "
                f"Do NOT call any tools. Just speak, then STOP."
            )
            logger.info(f"[{session.id}] Action: dispatch_image_speech | Asset: {next_asset} | Turn: {turn_count}")
            asyncio.create_task(_wait_and_nudge(session, live_session, nudge, f"image_speech:{next_asset}"))
        elif not session.voiceover_sent:
            brand_state.transition_phase(session, AgentPhase.VOICEOVER_SPEECH)
            session.auto_continue_count += 1
            nudge = (
                "All brand assets are complete. "
                "Say ONE sentence that ties the creative journey together and introduces Anna "
                "who will narrate the brand story — weave in something specific about THIS brand. "
                "Do NOT call any tools. Just speak, then STOP."
            )
            logger.info(f"[{session.id}] Action: dispatch_voiceover_speech | Turn: {turn_count}")
            asyncio.create_task(_wait_and_nudge(session, live_session, nudge, "voiceover_speech"))

    # ── IMAGE_SPEECH done → call generate_image ───────────────────────────────
    elif phase == AgentPhase.IMAGE_SPEECH:
        remaining_types = [
            a for a in ["logo", "hero_lifestyle", "instagram_post"]
            if a not in session.completed_assets
        ]
        if remaining_types:
            next_asset = remaining_types[0]
            brand_state.transition_phase(session, AgentPhase.IMAGE_TOOL)
            session.auto_continue_count += 1
            nudge = (
                f"Now call generate_image with asset_type '{next_asset}'. "
                f"Do NOT speak. Just call the tool."
            )
            logger.info(f"[{session.id}] Action: dispatch_image_tool | Asset: {next_asset} | Turn: {turn_count}")
            asyncio.create_task(_wait_and_nudge(session, live_session, nudge, f"image_tool:{next_asset}"))

    # ── VOICEOVER_SPEECH done → call generate_voiceover ──────────────────────
    elif phase == AgentPhase.VOICEOVER_SPEECH:
        brand_state.transition_phase(session, AgentPhase.VOICEOVER_TOOL)
        session.auto_continue_count += 1
        nudge = (
            "Now call generate_voiceover with ALL FOUR parameters:\n"
            "- handoff_text: one sentence handing over to Anna (brand-specific)\n"
            "- greeting_text: Anna's short self-introduction, 1-2 sentences\n"
            "- narration_text: Anna's full brand story narration — story ONLY, no greeting\n"
            "- mood: brand mood\n"
            "Do NOT speak. Call the tool immediately."
        )
        logger.info(f"[{session.id}] Action: dispatch_voiceover_tool | Turn: {turn_count}")
        asyncio.create_task(_wait_and_nudge(session, live_session, nudge, "voiceover_tool"))

    # ── Legacy AWAITING_INPUT fallback for user-interrupt recovery ────────────
    elif phase == AgentPhase.AWAITING_INPUT and session.brand_name and not session.zip_url:
        # Determine what to do next based on session state
        remaining_types = [
            a for a in ["logo", "hero_lifestyle", "instagram_post"]
            if a not in session.completed_assets
        ]
        if not session.tagline:
            brand_state.transition_phase(session, AgentPhase.REVEAL_SPEECH)
            session.auto_continue_count += 1
            nudge = (
                f"The user chose the name '{session.brand_name}'. "
                "Say a confident comment about why this name fits (max 2 sentences). "
                "End with 'Let me build out the full brand identity.' "
                "Do NOT call any tools. Just speak, then STOP."
            )
            asyncio.create_task(_wait_and_nudge(session, live_session, nudge, "reveal_speech_recovery"))
        elif not session.palette:
            brand_state.transition_phase(session, AgentPhase.PALETTE_SPEECH)
            session.auto_continue_count += 1
            nudge = (
                "Say ONE sentence about the palette direction — mention a specific hue or mood. "
                "Do NOT call any tools. Just speak, then STOP."
            )
            asyncio.create_task(_wait_and_nudge(session, live_session, nudge, "palette_speech_recovery"))
        elif not session.font_suggestion:
            brand_state.transition_phase(session, AgentPhase.FONTS_SPEECH)
            session.auto_continue_count += 1
            nudge = (
                "Say ONE sentence connecting typography to this brand's personality. "
                "Do NOT call any tools. Just speak, then STOP."
            )
            asyncio.create_task(_wait_and_nudge(session, live_session, nudge, "fonts_speech_recovery"))
        elif remaining_types:
            next_asset = remaining_types[0]
            label = {"logo": "logo", "hero_lifestyle": "lifestyle hero",
                     "instagram_post": "Instagram post"}.get(next_asset, next_asset)
            brand_state.transition_phase(session, AgentPhase.IMAGE_SPEECH)
            session.auto_continue_count += 1
            nudge = (
                f"Say ONE sentence teasing the creative direction for the {label}. "
                f"Do NOT call any tools. Just speak, then STOP."
            )
            asyncio.create_task(_wait_and_nudge(session, live_session, nudge, f"image_speech_recovery:{next_asset}"))
        elif not session.voiceover_sent:
            brand_state.transition_phase(session, AgentPhase.VOICEOVER_SPEECH)
            session.auto_continue_count += 1
            nudge = (
                "Say ONE sentence introducing Anna who will narrate the brand story. "
                "Do NOT call any tools. Just speak, then STOP."
            )
            asyncio.create_task(_wait_and_nudge(session, live_session, nudge, "voiceover_speech_recovery"))
        logger.info(f"[{session.id}] Action: dispatch_awaiting_input_recovery | Phase: {phase} | Turn: {turn_count}")


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
                _tool_called_this_turn = False
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
                        if sc.model_turn and sc.model_turn.parts:
                            for part in sc.model_turn.parts:
                                if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
                                    # Suppress agent audio while Anna is narrating or interrupt active
                                    if session.voiceover_playing or session.interrupt_text:
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
                                    # SKIP model_turn text — use output_transcription instead.
                                    # Native audio model generates both text and audio in parallel,
                                    # but they often say slightly different things, causing duplicates.
                                    # output_transcription is the accurate version of what was spoken.
                                    pass

                        # output_transcription — the ONLY text source for native audio.
                        # Skip emitting a partial when turn_complete is also set on this
                        # message — the turn_complete flush sends partial=False with the
                        # full buffer, so emitting a partial here first would cause the
                        # frontend to see the last sentence twice.
                        if (sc.output_transcription and sc.output_transcription.text
                                and not session.voiceover_playing
                                and not session.interrupt_text):
                            text = sc.output_transcription.text
                            agent_text_buffer.append(text)
                            if not sc.turn_complete:
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
                                if _tool_called_this_turn:
                                    # Tool executor already emitted structured events via emit_cb.
                                    # Don't re-parse text for tags — just close the partial with
                                    # the spoken narration (no structured event extraction).
                                    # Strip any raw tags from transcription before displaying.
                                    _, clean_narration = parse_agent_text(full_text, seen_types=seen_event_types)
                                    await send_json(ws, {
                                        "type": "agent_text",
                                        "text": clean_narration or "",
                                        "partial": False,
                                    })
                                    session.add_transcript("agent", full_text)
                                else:
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
                                # Opening turn complete → agent speaks analysis (SPEECH only, no tools)
                                brand_state.transition_phase(session, AgentPhase.ANALYSIS_SPEECH)
                                await send_json(ws, {
                                    "type": "agent_turn_complete",
                                    "phase": session.phase.value,
                                })
                                nudge = (
                                    "Now analyze the product photo. "
                                    "Say what you see (2 sentences, cite specific visual evidence). "
                                    "Then pick ONE creative direction (1 sentence). "
                                    "Then say a creative transition line for the names (1 sentence, varied). "
                                    "Do NOT call any tools. Just speak, then STOP."
                                )
                                logger.info(f"[{session.id}] Action: auto_nudge_analysis_speech | Turn: {turn_count}")
                                await live_session.send_client_content(
                                    turns=[types.Content(
                                        role="user",
                                        parts=[types.Part.from_text(text=nudge)],
                                    )],
                                    turn_complete=True,
                                )

                                # --- PARALLEL: pre-generate name proposals via text model ---
                                # Cards appear on frontend while agent is still speaking analysis.
                                # When analysis audio ends, countdown starts.
                                async def _pregen_names(_ws=ws, _session=session):
                                    try:
                                        from services.gemini_live import create_client as _cc
                                        _tc = _cc()

                                        _img_part = types.Part.from_bytes(
                                            data=_session.product_image_bytes,
                                            mime_type=_session.product_image_mime or "image/jpeg",
                                        )

                                        _prompt = (
                                            "You are an elite creative director naming a brand based on this product photo.\n"
                                            "Respond with ONLY this JSON, no markdown:\n"
                                            '{"names": [\n'
                                            '  {"name": "...", "rationale": "...", "recommended": true},\n'
                                            '  {"name": "...", "rationale": "..."},\n'
                                            '  {"name": "...", "rationale": "..."}\n'
                                            ']}\n\n'
                                            "Rules:\n"
                                            "- EXACTLY 3 names, each 1-2 words\n"
                                            "- Each name uses a DIFFERENT creative approach: "
                                            "one abstract/invented, one evocative/emotional, one descriptive/poetic\n"
                                            "- Rationale: 1 sentence explaining the name's connection to the product\n"
                                            "- Mark ONE as recommended: true\n"
                                            "- Names must be original, ownable, memorable\n"
                                            "- Ground every name in specific visual evidence from the photo"
                                        )

                                        _resp = await _tc.aio.models.generate_content(
                                            model="gemini-2.5-flash",
                                            contents=[_img_part, _prompt],
                                            config=types.GenerateContentConfig(
                                                response_mime_type="application/json",
                                            ),
                                        )

                                        _text = _resp.text.strip()
                                        if _text.startswith("```"):
                                            _text = _text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                                        _data = json.loads(_text)
                                        _raw_names = _data.get("names", [])

                                        validated = []
                                        for i, n in enumerate(_raw_names[:3]):
                                            if isinstance(n, dict) and n.get("name"):
                                                entry = {
                                                    "id": i + 1,
                                                    "name": n["name"],
                                                    "rationale": n.get("rationale", ""),
                                                }
                                                if n.get("recommended"):
                                                    entry["recommended"] = True
                                                validated.append(entry)

                                        if validated:
                                            # Send cards to frontend — appear while agent speaks
                                            await send_json(_ws, {
                                                "type": "name_proposals",
                                                "names": validated,
                                                "auto_select_seconds": 10,
                                            })
                                            # Store on session so _dispatch_next_step can use them
                                            _session._pregen_names = validated
                                            logger.info(
                                                f"[{_session.id}] Action: pregen_names_sent | "
                                                f"Names: {[n['name'] for n in validated]}"
                                            )
                                    except Exception as e:
                                        logger.warning(
                                            f"[{session.id}] Action: pregen_names_failed | Error: {e}"
                                        )

                                asyncio.create_task(_pregen_names(), name="pregen-names")
                                break

                            # Normalise legacy GENERATING/PROPOSING → AWAITING_INPUT so
                            # _dispatch_next_step can route based on micro-phase.
                            if session.phase == AgentPhase.GENERATING:
                                brand_state.transition_phase(session, AgentPhase.AWAITING_INPUT)
                            # After propose_names, phase stays AWAITING_NAME even while agent
                            # speaks REVEAL_SPEECH. Normalize to REVEAL_TOOL so dispatch
                            # knows the speech turn is done and the tool nudge is in-flight.
                            elif (session.phase == AgentPhase.AWAITING_NAME
                                    and session.brand_name
                                    and not session.tagline
                                    and full_text.strip()):
                                brand_state.transition_phase(session, AgentPhase.REVEAL_TOOL)

                            logger.info(f"[{session.id}] Action: turn_complete | Turn: {turn_count} | Msgs: {msg_count}")
                            await send_json(ws, {
                                "type": "agent_turn_complete",
                                "phase": session.phase.value,
                            })

                            # --- Pending-regen nudge (user asked to change something) ---
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

                            # State-machine dispatch — speech and tool turns are always separate.
                            # Skip dispatch on empty turns: agent acknowledged a nudge without
                            # speaking. _wait_and_nudge already has the next nudge scheduled —
                            # dispatching again here would send a duplicate nudge.
                            if full_text.strip():
                                await _dispatch_next_step(session, live_session, ws, turn_count, _pending_tool_bg)

                            break

                    # Tool calls from agent
                    if message.tool_call:
                        _tool_called_this_turn = True
                        for fc in message.tool_call.function_calls:
                            # NOTE: Do NOT flush agent_text_buffer here.
                            # In combined speech+tool turns, transcription chunks arrive
                            # before AND after the tool_call message. Flushing mid-turn
                            # splits them into two separate chat messages (duplicate text).
                            # turn_complete handles all text at once.

                            brand_state.infer_phase_from_tool(session, fc.name)

                            # ── 2. Send spinner immediately (frontend queues if audio playing) ──
                            await send_json(ws, {
                                "type": "tool_invoked",
                                "tool": fc.name,
                                "args": dict(fc.args) if fc.args else {},
                                "phase": session.phase.value,
                            })

                            # ── 2b. For propose_names: send cards IMMEDIATELY ──
                            # fc.args already contains the names — no need to wait
                            # for background task. Cards reach frontend while analysis
                            # audio is still playing (tool call fires right after speech).
                            if fc.name == "propose_names":
                                args_dict = dict(fc.args) if fc.args else {}
                                raw_names = args_dict.get("names", [])
                                validated = []
                                for i, n in enumerate(raw_names[:3]):
                                    if isinstance(n, dict) and n.get("name"):
                                        entry = {
                                            "id": i + 1,
                                            "name": n["name"],
                                            "rationale": n.get("rationale", ""),
                                        }
                                        if n.get("recommended"):
                                            entry["recommended"] = True
                                        validated.append(entry)
                                if validated:
                                    early_event = {
                                        "type": "name_proposals",
                                        "names": validated,
                                        "auto_select_seconds": 8,
                                    }
                                    await send_json(ws, early_event)
                                    logger.info(
                                        f"[{session.id}] Action: name_proposals_early | "
                                        f"Names: {[n['name'] for n in validated]}"
                                    )

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
                                    # Guard: skip duplicate generate_voiceover calls.
                                    # Gemini Live can self-interrupt and retry the tool
                                    # call, which would produce two overlapping audios.
                                    if _fc.name == "generate_voiceover":
                                        if session.voiceover_sent:
                                            logger.info(
                                                f"[{session.id}] Action: voiceover_dup_skip | "
                                                f"generate_voiceover already executed, ignoring duplicate"
                                            )
                                            return
                                        session.voiceover_sent = True

                                    fn_response, event = await tool_executor.execute(
                                        session, _fc, emit_cb=_emit_cb
                                    )
                                    logger.info(
                                        f"[{session.id}] Action: tool_done | Tool: {_fc.name}"
                                    )

                                    # Wait for frontend audio to finish before sending
                                    # tool_response back to Live API for fast tools.
                                    # Fast tools complete in <100ms — if we send tool_response
                                    # immediately, Live API stops the agent's current audio
                                    # mid-sentence to start processing the tool result.
                                    # Slow tools (generate_image) take 5-15s so audio is done.
                                    #
                                    # IMPORTANT: only wait if this turn actually has audio.
                                    # TOOL-only phases (no preceding speech) never produce audio,
                                    # so waiting would deadlock — frontend_ready is never set
                                    # because audio_playback_done never fires.
                                    _FAST_TOOLS = {
                                        "reveal_brand_identity", "suggest_fonts",
                                        "generate_palette", "propose_names",
                                    }
                                    # Phases where the agent goes straight to a tool call
                                    # without a speech preamble — no audio in this turn.
                                    _TOOL_ONLY_PHASES = {
                                        AgentPhase.REVEAL_TOOL, AgentPhase.PALETTE_TOOL,
                                        AgentPhase.FONTS_TOOL, AgentPhase.IMAGE_TOOL,
                                        AgentPhase.VOICEOVER_TOOL, AgentPhase.PROPOSING,
                                    }
                                    if _fc.name in _FAST_TOOLS and session.phase not in _TOOL_ONLY_PHASES:
                                        if not hasattr(session, "frontend_ready"):
                                            session.frontend_ready = asyncio.Event()
                                        session.frontend_ready.clear()
                                        try:
                                            await asyncio.wait_for(
                                                session.frontend_ready.wait(), timeout=15.0
                                            )
                                            logger.info(
                                                f"[{session.id}] Action: fast_tool_audio_done | "
                                                f"Tool: {_fc.name} | Sending tool_response"
                                            )
                                        except asyncio.TimeoutError:
                                            logger.warning(
                                                f"[{session.id}] Action: fast_tool_audio_wait_timeout | "
                                                f"Tool: {_fc.name} | Proceeding after 15s"
                                            )

                                    # Set voiceover flag BEFORE sending tool_response
                                    # to prevent race condition where auto-continue
                                    # fires Case C again before flag is set.
                                    if _fc.name == "generate_voiceover":
                                        session.voiceover_playing = True

                                    # propose_names was already sent early (before background task).
                                    # Suppress duplicate here to avoid double render.
                                    if _fc.name == "propose_names":
                                        event = None

                                    # Send tool_response to Live API
                                    await _ls.send_tool_response(
                                        function_responses=[fn_response]
                                    )
                                    logger.info(f"[{session.id}] Action: tool_response_sent | Tool: {_fc.name}")
                                    session.auto_continue_count = 0

                                    # Send results to frontend (non-propose_names tools)
                                    if event:
                                        await send_json(ws, event)
                                        _store_event_on_session(session, event, pregen=pregen, emit_cb=None)

                                    # Advance micro-phase after tool completion so
                                    # _dispatch_next_step knows which step comes next.
                                    if _fc.name == "propose_names":
                                        brand_state.transition_phase(session, AgentPhase.AWAITING_NAME)
                                    elif _fc.name == "reveal_brand_identity":
                                        brand_state.transition_phase(session, AgentPhase.REVEAL_TOOL)
                                    elif _fc.name == "generate_palette":
                                        brand_state.transition_phase(session, AgentPhase.PALETTE_TOOL)
                                    elif _fc.name == "suggest_fonts":
                                        brand_state.transition_phase(session, AgentPhase.FONTS_TOOL)
                                    elif _fc.name == "generate_image":
                                        brand_state.transition_phase(session, AgentPhase.IMAGE_TOOL)

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
                                    if _pending_tool_bg[0] == 0:
                                        # Skip dispatch after propose_names when the user
                                        # already chose a name — a REVEAL_TOOL nudge is
                                        # already in-flight from the user-input path.
                                        # Dispatching again would send a duplicate nudge
                                        # and cause the REVEAL_SPEECH text to appear twice.
                                        _skip_dispatch = (
                                            _fc.name == "propose_names"
                                            and session.brand_name
                                            and session.phase in (
                                                AgentPhase.REVEAL_TOOL,
                                                AgentPhase.REVEAL_SPEECH,
                                            )
                                        )
                                        if _skip_dispatch:
                                            logger.info(
                                                f"[{session.id}] Action: dispatch_skip_after_propose | "
                                                f"Phase: {session.phase.value} | "
                                                f"Brand already chosen: {session.brand_name}"
                                            )
                                        else:
                                            logger.info(
                                                f"[{session.id}] Action: dispatch_retry_after_tool | "
                                                f"Tool: {_fc.name} | Phase: {session.phase.value}"
                                            )
                                            try:
                                                await _dispatch_next_step(
                                                    session, live_session, ws, turn_count, _pending_tool_bg
                                                )
                                            except Exception as e:
                                                logger.error(
                                                    f"[{session.id}] Action: dispatch_retry_failed | Error: {e}"
                                                )

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
