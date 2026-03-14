"""Executes function calls from Live API agent.

Dispatches to image_generator, palette generation, finalization.
Returns FunctionResponse to send back to the Live API session.
Validates tool args with sensible defaults — never crashes on malformed input.
"""

import io
import logging
import time

from google.genai import types

from models.session import Session
from services.image_generator import ImageGenerator
from services.pregen import PreGenerator
from services.storage import StorageService
from services.voiceover import _tts_generate

logger = logging.getLogger("brand-agent")

# Max dimension for reference images sent to the image model.
# Large images (e.g. 2871×2000) cause internal tensor errors in Gemini.
_MAX_REF_IMAGE_DIM = 1024

# Human-readable labels for asset types (used in default prompts)
_ASSET_LABELS: dict[str, str] = {
    "logo": "brand logo",
    "hero_lifestyle": "hero lifestyle photograph",
    "instagram_post": "Instagram post",
    "packaging": "product packaging concept",
}


def _resize_image_bytes(
    img_bytes: bytes, mime_type: str, max_dim: int, session_id: str,
) -> tuple[bytes, str]:
    """Resize image to fit within max_dim×max_dim, preserving aspect ratio.

    Returns (resized_bytes, mime_type). Falls back to original if resize fails.
    """
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(img_bytes))
        w, h = img.size
        if w <= max_dim and h <= max_dim:
            return img_bytes, mime_type  # already small enough

        # Scale to fit within max_dim
        scale = min(max_dim / w, max_dim / h)
        new_w, new_h = int(w * scale), int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

        buf = io.BytesIO()
        fmt = "JPEG" if "jpeg" in mime_type or "jpg" in mime_type else "PNG"
        img.save(buf, format=fmt, quality=85)
        resized = buf.getvalue()

        logger.info(
            f"[{session_id}] Resized ref image: {w}×{h} → {new_w}×{new_h} | "
            f"{len(img_bytes)//1024}KB → {len(resized)//1024}KB"
        )
        out_mime = "image/jpeg" if fmt == "JPEG" else "image/png"
        return resized, out_mime

    except ImportError:
        logger.warning(f"[{session_id}] Pillow not installed — skipping resize")
        return img_bytes, mime_type
    except Exception as e:
        logger.warning(f"[{session_id}] Resize failed: {e} — using original")
        return img_bytes, mime_type


