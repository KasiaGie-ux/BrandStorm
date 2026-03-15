"""Session dataclass — lean runtime state built on BrandCanvas.

No phases. No boolean flags. The canvas IS the state.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from models.canvas import BrandCanvas


@dataclass
class Session:
    """Tracks a single brand generation session."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # The brand canvas IS the source of truth
    canvas: BrandCanvas = field(default_factory=BrandCanvas)

    # Product input
    product_image_bytes: bytes | None = None
    product_image_mime: str = "image/jpeg"

    # Logo bytes cached for chaining to hero/instagram generation
    logo_image_bytes: bytes | None = None
    logo_image_mime: str = "image/png"

    # Conversation transcript (for context, not for control)
    transcript: list[dict[str, Any]] = field(default_factory=list)

    # Last event that happened (tool result, user message) — for logging
    last_event: dict | None = None

    # Background async tasks (image gen, TTS) — keyed by task name
    background_tasks: dict[str, Any] = field(default_factory=dict)

    # Set to tool names after send_tool_response, cleared when agent speaks.
    # Used by the post-tool nudge to detect agent getting stuck after a tool.
    pending_tool_response: list[str] | None = None

    # True once propose_names has been called — prevents re-proposing on affirmations
    # while user is still deciding between the presented names.
    names_proposed: bool = False

    # Names currently on offer — used to detect voice-spoken selection.
    proposed_names: list[str] = field(default_factory=list)

    # Tracks the last [NEXT STEP] instruction sent to the agent.
    # Prevents duplicate instructions when user sends multiple affirmations rapidly
    # before the agent has had a chance to act on the first one.
    pending_next_step: str | None = None

    # Canvas fingerprint when pending_next_step was last set.
    # If canvas hasn't changed and pending_next_step is set, the user's next
    # affirmation is likely confirming something else (e.g. a tagline change) —
    # don't re-inject [NEXT STEP].
    pending_next_step_canvas_key: str | None = None

    def add_transcript(self, role: str, text: str) -> None:
        self.transcript.append({"role": role, "text": text, "ts": time.time()})
        self.updated_at = time.time()

    @property
    def progress(self) -> float:
        return self.canvas.progress

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "canvas": self.canvas.snapshot(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
