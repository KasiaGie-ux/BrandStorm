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
    DEBUG_API_KEY_ONLY,
)

logger = logging.getLogger("brand-agent")

# Aspect ratio mapping for asset types
ASPECT_RATIOS: dict[str, str] = {
    "logo": "1:1",
    "hero_lifestyle": "16:9",
    "hero": "16:9",
    "instagram_post": "4:5",
    "instagram": "4:5",
}

MAX_RETRIES_429 = 3
BACKOFF_SECS = [1, 2, 4]  # backoff per retry attempt
REQUEST_TIMEOUT_SEC = 60   # per-call timeout — prevents hanging requests from blocking the chain

# gemini-3-pro-image-preview requires the GLOBAL endpoint (not us-central1)
_global_client: genai.Client | None = None
_dev_client: genai.Client | None = None


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
    return _global_client


def _get_dev_client() -> genai.Client | None:
    """Lazy-init Developer API client (api_key mode). Returns None if no key."""
    global _dev_client
    if not GEMINI_API_KEY:
        return None
    if _dev_client is None:
        _dev_client = genai.Client(api_key=GEMINI_API_KEY)
    return _dev_client


# ---------------------------------------------------------------------------
# Generation chain — ordered priority:
#   Step 1: Developer API (api_key) — primary model (up to MAX_RETRIES_429)
#   Step 2: Vertex AI global — fallback (1 attempt, no retry)
#   Step 3: Vertex AI fallback models (up to MAX_RETRIES_429 each)
# ---------------------------------------------------------------------------


