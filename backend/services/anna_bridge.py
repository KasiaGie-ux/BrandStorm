"""Anna Bridge — forwards audio between Charon and Anna Live API sessions.

Charon audio out (24kHz PCM) → resample to 16kHz → Anna audio in
Anna audio out (24kHz PCM)   → forwarded to frontend WebSocket as agent_audio chunks
                              → resample to 16kHz → Charon audio in

End detection: watches Anna's output_transcription for "That's all, Charon"
and sets session.anna_done_event when found.
"""

import asyncio
import base64
import logging
from typing import Any

from google.genai import types

logger = logging.getLogger("brand-agent")

# Live API outputs 24kHz, inputs expect 16kHz PCM
_OUTPUT_RATE = 24000
_INPUT_RATE = 16000
_RESAMPLE_RATIO = _INPUT_RATE / _OUTPUT_RATE  # 0.6667


def _resample_24k_to_16k(pcm_24k: bytes) -> bytes:
    """Downsample 24kHz 16-bit mono PCM to 16kHz by keeping every 2 out of 3 samples."""
    try:
        import audioop
        resampled, _ = audioop.ratecv(pcm_24k, 2, 1, _OUTPUT_RATE, _INPUT_RATE, None)
        return resampled
    except Exception:
        # Fallback: simple decimation (take every 3rd sample pair starting at 0 and 1)
        import struct
        samples = struct.unpack(f"<{len(pcm_24k)//2}h", pcm_24k)
        # Keep approximately 2 out of every 3 samples
        out = []
        i = 0
        while i < len(samples):
            out.append(samples[i])
            if i + 1 < len(samples):
                out.append(samples[i + 1])
            i += 3
        return struct.pack(f"<{len(out)}h", *out)


_END_SIGNAL = "that's all, charon"


def _contains_end_signal(text: str) -> bool:
    return _END_SIGNAL in text.lower()


async def run_anna_bridge(
    session,          # Session object
    anna_live_session,  # Anna's Live API session
    frontend_ws,      # FastAPI WebSocket for the /anna endpoint (Anna's audio → frontend)
    main_ws_send,     # callable: async (dict) → None  (sends events to the MAIN frontend WS)
) -> None:
    """Bridge audio between Charon and Anna sessions until Anna signals end.

    Spawns three concurrent tasks:
    1. charon_to_anna: forwards Charon PCM chunks from session.charon_audio_queue → Anna
    2. anna_to_frontend: receives Anna audio → frontend WS + Charon input
    3. Timeout watchdog: 120s max for the whole exchange
    """
    session_id = session.id
    logger.info(f"[{session_id}] Anna bridge starting")

    async def charon_to_anna() -> None:
        """Forward Charon's audio output queue into Anna's input."""
        try:
            while True:
                pcm_24k: bytes = await session.charon_audio_queue.get()
                if pcm_24k is None:
                    break
                pcm_16k = _resample_24k_to_16k(pcm_24k)
                await anna_live_session.send_realtime_input(
                    audio=types.Blob(data=pcm_16k, mime_type="audio/pcm;rate=16000")
                )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[{session_id}] charon_to_anna error: {e}")

    async def anna_receive() -> None:
        """Receive Anna's output, forward to frontend + Charon input."""
        try:
            async for message in anna_live_session.receive():
                if message.server_content:
                    sc = message.server_content

                    # Forward Anna's audio chunks to frontend
                    if sc.model_turn and sc.model_turn.parts:
                        for part in sc.model_turn.parts:
                            if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
                                pcm_24k = part.inline_data.data
                                # To frontend (Anna WS)
                                try:
                                    await frontend_ws.send_json({
                                        "type": "agent_audio",
                                        "data": base64.b64encode(pcm_24k).decode(),
                                        "mime_type": part.inline_data.mime_type,
                                        "source": "anna",
                                    })
                                except Exception:
                                    pass

                                # To Charon input so he "hears" Anna
                                pcm_16k = _resample_24k_to_16k(pcm_24k)
                                try:
                                    await session.anna_live_session  # reference check
                                    # We inject directly via Charon's live session stored in agent_loop
                                    if hasattr(session, "charon_live_session") and session.charon_live_session:
                                        await session.charon_live_session.send_realtime_input(
                                            audio=types.Blob(data=pcm_16k, mime_type="audio/pcm;rate=16000")
                                        )
                                except Exception:
                                    pass

                    # Watch output transcription — forward to frontend chat + detect end signal
                    if sc.output_transcription and sc.output_transcription.text:
                        text = sc.output_transcription.text
                        logger.info(f"[{session_id}] Anna: {text[:80]}")
                        end_detected = _contains_end_signal(text)
                        # Strip end signal phrase before sending to chat
                        display_text = text
                        if end_detected:
                            import re
                            display_text = re.sub(r"(?i)that'?s all,?\s*charon\.?", "", text).strip()
                        if display_text:
                            await main_ws_send({
                                "type": "agent_text",
                                "text": display_text,
                                "partial": not getattr(sc, "turn_complete", False),
                                "source": "anna",
                            })
                        if end_detected:
                            logger.info(f"[{session_id}] Anna end signal detected")
                            session.anna_done_event.set()
                            # Notify frontend via main WS
                            await main_ws_send({"type": "anna_done", "session_id": session_id})
                            # Nudge Charon directly — tell him Anna is done, finalize now
                            if hasattr(session, "charon_live_session") and session.charon_live_session:
                                try:
                                    from services.context_injector import build_context_message
                                    ctx = build_context_message(
                                        session,
                                        trigger="anna_done",
                                        details="Anna has finished the brand story narration. Call finalize_brand_kit now.",
                                    )
                                    await session.charon_live_session.send_client_content(
                                        turns=[types.Content(
                                            role="user",
                                            parts=[types.Part.from_text(text=ctx)],
                                        )],
                                        turn_complete=True,
                                    )
                                    logger.info(f"[{session_id}] Charon nudged to finalize")
                                except Exception as e:
                                    logger.error(f"[{session_id}] Failed to nudge Charon: {e}")
                            return

                    if getattr(sc, "turn_complete", False):
                        logger.info(f"[{session_id}] Anna turn complete")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[{session_id}] anna_receive error: {e}")
            session.anna_done_event.set()
            await main_ws_send({"type": "anna_done", "session_id": session_id, "error": str(e)})

    # Run bridge tasks with 120s timeout
    charon_task = asyncio.create_task(charon_to_anna())
    anna_task = asyncio.create_task(anna_receive())

    try:
        await asyncio.wait_for(
            session.anna_done_event.wait(),
            timeout=120.0,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[{session_id}] Anna bridge timeout — forcing anna_done")
        session.anna_done_event.set()
        await main_ws_send({"type": "anna_done", "session_id": session_id, "timeout": True})
    finally:
        charon_task.cancel()
        anna_task.cancel()
        # Drain the queue
        while not session.charon_audio_queue.empty():
            try:
                session.charon_audio_queue.get_nowait()
            except Exception:
                break
        logger.info(f"[{session_id}] Anna bridge finished")
