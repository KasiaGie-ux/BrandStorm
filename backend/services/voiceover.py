"""Voiceover generation via Gemini TTS.

Uses gemini-2.5-flash-preview-tts to narrate the brand story.
Picks a voice that matches the brand mood/style anchor.
Returns WAV bytes or None on failure.
"""

import io
import logging
import struct
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

# Gemini TTS returns raw PCM: 24kHz, 16-bit, mono (little-endian).
_PCM_SAMPLE_RATE = 24000
_PCM_BITS_PER_SAMPLE = 16
_PCM_CHANNELS = 1


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


def _wrap_pcm_as_wav(pcm_data: bytes) -> bytes:
    """Wrap raw PCM bytes in a valid WAV header so browsers can play it.

    Gemini TTS returns headerless PCM (24kHz, 16-bit, mono).
    """
    data_size = len(pcm_data)
    byte_rate = _PCM_SAMPLE_RATE * _PCM_CHANNELS * (_PCM_BITS_PER_SAMPLE // 8)
    block_align = _PCM_CHANNELS * (_PCM_BITS_PER_SAMPLE // 8)

    buf = io.BytesIO()
    # RIFF header
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))  # file size - 8
    buf.write(b"WAVE")
    # fmt chunk
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))               # chunk size
    buf.write(struct.pack("<H", 1))                # PCM format
    buf.write(struct.pack("<H", _PCM_CHANNELS))
    buf.write(struct.pack("<I", _PCM_SAMPLE_RATE))
    buf.write(struct.pack("<I", byte_rate))
    buf.write(struct.pack("<H", block_align))
    buf.write(struct.pack("<H", _PCM_BITS_PER_SAMPLE))
    # data chunk
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(pcm_data)

    return buf.getvalue()


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
                    raw_pcm = part.inline_data.data
                    # Gemini TTS returns raw PCM — wrap in WAV header
                    # so browsers can play it natively.
                    wav_bytes = _wrap_pcm_as_wav(raw_pcm)
                    latency = (time.perf_counter() - t0) * 1000
                    logger.info(
                        f"[{session_id}] Phase: GENERATING | Action: voiceover_success | "
                        f"Voice: {voice} | PCM: {len(raw_pcm)} bytes | "
                        f"WAV: {len(wav_bytes)} bytes | Latency: {latency:.0f}ms"
                    )
                    return wav_bytes

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
