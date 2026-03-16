"""Anna WebSocket endpoint — /ws/{session_id}/anna

Frontend connects here when it receives anna_ready event.
Anna's Live API session is already started in the background by tool_executor.
This route:
1. Registers itself as the audio drain target for the bridge
2. Signals anna_ws_connected so the background task sends the cue
3. Drains incoming messages (keepalive etc.) while bridge runs
"""

import asyncio
import logging

from fastapi import WebSocket, WebSocketDisconnect

from models.session import Session

logger = logging.getLogger("brand-agent")


async def anna_websocket(
    ws: WebSocket,
    session: Session,
    main_ws_send,  # callable: async (dict) → None — sends events to main frontend WS
) -> None:
    """Handle Anna's WebSocket connection.

    The Live API session for Anna is already running in the background.
    We register this WS as the audio drain target, then signal the background
    task that it can now send the cue to Anna.
    """
    await ws.accept()
    session_id = session.id

    if not session.anna_script:
        logger.warning(f"[{session_id}] Anna WS connected but no script set")
        await ws.close(code=4000, reason="No script")
        return

    # Register this WS so the background task can send audio to frontend
    session._anna_frontend_ws = ws
    session._anna_main_ws_send = main_ws_send

    logger.info(f"[{session_id}] Anna frontend WS connected — signaling cue")

    # Signal background task: frontend is ready, send the cue now
    session.anna_ws_connected.set()

    try:
        # Drain frontend messages while bridge runs (keepalive, etc.)
        await _drain_until_done(ws, session, session_id)
    except WebSocketDisconnect:
        logger.info(f"[{session_id}] Anna WS disconnected by frontend")
        session.anna_done_event.set()
    except Exception as e:
        logger.error(f"[{session_id}] Anna WS error: {e}")
        session.anna_done_event.set()
        await main_ws_send({"type": "anna_done", "session_id": session_id, "error": str(e)})
    finally:
        session._anna_frontend_ws = None
        try:
            await ws.close()
        except Exception:
            pass
        logger.info(f"[{session_id}] Anna WS session ended")


async def _drain_until_done(ws: WebSocket, session: Session, session_id: str) -> None:
    """Drain frontend messages until anna_done_event is set."""
    done_task = asyncio.create_task(session.anna_done_event.wait())
    recv_task = asyncio.create_task(_recv_loop(ws, session_id))

    done, pending = await asyncio.wait(
        [done_task, recv_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for t in pending:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass


async def _recv_loop(ws: WebSocket, session_id: str) -> None:
    """Receive and discard messages from frontend (keepalive, etc.)."""
    try:
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as e:
        logger.debug(f"[{session_id}] Anna recv: {e}")
