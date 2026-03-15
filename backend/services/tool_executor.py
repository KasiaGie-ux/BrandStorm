"""Canvas-aware tool executor.

Each tool handler: validate args -> execute -> update canvas -> return events.
Returns (FunctionResponse, list[frontend_events]).
"""

import io
import logging
import time

from google.genai import types

from models.canvas import BrandElement, ElementStatus
from models.session import Session
from services.image_generator import ImageGenerator
from services.storage import StorageService
from services.voiceover import _tts_generate

logger = logging.getLogger("brand-agent")

_MAX_REF_IMAGE_DIM = 1024

# Human-readable labels for image elements
_IMAGE_LABELS: dict[str, str] = {
    "logo": "Brand Logo",
    "hero": "Hero Lifestyle",
    "instagram": "Instagram Post",
}


def _resize_image_bytes(
    img_bytes: bytes, mime_type: str, max_dim: int, session_id: str,
) -> tuple[bytes, str]:
    """Resize image to fit within max_dim x max_dim, preserving aspect ratio."""
    try:
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
        logger.info(f"[{session_id}] Resized ref image: {w}x{h} -> {new_w}x{new_h}")
        return buf.getvalue(), out_mime
    except ImportError:
        return img_bytes, mime_type
    except Exception as e:
        logger.warning(f"[{session_id}] Resize failed: {e}")
        return img_bytes, mime_type


