"""
Phase 1: Live API + Function Calling Spike
============================================
Validates: Gemini Live API voice conversation + vision + function calling
for image generation via Nano Banana Pro (gemini-3-pro-image-preview).

Usage:
    python backend/spike_live_api.py <product_image_path> [prompt]

Requires:
    - ADC configured: gcloud auth application-default login
    - pip install google-genai Pillow
"""

import asyncio
import base64
import io
import logging
import mimetypes
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

from config import (
    GCP_LOCATION,
    GCP_PROJECT,
    IMAGE_MODEL,
    IMAGE_MODEL_FALLBACK,
    LIVE_API_MODEL,
    SESSION_TIMEOUT_SEC,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("spike")

SESSION_ID = "spike-001"

# ---------------------------------------------------------------------------
# Tool declaration — registered with Live API so the agent can call it
# ---------------------------------------------------------------------------
GENERATE_IMAGE_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="generate_image",
            description=(
                "Generate a brand image asset (logo, hero shot, Instagram post, "
                "packaging mockup). Call this when you have decided on a brand "
                "direction and want to create a visual asset."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "asset_type": types.Schema(
                        type=types.Type.STRING,
                        description="Type of asset: logo, hero, instagram, packaging",
                        enum=["logo", "hero", "instagram", "packaging"],
                    ),
                    "prompt": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "Detailed image generation prompt describing the "
                            "desired visual. Include brand name, colors, style, "
                            "composition, and mood."
                        ),
                    ),
                    "brand_name": types.Schema(
                        type=types.Type.STRING,
                        description="The brand name to incorporate.",
                    ),
                },
                required=["asset_type", "prompt", "brand_name"],
            ),
        )
    ]
)

SYSTEM_PROMPT = """You are a live AI creative director for "Brand in a Box".

The user will show you a product photo. Your job:
1. Analyze the product — describe what you see (materials, colors, shape, vibe).
2. Propose a brand name and brief creative direction.
3. Call the generate_image tool to create a logo for the brand.
4. After the image is generated, comment on it and ask the user for feedback.

Be opinionated, creative, and concise. Speak like a confident creative director."""


# ---------------------------------------------------------------------------
# Image generation — calls Nano Banana Pro with fallback
# ---------------------------------------------------------------------------
async def generate_image_with_fallback(
    client: genai.Client,
    prompt: str,
    asset_type: str,
    brand_name: str,
) -> dict:
    """Generate image via Nano Banana Pro, fallback to gemini-2.5-flash-image."""
    full_prompt = (
        f"Create a professional {asset_type} for the brand '{brand_name}'. "
        f"{prompt} "
        f"High quality, clean design, suitable for commercial use."
    )

    models_to_try = [
        (IMAGE_MODEL, "Nano Banana Pro"),
        (IMAGE_MODEL_FALLBACK, "Nano Banana (fallback)"),
    ]

    for model_name, label in models_to_try:
        t0 = time.perf_counter()
        try:
            logger.info(
                f"[{SESSION_ID}] Phase: GENERATING | Action: image_gen_start | "
                f"Model: {label} ({model_name}) | Asset: {asset_type}"
            )
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )
            latency = (time.perf_counter() - t0) * 1000

            # Extract image data from response
            if not response.candidates or not response.candidates[0].content.parts:
                logger.warning(
                    f"[{SESSION_ID}] Phase: GENERATING | Action: empty_response | "
                    f"Model: {label} | Latency: {latency:.0f}ms"
                )
                continue

            image_part = None
            text_part = None
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    image_part = part.inline_data
                elif part.text:
                    text_part = part.text

            if image_part is None:
                logger.warning(
                    f"[{SESSION_ID}] Phase: GENERATING | Action: no_image_in_response | "
                    f"Model: {label} | Latency: {latency:.0f}ms"
                )
                continue

            # Save image to disk for inspection
            ext = image_part.mime_type.split("/")[-1]
            out_path = Path(f"spike_output_{asset_type}.{ext}")
            out_path.write_bytes(image_part.data)

            logger.info(
                f"[{SESSION_ID}] Phase: GENERATING | Action: image_generated | "
                f"Model: {label} | Asset: {asset_type} | Latency: {latency:.0f}ms | "
                f"Saved: {out_path}"
            )

            return {
                "status": "success",
                "asset_type": asset_type,
                "brand_name": brand_name,
                "model_used": model_name,
                "latency_ms": round(latency),
                "image_size_bytes": len(image_part.data),
                "description": text_part or "Image generated successfully.",
            }

        except Exception as e:
            latency = (time.perf_counter() - t0) * 1000
            logger.error(
                f"[{SESSION_ID}] Phase: GENERATING | Action: image_gen_failed | "
                f"Model: {label} | Latency: {latency:.0f}ms | Error: {e}"
            )
            continue

    return {
        "status": "error",
        "asset_type": asset_type,
        "error": "All image generation models failed. Try again shortly.",
    }


