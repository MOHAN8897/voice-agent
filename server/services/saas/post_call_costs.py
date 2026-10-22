"""Attribute structured post-call API responses without sharing state across calls."""
from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

_call: ContextVar[str | None] = ContextVar("post_call_cost_call", default=None)
logger = logging.getLogger(__name__)


@contextmanager
def capture_post_call_cost(call_id: str):
    token = _call.set(call_id)
    try:
        yield
    finally:
        _call.reset(token)


async def record_post_call_response(response, model: str) -> None:
    call_id = _call.get()
    if not call_id:
        return
    from server.call.call_ledger import call_ledger
    from server.services.usage_pricing import cost_llm_usd, resolve_fx_rate_inr
    try:
        raw = getattr(response, "usage", None)
        usage = raw if isinstance(raw, dict) else raw.model_dump() if raw is not None else {}
        if usage.get("input_tokens") is None or usage.get("output_tokens") is None:
            logger.warning("[BILLING] post-call response has no usage call=%s", call_id)
            return
        details = usage.get("input_tokens_details") or {}
        tokens = {"input_tokens": int(usage["input_tokens"]), "output_tokens": int(usage["output_tokens"]),
            "cached_tokens": int(details.get("cached_tokens") or 0), "cache_write_tokens": int(details.get("cache_write_tokens") or 0)}
        cost = cost_llm_usd(llm_model=model, **tokens)["total_usd"]
        meta = call_ledger.read_meta(call_id)
        if not meta:
            return
        fx = float((await asyncio.to_thread(resolve_fx_rate_inr, preferred=(meta.get("usage") or {}).get("fx_rate_inr")))["rate"])
        meta = call_ledger.read_meta(call_id)
        stored = meta.setdefault("usage", {})
        events = stored.setdefault("post_call_analysis_responses", {})
        response_id = str(getattr(response, "id", None) or uuid.uuid4())
        if response_id in events:
            return
        events[response_id] = {**tokens, "model": model, "cost_usd": cost}
        stored["post_call_analysis_usd"] = sum(item["cost_usd"] for item in events.values())
        stored["post_call_analysis_inr"] = stored["post_call_analysis_usd"] * fx
        call_ledger.write_meta(call_id, meta)
        if meta.get("ended_at"):
            call_ledger.stamp_ended_usage(call_id, reason=meta.get("end_reason") or "ended", duration_sec=meta.get("duration_sec", 0))
    except Exception as exc:
        # Accounting trouble must never retry a successfully billed generation.
        logger.error("[BILLING] post-call usage persistence failed call=%s kind=%s", call_id, type(exc).__name__)
