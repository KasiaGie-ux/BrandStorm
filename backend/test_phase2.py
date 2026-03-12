"""Phase 2 end-to-end test — WebSocket + Live API + image generation.

Starts the FastAPI server, connects via WebSocket, sends a product image,
and prints every event received from the agent pipeline.

Usage:
    python test_phase2.py <product_image_path>
    python test_phase2.py C:\\Users\\Admin\\Desktop\\primary.png
"""

import asyncio
import base64
import json
import mimetypes
import sys
import time
from pathlib import Path

import httpx
import websockets

SERVER_HOST = "localhost"
SERVER_PORT = 8080
BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
WS_URL = f"ws://{SERVER_HOST}:{SERVER_PORT}/ws/test-e2e"
TIMEOUT_SEC = 180  # 3 min max for full brand generation (4 images)


def ts() -> str:
    """Formatted timestamp for logging."""
    return time.strftime("%H:%M:%S")


def load_image(path: str) -> tuple[str, str]:
    """Load image, return (base64_data, mime_type)."""
    p = Path(path)
    if not p.exists():
        print(f"ERROR: Image not found: {path}")
        sys.exit(1)
    mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
    b64 = base64.b64encode(p.read_bytes()).decode()
    print(f"[{ts()}] Loaded image: {p.name} ({p.stat().st_size / 1024:.0f} KB, {mime})")
    return b64, mime


async def check_health() -> bool:
    """Verify server is running."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/api/health", timeout=5)
            data = r.json()
            print(f"[{ts()}] Health: {data}")
            return data.get("status") == "ok"
    except Exception as e:
        print(f"[{ts()}] Health check failed: {e}")
        return False


async def get_assets(session_id: str) -> dict | None:
    """Fetch session assets via REST API."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/api/assets/{session_id}", timeout=10)
            if r.status_code == 200:
                return r.json()
            print(f"[{ts()}] GET /api/assets/{session_id} → {r.status_code}")
            return None
    except Exception as e:
        print(f"[{ts()}] Assets fetch error: {e}")
        return None


