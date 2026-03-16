"""Agent loop — receives from Gemini Live API, forwards to frontend.

Simple loop: receive → process → forward. No dispatch, no phases, no nudges.
The agent is autonomous — this loop just bridges Live API and WebSocket.
"""

import asyncio
import base64
import logging

from fastapi import WebSocket
from google.genai import types

from config import SESSION_TIMEOUT_SEC
from models.session import Session
from services.tool_executor import ToolExecutor

logger = logging.getLogger("brand-agent")



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


    _SILENCE = b"\x00" * 480  # 15ms silence at 16kHz 16-bit mono — below VAD threshold
    _IDLE_KEEPALIVE_SEC = 8       # interval between silence pings
    _IDLE_KEEPALIVE_LIMIT = 120   # stop after 2 minutes of idle keepalive
    idle_keepalive_task: asyncio.Task | None = None

    async def _idle_keepalive():
        """Send silence to Live API every 8s for up to 2 minutes after a tool fires."""
        elapsed = 0
        try:
            while elapsed < _IDLE_KEEPALIVE_LIMIT:
                await asyncio.sleep(_IDLE_KEEPALIVE_SEC)
                elapsed += _IDLE_KEEPALIVE_SEC
                try:
                    await live_session.send_realtime_input(
                        audio=types.Blob(data=_SILENCE, mime_type="audio/pcm;rate=16000"),
                    )
                    logger.debug(f"[{session.id}] Idle keepalive | {elapsed}s")
                except Exception as ke:
                    logger.warning(f"[{session.id}] Idle keepalive failed: {ke}")
                    break
        except asyncio.CancelledError:
            pass

    try:

        while True:
            async for message in live_session.receive():
                logger.info(f"[{session.id}] Live API message | sc={bool(message.server_content)} tool={bool(message.tool_call)} setup={bool(getattr(message, 'setup_complete', None))}")
                # -- Server content: audio, text, transcription --
                if message.server_content:
                    sc = message.server_content

                    has_model_turn = bool(sc.model_turn and sc.model_turn.parts)
                    has_input_tx = bool(getattr(sc, "input_transcription", None))
                    has_output_tx = bool(getattr(sc, "output_transcription", None))
                    turn_complete = bool(getattr(sc, "turn_complete", False))
                    interrupted = bool(getattr(sc, "interrupted", False))
                    waiting = getattr(sc, "waiting_for_input", None)
                    gen_complete = getattr(sc, "generation_complete", None)
                    turn_reason = getattr(sc, "turn_complete_reason", None)
                    n_parts = len(sc.model_turn.parts) if has_model_turn else 0
                    part_types = [
                        ("audio" if (p.inline_data and p.inline_data.mime_type.startswith("audio/")) else "text" if p.text else "other")
                        for p in sc.model_turn.parts
                    ] if has_model_turn else []
                    # Log full output_transcription object for inspection
                    out_tx_obj = getattr(sc, "output_transcription", None)
                    out_tx_text = repr(getattr(out_tx_obj, "text", None)[:80]) if out_tx_obj and getattr(out_tx_obj, "text", None) else repr(getattr(out_tx_obj, "text", None))
                    logger.info(
                        f"[{session.id}] sc detail | model_turn={has_model_turn} parts={n_parts} "
                        f"types={part_types} input_tx={has_input_tx} output_tx={has_output_tx} "
                        f"out_tx_text={out_tx_text} turn_complete={turn_complete} "
                        f"waiting={waiting} gen_complete={gen_complete} reason={turn_reason} interrupted={interrupted}"
                    )

                    # Barge-in: agent was interrupted by user
                    if interrupted:
                        # If interrupted before agent produced any opening audio/text
                        # (canvas still empty = agent never started), re-arm the opening
                        # flag so the next turn_complete triggers another retry.
                        if not session.opening_awaiting_response and session.canvas.ready_count == 0:
                            logger.warning(f"[{session.id}] Interrupted during opening — re-arming retry")
                            session.opening_awaiting_response = True
                        await send_json(ws, {"type": "agent_audio_interrupted"})
                        continue

                    # Forward audio chunks
                    if sc.model_turn and sc.model_turn.parts:
                        for part in sc.model_turn.parts:
                            if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
                                # Agent is producing audio — clear watchdog and opening flag
                                session.opening_awaiting_response = False
                                if session.pending_tool_response is not None:
                                    logger.debug(f"[{session.id}] Watchdog cleared — agent audio started")
                                    session.pending_tool_response = None
                                if not session.finalize_in_progress:
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

                            # Detect voice name selection — update canvas state so receive_loop
                            # picks it up on the next user affirmation turn.
                            from routes.receive_loop import _detect_name_choice
                            if session.proposed_names and session.canvas.name.status != "ready":
                                chosen = _detect_name_choice(text.strip(), session.proposed_names)
                                if chosen:
                                    session.canvas.name.set(chosen)
                                    session.proposed_names = []
                                    session.pending_tool_response = None
                                    logger.debug(f"[{session.id}] Voice name selected: '{chosen}' (from: '{text.strip()}')")

                    # Output transcription (agent speech)
                    if getattr(sc, "output_transcription", None):
                        text = getattr(sc.output_transcription, "text", "")
                        finished = getattr(sc.output_transcription, "finished", None)
                        logger.info(f"[{session.id}] output_tx | text={repr(text[:60]) if text else repr(text)} finished={finished}")
                        if text:
                            session.opening_awaiting_response = False
                        if text and not session.finalize_in_progress:
                            await send_json(ws, {
                                "type": "agent_text",
                                "text": text,
                                "partial": not getattr(sc, "turn_complete", False),
                            })
                            # Clear watchdog flag — agent is speaking
                            if text.strip() and session.pending_tool_response is not None:
                                logger.debug(
                                    f"[{session.id}] Watchdog cleared — agent spoke: '{text[:40]}'"
                                )
                                session.pending_tool_response = None

                    # Turn complete — always send agent_turn_complete
                    if getattr(sc, "turn_complete", False):
                        logger.info(f"[{session.id}] turn_complete | opening_awaiting={session.opening_awaiting_response}")
                        if idle_keepalive_task and not idle_keepalive_task.done():
                            idle_keepalive_task.cancel()
                            idle_keepalive_task = None

                        # Silent first turn: Live API returned turn_complete without
                        # producing any audio/text for the opening sequence.
                        # Retry once by re-sending the opening instruction.
                        if session.opening_awaiting_response:
                            session.opening_awaiting_response = False
                            logger.warning(
                                f"[{session.id}] Silent turn_complete on opening — retrying"
                            )
                            try:
                                from services.context_injector import build_context_message
                                retry_ctx = build_context_message(
                                    session,
                                    trigger="session_start",
                                    details=(
                                        "CRITICAL: Execute your OPENING SEQUENCE now. "
                                        "Say EXACTLY 3 dramatic adjective words. "
                                        "Then introduce yourself. STOP."
                                    ),
                                )
                                await live_session.send_client_content(
                                    turns=[types.Content(
                                        role="user",
                                        parts=[types.Part.from_text(text=retry_ctx)],
                                    )],
                                    turn_complete=True,
                                )
                            except Exception as re_err:
                                logger.error(f"[{session.id}] Opening retry failed: {re_err}")
                            # Don't send agent_turn_complete to frontend — this was a no-op turn
                            continue

                        await send_json(ws, {
                            "type": "agent_turn_complete",
                            "canvas": session.canvas.snapshot(),
                        })
                        # Agent spoke after generate_image — guard stays until user's
                        # affirmation is consumed (receive_loop will reset it when
                        # canvas_key changes after the next tool fires).

                # -- Tool calls from agent --
                if message.tool_call:
                    all_responses = []
                    all_events = []
                    tool_names = []
                    logger.info(f"[{session.id}] Tool call from agent | Tools: {[fc.name for fc in message.tool_call.function_calls]}")

                    for fc in message.tool_call.function_calls:
                        await send_json(ws, {
                            "type": "tool_invoked",
                            "tool": fc.name,
                            "args": dict(fc.args) if fc.args else {},
                        })

                        # For long-running tools (image generation), send silent PCM
                        # chunks every 8s to keep the Live API session alive.
                        # 480 bytes of silence = 15ms at 16kHz 16-bit mono — below VAD threshold.
                        _LONG_RUNNING = {"generate_image", "generate_voiceover"}
                        if fc.name in _LONG_RUNNING:
                            _SILENCE = b"\x00" * 480
                            execute_task = asyncio.create_task(
                                tool_executor.execute(session, fc)
                            )
                            while not execute_task.done():
                                try:
                                    await asyncio.wait_for(
                                        asyncio.shield(execute_task), timeout=8.0
                                    )
                                except asyncio.TimeoutError:
                                    try:
                                        await live_session.send_realtime_input(
                                            audio=types.Blob(
                                                data=_SILENCE,
                                                mime_type="audio/pcm;rate=16000",
                                            )
                                        )
                                        logger.debug(
                                            f"[{session.id}] Live API keepalive | Tool: {fc.name}"
                                        )
                                    except Exception as ke:
                                        logger.warning(
                                            f"[{session.id}] Keepalive failed: {ke}"
                                        )
                            fn_response, frontend_events = execute_task.result()
                        else:
                            fn_response, frontend_events = await tool_executor.execute(
                                session, fc,
                            )

                        all_responses.append(fn_response)
                        all_events.extend(frontend_events)
                        tool_names.append(fc.name)

                    for event in all_events:
                        await send_json(ws, event)

                    try:
                        await live_session.send_tool_response(
                            function_responses=all_responses,
                        )
                    except Exception as tre:
                        logger.error(f"[{session.id}] send_tool_response failed: {tre}")
                        raise
                    logger.debug(f"[{session.id}] Batch tool response | Tools: {tool_names}")

                    # Start idle keepalive — keeps Live API session alive while agent processes
                    if idle_keepalive_task and not idle_keepalive_task.done():
                        idle_keepalive_task.cancel()
                    idle_keepalive_task = asyncio.create_task(_idle_keepalive())

                    # Mark pending — tool_watchdog (in ws.py) will nudge if agent stays silent
                    session.pending_tool_response = tool_names[:]
                    # Suppress second agent speech turn after finalize_brand_kit result
                    if "finalize_brand_kit" in tool_names:
                        session.finalize_in_progress = True
                    # Clear next-step dedup guard — tool fired, canvas state will change.
                    # Exception: after generate_image, keep the guard armed with the NEW
                    # canvas key so the agent's first "what do you think?" question is
                    # protected — the user's feedback "yes" should not be hijacked by
                    # [NEXT STEP generate hero] before agent even asks about the image.
                    if any(t == "generate_image" for t in tool_names):
                        c = session.canvas
                        session.pending_next_step = "guarded"
                        session.pending_next_step_canvas_key = "|".join([
                            c.name.status, c.tagline.status, c.palette.status,
                            c.fonts.status, c.logo.status, c.hero.status,
                            c.instagram.status, c.voiceover.status,
                        ])
                    else:
                        session.pending_next_step = None
                        session.pending_next_step_canvas_key = None
                    logger.debug(f"[{session.id}] Watchdog armed | Tools: {tool_names}")


        # If we reach here the Live API stream ended (server closed it)
        logger.warning(f"[{session.id}] Live API stream ended (receive generator exhausted)")

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[{session.id}] agent_loop error: {e}")
        await send_json(ws, {"type": "error", "message": str(e)})
        raise
    finally:
        if idle_keepalive_task and not idle_keepalive_task.done():
            idle_keepalive_task.cancel()
