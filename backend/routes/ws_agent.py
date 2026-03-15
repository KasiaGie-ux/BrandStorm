# UNUSED — superseded by routes/agent_loop.py + routes/receive_loop.py
"""Agent loop — Live API → frontend."""

import asyncio
import base64
import logging

from fastapi import WebSocket
from google.genai import types

from config import SESSION_TIMEOUT_SEC
from models.session import AgentPhase, Session
from services import brand_state
from services.pregen import PreGenerator
from services.text_parser import parse_agent_text
from services.tool_executor import ToolExecutor
from routes.ws_helpers import send_json, _store_event_on_session, _flush_and_emit, _wait_and_nudge
from routes.ws_dispatch import _dispatch_next_step

logger = logging.getLogger("brand-agent")


async def agent_loop(
    ws: WebSocket,
    live_session: object,
    session: Session,
    tool_executor: ToolExecutor,
    pregen: PreGenerator | None = None,
) -> None:
    """Receive messages from Live API and forward to frontend."""
    agent_text_buffer: list[str] = []
    seen_event_types: set[str] = set()
    msg_count = 0
    turn_count = 0
    session_active = True
    _pending_tool_bg = [0]  # mutable container to avoid nonlocal issues

    async def _emit_cb(ev: dict):
        await send_json(ws, ev)
        _store_event_on_session(session, ev, pregen=pregen, emit_cb=None)

    try:
        async with asyncio.timeout(SESSION_TIMEOUT_SEC):
            logger.info(
                f"[{session.id}] Action: agent_loop_started | Timeout: {SESSION_TIMEOUT_SEC}s"
            )

            while session_active:
                turn_count += 1
                _tool_called_this_turn = False
                logger.info(
                    f"[{session.id}] Action: waiting_for_live_api_message | Turn: {turn_count}"
                )

                async for message in live_session.receive():
                    msg_count += 1

                    logger.info(
                        f"[{session.id}] Raw msg #{msg_count} | "
                        f"server_content={message.server_content is not None} | "
                        f"tool_call={message.tool_call is not None} | "
                        f"setup_complete={message.setup_complete is not None}"
                    )

                    # ── Server content: audio, text, transcription ──────────
                    if message.server_content:
                        sc = message.server_content

                        # FIX 4: interrupted handler sets awaiting_feedback
                        if getattr(sc, "interrupted", False):
                            logger.info(
                                f"[{session.id}] Action: barge_in_interrupted | "
                                f"Phase: {session.phase.value}"
                            )
                            await send_json(ws, {"type": "agent_audio_interrupted"})
                            session.awaiting_feedback = True
                            agent_text_buffer.clear()
                            break

                        if sc.model_turn and sc.model_turn.parts:
                            for part in sc.model_turn.parts:
                                if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
                                    if session.voiceover_playing:
                                        logger.info(
                                            f"[{session.id}] Action: suppress_audio_during_voiceover"
                                        )
                                    else:
                                        await send_json(ws, {
                                            "type": "agent_audio",
                                            "data": base64.b64encode(
                                                part.inline_data.data
                                            ).decode(),
                                            "mime_type": part.inline_data.mime_type,
                                        })
                                elif hasattr(part, "text") and part.text:
                                    # SKIP model_turn text — use output_transcription instead
                                    pass

                        if getattr(sc, "input_transcription", None) and sc.input_transcription.text:
                            user_speech_text = sc.input_transcription.text.strip()
                            if user_speech_text:
                                logger.info(
                                    f"[{session.id}] Action: user_voice_transcription | "
                                    f"Text: {user_speech_text[:80]}"
                                )
                                session.add_transcript("user", user_speech_text)
                                await send_json(ws, {
                                    "type": "user_voice_text",
                                    "text": user_speech_text,
                                })

                        if (sc.output_transcription and sc.output_transcription.text
                                and not session.voiceover_playing):
                            text = sc.output_transcription.text
                            agent_text_buffer.append(text)
                            if not sc.turn_complete:
                                await send_json(ws, {
                                    "type": "agent_text",
                                    "text": text,
                                    "partial": True,
                                })

                        if sc.turn_complete:
                            full_text = " ".join(
                                chunk for chunk in agent_text_buffer if chunk.strip()
                            )
                            logger.info(
                                f"[{session.id}] Action: turn_text_flush | "
                                f"Turn: {turn_count} | Text length: {len(full_text)} | "
                                f"Preview: {full_text[:120]}"
                            )

                            if session.phase == AgentPhase.ANALYZING:
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
                                    _, clean_narration = parse_agent_text(
                                        full_text, seen_types=seen_event_types
                                    )
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
                                await send_json(ws, {
                                    "type": "agent_text",
                                    "text": "",
                                    "partial": False,
                                })

                            # FIX 2: Never clear awaiting_feedback here
                            if full_text.strip() and not _tool_called_this_turn:
                                session.user_speaking = False

                            agent_text_buffer.clear()

                            if session.phase == AgentPhase.ANALYZING:
                                brand_state.transition_phase(
                                    session, AgentPhase.ANALYSIS_SPEECH
                                )
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
                                logger.info(
                                    f"[{session.id}] Action: auto_nudge_analysis_speech | "
                                    f"Turn: {turn_count}"
                                )
                                asyncio.create_task(_wait_and_nudge(
                                    session, live_session, nudge,
                                    label="analysis_speech_nudge",
                                    timeout=15.0,
                                ))

                                # Parallel: pre-generate name proposals via text model
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
                                        import json as _json
                                        _text = _resp.text.strip()
                                        if _text.startswith("```"):
                                            _text = _text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                                        _data = _json.loads(_text)
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
                                            _session._pregen_names = validated
                                            if not getattr(_session, "_pregen_names_sent", False):
                                                _session._pregen_names_sent = True
                                                await send_json(_ws, {
                                                    "type": "name_proposals",
                                                    "names": validated,
                                                    "auto_select_seconds": 10,
                                                })
                                                logger.info(
                                                    f"[{_session.id}] Action: pregen_names_sent | "
                                                    f"Names: {[n['name'] for n in validated]}"
                                                )
                                            else:
                                                logger.info(
                                                    f"[{_session.id}] Action: pregen_names_skip | "
                                                    f"Agent already sent early names — storing only"
                                                )
                                    except Exception as e:
                                        logger.warning(
                                            f"[{session.id}] Action: pregen_names_failed | Error: {e}"
                                        )

                                asyncio.create_task(_pregen_names(), name="pregen-names")
                                break

                            # Normalize legacy GENERATING → AWAITING_INPUT
                            if session.phase == AgentPhase.GENERATING:
                                brand_state.transition_phase(
                                    session, AgentPhase.AWAITING_INPUT
                                )
                            # After propose_names, normalize to REVEAL_TOOL if name chosen
                            elif (session.phase == AgentPhase.AWAITING_NAME
                                    and session.brand_name
                                    and not session.tagline
                                    and full_text.strip()):
                                brand_state.transition_phase(session, AgentPhase.REVEAL_TOOL)
                            # Agent narrated names — mark done so retry doesn't fire
                            elif (session.phase == AgentPhase.AWAITING_NAME
                                    and not session.brand_name
                                    and not _tool_called_this_turn
                                    and full_text.strip()):
                                if getattr(session, "_pregen_names_sent", False):
                                    session._names_narrated = True
                                    logger.info(
                                        f"[{session.id}] Action: names_narrated | "
                                        f"Turn: {turn_count} | Pregen cards visible"
                                    )
                                else:
                                    logger.info(
                                        f"[{session.id}] Action: names_narrated_skip | "
                                        f"Turn: {turn_count} | No cards visible (rejection ack)"
                                    )

                            logger.info(
                                f"[{session.id}] Action: turn_complete | "
                                f"Turn: {turn_count} | Msgs: {msg_count}"
                            )
                            await send_json(ws, {
                                "type": "agent_turn_complete",
                                "phase": session.phase.value,
                            })

                            # FIX 3: Simplified dispatch decision
                            if full_text.strip() and not session.awaiting_feedback:
                                await _dispatch_next_step(
                                    session, live_session, ws, turn_count, _pending_tool_bg
                                )

                            break

                    # ── Tool calls from agent ───────────────────────────────
                    if message.tool_call:
                        _tool_called_this_turn = True
                        for fc in message.tool_call.function_calls:
                            brand_state.infer_phase_from_tool(session, fc.name)

                            await send_json(ws, {
                                "type": "tool_invoked",
                                "tool": fc.name,
                                "args": dict(fc.args) if fc.args else {},
                                "phase": session.phase.value,
                            })

                            # For propose_names: send cards IMMEDIATELY (before bg task).
                            # Always send — frontend dedup handles exact duplicates.
                            # (Gating on _pregen_names_sent caused retries to be swallowed
                            # when the flag was still True from a concurrent pregen task.)
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
                                    session._pregen_names_sent = True
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

                            if fc.name == "generate_voiceover":
                                session.voiceover_playing = True

                            _pending_tool_bg[0] += 1

                            async def _tool_background(_fc=fc, _ls=live_session):
                                try:
                                    if _fc.name == "generate_voiceover":
                                        if session.voiceover_sent:
                                            logger.info(
                                                f"[{session.id}] Action: voiceover_dup_skip | "
                                                f"generate_voiceover already executed"
                                            )
                                            return
                                        session.voiceover_sent = True

                                    fn_response, event = await tool_executor.execute(
                                        session, _fc, emit_cb=_emit_cb
                                    )
                                    logger.info(
                                        f"[{session.id}] Action: tool_done | Tool: {_fc.name}"
                                    )

                                    _FAST_TOOLS = {
                                        "reveal_brand_identity", "suggest_fonts",
                                        "generate_palette", "propose_names",
                                        "update_tagline", "update_brand_story",
                                        "update_brand_voice", "update_brand_values",
                                    }
                                    _TOOL_ONLY_PHASES = {
                                        AgentPhase.REVEAL_TOOL,
                                        AgentPhase.PALETTE_TOOL,
                                        AgentPhase.FONTS_TOOL,
                                    }
                                    if _fc.name in _FAST_TOOLS and session.phase not in _TOOL_ONLY_PHASES:
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

                                    if _fc.name == "generate_voiceover":
                                        session.voiceover_playing = True

                                    # propose_names: only suppress event when pregen was used
                                    # (_handle_propose_names returns event=None in that case).
                                    # On retry/regen, it returns a real event — let it through.

                                    if _fc.name == "finalize_brand_kit":
                                        session.voiceover_playing = False

                                    await _ls.send_tool_response(
                                        function_responses=[fn_response]
                                    )
                                    logger.info(
                                        f"[{session.id}] Action: tool_response_sent | "
                                        f"Tool: {_fc.name}"
                                    )
                                    session.auto_continue_count = 0

                                    # Regen tools: clear awaiting_feedback so pipeline
                                    # can continue after agent executes the fix.
                                    # The agent called the tool — that IS the fix.
                                    # User still needs to confirm via positive signal
                                    # before the NEXT auto-continue fires, but the
                                    # current turn's dispatch should be unblocked.
                                    _REGEN_TOOLS = {
                                        "update_tagline", "update_brand_story",
                                        "update_brand_voice", "update_brand_values",
                                        "generate_palette", "generate_image",
                                        "suggest_fonts",
                                    }
                                    if _fc.name in _REGEN_TOOLS and session.awaiting_feedback:
                                        session.awaiting_feedback = False
                                        logger.info(
                                            f"[{session.id}] Action: feedback_cleared_after_regen | "
                                            f"Tool: {_fc.name}"
                                        )

                                    if event:
                                        await send_json(ws, event)
                                        _store_event_on_session(
                                            session, event, pregen=pregen, emit_cb=None
                                        )

                                    if _fc.name == "propose_names":
                                        brand_state.transition_phase(
                                            session, AgentPhase.AWAITING_NAME
                                        )
                                        session._names_narrated = False
                                        session._pregen_names_sent = False
                                    elif _fc.name == "reveal_brand_identity":
                                        brand_state.transition_phase(
                                            session, AgentPhase.REVEAL_TOOL
                                        )
                                        # Name selection = user intent — clear barge-in
                                        # flag so dispatch_retry_after_tool can proceed.
                                        # (The barge-in from send_client_content's
                                        # turn_complete=True re-sets awaiting_feedback
                                        # AFTER ws_receive.py clears it — race condition.)
                                        session.awaiting_feedback = False
                                    elif _fc.name == "generate_palette":
                                        brand_state.transition_phase(
                                            session, AgentPhase.PALETTE_TOOL
                                        )
                                    elif _fc.name == "suggest_fonts":
                                        brand_state.transition_phase(
                                            session, AgentPhase.FONTS_TOOL
                                        )
                                    elif _fc.name == "generate_image":
                                        brand_state.transition_phase(
                                            session, AgentPhase.IMAGE_TOOL
                                        )
                                    elif _fc.name == "finalize_brand_kit":
                                        session.voiceover_playing = False

                                    if _fc.name == "generate_voiceover" and not event:
                                        session.voiceover_playing = False
                                        logger.warning(
                                            f"[{session.id}] Action: voiceover_skipped_clearing_flag"
                                        )

                                    if _fc.name == "generate_voiceover" and event:
                                        async def _voiceover_safety_timeout(
                                            sid=session.id, __ls=_ls,
                                        ):
                                            await asyncio.sleep(90)
                                            if session.voiceover_playing:
                                                session.voiceover_playing = False
                                                logger.warning(
                                                    f"[{sid}] Action: voiceover_safety_timeout"
                                                )
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
                                    if _fc.name == "generate_voiceover":
                                        session.voiceover_playing = False
                                        logger.warning(
                                            f"[{session.id}] Action: voiceover_flag_cleared_on_error"
                                        )
                                finally:
                                    _pending_tool_bg[0] -= 1
                                    if _pending_tool_bg[0] == 0:
                                        _skip_dispatch = (
                                            _fc.name == "propose_names"
                                            and (
                                                (
                                                    session.brand_name
                                                    and session.phase in (
                                                        AgentPhase.REVEAL_TOOL,
                                                        AgentPhase.REVEAL_SPEECH,
                                                    )
                                                )
                                                or (
                                                    not session.brand_name
                                                    and session.phase == AgentPhase.AWAITING_NAME
                                                )
                                            )
                                        )
                                        if _skip_dispatch:
                                            logger.info(
                                                f"[{session.id}] Action: dispatch_skip_after_propose | "
                                                f"Phase: {session.phase.value} | "
                                                f"Brand chosen: {bool(session.brand_name)}"
                                            )
                                        else:
                                            logger.info(
                                                f"[{session.id}] Action: dispatch_retry_after_tool | "
                                                f"Tool: {_fc.name} | Phase: {session.phase.value}"
                                            )
                                            try:
                                                await _dispatch_next_step(
                                                    session, live_session, ws,
                                                    turn_count, _pending_tool_bg,
                                                )
                                            except Exception as e:
                                                logger.error(
                                                    f"[{session.id}] Action: dispatch_retry_failed | "
                                                    f"Error: {e}"
                                                )

                            asyncio.create_task(
                                _tool_background(), name=f"tool-bg-{fc.name}"
                            )

                            # Clear pending_regen — agent executed a corrective tool call
                            if session.pending_regen:
                                logger.info(
                                    f"[{session.id}] Action: pending_regen_cleared | "
                                    f"Tool: {fc.name}"
                                )
                                session.pending_regen = False

                            # Interrupt check between tool calls.
                            # propose_names and reveal_brand_identity are user-response tools
                            # (agent reacting to user input), NOT auto-continue tools —
                            # never block them even when awaiting_feedback is True.
                            _user_response_tools = {"propose_names", "reveal_brand_identity"}
                            if (session.interrupt_text or session.awaiting_feedback) and fc.name not in _user_response_tools:
                                logger.info(
                                    f"[{session.id}] Action: interrupt_break | "
                                    f"Tool: {fc.name} | "
                                    f"Text: {(session.interrupt_text or '')[:80]} | "
                                    f"awaiting_feedback: {session.awaiting_feedback} | "
                                    f"Stopping auto-continue"
                                )
                                session.interrupt_text = None
                                session.user_speaking = False
                                brand_state.transition_phase(
                                    session, AgentPhase.AWAITING_INPUT
                                )
                                await send_json(ws, {
                                    "type": "agent_turn_complete",
                                    "phase": session.phase.value,
                                })
                                break

                            if fc.name == "finalize_brand_kit":
                                logger.info(
                                    f"[{session.id}] Action: finalize_complete | "
                                    f"Staying alive for feedback"
                                )
                                brand_state.transition_phase(
                                    session, AgentPhase.AWAITING_INPUT
                                )
                                session.awaiting_feedback = False
                                await send_json(ws, {
                                    "type": "agent_turn_complete",
                                    "phase": session.phase.value,
                                })

                    if message.setup_complete:
                        logger.debug(f"[{session.id}] setup_complete (ignored)")

                else:
                    logger.warning(
                        f"[{session.id}] Action: receive_stream_ended | Turn: {turn_count}"
                    )

            logger.info(
                f"[{session.id}] Action: agent_loop_finished | "
                f"Turns: {turn_count} | Msgs: {msg_count}"
            )

    except TimeoutError:
        logger.error(
            f"[{session.id}] Action: session_timeout | "
            f"{SESSION_TIMEOUT_SEC}s | Turns: {turn_count}"
        )
        await send_json(ws, {
            "type": "session_timeout",
            "message": f"Session timed out after {SESSION_TIMEOUT_SEC}s",
        })
    except Exception as e:
        logger.error(
            f"[{session.id}] Action: agent_loop_error | Error: {e} | Turns: {turn_count}"
        )
        await send_json(ws, {"type": "error", "message": str(e)})
    finally:
        pass  # background tool tasks will finish on their own
