"""BrandKit dataclass — holds all generated brand assets and metadata."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PaletteColor:
    """Single color in the brand palette."""
    hex: str
    role: str  # primary, secondary, accent, neutral, background
    name: str = ""


@dataclass
class ToneOfVoice:
    """Brand tone of voice guide."""
    do: list[str] = field(default_factory=list)
    dont: list[str] = field(default_factory=list)


@dataclass
class BrandKit:
    """Complete brand kit output — 11 assets."""

    # Strategy (text assets)
    name: str | None = None
    name_rationale: str | None = None
    tagline: str | None = None
    brand_story: str | None = None
    brand_values: list[str] = field(default_factory=list)
    tone_of_voice: ToneOfVoice = field(default_factory=ToneOfVoice)

    # Palette
    palette: list[PaletteColor] = field(default_factory=list)

    # Visual assets (URLs or base64)
    logo_url: str | None = None
    hero_url: str | None = None
    instagram_url: str | None = None
    packaging_url: str | None = None

    # Style
    style_anchor: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "name_rationale": self.name_rationale,
            "tagline": self.tagline,
            "brand_story": self.brand_story,
            "brand_values": self.brand_values,
            "tone_of_voice": {
                "do": self.tone_of_voice.do,
                "dont": self.tone_of_voice.dont,
            },
            "palette": [
                {"hex": c.hex, "role": c.role, "name": c.name}
                for c in self.palette
            ],
            "assets": {
                "logo": self.logo_url,
                "hero_lifestyle": self.hero_url,
                "instagram_post": self.instagram_url,
                "packaging": self.packaging_url,
            },
            "style_anchor": self.style_anchor,
        }
