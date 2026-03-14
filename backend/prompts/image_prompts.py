"""Image generation prompt templates for Nano Banana Pro.

Nano Banana Pro (gemini-3-pro-image-preview) is a reasoning-driven model.
All prompts are DESCRIPTIVE creative briefs — zero negative instructions.
The model reasons over the brief to produce studio-quality output.
"""

# ---------------------------------------------------------------------------
# Style vocabulary — structured visual language for 6 brand archetypes
# ---------------------------------------------------------------------------

STYLE_VOCABULARY: dict[str, dict[str, str]] = {
    "luxury": {
        "lighting": "warm studio lighting with soft shadows and subtle rim light",
        "palette_usage": "deep, saturated tones with metallic or warm neutral accents",
        "texture": "rich tactile surfaces — marble, velvet, brushed metal, frosted glass",
        "mood": "aspirational, elevated, intimate",
        "photography_ref": "editorial campaign aesthetic — minimal props, maximum presence",
        "typography_style": "refined serif or elegant geometric sans-serif with generous tracking",
    },
    "modern": {
        "lighting": "clean, even lighting with crisp shadows and high clarity",
        "palette_usage": "bold primary paired with clean neutrals, high contrast",
        "texture": "smooth surfaces, matte finishes, clean geometry",
        "mood": "confident, precise, forward-looking",
        "photography_ref": "clean product campaign — precise angles, controlled backdrop",
        "typography_style": "geometric sans-serif, tight letter-spacing, strong weight contrast",
    },
    "eco": {
        "lighting": "soft, diffused natural daylight with gentle warmth",
        "palette_usage": "earth tones, sage greens, warm browns, natural whites",
        "texture": "natural materials — linen, kraft paper, raw wood, dried botanicals",
        "mood": "grounded, honest, calm, sustainable",
        "photography_ref": "organic composition — breathing space, natural surfaces",
        "typography_style": "humanist sans-serif or subtle serif with natural proportions",
    },
    "energetic": {
        "lighting": "bright, dynamic lighting with vivid color temperature",
        "palette_usage": "saturated, high-energy colors with bold contrast pairings",
        "texture": "glossy surfaces, smooth plastics, bold graphic patterns",
        "mood": "playful, bold, youthful, kinetic",
        "photography_ref": "vibrant campaign — movement, energy, pop of color",
        "typography_style": "bold rounded sans-serif or display type with personality",
    },
    "gentle": {
        "lighting": "soft, ethereal glow with pastel tones and minimal shadow",
        "palette_usage": "muted pastels, blush tones, soft whites, whisper-quiet accents",
        "texture": "soft fabrics, petal-smooth surfaces, delicate materials",
        "mood": "tender, refined, quiet luxury, delicate",
        "photography_ref": "serene intimate composition — soft focus edges, warm tone",
        "typography_style": "light-weight serif or thin sans-serif with airy spacing",
    },
    "edgy": {
        "lighting": "dramatic, high-contrast with deep shadows and selective illumination",
        "palette_usage": "dark base with sharp accent — black, charcoal, neon or red punch",
        "texture": "raw concrete, distressed metal, matte black, industrial surfaces",
        "mood": "provocative, unapologetic, raw, powerful",
        "photography_ref": "moody editorial — confrontational angles, dramatic tension",
        "typography_style": "condensed bold sans-serif or brutalist display type",
    },
}

# Synonym mapping for resolving free-text style anchors
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

    # Direct match
    for key in STYLE_VOCABULARY:
        if key in anchor_lower:
            return key

    # Synonym match
    for key, words in _STYLE_SYNONYMS.items():
        if any(w in anchor_lower for w in words):
            return key

    return "modern"


# ---------------------------------------------------------------------------
# Palette instruction builder
# ---------------------------------------------------------------------------

_ROLE_GUIDANCE: dict[str, str] = {
    "primary": "dominant brand color — use as the main visual anchor of the composition",
    "secondary": "supporting color — complement the primary in secondary elements",
    "accent": "use sparingly — a single pop of contrast on one focal detail",
    "background": "environmental tone — surfaces, backdrops, negative space",
    "neutral": "grounding element — shadows, transitions, subtle depth",
}


def _build_palette_instruction(
    palette: list[dict[str, str]] | None,
    asset_type: str,
) -> str:
    """Transform raw hex codes into actionable color direction."""
    if not palette:
        return (
            "Use a cohesive, professionally curated color palette "
            "appropriate to the brand's positioning."
        )

    lines = []
    for color in palette:
        hex_val = color.get("hex", "")
        role = color.get("role", "")
        name = color.get("name", "")
        if hex_val:
            guidance = _ROLE_GUIDANCE.get(role, f"use as {role}")
            lines.append(f"- {name} ({hex_val}): {guidance}")

    header = "Integrate these brand colors with intention throughout the composition:"
    return header + "\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Logo placement logic