class ToolExecutor:
    """Dispatches and executes tool calls from the Live API agent."""

    def __init__(
        self,
        image_generator: ImageGenerator,
        storage: StorageService,
        pregen: PreGenerator | None = None,
    ) -> None:
        self._image_gen = image_generator
        self._storage = storage
        self._pregen = pregen

    async def execute(
        self,
        session: Session,
        function_call: types.FunctionCall,
        emit_cb=None,
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
            elif name == "propose_names":
                result, event = await self._handle_propose_names(session, args)
            elif name == "reveal_brand_identity":
                result, event = await self._handle_reveal_brand_identity(session, args, emit_cb=emit_cb)
            elif name == "suggest_fonts":
                result, event = await self._handle_suggest_fonts(session, args)
            elif name == "generate_image":
                result, event = await self._handle_generate_image(session, args)
            elif name == "generate_palette":
                result, event = await self._handle_generate_palette(session, args)
            elif name == "update_tagline":
                result, event = await self._handle_update_tagline(session, args)
            elif name == "update_brand_story":
                result, event = await self._handle_update_brand_story(session, args)
            elif name == "update_brand_voice":
                result, event = await self._handle_update_brand_voice(session, args)
            elif name == "update_brand_values":
                result, event = await self._handle_update_brand_values(session, args)
            elif name == "generate_voiceover":
                result, event = await self._handle_voiceover(session, args, emit_cb=emit_cb)
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

    async def _handle_propose_names(
        self, session: Session, args: dict,
    ) -> tuple[dict, dict | None]:
        """propose_names — present 3 brand name proposals to user.

        If names were pre-generated in parallel (during analysis speech) AND
        already sent to the frontend (_pregen_names_sent=True), return them
        immediately — the cards are already visible.

        If _pregen_names_sent is False, the user never saw the pregen names
        (e.g. this is a retry after name rejection). Ignore the stale cache
        and use the agent's fresh args instead.
        """
        # Only use pregen cache if cards were already sent to frontend
        pregen = getattr(session, "_pregen_names", None)
        pregen_sent = getattr(session, "_pregen_names_sent", False)
        if pregen and pregen_sent:
            session._pregen_names = None  # clear to prevent re-use
            session._pregen_names_sent = False
            logger.info(
                f"[{session.id}] Phase: PROPOSING | Action: propose_names_pregen_hit | "
                f"Names: {[n['name'] for n in pregen]}"
            )
            result = {
                "status": "success",
                "message": "Done. Do NOT speak.",
                "names": [n["name"] for n in pregen],
            }
            return result, None  # don't re-emit — already sent to frontend

        # Stale pregen cache (cards never shown) — discard and use agent's args
        if pregen and not pregen_sent:
            logger.info(
                f"[{session.id}] Phase: PROPOSING | Action: propose_names_pregen_discarded | "
                f"Reason: _pregen_names_sent=False (retry/regen) | "
                f"Using agent args instead"
            )
            session._pregen_names = None

        names = args.get("names", [])
        if not names:
            return {"status": "error", "error": "No names provided"}, None

        # Validate and normalize
        validated = []
        for i, n in enumerate(names[:3]):
            if isinstance(n, dict) and n.get("name"):
                validated.append({
                    "id": i + 1,
                    "name": n["name"],
                    "rationale": n.get("rationale", ""),
                    **({"recommended": True} if n.get("recommended") else {}),
                })

        logger.info(
            f"[{session.id}] Phase: PROPOSING | Action: propose_names | "
            f"Names: {[n['name'] for n in validated]}"
        )

        event = {
            "type": "name_proposals",
            "names": validated,
            "auto_select_seconds": 8,
        }
        result = {
            "status": "success",
            "message": "Done. Do NOT speak.",
            "names": [n["name"] for n in validated],
        }
        return result, event

    async def _handle_reveal_brand_identity(
        self, session: Session, args: dict,
        emit_cb=None,
    ) -> tuple[dict, dict | None]:
        """reveal_brand_identity — emit brand name, tagline, story, values, tone."""
        import asyncio

        brand_name = args.get("brand_name", session.brand_name or "Brand")
        tagline = args.get("tagline", "")
        brand_story = args.get("brand_story", "")
        brand_values = args.get("brand_values", [])
        tone_do = args.get("tone_of_voice_do", [])
        tone_dont = args.get("tone_of_voice_dont", [])

        session.brand_name = brand_name
        session.tagline = tagline
        session.brand_story = brand_story
        session.brand_values = brand_values
        session.tone_of_voice = {"do": tone_do, "dont": tone_dont}

        logger.info(
            f"[{session.id}] Phase: PROPOSING | Action: reveal_brand_identity | "
            f"Name: {brand_name} | Tagline: {tagline[:50]}"
        )

        # Emit events sequentially with stagger so frontend animates them
        events = [
            {"type": "brand_name_reveal", "name": brand_name},
        ]
        if tagline:
            events.append({"type": "tagline_reveal", "tagline": tagline})
        if brand_story:
            events.append({"type": "brand_story", "story": brand_story})
        if brand_values:
            events.append({"type": "brand_values", "values": brand_values})
        if tone_do or tone_dont:
            events.append({
                "type": "tone_of_voice",
                "tone_of_voice": {"do": tone_do, "dont": tone_dont},
            })

        # Emit all except the last via callback; return the last as the event.
        # No sleep here — delivery consumer handles stagger timing.
        if emit_cb and len(events) > 1:
            for ev in events[:-1]:
                await emit_cb(ev)
            last_event = events[-1]
        elif events:
            last_event = events[0]
        else:
            last_event = None

        result = {
            "status": "success",
            "brand_name": brand_name,
            "message": "Done. Do NOT speak.",
        }
        return result, last_event

    async def _handle_suggest_fonts(
        self, session: Session, args: dict,
    ) -> tuple[dict, dict | None]:
        """suggest_fonts — emit font suggestion to frontend."""
        heading_font = args.get("heading_font", "")
        heading_style = args.get("heading_style", "")
        body_font = args.get("body_font", "")
        body_style = args.get("body_style", "")
        rationale = args.get("rationale", "")

        session.font_suggestion = {
            "heading": {"family": heading_font, "style": heading_style},
            "body": {"family": body_font, "style": body_style},
        }

        logger.info(
            f"[{session.id}] Phase: GENERATING | Action: suggest_fonts | "
            f"Heading: {heading_font} | Body: {body_font}"
        )

        event = {
            "type": "font_suggestion",
            "heading": {"family": heading_font, "google_fonts": True, "style": heading_style},
            "body": {"family": body_font, "google_fonts": True, "style": body_style},
            "rationale": rationale,
        }
        result = {
            "status": "success",
            "message": "Done. Do NOT speak.",
        }
        return result, event

    async def _handle_generate_image(
        self, session: Session, args: dict,
    ) -> tuple[dict, dict | None]:
        """generate_image — generate brand asset via Nano Banana Pro.

        Checks pre-generated results first. Falls back to live generation.
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

        brand_name = args.get("brand_name", session.brand_name or "Brand")

        # --- Check pre-generated result first ---
        # Skip pregen cache if this is a REGENERATION (asset already completed once).
        # The agent is calling generate_image again because the user asked for changes,
        # so we must honor the new prompt instead of returning the cached version.
        is_regen = asset_type in session.completed_assets
        if self._pregen and not is_regen:
            pregen_result = await self._pregen.get_image_result(session, asset_type)
            if pregen_result and pregen_result.get("status") == "success":
                url = pregen_result.get("url")
                if url:
                    session.mark_asset_complete(asset_type, url)
                    logger.info(
                        f"[{session.id}] Phase: GENERATING | Action: pregen_image_hit | "
                        f"Asset: {asset_type} | URL: {url} | "
                        f"Progress: {session.progress}"
                    )
                    event = {
                        "type": "image_generated",
                        "asset_type": asset_type,
                        "url": url,
                        "label": _ASSET_LABELS.get(asset_type, asset_type).title(),
                        "description": pregen_result.get("description", ""),
                        "brand_name": brand_name,
                        "progress": session.progress,
                    }
                    return pregen_result, event
        elif is_regen:
            logger.info(
                f"[{session.id}] Phase: GENERATING | Action: pregen_cache_skipped | "
                f"Asset: {asset_type} | Reason: regeneration (user feedback)"
            )

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

        style_anchor = args.get("style_anchor", "")
        aspect_ratio = args.get("aspect_ratio")

        # Update brand name if agent provides one
        if args.get("brand_name") and not session.brand_name:
            session.brand_name = args["brand_name"]

        # Build reference images for chaining:
        # - logo: text-only (no product photo in the logo)
        # - hero_lifestyle / instagram_post: product + logo as references
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

        # Enrich prompt: product + logo must be visible in the output
        enriched_prompt = prompt
        if asset_type in ("hero_lifestyle", "instagram_post") and ref_images:
            enriched_prompt += (
                " IMPORTANT: The generated image MUST prominently feature the exact product "
                "from the reference photo. The brand logo must be clearly visible and "
                "naturally integrated into the composition."
            )

        # Append palette hex values if available
        if session.palette and asset_type in ("hero_lifestyle", "instagram_post"):
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

        If pre-gen palette is available, returns it instantly.
        Otherwise uses agent-provided colors. Requires at minimum mood OR
        style_anchor. Colors array is required but we default to empty if missing.
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

        # Check pre-generated palette first
        colors = None
        if self._pregen and self._pregen.has_palette(session):
            colors = session.palette
            logger.info(
                f"[{session.id}] Phase: GENERATING | Action: pregen_palette_hit | "
                f"Colors: {len(colors)}"
            )

        # Fall back to agent-provided colors
        if not colors:
            colors = args.get("colors", [])
            if colors:
                validated = []
                for c in colors:
                    if isinstance(c, dict) and c.get("hex"):
                        validated.append({
                            "hex": c["hex"],
                            "role": c.get("role", "unknown"),
                            "name": c.get("name", ""),
                        })
                colors = validated

        if colors:
            session.palette = colors
            logger.info(
                f"[{session.id}] Phase: GENERATING | Action: palette_stored | "
                f"Colors: {len(colors)}"
            )

        result = {
            "status": "success",
            "message": "Done. Do NOT speak.",
            "mood": mood,
            "style_anchor": style_anchor,
            "product_colors": product_colors,
        }
        # Emit palette_reveal (structured event for frontend rendering)
        event = {"type": "palette_reveal", "mood": mood, "colors": colors or []}
        return result, event

    async def _handle_voiceover(
        self, session: Session, args: dict,
        emit_cb=None,
    ) -> tuple[dict, dict | None]:
        """generate_voiceover — dual-voice brand story via Gemini TTS.

        Generates TWO audio files:
        1. voiceover_handoff.wav — Charon's handoff line
        2. voiceover_story.wav — Anna/Kore's brand story narration

        Emits two sequential events: voiceover_handoff, then voiceover_story.
        Only voiceover_story URL is stored as session.audio_url (the deliverable).
        """
        handoff_text = args.get("handoff_text", "")
        narration_text = args.get("narration_text", args.get("text", session.brand_story or ""))
        mood = args.get("mood", "luxury")

        if not narration_text:
            logger.warning(
                f"[{session.id}] Phase: GENERATING | Action: voiceover_no_text | "
                f"No narration text available for voiceover"
            )
            return {"status": "skipped", "reason": "No narration text provided"}, None

        import asyncio
        from config import LIVE_API_VOICE, NARRATOR_VOICE

        # Await background story TTS task if still running
        bg_task = session.pregen_tasks.get("voiceover")
        if bg_task and not bg_task.done():
            logger.info(
                f"[{session.id}] Phase: GENERATING | Action: voiceover_awaiting_bg"
            )
            try:
                await bg_task
            except Exception:
                pass

        # --- Generate handoff (Charon) + greeting (Anna) in parallel ---
        # greeting_text is a dedicated parameter — agent explicitly separates
        # Anna's intro from the brand story. No extraction needed.
        greeting_text = args.get("greeting_text", "").strip()
        logger.info(
            f"[{session.id}] Phase: GENERATING | Action: voiceover_params | "
            f"handoff={bool(handoff_text)} | greeting={bool(greeting_text)} | "
            f"narration_len={len(narration_text)}"
        )

        async def _noop():
            return None

        # Handoff TTS is NOT generated — Charon already said the handoff line
        # via Live API audio. Generating TTS would play it twice.
        # We still emit the event so the text appears in chat.
        result = {"status": "success"}

        if handoff_text and emit_cb:
            await emit_cb({
                "type": "voiceover_handoff",
                "audio_url": None,
                "text": handoff_text,
            })

        # Greeting (Anna's voice only)
        greeting_wav = None
        if greeting_text:
            greeting_wav = await _tts_generate(
                session_id=session.id,
                text=greeting_text,
                voice=NARRATOR_VOICE,
                label="voiceover_greeting",
            )

        # --- Emit greeting (Anna's intro) ---
        if greeting_wav:
            greeting_url = await self._storage.upload_image(
                session_id=session.id,
                asset_type="voiceover_greeting",
                image_bytes=greeting_wav,
                mime_type="audio/wav",
            )
            logger.info(
                f"[{session.id}] Phase: GENERATING | Action: voiceover_greeting_stored | "
                f"URL: {greeting_url} | Size: {len(greeting_wav)} bytes"
            )
            if emit_cb:
                await emit_cb({
                    "type": "voiceover_greeting",
                    "audio_url": greeting_url,
                    "text": greeting_text,
                })

        # --- Story narration (Anna's voice) — use bg pre-gen cache ---
        if session.audio_url:
            story_url = session.audio_url
            logger.info(
                f"[{session.id}] Phase: GENERATING | Action: voiceover_story_cached | "
                f"URL: {story_url}"
            )
        else:
            # Fallback: generate story fresh
            story_wav = await _tts_generate(
                session_id=session.id,
                text=narration_text,
                voice=NARRATOR_VOICE,
                label="voiceover_story",
            )
            if not story_wav:
                logger.warning(
                    f"[{session.id}] Phase: GENERATING | Action: voiceover_story_failed"
                )
                return {"status": "skipped", "reason": "TTS generation failed"}, None

            story_url = await self._storage.upload_image(
                session_id=session.id,
                asset_type="voiceover_story",
                image_bytes=story_wav,
                mime_type="audio/wav",
            )
            session.audio_url = story_url
            logger.info(
                f"[{session.id}] Phase: GENERATING | Action: voiceover_story_stored | "
                f"URL: {story_url} | Size: {len(story_wav)} bytes"
            )

        result["audio_url"] = story_url
        last_event = {
            "type": "voiceover_story",
            "audio_url": story_url,
        }

        return result, last_event

    async def _handle_update_tagline(
        self, session: Session, args: dict,
    ) -> tuple[dict, dict | None]:
        """update_tagline — replace only the tagline, nothing else."""
        tagline = args.get("tagline", "").strip()
        if not tagline:
            return {"status": "error", "error": "No tagline provided"}, None
        session.tagline = tagline
        logger.info(f"[{session.id}] Action: update_tagline | Tagline: {tagline[:60]}")
        event = {"type": "tagline_reveal", "tagline": tagline}
        return {"status": "success", "message": "Done. Do NOT speak."}, event

    async def _handle_update_brand_story(
        self, session: Session, args: dict,
    ) -> tuple[dict, dict | None]:
        """update_brand_story — replace story and clear voiceover so it regenerates."""
        brand_story = args.get("brand_story", "").strip()
        if not brand_story:
            return {"status": "error", "error": "No brand_story provided"}, None
        session.brand_story = brand_story
        # Clear cached voiceover — will be regenerated in next pipeline step
        session.audio_url = None
        session.voiceover_sent = False
        if session.zip_url:
            session.zip_url = None
        logger.info(f"[{session.id}] Action: update_brand_story | Story: {brand_story[:60]}")
        event = {"type": "brand_story", "story": brand_story}
        return {"status": "success", "message": "Done. Voiceover will regenerate."}, event

    async def _handle_update_brand_voice(
        self, session: Session, args: dict,
    ) -> tuple[dict, dict | None]:
        """update_brand_voice — replace tone of voice do/don't rules only."""
        tone_do = args.get("tone_of_voice_do", [])
        tone_dont = args.get("tone_of_voice_dont", [])
        if not tone_do and not tone_dont:
            return {"status": "error", "error": "No tone rules provided"}, None
        session.tone_of_voice = {"do": tone_do, "dont": tone_dont}
        if session.zip_url:
            session.zip_url = None
        logger.info(f"[{session.id}] Action: update_brand_voice | Do: {tone_do[:2]} | Dont: {tone_dont[:2]}")
        event = {"type": "tone_of_voice", "tone_of_voice": {"do": tone_do, "dont": tone_dont}}
        return {"status": "success", "message": "Done. Do NOT speak."}, event

    async def _handle_update_brand_values(
        self, session: Session, args: dict,
    ) -> tuple[dict, dict | None]:
        """update_brand_values — replace only the brand values list."""
        values = args.get("brand_values", [])
        if not values:
            return {"status": "error", "error": "No brand values provided"}, None
        session.brand_values = values
        if session.zip_url:
            session.zip_url = None
        logger.info(f"[{session.id}] Action: update_brand_values | Values: {values}")
        event = {"type": "brand_values", "values": values}
        return {"status": "success", "message": "Done. Do NOT speak."}, event

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

        try:
            zip_url = await self._storage.create_zip(
                session_id=session.id,
                asset_urls=session.asset_urls,
            )
            session.zip_url = zip_url
        except Exception as e:
            logger.error(
                f"[{session.id}] Phase: GENERATING | Action: zip_creation_failed | Error: {e}"
            )
            zip_url = None
            session.zip_url = None

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
            "message": "Done. Do NOT speak.",
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
