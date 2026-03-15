"""Configuration — all settings from environment variables."""
import os

# GCP
GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "brandstorm-2026")
GCP_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
USE_VERTEX_AI = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() == "true"

# === Image Generation ===
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gemini-3.1-flash-image-preview")    # primary image generation model
IMAGE_MODEL_FALLBACK = os.getenv("IMAGE_MODEL_FALLBACK", "gemini-2.5-flash-image")  # Nano Banana — faster, GA
IMAGE_MODEL_FALLBACK_2 = os.getenv("IMAGE_MODEL_FALLBACK_2", "gemini-2.0-flash-preview-image-generation")  # Flash image gen — separate quota

# === Text / Reasoning ===
TEXT_MODEL = os.getenv("TEXT_MODEL", "gemini-2.5-pro")                      # Stable, GA — 3.1-pro-preview not available in all projects
TEXT_MODEL_FALLBACK = os.getenv("TEXT_MODEL_FALLBACK", "gemini-2.5-pro")    # Stable, GA

# === Live API (voice conversation) ===
LIVE_API_MODEL = os.getenv("LIVE_API_MODEL", "gemini-live-2.5-flash-native-audio")  # Vertex AI GA — native audio, function calling, 30 voices
LIVE_API_MODEL_DEV = os.getenv("LIVE_API_MODEL_DEV", "gemini-2.5-flash-native-audio-preview-12-2025")  # Dev API preview
LIVE_API_FALLBACK = os.getenv("LIVE_API_FALLBACK", "gemini-2.5-flash")      # Basic Live API, worse voice
LIVE_API_VOICE = os.getenv("LIVE_API_VOICE", "Charon")                     # Voice name for Live API (Charon, Kore, Fenrir, Aoede, Puck, etc.)
NARRATOR_VOICE = os.getenv("NARRATOR_VOICE", "Kore")                      # Voice for brand story narration (Anna/Kore — warm, polished female voice)

# Storage
UPLOAD_BUCKET = os.getenv("UPLOAD_BUCKET", f"bb-uploads-{GCP_PROJECT}")
ASSETS_BUCKET = os.getenv("ASSETS_BUCKET", f"bb-assets-{GCP_PROJECT}")

# Session
SESSION_TIMEOUT_SEC = int(os.getenv("SESSION_TIMEOUT_SEC", "900"))
SESSION_WARNING_SEC = int(os.getenv("SESSION_WARNING_SEC", "240"))

# Local storage
LOCAL_ASSETS_DIR = os.getenv("LOCAL_ASSETS_DIR", "generated_assets")
USE_GCS = os.getenv("USE_GCS", "false").lower() == "true"

# Developer API fallback (when Vertex AI image gen fails completely)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
USE_DEVELOPER_API_FALLBACK = os.getenv("USE_DEVELOPER_API_FALLBACK", "true").lower() == "true"
DEVELOPER_API_IMAGE_MODEL = os.getenv("DEVELOPER_API_IMAGE_MODEL", "gemini-2.5-flash-image")

# Debug mode: skip Vertex AI entirely for images, go straight to Developer API (api_key).
# Set DEBUG_API_KEY_ONLY=true in .env when running locally without ADC credentials.
DEBUG_API_KEY_ONLY = os.getenv("DEBUG_API_KEY_ONLY", "false").lower() == "true"

# Server
PORT = int(os.getenv("PORT", "8080"))
HOST = os.getenv("HOST", "0.0.0.0")
