"""Dedicated Voice Gateway service — isolates real-time audio WebSockets from REST API load."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.config.env import get_settings
from server.db.connection import close_db, init_db
from server.routes.exotel_ws import router as exotel_ws_router
from server.routes.telnyx_ws import router as telnyx_ws_router
from server.routes.web_agent_ws import router as web_agent_ws_router
from server.utils.logger import logger


@asynccontextmanager
async def voice_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("[VOICE_APP] Voice Gateway starting up...")
    try:
        await init_db()
        logger.info("[VOICE_APP] Database connection initialized")
    except Exception as exc:
        logger.warning("[VOICE_APP] DB init skipped or failed: %s", exc)

    yield

    logger.info("[VOICE_APP] Voice Gateway shutting down...")
    try:
        await close_db()
    except Exception:
        pass


app = FastAPI(
    title="Voxly Voice Gateway",
    description="Dedicated real-time audio WebSocket gateway",
    lifespan=voice_lifespan,
)

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Voice WebSocket Routers
app.include_router(telnyx_ws_router)
app.include_router(exotel_ws_router)
app.include_router(web_agent_ws_router)


@app.get("/api/health")
async def voice_health():
    """Health check endpoint for Railway container routing."""
    return {
        "ok": True,
        "service": "voice_gateway",
        "websocket_routes": ["/ws/telnyx-stream", "/ws/exotel", "/ws/web-agent"],
    }
