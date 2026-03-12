"""Image generation service — Nano Banana Pro with auto-fallback.

Extracted from spike_live_api.py (proven working pattern).
Generates brand assets via gemini-3-pro-image-preview, falls back to
gemini-2.5-flash-image on failure.
"""

import logging
import time

from google import genai
from google.genai import types

from config import IMAGE_MODEL, IMAGE_MODEL_FALLBACK

logger = logging.getLogger("brand-agent")

# Aspect ratio mapping for asset types
ASPECT_RATIOS: dict[str, str] = {
    "logo": "1:1",
    "hero_lifestyle": "16:9",
    "instagram_post": "4:5",
    "packaging": "1:1",
}

MODELS_CHAIN = [
    (IMAGE_MODEL, "Nano Banana Pro"),
    (IMAGE_MODEL_FALLBACK, "Nano Banana (fallback)"),
]


class ImageGenerator:
    """Generates brand images with automatic model fallback."""

    def __init__(self, client: genai.Client) -> None:
        self._client = client

    async def generate(
        self,
        session_id: str,
        prompt: str,
        asset_type: str,
        brand_name: str = "Brand",
        style_anchor: str = "",
        aspect_ratio: str | None = None,
    ) -> dict:
        """Generate an image asset. Returns dict with status, image_data, etc."""
        ratio = aspect_ratio or ASPECT_RATIOS.get(asset_type, "1:1")
        full_prompt = self._build_prompt(prompt, asset_type, brand_name, style_anchor, ratio)

        for model_name, label in MODELS_CHAIN:
            t0 = time.perf_counter()
            try:
                logger.info(
                    f"[{session_id}] Phase: GENERATING | Action: image_gen_start | "
                    f"Model: {label} ({model_name}) | Asset: {asset_type}"
                )
                response = await self._client.aio.models.generate_content(
                    model=model_name,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["TEXT", "IMAGE"],
                    ),
                )
                latency = (time.perf_counter() - t0) * 1000

                if not response.candidates or not response.candidates[0].content.parts:
                    logger.warning(
                        f"[{session_id}] Phase: GENERATING | Action: empty_response | "
                        f"Model: {label} | Latency: {latency:.0f}ms"
                    )
                    continue

                image_data, text_desc = self._extract_parts(response)
                if image_data is None:
                    logger.warning(
                        f"[{session_id}] Phase: GENERATING | Action: no_image_in_response | "
                        f"Model: {label} | Latency: {latency:.0f}ms"
                    )
                    continue

                logger.info(
                    f"[{session_id}] Phase: GENERATING | Action: image_generated | "
                    f"Model: {label} | Asset: {asset_type} | Latency: {latency:.0f}ms | "
                    f"Size: {len(image_data.data) / 1024:.0f}KB"
                )

                return {
                    "status": "success",
                    "asset_type": asset_type,
                    "brand_name": brand_name,
                    "model_used": model_name,
                    "latency_ms": round(latency),
                    "image_size_bytes": len(image_data.data),
                    "image_bytes": image_data.data,
                    "mime_type": image_data.mime_type,
                    "description": text_desc or "Image generated successfully.",
                }

            except Exception as e:
                latency = (time.perf_counter() - t0) * 1000
                logger.error(
                    f"[{session_id}] Phase: GENERATING | Action: image_gen_failed | "
                    f"Model: {label} | Latency: {latency:.0f}ms | Error: {e}"
                )
                continue

        return {
            "status": "error",
            "asset_type": asset_type,
            "error": "All image generation models failed. Try again shortly.",
        }

    def _build_prompt(
        self, prompt: str, asset_type: str, brand_name: str,
        style_anchor: str, aspect_ratio: str,
    ) -> str:
        parts = [
            f"Create a professional {asset_type} for the brand '{brand_name}'.",
            prompt,
        ]
        if style_anchor:
            parts.append(f"Visual style: {style_anchor}.")
        parts.append(f"Aspect ratio: {aspect_ratio}.")
        parts.append("High quality, clean design, suitable for commercial use.")
        return " ".join(parts)

    @staticmethod
    def _extract_parts(response: object) -> tuple[object | None, str | None]:
        """Extract image inline_data and text description from response."""
        image_data = None
        text_desc = None
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                image_data = part.inline_data
            elif part.text:
                text_desc = part.text
        return image_data, text_desc
