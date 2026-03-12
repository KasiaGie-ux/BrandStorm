"""Gemini Live API client service.

Manages Live API session with full tool declarations from PRD 7.3.1.
Sends/receives audio+text. Dispatches function calls to ToolExecutor.
"""

import logging
import mimetypes
from pathlib import Path
from google import genai
from google.genai import types

from config import GCP_LOCATION, GCP_PROJECT, LIVE_API_MODEL
from prompts.system import SYSTEM_PROMPT

logger = logging.getLogger("brand-agent")


# ---------------------------------------------------------------------------
# Full tool declarations from PRD 7.3.1
# ---------------------------------------------------------------------------
TOOL_DECLARATIONS = types.Tool(
    function_declarations=[
        # NOTE: analyze_product removed — agent analyzes via vision directly.
        # The spike proved this works. The tool was causing the agent to stall
        # because the response had no useful data (agent already sees the image).
        types.FunctionDeclaration(
            name="generate_image",
            description=(
                "Generate a brand asset image. Use this when you are ready "
                "to create a visual asset for the brand kit. Always narrate "
                "your creative reasoning BEFORE calling this tool."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "asset_type": types.Schema(
                        type=types.Type.STRING,
                        enum=["logo", "hero_lifestyle", "instagram_post", "packaging"],
                        description="Type of brand asset to generate.",
                    ),
                    "prompt": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "Detailed image generation prompt. Must reference "
                            "the product, brand name, style anchor, and color palette."
                        ),
                    ),
                    "aspect_ratio": types.Schema(
                        type=types.Type.STRING,
                        enum=["1:1", "4:5", "16:9"],
                        description="Image aspect ratio. Use 4:5 for Instagram.",
                    ),
                    "style_anchor": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "Visual style: luxury, energetic, eco, modern, gentle, edgy"
                        ),
                    ),
                },
                required=["asset_type", "prompt", "style_anchor"],
            ),
        ),
        types.FunctionDeclaration(
            name="generate_palette",
            description=(
                "Generate a 5-color brand palette based on product analysis "
                "and brand direction. You MUST provide the colors array with "
                "hex values, roles, and names."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "mood": types.Schema(
                        type=types.Type.STRING,
                        description="Overall mood for the palette.",
                    ),
                    "product_colors": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.STRING),
                        description="Dominant colors observed in the product photo.",
                    ),
                    "style_anchor": types.Schema(
                        type=types.Type.STRING,
                        description="Visual style anchor.",
                    ),
                    "colors": types.Schema(
                        type=types.Type.ARRAY,
                        description="The 5 brand colors with hex, role, and name.",
                        items=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "hex": types.Schema(
                                    type=types.Type.STRING,
                                    description="Hex color code e.g. #1a1a2e",
                                ),
                                "role": types.Schema(
                                    type=types.Type.STRING,
                                    enum=["primary", "secondary", "accent", "neutral", "background"],
                                    description="Color role in the palette.",
                                ),
                                "name": types.Schema(
                                    type=types.Type.STRING,
                                    description="Creative color name e.g. Deep Ink",
                                ),
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
                "Package all generated assets into a downloadable ZIP. "
                "Call this only after all visual assets are complete."
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
                "Record the brand story as a professional voiceover. "
                "Pick a voice that matches the brand mood. Call this "
                "after generating visual assets but before finalize_brand_kit."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "text": types.Schema(
                        type=types.Type.STRING,
                        description="Brand story text to narrate.",
                    ),
                    "mood": types.Schema(
                        type=types.Type.STRING,
                        enum=["luxury", "modern", "eco", "energetic", "gentle", "edgy"],
                        description="The brand mood — determines voice selection.",
                    ),
                },
                required=["text", "mood"],
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
    # gemini-2.0-flash-live supports TEXT+AUDIO with function calling.
    # Native-audio models use AUDIO only but have weak function calling.
    is_native_audio = "native-audio" in LIVE_API_MODEL
    if is_native_audio:
        logger.info("Using AUDIO-only modality (native-audio model)")
        modalities = [types.Modality.AUDIO]
    else:
        logger.info("Using TEXT modality (standard Live API — reliable tool calling)")
        modalities = [types.Modality.TEXT]

    logger.info(
        f"Model: {LIVE_API_MODEL} | Modalities: {modalities}"
    )

    config = types.LiveConnectConfig(
        response_modalities=modalities,
        tools=[TOOL_DECLARATIONS],
        system_instruction=types.Content(
            parts=[types.Part.from_text(text=SYSTEM_PROMPT)]
        ),
    )
    # Audio transcription only needed for native-audio models
    if is_native_audio:
        config.output_audio_transcription = types.AudioTranscriptionConfig()

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