class ImageGenerator:
    """Generates brand images with automatic model fallback."""

    def __init__(self, client: genai.Client) -> None:
        self._client = client  # us-central1 client for fallback models

    # ----- internal: single-model attempt runner -----

    async def _try_model(
        self,
        session_id: str,
        client: genai.Client,
        model_name: str,
        label: str,
        endpoint_tag: str,
        contents,
        asset_type: str,
        brand_name: str,
        max_attempts: int,
    ) -> dict | None:
        """Try *one* model up to `max_attempts` times (retrying only on 429).

        Returns a success dict or ``None`` if this model should be skipped.
        """
        for attempt in range(max_attempts):
            t0 = time.perf_counter()
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            response_modalities=["TEXT", "IMAGE"],
                        ),
                    ),
                    timeout=REQUEST_TIMEOUT_SEC,
                )
                latency = (time.perf_counter() - t0) * 1000

                if not response.candidates or not response.candidates[0].content.parts:
                    logger.warning(
                        f"[{session_id}] Phase: GENERATING | Action: empty_response | "
                        f"Model: {label} | Latency: {latency:.0f}ms"
                    )
                    return None  # empty → next step in chain

                image_data, text_desc = self._extract_parts(response)
                if image_data is None:
                    logger.warning(
                        f"[{session_id}] Phase: GENERATING | Action: no_image_in_response | "
                        f"Model: {label} | Latency: {latency:.0f}ms"
                    )
                    return None

                return {
                    "status": "success",
                    "asset_type": asset_type,
                    "brand_name": brand_name,
                    "model_used": model_name,
                    "latency_ms": round(latency),
                    "image_size_bytes": len(image_data.data),
                    "image_bytes": image_data.data,
                    "mime_type": image_data.mime_type,
                    "description": "Image generation completed successfully.",
                }

            except TimeoutError:
                latency = (time.perf_counter() - t0) * 1000
                logger.error(
                    f"[{session_id}] Phase: GENERATING | Action: image_gen_timeout | "
                    f"Model: {label} | Timeout: {REQUEST_TIMEOUT_SEC}s | "
                    f"Latency: {latency:.0f}ms | Attempt: {attempt + 1}"
                )
                return None  # timeout → skip to next step in chain

            except Exception as e:
                latency = (time.perf_counter() - t0) * 1000
                is_429 = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
                logger.error(
                    f"[{session_id}] Phase: GENERATING | Action: image_gen_failed | "
                    f"Model: {label} | Latency: {latency:.0f}ms | "
                    f"Attempt: {attempt + 1} | 429: {is_429} | Error: {e}"
                )
                if is_429 and attempt < max_attempts - 1:
                    wait = BACKOFF_SECS[attempt] if attempt < len(BACKOFF_SECS) else 4
                    await asyncio.sleep(wait)
                    continue  # retry same model
                return None  # non-429 or retries exhausted → next step

        return None  # all attempts exhausted

    # ----- public entry point -----

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

        Chain order:
          1. Developer API     — primary model, up to MAX_RETRIES_429 retries
          2. Vertex AI global  — fallback, **1 attempt only**
          3. Vertex AI         — fallback models, up to MAX_RETRIES_429 retries each
        """
        ratio = aspect_ratio or ASPECT_RATIOS.get(asset_type, "1:1")
        full_prompt = self._build_prompt(prompt, asset_type, brand_name, style_anchor, ratio)

        # Build contents: reference images + text prompt, or text-only
        if reference_images:
            contents = []
            for img_bytes, img_mime in reference_images:
                contents.append(types.Part.from_bytes(data=img_bytes, mime_type=img_mime))
            contents.append(types.Part.from_text(text=full_prompt))
        else:
            contents = full_prompt

        # ------------------------------------------------------------------
        # Debug mode: skip Vertex AI, go straight to Developer API
        # ------------------------------------------------------------------
        if DEBUG_API_KEY_ONLY and GEMINI_API_KEY:
            dev_client = _get_dev_client()
            if dev_client:
                # Try primary model via API key
                result = await self._try_model(
                    session_id, dev_client,
                    DEVELOPER_API_IMAGE_MODEL, "Nano Banana Pro (debug/api-key)", "developer-api",
                    contents, asset_type, brand_name,
                    max_attempts=1 + MAX_RETRIES_429,
                )
                if result:
                    return result
                # Try fallback models via API key
                for fb_model, fb_label in [
                    (IMAGE_MODEL_FALLBACK,   "Nano Banana (debug/api-key)"),
                    (IMAGE_MODEL_FALLBACK_2, "Flash Image Gen (debug/api-key)"),
                ]:
                    result = await self._try_model(
                        session_id, dev_client,
                        fb_model, fb_label, "developer-api",
                        contents, asset_type, brand_name,
                        max_attempts=1 + MAX_RETRIES_429,
                    )
                    if result:
                        return result

                return {
                    "status": "error",
                    "asset_type": asset_type,
                    "error": "All image generation models failed (debug/api-key mode).",
                }

        # ------------------------------------------------------------------
        # Step 1: Developer API (api_key) — primary, retries
        # ------------------------------------------------------------------
        if GEMINI_API_KEY:
            dev_client = _get_dev_client()
            if dev_client:
                result = await self._try_model(
                    session_id, dev_client,
                    DEVELOPER_API_IMAGE_MODEL, "Nano Banana Pro (GenAI)", "developer-api",
                    contents, asset_type, brand_name,
                    max_attempts=1 + MAX_RETRIES_429,
                )
                if result:
                    return result

        # ------------------------------------------------------------------
        # Step 2: Vertex AI global — fallback, 1 attempt only
        # ------------------------------------------------------------------
        result = await self._try_model(
            session_id, _get_global_client(),
            IMAGE_MODEL, "Nano Banana Pro (Vertex)", "global",
            contents, asset_type, brand_name,
            max_attempts=1,
        )
        if result:
            return result

        # ------------------------------------------------------------------
        # Step 3: Vertex AI fallback models (flash-image, flash-preview)
        # ------------------------------------------------------------------
        fallback_models = [
            (IMAGE_MODEL_FALLBACK,   "Nano Banana (fallback)"),
            (IMAGE_MODEL_FALLBACK_2, "Flash Image Gen (fallback 2)"),
        ]
        for fb_model, fb_label in fallback_models:
            result = await self._try_model(
                session_id, self._client,
                fb_model, fb_label, "us-central1",
                contents, asset_type, brand_name,
                max_attempts=1 + MAX_RETRIES_429,
            )
            if result:
                return result

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
                "A professional brand logo, flat vector style, crisp clean edges. "
                "Minimalist and distinctive design. Geometric typography, precise letter-spacing, "
                "balanced composition. Optional simple abstract symbol integrated with the wordmark. "
                "Solid single-color background. No gradients, no shadows, no 3D effects, no texture, "
                "no clip art, no generic icons. Ultra-refined, studio-grade graphic design. "
                "Centered, square. World-class brand identity quality. The level of refinement seen "
                "in Apple, Google, and Airbnb brand systems. Pixel-perfect precision, intentional "
                "white space, every element essential."
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
