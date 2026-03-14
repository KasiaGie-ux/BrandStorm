"""Background pre-generation pipeline.

Fires off palette + image generation as soon as the brand name is known.
Results are invisible to the user until the agent narrates them.
When the agent calls generate_palette or generate_image, the tool_executor
checks here first and returns the pre-generated result instantly.

Pipeline:
  1. brand_name_reveal detected → start()
  2. Generate palette via Gemini text API (fast, ~2s)
  3. Store palette on session → fire off 3 image tasks in parallel
  4. As images complete → store on session + emit to frontend
  5. Agent calls generate_palette → return pre-gen palette
  6. Agent calls generate_image → return pre-gen result (or await if running)
  7. Brand name changes → cancel() everything, restart

All results are stored in session.pregen_tasks as asyncio.Tasks.
"""

import asyncio
import json
import logging
import time

from google import genai
from google.genai import types

import config
from models.session import Session
from services.image_generator import ImageGenerator
from services.storage import StorageService

logger = logging.getLogger("brand-agent")

_ASSET_LABELS: dict[str, str] = {
    "logo": "brand logo",
    "hero_lifestyle": "hero lifestyle photograph",
    "instagram_post": "Instagram post",
}

_DEFAULT_PROMPTS: dict[str, str] = {
    "logo": (
        "A distinctive brand identity mark. Typography-driven with an optional "
        "minimal geometric symbol. The letterforms feel crafted and intentional, "
        "as if shaped by a master typographer."
    ),
    "hero_lifestyle": (
        "An editorial-quality lifestyle photograph. The product is the clear hero, "
        "placed in an environment that tells the brand story. Think magazine cover, "
        "with natural lighting, intentional props, and breathing space."
    ),
    "instagram_post": (
        "A scroll-stopping social media photograph. The product fills the frame "
        "with confidence. Unexpected angle or striking color contrast that makes "
        "someone stop scrolling and double-tap."
    ),
}

_MAX_REF_IMAGE_DIM = 1024


def _resize_image_bytes(
    img_bytes: bytes, mime_type: str, max_dim: int, session_id: str,
) -> tuple[bytes, str]:
    """Resize image to fit within max_dim×max_dim."""
    try:
        import io
        from PIL import Image

        img = Image.open(io.BytesIO(img_bytes))
        w, h = img.size
        if w <= max_dim and h <= max_dim:
            return img_bytes, mime_type

        scale = min(max_dim / w, max_dim / h)
        new_w, new_h = int(w * scale), int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

        buf = io.BytesIO()
        fmt = "JPEG" if "jpeg" in mime_type or "jpg" in mime_type else "PNG"
        img.save(buf, format=fmt, quality=85)
        out_mime = "image/jpeg" if fmt == "JPEG" else "image/png"
        return buf.getvalue(), out_mime
    except Exception:
        return img_bytes, mime_type


