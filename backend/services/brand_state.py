"""Agent state machine — tracks phase transitions and completed assets.

The Live API agent drives transitions. This module only records them and
enforces valid transitions for observability.
"""

import logging
import time

from models.session import AgentPhase, Session, VALID_TRANSITIONS

logger = logging.getLogger("brand-agent")

# In-memory session store (hackathon scope — no DB needed)
_sessions: dict[str, Session] = {}
# Completed sessions kept for REST API access after WebSocket disconnects
_completed: dict[str, Session] = {}


def create_session(session_id: str | None = None) -> Session:
    """Create or restore a session.

    If a completed session with the same ID exists (e.g. after stop/reconnect),
    restore it so that accumulated brand data (palette, images, etc.) survives.
    """
    # Check if there's a completed session to restore
    if session_id and session_id in _completed:
        session = _completed.pop(session_id)
        _sessions[session.id] = session
        logger.info(
            f"[{session.id}] Phase: {session.phase.value} | Action: session_restored | "
            f"Assets: {list(session.asset_urls.keys())}"
        )
        return session

    # Also check active sessions (duplicate WS connect)
    if session_id and session_id in _sessions:
        logger.info(
            f"[{session_id}] Phase: {_sessions[session_id].phase.value} | "
            f"Action: session_reused"
        )
        return _sessions[session_id]

    session = Session() if session_id is None else Session(id=session_id)
    _sessions[session.id] = session
    logger.info(
        f"[{session.id}] Phase: INIT | Action: session_created"
    )
    return session


def get_session(session_id: str) -> Session | None:
    """Retrieve session by ID (checks active first, then completed)."""
    return _sessions.get(session_id) or _completed.get(session_id)


def remove_session(session_id: str) -> None:
    """Move session from active to completed (keeps data for REST API)."""
    session = _sessions.pop(session_id, None)
    if session:
        _completed[session_id] = session
        logger.info(
            f"[{session_id}] Phase: {session.phase.value} | "
            f"Action: session_archived | Assets: {list(session.asset_urls.keys())}"
        )


def transition_phase(session: Session, new_phase: AgentPhase) -> bool:
    """Transition session to a new phase. Returns True if valid."""
    old_phase = session.phase

    if new_phase == old_phase:
        return True

    valid_next = VALID_TRANSITIONS.get(old_phase, set())
    if new_phase not in valid_next:
        logger.warning(
            f"[{session.id}] Phase: {old_phase.value} → {new_phase.value} | "
            f"Action: invalid_transition (allowing anyway) | "
            f"Valid: {[p.value for p in valid_next]}"
        )
        # Allow anyway — agent may skip phases in practice

    logger.info(
        f"[{session.id}] Phase: {old_phase.value} → {new_phase.value} | "
        f"Action: phase_transition"
    )
    session.phase = new_phase
    session.updated_at = time.time()
    return True


def infer_phase_from_tool(session: Session, tool_name: str) -> None:
    """Infer and update phase based on which tool the agent called."""
    phase_map = {
        "analyze_product": AgentPhase.ANALYZING,
        "propose_names": AgentPhase.PROPOSING,
        "reveal_brand_identity": AgentPhase.PROPOSING,
        "suggest_fonts": AgentPhase.GENERATING,
        "generate_image": AgentPhase.GENERATING,
        "generate_palette": AgentPhase.GENERATING,
        "generate_voiceover": AgentPhase.GENERATING,
        "finalize_brand_kit": AgentPhase.COMPLETE,
    }
    new_phase = phase_map.get(tool_name)
    if new_phase and new_phase != session.phase:
        transition_phase(session, new_phase)


def get_all_sessions() -> dict[str, dict]:
    """Return all sessions as dicts (for admin/debug)."""
    all_sessions = {**_completed, **_sessions}  # active overrides completed
    return {sid: s.to_dict() for sid, s in all_sessions.items()}
