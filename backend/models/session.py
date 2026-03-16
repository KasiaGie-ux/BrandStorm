"""Session dataclass — lean runtime state built on BrandCanvas.

No phases. No boolean flags. The canvas IS the state.
"""

from __future__ import annotations

import asyncio
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
    
    # Event signaling that the frontend has finished playing agent audio
    audio_playback_event: asyncio.Event = field(default_factory=asyncio.Event)

    # Anna brand story agent — populated when invoke_brand_story_agent is called
    anna_script: str = ""
    anna_mood: str = "luxury"
    anna_live_session: Any = None   # Live API session for Anna
    anna_done_event: asyncio.Event = field(default_factory=asyncio.Event)
    # Set by anna_loop when frontend WS connects — bridge waits before sending cue
    anna_ws_connected: asyncio.Event = field(default_factory=asyncio.Event)
    # Queue for bridging Charon audio → Anna input
    charon_audio_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    # Charon's live session — stored so anna_bridge can inject Anna's audio into it
    charon_live_session: Any = None

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
