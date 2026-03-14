"""Session dataclass with agent state machine enum."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentPhase(str, Enum):
    """Agent state machine phases — backend orchestrates SPEECH vs TOOL turns separately."""
    INIT = "INIT"
    ANALYZING = "ANALYZING"
    ANALYSIS_SPEECH = "ANALYSIS_SPEECH"     # agent speaks analysis, no tools
    PROPOSING = "PROPOSING"                 # agent calls propose_names, no speech
    AWAITING_NAME = "AWAITING_NAME"         # waiting for user to pick a name
    REVEAL_SPEECH = "REVEAL_SPEECH"         # agent comments on chosen name, no tools
    REVEAL_TOOL = "REVEAL_TOOL"             # agent calls reveal_brand_identity, no speech
    PALETTE_SPEECH = "PALETTE_SPEECH"       # agent teases palette, no tools
    PALETTE_TOOL = "PALETTE_TOOL"           # agent calls generate_palette, no speech
    FONTS_SPEECH = "FONTS_SPEECH"           # agent teases fonts, no tools
    FONTS_TOOL = "FONTS_TOOL"               # agent calls suggest_fonts, no speech
    IMAGE_SPEECH = "IMAGE_SPEECH"           # agent teases next image, no tools
    IMAGE_TOOL = "IMAGE_TOOL"               # agent calls generate_image, no speech
    VOICEOVER_SPEECH = "VOICEOVER_SPEECH"   # agent says closing + handoff, no tools
    VOICEOVER_TOOL = "VOICEOVER_TOOL"       # agent calls generate_voiceover, no speech
    AWAITING_INPUT = "AWAITING_INPUT"
    GENERATING = "GENERATING"
    REFINING = "REFINING"
    COMPLETE = "COMPLETE"


# Valid phase transitions — permissive for the new micro-phases; strict ordering enforced by dispatcher
_MICRO_PHASES = {
    AgentPhase.ANALYSIS_SPEECH, AgentPhase.PROPOSING, AgentPhase.AWAITING_NAME,
    AgentPhase.REVEAL_SPEECH, AgentPhase.REVEAL_TOOL,
    AgentPhase.PALETTE_SPEECH, AgentPhase.PALETTE_TOOL,
    AgentPhase.FONTS_SPEECH, AgentPhase.FONTS_TOOL,
    AgentPhase.IMAGE_SPEECH, AgentPhase.IMAGE_TOOL,
    AgentPhase.VOICEOVER_SPEECH, AgentPhase.VOICEOVER_TOOL,
    AgentPhase.AWAITING_INPUT, AgentPhase.GENERATING,
    AgentPhase.REFINING, AgentPhase.COMPLETE,
}

VALID_TRANSITIONS: dict[AgentPhase, set[AgentPhase]] = {
    AgentPhase.INIT: {AgentPhase.ANALYZING},
    AgentPhase.ANALYZING: {AgentPhase.ANALYSIS_SPEECH, AgentPhase.PROPOSING},
    AgentPhase.ANALYSIS_SPEECH: {AgentPhase.PROPOSING, AgentPhase.AWAITING_NAME},
    AgentPhase.PROPOSING: {AgentPhase.AWAITING_NAME, AgentPhase.AWAITING_INPUT},
    AgentPhase.AWAITING_NAME: {AgentPhase.REVEAL_SPEECH, AgentPhase.GENERATING},
    AgentPhase.REVEAL_SPEECH: {AgentPhase.REVEAL_TOOL},
    AgentPhase.REVEAL_TOOL: {AgentPhase.PALETTE_SPEECH, AgentPhase.AWAITING_INPUT},
    AgentPhase.PALETTE_SPEECH: {AgentPhase.PALETTE_TOOL},
    AgentPhase.PALETTE_TOOL: {AgentPhase.FONTS_SPEECH, AgentPhase.AWAITING_INPUT},
    AgentPhase.FONTS_SPEECH: {AgentPhase.FONTS_TOOL},
    AgentPhase.FONTS_TOOL: {AgentPhase.IMAGE_SPEECH, AgentPhase.AWAITING_INPUT},
    AgentPhase.IMAGE_SPEECH: {AgentPhase.IMAGE_TOOL},
    AgentPhase.IMAGE_TOOL: {AgentPhase.IMAGE_SPEECH, AgentPhase.VOICEOVER_SPEECH, AgentPhase.AWAITING_INPUT},
    AgentPhase.VOICEOVER_SPEECH: {AgentPhase.VOICEOVER_TOOL},
    AgentPhase.VOICEOVER_TOOL: {AgentPhase.COMPLETE, AgentPhase.AWAITING_INPUT},
    AgentPhase.AWAITING_INPUT: {AgentPhase.GENERATING, AgentPhase.PROPOSING, AgentPhase.REVEAL_SPEECH,
                                AgentPhase.AWAITING_NAME} | _MICRO_PHASES,
    AgentPhase.GENERATING: {AgentPhase.REFINING, AgentPhase.COMPLETE, AgentPhase.AWAITING_INPUT} | _MICRO_PHASES,
    AgentPhase.REFINING: {AgentPhase.AWAITING_INPUT, AgentPhase.COMPLETE},
    AgentPhase.COMPLETE: {AgentPhase.GENERATING, AgentPhase.REFINING, AgentPhase.AWAITING_INPUT},
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

    # Generated asset bytes (for chaining as context to subsequent generations)
    logo_image_bytes: bytes | None = None
    logo_image_mime: str = "image/png"

    # Palette (set by generate_palette tool)
    palette: list[dict[str, str]] | None = None

    # Font suggestion (set by text_parser or finalize)
    font_suggestion: dict[str, Any] | None = None

    # Tone of voice (set by finalize_brand_kit tool)
    tone_of_voice: dict[str, list[str]] | None = None

    # Brand story, tagline, values (set by finalize_brand_kit tool)
    tagline: str | None = None
    brand_story: str | None = None
    brand_values: list[str] | None = None

    # Voiceover audio URL (set by generate_voiceover tool)
    audio_url: str | None = None

    # Finalization
    zip_url: str | None = None

    # Whether packaging asset is expected (agent decides based on product type)
    expects_packaging: bool = True

    # Track background image/audio generations to await them later
    pregen_tasks: dict = field(default_factory=dict)

    # Guard against runaway auto_continue loops (capped at MAX_AUTO_CONTINUE)
    auto_continue_count: int = 0

    # Pre-generated name proposals (set by parallel text-model call during analysis speech).
    # Consumed by _dispatch_next_step and propose_names tool handler.
    _pregen_names: list | None = field(default=None, repr=False)

    # Interrupt flag — set by receive_loop when user sends feedback during generation.
    # agent_loop checks this between tool calls and relays feedback to Live API.
    interrupt_text: str | None = None

    # Set True after negative feedback triggers asset regeneration.
    # Blocks auto-continue so agent asks user if they like the new version.
    # Cleared when user sends positive feedback or continues.
    awaiting_feedback: bool = False

    # Set True when user gives feedback that requires a tool call (regen asset,
    # change tagline, etc.). Blocks auto-continue until the agent actually
    # executes the corrective tool call.  Cleared in agent_loop after tool exec.
    pending_regen: bool = False

    # Set True when generate_voiceover emits events. Blocks auto-continue
    # (finalize nudge) until frontend signals voiceover playback is done.
    voiceover_playing: bool = False

    # Set True after the first successful generate_voiceover execution.
    # Guards against duplicate tool calls from Gemini self-interruption.
    voiceover_sent: bool = False

    # Set True when auto-continue fires the "speak closing sentence" nudge (C1).
    # C2 (generate_voiceover tool call) only fires after this is True.
    closing_spoken: bool = False

    # Tracks WHAT the user wants changed so nudges can reference it.
    # e.g. "tagline", "logo", "palette", "fonts", "hero", "instagram"
    pending_regen_target: str | None = None

    # Signaled by receive_loop when frontend reports audio playback finished.
    # agent_loop waits on this before sending auto-continue nudges.
    audio_done_event: Any = field(default=None, repr=False)

    def __post_init__(self):
        import asyncio
        # Initialize once here — never reassigned elsewhere.
        # Both _wait_and_nudge and _tool_background only call .clear()/.set().
        self.frontend_ready = asyncio.Event()

    @property
    def total_assets(self) -> int:
        return 3

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
            "tagline": self.tagline,
            "brand_story": self.brand_story,
            "brand_values": self.brand_values,
            "completed_assets": self.completed_assets,
            "asset_urls": self.asset_urls,
            "progress": self.progress,
            "palette": self.palette,
            "font_suggestion": self.font_suggestion,
            "tone_of_voice": self.tone_of_voice,
            "audio_url": self.audio_url,
            "zip_url": self.zip_url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
