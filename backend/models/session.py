"""Session dataclass with agent state machine enum."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentPhase(str, Enum):
    """Agent state machine phases — agent controls transitions via tool calls."""
    INIT = "INIT"
    ANALYZING = "ANALYZING"
    PROPOSING = "PROPOSING"
    AWAITING_INPUT = "AWAITING_INPUT"
    GENERATING = "GENERATING"
    REFINING = "REFINING"
    COMPLETE = "COMPLETE"


# Valid phase transitions
VALID_TRANSITIONS: dict[AgentPhase, set[AgentPhase]] = {
    AgentPhase.INIT: {AgentPhase.ANALYZING},
    AgentPhase.ANALYZING: {AgentPhase.PROPOSING},
    AgentPhase.PROPOSING: {AgentPhase.AWAITING_INPUT},
    AgentPhase.AWAITING_INPUT: {AgentPhase.GENERATING, AgentPhase.PROPOSING},
    AgentPhase.GENERATING: {AgentPhase.REFINING, AgentPhase.COMPLETE},
    AgentPhase.REFINING: {AgentPhase.AWAITING_INPUT, AgentPhase.COMPLETE},
    AgentPhase.COMPLETE: set(),
}


@dataclass
class Session:
    """Tracks a single brand generation session."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    phase: AgentPhase = AgentPhase.INIT
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # Product
    product_image_url: str | None = None
    product_image_bytes: bytes | None = None
    product_image_mime: str = "image/jpeg"

    # Brand kit state
    brand_name: str | None = None
    completed_assets: list[str] = field(default_factory=list)
    asset_urls: dict[str, str] = field(default_factory=dict)

    # Conversation
    transcript: list[dict[str, str]] = field(default_factory=list)
    user_preferences: dict[str, Any] = field(default_factory=dict)

    # Palette (set by generate_palette tool)
    palette: list[dict[str, str]] | None = None

    # Finalization
    zip_url: str | None = None

    @property
    def total_assets(self) -> int:
        return 4  # logo, hero_lifestyle, instagram_post, packaging

    @property
    def progress(self) -> float:
        if self.total_assets == 0:
            return 0.0
        return len(self.completed_assets) / self.total_assets

    def add_transcript(self, role: str, text: str) -> None:
        self.transcript.append({"role": role, "text": text, "ts": time.time()})
        self.updated_at = time.time()

    def mark_asset_complete(self, asset_type: str, url: str) -> None:
        if asset_type not in self.completed_assets:
            self.completed_assets.append(asset_type)
        self.asset_urls[asset_type] = url
        self.updated_at = time.time()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "phase": self.phase.value,
            "brand_name": self.brand_name,
            "completed_assets": self.completed_assets,
            "asset_urls": self.asset_urls,
            "progress": self.progress,
            "palette": self.palette,
            "zip_url": self.zip_url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