# ---------------------------------------------------------------------------
# Handle a function call from the Live API agent
# ---------------------------------------------------------------------------
async def handle_function_call(
    client: genai.Client,
    tool_call: types.FunctionCall,
) -> types.FunctionResponse:
    """Execute the agent's function call and return the result."""
    name = tool_call.name
    args = dict(tool_call.args) if tool_call.args else {}

    logger.info(
        f"[{SESSION_ID}] Phase: GENERATING | Action: tool_call_received | "
        f"Tool: {name} | Args: {args}"
    )

    if name == "generate_image":
        missing = [k for k in ("asset_type", "prompt", "brand_name") if k not in args]
        if missing:
            logger.warning(
                f"[{SESSION_ID}] Phase: GENERATING | Action: missing_tool_args | "
                f"Tool: {name} | Missing: {missing}"
            )
        result = await generate_image_with_fallback(
            client=client,
            prompt=args.get("prompt", ""),
            asset_type=args.get("asset_type", "logo"),
            brand_name=args.get("brand_name", "Brand"),
        )
    else:
        result = {"status": "error", "error": f"Unknown tool: {name}"}

    return types.FunctionResponse(
        name=name,
        response=result,
    )


# ---------------------------------------------------------------------------
# Load and encode product image
# ---------------------------------------------------------------------------
def load_product_image(image_path: str) -> types.Part:
    """Load a product image from disk and return as a genai Part."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    mime_type = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    image_bytes = path.read_bytes()

    logger.info(
        f"[{SESSION_ID}] Loaded product image: {path.name} "
        f"({len(image_bytes) / 1024:.0f} KB, {mime_type})"
    )

    return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)


# ---------------------------------------------------------------------------
# Main spike — Live API session with function calling
# ---------------------------------------------------------------------------
async def run_spike(image_path: str, user_prompt: str | None = None):
    """Connect to Gemini Live API, send product image, handle function calls."""
    logger.info(f"[{SESSION_ID}] === SPIKE START ===")
    logger.info(f"[{SESSION_ID}] Project: {GCP_PROJECT} | Location: {GCP_LOCATION}")
    logger.info(f"[{SESSION_ID}] Live model: {LIVE_API_MODEL}")
    logger.info(f"[{SESSION_ID}] Image model: {IMAGE_MODEL} (fallback: {IMAGE_MODEL_FALLBACK})")

    # Initialize client — Vertex AI mode, ADC auth
    client = genai.Client(
        vertexai=True,
        project=GCP_PROJECT,
        location=GCP_LOCATION,
        http_options=types.HttpOptions(api_version="v1beta1"),
    )

    # Load product image
    image_part = load_product_image(image_path)

    # Build the initial message
    prompt_text = user_prompt or (
        "Analyze this product and generate a brand name. "
        "Then call generate_image to create a logo for the brand."
    )

    transcript: list[str] = []

    # Connect to Live API
    logger.info(f"[{SESSION_ID}] Connecting to Live API...")
    t_connect = time.perf_counter()

    async with client.aio.live.connect(
        model=LIVE_API_MODEL,
        config=types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            tools=[GENERATE_IMAGE_TOOL],
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=SYSTEM_PROMPT)]
            ),
        ),
    ) as session:
        connect_ms = (time.perf_counter() - t_connect) * 1000
        logger.info(
            f"[{SESSION_ID}] Phase: INIT | Action: live_api_connected | "
            f"Latency: {connect_ms:.0f}ms"
        )

        # Send product image + prompt
        logger.info(f"[{SESSION_ID}] Sending image + prompt to agent...")
        await session.send_client_content(
            turns=[
                types.Content(
                    role="user",
                    parts=[
                        image_part,
                        types.Part.from_text(text=prompt_text),
                    ],
                )
            ],
            turn_complete=True,
        )

        transcript.append(f"USER: {prompt_text}")
        transcript.append(f"USER: [product image: {Path(image_path).name}]")

        # Receive loop — handle text, audio, and function calls
        logger.info(f"[{SESSION_ID}] Waiting for agent response...")
        agent_text_buffer: list[str] = []

        try:
            async with asyncio.timeout(SESSION_TIMEOUT_SEC):
                async for message in session.receive():
                    # Server content — audio + transcription from the agent
                    if message.server_content:
                        sc = message.server_content

                        # Audio transcription (native-audio model outputs audio,
                        # not text parts — transcription arrives separately)
                        if sc.output_transcription and sc.output_transcription.text:
                            agent_text_buffer.append(sc.output_transcription.text)
                            print(sc.output_transcription.text, end="", flush=True)

                        # Turn complete — flush buffer
                        if sc.turn_complete:
                            full_text = "".join(agent_text_buffer)
                            if full_text:
                                transcript.append(f"AGENT: {full_text}")
                                print()  # newline after streamed text
                            agent_text_buffer.clear()
                            logger.info(f"[{SESSION_ID}] Agent turn complete")

                    # Tool call — agent wants to generate an image
                    if message.tool_call:
                        for fc in message.tool_call.function_calls:
                            # Flush any text accumulated before the tool call
                            buffered = "".join(agent_text_buffer)
                            if buffered:
                                transcript.append(f"AGENT: {buffered}")
                                print()
                                agent_text_buffer.clear()

                            transcript.append(
                                f"TOOL_CALL: {fc.name}({dict(fc.args) if fc.args else {}})"
                            )

                            # Execute the function call
                            fn_response = await handle_function_call(client, fc)
                            transcript.append(
                                f"TOOL_RESULT: {fc.name} -> {fn_response.response}"
                            )

                            # Send result back to Live API session
                            await session.send_tool_response(
                                function_responses=[fn_response]
                            )
                            logger.info(
                                f"[{SESSION_ID}] Phase: GENERATING | Action: tool_response_sent | "
                                f"Tool: {fc.name}"
                            )

                    # Setup complete signal
                    if message.setup_complete:
                        logger.info(f"[{SESSION_ID}] Phase: INIT | Action: setup_complete")
        except TimeoutError:
            logger.error(
                f"[{SESSION_ID}] Phase: GENERATING | Action: session_timeout | "
                f"Timeout: {SESSION_TIMEOUT_SEC}s"
            )
            transcript.append(f"SYSTEM: Session timed out after {SESSION_TIMEOUT_SEC}s")

    # ---------------------------------------------------------------------------
    # Print full transcript
    # ---------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("FULL TRANSCRIPT")
    print("=" * 70)
    for i, line in enumerate(transcript, 1):
        print(f"  {i}. {line}")
    print("=" * 70)
    logger.info(f"[{SESSION_ID}] === SPIKE COMPLETE ===")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python spike_live_api.py <product_image_path> [prompt]")
        print()
        print("Example:")
        print('  python spike_live_api.py product.jpg "Analyze this and make a logo"')
        sys.exit(1)

    img_path = sys.argv[1]
    prompt = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else None

    asyncio.run(run_spike(img_path, prompt))
