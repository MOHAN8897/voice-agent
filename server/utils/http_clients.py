"""
Shared async HTTP clients — connection reuse for lower latency per request.
"""
from __future__ import annotations

import httpx
from openai import AsyncOpenAI

from server.config.env import get_settings

_openai_client: AsyncOpenAI | None = None
_sarvam_client: httpx.AsyncClient | None = None


def get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        settings = get_settings()
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


def get_sarvam_client() -> httpx.AsyncClient:
    global _sarvam_client
    if _sarvam_client is None:
        settings = get_settings()
        timeout_s = max(5.0, settings.request_timeout_ms / 1000)
        _sarvam_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s, connect=10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _sarvam_client


async def close_http_clients() -> None:
    global _openai_client, _sarvam_client
    if _sarvam_client is not None:
        await _sarvam_client.aclose()
        _sarvam_client = None
    _openai_client = None


async def warm_openai_client() -> dict:
    """
    Establish TLS + HTTP connection pool on startup so first user turn is faster.
    Does not affect prompt cache — no brain request is sent.
    """
    settings = get_settings()
    if not settings.openai_api_key:
        return {"warmed": False, "reason": "no_api_key"}
    client = get_openai_client()
    t0 = __import__("time").perf_counter()
    try:
        await client.models.list()
        ms = round((__import__("time").perf_counter() - t0) * 1000)
        return {"warmed": True, "ms": ms}
    except Exception as e:
        return {"warmed": False, "reason": str(e)[:200]}
