"""Voiceover generation via Gemini TTS.

Uses gemini-2.5-flash-preview-tts to narrate the brand story.
Picks a voice that matches the brand mood/style anchor.
Returns WAV bytes or None on failure.
"""

import logging
import time
from pathlib import Path

from google import genai
from google.genai import types

from config import GCP_PROJECT, GCP_LOCATION

logger = logging.getLogger("brand-agent")

# Voice map — mood → voice name
VOICE_MAP: dict[str, str] = {
    "luxury": "Kore",
    "modern": "Puck",
    "eco": "Aoede",
    "energetic": "Charon",
    "gentle": "Leda",
    "edgy": "Orus",
}

DEFAULT_VOICE = "Kore"
TTS_MODEL = "gemini-2.5-flash-preview-tts"


def _pick_voice(mood: str) -> str:
    """Pick a TTS voice based on mood string."""
    if not mood:
        return DEFAULT_VOICE
    mood_lower = mood.lower().strip()
    if mood_lower in VOICE_MAP:
        return VOICE_MAP[mood_lower]
    # Fuzzy match: check if any key is a substring
    for key, voice in VOICE_MAP.items():
        if key in mood_lower or mood_lower in key:
            return voice
    return DEFAULT_VOICE


async def generate_voiceover(
    session_id: str,
    text: str,
    mood: str = "",
) -> bytes | None:
    """Generate a voiceover WAV from text using Gemini TTS.

    Returns WAV bytes on success, None on failure.
    """
    if not text or not text.strip():
        logger.warning(
            f"[{session_id}] Phase: GENERATING | Action: voiceover_empty_text | "
            f"Skipping TTS — no text provided"
        )
        return None

    voice = _pick_voice(mood)
    t0 = time.perf_counter()

    logger.info(
        f"[{session_id}] Phase: GENERATING | Action: voiceover_starting | "
        f"Voice: {voice} | Mood: {mood} | Text length: {len(text)}"
    )

    try:
        client = genai.Client(
            vertexai=True,
            project=GCP_PROJECT,
            location=GCP_LOCATION,
            http_options=types.HttpOptions(api_version="v1beta1"),
        )

        response = await client.aio.models.generate_content(
            model=TTS_MODEL,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice,
                        ),
                    ),
                ),
            ),
        )

        # Extract audio data from response
        if (
            response.candidates
            and response.candidates[0].content
            and response.candidates[0].content.parts
        ):
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
                    audio_bytes = part.inline_data.data
                    latency = (time.perf_counter() - t0) * 1000
                    logger.info(
                        f"[{session_id}] Phase: GENERATING | Action: voiceover_success | "
                        f"Voice: {voice} | Size: {len(audio_bytes)} bytes | "
                        f"Latency: {latency:.0f}ms"
                    )
                    return audio_bytes

        logger.warning(
            f"[{session_id}] Phase: GENERATING | Action: voiceover_no_audio | "
            f"Response had no audio parts"
        )
        return None

    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000
        logger.error(
            f"[{session_id}] Phase: GENERATING | Action: voiceover_failed | "
            f"Voice: {voice} | Error: {e} | Latency: {latency:.0f}ms"
        )
        return None
