"""Image generation service — Nano Banana Pro with auto-fallback.

Extracted from spike_live_api.py (proven working pattern).
Generates brand assets via gemini-3-pro-image-preview (global endpoint),
falls back to gemini-2.5-flash-image, then gemini-2.0-flash-preview-image-generation.
Retries 429 RESOURCE_EXHAUSTED with exponential backoff before moving
to the next model.
"""

import asyncio
import logging
import time

from google import genai
from google.genai import types

import config
from config import (
    IMAGE_MODEL, IMAGE_MODEL_FALLBACK, IMAGE_MODEL_FALLBACK_2,
    GEMINI_API_KEY, USE_DEVELOPER_API_FALLBACK, DEVELOPER_API_IMAGE_MODEL,
)

logger = logging.getLogger("brand-agent")

# Aspect ratio mapping for asset types
ASPECT_RATIOS: dict[str, str] = {
    "logo": "1:1",
    "hero_lifestyle": "16:9",
    "instagram_post": "4:5",
    "packaging": "1:1",
}

MAX_RETRIES_429 = 3
BACKOFF_SECS = [1, 2, 4]  # backoff per retry attempt

# gemini-3-pro-image-preview requires the GLOBAL endpoint (not us-central1)
_global_client: genai.Client | None = None


def _get_global_client() -> genai.Client:
    """Lazy-init a separate client pointing at location=global."""
    global _global_client
    if _global_client is None:
        _global_client = genai.Client(
            vertexai=True,
            project=config.GCP_PROJECT,
            location="global",
            http_options=types.HttpOptions(api_version="v1beta1"),
        )
        logger.info("ImageGenerator: created global-endpoint client for preview models")
    return _global_client


# Models chain: (model_name, label, use_global_client)
MODELS_CHAIN: list[tuple[str, str, bool]] = [
    (IMAGE_MODEL, "Nano Banana Pro", True),           # global endpoint
    (IMAGE_MODEL_FALLBACK, "Nano Banana (fallback)", False),  # us-central1
    (IMAGE_MODEL_FALLBACK_2, "Flash Image Gen (fallback 2)", False),  # us-central1
]


