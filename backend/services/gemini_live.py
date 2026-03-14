"""Gemini Live API client service.

Manages Live API session with full tool declarations from PRD 7.3.1.
Sends/receives audio+text. Dispatches function calls to ToolExecutor.
"""

import logging
import mimetypes
from pathlib import Path
from google import genai
from google.genai import types

from config import GCP_LOCATION, GCP_PROJECT, LIVE_API_MODEL, LIVE_API_VOICE
from prompts.system import SYSTEM_PROMPT

logger = logging.getLogger("brand-agent")


# ---------------------------------------------------------------------------
# Full tool declarations from PRD 7.3.1
# ---------------------------------------------------------------------------
TOOL_DECLARATIONS = types.Tool(
    function_declarations=[
        # ── Structured data tools (SILENT — data via JSON, agent speaks naturally) ──
        types.FunctionDeclaration(
            name="propose_names",
            description=(
                "Present 3 brand name proposals to the user. "
                "Call this INSTEAD of speaking the names out loud. "
                "The UI renders beautiful name cards automatically. "
                "Speak ONLY a short intro like 'Here are three names' "
                "BEFORE calling this tool. Do NOT list names in speech."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "names": types.Schema(
                        type=types.Type.ARRAY,
                        description="Exactly 3 name proposals.",
                        items=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "name": types.Schema(type=types.Type.STRING),
                                "rationale": types.Schema(type=types.Type.STRING),
                                "recommended": types.Schema(type=types.Type.BOOLEAN),
                            },
                            required=["name", "rationale"],
                        ),
                    ),
                },
                required=["names"],
            ),
        ),
        types.FunctionDeclaration(
            name="reveal_brand_identity",
            description=(
                "Reveal the full brand identity after user picks a name. "
                "Pass all brand data as structured JSON — do NOT speak "
                "the tagline, story, values, or tone rules out loud. "
                "The UI renders each element as beautiful cards. "
                "Speak ONLY a brief intro like 'Here is your brand identity' "
                "BEFORE calling this tool."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "brand_name": types.Schema(type=types.Type.STRING),
                    "tagline": types.Schema(type=types.Type.STRING),
                    "brand_story": types.Schema(type=types.Type.STRING),
                    "brand_values": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.STRING),
                    ),
                    "tone_of_voice_do": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.STRING),
                    ),
                    "tone_of_voice_dont": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.STRING),
                    ),
                },
                required=["brand_name", "tagline", "brand_story", "brand_values"],
            ),
        ),
        types.FunctionDeclaration(
            name="suggest_fonts",
            description=(
                "Suggest a font pairing for the brand. "
                "Call this AFTER the palette. The UI renders a typography "
                "preview. Speak ONLY a brief intro BEFORE calling."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "heading_font": types.Schema(
                        type=types.Type.STRING,
                        description="Google Fonts family name for headings.",
                    ),
                    "heading_style": types.Schema(
                        type=types.Type.STRING,
                        description="Brief style (e.g. 'serif, elegant').",
                    ),
                    "body_font": types.Schema(
                        type=types.Type.STRING,
                        description="Google Fonts family name for body text.",
                    ),
                    "body_style": types.Schema(
                        type=types.Type.STRING,
                        description="Brief style (e.g. 'clean, modern').",
                    ),
                    "rationale": types.Schema(
                        type=types.Type.STRING,
                        description="Why this pairing works.",
                    ),
                },
                required=["heading_font", "body_font"],
            ),
        ),
        # ── Generation tools ──
        types.FunctionDeclaration(
            name="generate_image",
            description=(
                "Generate a brand asset image. Speak ONE evocative sentence "
                "BEFORE calling. Do NOT say the tool name or parameters."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "asset_type": types.Schema(
                        type=types.Type.STRING,
                        enum=["logo", "hero_lifestyle", "instagram_post", "packaging"],
                    ),
                    "prompt": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "Creative direction for the image. Be specific and visual: "
                            "describe the feeling, composition, lighting mood, and how "
                            "it connects to the product. Reference what you see in the "
                            "product photo. Example: 'warm golden lighting on marble "
                            "surface, the bottle's amber glass catching the light, "
                            "editorial intimacy.'"
                        ),
                    ),
                    "aspect_ratio": types.Schema(
                        type=types.Type.STRING,
                        enum=["1:1", "4:5", "16:9"],
                    ),
                    "style_anchor": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "Visual style direction: luxury, modern, eco, energetic, "
                            "gentle, or edgy. Can combine: 'modern luxury' or "
                            "'edgy eco'. Controls lighting, texture, and mood."
                        ),
                    ),
                },
                required=["asset_type", "prompt", "style_anchor"],
            ),
        ),
        types.FunctionDeclaration(
            name="generate_palette",
            description=(
                "Generate a 5-color brand palette. You MUST provide "
                "the colors array with hex, role, and name."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "mood": types.Schema(type=types.Type.STRING),
                    "product_colors": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.STRING),
                    ),
                    "style_anchor": types.Schema(type=types.Type.STRING),
                    "colors": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "hex": types.Schema(type=types.Type.STRING),
                                "role": types.Schema(
                                    type=types.Type.STRING,
                                    enum=["primary", "secondary", "accent", "neutral", "background"],
                                ),
                                "name": types.Schema(type=types.Type.STRING),
                            },
                            required=["hex", "role", "name"],
                        ),
                    ),
                },
                required=["mood", "style_anchor", "colors"],
            ),
        ),
        types.FunctionDeclaration(
            name="finalize_brand_kit",
            description=(
                "Package all assets into a downloadable ZIP. "
                "Call only after all visual assets are complete."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "brand_name": types.Schema(type=types.Type.STRING),
                    "tagline": types.Schema(type=types.Type.STRING),
                    "brand_story": types.Schema(type=types.Type.STRING),
                    "brand_values": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.STRING),
                    ),
                    "tone_of_voice": types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "do": types.Schema(
                                type=types.Type.ARRAY,
                                items=types.Schema(type=types.Type.STRING),
                            ),
                            "dont": types.Schema(
                                type=types.Type.ARRAY,
                                items=types.Schema(type=types.Type.STRING),
                            ),
                        },
                    ),
                },
                required=["brand_name", "tagline", "brand_story",
                           "brand_values", "tone_of_voice"],
            ),
        ),
        types.FunctionDeclaration(
            name="generate_voiceover",
            description=(
                "Generate brand story voiceover with two voices. "
                "Call after visual assets, before finalize."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "handoff_text": types.Schema(
                        type=types.Type.STRING,
                        description="Charon's handoff line introducing Anna (1 sentence).",
                    ),
                    "greeting_text": types.Schema(
                        type=types.Type.STRING,
                        description="Anna's short greeting intro (1-2 sentences, e.g. 'Hi, I'm Anna. Let me tell you the story of...'). Separate from the brand story.",
                    ),
                    "narration_text": types.Schema(
                        type=types.Type.STRING,
                        description="Anna's full brand story narration (the story only, without the greeting).",
                    ),
                    "mood": types.Schema(
                        type=types.Type.STRING,
                        enum=["luxury", "modern", "eco", "energetic", "gentle", "edgy"],
                    ),
                },
                required=["handoff_text", "greeting_text", "narration_text", "mood"],
            ),
        ),
    ]
)


