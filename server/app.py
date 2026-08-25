"""
FastAPI app — server/app.py
Serves API + static client. Fail-fast config validation.
"""
from __future__ import annotations

import traceback
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from server.config.constants import constants
from server.config.env import ConfigError, get_settings, validate_env
from server.routes.health import router as health_router
from server.routes.metrics import router as metrics_router
from server.routes.session_control import router as session_router
from server.routes.settings import router as settings_router
from server.routes.stt import router as stt_router
from server.routes.brain import router as brain_router
from server.routes.tts import router as tts_router
from server.routes.voice import router as voice_router
from server.routes.instructions import router as instructions_router
from server.routes.providers import router as providers_router
from server.routes.agents import router as agents_router
from server.routes.platform_brain import router as platform_brain_router
from server.routes.agents_business_brain import router as agents_business_brain_router
from server.routes.benchmarks import router as benchmarks_router
from server.routes.ws import router as ws_router
from server.routes.calls import router as calls_router
from server.routes.auth import router as auth_router
from server.routes.dev_stack import router as dev_stack_router
from server.routes.dev_environment import router as dev_environment_router
from server.routes.dev_audit import router as dev_audit_router
from server.routes.dev_compiled import router as dev_compiled_router
from server.routes.dev_plivo import router as dev_plivo_router
from server.routes.plivo import router as plivo_router
from server.routes.plivo_ws import router as plivo_ws_router
from server.routes.campaigns import router as campaigns_router
from starlette.middleware.base import BaseHTTPMiddleware

from server.utils.errors import AppError
from server.utils.logger import log_error, logger, set_level
from server.utils.metrics import metrics
from server.utils.rate_limiter import rate_limiter, tts_limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: validate env (fail-safe — keep server up so /api/health explains)
    try:
        settings = validate_env()
        set_level(settings.log_level)
        from server.agent.conversation_manager import conversation_manager
        conversation_manager.max_messages = settings.max_context_messages * 2
        conversation_manager.max_assistant_chars = settings.max_history_assistant_chars
        conversation_manager.max_user_chars = settings.max_history_user_chars
        logger.info(
            f"[VOICE] Server starting — version {constants.APP_VERSION}, "
            f"model {settings.openai_model}, stt {settings.sarvam_stt_model}"
        )
        from server.providers import init_provider_registry

        init_provider_registry(settings)
        logger.info("[VOICE] Provider registry initialized")
        try:
            from server.db import init_db
            from server.db.seed import ensure_default_tenant

            if await init_db():
                await ensure_default_tenant()
                try:
                    from server.db.tier_store import load_tier_cache

                    n = await load_tier_cache()
                    if n:
                        logger.info(f"[VOICE] Tier cache loaded ({n} rows)")
                except Exception as e:
                    logger.warning(f"[VOICE] Tier cache load skipped: {e}")
                logger.info("[VOICE] PostgreSQL connected")
            else:
                logger.info("[VOICE] PostgreSQL not configured (DATABASE_URL unset)")
        except Exception as e:
            logger.warning(f"[VOICE] PostgreSQL init skipped: {e}")
        try:
            from server.config.env import get_settings as _gs

            if _gs().use_versioned_brains:
                from server.brain.compiled_brain_service import warmup_versioned_brains

                await warmup_versioned_brains()
                logger.info("[VOICE] Versioned brains warmed")
        except Exception as e:
            logger.warning(f"[VOICE] Versioned brain warmup skipped: {e}")
        try:
            from server.call.call_lifecycle_service import call_lifecycle_service

            recovered = await call_lifecycle_service.recover_stale_calls()
            if recovered:
                logger.info(f"[VOICE] Recovered {recovered} stale calls")
        except Exception as e:
            logger.warning(f"[VOICE] Call recovery skipped: {e}")
        try:
            from server.utils.http_clients import warm_openai_client
            warm_result = await warm_openai_client()
            logger.info(f"[VOICE] OpenAI connection warm-up: {warm_result}")
        except Exception as e:
            logger.warning(f"[VOICE] OpenAI warm-up skipped: {e}")
    except ConfigError as e:
        logger.warning(f"[VOICE] Config invalid at startup: {e}. /api/health will report. Set .env and restart.")
    yield
    # Shutdown: close pooled HTTP clients
    try:
        from server.db import close_db

        await close_db()
    except Exception:
        pass
    try:
        from server.utils.http_clients import close_http_clients
        await close_http_clients()
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = PROJECT_ROOT / "client"

app = FastAPI(
    title="Telugu Voice Agent",
    version=constants.APP_VERSION,
    description="Telugu-first Voice AI — Phase 1–5: STT (saaras:v3) + Brain (Responses API) + TTS (bulbul:v3) + Custom Instructions + Hardening",
    lifespan=lifespan,
)

# CORS — allow local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Rate limiting middleware (Phase 5 hardening)


class RateLimitMiddleware(BaseHTTPMiddleware):
    _LIMITED_PATHS_TTS = ("/api/tts", "/api/voice")
    _LIMITED_PATHS_GENERAL = ("/api/brain", "/api/stt", "/api/voice", "/api/tts")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Only limit mutating API calls
        if request.method in ("POST", "PUT") and path.startswith("/api/"):
            # Call start/end must not 429 — beacon + auto-end are lifecycle, not abuse.
            if path.startswith("/api/call/"):
                return await call_next(request)
            client_ip = request.client.host if request.client else "unknown"
            # TTS/Voice stricter
            if any(path.startswith(p) for p in self._LIMITED_PATHS_TTS):
                allowed, retry_after = tts_limiter.allow(client_ip)
                if not allowed:
                    metrics.record_rate_limited()
                    return JSONResponse(
                        status_code=429,
                        content={"error": {"code": "rate_limit", "message": "Service is temporarily busy. Please try again.", "retry_after": retry_after}},
                        headers={"Retry-After": str(retry_after)},
                    )
            # General limiter
            allowed, retry_after = rate_limiter.allow(client_ip)
            if not allowed:
                metrics.record_rate_limited()
                return JSONResponse(
                    status_code=429,
                    content={"error": {"code": "rate_limit", "message": "Service is temporarily busy. Please try again.", "retry_after": retry_after}},
                    headers={"Retry-After": str(retry_after)},
                )
        return await call_next(request)


