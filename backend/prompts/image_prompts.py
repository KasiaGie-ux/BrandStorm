"""Image generation prompt templates for Nano Banana Pro.

Nano Banana Pro (gemini-3-pro-image-preview) is a reasoning-driven model.
All prompts are DESCRIPTIVE creative briefs -- zero negative instructions.

Architecture: the TEMPLATE controls quality and structure. The agent's
contributions (brand name, style, mood) are slotted into specific places.
The agent's free-text `prompt` is treated as an optional creative hint,
woven into the brief alongside data we pull from the session.
"""

# ---------------------------------------------------------------------------
# Style vocabulary -- structured visual language for 6 brand archetypes
# ---------------------------------------------------------------------------

STYLE_VOCABULARY: dict[str, dict[str, str]] = {
    "luxury": {
        "lighting": "warm studio lighting with soft shadows and subtle rim light",
        "palette_usage": "deep, saturated tones with metallic or warm neutral accents",
        "texture": "rich tactile surfaces -- marble, velvet, brushed metal, frosted glass",
        "mood": "aspirational, elevated, intimate",
        "photography_ref": "editorial campaign aesthetic -- minimal props, maximum presence",
        "typography_style": "refined serif or elegant geometric sans-serif with generous tracking",
    },
    "modern": {
        "lighting": "clean, even lighting with crisp shadows and high clarity",
        "palette_usage": "bold primary paired with clean neutrals, high contrast",
        "texture": "smooth surfaces, matte finishes, clean geometry",
        "mood": "confident, precise, forward-looking",
        "photography_ref": "clean product campaign -- precise angles, controlled backdrop",
        "typography_style": "geometric sans-serif, tight letter-spacing, strong weight contrast",
    },
    "eco": {
        "lighting": "soft, diffused natural daylight with gentle warmth",
        "palette_usage": "earth tones, sage greens, warm browns, natural whites",
        "texture": "natural materials -- linen, kraft paper, raw wood, dried botanicals",
        "mood": "grounded, honest, calm, sustainable",
        "photography_ref": "organic composition -- breathing space, natural surfaces",
        "typography_style": "humanist sans-serif or subtle serif with natural proportions",
    },
    "energetic": {
        "lighting": "bright, dynamic lighting with vivid color temperature",
        "palette_usage": "saturated, high-energy colors with bold contrast pairings",
        "texture": "glossy surfaces, smooth plastics, bold graphic patterns",
        "mood": "playful, bold, youthful, kinetic",
        "photography_ref": "vibrant campaign -- movement, energy, pop of color",
        "typography_style": "bold rounded sans-serif or display type with personality",
    },
    "gentle": {
        "lighting": "soft, ethereal glow with pastel tones and minimal shadow",
        "palette_usage": "muted pastels, blush tones, soft whites, whisper-quiet accents",
        "texture": "soft fabrics, petal-smooth surfaces, delicate materials",
        "mood": "tender, refined, quiet luxury, delicate",
        "photography_ref": "serene intimate composition -- soft focus edges, warm tone",
        "typography_style": "light-weight serif or thin sans-serif with airy spacing",
    },
    "edgy": {
        "lighting": "dramatic, high-contrast with deep shadows and selective illumination",
        "palette_usage": "dark base with sharp accent -- black, charcoal, neon or red punch",
        "texture": "raw concrete, distressed metal, matte black, industrial surfaces",
        "mood": "provocative, unapologetic, raw, powerful",
        "photography_ref": "moody editorial -- confrontational angles, dramatic tension",
        "typography_style": "condensed bold sans-serif or brutalist display type",
    },
}

_STYLE_SYNONYMS: dict[str, list[str]] = {
    "luxury": ["premium", "high-end", "sophisticated", "elegant", "refined", "opulent", "luxe"],
    "modern": ["contemporary", "minimal", "clean", "technical", "tech", "futuristic", "sleek"],
    "eco": ["natural", "organic", "sustainable", "earthy", "botanical", "green", "nature"],
    "energetic": ["fun", "playful", "vibrant", "bold", "dynamic", "youthful", "sporty", "pop"],
    "gentle": ["soft", "feminine", "delicate", "pastel", "tender", "serene", "calm", "romantic"],
    "edgy": ["raw", "industrial", "dark", "moody", "urban", "punk", "street", "grunge"],
}


def _resolve_style_key(style_anchor: str) -> str:
    """Map agent's free-text style anchor to a vocabulary key."""
    if not style_anchor:
        return "modern"
    anchor_lower = style_anchor.lower().strip()
    for key in STYLE_VOCABULARY:
        if key in anchor_lower:
            return key
    for key, words in _STYLE_SYNONYMS.items():
        if any(w in anchor_lower for w in words):
            return key
    return "modern"


# ---------------------------------------------------------------------------
# Palette instruction builder
# ---------------------------------------------------------------------------

_ROLE_GUIDANCE: dict[str, str] = {
    "primary": "dominant brand color -- use as the main visual anchor",
    "secondary": "supporting color -- complement the primary in secondary elements",
    "accent": "use sparingly -- a single pop of contrast on one focal detail",
    "background": "environmental tone -- surfaces, backdrops, negative space",
    "neutral": "grounding element -- shadows, transitions, subtle depth",
}


