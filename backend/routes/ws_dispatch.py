# UNUSED — superseded by routes/agent_loop.py + routes/receive_loop.py
"""State-machine driven auto-continue dispatcher."""

import asyncio
import logging

from fastapi import WebSocket
from google.genai import types

from models.session import AgentPhase, Session
from services import brand_state
from routes.ws_helpers import _wait_and_nudge

logger = logging.getLogger("brand-agent")


def _schedule_nudge(session, live_session, nudge, label, **kwargs):
    """Cancel any existing nudge task, then schedule a new one.

    Prevents concurrent nudge races — only one nudge is in-flight at a time.
    """
    if session._nudge_task and not session._nudge_task.done():
        session._nudge_task.cancel()
        logger.info(
            f"[{session.id}] Action: stale_nudge_cancelled | New: {label}"
        )
    session._nudge_task = asyncio.create_task(
        _wait_and_nudge(session, live_session, nudge, label, **kwargs),
        name=f"nudge-{label}",
    )


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
    if session.interrupt_text or session.awaiting_feedback:
        return
    if _pending_tool_bg[0] > 0:
        logger.info(
            f"[{session.id}] Action: dispatch_deferred | "
            f"Pending tools: {_pending_tool_bg[0]}"
        )
        return
    if session.voiceover_playing:
        logger.info(f"[{session.id}] Action: dispatch_deferred | Voiceover playing")
        return
    if session.zip_url:
        return

    # Nudge-in-flight guard — prevents agent_turn_complete dispatch from
    # racing against _tool_background dispatch.
    if session._nudge_task and not session._nudge_task.done():
        logger.info(f"[{session.id}] Action: dispatch_deferred | Nudge in-flight")
        return

    phase = session.phase
    _MAX = 15

    if session.auto_continue_count >= _MAX:
        if session.brand_name and not session.zip_url:
            logger.warning(
                f"[{session.id}] Action: dispatch_exhausted | "
                f"Attempts: {session.auto_continue_count}"
            )
        return

    # ── ANALYSIS_SPEECH → AWAITING_NAME (pregen) or PROPOSING (fallback) ────
    if phase == AgentPhase.ANALYSIS_SPEECH:
        session.auto_continue_count += 1

        async def _post_analysis_nudge():
            _deadline = 80  # 8s in 100ms steps
            while _deadline > 0 and not getattr(session, "_pregen_names", None):
                await asyncio.sleep(0.1)
                _deadline -= 1

            pregen_names = getattr(session, "_pregen_names", None)
            if pregen_names:
                brand_state.transition_phase(session, AgentPhase.AWAITING_NAME)
                names_text = ", ".join(f"'{n['name']}'" for n in pregen_names)
                _nudge = (
                    f"You proposed these brand names: {names_text}. "
                    f"The user is choosing now. Wait for their selection. "
                    f"Do NOT speak. Do NOT call any tools."
                )
                logger.info(
                    f"[{session.id}] Action: dispatch_awaiting_name_pregen | "
                    f"Turn: {turn_count}"
                )
            else:
                brand_state.transition_phase(session, AgentPhase.PROPOSING)
                _nudge = (
                    "Now call propose_names with 3 brand name options. "
                    "Do NOT speak. Just call the tool immediately."
                )
                logger.info(
                    f"[{session.id}] Action: dispatch_propose_names_fallback | "
                    f"Turn: {turn_count}"
                )

            await _wait_and_nudge(session, live_session, _nudge, "post_analysis")

        # Post-analysis has its own polling loop — use raw create_task
        # (not _schedule_nudge) because it polls for pregen before nudging.
        asyncio.create_task(_post_analysis_nudge(), name="post-analysis-nudge")

    # ── AWAITING_NAME: name chosen, no tagline yet → skip (REVEAL already in-flight) ─
    elif phase == AgentPhase.AWAITING_NAME and session.brand_name and not session.tagline:
        logger.info(
            f"[{session.id}] Action: dispatch_awaiting_name_skip | "
            f"Brand already chosen: {session.brand_name} | "
            f"REVEAL_TOOL nudge already in-flight from user-input path"
        )

    # FIX 8: AWAITING_NAME, no brand chosen → send propose_names retry directly
    elif phase == AgentPhase.AWAITING_NAME and not session.brand_name:
        if getattr(session, "_names_narrated", False):
            session._names_narrated = False
            logger.info(
                f"[{session.id}] Action: dispatch_skip_names_narrated"
            )
        else:
            session.auto_continue_count += 1
            if hasattr(session, "_pregen_names"):
                session._pregen_names = None
            session._pregen_names_sent = False
            nudge = (
                "Call propose_names now with 3 fresh brand name options. "
                "Do NOT speak first. Just call the tool immediately."
            )
            logger.info(
                f"[{session.id}] Action: dispatch_propose_names_retry"
            )
            try:
                await live_session.send_client_content(
                    turns=[types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=nudge)],
                    )],
                    turn_complete=True,
                )
            except Exception as e:
                logger.error(
                    f"[{session.id}] Action: propose_retry_failed | "
                    f"Error: {e}"
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
        _schedule_nudge(session, live_session, nudge, "reveal_tool")

    # ── REVEAL_TOOL done → palette (or skip to next missing thing) ───────────
    elif phase == AgentPhase.REVEAL_TOOL and session.tagline:
        if not session.palette:
            brand_state.transition_phase(session, AgentPhase.PALETTE_TOOL)
            session.auto_continue_count += 1
            nudge = (
                "Say ONE sentence about the palette direction for this brand — mention a specific hue or mood. "
                "Then immediately call generate_palette with 5 colors. Do NOT wait."
            )
            logger.info(f"[{session.id}] Action: dispatch_palette_combined | Turn: {turn_count}")
            _schedule_nudge(session, live_session, nudge, "palette_combined")
        else:
            # palette already exists (regen scenario) — skip straight to next missing thing
            brand_state.transition_phase(session, AgentPhase.AWAITING_INPUT)
            logger.info(f"[{session.id}] Action: dispatch_reveal_tool_skip_to_recovery | Turn: {turn_count}")
            await _dispatch_next_step(session, live_session, ws, turn_count, _pending_tool_bg)

    # ── PALETTE_SPEECH done → call generate_palette ───────────────────────────
    elif phase == AgentPhase.PALETTE_SPEECH:
        brand_state.transition_phase(session, AgentPhase.PALETTE_TOOL)
        session.auto_continue_count += 1
        nudge = (
            "Now call generate_palette with 5 colors. "
            "Do NOT speak. Just call the tool."
        )
        logger.info(f"[{session.id}] Action: dispatch_palette_tool | Turn: {turn_count}")
        _schedule_nudge(session, live_session, nudge, "palette_tool")

    # ── PALETTE_TOOL done → fonts (or skip to next missing thing) ────────────
    elif phase == AgentPhase.PALETTE_TOOL and session.palette:
        if not session.font_suggestion:
            brand_state.transition_phase(session, AgentPhase.FONTS_SPEECH)
            session.auto_continue_count += 1
            nudge = (
                "Say ONE sentence connecting typography to this brand's personality — "
                "mention the feeling you want or how it complements the palette. "
                "Do NOT use generic phrases. Do NOT call any tools. Just speak, then STOP."
            )
            logger.info(f"[{session.id}] Action: dispatch_fonts_speech | Turn: {turn_count}")
            _schedule_nudge(
                session, live_session, nudge, "fonts_speech",
                pause_seconds=10,
            )
        else:
            # fonts already exist — skip to next missing thing
            brand_state.transition_phase(session, AgentPhase.AWAITING_INPUT)
            logger.info(f"[{session.id}] Action: dispatch_palette_tool_skip_to_recovery | Turn: {turn_count}")
            await _dispatch_next_step(session, live_session, ws, turn_count, _pending_tool_bg)

    # ── FONTS_SPEECH done → call suggest_fonts ────────────────────────────────
    elif phase == AgentPhase.FONTS_SPEECH:
        brand_state.transition_phase(session, AgentPhase.FONTS_TOOL)
        session.auto_continue_count += 1
        nudge = (
            "Now call suggest_fonts with heading and body fonts. "
            "Do NOT speak. Just call the tool."
        )
        logger.info(f"[{session.id}] Action: dispatch_fonts_tool | Turn: {turn_count}")
        _schedule_nudge(session, live_session, nudge, "fonts_tool")

    # ── FONTS_TOOL or IMAGE_TOOL done → next image or closing ─────────────────
    elif phase in (AgentPhase.FONTS_TOOL, AgentPhase.IMAGE_TOOL):
        remaining_types = [
            a for a in ["logo", "hero_lifestyle", "instagram_post"]
            if a not in session.completed_assets
        ]
        if remaining_types:
            next_asset = remaining_types[0]
            label = {
                "logo": "logo",
                "hero_lifestyle": "lifestyle hero",
                "instagram_post": "Instagram post",
            }.get(next_asset, next_asset)
            brand_state.transition_phase(session, AgentPhase.IMAGE_SPEECH)
            session.auto_continue_count += 1
            nudge = (
                f"Say ONE sentence teasing the creative direction for the {label} — "
                f"reference the brand's palette or mood. Be specific. "
                f"Do NOT call any tools. Just speak, then STOP."
            )
            _pause = 8
            logger.info(
                f"[{session.id}] Action: dispatch_image_speech | "
                f"Asset: {next_asset} | Turn: {turn_count}"
            )
            _schedule_nudge(
                session, live_session, nudge, f"image_speech:{next_asset}",
                pause_seconds=_pause,
            )
        elif not session.voiceover_sent:
            brand_state.transition_phase(session, AgentPhase.VOICEOVER_SPEECH)
            session.auto_continue_count += 1
            nudge = (
                "All brand assets are complete. "
                "Say ONE sentence that ties the creative journey together and introduces Anna "
                "who will narrate the brand story — weave in something specific about THIS brand. "
                "Do NOT call any tools. Just speak, then STOP."
            )
            logger.info(
                f"[{session.id}] Action: dispatch_voiceover_speech | Turn: {turn_count}"
            )
            _schedule_nudge(
                session, live_session, nudge, "voiceover_speech",
                pause_seconds=3,
            )

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
            logger.info(
                f"[{session.id}] Action: dispatch_image_tool | "
                f"Asset: {next_asset} | Turn: {turn_count}"
            )
            _schedule_nudge(
                session, live_session, nudge, f"image_tool:{next_asset}",
            )

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
        _schedule_nudge(session, live_session, nudge, "voiceover_tool")

    # ── Legacy AWAITING_INPUT fallback for user-interrupt recovery ────────────
    elif phase == AgentPhase.AWAITING_INPUT and session.brand_name and not session.zip_url:
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
            _schedule_nudge(
                session, live_session, nudge, "reveal_speech_recovery",
            )
        elif not session.palette:
            brand_state.transition_phase(session, AgentPhase.PALETTE_SPEECH)
            session.auto_continue_count += 1
            nudge = (
                "Say ONE sentence about the palette direction — mention a specific hue or mood. "
                "Do NOT call any tools. Just speak, then STOP."
            )
            _schedule_nudge(
                session, live_session, nudge, "palette_speech_recovery",
            )
        elif not session.font_suggestion:
            brand_state.transition_phase(session, AgentPhase.FONTS_SPEECH)
            session.auto_continue_count += 1
            nudge = (
                "Say ONE sentence connecting typography to this brand's personality. "
                "Do NOT call any tools. Just speak, then STOP."
            )
            _schedule_nudge(
                session, live_session, nudge, "fonts_speech_recovery",
            )
        elif remaining_types:
            next_asset = remaining_types[0]
            label = {
                "logo": "logo",
                "hero_lifestyle": "lifestyle hero",
                "instagram_post": "Instagram post",
            }.get(next_asset, next_asset)
            brand_state.transition_phase(session, AgentPhase.IMAGE_SPEECH)
            session.auto_continue_count += 1
            nudge = (
                f"Say ONE sentence teasing the creative direction for the {label}. "
                f"Do NOT call any tools. Just speak, then STOP."
            )
            _schedule_nudge(
                session, live_session, nudge, f"image_speech_recovery:{next_asset}",
            )
        elif not session.voiceover_sent:
            brand_state.transition_phase(session, AgentPhase.VOICEOVER_SPEECH)
            session.auto_continue_count += 1
            nudge = (
                "Say ONE sentence introducing Anna who will narrate the brand story. "
                "Do NOT call any tools. Just speak, then STOP."
            )
            _schedule_nudge(
                session, live_session, nudge, "voiceover_speech_recovery",
            )
        logger.info(
            f"[{session.id}] Action: dispatch_awaiting_input_recovery | "
            f"Phase: {phase} | Turn: {turn_count}"
        )