def create_client() -> genai.Client:
    """Create a Vertex AI genai client with ADC."""
    import os
    # Suppress google.auth warning about missing project — we pass it explicitly
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", GCP_PROJECT)
    logger.info(f"Creating genai client | Project: {GCP_PROJECT} | Location: {GCP_LOCATION}")
    return genai.Client(
        vertexai=True,
        project=GCP_PROJECT,
        location=GCP_LOCATION,
        http_options=types.HttpOptions(api_version="v1beta1"),
    )


def build_live_config() -> types.LiveConnectConfig:
    """Build the LiveConnectConfig with all tools and system prompt."""
    tool_names = [
        fd.name for fd in TOOL_DECLARATIONS.function_declarations
    ]
    logger.info(
        f"Building LiveConnectConfig | Tools registered: {len(tool_names)} | "
        f"Names: {tool_names}"
    )
    # Live API only supports ONE response modality at a time.
    # Use AUDIO so the agent speaks, plus output_audio_transcription
    # so we get text transcripts for structured event parsing.
    logger.info("Using AUDIO modality + transcription")
    modalities = [types.Modality.AUDIO]

    logger.info(
        f"Model: {LIVE_API_MODEL} | Modalities: {modalities} | Voice: {LIVE_API_VOICE}"
    )

    config = types.LiveConnectConfig(
        response_modalities=modalities,
        tools=[TOOL_DECLARATIONS],
        system_instruction=types.Content(
            parts=[types.Part.from_text(text=SYSTEM_PROMPT)]
        ),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=LIVE_API_VOICE,
                )
            )
        ),
    )

    return config


def image_bytes_to_part(image_bytes: bytes, mime_type: str = "image/jpeg") -> types.Part:
    """Convert raw image bytes to a genai Part for sending to Live API."""
    if not image_bytes:
        raise ValueError("image_bytes is empty — cannot create Part from empty data")
    part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    logger.info(
        f"Created image Part | Size: {len(image_bytes)} bytes | MIME: {mime_type} | "
        f"Part type: {type(part).__name__} | "
        f"Has inline_data: {part.inline_data is not None}"
    )
    return part


def load_image_from_path(image_path: str) -> tuple[types.Part, str]:
    """Load image from disk path. Returns (Part, mime_type)."""
    path = Path(image_path)
    mime_type = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    image_bytes = path.read_bytes()
    part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    return part, mime_type