app.add_middleware(RateLimitMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """Convert raw 422s into our friendly error format + log field-level detail (no secrets)."""
    try:
        errs = exc.errors()
        first = errs[0] if errs else {}
        loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        msg = f"{loc or 'input'}: {first.get('msg', 'invalid value')}"
        if len(errs) > 1:
            msg += f" (+{len(errs)-1} more)"
        body = await request.body()
        logger.warning(f"[ERROR] Validation failed on {request.url.path}: {msg} | body_len={len(body)}")
    except Exception:
        msg = "invalid request"
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "validation_error", "message": msg, "retryable": False}},
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    log_error(f"AppError {exc.code.value}", provider=exc.provider, status=exc.status_code)
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(ConfigError)
async def config_error_handler(request: Request, exc: ConfigError):
    return JSONResponse(status_code=500, content={"error": {"code": "config_error", "message": str(exc)}})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    # Never leak stack with secrets
    logger.error(f"[ERROR] Unhandled {type(exc).__name__}: {str(exc)[:300]}")
    if get_settings().debug if _has_settings() else False:
        traceback.print_exc()
    return JSONResponse(status_code=500, content={"error": {"code": "provider_error", "message": "Internal server error"}})


def _has_settings() -> bool:
    try:
        get_settings()
        return True
    except Exception:
        return False


# Routes — Phases 1-5 (+ Fine-tune console & WebSocket proxies)
app.include_router(health_router)
app.include_router(stt_router)
app.include_router(brain_router)
app.include_router(tts_router)
app.include_router(voice_router)
app.include_router(instructions_router)
app.include_router(metrics_router)
app.include_router(session_router)
app.include_router(settings_router)
app.include_router(providers_router)
app.include_router(agents_router)
app.include_router(platform_brain_router)
app.include_router(agents_business_brain_router)
app.include_router(benchmarks_router)
app.include_router(calls_router)
app.include_router(auth_router)
app.include_router(dev_stack_router)
app.include_router(dev_environment_router)
app.include_router(dev_audit_router)
app.include_router(dev_compiled_router)
app.include_router(dev_plivo_router)
app.include_router(plivo_router)
app.include_router(plivo_ws_router)
app.include_router(campaigns_router)
app.include_router(ws_router)


@app.get("/api/meta")
async def meta():
    return {
        "version": constants.APP_VERSION,
        "phases": ["Phase 1: Foundation", "Phase 2: Brains", "Phase 3: Call lifecycle", "Phase 4: Memory", "Phase 5: Production"],
        "stt": {"url": "https://api.sarvam.ai/speech-to-text", "model": "saaras:v3", "language": "te-IN"},
        "brain": {
            "api": "OpenAI Responses API (/v1/responses)",
            "model": "see .env OPENAI_MODEL",
            "stream": "POST /api/brain/stream (SSE)",
            "effective_prompt": "GET /api/prompt/effective?sessionId=",
        },
        "tts": {"url": "https://api.sarvam.ai/text-to-speech", "model": "bulbul:v3", "language": "te-IN", "speaker": "shubh", "stream": "POST /api/tts/stream"},
        "voice": {"endpoint": "POST /api/voice/turn (multipart file → STT→Brain→TTS) returns base64 audio + metrics"},
        "hardening": {"rate_limit": "60/min general, 20/min TTS", "metrics": "GET /api/metrics", "barge_in": "POST /api/session/interrupt"},
        "realtime": {
            "stt_ws": "/ws/stt-realtime (browser PCM16 → saaras:v3-realtime, partials + VAD)",
            "tts_ws": "/ws/tts?model=bulbul:v3 (config/text/flush → base64 audio chunks)",
        },
        "finetune": {"catalog": "GET /api/settings/catalog", "runtime": "GET/POST/DELETE /api/settings/runtime", "console": "/settings.html"},
    }


def _should_serve_client() -> bool:
    try:
        return get_settings().serve_client_static
    except Exception:
        return os.getenv("SERVE_CLIENT_STATIC", "true").lower() in ("true", "1", "yes")


# Serve client static (if exists) — gated when Next.js web service is primary
if CLIENT_DIR.exists() and _should_serve_client():
    # Serve index.html at /
    @app.get("/")
    async def serve_index():
        index = CLIENT_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"message": "Client not built — API is running. See /api/health"}

    # Mount client dir for css/js
    try:
        app.mount("/client", StaticFiles(directory=str(CLIENT_DIR)), name="client")
    except Exception:
        pass

    # Also serve assets at root for relative paths (catch-all prevents future 404s)
    _CLIENT_MEDIA = {
        ".js": "application/javascript",
        ".css": "text/css",
        ".html": "text/html",
    }

    @app.get("/{asset_name}")
    async def serve_client_asset(asset_name: str):
        if ".." in asset_name or "/" in asset_name or "\\" in asset_name:
            return JSONResponse(status_code=404, content={"error": "not found"})
        p = CLIENT_DIR / asset_name
        media = _CLIENT_MEDIA.get(p.suffix.lower())
        if not media or not p.is_file():
            return JSONResponse(status_code=404, content={"error": "not found"})
        return FileResponse(str(p), media_type=media)