def _build_palette_instruction(palette: list[dict[str, str]] | None) -> str:
    """Transform raw hex codes into actionable color direction."""
    if not palette:
        return "Use a cohesive, professionally curated color palette."

    lines = []
    for color in palette:
        hex_val = color.get("hex", "")
        role = color.get("role", "")
        name = color.get("name", "")
        if hex_val:
            guidance = _ROLE_GUIDANCE.get(role, f"use as {role}")
            lines.append(f"  - {name} ({hex_val}): {guidance}")

    return "Brand colors:\n" + "\n".join(lines)


def _build_logo_placement(has_logo_ref: bool) -> str:
    """Smart logo placement instruction."""
    if not has_logo_ref:
        return ""
    return (
        "If the product has packaging (bottle, box, bag, jar, tube, can), "
        "show the logo printed or embossed on the product surface. "
        "If unpackaged (jewelry, food, clothing, art, flowers), "
        "place the logo on a small tag or card beside the product."
    )


def _brand_context_block(
    brand_name: str,
    tagline: str | None,
    brand_values: list[str] | None,
) -> str:
    """Build a compact brand context block from session data."""
    parts = [f"Brand: {brand_name}"]
    if tagline:
        parts.append(f"Tagline: \"{tagline}\"")
    if brand_values:
        parts.append(f"Values: {', '.join(brand_values)}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Asset templates -- WE control quality, agent fills the slots
# ---------------------------------------------------------------------------

LOGO_TEMPLATE = """Generate a brand logo -- a refined typographic wordmark for '{brand_name}'.

{brand_context}

TYPOGRAPHY:
The logo is built from carefully crafted letterforms in a {typography_style} style.
Every stroke has purpose. The word '{brand_name}' reads clearly even at 32px.
Imagine it etched into metal, embossed on heavy paper, reversed on dark background.
{agent_creative_hint}

{palette_instruction}

COMPOSITION:
Centered on a clean, single-color background. The brand name is the dominant element --
confident and unhurried. If a symbol accompanies the type, it is a single abstract
geometric shape that echoes the brand's essence. Generous whitespace -- the logo breathes.

FORMAT: {aspect_ratio}, single unified lockup."""

HERO_TEMPLATE = """Generate a premium editorial lifestyle photograph for the brand '{brand_name}'.

{brand_context}

THE PRODUCT:
The reference photo shows the actual product. This exact product appears in the final
image -- same shape, proportions, and key details. It is the undeniable hero of the
composition, grounded in a physical environment.

SCENE AND MOOD:
Style: {style_anchor}. Mood: {mood}.
{lighting}. Surfaces and textures: {texture}.
{photography_ref}.
{agent_creative_hint}

{palette_instruction}

COMPOSITION:
Product placed at a natural focal point, slightly off-center -- editorial, intentional.
Shallow depth of field draws the eye to the product first. Two to three contextual props
reinforce the brand story. Open space on one side for potential text overlay.
{logo_placement}

FORMAT: {aspect_ratio}, single unified photograph -- one moment, one scene."""

INSTAGRAM_TEMPLATE = """Generate a scroll-stopping Instagram post photograph for the brand '{brand_name}'.

{brand_context}

THE PRODUCT:
The reference photo shows the actual product. Feature it prominently -- same shape,
same details. The product commands attention in the frame.

VISUAL IMPACT:
Style: {style_anchor}. Mood: {mood}.
This image stops a user mid-scroll through visual tension, unexpected composition,
or striking color contrast. {photography_ref}.
{agent_creative_hint}

{palette_instruction}

COMPOSITION:
Portrait format (4:5), optimized for Instagram feed. Product fills at least 30% of the
frame. Strong visual hierarchy -- one focal point, one clear message. Background
complements the product through texture and color. The product feels grounded in a
real environment with surfaces and light. Every area of the frame is intentional.
{logo_placement}

FORMAT: {aspect_ratio}, single rich immersive photograph."""


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_image_prompt(
    agent_prompt: str,
    asset_type: str,
    brand_name: str,
    style_anchor: str,
    aspect_ratio: str,
    palette: list[dict[str, str]] | None = None,
    has_logo_ref: bool = False,
    tagline: str | None = None,
    brand_values: list[str] | None = None,
) -> str:
    """Assemble final image prompt. Template controls quality, agent fills slots."""

    style_key = _resolve_style_key(style_anchor)
    style = STYLE_VOCABULARY.get(style_key, STYLE_VOCABULARY["modern"])

    palette_instruction = _build_palette_instruction(palette)
    logo_placement = _build_logo_placement(has_logo_ref)
    brand_context = _brand_context_block(brand_name, tagline, brand_values)

    # Agent's free-text prompt becomes a creative hint woven into the brief
    agent_creative_hint = ""
    if agent_prompt and agent_prompt.strip():
        agent_creative_hint = f"Creative direction: {agent_prompt.strip()}"

    template = {
        "logo": LOGO_TEMPLATE,
        "hero_lifestyle": HERO_TEMPLATE,
        "instagram_post": INSTAGRAM_TEMPLATE,
    }.get(asset_type, HERO_TEMPLATE)

    return template.format(
        brand_name=brand_name,
        brand_context=brand_context,
        agent_creative_hint=agent_creative_hint,
        style_anchor=style_anchor or style_key,
        aspect_ratio=aspect_ratio,
        lighting=style["lighting"],
        mood=style["mood"],
        texture=style.get("texture", ""),
        photography_ref=style["photography_ref"],
        typography_style=style["typography_style"],
        palette_instruction=palette_instruction,
        logo_placement=logo_placement,
    )
