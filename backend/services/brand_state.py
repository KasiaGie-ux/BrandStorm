"""Session store — in-memory session management.

No phase logic, no transition maps. Just create/get/remove sessions.
"""

import asyncio
import logging

from models.session import Session

logger = logging.getLogger("brand-agent")

# In-memory session store (hackathon scope — no DB needed)
_sessions: dict[str, Session] = {}
_completed: dict[str, Session] = {}
_active_teardowns: dict[str, asyncio.Event] = {}


def register_teardown_event(session_id: str) -> asyncio.Event:
    """Register a stop event for the current WebSocket connection.

    If a previous connection exists, signal it to close.
    """
    existing = _active_teardowns.get(session_id)
    if existing and not existing.is_set():
        existing.set()
        logger.info(f"[{session_id}] Superseded old connection")
    ev = asyncio.Event()
    _active_teardowns[session_id] = ev
    return ev


def clear_teardown_event(session_id: str, event: asyncio.Event | None = None) -> None:
    """Clear teardown event only if it matches (prevents race on concurrent reconnect)."""
    existing = _active_teardowns.get(session_id)
    if event is None or existing is event:
        _active_teardowns.pop(session_id, None)


def create_session(session_id: str | None = None) -> Session:
    """Create or restore a session."""
    if session_id and session_id in _completed:
        session = _completed.pop(session_id)
        _sessions[session.id] = session
        logger.info(f"[{session.id}] Session restored")
        return session

    if session_id and session_id in _sessions:
        logger.info(f"[{session_id}] Session reused")
        return _sessions[session_id]

    session = Session() if session_id is None else Session(id=session_id)
    _sessions[session.id] = session
    logger.info(f"[{session.id}] Session created")
    return session


def get_session(session_id: str) -> Session | None:
    return _sessions.get(session_id) or _completed.get(session_id)


def remove_session(session_id: str) -> None:
    session = _sessions.pop(session_id, None)
    if session:
        _completed[session_id] = session
        logger.info(f"[{session_id}] Session archived")


def get_all_sessions() -> dict[str, dict]:
    all_sessions = {**_completed, **_sessions}
    return {sid: s.to_dict() for sid, s in all_sessions.items()}
