"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import PORT, HOST

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("brand-agent")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Brand in a Box starting up")
    yield
    logger.info("Brand in a Box shutting down")


app = FastAPI(title="Brand in a Box", version="5.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "5.0", "vertex_ai": True}


# from routes.ws import router as ws_router
# app.include_router(ws_router)

# from routes.api import router as api_router
# app.include_router(api_router)

# app.mount("/", StaticFiles(directory="static", html=True), name="spa")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