# ---------------------------------------------------------------------------

def _build_logo_placement(asset_type: str, has_logo_ref: bool) -> str:
    """Smart logo placement based on product type."""
    if asset_type == "logo":
        return ""
    if not has_logo_ref:
        return "Logo reference is not yet available — focus on the product itself."
    return (
        "If the product has a packaging surface (bottle, box, bag, jar, tube, can), "
        "show the logo printed or embossed naturally on the product surface. "
        "If the product is unpackaged (jewelry, food, clothing, art, flowers), "
        "place the logo on a small tag, card, or nearby surface beside the product."
    )


# ---------------------------------------------------------------------------
# Asset templates — descriptive creative briefs (zero negatives)
# ---------------------------------------------------------------------------

LOGO_TEMPLATE = """You are a senior identity designer at a world-class branding studio.

BRIEF: Design a brand logo for '{brand_name}'.
{agent_prompt}

CREATIVE DIRECTION:
- Style: {style_anchor}
- Typography approach: {typography_style}
- This is a refined typographic wordmark or lettermark with an optional minimal geometric symbol.
- The letterforms should feel crafted and intentional — as if hand-drawn by a master typographer, then digitized.
- The logo reads clearly at 32px wide. Every stroke has purpose.
- Imagine how '{brand_name}' would look etched into metal, embossed on heavy stock paper, or reversed out of a dark surface.

COLOR:
{palette_instruction}

COMPOSITION:
- Centered on a clean, single-color background.
- The brand name '{brand_name}' is the dominant element — confident and unhurried.
- If a symbol accompanies the type, it is abstract and geometric — a single shape that echoes the brand's essence.
- Generous whitespace surrounding the mark — the logo breathes.
- Single unified composition, one lockup.

Aspect ratio: {aspect_ratio}."""

HERO_TEMPLATE = """You are an editorial photographer art-directing a premium campaign hero shot.

BRIEF: Create a lifestyle hero image for the brand '{brand_name}'.
{agent_prompt}

THE PRODUCT: The reference photo shows the actual product. This exact product appears in the final image — same shape, same proportions, same key details. It is the undeniable hero of the composition, grounded in a physical environment.

CREATIVE DIRECTION:
- Style: {style_anchor}
- Lighting: {lighting}
- Mood: {mood}
- Aesthetic: {photography_ref}

COLOR:
{palette_instruction}

COMPOSITION:
- The product is placed at a natural focal point, slightly off-center — editorial, intentional.
- Shallow depth of field draws the eye to the product first.
- {lighting}
- Two to three contextual props reinforce the brand story without cluttering the frame.
- Open space on one side for potential text overlay.
- Single unified photograph — one moment, one scene.

LOGO INTEGRATION:
{logo_placement}

Aspect ratio: {aspect_ratio}."""

INSTAGRAM_TEMPLATE = """You are a brand creative director crafting a scroll-stopping Instagram post.

BRIEF: Create an Instagram post for the brand '{brand_name}'.
{agent_prompt}

THE PRODUCT: The reference photo shows the actual product. Feature it prominently — same shape, same details. The product commands attention in the frame.

CREATIVE DIRECTION:
- Style: {style_anchor}
- Mood: {mood}
- This image stops a user mid-scroll. Visual tension, unexpected composition, or striking color contrast.
- Aesthetic: {photography_ref}

COLOR:
{palette_instruction}

COMPOSITION:
- Portrait format (4:5) — optimized for the Instagram feed.
- The product fills at least 30% of the frame with confidence.
- Strong visual hierarchy — one focal point, one clear message.
- Background complements the product through texture and color, creating depth.
- Every area of the frame is intentional — a rich, immersive photograph.
- The product feels grounded in a real environment with surfaces and light.

LOGO INTEGRATION:
{logo_placement}

Aspect ratio: {aspect_ratio}."""


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
) -> str:
    """Assemble the final image generation prompt from template + context."""

    style_key = _resolve_style_key(style_anchor)
    style = STYLE_VOCABULARY.get(style_key, STYLE_VOCABULARY["modern"])

    palette_instruction = _build_palette_instruction(palette, asset_type)
    logo_placement = _build_logo_placement(asset_type, has_logo_ref)

    template = {
        "logo": LOGO_TEMPLATE,
        "hero_lifestyle": HERO_TEMPLATE,
        "instagram_post": INSTAGRAM_TEMPLATE,
    }.get(asset_type, HERO_TEMPLATE)

    return template.format(
        brand_name=brand_name,
        agent_prompt=agent_prompt if agent_prompt else "",
        style_anchor=style_anchor or style_key,
        aspect_ratio=aspect_ratio,
        lighting=style["lighting"],
        mood=style["mood"],
        photography_ref=style["photography_ref"],
        typography_style=style["typography_style"],
        palette_instruction=palette_instruction,
        logo_placement=logo_placement,
    )