class ImageGenerator:
    """Generates brand images with automatic model fallback."""

    def __init__(self, client: genai.Client) -> None:
        self._client = client  # us-central1 client for fallback models

    async def generate(
        self,
        session_id: str,
        prompt: str,
        asset_type: str,
        brand_name: str = "Brand",
        style_anchor: str = "",
        aspect_ratio: str | None = None,
        reference_images: list[tuple[bytes, str]] | None = None,
    ) -> dict:
        """Generate an image asset. Returns dict with status, image_data, etc.

        reference_images: list of (bytes, mime_type) tuples — product photo,
        logo, etc. to include as visual context for the image model.
        """
        ratio = aspect_ratio or ASPECT_RATIOS.get(asset_type, "1:1")
        full_prompt = self._build_prompt(prompt, asset_type, brand_name, style_anchor, ratio)

        # Build contents: reference images + text prompt, or text-only
        if reference_images:
            contents = []
            for img_bytes, img_mime in reference_images:
                contents.append(types.Part.from_bytes(data=img_bytes, mime_type=img_mime))
            contents.append(types.Part.from_text(text=full_prompt))
            logger.info(
                f"[{session_id}] Phase: GENERATING | Action: image_gen_with_refs | "
                f"Asset: {asset_type} | Ref images: {len(reference_images)} | "
                f"Sizes: {[len(r[0])//1024 for r in reference_images]}KB"
            )
        else:
            contents = full_prompt

        for model_name, label, use_global in MODELS_CHAIN:
            client = _get_global_client() if use_global else self._client
            for attempt in range(1 + MAX_RETRIES_429):
                t0 = time.perf_counter()
                try:
                    logger.info(
                        f"[{session_id}] Phase: GENERATING | Action: image_gen_start | "
                        f"Model: {label} ({model_name}) | Asset: {asset_type} | "
                        f"Attempt: {attempt + 1}/{1 + MAX_RETRIES_429} | "
                        f"Endpoint: {'global' if use_global else 'us-central1'}"
                    )
                    response = await client.aio.models.generate_content(
                        model=model_name,
                        contents=contents,
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
                        break  # empty response → skip to next model

                    image_data, text_desc = self._extract_parts(response)
                    if image_data is None:
                        logger.warning(
                            f"[{session_id}] Phase: GENERATING | Action: no_image_in_response | "
                            f"Model: {label} | Latency: {latency:.0f}ms"
                        )
                        break  # no image part → skip to next model

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
                    is_429 = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
                    logger.error(
                        f"[{session_id}] Phase: GENERATING | Action: image_gen_failed | "
                        f"Model: {label} | Latency: {latency:.0f}ms | "
                        f"Attempt: {attempt + 1} | 429: {is_429} | Error: {e}"
                    )
                    if is_429 and attempt < MAX_RETRIES_429:
                        wait = BACKOFF_SECS[attempt] if attempt < len(BACKOFF_SECS) else 4
                        logger.info(
                            f"[{session_id}] Phase: GENERATING | Action: 429_backoff | "
                            f"Model: {label} | Wait: {wait}s"
                        )
                        await asyncio.sleep(wait)
                        continue  # retry same model
                    break  # non-429 or retries exhausted → next model

        # --- Developer API fallback (API key mode) ---
        if USE_DEVELOPER_API_FALLBACK and GEMINI_API_KEY:
            try:
                logger.info(
                    f"[{session_id}] Phase: GENERATING | Action: developer_api_fallback | "
                    f"Model: {DEVELOPER_API_IMAGE_MODEL} | Asset: {asset_type}"
                )
                dev_client = genai.Client(api_key=GEMINI_API_KEY)
                t0 = time.perf_counter()
                response = await dev_client.aio.models.generate_content(
                    model=DEVELOPER_API_IMAGE_MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_modalities=["TEXT", "IMAGE"],
                    ),
                )
                latency = (time.perf_counter() - t0) * 1000

                if response.candidates and response.candidates[0].content.parts:
                    image_data, text_desc = self._extract_parts(response)
                    if image_data:
                        logger.info(
                            f"[{session_id}] Phase: GENERATING | Action: developer_api_success | "
                            f"Model: {DEVELOPER_API_IMAGE_MODEL} | Asset: {asset_type} | "
                            f"Latency: {latency:.0f}ms | Size: {len(image_data.data) / 1024:.0f}KB"
                        )
                        return {
                            "status": "success",
                            "asset_type": asset_type,
                            "brand_name": brand_name,
                            "model_used": DEVELOPER_API_IMAGE_MODEL,
                            "latency_ms": round(latency),
                            "image_size_bytes": len(image_data.data),
                            "image_bytes": image_data.data,
                            "mime_type": image_data.mime_type,
                            "description": text_desc or "Image generated successfully.",
                        }
            except Exception as e:
                logger.error(
                    f"[{session_id}] Phase: GENERATING | Action: developer_api_failed | "
                    f"Model: {DEVELOPER_API_IMAGE_MODEL} | Error: {e}"
                )

        return {
            "status": "error",
            "asset_type": asset_type,
            "error": "All image generation models failed. Try again shortly.",
        }

    def _build_prompt(
        self, prompt: str, asset_type: str, brand_name: str,
        style_anchor: str, aspect_ratio: str,
    ) -> str:
        parts: list[str] = []

        # Logo-specific quality preamble
        if asset_type == "logo":
            parts.append(
                "Professional brand identity design. Clean, modern, memorable. "
                "NOT clip art, NOT generic icons. Think Pentagram or Sagmeister & Walsh "
                "quality. Minimalist but distinctive. The logo must work at small sizes. "
                "Typography-focused with optional symbol. Use the brand's color palette."
            )

        parts.append(f"Create a professional {asset_type} for the brand '{brand_name}'.")
        parts.append(prompt)

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