async def run_test(image_path: str):
    """Main test: connect WS, send image, collect events."""
    t_start = time.perf_counter()

    # 1. Health check
    print(f"\n{'='*60}")
    print(f"  PHASE 2 E2E TEST")
    print(f"{'='*60}\n")

    if not await check_health():
        print("Server not running. Start with: cd backend && python main.py")
        return

    # 2. Load image
    image_b64, mime_type = load_image(image_path)

    # 3. Connect WebSocket
    print(f"[{ts()}] Connecting to {WS_URL}...")
    session_id = "test-e2e"
    events: list[dict] = []
    agent_texts: list[str] = []
    assets_generated: list[str] = []
    tools_invoked: list[str] = []
    complete = False
    followup_sent = False

    try:
        async with websockets.connect(WS_URL, max_size=50 * 1024 * 1024) as ws:
            print(f"[{ts()}] WebSocket connected\n")

            # 4. Send image_upload
            upload_msg = json.dumps({
                "type": "image_upload",
                "data": image_b64,
                "mime_type": mime_type,
                "prompt": (
                    "Analyze this product and create a complete brand kit. "
                    "Generate a brand name, then call your tools to create "
                    "logo, hero image, Instagram post, and packaging concept."
                ),
            })
            await ws.send(upload_msg)
            print(f"[{ts()}] Sent image_upload ({len(upload_msg) / 1024:.0f} KB)")
            print(f"[{ts()}] Waiting for agent response...\n")

            # 5. Receive loop
            try:
                async with asyncio.timeout(TIMEOUT_SEC):
                    async for raw in ws:
                        event = json.loads(raw)
                        event_type = event.get("type", "unknown")
                        events.append({"ts": time.perf_counter() - t_start, **event})

                        if event_type == "session_ready":
                            print(f"[{ts()}] SESSION READY")

                        elif event_type == "agent_text":
                            text = event.get("text", "")
                            partial = event.get("partial", False)
                            if partial:
                                print(text, end="", flush=True)
                            else:
                                agent_texts.append(text)
                                print(f"\n[{ts()}] --- agent turn complete ---")

                        elif event_type == "agent_audio":
                            size = len(event.get("data", ""))
                            print(f"[{ts()}] AUDIO chunk ({size} b64 chars)")

                        elif event_type == "agent_turn_complete":
                            # After first agent turn, send follow-up to trigger generation
                            if not followup_sent:
                                followup_sent = True
                                followup = json.dumps({
                                    "type": "text_input",
                                    "text": (
                                        "Go with that direction. Generate all brand assets — "
                                        "logo, hero shot, Instagram post, and packaging."
                                    ),
                                })
                                await ws.send(followup)
                                print(f"[{ts()}] SENT FOLLOW-UP: choosing direction + generate all\n")

                        elif event_type == "tool_invoked":
                            tool = event.get("tool", "?")
                            tools_invoked.append(tool)
                            args = event.get("args", {})
                            phase = event.get("phase", "?")
                            print(f"\n[{ts()}] TOOL INVOKED: {tool} | phase={phase}")
                            if args:
                                for k, v in args.items():
                                    val = str(v)[:80]
                                    print(f"         {k}: {val}")

                        elif event_type == "image_generated":
                            asset = event.get("asset_type", "?")
                            url = event.get("url", "?")
                            progress = event.get("progress", 0)
                            assets_generated.append(asset)
                            print(
                                f"[{ts()}] IMAGE GENERATED: {asset} | "
                                f"url={url} | progress={progress:.0%}"
                            )

                        elif event_type == "generation_complete":
                            complete = True
                            brand = event.get("brand_name", "?")
                            zip_url = event.get("zip_url", "?")
                            print(f"\n[{ts()}] GENERATION COMPLETE!")
                            print(f"         Brand: {brand}")
                            print(f"         ZIP:   {zip_url}")
                            break

                        elif event_type == "session_timeout":
                            print(f"\n[{ts()}] SESSION TIMEOUT: {event.get('message')}")
                            break

                        elif event_type == "error":
                            print(f"\n[{ts()}] ERROR: {event.get('message')}")

                        else:
                            print(f"[{ts()}] EVENT: {event_type} → {json.dumps(event)[:120]}")

            except TimeoutError:
                print(f"\n[{ts()}] TEST TIMEOUT ({TIMEOUT_SEC}s)")

    except Exception as e:
        print(f"[{ts()}] WebSocket error: {e}")

    # 6. Fetch assets via REST
    print(f"\n[{ts()}] Fetching assets via REST API...")
    assets = await get_assets(session_id)

    # 7. Summary
    elapsed = time.perf_counter() - t_start
    print(f"\n{'='*60}")
    print(f"  TEST SUMMARY")
    print(f"{'='*60}")
    print(f"  Total time:        {elapsed:.1f}s")
    print(f"  Events received:   {len(events)}")
    print(f"  Agent turns:       {len(agent_texts)}")
    print(f"  Tools invoked:     {', '.join(tools_invoked) or 'none'}")
    print(f"  Assets generated:  {', '.join(assets_generated) or 'none'}")
    print(f"  Complete:          {'YES' if complete else 'NO'}")

    if assets:
        print(f"\n  REST /api/assets response:")
        print(f"    Phase:           {assets.get('phase', '?')}")
        print(f"    Brand name:      {assets.get('brand_name', '?')}")
        print(f"    Progress:        {assets.get('progress', 0):.0%}")
        print(f"    Assets:          {list(assets.get('asset_urls', {}).keys())}")
        print(f"    ZIP:             {assets.get('zip_url', 'none')}")
    else:
        print(f"\n  REST /api/assets: session not found (already cleaned up)")

    print(f"{'='*60}\n")

    # Exit code
    if assets_generated:
        print("PASS — at least one asset generated")
    elif tools_invoked:
        print("PARTIAL — tools invoked but no images generated")
    else:
        print("FAIL — no tools invoked")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_phase2.py <product_image_path>")
        print("Example: python test_phase2.py C:\\Users\\Admin\\Desktop\\primary.png")
        sys.exit(1)

    asyncio.run(run_test(sys.argv[1]))
