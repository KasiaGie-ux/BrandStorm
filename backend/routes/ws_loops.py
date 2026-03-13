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
from services.voiceover import generate_voiceover

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
        # Fire voiceover in background immediately — don't wait for agent.
        # Only stores result on session; the agent's generate_voiceover tool
        # call will emit the event to frontend (so it appears at the right
        # moment in the chat, preceded by agent narration).
        if not session.audio_url:
            _storage = StorageService()

            async def _bg_voiceover():
                try:
                    wav = await generate_voiceover(
                        session_id=session.id,
                        text=event["story"],
                        mood="luxury",
                    )
                    if wav:
                        url = await _storage.upload_image(
                            session_id=session.id,
                            asset_type="voiceover",
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


# short delay inserted between consecutive structured events so that the
# frontend can reveal them one‑by‑one rather than having everything appear
# simultaneously when a single Live API turn contains a bunch of tags.
# The previous behaviour was the source of the "everything at once" bug
# when the agent output a name, tagline, story, values, palette, fonts, etc.
_EVENT_STAGGER_DELAY = 1.2   # seconds – enough for each card to animate in & be read

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
    if not text:
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
        if data.get("type") in ("image_generated", "palette_reveal", "generation_complete"):
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

                # If a tool is currently executing, queue feedback for relay
                # between tool calls so the agent sees it at a safe point.
                if session.phase == AgentPhase.GENERATING:
                    session.interrupt_text = text
                    logger.info(
                        f"[{session.id}] Action: interrupt_queued | "
                        f"Text: {text[:80]} | Phase: GENERATING"
                    )
                else:
                    # During AWAITING_INPUT with active brand flow,
                    # wrap user text so agent classifies feedback properly
                    if session.phase == AgentPhase.AWAITING_INPUT and session.brand_name:
                        wrapped = (
                            f"USER INPUT: {text}\n"
                            "Classify: if positive/neutral → continue the flow. "
                            "If negative about something specific → fix that thing only. "
                            "If vague negative → ask what to change. "
                            "If name change → propose 3 new names."
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
                    "Here is the product photo. Start immediately — analyze what you see, "
                    "pick the best creative direction yourself, then start "
                    "generating the full brand kit. Go."
                )
                if user_context:
                    prompt += f"\n\nAdditional context from the client: {user_context}"

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

    async def _emit_cb(ev: dict):
        """Callback for pregen to emit events to frontend."""
        await send_json(ws, ev)

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
                            logger.info(
                                f"[{session.id}] Action: turn_text_flush | "
                                f"Turn: {turn_count} | Text length: {len(full_text)} | "
                                f"Preview: {full_text[:120]}"
                            )
                            await _flush_and_emit(
                                ws, session, full_text, seen_event_types,
                                pregen=pregen, emit_cb=_emit_cb,
                            )
                            agent_text_buffer.clear()

                            if session.phase == AgentPhase.ANALYZING:
                                brand_state.transition_phase(session, AgentPhase.PROPOSING)
                                brand_state.transition_phase(session, AgentPhase.AWAITING_INPUT)
                            elif session.phase == AgentPhase.GENERATING:
                                brand_state.transition_phase(session, AgentPhase.AWAITING_INPUT)

                            logger.info(f"[{session.id}] Action: turn_complete | Turn: {turn_count} | Msgs: {msg_count}")
                            await send_json(ws, {
                                "type": "agent_turn_complete",
                                "phase": session.phase.value,
                            })

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
                            )

                            if should_continue and not session.palette:
                                # Case A: brand name chosen but no palette yet
                                session.auto_continue_count += 1
                                nudge = (
                                    "Great. Now call generate_palette with your chosen colors. "
                                    "After that, output your font pairing using [FONT_SUGGESTION] tags. "
                                    "Do NOT mention logo or images yet — just colors and fonts."
                                )
                                logger.info(
                                    f"[{session.id}] Action: auto_continue_palette | "
                                    f"Attempt: {session.auto_continue_count}/{_MAX_AUTO_CONTINUE}"
                                )
                                brand_state.transition_phase(session, AgentPhase.GENERATING)
                                await live_session.send_client_content(
                                    turns=[types.Content(
                                        role="user",
                                        parts=[types.Part.from_text(text=nudge)],
                                    )],
                                    turn_complete=True,
                                )
                            elif should_continue and session.palette and remaining > 0:
                                # Case B: palette done, images remaining
                                session.auto_continue_count += 1
                                done = ", ".join(session.completed_assets) or "none"
                                if not session.completed_assets:
                                    nudge = (
                                        "Continue. Output exactly ONE short evocative sentence about the logo, "
                                        "then IMMEDIATELY call generate_image with asset_type 'logo'. "
                                        "Do NOT output more than one sentence. Do NOT repeat yourself."
                                    )
                                else:
                                    remaining_types = [
                                        a for a in ["logo", "hero_lifestyle", "instagram_post"]
                                        if a not in session.completed_assets
                                    ]
                                    next_asset = remaining_types[0] if remaining_types else "next"
                                    label = {"hero_lifestyle": "lifestyle hero", "instagram_post": "Instagram post"}.get(next_asset, next_asset)
                                    nudge = (
                                        f"Continue. Output exactly ONE short evocative sentence about the {label}, "
                                        f"then IMMEDIATELY call generate_image with asset_type '{next_asset}'. "
                                        f"Do NOT output more than one sentence. Do NOT repeat yourself."
                                    )
                                logger.info(
                                    f"[{session.id}] Action: auto_continue | "
                                    f"Attempt: {session.auto_continue_count}/{_MAX_AUTO_CONTINUE} | "
                                    f"Done: {done} | Remaining: {remaining}"
                                )
                                brand_state.transition_phase(session, AgentPhase.GENERATING)
                                await live_session.send_client_content(
                                    turns=[types.Content(
                                        role="user",
                                        parts=[types.Part.from_text(text=nudge)],
                                    )],
                                    turn_complete=True,
                                )
                            elif should_continue and session.palette and remaining == 0 and not session.zip_url:
                                # Case C: all images done but not finalized yet
                                session.auto_continue_count += 1
                                if not session.audio_url:
                                    nudge = (
                                        "All images are done. Now call generate_voiceover with the brand story, "
                                        "then call finalize_brand_kit. You MUST call the tools."
                                    )
                                else:
                                    nudge = (
                                        "Everything is ready. Now call finalize_brand_kit with "
                                        "brand_name, tagline, brand_story, brand_values, and tone_of_voice. "
                                        "You MUST call the tool."
                                    )
                                logger.info(
                                    f"[{session.id}] Action: auto_continue_finalize | "
                                    f"Attempt: {session.auto_continue_count}/{_MAX_AUTO_CONTINUE} | "
                                    f"Audio: {bool(session.audio_url)}"
                                )
                                brand_state.transition_phase(session, AgentPhase.GENERATING)
                                await live_session.send_client_content(
                                    turns=[types.Content(
                                        role="user",
                                        parts=[types.Part.from_text(text=nudge)],
                                    )],
                                    turn_complete=True,
                                )
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
                            buffered = "".join(agent_text_buffer)
                            if buffered:
                                await _flush_and_emit(
                                    ws, session, buffered, seen_event_types,
                                    pregen=pregen, emit_cb=_emit_cb,
                                )
                                agent_text_buffer.clear()

                            brand_state.infer_phase_from_tool(session, fc.name)
                            await send_json(ws, {
                                "type": "tool_invoked",
                                "tool": fc.name,
                                "args": dict(fc.args) if fc.args else {},
                                "phase": session.phase.value,
                            })

                            fn_response, event = await tool_executor.execute(
                                session, fc, emit_cb=_emit_cb
                            )

                            if event:
                                await send_json(ws, event)

                            await live_session.send_tool_response(
                                function_responses=[fn_response]
                            )
                            logger.info(f"[{session.id}] Action: tool_response_sent | Tool: {fc.name}")

                            # Reset auto-continue counter — the agent responded
                            # with a tool call so it's alive. Allow fresh nudges
                            # after the next potential gap.
                            session.auto_continue_count = 0

                            # --- Interrupt check ---
                            # If the user sent feedback while a tool was executing,
                            # relay it to the Live API NOW so the agent sees it
                            # before deciding its next action.
                            if session.interrupt_text:
                                interrupt = session.interrupt_text
                                session.interrupt_text = None
                                logger.info(
                                    f"[{session.id}] Action: interrupt_relayed | "
                                    f"Text: {interrupt[:80]}"
                                )

                                # Quick heuristic: is this positive or negative?
                                _lower = interrupt.lower().strip()
                                _positive_signals = [
                                    "super", "ok", "great", "love", "nice",
                                    "perfect", "good", "yes", "tak", "dobr",
                                    "swietn", "fajn", "podoba", "continue",
                                    "dalej", "kontynuuj", "👍", "👏",
                                ]
                                _is_positive = any(s in _lower for s in _positive_signals)

                                if _is_positive:
                                    # Positive feedback — just relay and let agent continue
                                    await live_session.send_client_content(
                                        turns=[types.Content(
                                            role="user",
                                            parts=[types.Part.from_text(
                                                text=(
                                                    f"USER FEEDBACK (positive): {interrupt}\n"
                                                    "The user is happy. Acknowledge in max 1 sentence, "
                                                    "then continue the flow exactly where you left off."
                                                ),
                                            )],
                                        )],
                                        turn_complete=True,
                                    )
                                else:
                                    # Negative or ambiguous — cancel pregen, classify
                                    if pregen:
                                        pregen.cancel(session)
                                    await live_session.send_client_content(
                                        turns=[types.Content(
                                            role="user",
                                            parts=[types.Part.from_text(
                                                text=(
                                                    f"USER FEEDBACK (needs attention): {interrupt}\n"
                                                    "STOP generating new assets. Classify the feedback:\n"
                                                    "- NEGATIVE about a SPECIFIC asset (e.g. 'change the logo', "
                                                    "'darker colors') → acknowledge, regenerate ONLY that asset, "
                                                    "then continue from where you were.\n"
                                                    "- NEGATIVE but VAGUE (e.g. 'I don't like it', 'start over') → "
                                                    "ASK what specifically they want changed. Be direct: "
                                                    "'What would you like me to change — the name, colors, fonts, "
                                                    "or something else?' Do NOT guess.\n"
                                                    "- NAME CHANGE (e.g. 'I don't like the name', 'rename it') → "
                                                    "propose 3 new names, then redo ALL brand identity + assets.\n"
                                                    "React like a smart creative director."
                                                ),
                                            )],
                                        )],
                                        turn_complete=True,
                                    )

                            if fc.name == "finalize_brand_kit":
                                logger.info(f"[{session.id}] Action: finalize_complete")
                                session_active = False

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
