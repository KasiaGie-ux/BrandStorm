"""Configuration — all settings from environment variables."""
import os

# GCP
GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "brand-in-a-box")
GCP_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
USE_VERTEX_AI = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() == "true"

# === Image Generation ===
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gemini-3-pro-image-preview")        # Nano Banana Pro — best quality, reasoning-driven
IMAGE_MODEL_FALLBACK = os.getenv("IMAGE_MODEL_FALLBACK", "gemini-2.5-flash-image")  # Nano Banana — faster, GA

# === Text / Reasoning ===
TEXT_MODEL = os.getenv("TEXT_MODEL", "gemini-3.1-pro-preview")              # Latest SOTA reasoning
TEXT_MODEL_FALLBACK = os.getenv("TEXT_MODEL_FALLBACK", "gemini-2.5-pro")    # Stable, GA

# === Live API (voice conversation) ===
LIVE_API_MODEL = os.getenv("LIVE_API_MODEL", "gemini-live-2.5-flash-native-audio")          # Vertex AI GA — HD voices, barge-in
LIVE_API_MODEL_DEV = os.getenv("LIVE_API_MODEL_DEV", "gemini-2.5-flash-native-audio-preview-12-2025")  # Dev API preview
LIVE_API_FALLBACK = os.getenv("LIVE_API_FALLBACK", "gemini-2.5-flash")      # Basic Live API, worse voice

# Storage
UPLOAD_BUCKET = os.getenv("UPLOAD_BUCKET", f"bb-uploads-{GCP_PROJECT}")
ASSETS_BUCKET = os.getenv("ASSETS_BUCKET", f"bb-assets-{GCP_PROJECT}")

# Session
SESSION_TIMEOUT_SEC = int(os.getenv("SESSION_TIMEOUT_SEC", "300"))
SESSION_WARNING_SEC = int(os.getenv("SESSION_WARNING_SEC", "240"))

# Server
PORT = int(os.getenv("PORT", "8080"))
HOST = os.getenv("HOST", "0.0.0.0")
