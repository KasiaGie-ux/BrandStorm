"""Brand Canvas — the source of truth for all brand elements.

Each element tracks its value, status, and what inputs were used to generate it
(generation_context). The agent receives a snapshot of this canvas on every turn
and autonomously decides what to create, regenerate, or skip.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ElementStatus(str, Enum):
    """Status of a single brand element on the canvas."""
    EMPTY = "empty"
    GENERATING = "generating"
    READY = "ready"
    STALE = "stale"


@dataclass
class BrandElement:
    """A single element in the brand kit canvas."""
    value: Any = None
    status: ElementStatus = ElementStatus.EMPTY
    generation_context: dict = field(default_factory=dict)
    updated_at: float = 0.0

    def set(self, value: Any, context: dict | None = None) -> None:
        self.value = value
        self.status = ElementStatus.READY
        if context is not None:
            self.generation_context = context
        self.updated_at = time.time()

    def mark_stale(self) -> None:
        if self.status in (ElementStatus.READY, ElementStatus.GENERATING):
            self.status = ElementStatus.STALE

    def mark_generating(self) -> None:
        self.status = ElementStatus.GENERATING

    def clear(self) -> None:
        self.value = None
        self.status = ElementStatus.EMPTY
        self.generation_context = {}
        self.updated_at = 0.0


# All canvas element field names (order matters for snapshot iteration)
ELEMENT_NAMES: list[str] = [
    "name", "tagline", "story", "values", "tone",
    "palette", "fonts",
    "logo", "hero", "instagram",
    "voiceover",
]

# Elements that are visual assets (URLs, not inline values)
_URL_ELEMENTS = {"logo", "hero", "instagram", "voiceover"}

# Total scoreable elements (voiceover is optional, excluded from progress)
_SCOREABLE_ELEMENTS = [n for n in ELEMENT_NAMES if n != "voiceover"]


@dataclass
class BrandCanvas:
    """The complete brand kit canvas.

    This IS the session memory. The agent receives a snapshot of this
    on every turn to make autonomous decisions.
    """
    # Strategy
    name: BrandElement = field(default_factory=BrandElement)
    tagline: BrandElement = field(default_factory=BrandElement)
    story: BrandElement = field(default_factory=BrandElement)
    values: BrandElement = field(default_factory=BrandElement)
    tone: BrandElement = field(default_factory=BrandElement)

    # Design system
    palette: BrandElement = field(default_factory=BrandElement)
    fonts: BrandElement = field(default_factory=BrandElement)

    # Visual assets
    logo: BrandElement = field(default_factory=BrandElement)
    hero: BrandElement = field(default_factory=BrandElement)
    instagram: BrandElement = field(default_factory=BrandElement)

    # Audio
    voiceover: BrandElement = field(default_factory=BrandElement)

    # Creative direction (set once during analysis, referenced by agent)
    style_anchor: str = ""

    def snapshot(self) -> dict:
        """JSON-serializable snapshot for agent context injection and frontend."""
        result = {}
        for field_name in ELEMENT_NAMES:
            el: BrandElement = getattr(self, field_name)
            entry: dict[str, Any] = {"status": el.status.value}
            if el.status in (ElementStatus.READY, ElementStatus.STALE):
                if field_name in _URL_ELEMENTS:
                    entry["url"] = el.value
                else:
                    entry["value"] = el.value
                entry["generated_with"] = el.generation_context
            result[field_name] = entry
        result["style_anchor"] = self.style_anchor
        result["progress"] = self.progress
        return result

    def element_by_name(self, name: str) -> BrandElement | None:
        if name in ELEMENT_NAMES:
            return getattr(self, name)
        return None

    @property
    def ready_count(self) -> int:
        return sum(
            1 for n in _SCOREABLE_ELEMENTS
            if getattr(self, n).status == ElementStatus.READY
        )

    @property
    def total_elements(self) -> int:
        return len(_SCOREABLE_ELEMENTS)

    @property
    def progress(self) -> float:
        total = self.total_elements
        return self.ready_count / total if total > 0 else 0.0

    @property
    def asset_urls(self) -> dict[str, str]:
        """Return a dict of element_name → URL for all ready visual assets."""
        urls = {}
        for name in _URL_ELEMENTS:
            el: BrandElement = getattr(self, name)
            if el.status == ElementStatus.READY and el.value:
                urls[name] = el.value
        return urls
