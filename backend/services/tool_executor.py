"""Executes function calls from Live API agent.

Dispatches to image_generator, palette generation, finalization.
Returns FunctionResponse to send back to the Live API session.
Validates tool args with sensible defaults — never crashes on malformed input.
"""

import logging
import time

from google.genai import types

from models.session import Session
from services.image_generator import ImageGenerator
from services.storage import StorageService
from services.voiceover import generate_voiceover

logger = logging.getLogger("brand-agent")

# Human-readable labels for asset types (used in default prompts)
_ASSET_LABELS: dict[str, str] = {
    "logo": "brand logo",
    "hero_lifestyle": "hero lifestyle photograph",
    "instagram_post": "Instagram post",
    "packaging": "product packaging concept",
}


class ToolExecutor:
    """Dispatches and executes tool calls from the Live API agent."""

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
    ) -> tuple[types.FunctionResponse, dict | None]:
        """Execute a function call. Returns (FunctionResponse, event_to_send).

        event_to_send is a dict to forward to the frontend WebSocket, or None.
        Never raises — all errors are caught and returned as error results.
        """
        name = function_call.name
        try:
            args = dict(function_call.args) if function_call.args else {}
        except Exception:
            args = {}
            logger.warning(
                f"[{session.id}] Phase: GENERATING | Action: malformed_tool_args | "
                f"Tool: {name} | Using empty args"
            )
        t0 = time.perf_counter()

        logger.info(
            f"[{session.id}] Phase: GENERATING | Action: tool_call_received | "
            f"Tool: {name} | Args: {args}"
        )

        try:
            if name == "analyze_product":
                result, event = await self._handle_analyze(session, args)
            elif name == "generate_image":
                result, event = await self._handle_generate_image(session, args)
            elif name == "generate_palette":
                result, event = await self._handle_generate_palette(session, args)
            elif name == "generate_voiceover":
                result, event = await self._handle_voiceover(session, args)
            elif name == "finalize_brand_kit":
                result, event = await self._handle_finalize(session, args)
            else:
                result = {"status": "error", "error": f"Unknown tool: {name}"}
                event = None
        except Exception as e:
            logger.error(
                f"[{session.id}] Phase: GENERATING | Action: tool_exec_failed | "
                f"Tool: {name} | Error: {e}"
            )
            result = {"status": "error", "error": str(e)}
            event = None

        latency = (time.perf_counter() - t0) * 1000
        logger.info(
            f"[{session.id}] Phase: {session.phase.value} | Action: tool_exec_done | "
            f"Tool: {name} | Latency: {latency:.0f}ms | "
            f"Status: {result.get('status', 'unknown')}"
        )

        fn_response = types.FunctionResponse(name=name, response=result)
        return fn_response, event

    async def _handle_analyze(
        self, session: Session, args: dict,
    ) -> tuple[dict, dict | None]:
        """analyze_product — the agent analyzes the image itself via vision.

        We just acknowledge. The real analysis happens in the agent's response.
        """
        result = {
            "status": "success",
            "analysis_complete": True,
            "focus_areas": args.get("focus_areas", [
                "material", "color", "shape", "finish", "category", "positioning",
            ]),
            "next_step": "Propose 2-3 creative brand directions based on your visual analysis, then proceed to generate assets.",
        }
        return result, None

    async def _handle_generate_image(
        self, session: Session, args: dict,
    ) -> tuple[dict, dict | None]:
        """generate_image — generate brand asset via Nano Banana Pro.

        Validates args and fills sensible defaults from session context.
        """
        # --- Validate & default: asset_type ---
        asset_type = args.get("asset_type", "logo")
        if asset_type not in _ASSET_LABELS:
            logger.warning(
                f"[{session.id}] Phase: GENERATING | Action: invalid_asset_type | "
                f"Got: {asset_type} | Defaulting to logo"
            )
            asset_type = "logo"

        # --- Validate & default: prompt ---
        prompt = args.get("prompt", "")
        if not prompt or not prompt.strip():
            # Build a default prompt from session context
            brand = session.brand_name or "Brand"
            label = _ASSET_LABELS.get(asset_type, asset_type)
            style = args.get("style_anchor", "modern luxury")
            prompt = (
                f"Create a professional {label} for '{brand}'. "
                f"Style: {style}. High quality, commercially viable."
            )
            logger.warning(
                f"[{session.id}] Phase: GENERATING | Action: empty_prompt_defaulted | "
                f"Asset: {asset_type} | Default prompt: {prompt[:80]}"
            )

        brand_name = args.get("brand_name", session.brand_name or "Brand")
        style_anchor = args.get("style_anchor", "")
        aspect_ratio = args.get("aspect_ratio")

        # Update brand name if agent provides one
        if args.get("brand_name") and not session.brand_name:
            session.brand_name = args["brand_name"]

        # Build reference images for chaining:
        # - logo: text-only (no product photo in the logo)
        # - hero_lifestyle / instagram_post / packaging: product + logo as references
        ref_images = []
        if asset_type in ("hero_lifestyle", "instagram_post", "packaging"):
            if session.product_image_bytes:
                ref_images.append((session.product_image_bytes, session.product_image_mime))
            if session.logo_image_bytes:
                ref_images.append((session.logo_image_bytes, session.logo_image_mime))

        # Enrich prompt: product + logo must be visible in the output
        enriched_prompt = prompt
        if asset_type in ("hero_lifestyle", "instagram_post", "packaging") and ref_images:
            enriched_prompt += (
                " IMPORTANT: The generated image MUST prominently feature the exact product "
                "from the reference photo. The brand logo must be clearly visible and "
                "naturally integrated into the composition."
            )

        # Append palette hex values if available
        if session.palette and asset_type in ("hero_lifestyle", "instagram_post", "packaging"):
            hex_list = ", ".join(
                c.get("hex", "") for c in session.palette if c.get("hex")
            )
            if hex_list:
                enriched_prompt += f" Use these brand colors: {hex_list}."

        logger.info(
            f"[{session.id}] Phase: GENERATING | Action: image_gen_starting | "
            f"Asset: {asset_type} | Brand: {brand_name} | Style: {style_anchor} | "
            f"Prompt length: {len(enriched_prompt)} | "
            f"Ref images: {len(ref_images)} | "
            f"Palette: {'yes' if session.palette else 'no'}"
        )

        result = await self._image_gen.generate(
            session_id=session.id,
            prompt=enriched_prompt,
            asset_type=asset_type,
            brand_name=brand_name,
            style_anchor=style_anchor,
            aspect_ratio=aspect_ratio,
            reference_images=ref_images if ref_images else None,
        )

        event = None
        if result["status"] == "success":
            image_bytes = result["image_bytes"]
            mime_type_img = result["mime_type"]

            # Validate: non-empty image data
            if not image_bytes or len(image_bytes) < 100:
                logger.error(
                    f"[{session.id}] Phase: GENERATING | Action: empty_image_data | "
                    f"Asset: {asset_type} | Size: {len(image_bytes) if image_bytes else 0}"
                )
                result = {
                    "status": "error",
                    "asset_type": asset_type,
                    "error": "Image generation returned empty data. Let me try again.",
                }
                event = {
                    "type": "error",
                    "message": f"Image generation for {_ASSET_LABELS.get(asset_type, asset_type)} returned empty. Retrying...",
                }
                return result, event

            logger.info(
                f"[{session.id}] Phase: GENERATING | Action: image_gen_success | "
                f"Asset: {asset_type} | Size: {len(image_bytes)} bytes | "
                f"MIME: {mime_type_img} | Model: {result.get('model_used')}"
            )

            # Store logo bytes for chaining to subsequent generations
            if asset_type == "logo":
                session.logo_image_bytes = image_bytes
                session.logo_image_mime = mime_type_img

            # Upload to storage
            url = await self._storage.upload_image(
                session_id=session.id,
                asset_type=asset_type,
                image_bytes=image_bytes,
                mime_type=mime_type_img,
            )
            session.mark_asset_complete(asset_type, url)
            logger.info(
                f"[{session.id}] Phase: GENERATING | Action: asset_stored | "
                f"Asset: {asset_type} | URL: {url}"
            )

            # Remove raw bytes before sending to Live API (too large)
            result.pop("image_bytes", None)
            result["url"] = url

            event = {
                "type": "image_generated",
                "asset_type": asset_type,
                "url": url,
                "label": _ASSET_LABELS.get(asset_type, asset_type).title(),
                "description": result.get("description", ""),
                "brand_name": brand_name,
                "progress": session.progress,
            }
            logger.info(
                f"[{session.id}] Phase: GENERATING | Action: image_generated_event | "
                f"Asset: {asset_type} | URL: {url} | Progress: {session.progress}"
            )
        else:
            logger.error(
                f"[{session.id}] Phase: GENERATING | Action: image_gen_failed | "
                f"Asset: {asset_type} | Error: {result.get('error', 'unknown')}"
            )

        return result, event

    async def _handle_generate_palette(
        self, session: Session, args: dict,
    ) -> tuple[dict, dict | None]:
        """generate_palette — agent decides colors, we store them.

        Requires at minimum mood OR style_anchor. Colors array is required
        but we default to empty if missing.
        """
        mood = args.get("mood", "")
        style_anchor = args.get("style_anchor", "")

        # Validate: at least one of mood/style_anchor
        if not mood and not style_anchor:
            logger.warning(
                f"[{session.id}] Phase: GENERATING | Action: palette_missing_context | "
                f"Defaulting mood to 'sophisticated'"
            )
            mood = "sophisticated"

        product_colors = args.get("product_colors", [])

        # Store palette colors on session for chaining to image generation
        colors = args.get("colors", [])
        if colors:
            # Validate each color has at least hex
            validated = []
            for c in colors:
                if isinstance(c, dict) and c.get("hex"):
                    validated.append({
                        "hex": c["hex"],
                        "role": c.get("role", "unknown"),
                        "name": c.get("name", ""),
                    })
            colors = validated
            session.palette = colors
            logger.info(
                f"[{session.id}] Phase: GENERATING | Action: palette_stored | "
                f"Colors: {len(colors)}"
            )

        result = {
            "status": "success",
            "message": (
                "Palette acknowledged. Now output your font pairing using "
                "[FONT_SUGGESTION] tags (heading and body fonts with rationale). "
                "After that, proceed to generate the logo."
            ),
            "mood": mood,
            "style_anchor": style_anchor,
            "product_colors": product_colors,
        }
        # Emit palette_reveal (structured event for frontend rendering)
        event = {"type": "palette_reveal", "mood": mood, "colors": colors}
        return result, event

    async def _handle_voiceover(
        self, session: Session, args: dict,
    ) -> tuple[dict, dict | None]:
        """generate_voiceover — narrate brand story via Gemini TTS."""
        text = args.get("text", session.brand_story or "")
        mood = args.get("mood", "luxury")

        if not text:
            logger.warning(
                f"[{session.id}] Phase: GENERATING | Action: voiceover_no_text | "
                f"No brand story text available for voiceover"
            )
            return {"status": "skipped", "reason": "No text provided"}, None

        audio_bytes = await generate_voiceover(
            session_id=session.id,
            text=text,
            mood=mood,
        )

        if not audio_bytes:
            return {"status": "skipped", "reason": "TTS generation failed"}, None

        # Upload audio to storage
        url = await self._storage.upload_image(
            session_id=session.id,
            asset_type="voiceover",
            image_bytes=audio_bytes,
            mime_type="audio/wav",
        )
        session.audio_url = url

        logger.info(
            f"[{session.id}] Phase: GENERATING | Action: voiceover_stored | "
            f"URL: {url} | Size: {len(audio_bytes)} bytes"
        )

        result = {"status": "success", "audio_url": url}
        event = {
            "type": "voiceover_generated",
            "audio_url": url,
        }
        return result, event

    async def _handle_finalize(
        self, session: Session, args: dict,
    ) -> tuple[dict, dict | None]:
        """finalize_brand_kit — package all assets into ZIP.

        Requires at minimum brand_name. Other fields default gracefully.
        """
        # Default brand_name from session if not in args
        brand_name = args.get("brand_name", session.brand_name or "Brand")
        if not session.brand_name:
            session.brand_name = brand_name
        elif args.get("brand_name"):
            session.brand_name = args["brand_name"]

        # Store finalize args on session for full payload
        tagline = args.get("tagline", session.tagline or "")
        brand_story = args.get("brand_story", session.brand_story or "")
        brand_values = args.get("brand_values", session.brand_values or [])
        tone_of_voice = args.get("tone_of_voice", session.tone_of_voice or {})

        session.tagline = tagline
        session.brand_story = brand_story
        session.brand_values = brand_values
        session.tone_of_voice = tone_of_voice

        if not session.completed_assets:
            logger.warning(
                f"[{session.id}] Phase: GENERATING | Action: finalize_no_assets | "
                f"Completing with 0 assets"
            )

        zip_url = await self._storage.create_zip(
            session_id=session.id,
            asset_urls=session.asset_urls,
        )
        session.zip_url = zip_url

        # Build images array from asset_urls for frontend
        images = []
        for asset_type, url in session.asset_urls.items():
            images.append({
                "url": url,
                "asset_type": asset_type,
                "label": _ASSET_LABELS.get(asset_type, asset_type).title(),
                "description": "",
            })

        result = {
            "status": "success",
            "brand_name": session.brand_name,
            "assets_count": len(session.completed_assets),
            "zip_url": zip_url,
        }
        event = {
            "type": "generation_complete",
            "brand_name": session.brand_name,
            "tagline": session.tagline,
            "brand_story": session.brand_story,
            "brand_values": session.brand_values,
            "palette": session.palette or [],
            "font_suggestion": session.font_suggestion,
            "images": images,
            "tone_of_voice": session.tone_of_voice,
            "audio_url": session.audio_url,
            "asset_urls": session.asset_urls,
            "zip_url": zip_url,
            "progress": 1.0,
        }
        return result, event
