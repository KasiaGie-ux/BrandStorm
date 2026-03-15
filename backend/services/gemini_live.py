"""Gemini Live API client service.

Manages Live API session with canvas-model tool declarations.
7 clean CRUD tools replacing the previous 11 overlapping ones.
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
# Tool declarations — 7 clean CRUD tools + 1 future multi-agent interface
# ---------------------------------------------------------------------------
TOOL_DECLARATIONS = types.Tool(
    function_declarations=[
        # 1. SET_BRAND_IDENTITY — CRUD any subset of strategy elements
        types.FunctionDeclaration(
            name="set_brand_identity",
            description=(
                "Set or update brand strategy elements. Include ONLY fields you want "
                "to change — omit the rest. The UI displays each element as it arrives."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(
                        type=types.Type.STRING,
                        description="Brand name (1-3 words, original, memorable).",
                    ),
                    "tagline": types.Schema(
                        type=types.Type.STRING,
                        description="Brand tagline (one punchy line, 4-8 words).",
                    ),
                    "story": types.Schema(
                        type=types.Type.STRING,
                        description="Brand story (2-4 sentences).",
                    ),
                    "values": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.STRING),
                        description="3-5 brand values (single words or short phrases).",
                    ),
                    "tone_do": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.STRING),
                        description="Tone of voice: what the brand DOES (3-5 rules).",
                    ),
                    "tone_dont": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.STRING),
                        description="Tone of voice: what the brand DOES NOT (3-5 rules).",
                    ),
                },
                # No required fields — agent can update any subset
            ),
        ),

        # 2. SET_PALETTE — set 5-color brand palette
        types.FunctionDeclaration(
            name="set_palette",
            description=(
                "Set or replace the 5-color brand palette. You decide the colors "
                "based on the product analysis and brand direction."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
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
                    "mood": types.Schema(type=types.Type.STRING),
                },
                required=["colors"],
            ),
        ),

        # 3. SET_FONTS — set typography pairing
        types.FunctionDeclaration(
            name="set_fonts",
            description="Set or replace the brand typography pairing.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "heading_font": types.Schema(
                        type=types.Type.STRING,
                        description="Google Fonts family name for headings.",
                    ),
                    "heading_style": types.Schema(
                        type=types.Type.STRING,
                        description="Brief style description (e.g. 'serif, elegant').",
                    ),
                    "body_font": types.Schema(
                        type=types.Type.STRING,
                        description="Google Fonts family name for body text.",
                    ),
                    "body_style": types.Schema(
                        type=types.Type.STRING,
                        description="Brief style description (e.g. 'clean, modern').",
                    ),
                },
                required=["heading_font", "body_font"],
            ),
        ),

        # 4. GENERATE_IMAGE — create a visual asset
        types.FunctionDeclaration(
            name="generate_image",
            description=(
                "Generate a brand visual asset. The image will be generated by the "
                "image model and stored on the canvas. Speak ONE evocative sentence "
                "BEFORE calling this tool."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "element": types.Schema(
                        type=types.Type.STRING,
                        enum=["logo", "hero", "instagram"],
                        description="Which canvas element to generate.",
                    ),
                    "prompt": types.Schema(
                        type=types.Type.STRING,
                        description="Detailed image generation prompt.",
                    ),
                    "style_anchor": types.Schema(
                        type=types.Type.STRING,
                        description="Creative style (luxury, modern, eco, energetic, etc.).",
                    ),
                },
                required=["element", "prompt"],
            ),
        ),

        # 5. PROPOSE_NAMES — present 3 name options
        types.FunctionDeclaration(
            name="propose_names",
            description=(
                "Present 3 brand name proposals to the user. The UI renders name "
                "cards. After calling, narrate each name then wait for user to choose."
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

        # 6. GENERATE_VOICEOVER — dual-voice brand story narration
        types.FunctionDeclaration(
            name="generate_voiceover",
            description=(
                "Generate brand story voiceover with two voices. "
                "Call after visual assets are ready, before finalize."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "handoff_text": types.Schema(
                        type=types.Type.STRING,
                        description="Your handoff line introducing Anna (1 sentence).",
                    ),
                    "greeting_text": types.Schema(
                        type=types.Type.STRING,
                        description="Anna's greeting intro (1-2 sentences).",
                    ),
                    "narration_text": types.Schema(
                        type=types.Type.STRING,
                        description="Anna's full brand story narration.",
                    ),
                    "mood": types.Schema(
                        type=types.Type.STRING,
                        enum=["luxury", "modern", "eco", "energetic", "gentle", "edgy"],
                    ),
                },
                required=["handoff_text", "narration_text", "mood"],
            ),
        ),

        # 7. FINALIZE_BRAND_KIT — package into ZIP
        types.FunctionDeclaration(
            name="finalize_brand_kit",
            description=(
                "Package all completed brand assets into a downloadable ZIP. "
                "Call only when all visual assets are ready and user is satisfied."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={},
            ),
        ),

        # 8. DELEGATE_TO_SPECIALIST — multi-agent interface (future)
        types.FunctionDeclaration(
            name="delegate_to_specialist",
            description=(
                "Delegate a task to a specialist agent for deeper expertise. "
                "NOT YET AVAILABLE — will return an error. "
                "Future specialists: marketing_advisor, color_expert, copywriter."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "specialist": types.Schema(
                        type=types.Type.STRING,
                        enum=["marketing_advisor", "color_expert", "copywriter"],
                    ),
                    "task": types.Schema(
                        type=types.Type.STRING,
                        description="What the specialist should do.",
                    ),
                    "context": types.Schema(
                        type=types.Type.STRING,
                        description="Relevant context from the current brand kit.",
                    ),
                },
                required=["specialist", "task"],
            ),
        ),
    ]
)


def create_client() -> genai.Client:
    """Create a Vertex AI genai client with ADC."""
    import os
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
    tool_names = [fd.name for fd in TOOL_DECLARATIONS.function_declarations]
    logger.info(
        f"Building LiveConnectConfig | Tools: {len(tool_names)} | Names: {tool_names}"
    )

    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        tools=[TOOL_DECLARATIONS],
        system_instruction=types.Content(
            parts=[types.Part.from_text(text=SYSTEM_PROMPT)]
        ),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=LIVE_API_VOICE,
                )
            ),
            language_code="en-US",
        ),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=False,
                start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_LOW,
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
                prefix_padding_ms=300,
                silence_duration_ms=800,
            )
        ),
    )
    return config


def image_bytes_to_part(image_bytes: bytes, mime_type: str = "image/jpeg") -> types.Part:
    """Convert raw image bytes to a genai Part for sending to Live API."""
    if not image_bytes:
        raise ValueError("image_bytes is empty")
    return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
