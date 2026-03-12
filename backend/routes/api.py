"""REST API endpoints — upload, assets, health, download."""

import logging
import mimetypes
import uuid

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from services import brand_state
from services.storage import StorageService

logger = logging.getLogger("brand-agent")
router = APIRouter(prefix="/api")

_storage = StorageService()


@router.get("/health")
async def health():
    return {"status": "ok", "version": "5.0", "vertex_ai": True}


@router.post("/upload")
async def upload_product_image(file: UploadFile = File(...)):
    """Upload product image, create session, return session_id + image URL."""
    session_id = uuid.uuid4().hex[:12]
    image_bytes = await file.read()
    mime_type = file.content_type or "image/jpeg"

    session = brand_state.create_session(session_id)
    session.product_image_bytes = image_bytes
    session.product_image_mime = mime_type

    url = await _storage.upload_product_image(
        session_id=session_id,
        image_bytes=image_bytes,
        mime_type=mime_type,
    )
    session.product_image_url = url

    logger.info(
        f"[{session_id}] Phase: INIT | Action: image_uploaded | "
        f"Size: {len(image_bytes) / 1024:.0f}KB | Type: {mime_type}"
    )
    return {"session_id": session_id, "image_url": url}


@router.get("/assets/{session_id}")
async def get_assets(session_id: str):
    """Get all generated assets for a session."""
    session = brand_state.get_session(session_id)
    if not session:
        return JSONResponse(
            status_code=404,
            content={"error": "Session not found"},
        )
    return session.to_dict()


@router.get("/download/{session_id}")
async def download_zip(session_id: str):
    """Download ZIP of all brand assets."""
    session = brand_state.get_session(session_id)
    if not session:
        return JSONResponse(
            status_code=404,
            content={"error": "Session not found"},
        )

    if not session.zip_url:
        # Create ZIP on demand
        if session.asset_urls:
            session.zip_url = await _storage.create_zip(
                session_id=session_id,
                asset_urls=session.asset_urls,
            )
        else:
            return JSONResponse(
                status_code=404,
                content={"error": "No assets generated yet"},
            )

    # For local storage, serve the file directly
    local_path = _storage.get_local_path(session_id, "brand_kit")
    if local_path and local_path.exists():
        return FileResponse(
            path=str(local_path),
            media_type="application/zip",
            filename=f"{session.brand_name or 'brand'}_kit.zip",
        )

    return JSONResponse(
        content={"zip_url": session.zip_url},
    )


@router.get("/assets/{session_id}/{asset_name}")
async def serve_asset(session_id: str, asset_name: str):
    """Serve a single generated asset file (local mode)."""
    asset_type = asset_name.rsplit(".", 1)[0] if "." in asset_name else asset_name
    local_path = _storage.get_local_path(session_id, asset_type)
    if not local_path or not local_path.exists():
        return JSONResponse(status_code=404, content={"error": "Asset not found"})

    mime = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"
    return FileResponse(path=str(local_path), media_type=mime)
