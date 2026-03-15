# UNUSED — superseded by routes/agent_loop.py + routes/receive_loop.py
"""Shared WebSocket helpers used by ws_receive, ws_dispatch, ws_agent."""

import asyncio
import logging

from fastapi import WebSocket
from google.genai import types

from models.session import Session
from services.pregen import PreGenerator
from services.storage import StorageService
from services.text_parser import parse_agent_text

logger = logging.getLogger("brand-agent")

# Short delay between consecutive structured events in _flush_and_emit.
# Frontend's useEventQueue handles the real visual stagger while audio plays.
# This is just a safety gap so the WebSocket doesn't batch events into one frame.
_EVENT_STAGGER_DELAY = 0.3  # seconds


async def send_json(ws: WebSocket, data: dict) -> None:
    """Send JSON to frontend, silently ignore if closed."""
    try:
        await ws.send_json(data)
        if data.get("type") in (
            "image_generated", "palette_reveal", "generation_complete",
            "voiceover_handoff", "voiceover_greeting", "voiceover_story",
        ):
            logger.info(f"[WS→FE] Sent {data['type']} | keys={list(data.keys())}")
    except Exception as e:
        logger.warning(f"WebSocket send failed: {e} | type={data.get('type')}")


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
            session.tagline = None
            session.brand_story = None
            session.brand_values = None
            session.tone_of_voice = None
            session.voiceover_sent = False
            session.auto_continue_count = 0
            session._pregen_names_sent = False
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


async def _wait_and_nudge(
    session: "Session",
    live_session: object,
    nudge: str,
    label: str,
    timeout: float = 30.0,
    pause_seconds: float = 0,
) -> None:
    """Wait for frontend to signal it finished showing the current turn's
    visual events + audio, then send the next auto-continue nudge.

    The frontend sends ``audio_playback_done`` after its event-queue flush
    completes, which sets ``session.frontend_ready``.  If no audio was
    played for the turn the frontend fires a fallback after 800 ms.

    ``pause_seconds`` adds extra delay after frontend_ready — gives users
    time to provide feedback before the next step fires.

    Guards against stale nudges: if the user interrupted (barge-in) or
    the session is awaiting feedback we silently drop the nudge.
    """
    # Always clear BEFORE waiting — forces a fresh signal from frontend.
    # Consuming a stale set() from a previous cycle caused nudges to fire
    # immediately while agent audio was still playing.
    session.frontend_ready.clear()
    try:
        await asyncio.wait_for(session.frontend_ready.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(
            f"[{session.id}] {label}: frontend_ready timeout ({timeout}s), proceeding"
        )
    session.frontend_ready.clear()

    # Extra guard — wait for agent audio to fully stop before nudging.
    # frontend_ready signals UI readiness but audio may still be draining.
    await asyncio.sleep(0.5)

    # Feedback pause — give user time to speak before next step
    if pause_seconds > 0:
        logger.info(
            f"[{session.id}] {label}: pausing {pause_seconds}s for feedback"
        )
        await asyncio.sleep(pause_seconds)

    # Stale-nudge guard — re-checked after pause so user feedback during
    # the wait window is respected.
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
    """
    if not text or not text.strip():
        return
    session.add_transcript("agent", text)
    events, narration = parse_agent_text(text, seen_types=seen_types)

    if events:
        # Replace partial agent_text with cleaned narration BEFORE events
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
            await asyncio.sleep(_EVENT_STAGGER_DELAY)
    else:
        # No structured events — send the full text as final
        await send_json(ws, {
            "type": "agent_text",
            "text": text,
            "partial": False,
        })