class ToolExecutor:
    """Executes tool calls from the Live API agent, updating the canvas."""

    def __init__(
        self,
        image_generator: ImageGenerator,
        storage: StorageService,
    ) -> None:
        self._image_gen = image_generator
        self._storage = storage

    async def execute(
        self,
        session: Session,
        function_call: types.FunctionCall,
    ) -> tuple[types.FunctionResponse, list[dict]]:
        """Execute a function call. Returns (FunctionResponse, frontend_events).

        Never raises — errors are caught and returned as error results.
        """
        name = function_call.name
        try:
            args = dict(function_call.args) if function_call.args else {}
        except Exception:
            args = {}

        t0 = time.perf_counter()
        logger.info(f"[{session.id}] Tool: {name} | Args: {list(args.keys())}")

        try:
            if name == "set_brand_identity":
                result, events = await self._handle_set_identity(session, args)
            elif name == "set_palette":
                result, events = await self._handle_set_palette(session, args)
            elif name == "set_fonts":
                result, events = await self._handle_set_fonts(session, args)
            elif name == "generate_image":
                result, events = await self._handle_generate_image(session, args)
            elif name == "propose_names":
                result, events = await self._handle_propose_names(session, args)
            elif name == "generate_voiceover":
                result, events = await self._handle_voiceover(session, args)
            elif name == "finalize_brand_kit":
                result, events = await self._handle_finalize(session)
            elif name == "delegate_to_specialist":
                result = {
                    "status": "error",
                    "error": "Specialist agents are not yet available. Use your own expertise.",
                }
                events = []
            else:
                result = {"status": "error", "error": f"Unknown tool: {name}"}
                events = []
        except Exception as e:
            logger.error(f"[{session.id}] Tool: {name} | Error: {e}")
            result = {"status": "error", "error": str(e)}
            events = []

        latency = (time.perf_counter() - t0) * 1000
        logger.info(
            f"[{session.id}] Tool: {name} | Latency: {latency:.0f}ms | "
            f"Status: {result.get('status', 'unknown')}"
        )

        fn_response = types.FunctionResponse(name=name, response=result)
        return fn_response, events

    # ------------------------------------------------------------------
    # Tool handlers
    # ------------------------------------------------------------------

    async def _handle_set_identity(
        self, session: Session, args: dict,
    ) -> tuple[dict, list[dict]]:
        """Set any subset of brand identity elements."""
        canvas = session.canvas
        events: list[dict] = []
        fields_updated = []

        if "name" in args and args["name"]:
            old_name = canvas.name.value
            canvas.name.set(args["name"], {"source": "agent"})
            fields_updated.append("name")
            events.append({"type": "brand_name_reveal", "name": args["name"]})
            # Name changed — mark dependent elements stale
            if old_name and old_name != args["name"]:
                canvas.logo.mark_stale()
                canvas.voiceover.mark_stale()
                # Tagline and story may reference the name
                if canvas.tagline.status == ElementStatus.READY:
                    canvas.tagline.mark_stale()

        if "tagline" in args and args["tagline"]:
            canvas.tagline.set(args["tagline"], {"brand_name": canvas.name.value})
            fields_updated.append("tagline")
            events.append({"type": "tagline_reveal", "tagline": args["tagline"]})

        if "story" in args and args["story"]:
            canvas.story.set(args["story"], {"brand_name": canvas.name.value})
            fields_updated.append("story")
            events.append({"type": "brand_story", "story": args["story"]})
            canvas.voiceover.mark_stale()

        if "values" in args and args["values"]:
            canvas.values.set(args["values"])
            fields_updated.append("values")
            events.append({"type": "brand_values", "values": args["values"]})

        if "tone_do" in args or "tone_dont" in args:
            tone = {
                "do": args.get("tone_do", []),
                "dont": args.get("tone_dont", []),
            }
            canvas.tone.set(tone)
            fields_updated.append("tone")
            events.append({"type": "tone_of_voice", "tone_of_voice": tone})

        events.append({"type": "canvas_update", "canvas": canvas.snapshot()})

        logger.info(f"[{session.id}] set_brand_identity | Updated: {fields_updated}")
        return {"status": "success", "fields_updated": fields_updated}, events

    async def _handle_set_palette(
        self, session: Session, args: dict,
    ) -> tuple[dict, list[dict]]:
        """Set 5-color brand palette."""
        colors_raw = args.get("colors", [])
        mood = args.get("mood", "")

        colors = []
        for c in colors_raw:
            if isinstance(c, dict) and c.get("hex"):
                colors.append({
                    "hex": c["hex"],
                    "role": c.get("role", "unknown"),
                    "name": c.get("name", ""),
                })

        if not colors:
            return {"status": "error", "error": "No valid colors provided"}, []

        canvas = session.canvas
        old_palette = canvas.palette.value
        canvas.palette.set(colors, {"mood": mood})

        # If palette changed and images exist, mark them stale
        if old_palette and old_palette != colors:
            for img_name in ("logo", "hero", "instagram"):
                el = canvas.element_by_name(img_name)
                if el and el.status == ElementStatus.READY:
                    el.mark_stale()

        events = [
            {"type": "palette_reveal", "mood": mood, "colors": colors},
            {"type": "canvas_update", "canvas": canvas.snapshot()},
        ]
        logger.info(f"[{session.id}] set_palette | Colors: {len(colors)}")
        return {"status": "success", "colors_count": len(colors)}, events

    async def _handle_set_fonts(
        self, session: Session, args: dict,
    ) -> tuple[dict, list[dict]]:
        """Set font pairing."""
        heading_font = args.get("heading_font", "")
        body_font = args.get("body_font", "")
        if not heading_font or not body_font:
            return {"status": "error", "error": "Both heading_font and body_font required"}, []

        font_data = {
            "heading": {
                "family": heading_font,
                "style": args.get("heading_style", ""),
            },
            "body": {
                "family": body_font,
                "style": args.get("body_style", ""),
            },
        }
        session.canvas.fonts.set(font_data)

        events = [
            {
                "type": "font_suggestion",
                "heading": {"family": heading_font, "google_fonts": True, "style": args.get("heading_style", "")},
                "body": {"family": body_font, "google_fonts": True, "style": args.get("body_style", "")},
            },
            {"type": "canvas_update", "canvas": session.canvas.snapshot()},
        ]
        logger.info(f"[{session.id}] set_fonts | Heading: {heading_font} | Body: {body_font}")
        return {"status": "success"}, events

    async def _handle_propose_names(
        self, session: Session, args: dict,
    ) -> tuple[dict, list[dict]]:
        """Present 3 name proposals to user."""
        names = args.get("names", [])
        if not names:
            return {"status": "error", "error": "No names provided"}, []

        validated = []
        for i, n in enumerate(names[:3]):
            if isinstance(n, dict) and n.get("name"):
                validated.append({
                    "id": i + 1,
                    "name": n["name"],
                    "rationale": n.get("rationale", ""),
                    **({"recommended": True} if n.get("recommended") else {}),
                })

        event = {
            "type": "name_proposals",
            "names": validated,
            "auto_select_seconds": 8,
        }
        logger.info(f"[{session.id}] propose_names | Names: {[n['name'] for n in validated]}")
        return {"status": "success", "names": [n["name"] for n in validated]}, [
            event,
            {"type": "canvas_update", "canvas": session.canvas.snapshot()},
        ]

    async def _handle_generate_image(
        self, session: Session, args: dict,
    ) -> tuple[dict, list[dict]]:
        """Generate a visual asset via Nano Banana Pro."""
        element_name = args.get("element", "logo")
        prompt = args.get("prompt", "")
        style_anchor = args.get("style_anchor", session.canvas.style_anchor or "modern")

        element = session.canvas.element_by_name(element_name)
        if not element:
            return {"status": "error", "error": f"Unknown element: {element_name}"}, []

        element.mark_generating()
        brand_name = session.canvas.name.value or "Brand"

        # Default prompt if empty
        if not prompt.strip():
            label = _IMAGE_LABELS.get(element_name, element_name)
            prompt = (
                f"Create a professional {label} for '{brand_name}'. "
                f"Style: {style_anchor}. High quality, commercially viable."
            )

        # Build reference images for chaining
        ref_images = []
        if element_name in ("hero", "instagram"):
            if session.product_image_bytes:
                ref_images.append(_resize_image_bytes(
                    session.product_image_bytes, session.product_image_mime,
                    _MAX_REF_IMAGE_DIM, session.id,
                ))
            if session.logo_image_bytes:
                ref_images.append(_resize_image_bytes(
                    session.logo_image_bytes, session.logo_image_mime,
                    _MAX_REF_IMAGE_DIM, session.id,
                ))

        # Enrich prompt with product/logo reference
        enriched_prompt = prompt
        if element_name in ("hero", "instagram") and ref_images:
            enriched_prompt += (
                " IMPORTANT: The generated image MUST prominently feature the exact product "
                "from the reference photo. The brand logo must be clearly visible."
            )

        # Append palette colors if available
        palette = session.canvas.palette.value
        if palette and element_name in ("hero", "instagram"):
            hex_list = ", ".join(c.get("hex", "") for c in palette if c.get("hex"))
            if hex_list:
                enriched_prompt += f" Use these brand colors: {hex_list}."

        # Generation context for staleness tracking
        gen_context = {
            "brand_name": brand_name,
            "palette": [c["hex"] for c in (palette or [])],
            "style_anchor": style_anchor,
            "prompt_hash": hash(enriched_prompt) % 10**8,
        }

        logger.info(
            f"[{session.id}] generate_image | Element: {element_name} | "
            f"Prompt: {len(enriched_prompt)} chars | Refs: {len(ref_images)}"
        )

        result = await self._image_gen.generate(
            session_id=session.id,
            prompt=enriched_prompt,
            asset_type=element_name,
            brand_name=brand_name,
            style_anchor=style_anchor,
            reference_images=ref_images if ref_images else None,
        )

        events: list[dict] = []
        if result["status"] == "success":
            image_bytes = result["image_bytes"]
            mime_type = result["mime_type"]

            if not image_bytes or len(image_bytes) < 100:
                element.clear()
                return {"status": "error", "error": "Image generation returned empty data"}, [
                    {"type": "canvas_update", "canvas": session.canvas.snapshot()},
                ]

            # Store logo for chaining
            if element_name == "logo":
                session.logo_image_bytes = image_bytes
                session.logo_image_mime = mime_type

            url = await self._storage.upload_image(
                session_id=session.id,
                asset_type=element_name,
                image_bytes=image_bytes,
                mime_type=mime_type,
            )

            # If inputs changed while generating, discard the stale result
            if element.status == ElementStatus.STALE:
                element.clear()
                logger.info(f"[{session.id}] Discarding stale {element_name} generation result")
                events.append({"type": "canvas_update", "canvas": session.canvas.snapshot()})
                return {"status": "stale", "reason": "Inputs changed during generation"}, events

            element.set(url, gen_context)
            result.pop("image_bytes", None)
            result["url"] = url

            events.append({
                "type": "image_generated",
                "element": element_name,
                "asset_type": element_name,  # backward compat with frontend
                "url": url,
                "label": _IMAGE_LABELS.get(element_name, element_name),
                "description": result.get("description", ""),
                "brand_name": brand_name,
                "progress": session.canvas.progress,
            })
        else:
            element.clear()

        events.append({"type": "canvas_update", "canvas": session.canvas.snapshot()})
        return result, events

    async def _handle_voiceover(
        self, session: Session, args: dict,
    ) -> tuple[dict, list[dict]]:
        """Generate dual-voice brand story narration."""
        handoff_text = args.get("handoff_text", "")
        greeting_text = args.get("greeting_text", "")
        narration_text = args.get("narration_text", session.canvas.story.value or "")
        mood = args.get("mood", "luxury")

        if not narration_text:
            return {"status": "skipped", "reason": "No narration text"}, []

        from config import NARRATOR_VOICE

        events: list[dict] = []

        # Emit handoff text event (Charon already spoke it via Live API audio)
        if handoff_text:
            events.append({
                "type": "voiceover_handoff",
                "audio_url": None,
                "text": handoff_text,
            })

        # Generate greeting (Anna's voice)
        if greeting_text:
            greeting_wav = await _tts_generate(
                session_id=session.id,
                text=greeting_text,
                voice=NARRATOR_VOICE,
                label="voiceover_greeting",
            )
            if greeting_wav:
                greeting_url = await self._storage.upload_image(
                    session_id=session.id,
                    asset_type="voiceover_greeting",
                    image_bytes=greeting_wav,
                    mime_type="audio/wav",
                )
                events.append({
                    "type": "voiceover_greeting",
                    "audio_url": greeting_url,
                    "text": greeting_text,
                })

        # Generate story narration (Anna's voice)
        story_wav = await _tts_generate(
            session_id=session.id,
            text=narration_text,
            voice=NARRATOR_VOICE,
            label="voiceover_story",
        )
        if not story_wav:
            return {"status": "skipped", "reason": "TTS generation failed"}, events

        story_url = await self._storage.upload_image(
            session_id=session.id,
            asset_type="voiceover_story",
            image_bytes=story_wav,
            mime_type="audio/wav",
        )

        session.canvas.voiceover.set(story_url, {"story": narration_text[:100], "mood": mood})

        events.append({
            "type": "voiceover_story",
            "audio_url": story_url,
        })
        events.append({"type": "canvas_update", "canvas": session.canvas.snapshot()})

        logger.info(f"[{session.id}] generate_voiceover | Story URL: {story_url}")
        return {"status": "success", "audio_url": story_url}, events

    async def _handle_finalize(
        self, session: Session,
    ) -> tuple[dict, list[dict]]:
        """Package all completed assets into a ZIP."""
        canvas = session.canvas
        brand_name = canvas.name.value or "Brand"

        asset_urls = canvas.asset_urls
        if not asset_urls:
            logger.warning(f"[{session.id}] finalize_brand_kit | No assets to package")

        try:
            zip_url = await self._storage.create_zip(
                session_id=session.id,
                asset_urls=asset_urls,
            )
        except Exception as e:
            logger.error(f"[{session.id}] finalize_brand_kit | ZIP failed: {e}")
            zip_url = None

        # Build images array for frontend
        images = []
        for elem_name in ("logo", "hero", "instagram"):
            el = canvas.element_by_name(elem_name)
            if el and el.status == ElementStatus.READY and el.value:
                images.append({
                    "url": el.value,
                    "asset_type": elem_name,
                    "label": _IMAGE_LABELS.get(elem_name, elem_name),
                })

        event = {
            "type": "generation_complete",
            "brand_name": brand_name,
            "tagline": canvas.tagline.value or "",
            "brand_story": canvas.story.value or "",
            "brand_values": canvas.values.value or [],
            "palette": canvas.palette.value or [],
            "font_suggestion": canvas.fonts.value,
            "images": images,
            "tone_of_voice": canvas.tone.value or {},
            "audio_url": canvas.voiceover.value,
            "asset_urls": asset_urls,
            "zip_url": zip_url,
            "progress": 1.0,
        }

        logger.info(
            f"[{session.id}] finalize_brand_kit | Assets: {len(images)} | ZIP: {bool(zip_url)}"
        )
        return {"status": "success", "zip_url": zip_url}, [event]