class PreGenerator:
    """Background pipeline: brand_name → palette → images."""

    def __init__(
        self,
        image_gen: ImageGenerator,
        storage: StorageService,
    ) -> None:
        self._image_gen = image_gen
        self._storage = storage
        self._text_client: genai.Client | None = None

    def _get_text_client(self) -> genai.Client:
        if self._text_client is None:
            self._text_client = genai.Client(
                vertexai=True,
                project=config.GCP_PROJECT,
                location=config.GCP_LOCATION,
                http_options=types.HttpOptions(api_version="v1beta1"),
            )
        return self._text_client

    # ── Public API ──────────────────────────────────────────────

    def start(self, session: Session) -> None:
        """Start the full pipeline: palette → logo → images.

        Called when brand_name_reveal is detected.
        Results are stored silently — NO events emitted to frontend.
        """
        self.cancel(session)

        brand_name = session.brand_name or "Brand"
        logger.info(
            f"[{session.id}] Action: pregen_pipeline_start | Brand: {brand_name}"
        )

        task = asyncio.create_task(
            self._pipeline(session, brand_name),
            name="pregen-pipeline",
        )
        session.pregen_tasks["_pipeline"] = task

    def cancel(self, session: Session) -> None:
        """Cancel all pending pre-generation tasks."""
        if not session.pregen_tasks:
            return
        for name, task in list(session.pregen_tasks.items()):
            if not task.done():
                task.cancel()
                logger.info(
                    f"[{session.id}] Action: pregen_cancelled | Task: {name}"
                )
        session.pregen_tasks.clear()
        # Clear results from cancelled pre-gen
        session.completed_assets.clear()
        session.asset_urls.clear()
        session.logo_image_bytes = None
        session.palette = None

    async def get_image_result(
        self, session: Session, asset_type: str,
    ) -> dict | None:
        """Get pre-generated image result, awaiting if still running."""
        task = session.pregen_tasks.get(asset_type)
        if task is None:
            return None

        if task.done():
            try:
                return task.result()
            except (asyncio.CancelledError, Exception):
                return None

        logger.info(
            f"[{session.id}] Action: pregen_awaiting | Asset: {asset_type}"
        )
        try:
            return await task
        except (asyncio.CancelledError, Exception):
            return None

    def has_palette(self, session: Session) -> bool:
        """Check if pre-gen palette is available."""
        return session.palette is not None and len(session.pregen_tasks) > 0

    # ── Pipeline ────────────────────────────────────────────────

    async def _pipeline(
        self,
        session: Session,
        brand_name: str,
    ) -> None:
        """Orchestrate: palette → logo → (hero + instagram) in parallel.

        Logo must finish first so hero_lifestyle and instagram_post can
        use the generated logo as a reference image for visual consistency.

        All results are stored silently — NO events emitted to frontend.
        The agent's tool calls (via tool_executor) handle all UI events.
        """
        try:
            # Step 1: Generate palette via text model
            palette = await self._generate_palette(session, brand_name)
            if palette:
                session.palette = palette
                logger.info(
                    f"[{session.id}] Action: pregen_palette_done | "
                    f"Colors: {len(palette)}"
                )

            # Step 2: Generate logo FIRST (others need it as reference)
            logo_task = asyncio.create_task(
                self._generate_one_image(session, "logo", brand_name),
                name="pregen-logo",
            )
            session.pregen_tasks["logo"] = logo_task
            await logo_task  # wait for logo before firing the rest

            logger.info(
                f"[{session.id}] Action: pregen_logo_ready | "
                f"Has logo bytes: {session.logo_image_bytes is not None}"
            )

            # Step 3: Fire hero + instagram in parallel (logo is now available)
            for asset_type in ("hero_lifestyle", "instagram_post"):
                task = asyncio.create_task(
                    self._generate_one_image(session, asset_type, brand_name),
                    name=f"pregen-{asset_type}",
                )
                session.pregen_tasks[asset_type] = task

            remaining_tasks = [
                session.pregen_tasks[at]
                for at in ("hero_lifestyle", "instagram_post")
                if at in session.pregen_tasks
            ]
            await asyncio.gather(*remaining_tasks, return_exceptions=True)

        except asyncio.CancelledError:
            logger.info(f"[{session.id}] Action: pregen_pipeline_cancelled")
            raise
        except Exception as e:
            logger.error(
                f"[{session.id}] Action: pregen_pipeline_error | Error: {e}"
            )

    async def _generate_palette(
        self, session: Session, brand_name: str,
    ) -> list[dict[str, str]] | None:
        """Generate a 5-color palette via Gemini text API."""
        t0 = time.perf_counter()

        prompt_parts = [
            f"You are a brand color expert. Generate a 5-color palette for "
            f"a brand called '{brand_name}'.",
        ]

        # Include product image for context if available
        contents = []
        if session.product_image_bytes:
            resized, mime = _resize_image_bytes(
                session.product_image_bytes, session.product_image_mime,
                512, session.id,
            )
            contents.append(types.Part.from_bytes(data=resized, mime_type=mime))
            prompt_parts.append(
                "The product is shown in the attached image. "
                "Choose colors that complement the product."
            )

        prompt_parts.append(
            "Return ONLY a JSON array of 5 objects, each with keys: "
            '"hex" (e.g. "#1a1a2e"), "role" (primary/secondary/background/accent/neutral), '
            '"name" (creative color name). No other text.'
        )

        contents.append(types.Part.from_text(text=" ".join(prompt_parts)))

        try:
            client = self._get_text_client()
            response = await client.aio.models.generate_content(
                model=config.TEXT_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.8,
                    max_output_tokens=300,
                ),
            )

            text = response.text.strip()
            # Extract JSON from response (might be wrapped in ```json ... ```)
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            colors = json.loads(text)
            if isinstance(colors, list) and len(colors) >= 3:
                validated = []
                for c in colors[:5]:
                    if isinstance(c, dict) and c.get("hex"):
                        validated.append({
                            "hex": c["hex"],
                            "role": c.get("role", "unknown"),
                            "name": c.get("name", ""),
                        })
                latency = (time.perf_counter() - t0) * 1000
                logger.info(
                    f"[{session.id}] Action: pregen_palette_generated | "
                    f"Colors: {len(validated)} | Latency: {latency:.0f}ms"
                )
                return validated

        except Exception as e:
            latency = (time.perf_counter() - t0) * 1000
            logger.warning(
                f"[{session.id}] Action: pregen_palette_failed | "
                f"Error: {e} | Latency: {latency:.0f}ms"
            )

        return None

    async def _generate_one_image(
        self,
        session: Session,
        asset_type: str,
        brand_name: str,
    ) -> dict | None:
        """Generate a single image in the background.

        Results are stored silently — NO events emitted to frontend.
        The agent's tool calls (via tool_executor) handle all UI events.
        """
        t0 = time.perf_counter()

        prompt = _DEFAULT_PROMPTS.get(asset_type, "")

        # Reference images
        ref_images = []
        if asset_type in ("hero_lifestyle", "instagram_post"):
            if session.product_image_bytes:
                resized = _resize_image_bytes(
                    session.product_image_bytes, session.product_image_mime,
                    _MAX_REF_IMAGE_DIM, session.id,
                )
                ref_images.append(resized)
            if session.logo_image_bytes:
                resized = _resize_image_bytes(
                    session.logo_image_bytes, session.logo_image_mime,
                    _MAX_REF_IMAGE_DIM, session.id,
                )
                ref_images.append(resized)

        # Infer style from session or default
        style_anchor = getattr(session, "user_preferences", {}).get(
            "style_anchor", "modern",
        ) if hasattr(session, "user_preferences") else "modern"

        logger.info(
            f"[{session.id}] Action: pregen_image_start | "
            f"Asset: {asset_type} | Brand: {brand_name}"
        )

        result = await self._image_gen.generate(
            session_id=session.id,
            prompt=prompt,
            asset_type=asset_type,
            brand_name=brand_name,
            style_anchor=style_anchor,
            reference_images=ref_images if ref_images else None,
            palette=session.palette,
            has_logo_ref=bool(session.logo_image_bytes),
            tagline=session.tagline,
            brand_values=session.brand_values,
        )

        latency = (time.perf_counter() - t0) * 1000

        if result["status"] == "success":
            image_bytes = result["image_bytes"]
            mime_type = result["mime_type"]

            if not image_bytes or len(image_bytes) < 100:
                return None

            if asset_type == "logo":
                session.logo_image_bytes = image_bytes
                session.logo_image_mime = mime_type

            url = await self._storage.upload_image(
                session_id=session.id,
                asset_type=asset_type,
                image_bytes=image_bytes,
                mime_type=mime_type,
            )

            logger.info(
                f"[{session.id}] Action: pregen_image_done | "
                f"Asset: {asset_type} | Latency: {latency:.0f}ms | URL: {url}"
            )

            result.pop("image_bytes", None)
            result["url"] = url
            return result

        logger.warning(
            f"[{session.id}] Action: pregen_image_failed | "
            f"Asset: {asset_type} | Latency: {latency:.0f}ms"
        )
        return None
