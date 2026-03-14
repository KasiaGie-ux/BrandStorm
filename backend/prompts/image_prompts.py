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
        "lighting": "warm directional studio lighting with gobo-dappled shadows and a 45-degree kicker rim light separating the product from the background",
        "optics": "pronounced caustics refracting through glass and translucent surfaces onto the set, crisp specular highlights outlining product edges, subtle subsurface scattering on organic materials",
        "camera": "captured on a medium format 85mm lens at f/2.8 -- natural optical depth-of-field roll-off, tack-sharp focal plane",
        "palette_usage": "deep, saturated tones with metallic or warm neutral accents",
        "texture": "rich tactile surfaces -- marble, velvet, brushed metal, frosted glass",
        "mood": "aspirational, elevated, intimate",
        "photography_ref": "editorial campaign aesthetic -- minimal props, maximum presence",
        "typography_style": "high-contrast serif with razor-sharp terminals and impeccable optical kerning, or elegant geometric sans-serif with generous tracking and refined stroke modulation",
    },
    "modern": {
        "lighting": "clean, even key light with crisp geometric shadows and high clarity, precise light fall-off at surface edges",
        "optics": "clean specular edges with controlled reflections, precise light fall-off, minimal scatter -- every surface reads with clinical sharpness",
        "camera": "shot on a 35mm prime lens at f/5.6 -- tack-sharp across the entire frame, precise rendering of edges and surfaces",
        "palette_usage": "bold primary paired with clean neutrals, high contrast",
        "texture": "smooth surfaces, matte finishes, clean geometry",
        "mood": "confident, precise, forward-looking",
        "photography_ref": "clean product campaign -- precise angles, controlled backdrop",
        "typography_style": "geometric sans-serif with monoline stroke weight, tight optical kerning, grid-based Swiss composition, strong weight contrast between display and body sizes",
    },
    "eco": {
        "lighting": "soft, diffused natural daylight filtering through foliage, gentle warmth with dappled leaf-shadow patterns across surfaces",
        "optics": "subsurface scattering through leaves and organic materials giving them a living inner glow, soft light diffusion wrapping around natural textures",
        "camera": "50mm natural perspective lens at f/4 -- gentle depth separation, honest rendering without optical distortion",
        "palette_usage": "earth tones, sage greens, warm browns, natural whites",
        "texture": "natural materials -- linen, kraft paper, raw wood, dried botanicals",
        "mood": "grounded, honest, calm, sustainable",
        "photography_ref": "organic composition -- breathing space, natural surfaces",
        "typography_style": "humanist sans-serif with organic stroke modulation and natural proportions, or subtle serif with hand-drawn warmth and open counters",
    },
    "energetic": {
        "lighting": "bright, dynamic lighting with vivid color temperature, multiple colored light sources creating energetic interplay",
        "optics": "vivid specular bounces across glossy surfaces, saturated color reflections between objects, dynamic light flares and prismatic color spill",
        "camera": "24mm wide-angle lens at f/4 -- dynamic perspective with slight barrel energy, sense of motion and immediacy",
        "palette_usage": "saturated, high-energy colors with bold contrast pairings",
        "texture": "glossy surfaces, smooth plastics, bold graphic patterns",
        "mood": "playful, bold, youthful, kinetic",
        "photography_ref": "vibrant campaign -- movement, energy, pop of color",
        "typography_style": "bold rounded sans-serif with uniform stroke weight and open counters, or expressive display type with Bauhaus geometry and playful personality",
    },
    "gentle": {
        "lighting": "soft, ethereal glow with luminous wrap-around light, pastel tones and feathered shadow edges",
        "optics": "delicate specular shimmer on smooth surfaces, ethereal light bloom around highlights, soft luminous wrap that dissolves hard edges",
        "camera": "90mm portrait lens at f/2 -- creamy bokeh with soft optical transitions, intimate close perspective",
        "palette_usage": "muted pastels, blush tones, soft whites, whisper-quiet accents",
        "texture": "soft fabrics, petal-smooth surfaces, delicate materials",
        "mood": "tender, refined, quiet luxury, delicate",
        "photography_ref": "serene intimate composition -- soft focus edges, warm tone",
        "typography_style": "light-weight serif with delicate hairline strokes and graceful terminals, or thin sans-serif with airy letter-spacing and gentle curves",
    },
    "edgy": {
        "lighting": "dramatic, high-contrast with deep shadows and selective hard illumination, razor-sharp light boundaries",
        "optics": "harsh specular fall-off with razor-sharp light-to-shadow transitions, dramatic chiaroscuro, selective illumination carving the product out of darkness",
        "camera": "28mm wide lens at f/8 -- confrontational perspective with deep focus, everything rendered with raw sharpness",
        "palette_usage": "dark base with sharp accent -- black, charcoal, neon or red punch",
        "texture": "raw concrete, distressed metal, matte black, industrial surfaces",
        "mood": "provocative, unapologetic, raw, powerful",
        "photography_ref": "moody editorial -- confrontational angles, dramatic tension",
        "typography_style": "condensed bold sans-serif with aggressive vertical proportions and tight negative space, or brutalist display type with raw geometric authority",
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


def _build_tagline_typography(tagline: str | None) -> str:
    """Tagline rendering instruction for logo template."""
    if not tagline:
        return ""
    return (
        f"The tagline \"{tagline}\" renders in a tracking-widened, microscopic "
        f"geometric sans-serif — subordinate to the wordmark, precise and unhurried."
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

TYPOGRAPHY & DESIGN DIRECTION:
Strictly flat 2D vector graphic. Every shape has razor-sharp, perfectly clean edges
with crisp opaque solid fills — absolute typographic precision.
Bespoke letterforms: {typography_style}.
Every stroke, terminal, and counter is purposeful. The word '{brand_name}' reads
clearly even at 32px. Impeccable optical kerning -- each letter pair balanced by eye.
{agent_creative_hint}
{tagline_typography}

{palette_instruction}

COMPOSITION:
Strict flat vector lockup. The background is a single solid color — white if the
logo is dark, dark if the logo is light — chosen for maximum contrast and legibility.
Grid-based type architecture -- every element aligned to an invisible structure. The brand name is
the dominant element -- confident and unhurried. If a symbol accompanies the type,
it is a single abstract geometric form — not a standard icon or clipart shape, but a
custom minimalist construction that architecturally interprets the brand's essence.
Bold, unhurried, confident.
Generous whitespace -- the logo breathes.

FORMAT: {aspect_ratio}, single unified lockup."""

HERO_TEMPLATE = """Generate a premium editorial lifestyle photograph for the brand '{brand_name}'.

{brand_context}

THE PRODUCT:
The reference photo shows the actual product. This exact product appears in the final
image -- same shape, proportions, and key details. It is the undeniable hero of the
composition, grounded in a physical environment.
The product is shown in a natural, physically plausible position — as it would rest
on a surface or be held in real life. Present the product in its most polished,
idealized form — pristine surfaces, perfect condition, studio-quality rendering
regardless of the reference photo quality.

SCENE AND MOOD:
Style: {style_anchor}. Mood: {mood}.
{camera}.
{lighting}. {optics}.
Surfaces and textures: {texture}.
{photography_ref}.
{agent_creative_hint}

{palette_instruction}

COMPOSITION:
Product placed at a natural focal point, slightly off-center -- editorial, intentional.
The lens delivers natural depth separation -- the product is tack-sharp while the
background softens through optical fall-off. Two to three contextual props reinforce the
brand story. Open space on one side for potential text overlay. Cinematic light physics.
{logo_placement}

FORMAT: {aspect_ratio}, single unified photograph -- one moment, one scene."""

INSTAGRAM_TEMPLATE = """Generate a scroll-stopping Instagram post photograph for the brand '{brand_name}'.

{brand_context}

THE PRODUCT:
The reference photo shows the actual product. Feature it prominently -- same shape,
same details. The product commands attention in the frame.
The product is shown in a natural, physically plausible position — as it would rest
on a surface or be worn in real life. Present the product in its most polished,
idealized form — pristine, flawless, studio-quality regardless of reference photo quality.

VISUAL IMPACT:
Style: {style_anchor}. Mood: {mood}.
{camera}.
{lighting}. {optics}.
This image stops a user mid-scroll through visual tension, unexpected composition,
or striking color contrast. {photography_ref}.
{agent_creative_hint}

{palette_instruction}

COMPOSITION:
Portrait format (4:5), optimized for Instagram feed. Product fills at least 30% of the
frame. Strong visual hierarchy -- one focal point, one clear message. Background
complements the product through texture and color. The product feels grounded in a
real environment with surfaces and light. Cinematic light physics throughout.
Every area of the frame is intentional.
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
    tagline_typography = _build_tagline_typography(tagline)

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
        optics=style.get("optics", ""),
        camera=style.get("camera", ""),
        mood=style["mood"],
        texture=style.get("texture", ""),
        photography_ref=style["photography_ref"],
        typography_style=style["typography_style"],
        palette_instruction=palette_instruction,
        logo_placement=logo_placement,
        tagline_typography=tagline_typography,
    )
