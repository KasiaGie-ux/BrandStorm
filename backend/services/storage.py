"""Cloud Storage service — upload, signed URLs, ZIP creation.

For hackathon/local dev: saves files locally and returns file:// paths.
In production (Cloud Run): uses GCS with signed URLs.
"""

import asyncio
import io
import logging
import time
import zipfile
from pathlib import Path

from config import LOCAL_ASSETS_DIR as _LOCAL_ASSETS_DIR_STR, USE_GCS

logger = logging.getLogger("brand-agent")

LOCAL_ASSETS_DIR = Path(_LOCAL_ASSETS_DIR_STR)


class StorageService:
    """Handles file storage — local filesystem or GCS."""

    def __init__(self) -> None:
        if not USE_GCS:
            LOCAL_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Storage: local mode → {LOCAL_ASSETS_DIR}")
        else:
            logger.debug("Storage: GCS mode")

    async def upload_image(
        self,
        session_id: str,
        asset_type: str,
        image_bytes: bytes,
        mime_type: str = "image/png",
    ) -> str:
        """Upload generated image, return URL."""
        ext = mime_type.split("/")[-1]
        filename = f"{session_id}/{asset_type}.{ext}"
        t0 = time.perf_counter()

        if USE_GCS:
            url = await self._upload_gcs(filename, image_bytes, mime_type, session_id)
        else:
            url = self._save_local(filename, image_bytes, session_id)

        latency = (time.perf_counter() - t0) * 1000
        logger.debug(
            f"[{session_id}] Phase: GENERATING | Action: asset_uploaded | "
            f"Asset: {asset_type} | Size: {len(image_bytes) / 1024:.0f}KB | "
            f"Latency: {latency:.0f}ms"
        )
        return url

    async def upload_product_image(
        self,
        session_id: str,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> str:
        """Upload the original product image."""
        ext = mime_type.split("/")[-1]
        filename = f"{session_id}/product.{ext}"

        if USE_GCS:
            return await self._upload_gcs(filename, image_bytes, mime_type, session_id)
        return self._save_local(filename, image_bytes, session_id)

    async def create_zip(
        self,
        session_id: str,
        asset_urls: dict[str, str],
    ) -> str:
        """Create a ZIP of all brand assets and return URL."""
        t0 = time.perf_counter()
        buf = io.BytesIO()

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for asset_type, url in asset_urls.items():
                file_path = self._url_to_local_path(url)
                if file_path and file_path.exists():
                    zf.write(file_path, arcname=f"{asset_type}{file_path.suffix}")

        zip_bytes = buf.getvalue()
        zip_filename = f"{session_id}/brand_kit.zip"

        if USE_GCS:
            url = await self._upload_gcs(zip_filename, zip_bytes, "application/zip", session_id)
        else:
            url = self._save_local(zip_filename, zip_bytes, session_id)

        latency = (time.perf_counter() - t0) * 1000
        logger.debug(
            f"[{session_id}] Phase: COMPLETE | Action: zip_created | "
            f"Size: {len(zip_bytes) / 1024:.0f}KB | Assets: {len(asset_urls)} | "
            f"Latency: {latency:.0f}ms"
        )
        return url

    def get_local_path(self, session_id: str, asset_type: str) -> Path | None:
        """Get local file path for an asset (for serving via API)."""
        session_dir = LOCAL_ASSETS_DIR / session_id
        if not session_dir.exists():
            return None
        for f in session_dir.iterdir():
            if f.stem == asset_type:
                return f
        return None

    # --- Private helpers ---

    def _save_local(self, filename: str, data: bytes, session_id: str) -> str:
        path = LOCAL_ASSETS_DIR / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"/api/assets/{filename}"

    def _url_to_local_path(self, url: str) -> Path | None:
        if url.startswith("/api/assets/"):
            rel = url[len("/api/assets/"):]
            path = LOCAL_ASSETS_DIR / rel
            return path if path.exists() else None
        return None

    async def _upload_gcs(
        self, filename: str, data: bytes, mime_type: str, session_id: str,
    ) -> str:
        """Upload to GCS and return signed URL. Imports lazily."""
        from google.cloud import storage as gcs
        from config import ASSETS_BUCKET

        try:
            def _sync_upload() -> str:
                client = gcs.Client()
                bucket = client.bucket(ASSETS_BUCKET)
                blob = bucket.blob(filename)
                blob.upload_from_string(data, content_type=mime_type)
                return blob.generate_signed_url(
                    version="v4",
                    expiration=3600,
                    method="GET",
                )

            url = await asyncio.to_thread(_sync_upload)
            return url
        except Exception as e:
            logger.error(
                f"[{session_id}] Phase: GENERATING | Action: gcs_upload_failed | "
                f"Error: {e} | Falling back to local"
            )
            return self._save_local(filename, data, session_id)
