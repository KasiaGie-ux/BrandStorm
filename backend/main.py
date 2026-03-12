"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")  # load .env from project root

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import PORT, HOST

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("brand-agent")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("BrandStorm starting up")
    yield
    logger.info("BrandStorm shutting down")


app = FastAPI(title="BrandStorm", version="5.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routes ---
from routes.ws import router as ws_router
app.include_router(ws_router)

from routes.api import router as api_router
app.include_router(api_router)

# --- Static SPA (React build) ---
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="spa")


if __name__ == "__main__":
    import uvicorn
    import sys
    use_reload = "--no-reload" not in sys.argv
    uvicorn.run("main:app", host=HOST, port=PORT, reload=use_reload)
