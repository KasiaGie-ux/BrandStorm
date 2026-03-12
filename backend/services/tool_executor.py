"""Executes function calls from Live API agent.

Dispatches to image_generator, palette generation, finalization.
Returns FunctionResponse to send back to the Live API session.
Tracks tool call latency for structured logging.
"""

import logging
import time

from google.genai import types

from models.session import Session
from services.image_generator import ImageGenerator
from services.storage import StorageService

logger = logging.getLogger("brand-agent")


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
        """
        name = function_call.name
        args = dict(function_call.args) if function_call.args else {}
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
        """generate_image — generate brand asset via Nano Banana Pro."""
        missing = [k for k in ("asset_type", "prompt", "style_anchor") if k not in args]
        if missing:
            logger.warning(
                f"[{session.id}] Phase: GENERATING | Action: missing_tool_args | "
                f"Tool: generate_image | Missing: {missing}"
            )

        asset_type = args.get("asset_type", "logo")
        prompt = args.get("prompt", "")
        brand_name = args.get("brand_name", session.brand_name or "Brand")
        style_anchor = args.get("style_anchor", "")
        aspect_ratio = args.get("aspect_ratio")

        # Update brand name if agent provides one
        if args.get("brand_name") and not session.brand_name:
            session.brand_name = args["brand_name"]

        result = await self._image_gen.generate(
            session_id=session.id,
            prompt=prompt,
            asset_type=asset_type,
            brand_name=brand_name,
            style_anchor=style_anchor,
            aspect_ratio=aspect_ratio,
        )

        event = None
        if result["status"] == "success":
            # Upload to storage
            url = await self._storage.upload_image(
                session_id=session.id,
                asset_type=asset_type,
                image_bytes=result["image_bytes"],
                mime_type=result["mime_type"],
            )
            session.mark_asset_complete(asset_type, url)

            # Remove raw bytes before sending to Live API (too large)
            result.pop("image_bytes", None)
            result["url"] = url

            event = {
                "type": "image_generated",
                "asset_type": asset_type,
                "url": url,
                "brand_name": brand_name,
                "progress": session.progress,
            }

        return result, event

    async def _handle_generate_palette(
        self, session: Session, args: dict,
    ) -> tuple[dict, dict | None]:
        """generate_palette — agent decides colors, we store them."""
        mood = args.get("mood", "")
        style_anchor = args.get("style_anchor", "")
        product_colors = args.get("product_colors", [])

        # The agent will describe the palette in its response.
        # We acknowledge and ask it to provide HEX values.
        result = {
            "status": "success",
            "message": (
                "Generate a 5-color palette. Return colors as a list with: "
                "hex value, role (primary/secondary/accent/neutral/background), "
                f"and name. Mood: {mood}. Style: {style_anchor}."
            ),
            "mood": mood,
            "style_anchor": style_anchor,
            "product_colors": product_colors,
        }
        event = {"type": "tool_invoked", "tool": "generate_palette", "mood": mood}
        return result, event

    async def _handle_finalize(
        self, session: Session, args: dict,
    ) -> tuple[dict, dict | None]:
        """finalize_brand_kit — package all assets into ZIP."""
        # Update brand kit text assets from args
        if args.get("brand_name"):
            session.brand_name = args["brand_name"]

        zip_url = await self._storage.create_zip(
            session_id=session.id,
            asset_urls=session.asset_urls,
        )
        session.zip_url = zip_url

        result = {
            "status": "success",
            "brand_name": session.brand_name,
            "assets_count": len(session.completed_assets),
            "zip_url": zip_url,
        }
        event = {
            "type": "generation_complete",
            "brand_name": session.brand_name,
            "zip_url": zip_url,
            "assets": session.asset_urls,
            "progress": 1.0,
        }
        return result, event
