"""Canvas-aware tool executor — orchestrates tool dispatch and response wrapping.

Handlers live in tool_handlers.py. This module only:
  1. Dispatches FunctionCall to the right handler.
  2. Injects _instruction into successful responses.
  3. Wraps result in FunctionResponse.
  4. Never raises — all errors returned as error results.
"""

import logging
import time

from google.genai import types

from models.session import Session
from services.image_generator import ImageGenerator
from services.storage import StorageService
from services import tool_handlers as handlers

logger = logging.getLogger("brand-agent")

# Tools that must NOT receive the generic feedback _instruction
_NO_FEEDBACK_TOOLS = {"propose_names", "finalize_brand_kit"}
# Tools that update canvas text — get a slightly different instruction
_CANVAS_UPDATE_TOOLS = {"set_brand_identity", "set_palette", "set_fonts"}

_INSTRUCTION_CANVAS = (
    "ONE sentence confirming the update and telling the user they can see it above. "
    "Example: 'Updated — you can check it in the section above.' "
    "ONE question asking what to do next. STOP."
)
_INSTRUCTION_DEFAULT = (
    "Follow the exact script for this step. "
    "ONE sentence. ONE question. STOP."
)


class ToolExecutor:
    """Executes tool calls from the Live API agent, updating the canvas."""

    def __init__(self, image_generator: ImageGenerator, storage: StorageService) -> None:
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
        result, events = await self._dispatch(name, session, args)
        latency = (time.perf_counter() - t0) * 1000

        logger.debug(
            f"[{session.id}] Tool: {name} | Status: {result.get('status')} | "
            f"Latency: {latency:.0f}ms"
        )

        if name not in _NO_FEEDBACK_TOOLS and result.get("status") != "error":
            instruction = _INSTRUCTION_CANVAS if name in _CANVAS_UPDATE_TOOLS else _INSTRUCTION_DEFAULT
            result["_instruction"] = instruction

        return types.FunctionResponse(name=name, response=result), events

    async def _dispatch(
        self, name: str, session: Session, args: dict,
    ) -> tuple[dict, list[dict]]:
        """Route to the correct handler. Never raises."""
        try:
            if name == "set_brand_identity":
                return await handlers.handle_set_identity(session, args)
            elif name == "set_palette":
                return await handlers.handle_set_palette(session, args)
            elif name == "set_fonts":
                return await handlers.handle_set_fonts(session, args)
            elif name == "generate_image":
                return await handlers.handle_generate_image(session, args, self._image_gen, self._storage)
            elif name == "propose_names":
                return await handlers.handle_propose_names(session, args)
            elif name == "generate_voiceover":
                return await handlers.handle_voiceover(session, args, self._storage)
            elif name == "finalize_brand_kit":
                return await handlers.handle_finalize(session, self._storage)
            else:
                return {"status": "error", "error": f"Unknown tool: {name}"}, []
        except Exception as e:
            logger.error(f"[{session.id}] Tool: {name} | Error: {e}")
            return {"status": "error", "error": str(e)}, []
