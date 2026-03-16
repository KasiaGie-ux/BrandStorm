"""REST API endpoints — upload, assets, health, download."""

import logging
import mimetypes
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from services import brand_state
from services.storage import StorageService

logger = logging.getLogger("brand-agent")
router = APIRouter(prefix="/api")

_storage = StorageService()


@router.get("/health")
async def health():
    return {"status": "ok", "version": "5.0", "vertex_ai": True}


_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/upload")
async def upload_product_image(file: UploadFile = File(...)):
    """Upload product image, create session, return session_id + image URL."""
    session_id = uuid.uuid4().hex[:12]
    image_bytes = await file.read()
    mime_type = file.content_type or "image/jpeg"

    if len(image_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image too large (max 10 MB)")
    if not mime_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Only image files are accepted")

    session = brand_state.create_session(session_id)
    session.product_image_bytes = image_bytes
    session.product_image_mime = mime_type

    url = await _storage.upload_product_image(
        session_id=session_id,
        image_bytes=image_bytes,
        mime_type=mime_type,
    )
    logger.info(
        f"[{session_id}] Image uploaded | Size: {len(image_bytes) / 1024:.0f}KB | Type: {mime_type}"
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

    asset_urls = session.canvas.asset_urls
    brand_name = session.canvas.name.value or "brand"

    if not asset_urls:
        return JSONResponse(
            status_code=404,
            content={"error": "No assets generated yet"},
        )

    zip_url = await _storage.create_zip(
        session_id=session_id,
        asset_urls=asset_urls,
    )

    # For local storage, serve the file directly
    local_path = _storage.get_local_path(session_id, "brand_kit")
    if local_path and local_path.exists():
        return FileResponse(
            path=str(local_path),
            media_type="application/zip",
            filename=f"{brand_name}_kit.zip",
        )

    return JSONResponse(
        content={"zip_url": zip_url},
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
