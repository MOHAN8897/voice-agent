"""PSTN Realtime audio E2E loop — Telnyx PCM ↔ OpenAI Realtime mini speech-to-speech."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import time
import uuid
import weakref
from functools import wraps
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from server.call.call_controller import AgentAction, CallAction, CallLifecycleController, CallState
from server.call.end_call_validate import (
    caller_asked_to_record_details,
    caller_firm_refusal,
    caller_requested_callback,
    caller_requested_hangup,
    looks_like_bare_name,
    validate_end_call,
)
from server.call.hangup_judge import (
    caller_declines_more_help,
    caller_wants_to_continue,
    caller_withdrew_callback,
    is_generic_inbound_greeting,
    user_short_close_ack,
)
from server.realtime.hangup_tools import LIVE_HANGUP_TOOL_NAMES, parse_live_hangup_tool
from server.realtime.models import (
    REALTIME_PCM_RATE,
    realtime_voice_config,
    resolve_realtime_voice_max_output_tokens,
    resolve_realtime_voice_model,
)
from server.realtime.voice_instructions import build_realtime_voice_instructions
from server.services.audio_transcode import StreamingPcmResampler, pcm16_to_mulaw
from server.services.echo_guard import is_likely_echo
from server.services.pstn_debug import log_pstn
from server.services.pstn_media_flow import pstn_media_flow
from server.services.pstn_text_chunker import extract_opening_greeting, extract_prewarm_greeting
from server.services.pstn_voice_core import (
    PHASE_CLOSING,
    PHASE_ENDED,
    PHASE_INTRO,
    PHASE_LISTENING,
    PHASE_SPEAKING,
    PSTN_AEC_QUIET_CLOSE_FRAMES,
    TELNYX_PCM_SAMPLE_RATE,
)

# Telnyx already separates inbound/outbound tracks; this gate only filters
# residual handset acoustic echo. Echo of our own greeting sits ~500–1400 RMS
# on some handsets — that must not PROVIDER_CLEAR live audio.
REALTIME_AEC_ENERGY_MIN = 1600
REALTIME_AEC_LOUD_OPEN_FRAMES = 2
# Callee "hello" is quieter than barge. Keep pickup detection below the echo floor
# so listen-first still starts the cached greeting without waiting for remote VAD.
REALTIME_PICKUP_ENERGY_MIN = 500
_PICKUP_MIN_SPEECH_MS = 300.0
_PICKUP_MIN_SPEECH_FAST_MS = 80.0
_PICKUP_QUIET_MS = 120.0
_PICKUP_DIP_RESET_MS = 200.0
_PICKUP_VAD_DEBOUNCE_SEC = 0.28
_PICKUP_VAD_FAST_DEBOUNCE_SEC = 0.12
_PICKUP_FALLBACK_SEC = 0.45
_PENDING_INBOUND_MAX_BYTES = 16000 * 2 * 2
_BARGE_HOLD_SEC = 2.5
_PICKUP_SUPPRESS_SEC = 1.8
# After a spoken farewell, keep the line open this long so a late "wait" / "I'm here" can cancel hangup.
CLOSE_LISTEN_SEC = 3.5
# Cost-optimized hangup: brief post-farewell wait, then Telnyx + Live teardown (no long listen).
FAST_REFUSAL_POST_FAREWELL_SEC = 0.45
FAST_GOAL_COMPLETE_POST_FAREWELL_SEC = 2.0
HANGUP_RESPONSE_TIMEOUT_SEC = 6.0
PENDING_HANGUP_STUCK_SEC = 8.0
_BACKGROUND_HANGUP_TASKS: set[asyncio.Task] = set()


def _transcription_policy_for_stack(stack: dict[str, Any] | None):
    from server.services.transcription_policy import transcription_policy_from_stack

    return transcription_policy_from_stack(stack)

# Later hello / are-you-there after the intro is an availability check, not a new opening.
_SIMPLE_HELLO_RE = re.compile(
    r"^(?:hello|hallo|hi+|hey|ഹലോ|హలో|हेलो|हैलो|नमस्ते)[.!?]*\s*$",
    re.I | re.UNICODE,
)
_AVAILABILITY_RE = re.compile(
    r"^(?:"
    r"(?:hello|hallo|hi+|hey)(?:\s+\w+){0,3}[.!?]*|"
    r"are you (?:still\s+)?(?:there|here)\??|"
    r"(?:you|u) (?:there|here)\??|"
    r"can you hear me\??|"
    r"ഹലో[.!?]*|హలో[.!?]*|हेलो[.!?]*|हैलो[.!?]*|नमस्ते[.!?]*"
    r")\s*$",
    re.I | re.UNICODE,
)
_PICKUP_RE = re.compile(
    r"^(?:(?:yes|yeah|ya|ok|okay|hai)[,.\s]+)?"
    r"(?:hello|hallo|hi+|hey|ഹലോ|హలో)[.!?]*$",
    re.I | re.UNICODE,
)
# Caller confirming they are still on the line (after farewell or "are you still there?").
_PRESENCE_RE = re.compile(
    r"^(?:"
    r"(?:(?:yes|yeah|yep|ya|ok|okay|hai)[,.\s]+)?"
    r"(?:"
    r"i(?:['’]?m| am) (?:still )?(?:here|there|listening)|"
    r"still (?:here|there)|"
    r"(?:hello|hallo|hi+|hey)|"
    r"wait(?: a (?:sec(?:ond)?|minute|moment))?|"
    r"hold on(?: a (?:sec(?:ond)?|minute|moment))?|"
    r"one (?:sec(?:ond)?|minute|moment)|"
    r"go ahead|"
    r"i(?:['’]?m| am) (?:still )?on the line"
    r")|"
    r"నేను\s*(?:ఇక్కడ\s*)?ఉన్నా(?:ను)?|"
    r"ఇక్కడ\s*ఉన్నా(?:ను)?|"
    r"వినిపిస్తోంది|"
    r"మాట్లాడు|"
    r"मैं\s*(?:यहाँ\s*|यहां\s*)?(?:हूँ|हूं|है)|"
    r"हाँ\s*(?:सुन\s*रहा|हूँ|हूं)|"
    r"हां\s*(?:सुन\s*रहा|हूँ|हूं)"
    r")[.!?]*$",
    re.I | re.UNICODE,
)
_SILENCE_PROMPT_ACK_RE = re.compile(
    r"^(?:yes|yeah|yep|ya|yup|ok|okay|hai)[.!?]*$",
    re.I,
)
# Arabic / Persian / Urdu / Thai / Hangul / CJK with no Latin or Indic — overlap STT junk.
_FOREIGN_SCRIPT_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF"
    r"\u0E00-\u0E7F\uAC00-\uD7AF\u3040-\u30FF\u4E00-\u9FFF]"
)
_LATIN_OR_INDIC_RE = re.compile(
    r"[A-Za-z\u0900-\u097F\u0A80-\u0D7F]"
)
_REJECTED_END_CALL_FOLLOWUP = (
    "Stay on the line. Confirm or answer what they just said in one short sentence. "
    "Do not re-introduce yourself. Do not call end_call this turn."
)
_AVAILABILITY_FOLLOWUP = (
    "The caller is checking you are still on the line. "
    "Say only that you are here, then continue the current topic. "
    "Do not re-introduce yourself or restart the opening."
)
_STILL_ON_LINE_FOLLOWUP = (
    "The caller is still on the line. Acknowledge once that you heard them, "
    "then continue the previous topic. Do not hang up, do not say goodbye, "
    "and do not ask if they are still there."
)
_UNCLEAR_NAME_FOLLOWUP = (
    "The last thing they said was their name, but it was unclear. "
    "Ask them to repeat their name only. Do not invent a name or a messaging app. "
    "Do not re-introduce yourself."
)


def _is_simple_hello(text: str) -> bool:
    return bool(_SIMPLE_HELLO_RE.fullmatch((text or "").strip()))


def _is_availability_check(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 80:
        return False
    if re.search(r"\bwho\b", t, flags=re.I):
        return False
    return _is_simple_hello(t) or bool(_AVAILABILITY_RE.fullmatch(t))


def _is_pickup_phrase(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return _is_simple_hello(t) or bool(_PICKUP_RE.fullmatch(t)) or _is_availability_check(t)


def _is_line_check(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(
        re.fullmatch(
            r"(?:are you (?:still\s+)?(?:there|here)|(?:you|u) (?:there|here)|can you hear me)\??",
            t,
            flags=re.I,
        )
    )


def _is_presence_reply(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 80:
        return False
    return bool(_PRESENCE_RE.fullmatch(t))


def _is_silence_prompt_ack(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_SILENCE_PROMPT_ACK_RE.fullmatch(t)) or _is_presence_reply(t)


def _is_foreign_script_junk(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_FOREIGN_SCRIPT_RE.search(t) and not _LATIN_OR_INDIC_RE.search(t))

logger = logging.getLogger(__name__)

OnAgentWire = Callable[[bytes], Awaitable[None]]


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _existing_adapter_instructions(adapter: Any) -> str:
    text = str(getattr(adapter, "instructions", "") or "").strip()
    if text:
        return text
    session = getattr(adapter, "last_session", None)
    if isinstance(session, dict):
        return str(session.get("instructions") or "").strip()
    return ""


def _realtime_usage_fingerprint(
    *,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    cache_write: int,
    input_audio: int,
    output_audio: int,
    cached_audio: int,
    input_image: int,
) -> str:
    return (
        f"{input_tokens}:{output_tokens}:{cached_tokens}:{cache_write}:"
        f"{input_audio}:{output_audio}:{cached_audio}:{input_image}"
    )


_usage_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


def _usage_transcription_model(call_id: str | None, llm_model: str, gemini_live: bool) -> str:
    from server.call.call_ledger import call_ledger
    from server.services.transcription_policy import transcription_policy_from_meta

    meta = call_ledger.read_meta(call_id) if call_id else {}
    policy = transcription_policy_from_meta(meta if isinstance(meta, dict) else None)
    if policy.post_call_enabled and gemini_live:
        return policy.post_call_model
    if policy.live_enabled:
        return policy.live_model
    return llm_model if gemini_live else "gpt-4o-mini-transcribe"


def _usage_transcription_billing(call_id: str | None, llm_model: str, gemini_live: bool) -> str:
    from server.call.call_ledger import call_ledger
    from server.services.transcription_policy import transcription_policy_from_meta

    meta = call_ledger.read_meta(call_id) if call_id else {}
    policy = transcription_policy_from_meta(meta if isinstance(meta, dict) else None)
    live = policy.live_enabled
    post = policy.post_call_enabled and gemini_live
    if post:
        return "post_call_gemini_transcribe"
    if live:
        return "live_openai_transcribe"
    if gemini_live:
        return "none"
    return "separate_not_metered"


def _serialize_call_usage(fn):
    @wraps(fn)
    async def wrapped(*args, **kwargs):
        key = str(kwargs.get("call_id") or "")
        lock = _usage_locks.setdefault(key, asyncio.Lock())
        async with lock:
            return await fn(*args, **kwargs)
    return wrapped


@_serialize_call_usage
async def record_realtime_voice_usage(
    *,
    call_id: str | None,
    usage: dict[str, Any],
    llm_model: str,
    user_text: str = "",
    assistant_text: str = "",
    started_at: float | None = None,
    prewarm: bool = False,
) -> dict[str, Any] | None:
    """Persist realtime usage + USD/INR cost onto the call ledger."""
    if not call_id:
        return None
    from server.call.call_ledger import call_ledger
    from server.config.env import get_settings
    from server.realtime.models import is_gemini_live_voice_model
    from server.realtime.usage import extract_realtime_usage
    from server.services.usage_pricing import estimate_turn_cost, resolve_fx_rate_inr

    normalized = extract_realtime_usage({"usage": usage}) if usage else {}
    input_tokens = int(normalized.get("input_tokens") or usage.get("input_tokens") or 0)
    output_tokens = int(normalized.get("output_tokens") or usage.get("output_tokens") or 0)
    cached_tokens = int(normalized.get("cached_tokens") or usage.get("cached_tokens") or 0)
    cache_write = int(normalized.get("cache_write_tokens") or usage.get("cache_write_tokens") or 0)
    input_audio = int(normalized.get("input_audio_tokens") or usage.get("input_audio_tokens") or 0)
    output_audio = int(normalized.get("output_audio_tokens") or usage.get("output_audio_tokens") or 0)
    cached_audio = int(normalized.get("cached_audio_tokens") or usage.get("cached_audio_tokens") or 0)
    input_image = int(normalized.get("input_image_tokens") or usage.get("input_image_tokens") or 0)
    if not any((input_tokens, output_tokens, input_audio, output_audio, input_image)):
        return None
    fingerprint = _realtime_usage_fingerprint(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        cache_write=cache_write,
        input_audio=input_audio,
        output_audio=output_audio,
        cached_audio=cached_audio,
        input_image=input_image,
    )
    meta = call_ledger.read_meta(call_id)
    prev = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
    usage_id = str(usage.get("usage_id") or "")
    response_snapshot = usage.get("usage_scope") == "response" and bool(usage_id)
    gemini_live = is_gemini_live_voice_model(llm_model)
    # Gemini Live usage_metadata is session-cumulative; usage_id only dedupes retries.
    session_snapshot = gemini_live and not prewarm
    snapshots = dict(prev.get("response_usage") or {})
    prior_snapshot = snapshots.get(usage_id, {}) if response_snapshot else {}
    if response_snapshot and prior_snapshot.get("fingerprint") == fingerprint:
        return None
    # Gemini Live may emit the same session-cumulative fingerprint on usage_only trailers
    # and on response_done — dedupe globally, not only per usage_id.
    if gemini_live and not prewarm and str(prev.get("usage_fingerprint") or "") == fingerprint:
        return None
    fx_info = resolve_fx_rate_inr(preferred=prev.get("fx_rate_inr") if prev else None)
    fx = float(fx_info["rate"])
    cost = estimate_turn_cost(
        stt_audio_sec=0,
        tts_chars=0,
        tts_provider="openai",
        llm_model=llm_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        cache_write_tokens=cache_write,
        fx_rate_inr=fx,
        input_audio_tokens=input_audio,
        output_audio_tokens=output_audio,
        cached_audio_tokens=cached_audio,
        input_image_tokens=input_image,
    )
    component_keys = ("uncached_usd", "cached_usd", "cache_write_usd", "output_usd",
                      "audio_input_usd", "audio_output_usd", "image_input_usd")
    previous_parts = prev.get("cost_breakdown_usd") or {}
    prewarm_parts = dict(prev.get("prewarm_cost_breakdown_usd") or {})
    seq = int(prev.get("turns") or 0) + 1
    duration_sec = max(0.0, time.monotonic() - started_at) if started_at else 0.0
    minutes = duration_sec / 60.0 if duration_sec > 0 else 0.0
    prewarm_in = int(prev.get("prewarm_input_tokens") or 0)
    prewarm_out = int(prev.get("prewarm_output_tokens") or 0)
    prewarm_audio_in = int(prev.get("prewarm_input_audio_tokens") or 0)
    prewarm_audio_out = int(prev.get("prewarm_output_audio_tokens") or 0)
    prewarm_image = int(prev.get("prewarm_input_image_tokens") or 0)
    prewarm_usd = float(prev.get("prewarm_cost_usd") or 0)
    prewarm_inr = float(prev.get("prewarm_cost_inr") or 0)
    if response_snapshot and not session_snapshot:
        # Live metadata describes a generation request, not the entire call.
        # Deduplicate trailers by response identity, never by token counts alone.
        values = {"input_tokens": input_tokens, "output_tokens": output_tokens,
                  "input_audio_tokens": input_audio, "output_audio_tokens": output_audio,
                  "cached_tokens": cached_tokens, "cached_audio_tokens": cached_audio,
                  "input_image_tokens": input_image, "cache_write_tokens": cache_write}
        snapshots[usage_id] = {**values, "fingerprint": fingerprint,
                               "cost_usd": float(cost["total_usd"]), "cost_inr": float(cost["total_inr"]),
                               "cost_breakdown_usd": cost["llm"]}
        input_tokens = max(0, input_tokens - int(prior_snapshot.get("input_tokens", 0)))
        output_tokens = max(0, output_tokens - int(prior_snapshot.get("output_tokens", 0)))
        input_audio = max(0, input_audio - int(prior_snapshot.get("input_audio_tokens", 0)))
        output_audio = max(0, output_audio - int(prior_snapshot.get("output_audio_tokens", 0)))
        cached_tokens = max(0, cached_tokens - int(prior_snapshot.get("cached_tokens", 0)))
        cached_audio = max(0, cached_audio - int(prior_snapshot.get("cached_audio_tokens", 0)))
        input_image = max(0, input_image - int(prior_snapshot.get("input_image_tokens", 0)))
        cache_write = max(0, cache_write - int(prior_snapshot.get("cache_write_tokens", 0)))
        cost["total_usd"] = max(0.0, float(cost["total_usd"]) - float(prior_snapshot.get("cost_usd", 0)))
        cost["total_inr"] = max(0.0, float(cost["total_inr"]) - float(prior_snapshot.get("cost_inr", 0)))
    elif response_snapshot and session_snapshot:
        snapshots[usage_id] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "input_audio_tokens": input_audio,
            "output_audio_tokens": output_audio,
            "cached_tokens": cached_tokens,
            "cached_audio_tokens": cached_audio,
            "input_image_tokens": input_image,
            "cache_write_tokens": cache_write,
            "fingerprint": fingerprint,
            "cost_usd": float(cost["total_usd"]),
            "cost_inr": float(cost["total_inr"]),
        }
    if session_snapshot:
        tot_in = input_tokens + prewarm_in
        tot_out = output_tokens + prewarm_out
        tot_audio_in = input_audio + prewarm_audio_in
        tot_audio_out = output_audio + prewarm_audio_out
        tot_cached = cached_tokens
        tot_cached_audio = cached_audio
        tot_image = input_image + prewarm_image
        total_usd = float(cost["total_usd"]) + prewarm_usd
        total_inr = float(cost["total_inr"]) + prewarm_inr
        prev_model_usd = float(
            prev.get("model_cost_usd")
            if prev.get("model_cost_usd") is not None
            else prev.get("cost_usd") or 0
        )
        prev_model_inr = float(
            prev.get("model_cost_inr")
            if prev.get("model_cost_inr") is not None
            else prev.get("cost_inr") or 0
        )
        delta_usd = max(0.0, total_usd - prev_model_usd)
        delta_inr = max(0.0, total_inr - prev_model_inr)
        if (
            delta_usd < 1e-12
            and delta_inr < 1e-12
            and tot_in == int(prev.get("input_tokens") or 0)
            and tot_out == int(prev.get("output_tokens") or 0)
        ):
            return None
    else:
        tot_in = int(prev.get("input_tokens") or 0) + input_tokens
        tot_out = int(prev.get("output_tokens") or 0) + output_tokens
        tot_audio_in = int(prev.get("input_audio_tokens") or 0) + input_audio
        tot_audio_out = int(prev.get("output_audio_tokens") or 0) + output_audio
        tot_cached = int(prev.get("cached_tokens") or 0) + cached_tokens
        tot_cached_audio = int(prev.get("cached_audio_tokens") or 0) + cached_audio
        tot_image = int(prev.get("input_image_tokens") or 0) + input_image
        total_usd = float(prev.get("cost_usd") or 0) + float(cost["total_usd"])
        total_inr = float(prev.get("cost_inr") or 0) + float(cost["total_inr"])
        delta_usd = float(cost["total_usd"])
        delta_inr = float(cost["total_inr"])
    if prewarm:
        prewarm_in += input_tokens
        prewarm_out += output_tokens
        prewarm_audio_in += input_audio
        prewarm_audio_out += output_audio
        prewarm_image += input_image
        prewarm_usd += float(cost["total_usd"])
        prewarm_inr += float(cost["total_inr"])
    if session_snapshot:
        cost_parts = {k: float(cost["llm"].get(k, 0)) + float(prewarm_parts.get(k, 0)) for k in component_keys}
    elif response_snapshot:
        cost_parts = {k: float(previous_parts.get(k, 0)) + float(cost["llm"].get(k, 0))
                      - float(prior_snapshot.get("cost_breakdown_usd", {}).get(k, 0)) for k in component_keys}
    else:
        cost_parts = {k: float(previous_parts.get(k, 0)) + float(cost["llm"].get(k, 0)) for k in component_keys}
    if prewarm:
        prewarm_parts = {k: float(prewarm_parts.get(k, 0)) + float(cost["llm"].get(k, 0)) for k in component_keys}
    model_per_min_usd = (total_usd / minutes) if minutes > 0 else 0.0
    model_per_min_inr = (total_inr / minutes) if minutes > 0 else 0.0
    turn = {
        "turn": seq,
        "user_text": user_text,
        "assistant_text": assistant_text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "cache_write_tokens": cache_write,
        "input_audio_tokens": input_audio,
        "output_audio_tokens": output_audio,
        "cached_audio_tokens": cached_audio,
        "input_image_tokens": input_image,
        "stt_final_ms": None,
        "llm_ttft_ms": None,
        "tts_first_audio_ms": None,
        "e2e_ms": None,
        "cost_usd": delta_usd,
        "cost_inr": delta_inr,
        "llm_usd": delta_usd,
        "pipeline": "realtime_voice",
        "llm_model": llm_model,
        "errors": [],
        "usage_event": seq,
        "token_scope": "delta",
    }
    if session_snapshot:
        for key, total in (("input_tokens", tot_in), ("output_tokens", tot_out),
                           ("input_audio_tokens", tot_audio_in), ("output_audio_tokens", tot_audio_out),
                           ("cached_tokens", tot_cached), ("cached_audio_tokens", tot_cached_audio),
                           ("input_image_tokens", tot_image)):
            turn[key] = max(0, total - int(prev.get(key) or 0))
    await call_ledger.append_trace_turn(call_id, turn)
    meta["usage"] = {
        "pipeline": "realtime_voice",
        "llm_model": llm_model,
        "input_tokens": tot_in,
        "output_tokens": tot_out,
        "input_audio_tokens": tot_audio_in,
        "output_audio_tokens": tot_audio_out,
        "input_image_tokens": tot_image,
        "cached_tokens": tot_cached,
        "cached_audio_tokens": tot_cached_audio,
        "turns": seq,
        "usage_events": seq,
        "dialog_turns": sum(1 for row in call_ledger.read_lines(call_id) if row.get("role") == "assistant"),
        "cost_is_estimate": True,
        "response_usage": snapshots,
        "cost_usd": total_usd,
        "cost_inr": total_inr,
        "cost_breakdown_usd": cost_parts,
        "prewarm_cost_breakdown_usd": prewarm_parts,
        "transcription_model": _usage_transcription_model(call_id, llm_model, gemini_live),
        "transcription_billing": _usage_transcription_billing(call_id, llm_model, gemini_live),
        "model_cost_usd": total_usd,
        "model_cost_inr": total_inr,
        "duration_sec": round(duration_sec, 3),
        "cost_usd_per_min": model_per_min_usd,
        "cost_inr_per_min": model_per_min_inr,
        "model_cost_usd_per_min": model_per_min_usd,
        "model_cost_inr_per_min": model_per_min_inr,
        "fx_rate_inr": fx,
        "fx_source": fx_info.get("source"),
        "fx_as_of": fx_info.get("as_of"),
        "gst_inr": 0.0,
        "usage_fingerprint": fingerprint,
        "prewarm_input_tokens": prewarm_in,
        "prewarm_output_tokens": prewarm_out,
        "prewarm_input_audio_tokens": prewarm_audio_in,
        "prewarm_output_audio_tokens": prewarm_audio_out,
        "prewarm_input_image_tokens": prewarm_image,
        "prewarm_cost_usd": prewarm_usd,
        "prewarm_cost_inr": prewarm_inr,
    }
    if gemini_live:
        meta["usage"]["gemini_billing"] = "session_cumulative_tokens"
        meta["usage"]["gemini_billing_note"] = (
            "Live API usage_metadata is session-cumulative; each event bills text+audio+image "
            "tokens (including re-billed context), not wall-clock minutes of speech."
        )
    call_ledger.write_meta(call_id, meta)
    return turn


class PstnRealtimeVoiceLoop:
    """Drop-in voice-loop surface for Telnyx/Exotel/Plivo without Sarvam STT/TTS."""

    def __init__(
        self,
        *,
        session_id: str,
        call_id: str | None,
        on_agent_wire: OnAgentWire,
        sample_rate: int = 8000,
        tts_session_id: str | None = None,
        config_session_id: str | None = None,
        tts_output_codec: str = "mulaw",
        is_agent_audio_active: Callable[[], bool] | None = None,
        playback: Any | None = None,
        stack_override: dict[str, Any] | None = None,
        adapter: Any | None = None,
        tenant_id: str | None = None,
        agent_id: str | None = None,
        agent_tools: set[str] | list[str] | None = None,
    ) -> None:
        self.session_id = session_id
        self.call_id = call_id
        self.config_session_id = config_session_id
        self.tts_session_id = tts_session_id or session_id
        self.on_agent_wire = on_agent_wire
        self.sample_rate = int(sample_rate)
        self.tts_output_codec = tts_output_codec
        self.is_agent_audio_active = is_agent_audio_active
        self.playback = playback
        self.stack_override = stack_override or {}
        self._tenant_id = tenant_id or (self.stack_override.get("tenant_id") if self.stack_override else None)
        self._agent_id = agent_id or (self.stack_override.get("agent_id") if self.stack_override else None)
        self._agent_tools = set(agent_tools) if agent_tools else set()
        self._injected_adapter = adapter
        self._adapter: Any | None = adapter
        self._hold_inbound = True
        self._pending_inbound: list[bytes] = []
        self._pending_inbound_bytes = 0
        self._pump_task: asyncio.Task | None = None
        self._closed = False
        self._call_started = False
        self._phase = PHASE_LISTENING
        self._tts_active = False
        self._active_tts_session = None
        self._on_barge: Callable[[], Awaitable[None]] | None = None
        self._on_remote_hangup: Callable[[], Awaitable[None]] | None = None
        self._on_hangup_notice: Callable[[str, str], Awaitable[None] | None] | None = None
        self._on_turn_audio_done: Callable[[], Awaitable[None]] | None = None
        self._hangup_notice_sent = False
        self.current_turn_id: str | None = None
        self.current_generation_id: str | None = None
        self._barge_generation: str | None = None
        self.current_output_codec = "L16" if self.sample_rate >= TELNYX_PCM_SAMPLE_RATE else "PCMU"
        self._in_resampler = StreamingPcmResampler(self.sample_rate, REALTIME_PCM_RATE)
        self._out_resampler = StreamingPcmResampler(REALTIME_PCM_RATE, self.sample_rate)
        self._out_pcm = bytearray()
        self._wire_frames_out = 0
        self._user_partial = ""
        self._last_user_final_text = ""
        self._language_user_turn = 0
        self._unarmed_close_repair_turn: int | None = None
        self._language_reminder_turn = None
        self._hangup_arm_source: str | None = None
        self._assistant_text = ""
        self._response_had_audio = False
        self._pending_end_call: dict[str, Any] | None = None
        self._pending_followup_instruction: str | None = None
        self._pending_farewell_text: str | None = None
        self._farewell_response_active = False
        self._caller_requested_close = False
        self._callback_request_text = ""
        self._callback_collecting_field: str | None = None
        self._callback_details: dict[str, str] = {}
        self._callback_close_phase = "idle"
        self._hangup_started = False
        self._stt = None
        self._live_model = ""
        self._voice_name = ""
        self._started_at: float | None = None
        self._intro_noted = False
        self._deferred_greeting_frames: list[bytes] | None = None
        self._deferred_greeting_text: str | None = None
        self._deferred_greeting_armed = False
        self._deferred_greeting_playing = False
        self._deferred_greeting_task: asyncio.Task | None = None
        self._last_ledger_assistant = ""
        self._tts_started_emitted = False
        self._aec_loud_streak = 0
        self._aec_quiet_streak = 0
        self._aec_barge_open = False
        self._agent_audio_out_since = 0.0
        self._ignored_response_ids: deque[str] = deque(maxlen=128)
        self._response_open = False
        self._suppress_until_user = False
        self._openai_response_id = ""
        self._followup_inflight = False
        self._heard_user_turn = False
        self._heard_content_turn = False
        self._barge_hold_until = 0.0
        self._pickup_suppress_until = 0.0
        self.controller = CallLifecycleController()
        self._caller_stt: Any | None = None
        self._pickup_speech_ms = 0.0
        self._pickup_quiet_ms = 0.0
        self._pickup_dip_ms = 0.0
        self._pickup_rms_logs = 0
        self._pickup_user_text = ""
        self._pickup_finish_task: asyncio.Task | None = None
        self._pickup_fallback_task: asyncio.Task | None = None
        self._backup_hangup_task: asyncio.Task | None = None
        self._greeting_protect_until = 0.0
        self._runtime_task: asyncio.Task | None = None
        self._last_activity_at = time.monotonic()
        self._silence_prompted = False
        self._awaiting_presence_reply = False
        self._resume_after_close = False
        self._close_listen_until = 0.0
        self._caller_speaking = False
        self._ending_at: float | None = None
        self._response_activity_at = time.monotonic()
        self._callback_cancellation_persisted = False
        self._spoken_reply_language: str | None = None
        self._firm_refusal_close = False
        self._hangup_armed_at: float | None = None
        self._hangup_force_task: asyncio.Task | None = None
        self._hangup_farewell_inject_tried = False
        self._fast_script_farewell = False
        self._background_hangup_task: asyncio.Task | None = None
        self._post_turn_tasks: set[asyncio.Task] = set()
        self._farewell_complete = False
        from server.services.pstn_archive_writer import PstnArchiveWriter

        self._archive = PstnArchiveWriter()

    def emission_blocked(self) -> bool:
        if self._closed or self._phase == PHASE_ENDED:
            return True
        gen = self.current_generation_id
        if self._barge_generation and gen and gen == self._barge_generation:
            return True
        if self.playback is not None and hasattr(self.playback, "is_generation_valid"):
            if gen and not self.playback.is_generation_valid(gen):
                return True
        return False

    def _promote_queued_tts_to_heard(self) -> None:
        return None

    def set_barge_handler(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_barge = fn

    def set_hangup_handler(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_remote_hangup = fn

    def set_hangup_notice_handler(self, fn: Callable[[str, str], Awaitable[None] | None]) -> None:
        self._on_hangup_notice = fn

    def _uses_fast_hangup(self) -> bool:
        if self._firm_refusal_close or self._fast_script_farewell or self._farewell_complete:
            return True
        reason = str((self._pending_end_call or {}).get("reason") or "")
        return reason in {"goal_complete", "goodbye", "firm_refusal"}

    def _caller_text(self) -> str:
        return (self._last_user_final_text or self._user_partial or "").strip()

    def _transcription_policy(self):
        if self.call_id:
            from server.call.call_ledger import call_ledger
            from server.services.transcription_policy import transcription_policy_from_meta

            meta = call_ledger.read_meta(self.call_id) or {}
            policy = transcription_policy_from_meta(meta if isinstance(meta, dict) else None)
            if policy.live_enabled or policy.post_call_enabled:
                return policy
        return _transcription_policy_for_stack(self.stack_override)

    def _persist_live_transcript_ledger(self) -> bool:
        return self._transcription_policy().persist_live_transcript_ledger(self._live_model)

    def _persist_user_turn_to_ledger(self) -> bool:
        """Ledger user lines: OpenAI live session or Gemini+sidecar; never both writers."""
        if not self._persist_live_transcript_ledger():
            return False
        return self._caller_stt is None

    def _start_caller_stt_sidecar(self, language: str, llm_provider: str) -> None:
        policy = self._transcription_policy()
        from server.realtime.models import is_gemini_live_voice_model

        if not policy.gemini_use_openai_live_stt(self._live_model) or llm_provider != "gemini":
            return
        from server.services.openai_caller_transcribe_sidecar import OpenaiCallerTranscribeSidecar

        sidecar = OpenaiCallerTranscribeSidecar(language=language, on_final=self._on_caller_stt_final)
        sidecar.start()
        self._caller_stt = sidecar
        log_pstn("realtime_voice.caller_stt.start", call_id=self.call_id, model=policy.live_model)

    async def _on_caller_stt_final(self, text: str) -> None:
        # Billing/history only — hangup and turn logic use Gemini native input_transcription.
        cleaned = (text or "").strip()
        if not cleaned or not self.call_id or not self._persist_live_transcript_ledger():
            return
        if self._should_drop_user_final(cleaned):
            return
        from server.call.call_ledger import call_ledger

        await call_ledger.append_user_turn(self.call_id, cleaned)

    async def _sync_caller_stt_usage(self) -> None:
        sec = float(self._caller_stt.billed_audio_sec or 0) if self._caller_stt else 0.0
        await self._finalize_live_transcript_usage(sidecar_sec=sec)

    async def _finalize_live_transcript_usage(self, *, sidecar_sec: float | None = None) -> None:
        if not self.call_id:
            return
        policy = self._transcription_policy()
        if not policy.live_enabled:
            return
        from server.call.call_ledger import call_ledger

        meta = call_ledger.read_meta(self.call_id) or {"call_id": self.call_id}
        usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
        usage = dict(usage)
        if float(usage.get("live_transcript_seconds") or 0) > 0:
            return
        sec = float(sidecar_sec or 0)
        if sec <= 0 and self._started_at:
            sec = max(0.0, time.monotonic() - float(self._started_at))
        if sec <= 0:
            return
        usage["live_transcript_seconds"] = sec
        usage["live_transcript_model"] = policy.live_model
        usage["transcription_billing"] = "live_openai_transcribe"
        usage["transcription_model"] = policy.live_model
        meta["usage"] = usage
        meta["transcript_source"] = f"live:{policy.live_model}"
        call_ledger.write_meta(self.call_id, meta)

    def _set_hangup_arm_source(self, source: str) -> None:
        if self._hangup_arm_source:
            return
        self._hangup_arm_source = source
        log_pstn("hangup.arm_source", call_id=self.call_id, source=source)

    def _known_end_intent(self) -> bool:
        text = self._caller_text()
        return bool(
            self._hangup_flow_active()
            or caller_requested_hangup(text)
            or caller_firm_refusal(text)
        )

    def _close_listen_sec(self) -> float:
        # Disconnect timing is transport-driven and identical for every language.
        return 0.0

    def _silence_nudge_sec(self) -> float:
        try:
            from server.config.env import get_settings

            return max(5.0, float(get_settings().pstn_silence_nudge_sec or 8.0))
        except Exception:
            return 8.0

    def _silence_hangup_sec(self) -> float:
        try:
            from server.config.env import get_settings

            nudge = self._silence_nudge_sec()
            hang = float(get_settings().pstn_silence_hangup_sec or 20.0)
            return max(nudge + 4.0, hang)
        except Exception:
            return 20.0

    def _localized_farewell(self, spoken: str | None = None) -> str:
        from server.call.hangup_judge import default_farewell_for

        text = (spoken or "").strip()
        return text or default_farewell_for(self._resolve_language())

    def _farewell_audio_engaged(self) -> bool:
        return bool(
            self._farewell_complete
            or self._response_had_audio
            or (
                self._farewell_response_active
                and self._hangup_farewell_inject_tried
                and (self._assistant_text or "").strip()
            )
        )

    async def _play_farewell_side_session(self) -> bool:
        from server.realtime.models import is_gemini_live_voice_model

        if not is_gemini_live_voice_model(self._live_model or ""):
            return False
        text = (self._pending_farewell_text or self._localized_farewell()).strip()
        if not text or self._closed:
            return False
        from server.services.pstn_realtime_greeting_prewarm import synthesize_gemini_greeting_on_side_session

        voice = str(getattr(self._adapter, "voice", "") or "")
        frames, transcript, _usage = await synthesize_gemini_greeting_on_side_session(
            greeting_text=text,
            sample_rate=self.sample_rate,
            tts_output_codec=self.tts_output_codec,
            model=self._live_model or "gemini-3.8-live",
            language=self._resolve_language(),
            voice=voice or None,
            control_id=self.call_id or self.session_id,
        )
        if not frames:
            return False
        self._farewell_response_active = True
        self._set_tts_active(True)
        try:
            for wire in frames:
                if self._closed:
                    break
                if self.call_id:
                    self._archive.enqueue(self.call_id, "agent", wire)
                self._wire_frames_out += 1
                await self.on_agent_wire(wire)
        finally:
            self._set_tts_active(False)
        spoken = (transcript or text).strip()
        if spoken:
            self._assistant_text = spoken
            self._last_ledger_assistant = spoken
        self._response_had_audio = True
        self._farewell_complete = True
        if self.call_id and spoken and self._persist_live_transcript_ledger():
            from server.call.call_ledger import call_ledger

            await call_ledger.append_assistant_turn(self.call_id, spoken)
        log_pstn("hangup.farewell.side_session", call_id=self.call_id, chars=len(spoken))
        return True

    async def _ensure_hangup_farewell_audio(self, *, prefer_side_session: bool = False) -> None:
        if self._farewell_audio_engaged() or self._hangup_started or self._closed:
            return
        text = (self._pending_farewell_text or self._localized_farewell()).strip()
        if not text:
            return
        self._farewell_response_active = True
        if prefer_side_session:
            if await self._play_farewell_side_session():
                if self._pending_end_call and not self._hangup_started:
                    await self._finish_hangup()
            return
        if self._adapter is not None and not self._hangup_farewell_inject_tried:
            self._hangup_farewell_inject_tried = True
            try:
                await self._start_injected_response(
                    f"Say exactly this farewell once in audio in {self._resolve_language()}, then stop. "
                    f"No tools, no questions.\n{text}"
                )
                return
            except Exception as exc:
                log_pstn("hangup.farewell_inject.failed", call_id=self.call_id, error=str(exc)[:160])
        if await self._play_farewell_side_session():
            if self._pending_end_call and not self._hangup_started:
                await self._finish_hangup()

    async def _notify_hangup(self, stage: str, reason: str) -> None:
        log_pstn("hangup.notice", call_id=self.call_id, stage=stage, reason=reason)
        if self._hangup_notice_sent and stage == "initiated":
            return
        if stage == "initiated":
            self._hangup_notice_sent = True
        fn = self._on_hangup_notice
        if fn is None:
            return
        try:
            result = fn(stage, reason)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            log_pstn("hangup.notice.failed", call_id=self.call_id, error=str(exc)[:160])

    async def _play_gemini_inbound_opening_if_needed(
        self,
        *,
        adapter: Any,
        opening: str,
        model: str,
        cfg: dict[str, Any],
        max_output_tokens: int | None,
        llm_provider: str,
    ) -> bool:
        """Web / inbound Gemini: side-session greeting PCM — never pollute the live session."""
        if llm_provider != "gemini" or self._resolve_direction() != "inbound":
            return False
        line = (opening or "").strip()
        if not line:
            return False
        from server.services.pstn_realtime_greeting_prewarm import synthesize_gemini_greeting_on_side_session

        auto_response = getattr(adapter, "set_auto_response", None)
        if callable(auto_response):
            try:
                await auto_response(False)
            except Exception:
                pass
        frames, transcript, usage = await synthesize_gemini_greeting_on_side_session(
            greeting_text=line,
            sample_rate=self.sample_rate,
            tts_output_codec=self.tts_output_codec,
            model=model,
            voice=str(cfg.get("voice") or ""),
            turn_detection=str(cfg.get("turn_detection") or ""),
            max_output_tokens=max_output_tokens,
            control_id=self.call_id or self.session_id,
        )
        if usage and self.call_id:
            from server.services.pstn_prewarm import record_bundle_greeting_usage
            from server.services.pstn_prewarm import PstnPrewarmBundle

            bundle = PstnPrewarmBundle(
                provider="browser",
                external_id=self.call_id,
                realtime_key="",
                greeting_text=transcript or line,
                greeting_wire_frames=list(frames),
                greeting_source="side_session",
                greeting_usage=usage,
                greeting_model=model,
            )
            await record_bundle_greeting_usage(self.call_id, bundle)
        if not frames:
            if callable(auto_response):
                try:
                    await auto_response(True)
                except Exception:
                    pass
            return False
        self._deferred_greeting_frames = list(frames)
        self._deferred_greeting_text = (transcript or line).strip()
        await self._play_deferred_greeting()
        return True

    async def speak_opening_now(self) -> None:
        """Inbound / web test: speak the scripted opening, then wait (same as answered PSTN)."""
        from server.services.pstn_text_chunker import extract_opening_greeting

        opening = extract_opening_greeting(self._compiled_brain(), self._resolve_language(), direction="inbound")
        line = (opening or "").strip()
        instruction = (
            f"Speak only this opening greeting, then wait for the caller: {line}"
            if line
            else "Speak only your opening greeting from the script, then wait for the caller."
        )
        await self._start_injected_response(instruction)

    def set_turn_audio_done_handler(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_turn_audio_done = fn

    def _set_phase(self, phase: str) -> None:
        if self._phase == PHASE_ENDED:
            return
        if self._phase == PHASE_CLOSING and phase not in (PHASE_CLOSING, PHASE_ENDED):
            if not (phase == PHASE_LISTENING and not self._hangup_started):
                return
        self._phase = phase

    def _set_tts_active(self, active: bool) -> None:
        self._tts_active = bool(active)
        if active:
            self._agent_audio_out_since = time.monotonic()

    def _agent_audio_playing(self) -> bool:
        # Transport queue + frame in flight are authoritative. Model generation
        # can remain active after the final audible frame has left the queue.
        if self.playback is not None and hasattr(self.playback, "is_active"):
            try:
                return bool(self.playback.is_active())
            except Exception:
                pass
        if self.is_agent_audio_active:
            try:
                return bool(self.is_agent_audio_active())
            except Exception:
                return False
        return self._tts_active

    def _farewell_still_on_the_line(self) -> bool:
        """Playback still leaving the phone — same drain check as the classic PSTN hangup."""
        return self._agent_audio_playing()

    def _abort_in_progress_hangup(self) -> None:
        had_close = bool(
            self._pending_end_call
            or self._close_listen_until
            or self._hangup_started
            or self._caller_requested_close
            or self._farewell_response_active
        )
        self.controller.resume()
        self._ending_at = None
        if self.call_id:
            from server.call.call_context import get as get_ctx

            ctx = get_ctx(self.call_id)
            if ctx:
                ctx.agent_hangup_armed = False
        self._hangup_started = False
        self._pending_end_call = None
        self._pending_farewell_text = None
        self._farewell_response_active = False
        self._caller_requested_close = False
        self._close_listen_until = 0.0
        self._silence_prompted = False
        self._hangup_notice_sent = False
        self._hangup_armed_at = None
        self._hangup_farewell_inject_tried = False
        self._fast_script_farewell = False
        self._firm_refusal_close = False
        self._hangup_arm_source = None
        self._farewell_complete = False
        self._cancel_hangup_force_task()
        if had_close:
            self._resume_after_close = True
        self._clear_hangup_arm()
        log_pstn("hangup.aborted_barge", call_id=self.call_id)
        self._set_phase(PHASE_LISTENING)
        if had_close:
            asyncio.create_task(self._set_live_auto_response(True))

    def _cancel_hangup_force_task(self) -> None:
        task = self._hangup_force_task
        self._hangup_force_task = None
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()

    def _schedule_hangup_force_finish(self) -> None:
        self._cancel_hangup_force_task()
        if not self._pending_end_call or self._hangup_started:
            return

        async def _force() -> None:
            try:
                # A missing response_done must not strand the call, but a gap
                # between streaming chunks is not the end of the farewell.
                await asyncio.sleep(HANGUP_RESPONSE_TIMEOUT_SEC)
            except asyncio.CancelledError:
                return
            if self._closed or self._hangup_started or not self._pending_end_call:
                return
            if not self._farewell_audio_engaged():
                await self._ensure_hangup_farewell_audio(prefer_side_session=True)
            if self._hangup_started or self._closed:
                return
            log_pstn("hangup.force_finish", call_id=self.call_id, reason="watchdog")
            self._farewell_complete = True
            await self._finish_hangup()

        self._hangup_force_task = asyncio.create_task(
            _force(),
            name=f"rt-hangup-force-{self.call_id}",
        )

    def _note_hangup_armed(self) -> None:
        if self._hangup_armed_at is None:
            self._hangup_armed_at = time.monotonic()
        self._schedule_hangup_force_finish()

    def _commit_pending_hangup(self, accepted: dict[str, Any], *, source: str) -> None:
        reason = str(accepted.get("reason") or "agent_hangup")
        self._pending_end_call = accepted
        self._pending_farewell_text = self._localized_farewell(str(accepted.get("farewell") or ""))
        self._pending_followup_instruction = None
        self._apply_hangup_close_flags(reason)
        self._set_hangup_arm_source(source)
        self._ending_at = time.monotonic()
        self.controller.state = CallState.ENDING
        self._note_hangup_armed()

    async def _repair_arm_hangup(self, accepted: dict[str, Any], *, log_event: str) -> None:
        reason = str(accepted.get("reason") or "goal_complete")
        self._commit_pending_hangup(accepted, source="repair")
        log_pstn(log_event, call_id=self.call_id)
        await self._notify_hangup("initiated", reason)

    async def _finalize_hangup_after_farewell(self) -> None:
        """Drain the completed farewell, then disconnect without a listen window."""
        spoken = (self._assistant_text or "").strip()
        pending = self._pending_end_call or {}
        reason = str(pending.get("reason") or "")
        farewell_required = bool(pending.get("farewell_required", True))
        if self._response_had_audio:
            self._farewell_response_active = False
            self._pending_followup_instruction = None
            if reason in ("goal_complete", "goodbye", "firm_refusal"):
                self._apply_hangup_close_flags(reason)
            self._farewell_complete = True
            await self._finish_hangup()
            return
        if not farewell_required and (spoken or self._response_had_audio):
            self._farewell_response_active = False
            self._farewell_complete = True
            await self._finish_hangup()
            return
        if self._hangup_farewell_inject_tried:
            if self._response_had_audio:
                self._farewell_response_active = False
                self._pending_followup_instruction = None
                if reason in ("goal_complete", "goodbye", "firm_refusal"):
                    self._apply_hangup_close_flags(reason)
                self._farewell_complete = True
                await self._finish_hangup()
                return
            # Inject finished without audio — do not disconnect; allow one more inject.
            self._hangup_farewell_inject_tried = False
        text = (self._pending_farewell_text or self._localized_farewell()).strip()
        if text and self._adapter is not None:
            self._hangup_farewell_inject_tried = True
            self._farewell_response_active = True
            self._response_had_audio = False
            self._assistant_text = ""
            try:
                await self._start_injected_response(
                    "Say this farewell once in audio in the agent language, then stop. "
                    "Do not use tools or explain your reasoning.\n"
                    f"{text}"
                )
            except Exception as exc:
                log_pstn("hangup.farewell_inject.failed", call_id=self.call_id, error=str(exc)[:160])
                self._farewell_complete = True
                await self._finish_hangup()
            return
        self._farewell_complete = True
        await self._finish_hangup()

    def _begin_close_listen(self) -> None:
        """Farewell is done — wait for a barge before actually disconnecting."""
        self._farewell_response_active = False
        if self._caller_speaking:
            log_pstn("hangup.close_listen.deferred", call_id=self.call_id, reason="caller_speaking")
            return
        wait_sec = self._close_listen_sec()
        self._close_listen_until = time.monotonic() + wait_sec
        self._last_activity_at = time.monotonic()
        self._set_phase(PHASE_LISTENING)
        asyncio.create_task(self._set_live_auto_response(False))
        log_pstn(
            "hangup.close_listen",
            call_id=self.call_id,
            wait_ms=int(wait_sec * 1000),
            fast=self._uses_fast_hangup(),
        )

    def _clear_hangup_arm(self) -> None:
        from server.call.call_context import get as get_ctx

        ctx = get_ctx(self.call_id) if self.call_id else None
        if ctx:
            ctx.agent_hangup_armed = False
            ctx.barge_in_flight = False

    def _greeting_protected(self) -> bool:
        if self._deferred_greeting_playing:
            return True
        return bool(self._greeting_protect_until and time.monotonic() < self._greeting_protect_until)

    def _greeting_waiting(self) -> bool:
        return bool(self._deferred_greeting_armed)

    def _barge_hold_active(self) -> bool:
        return bool(self._barge_hold_until and time.monotonic() < self._barge_hold_until)

    def _pickup_suppressed(self) -> bool:
        return bool(self._pickup_suppress_until and time.monotonic() < self._pickup_suppress_until)

    def _event_response_id(self, event: dict[str, Any]) -> str:
        return str(event.get("response_id") or "").strip()

    def _is_stale_openai_event(self, event: dict[str, Any]) -> bool:
        rid = self._event_response_id(event)
        current = self._openai_response_id
        return bool(rid and (rid in self._ignored_response_ids or (current and rid != current)))

    def _should_drop_user_final(self, text: str) -> bool:
        if not (text or "").strip():
            return True
        if _is_foreign_script_junk(text):
            return True
        if self._deferred_greeting_armed or self._deferred_greeting_playing:
            # Pickup speech only arms the cached greeting — never a model turn.
            return True
        if self._greeting_protected():
            return True
        if _is_pickup_phrase(text) or _is_availability_check(text):
            return False
        spoken = (self._assistant_text or self._deferred_greeting_text or "").strip()
        if spoken and self._agent_audio_playing() and is_likely_echo(text, spoken):
            return True
        if _is_presence_reply(text):
            return False
        if self._awaiting_presence_reply and _is_silence_prompt_ack(text):
            return False
        if self._pending_end_call or self._close_listen_until or self._resume_after_close:
            return False
        if self._aec_barge_open or self._barge_hold_active():
            return False
        return False

    async def _commit_local_barge(self) -> None:
        """Cut agent audio as soon as local AEC commits a barge — do not wait for VAD."""
        if self._closed:
            return
        if self._greeting_protected():
            log_pstn("realtime_voice.barge_ignored_greeting", call_id=self.call_id)
            return
        self._barge_generation = self.current_generation_id
        self._suppress_until_user = False
        self._response_open = False
        self._followup_inflight = False
        self._barge_hold_until = time.monotonic() + _BARGE_HOLD_SEC
        if self._on_barge:
            try:
                await asyncio.wait_for(self._on_barge(), timeout=1.0)
            except Exception as exc:
                log_pstn("playback.remote_clear.failed", call_id=self.call_id, error=str(exc)[:160])
        await self.interrupt_tts()
        if self._hangup_flow_active():
            self._caller_speaking = True
            self._set_phase(PHASE_LISTENING)
            return
        self._clear_hangup_arm()
        if self._hangup_started or self._phase == PHASE_CLOSING or self._farewell_response_active:
            self._abort_in_progress_hangup()
        else:
            self._set_phase(PHASE_LISTENING)

    async def _start_injected_response(self, instruction: str) -> None:
        if self._adapter is None or not (instruction or "").strip():
            return
        self._pending_followup_instruction = None
        self._suppress_until_user = False
        self._response_open = False
        self._followup_inflight = True
        self._response_activity_at = time.monotonic()
        self._assistant_text = ""
        # OpenAI response instructions replace the session instructions for this turn.
        # Keep the business script and language lock during injected recovery replies.
        base = _existing_adapter_instructions(self._adapter)
        instruction = (
            f"{base}\n\nCURRENT TURN TASK\n{instruction}\n\n"
            f"FINAL LANGUAGE CONSTRAINT: Speak only {self._resolve_language()}. "
            "Keep the business facts and required script steps. Do not translate into the caller's language."
        )
        await self._adapter.start_response(instructions=instruction)
        self._set_phase(PHASE_SPEAKING)

    async def _handle_pickup_or_availability(self, text: str, *, first_user: bool) -> None:
        """First hello is pickup (greeting already covers it). Later hello is availability."""
        if self._adapter is None:
            return
        try:
            await self._adapter.cancel_response()
        except Exception:
            pass
        who = bool(re.search(r"who(?:'s| is) this", text or "", flags=re.I))
        pickup = (first_user or (who and not self._heard_content_turn)) and not _is_line_check(text)
        if pickup:
            self._pickup_suppress_until = time.monotonic() + _PICKUP_SUPPRESS_SEC
            if not self._intro_noted and self._wire_frames_out == 0:
                # A prewarm miss means there is no delivered opening to cover
                # this hello. Cancelling its VAD reply and consuming it silently
                # leaves both sides waiting forever.
                from server.services.pstn_realtime_greeting_prewarm import prewarm_greeting_response_instructions

                opening = getattr(self, "_opening_text", None) or extract_opening_greeting(
                    self._compiled_brain(), self._resolve_language(), direction="outbound",
                )
                await self._start_injected_response(prewarm_greeting_response_instructions(
                    self._resolve_language(), opening,
                ))
                log_pstn("greeting.pickup.recovery", call_id=self.call_id)
                return
            log_pstn("realtime_voice.pickup_consumed", call_id=self.call_id, text=(text or "")[:80])
            return
        if not self._intro_noted:
            return
        log_pstn("realtime_voice.availability_check", call_id=self.call_id, text=(text or "")[:80])
        try:
            await self._start_injected_response(_AVAILABILITY_FOLLOWUP)
        except Exception as exc:
            log_pstn(
                "realtime_voice.availability_followup.failed",
                call_id=self.call_id,
                error=str(exc)[:160],
            )
            self._pending_followup_instruction = _AVAILABILITY_FOLLOWUP

    async def _handle_stay_on_line(self, text: str) -> None:
        """Caller came back after a farewell or 'are you still there?' — keep talking."""
        if self._adapter is None:
            return
        log_pstn("realtime_voice.stay_on_line", call_id=self.call_id, text=(text or "")[:80])
        try:
            await self._adapter.cancel_response()
        except Exception:
            pass
        try:
            await self._start_injected_response(_STILL_ON_LINE_FOLLOWUP)
        except Exception as exc:
            log_pstn(
                "realtime_voice.stay_on_line.failed",
                call_id=self.call_id,
                error=str(exc)[:160],
            )
            self._pending_followup_instruction = _STILL_ON_LINE_FOLLOWUP

    def _resolve_language(self) -> str:
        from server.prompts.agent_voice_rules import normalize_compile_language

        cached = getattr(self, "_cached_resolve_language", None)
        if cached:
            return cached
        if self.call_id:
            from server.call.call_ledger import call_ledger

            meta_lang = (call_ledger.read_meta(self.call_id) or {}).get("language")
            if meta_lang:
                self._cached_resolve_language = normalize_compile_language(str(meta_lang))
                return self._cached_resolve_language
        from server.call.call_context import get as get_ctx

        ctx = get_ctx(self.call_id) if self.call_id else None
        if ctx and getattr(ctx, "resolved_stack", None):
            lang = getattr(ctx.resolved_stack, "language", None)
            if lang:
                self._cached_resolve_language = normalize_compile_language(str(lang))
                return self._cached_resolve_language
        lang = normalize_compile_language(
            str(self.stack_override.get("language") or "te-IN")
        )
        self._cached_resolve_language = lang
        return lang

    def _active_spoken_language(self) -> str:
        return self._spoken_reply_language or self._resolve_language()

    def _maybe_mirror_caller_language(self, text: str) -> None:
        """Fixed-language mode (audit B2): do not auto-switch spoken language from STT."""
        _ = text
        return

    def _maybe_auto_language_mismatch_reminder(self, inferred: str) -> None:
        """LANG-3: one platform mismatch line without waiting for the Live tool race."""
        from server.call.call_context import get as get_ctx
        from server.prompts.agent_voice_rules import language_mismatch_fallback_for

        ctx = get_ctx(self.call_id) if self.call_id else None
        if not ctx or ctx.language_mismatch_handled or self._language_reminder_turn is not None:
            return
        if self._hangup_flow_active() or self._pending_end_call:
            return
        lang = self._resolve_language()
        line = language_mismatch_fallback_for(lang)
        self._language_reminder_turn = self._language_user_turn
        ctx.language_mismatch_handled = True
        self._pending_followup_instruction = (
            f"Speak only {lang}. Say exactly this once, then wait for the caller. "
            f"Do not hang up or request a callback on this turn: {line}"
        )
        log_pstn(
            "realtime_voice.language_mismatch_reminder",
            call_id=self.call_id,
            inferred=inferred,
            agent_lang=lang,
        )

    def _resolve_direction(self) -> str:
        from server.call.call_context import get as get_ctx

        ctx = get_ctx(self.call_id) if self.call_id else None
        raw = str(getattr(ctx, "direction", "") or self.stack_override.get("direction") or "")
        return "outbound" if raw.strip().lower() in ("outbound", "outgoing", "outbound-api") else "inbound"

    def _compiled_brain(self) -> str | None:
        from server.call.call_context import get as get_ctx

        ctx = get_ctx(self.call_id) if self.call_id else None
        return ctx.compiled_brain_text if ctx else None

    def _sanitize_live_assistant_text(self, text: str) -> str:
        if not text:
            return text
        from server.realtime.language_guard import enforce_output_language_script, filter_unrelated_scripts
        from server.realtime.live_transcript_sanitize import sanitize_live_assistant_transcript
        from server.realtime.models import is_gemini_live_voice_model

        lang = self._active_spoken_language()
        cleaned = filter_unrelated_scripts(text, lang)
        if is_gemini_live_voice_model(self._live_model or ""):
            cleaned = enforce_output_language_script(cleaned, lang)
        return sanitize_live_assistant_transcript(cleaned)

    async def _set_live_auto_response(self, enabled: bool) -> None:
        fn = getattr(self._adapter, "set_auto_response", None) if self._adapter else None
        if not callable(fn):
            return
        try:
            await fn(bool(enabled))
        except Exception as exc:
            log_pstn(
                "realtime_voice.auto_response.failed",
                call_id=self.call_id,
                enabled=bool(enabled),
                error=str(exc)[:160],
            )

    async def _maybe_refresh_gemini_deferred_greeting(
        self,
        *,
        brain: str | None,
        language: str,
        greeting_text: str | None,
        greeting_wire_frames: list[bytes] | None,
        model: str,
        cfg: dict[str, Any],
        max_output_tokens: int | None,
    ) -> tuple[str | None, list[bytes] | None]:
        """Re-synth PCM when an old prewarm bundle has a too-short intro (OpenAI parity)."""
        line = (greeting_text or "").strip()
        if not brain or not line or not greeting_wire_frames:
            return greeting_text, greeting_wire_frames
        from server.realtime.models import is_gemini_live_voice_model

        if not is_gemini_live_voice_model(model):
            return greeting_text, greeting_wire_frames
        refreshed = extract_prewarm_greeting(brain, language, direction="outbound")
        if not refreshed or refreshed.strip() == line:
            return greeting_text, greeting_wire_frames
        # ponytail: full side-session resynth on answer blocked the line for seconds; only refresh tiny intros.
        if len(line) >= 36:
            return greeting_text, greeting_wire_frames
        from server.services.pstn_realtime_greeting_prewarm import synthesize_gemini_greeting_on_side_session

        log_pstn(
            "greeting.deferred.refresh",
            call_id=self.call_id,
            old_chars=len(line),
            new_chars=len(refreshed),
        )
        frames, transcript, _usage = await synthesize_gemini_greeting_on_side_session(
            greeting_text=refreshed,
            sample_rate=self.sample_rate,
            tts_output_codec=self.tts_output_codec,
            model=model,
            voice=str(cfg.get("voice") or ""),
            turn_detection=str(cfg.get("turn_detection") or ""),
            max_output_tokens=max_output_tokens,
            control_id=self.call_id or self.session_id,
        )
        if _usage:
            await record_realtime_voice_usage(
                call_id=self.call_id, usage=_usage, llm_model=model, prewarm=True,
            )
        if not frames:
            # Never play a known stale identity/offer when regeneration fails, but do
            # not go silent without a trace: the platform has no opening left to play
            # and the model is instructed not to speak first, so the callee hears
            # nothing until they talk.
            log_pstn(
                "greeting.deferred.resynth_failed",
                call_id=self.call_id,
                model=model,
                old_chars=len(line),
                new_chars=len(refreshed),
                reason="side_session_returned_no_audio",
            )
            return refreshed, []
        return (transcript or refreshed).strip(), frames

    async def _recover_outbound_deferred_opening(
        self,
        *,
        brain: str | None,
        language: str,
        model: str,
        cfg: dict[str, Any],
        max_output_tokens: int | None,
        adapter: Any,
    ) -> tuple[str | None, list[bytes]]:
        """Answer-time PCM when dial-time prewarm was not adopted (multi-worker, adopt miss, etc.)."""
        if not (brain or "").strip():
            return None, []
        line = extract_prewarm_greeting(brain, language, direction="outbound")
        if not line:
            return None, []
        from server.realtime.models import is_gemini_live_voice_model
        from server.services.pstn_realtime_greeting_prewarm import (
            synthesize_gemini_greeting_on_side_session,
            synthesize_realtime_greeting_frames,
        )

        log_pstn(
            "greeting.deferred.recover",
            call_id=self.call_id,
            model=model,
            chars=len(line),
        )
        if is_gemini_live_voice_model(model):
            frames, transcript, usage = await synthesize_gemini_greeting_on_side_session(
                greeting_text=line,
                sample_rate=self.sample_rate,
                tts_output_codec=self.tts_output_codec,
                language=language,
                model=model,
                voice=str(cfg.get("voice") or ""),
                turn_detection=str(cfg.get("turn_detection") or ""),
                max_output_tokens=max_output_tokens,
                control_id=self.call_id or self.session_id,
            )
            if usage and self.call_id:
                await record_realtime_voice_usage(
                    call_id=self.call_id, usage=usage, llm_model=model, prewarm=True,
                )
        else:
            frames, transcript, usage = await synthesize_realtime_greeting_frames(
                adapter,
                greeting_text=line,
                sample_rate=self.sample_rate,
                tts_output_codec=self.tts_output_codec,
                language=language,
                control_id=self.call_id or self.session_id,
            )
            if usage and self.call_id:
                await record_realtime_voice_usage(
                    call_id=self.call_id,
                    usage=usage,
                    llm_model=model,
                    prewarm=True,
                )
        if not frames:
            log_pstn(
                "greeting.deferred.recover_failed",
                call_id=self.call_id,
                model=model,
                reason="no_audio_frames",
            )
            return None, []
        return (transcript or line).strip(), list(frames)

    def _frame_bytes(self) -> int:
        if self.current_output_codec == "L16":
            return int(self.sample_rate * 0.02) * 2
        return 160

    async def start_call(
        self,
        *,
        play_greeting: bool = True,
        greeting_wire_frames: list[bytes] | None = None,
        greeting_text: str | None = None,
    ) -> None:
        if self._call_started:
            return
        self._call_started = True
        if self.call_id:
            from server.call.audio_archive import audio_archive

            audio_archive.set_agent_sample_rate(self.call_id, self.sample_rate)

        # --- TOOL DISCOVERY: fetch tenant's active integrations via registry ---
        tenant_tool_schemas: list[dict] = []
        if (not self._tenant_id or not self._agent_id) and self.call_id:
            try:
                from server.call.call_ledger import call_ledger
                meta = call_ledger.read_meta(self.call_id) or {}
                if not self._tenant_id:
                    self._tenant_id = meta.get("tenant_id")
                if not self._agent_id:
                    self._agent_id = meta.get("agent_id")
            except Exception:
                pass

        tenant_tool_schemas: list[dict[str, Any]] = []
        if self._tenant_id:
            try:
                from server.db.connection import get_session_factory as _get_sf
                from server.services.tenant_tool_cache import get_active_app_names
                from server.services.tool_schema_registry import (
                    get_tools_for_tenant,
                    get_tool_names_for_tenant,
                )
                _sf = _get_sf()
                active_apps = await get_active_app_names(str(self._tenant_id), _sf)
                if active_apps:
                    tenant_tool_schemas = get_tools_for_tenant(active_apps)
                    # Exact tool names from registry — no guesswork suffixes
                    self._agent_tools = get_tool_names_for_tenant(active_apps)
                    log_pstn(
                        "tool_router.tenant_tools_loaded",
                        call_id=self.call_id,
                        apps=active_apps,
                        tools=len(tenant_tool_schemas),
                    )
            except Exception as exc:
                logger.warning("[PSTN_REALTIME] Could not load tenant tool schemas: %s", exc)

        language = self._resolve_language()
        direction = self._resolve_direction()
        brain = self._compiled_brain()
        cfg = realtime_voice_config(self.stack_override)
        from server.call.call_context import get as get_ctx
        from server.realtime.voice_manager import realtime_voice_manager
        from server.services.runtime_settings import runtime_settings

        ctx = get_ctx(self.call_id) if self.call_id else None
        caller_id = getattr(ctx, "session_id", None)
        rt = runtime_settings.get(self.config_session_id or self.session_id)
        model = resolve_realtime_voice_model(self.stack_override, rt.get("openaiModel"))
        max_output_tokens = resolve_realtime_voice_max_output_tokens(rt.get("openaiMaxTokens"))
        self._live_model = model
        self._voice_name = str(cfg.get("voice") or "")
        self._started_at = time.monotonic()
        from server.realtime.voice_factory import realtime_voice_llm_provider

        llm_provider, _ = realtime_voice_llm_provider(self.stack_override, model)
        tx_policy = self._transcription_policy()
        input_transcription = tx_policy.openai_session_input_transcription()
        deferred_frames = list(greeting_wire_frames or [])
        deferred_text = (greeting_text or "").strip()
        if (
            play_greeting
            and direction == "outbound"
            and deferred_frames
            and deferred_text
        ):
            deferred_text, deferred_frames = await self._maybe_refresh_gemini_deferred_greeting(
                brain=brain,
                language=language,
                greeting_text=deferred_text,
                greeting_wire_frames=deferred_frames,
                model=model,
                cfg=cfg,
                max_output_tokens=max_output_tokens,
            )
        opening = deferred_text or greeting_text
        if not opening and play_greeting:
            if llm_provider == "gemini":
                opening = extract_prewarm_greeting(brain, language, direction=direction)
            if not opening:
                opening = extract_opening_greeting(brain, language, direction=direction)
        self._opening_text = opening
        instructions = build_realtime_voice_instructions(
            brain,
            model=model,
            stack_override=self.stack_override,
            caller_id=str(caller_id or "") if direction == "inbound" else None,
            language=language,
            direction=direction,
            opening_greeting=opening,
        )
        adapter = self._injected_adapter
        if adapter is None and self.call_id:
            adapter = realtime_voice_manager.get(self.call_id)
        if adapter is None:
            adapter = await realtime_voice_manager.create(
                self.call_id or f"voice-{uuid.uuid4().hex[:10]}",
                instructions=instructions,
                compiled_brain=brain,
                model=model,
                language=language,
                voice=cfg["voice"],
                turn_detection=cfg["turn_detection"],
                stack_override=self.stack_override,
                max_output_tokens=max_output_tokens,
                wait_ready=True,
                extra_tools=tenant_tool_schemas,
            )
        else:
            warm = _existing_adapter_instructions(adapter)
            # Gemini system instructions and tools are immutable after setup. At answer
            # there is no caller history yet, so reconnect a stale warm session.
            if llm_provider == "gemini" and adapter.is_open() and (warm != instructions or tenant_tool_schemas):
                log_pstn("realtime_voice.prewarm.reconnect", call_id=self.call_id, reason="tools_or_instructions_changed")
                await adapter.close()
            if not adapter.is_open():
                connect_kw: dict[str, Any] = {
                    "model": model,
                    "instructions": instructions,
                    "voice": cfg["voice"],
                    "turn_detection": cfg["turn_detection"],
                    "vad_eagerness": cfg.get("vad_eagerness"),
                    "noise_reduction": cfg.get("noise_reduction"),
                    "speed": cfg.get("speed"),
                    "silence_ms": cfg.get("silence_ms"),
                    "max_output_tokens": max_output_tokens,
                    "extra_tools": tenant_tool_schemas,
                }
                import inspect

                if "input_transcription_enabled" in inspect.signature(adapter.connect).parameters:
                    connect_kw["input_transcription_enabled"] = input_transcription
                await adapter.connect(**connect_kw)
                await adapter.wait_ready()
            else:
                warm = _existing_adapter_instructions(adapter)
                updater = getattr(adapter, "update_instructions", None)
                tools_updater = getattr(adapter, "update_tools", None)
                if callable(tools_updater) and tenant_tool_schemas:
                    try:
                        await tools_updater(tenant_tool_schemas)
                        log_pstn("realtime_voice.prewarm.tools_updated", call_id=self.call_id, count=len(tenant_tool_schemas))
                    except Exception as e:
                        logger.warning("[PSTN] Failed to update prewarm tools: %s", e)
                canon = (opening or "").strip()
                needs_opening_patch = bool(canon and warm and canon[:48] not in warm)
                if warm and not needs_opening_patch:
                    log_pstn(
                        "realtime_voice.instructions.kept_prewarm",
                        call_id=self.call_id,
                        chars=len(warm),
                    )
                elif callable(updater):
                    await updater(instructions)
                elif hasattr(adapter, "instructions"):
                    adapter.instructions = instructions
        self._adapter = adapter
        self._start_caller_stt_sidecar(language, llm_provider)
        if play_greeting and direction == "outbound" and deferred_frames and deferred_text:
            self._deferred_greeting_frames = list(deferred_frames)
            self._deferred_greeting_text = deferred_text.strip()
            self._deferred_greeting_armed = True
        elif play_greeting and direction == "outbound":
            # Outbound with no pre-synthesized opening. This must always leave a
            # trace: without an opening the model is told not to speak first, so
            # the callee hears silence until they talk, and the call is billable.
            log_pstn(
                "greeting.deferred.miss",
                call_id=self.call_id,
                reason="no_prewarm_frames" if not deferred_frames else "no_greeting_text",
                llm_provider=llm_provider,
                model=model,
                chars=len(deferred_text or ""),
            )
            recovered_text, recovered_frames = await self._recover_outbound_deferred_opening(
                brain=brain,
                language=language,
                model=model,
                cfg=cfg,
                max_output_tokens=max_output_tokens,
                adapter=adapter,
            )
            if recovered_frames and recovered_text:
                deferred_text = recovered_text
                deferred_frames = recovered_frames
                self._deferred_greeting_frames = list(deferred_frames)
                self._deferred_greeting_text = deferred_text.strip()
                self._deferred_greeting_armed = True
                log_pstn(
                    "greeting.deferred.recovered",
                    call_id=self.call_id,
                    frames=len(recovered_frames),
                    chars=len(recovered_text),
                )
        if self._deferred_greeting_armed:
            auto_response = getattr(adapter, "set_auto_response", None)
            if callable(auto_response):
                await auto_response(False)
            else:
                # Without this control VAD can create a competing live reply.
                log_pstn(
                    "greeting.deferred.miss",
                    call_id=self.call_id,
                    reason="adapter_missing_auto_response_control",
                )
                self._deferred_greeting_frames = None
                self._deferred_greeting_text = None
                self._deferred_greeting_armed = False
        self._pump_task = asyncio.create_task(self._event_pump(), name=f"rt-voice-pump-{self.call_id}")
        self._last_activity_at = time.monotonic()
        self._runtime_task = asyncio.create_task(self._watch_runtime(), name=f"rt-watch-{self.call_id}")
        if self._deferred_greeting_armed:
            self._arm_pickup_fallback()
        elif play_greeting and opening and (
            direction == "outbound" or getattr(adapter, "needs_explicit_opening", False)
        ):
            played_side = await self._play_gemini_inbound_opening_if_needed(
                adapter=adapter,
                opening=opening,
                model=model,
                cfg=cfg,
                max_output_tokens=max_output_tokens,
                llm_provider=llm_provider,
            )
            if not played_side:
                from server.services.pstn_realtime_greeting_prewarm import (
                    prewarm_greeting_response_instructions,
                )

                auto_response = getattr(adapter, "set_auto_response", None)
                if callable(auto_response):
                    await auto_response(False)
                try:
                    log_pstn("greeting.fallback.requested", call_id=self.call_id, model=model)
                    await adapter.start_response(
                        instructions=prewarm_greeting_response_instructions(
                            self._resolve_language(), opening
                        )
                    )
                except Exception as exc:
                    log_pstn("realtime_voice.opening.failed", call_id=self.call_id, error=str(exc)[:160])
                    raise RuntimeError("Opening response could not be started") from exc
                finally:
                    if callable(auto_response):
                        try:
                            await auto_response(True)
                        except Exception:
                            pass
        log_pstn(
            "lifecycle.started",
            call_id=self.call_id,
            session_id=self.session_id,
            sample_rate=self.sample_rate,
            pipeline="realtime_voice",
            vad_mode="natural_vad",
            direction=direction,
            play_greeting=play_greeting,
            deferred_greeting=self._deferred_greeting_armed,
            deferred_frames=len(self._deferred_greeting_frames or []),
        )
        self._set_phase(PHASE_LISTENING)
        self._hold_inbound = False
        await self._flush_pending_inbound()

    async def feed_user_pcm16(self, pcm16: bytes) -> None:
        if not pcm16 or self._closed or self._farewell_complete:
            return
        if self._hold_inbound or self._adapter is None:
            self._queue_pending_inbound(pcm16)
            return
        raw = pcm16
        if self._deferred_greeting_armed:
            # Pickup is local energy only. Do not append to OpenAI — the first
            # utterance must not become an LLM turn.
            from server.services.audio_transcode import pcm16_rms

            frame_ms = len(raw) * 1000 / (2 * self.sample_rate)
            rms = pcm16_rms(raw)
            if rms >= REALTIME_PICKUP_ENERGY_MIN:
                self._pickup_speech_ms += frame_ms
                self._pickup_quiet_ms = 0.0
                self._pickup_dip_ms = 0.0
                self._cancel_pickup_finish()
            elif self._pickup_speech_ms >= _PICKUP_MIN_SPEECH_MS:
                self._pickup_quiet_ms += frame_ms
                self._pickup_dip_ms = 0.0
                if self._pickup_quiet_ms >= _PICKUP_QUIET_MS:
                    self._schedule_deferred_greeting()
            else:
                self._pickup_dip_ms += frame_ms
                if self._pickup_dip_ms >= _PICKUP_DIP_RESET_MS:
                    self._pickup_speech_ms = 0.0
                    self._pickup_dip_ms = 0.0
            self._note_pickup_rms(rms)
            if self.call_id:
                self._archive.enqueue(self.call_id, "user", raw)
            return
        if self.call_id:
            self._archive.enqueue(self.call_id, "user", raw)
        if self._greeting_protected():
            return
        # Handset echo of agent audio looks like the caller to OpenAI VAD and
        # cuts the reply. Hold inbound (do not append zeros — that can look like
        # speech_stopped and spawn an overlapping response) until the level is a barge.
        if self._agent_audio_playing():
            try:
                from server.services.audio_transcode import pcm16_rms

                rms = pcm16_rms(raw)
                # ponytail: echo tail ~550ms after agent audio starts — stricter RMS/frame gate (A2).
                echo_tail = (
                    self._agent_audio_out_since > 0
                    and (time.monotonic() - self._agent_audio_out_since) < 0.55
                )
                need_rms = REALTIME_AEC_ENERGY_MIN + (550 if echo_tail else 0)
                need_frames = REALTIME_AEC_LOUD_OPEN_FRAMES
                partial = (self._user_partial or "").strip()
                spoken = (self._assistant_text or "").strip()
                if partial and spoken and is_likely_echo(partial, spoken):
                    self._aec_loud_streak = 0
                    return
                if rms >= need_rms:
                    self._aec_loud_streak += 1
                    self._aec_quiet_streak = 0
                    if self._aec_loud_streak >= need_frames:
                        if not self._aec_barge_open:
                            log_pstn(
                                "realtime_voice.barge_open",
                                call_id=self.call_id,
                                rms=round(rms, 1),
                            )
                            self._aec_barge_open = True
                            await self._commit_local_barge()
                        else:
                            self._aec_barge_open = True
                else:
                    self._aec_quiet_streak += 1
                    self._aec_loud_streak = 0
                    if self._aec_quiet_streak >= PSTN_AEC_QUIET_CLOSE_FRAMES:
                        self._aec_barge_open = False
                if not self._aec_barge_open:
                    return
            except Exception:
                return
        else:
            self._aec_loud_streak = 0
            self._aec_quiet_streak = 0
            self._aec_barge_open = False
            self._agent_audio_out_since = 0.0
        pcm24 = self._in_resampler.feed(pcm16)
        if not pcm24:
            return
        if self._caller_stt is not None:
            self._caller_stt.feed_pcm16(pcm24)
        try:
            await self._adapter.append_pcm16(pcm24)
        except Exception as exc:
            log_pstn("realtime_voice.append.failed", call_id=self.call_id, error=str(exc)[:160])

    async def _event_pump(self) -> None:
        adapter = self._adapter
        if adapter is None:
            return
        try:
            while not self._closed:
                try:
                    async for event in adapter.events():
                        if self._closed:
                            break
                        await self._handle_event(event)
                except asyncio.CancelledError:
                    return
                except Exception as exc:
                    logger.warning("[REALTIME_VOICE] pump failed: %s", str(exc)[:200])
                if self._closed or self.controller.state == CallState.ENDED:
                    break
                ensure = getattr(adapter, "ensure_recv_pump", None)
                if callable(ensure) and adapter.is_open():
                    await ensure()
                    alive = getattr(adapter, "recv_pump_alive", None)
                    if callable(alive) and not alive():
                        break
                    await asyncio.sleep(0.05)
                    continue
                break
        finally:
            if not self._closed and self.controller.state != CallState.ENDED:
                await self._runtime_end("provider_failure")

    async def _runtime_end(self, reason: str) -> None:
        """Disconnect the caller before archive/accounting, also on failures."""
        if self._closed or self.controller.state == CallState.ENDED:
            return
        await self._fast_disconnect_after_farewell(reason, self._response_had_audio)

    async def _watch_runtime(self) -> None:
        try:
            while not self._closed and self.controller.state != CallState.ENDED:
                await asyncio.sleep(0.25)
                await self._check_runtime(time.monotonic())
        except asyncio.CancelledError:
            return
        except Exception as exc:
            log_pstn("runtime.watch.failed", call_id=self.call_id, error=str(exc)[:160])
            await self._runtime_end("runtime_failure")

    async def _check_runtime(self, now: float) -> None:
        if self._closed or self._hangup_started:
            return
        if self._farewell_complete and self._pending_end_call:
            try:
                await self._finish_hangup()
            except Exception as exc:
                log_pstn("hangup.retry.failed", call_id=self.call_id, error=str(exc)[:160])
            return
        if self._started_at and now - self._started_at >= 900:
            await self._runtime_end("max_duration")
            return
        if self._ending_at and now - self._ending_at >= 30:
            if self._hangup_flow_active() or self._pending_end_call:
                log_pstn("hangup.farewell_timeout_finish", call_id=self.call_id)
                await self._finish_hangup()
            else:
                await self._runtime_end("farewell_timeout")
            return
        if (self._response_open or self._followup_inflight) and now - self._response_activity_at >= 30:
            if self._caller_speaking or self._aec_barge_open:
                # Caller activity is not a provider failure. Retire the stuck
                # response and keep listening; genuine dead sessions still fail.
                if self._openai_response_id:
                    self._ignored_response_ids.append(self._openai_response_id)
                self._response_open = False
                self._followup_inflight = False
                self._set_tts_active(False)
                self._last_activity_at = now
                self._set_phase(PHASE_LISTENING)
                return
            if await self._recover_stuck_response_for_hangup():
                return
            await self._runtime_end("response_timeout")
            return
        if self._hangup_started:
            return
        if self._pending_end_call:
            if self._tts_active or self._agent_audio_playing() or self._response_open:
                self._last_activity_at = now
                return
            if self._caller_speaking:
                self._last_activity_at = now
                return
            if self._aec_barge_open and not self._close_listen_until:
                self._last_activity_at = now
                return
            if self._close_listen_until and now >= self._close_listen_until:
                log_pstn("hangup.close_listen.expired", call_id=self.call_id)
                await self._finish_hangup()
                return
            if not self._close_listen_until and not self._farewell_response_active:
                self._begin_close_listen()
            if (
                self._uses_fast_hangup()
                and not self._farewell_response_active
                and not self._farewell_audio_engaged()
            ):
                log_pstn("hangup.fast_finish_pending", call_id=self.call_id)
                await self._finish_hangup()
                return
            if self._hangup_armed_at and now - self._hangup_armed_at >= PENDING_HANGUP_STUCK_SEC:
                log_pstn("hangup.stuck_pending", call_id=self.call_id)
                await self._finish_hangup()
            return
        if self._caller_speaking or self._tts_active or self._agent_audio_playing() or self._response_open:
            self._last_activity_at = now
            return
        idle = now - self._last_activity_at
        if self._deferred_greeting_armed:
            if idle >= 25:
                self._schedule_deferred_greeting()
            return
        hang_after = self._silence_hangup_sec()
        nudge_after = self._silence_nudge_sec()
        if idle >= hang_after and self._silence_prompted:
            from server.call.hangup_judge import silence_close_instruction

            self._awaiting_presence_reply = False
            self._pending_end_call = {"should_end": True, "reason": "silence_timeout"}
            self._pending_farewell_text = self._localized_farewell()
            self.controller.state = CallState.ENDING
            self._ending_at = now
            self._farewell_response_active = True
            self._set_hangup_arm_source("silence")
            await self._notify_hangup("initiated", "silence_timeout")
            await self._start_injected_response(silence_close_instruction(self._resolve_language()))
        elif idle >= nudge_after and not self._silence_prompted:
            if self._hangup_flow_active():
                return
            if caller_requested_hangup(self._caller_text()) or caller_firm_refusal(self._caller_text()):
                await self._arm_hangup_from_caller_words(self._caller_text())
                return
            self._silence_prompted = True
            self._awaiting_presence_reply = True
            self._last_activity_at = now
            await self._start_injected_response(
                "Ask only 'Are you still there?' in the configured language, then wait."
            )

    async def _recover_stuck_response_for_hangup(self) -> bool:
        """Convert a stuck Live response into a clean hangup when end intent is known."""
        if not self._known_end_intent():
            return False
        log_pstn(
            "hangup.stuck_response",
            call_id=self.call_id,
            arm_source=self._hangup_arm_source or "backup",
        )
        if self._openai_response_id:
            self._ignored_response_ids.append(self._openai_response_id)
            self._openai_response_id = ""
        try:
            if self._adapter is not None:
                await self._adapter.cancel_response()
        except Exception:
            pass
        self._response_open = False
        self._followup_inflight = False
        self._set_tts_active(False)
        if not self._pending_end_call:
            await self._arm_hangup_from_caller_words(self._caller_text())
        if not self._pending_end_call:
            return False
        if self._adapter is not None and not self._farewell_audio_engaged():
            from server.realtime.models import is_gemini_live_voice_model

            await self._ensure_hangup_farewell_audio(
                prefer_side_session=is_gemini_live_voice_model(self._live_model or "")
            )
        await self._finish_hangup()
        return True

    def _outbound_callee_digits(self) -> str | None:
        if self._resolve_direction() != "outbound" or not self.call_id:
            return None
        from server.call.call_ledger import call_ledger

        meta = call_ledger.read_meta(self.call_id) or {}
        raw = str(meta.get("callee_e164") or "").strip()
        if not raw:
            from server.services.pstn_media_flow import pstn_media_flow

            snap = pstn_media_flow.snapshot(self.call_id) or {}
            ext = str(snap.get("external_id") or "").strip()
            if ext:
                from server.services.telnyx_client import telnyx_call_registry

                row = telnyx_call_registry.get(ext) or {}
                raw = str(row.get("callee_e164") or row.get("to") or "").strip()
        if not raw:
            return None
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        if len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        if 7 <= len(digits) <= 15:
            return digits
        return None

    def _should_persist_callback_withdrawal(self) -> bool:
        text = self._caller_text()
        if caller_withdrew_callback(text) or caller_firm_refusal(text) or caller_requested_hangup(text):
            return True
        if caller_declines_more_help(text) or user_short_close_ack(text):
            return False
        return bool(self.controller.callback_cancelled)

    def _cancel_callback(self) -> None:
        self.controller.callback_cancelled = True
        self._callback_request_text = ""
        self._callback_collecting_field = None
        self._callback_close_phase = "idle"
        self._pending_followup_instruction = None
        if self.call_id:
            from server.call.call_context import get as get_ctx
            ctx = get_ctx(self.call_id)
            if ctx:
                ctx.callback_request_text = ""
                ctx.callback_close_phase = "idle"
                ctx.components["callback_cancelled"] = True
            from server.call.call_ledger import call_ledger
            try:
                meta = call_ledger.read_meta(self.call_id)
                if meta.get("language_callback"):
                    meta["language_callback"]["status"] = "cancelled"
                    call_ledger.write_meta(self.call_id, meta)
            except Exception as exc:
                log_pstn("language_callback.cancel_failed", call_id=self.call_id, error=str(exc)[:160])
            if self._should_persist_callback_withdrawal():
                if not self._callback_cancellation_persisted:
                    from server.call.call_ledger import call_ledger
                    from server.call.memory_manager import memory_manager
                    try:
                        memory_manager.apply_proposals(
                            self.call_id,
                            [{"op": "set_fact", "key": "callback_requested", "value": "false"},
                             {"op": "set_fact", "key": "callback_cancelled", "value": "true"}],
                            turn_seq=1 + len(call_ledger.read_lines(self.call_id)),
                            source="realtime_callback_withdrawal",
                        )
                        self._callback_cancellation_persisted = True
                    except Exception as exc:
                        log_pstn("callback.withdrawal.persist_failed", call_id=self.call_id, error=str(exc)[:160])
    async def _handle_call_action(self, event: dict[str, Any]) -> None:
        action = AgentAction.parse(event.get("arguments"))
        error: str | None
        if action is None:
            error = "invalid_action"
        elif action.action == CallAction.END_CALL:
            from server.call.hangup_judge import map_call_action_end_reason

            accepted = await self._gate_end_call_payload(
                {
                    "should_end": True,
                    "reason": map_call_action_end_reason(action.reason),
                    "farewell": action.response or "",
                },
                tool_sourced=True,
            )
            if accepted:
                error = self.controller.request(action, caller_speaking=self._caller_speaking)
                if error is None:
                    await self._arm_accepted_hangup(accepted, tool_sourced=True)
                    self._ending_at = time.monotonic()
                else:
                    self.controller.resume()
            else:
                error = "end_call_rejected"
        else:
            if (
                action.reason == "callback_cancelled"
                and not caller_withdrew_callback(self._user_partial)
            ):
                self.controller.callback_cancelled = False
            error = self.controller.request(action, caller_speaking=self._caller_speaking)
        if action and self.controller.callback_cancelled:
            if caller_withdrew_callback(self._user_partial):
                self._cancel_callback()
            else:
                self.controller.callback_cancelled = False
        if action and error is None and action.action != CallAction.END_CALL:
            if action.action == CallAction.CALLBACK:
                self._callback_request_text = self._user_partial
                self._pending_followup_instruction = (
                    "The caller requests a callback. Collect only missing details one at a time. "
                    "Do not claim it is confirmed until details and consent are clear."
                )
            elif action.action == CallAction.CONTINUE:
                self._pending_followup_instruction = "Continue with the caller's current request."
        elif error == "action_unavailable":
            self._pending_followup_instruction = (
                "Explain briefly that this action is unavailable and ask how else you can help. "
                "Do not claim a transfer, voicemail, or callback succeeded."
            )
        elif error and self.controller.state == CallState.ACTIVE:
            self._pending_followup_instruction = "Clarify the caller's intent briefly; continue the call."
        if self._adapter and event.get("call_id"):
            await self._adapter.submit_function_output(
                call_id=str(event["call_id"]),
                output=json.dumps({"ok": error is None, "error": error, "state": self.controller.state.value}),
                name=str(event.get("name") or "call_action"),
            )

    def _capture_callback_detail(self, text: str) -> None:
        value = (text or "").strip()
        if not value:
            return
        field = self._callback_collecting_field
        if field == "name":
            cleaned = re.sub(
                r"^(?:my name is|this is|i am|i'm|name is)\s+",
                "",
                value,
                flags=re.IGNORECASE,
            ).strip(" .,!?:;")
            if cleaned and not re.search(r"\d", cleaned) and len(cleaned.split()) <= 8:
                self._callback_details["name"] = cleaned
                self._callback_collecting_field = None
        elif field == "phone":
            digits = re.sub(r"\D", "", value)
            if 7 <= len(digits) <= 15:
                self._callback_details["phone"] = digits
                self._callback_collecting_field = None
            elif looks_like_bare_name(value):
                self._callback_details["name"] = value.strip(" .,!?:;")
        elif field == "timing":
            self._callback_details["timing"] = value[:120]
            self._callback_collecting_field = None

        explicit_name = re.search(
            r"\b(?:my name is|name is|this is)\s+([A-Za-z][A-Za-z .'-]{0,60})",
            value,
            re.IGNORECASE,
        )
        if explicit_name:
            self._callback_details["name"] = explicit_name.group(1).strip(" .,!?:;")
        digits = re.sub(r"\D", "", value)
        if 7 <= len(digits) <= 15:
            self._callback_details["phone"] = digits

    def _sync_callback_close_state(self):
        from server.call.callback_close import advance_callback_close
        from server.call.call_context import get as get_ctx
        from server.call.memory_manager import memory_manager

        ctx = get_ctx(self.call_id) if self.call_id else None
        snapshot = None
        if self.call_id:
            try:
                snapshot = memory_manager.get_snapshot(self.call_id)
            except Exception:
                snapshot = None
        if self.controller.callback_cancelled and caller_withdrew_callback(self._user_partial):
            self._cancel_callback()
            from server.call.callback_close import CallbackCloseState
            return CallbackCloseState("idle")
        extra = dict(self._callback_details)
        if not extra.get("phone"):
            callee = self._outbound_callee_digits()
            if callee:
                extra["phone"] = callee
        state = advance_callback_close(
            ctx,
            self._user_partial,
            snapshot,
            extra_slots=extra,
            request_text=self._callback_request_text,
        )
        if caller_requested_callback(self._user_partial):
            self._callback_request_text = self._user_partial
        elif ctx and ctx.callback_request_text:
            self._callback_request_text = ctx.callback_request_text
        self._callback_close_phase = state.phase
        self._callback_collecting_field = state.missing
        if state.name:
            self._callback_details["name"] = state.name
        if state.phone:
            self._callback_details["phone"] = state.phone
        if state.when:
            self._callback_details["timing"] = state.when
        return state

    def _callback_missing_detail(self) -> str | None:
        return self._sync_callback_close_state().missing

    def _callback_followup_instruction(self, field: str) -> str:
        from server.call.callback_close import spoken_collect_instruction

        return spoken_collect_instruction(field, self._resolve_language())

    def _persist_callback_details(self) -> None:
        if not self.call_id or not self._callback_request_text:
            return
        try:
            from server.call.call_ledger import call_ledger
            from server.call.memory_manager import memory_manager

            meta = call_ledger.read_meta(self.call_id)
            snapshot = memory_manager.get_snapshot(self.call_id)
            facts = snapshot.get("facts") if isinstance(snapshot.get("facts"), dict) else {}
            from server.call.caller_detail_capture import is_usable_lead_name, is_usable_lead_phone

            name = (
                self._callback_details.get("name", "")
                or facts.get("name", "")
                or facts.get("caller_name", "")
            )
            if not is_usable_lead_name(str(name or "")):
                name = ""
            phone = (
                self._callback_details.get("phone", "")
                or facts.get("callback_phone", "")
                or facts.get("phone", "")
            )
            if not is_usable_lead_phone(str(phone or "")):
                phone = ""
            direction = str(meta.get("direction") or self._resolve_direction() or "")
            if not phone and direction.strip().lower() in ("outbound", "outgoing", "outbound-api"):
                dialed = str(meta.get("callee_e164") or "")
                phone = dialed if is_usable_lead_phone(dialed) else ""
            if (
                not phone
                and direction.strip().lower() not in ("outbound", "outgoing", "outbound-api")
                and not caller_asked_to_record_details(self._callback_request_text)
            ):
                ani = str(meta.get("caller_id") or "")
                phone = ani if is_usable_lead_phone(ani) else ""
            values = {
                "callback_requested": "true",
                "callback_time": self._callback_details.get("timing", ""),
                "name": name,
                "phone": phone,
            }
            operations = [
                {"op": "set_fact", "key": key, "value": str(value)}
                for key, value in values.items()
                if str(value).strip()
            ]
            turn_seq = 1 + sum(
                1 for row in call_ledger.read_lines(self.call_id) if row.get("role") == "user"
            )
            memory_manager.apply_proposals(
                self.call_id,
                operations,
                turn_seq=turn_seq,
                source="realtime_callback_gate",
            )
        except Exception as exc:
            log_pstn(
                "end_call.callback_memory_failed",
                call_id=self.call_id,
                error=str(exc)[:160],
            )

    async def _maybe_resume_callback_close(self) -> None:
        """If the caller asked to leave details / be contacted, keep collecting then hang up.

        The model often keeps pitching instead of calling end_call. Drive the close here.
        """
        if not self._callback_request_text or self.controller.callback_cancelled:
            return
        if self._pending_end_call or self._pending_followup_instruction:
            return
        if self._farewell_response_active or self._hangup_started:
            return
        if caller_requested_hangup(self._caller_text()) or caller_firm_refusal(self._caller_text()):
            return
        state = self._sync_callback_close_state()
        spoken = self._assistant_text or ""
        asked = {
            "name": re.compile(
                r"\b(your name|may i have your name|name please|మీ పేరు|aapka naam)\b",
                re.I,
            ),
            "phone": re.compile(
                r"\b(phone(?: number)?|mobile number|best number|నంబర్|नंबर)\b",
                re.I,
            ),
        }
        if state.missing:
            self._callback_collecting_field = state.missing
            if asked.get(state.missing) and asked[state.missing].search(spoken):
                return
            self._pending_followup_instruction = self._callback_followup_instruction(state.missing)
            log_pstn("end_call.callback_prompted", call_id=self.call_id, missing=state.missing)
            return
        from server.call.end_call_validate import looks_like_question
        from server.call.hangup_judge import agent_spoke_closing

        if looks_like_question(spoken) or asked["phone"].search(spoken) or asked["name"].search(spoken):
            return
        if agent_spoke_closing(spoken):
            if state.missing:
                self._pending_followup_instruction = self._callback_followup_instruction(state.missing)
                log_pstn("end_call.callback_blocked_close", call_id=self.call_id, missing=state.missing)
                return
            accepted = await self._gate_end_call_payload(
                {
                    "should_end": True,
                    "reason": "goal_complete",
                    "farewell": spoken,
                }
            )
            if accepted:
                self._pending_end_call = accepted
                self._pending_farewell_text = str(accepted.get("farewell") or "").strip()
                await self._notify_hangup("initiated", str(accepted.get("reason") or "goal_complete"))
            return
        self._pending_followup_instruction = (
            "The caller already asked to record their details and be contacted later. "
            "Confirm the callback in one short sentence, thank them, say goodbye, "
            "and call end_call with should_end true and reason goal_complete. Do not pitch."
        )

    def _apply_hangup_close_flags(self, reason: str) -> None:
        if reason == "firm_refusal":
            self._firm_refusal_close = True
        if reason in ("goal_complete", "goodbye"):
            self._fast_script_farewell = True

    def _hangup_flow_active(self) -> bool:
        from server.call.call_controller import CallState

        return bool(
            self._pending_end_call
            or self._close_listen_until
            or self._farewell_response_active
            or self._hangup_armed_at
            or self._caller_requested_close
            or self.controller.state == CallState.ENDING
        )

    async def _arm_accepted_hangup(
        self,
        accepted: dict[str, Any],
        *,
        tool_sourced: bool,
    ) -> None:
        reason = str(accepted.get("reason") or "agent_hangup")
        self._commit_pending_hangup(accepted, source="tool" if tool_sourced else "gate")
        if tool_sourced:
            # Gemini's disable operation cancels the active response. Keep the
            # farewell response alive through its audio and response_done.
            await self._set_live_auto_response(False)
        await self._notify_hangup("initiated", reason)

    async def _handle_language_callback_tool(self, event: dict[str, Any]) -> None:
        from server.call.call_context import get as get_ctx
        from server.prompts.agent_voice_rules import language_mismatch_fallback_for

        lang = self._resolve_language()
        line = language_mismatch_fallback_for(lang)
        ctx = get_ctx(self.call_id) if self.call_id else None

        raw_args = event.get("arguments")
        if isinstance(raw_args, str):
            try:
                raw_args = json.loads(raw_args)
            except (json.JSONDecodeError, TypeError):
                raw_args = {}
        args = raw_args if isinstance(raw_args, dict) else {}
        action = args.get("action")
        caller_language = str(args.get("caller_language") or "").strip()[:80]
        summary = str(args.get("summary") or "").strip()[:1200]
        result: dict[str, Any] = {"ok": False, "action": action}
        instruction = ""
        if not ctx or ctx.status != "active":
            result["error"] = "call_not_active"
        elif (self.controller.callback_cancelled or caller_requested_hangup(self._caller_text())
              or caller_firm_refusal(self._caller_text())):
            result["error"] = "caller_opted_out"
        elif (
            args.get("communication_blocked") is not True
            or not caller_language or caller_language.lower() == "unknown"
            or caller_language.split("-")[0].lower() == lang.split("-")[0].lower()
            or (self._caller_text().strip() and len(self._caller_text().split()) < 3)
        ):
            result["error"] = "insufficient_language_barrier_evidence"
            result["instruction"] = (
                f"Answer the caller's meaning in {lang} if understood. Otherwise ask one neutral "
                "clarification. Do not repeat a language reminder or arrange a callback."
            )
        elif action == "remind":
            if self._language_reminder_turn is not None:
                result["error"] = "already_reminded"
                result["instruction"] = "Wait for a later caller turn. Do not repeat the reminder."
            else:
                self._language_reminder_turn = self._language_user_turn
                ctx.language_mismatch_handled = True
                result["ok"] = True
                instruction = (
                    f"Speak only {lang}. Say exactly this once, then wait for the caller. "
                    f"Do not hang up or request a callback on this turn: {line}"
                )
        elif action == "request_callback":
            if (self._language_reminder_turn is None
                    or self._language_user_turn <= self._language_reminder_turn):
                result["error"] = "reminder_and_later_caller_turn_required"
            elif not caller_language or caller_language.lower() == "unknown" or not summary:
                result["error"] = "caller_language_and_english_summary_required"
            else:
                from server.call.call_ledger import call_ledger
                try:
                    meta = call_ledger.read_meta(self.call_id)
                    handoff = meta.get("language_callback") or {
                        "status": "requested", "caller_language": caller_language,
                        "configured_language": lang, "summary": summary,
                    }
                    meta["language_callback"] = handoff
                    call_ledger.write_meta(self.call_id, meta)
                except Exception as exc:
                    result["error"] = "callback_save_failed"
                    log_pstn("language_callback.persist_failed", call_id=self.call_id, error=str(exc)[:160])
                else:
                    ctx.language_callback_summary = handoff["summary"]
                    ctx.language_callback_language = handoff["caller_language"]
                    ctx.callback_request_text = "Language callback requested: " + handoff["summary"]
                    self._callback_request_text = ctx.callback_request_text
                    ctx.callback_close_phase = self._callback_close_phase = "closing_allowed"
                    self._persist_callback_details()
                    result.update(ok=True, callback_recorded=True, handoff=handoff)
                    instruction = (
                        f"Speak only {lang}. Professionally confirm that a callback request in "
                        f"{handoff['caller_language']} has been recorded for the team. "
                        "Do not promise a booked time. Say a brief farewell, then use "
                        "request_end_call with reason=goal_complete."
                    )
        else:
            result["error"] = "invalid_action"
        if instruction:
            result["instruction"] = instruction
        elif "instruction" not in result:
            result["instruction"] = (
                f"Continue only in {lang}. Do not claim a callback was saved. "
                "Respect opt-outs; otherwise correct the missing prerequisite before retrying."
            )
        if self._adapter and event.get("call_id"):
            await self._adapter.submit_function_output(
                call_id=str(event["call_id"]), output=json.dumps(result),
                name="request_language_callback",
            )
            # Gemini resumes from its tool response. OpenAI requires response.create.
            from server.realtime.models import is_gemini_live_voice_model
            if instruction and not is_gemini_live_voice_model(self._live_model or ""):
                await self._start_injected_response(instruction)


    async def _gate_end_call_payload(
        self,
        parsed: dict[str, Any],
        *,
        tool_sourced: bool = False,
    ) -> dict[str, Any] | None:
        parsed = dict(parsed)
        from server.realtime.models import is_gemini_live_voice_model

        user = self._caller_text()
        if (is_gemini_live_voice_model(self._live_model or "")
                and parsed.get("should_end") and parsed.get("reason") == "out_of_scope"
                and (not self._intro_noted or (self._started_at and time.monotonic() - self._started_at < 45))
                and not caller_requested_hangup(user)
                and not caller_firm_refusal(user)):
            self._pending_followup_instruction = _REJECTED_END_CALL_FOLLOWUP
            log_pstn("end_call.rejected", call_id=self.call_id, code="early_out_of_scope")
            return None
        # Model-classified refusal/withdrawal supersedes historical callback slots.
        if parsed.get("should_end") and parsed.get("reason") in {"firm_refusal", "goodbye"}:
            self._cancel_callback()
        if caller_requested_hangup(user) or caller_firm_refusal(user):
            self._cancel_callback()
        if caller_requested_callback(user):
            self._callback_request_text = user
        state = self._sync_callback_close_state()
        callback_close = bool(
            self._callback_request_text
            and not self.controller.callback_cancelled
            and not caller_requested_hangup(user)
            and not caller_firm_refusal(user)
        )
        if callback_close:
            parsed["reason"] = "goal_complete" if parsed.get("should_end") else parsed.get("reason") or "none"
            if state.missing:
                self._callback_collecting_field = state.missing
                self._pending_followup_instruction = self._callback_followup_instruction(state.missing)
                log_pstn(
                    "end_call.callback_deferred",
                    call_id=self.call_id,
                    missing=state.missing,
                )
                return None
            elif parsed.get("should_end"):
                parsed["reason"] = "goal_complete"
                self._persist_callback_details()

        from server.call.call_context import get as get_ctx
        from server.call.call_ledger import call_ledger
        from server.call.memory_manager import memory_manager

        ctx = get_ctx(self.call_id) if self.call_id else None
        snapshot = memory_manager.get_snapshot(self.call_id) if self.call_id else None
        completed = 0
        if self.call_id:
            completed = sum(
                1 for row in call_ledger.read_lines(self.call_id) if row.get("role") == "assistant"
            )
        evidence_user = self._callback_request_text if callback_close else user
        spoken_for_gate = (self._assistant_text or "").strip()
        if tool_sourced:
            spoken_for_gate = spoken_for_gate or str(parsed.get("farewell") or "").strip()
        decision = validate_end_call(
            parsed,
            user_text=evidence_user,
            language=self._resolve_language(),
            call_status=ctx.status if ctx else "active",
            already_armed=bool(ctx and ctx.agent_hangup_armed),
            barge_in_flight=bool(ctx and ctx.barge_in_flight),
            last_stt_partial_at=ctx.last_stt_partial_at if ctx else None,
            completed_turns=completed,
            memory_snapshot=snapshot,
            call_end_policy=ctx.call_end_policy if ctx else None,
            spoken_text=spoken_for_gate,
            callback_close_phase=state.phase,
            tool_sourced=tool_sourced,
        )
        if not decision.accepted:
            log_pstn(
                "end_call.rejected",
                call_id=self.call_id,
                reason=decision.reason,
                code=decision.reject_code,
            )
            if (
                not self._pending_followup_instruction
                and not self._response_had_audio
                and not (self._assistant_text or "").strip()
                and not caller_requested_hangup(user)
                and not caller_firm_refusal(user)
                and not caller_withdrew_callback(user)
            ):
                self._pending_followup_instruction = _REJECTED_END_CALL_FOLLOWUP
            return None
        if caller_requested_hangup(evidence_user) or caller_firm_refusal(evidence_user):
            self._caller_requested_close = True
            self._pending_followup_instruction = None
        if ctx:
            ctx.agent_hangup_armed = True
        farewell = decision.farewell
        if self.controller.callback_cancelled:
            from server.call.hangup_judge import default_farewell_for
            farewell = default_farewell_for(self._resolve_language())
        if callback_close:
            from server.call.hangup_judge import callback_farewell_for

            farewell = callback_farewell_for(self._resolve_language())
            if state.when and self._resolve_language().startswith("en"):
                farewell = f"Your request for a callback {state.when} is noted. Thank you. Goodbye."
        return {
            "should_end": True,
            "reason": decision.reason,
            "farewell": farewell,
        }

    def _schedule_backup_hangup_from_words(self, text: str) -> None:
        """Defer backup hangup so a same-turn request_end_call tool can win (HUP-1)."""
        if self._backup_hangup_task and not self._backup_hangup_task.done():
            self._backup_hangup_task.cancel()

        async def _run() -> None:
            try:
                await asyncio.sleep(0.22)
                if self._hangup_started or self._closed:
                    return
                if self._hangup_arm_source == "tool":
                    return
                await self._arm_hangup_from_caller_words(text)
            except asyncio.CancelledError:
                return

        self._backup_hangup_task = asyncio.create_task(_run())

    async def _arm_hangup_from_transcript_closing(self, text: str) -> None:
        """Arm from STT immediately unless a model response may still emit end_call."""
        explicit = caller_requested_hangup(text) or caller_firm_refusal(text)
        if not explicit and (self._openai_response_id or self._response_open or self._followup_inflight):
            self._schedule_backup_hangup_from_words(text)
            return
        if explicit and self._followup_inflight:
            self._followup_inflight = False
            self._pending_followup_instruction = None
        await self._arm_hangup_from_caller_words(text)

    async def _arm_hangup_from_caller_words(self, text: str) -> None:
        """Close from the caller's words even if the Realtime tool raced STT."""
        if self._hangup_started or self._closed:
            return
        if not (caller_requested_hangup(text) or caller_firm_refusal(text)):
            return
        if caller_wants_to_continue(text) and not caller_requested_hangup(text):
            return
        if caller_firm_refusal(text):
            self._firm_refusal_close = True
        if self._pending_end_call:
            self._caller_requested_close = True
            self._pending_followup_instruction = None
            self._set_hangup_arm_source("backup")
            return
        end_reason = "firm_refusal" if caller_firm_refusal(text) else "goodbye"
        accepted = await self._gate_end_call_payload(
            {
                "should_end": True,
                "reason": end_reason,
                "farewell": self._pending_farewell_text or "",
            }
        )
        if not accepted:
            return
        self._pending_end_call = accepted
        self._pending_farewell_text = self._localized_farewell(str(accepted.get("farewell") or ""))
        self._pending_followup_instruction = None
        self._caller_requested_close = True
        self._resume_after_close = False
        self._awaiting_presence_reply = False
        self._farewell_response_active = True
        self._ending_at = time.monotonic()
        self._apply_hangup_close_flags(str(accepted.get("reason") or end_reason))
        self._note_hangup_armed()
        self.controller.state = CallState.ENDING
        self._set_hangup_arm_source("backup")
        log_pstn("end_call.armed_from_transcript", call_id=self.call_id, text=(text or "")[:80])
        await self._set_live_auto_response(False)
        await self._notify_hangup("initiated", str(accepted.get("reason") or "goodbye"))
        if self._adapter is None:
            return
        if self._openai_response_id:
            self._ignored_response_ids.append(self._openai_response_id)
            self._openai_response_id = ""
        try:
            await self._adapter.cancel_response()
        except Exception:
            pass
        from server.realtime.models import is_gemini_live_voice_model

        prefer_side = is_gemini_live_voice_model(self._live_model or "")
        await self._ensure_hangup_farewell_audio(prefer_side_session=prefer_side)

    async def _maybe_hangup_missed_end_call(self) -> None:
        """Repair a missed end_call only when the caller confirmed they are done."""
        if self._pending_end_call or self._hangup_started or self._farewell_response_active:
            return
        if self._pending_followup_instruction:
            return
        spoken = (self._assistant_text or "").strip()
        if not spoken:
            return
        from server.call.end_call_validate import (
            callback_ready_to_close,
            caller_confirmed_goal_complete,
            caller_requested_callback,
            looks_like_question,
        )
        from server.call.hangup_judge import (
            agent_spoke_closing,
            agent_spoke_disqualification_close,
            caller_polite_thanks_only,
        )
        from server.call.memory_manager import memory_manager

        snapshot = memory_manager.get_snapshot(self.call_id) if self.call_id else None
        user = self._caller_text()
        explicit_end = caller_requested_hangup(user) or caller_firm_refusal(user)
        confirmed_done = caller_confirmed_goal_complete(user)
        callback_done = caller_requested_callback(user) and callback_ready_to_close(user, snapshot)
        callback_scheduled = bool(self._callback_request_text and not self._callback_collecting_field)
        if agent_spoke_disqualification_close(spoken) and agent_spoke_closing(spoken):
            accepted = await self._gate_end_call_payload(
                {
                    "should_end": True,
                    "reason": "goal_complete",
                    "farewell": spoken,
                },
                tool_sourced=True,
            )
            if accepted:
                await self._repair_arm_hangup(
                    accepted, log_event="end_call.repaired_disqualification_close"
                )
            return
        _spoken_goodbye = bool(
            re.search(r"\b(?:goodbye|good day|have a (?:great|good|nice) day)\b", spoken, re.I)
        )
        polite_close_ready = (
            agent_spoke_closing(spoken)
            and not looks_like_question(spoken)
            and (
                confirmed_done
                or callback_done
                or (callback_scheduled and caller_polite_thanks_only(user))
                or (caller_polite_thanks_only(user) and _spoken_goodbye)
            )
        )
        if polite_close_ready:
            accepted = await self._gate_end_call_payload(
                {
                    "should_end": True,
                    "reason": "goal_complete",
                    "farewell": spoken,
                },
                tool_sourced=True,
            )
            if accepted:
                await self._repair_arm_hangup(accepted, log_event="end_call.repaired_polite_close")
            return
        if not explicit_end and not confirmed_done and not callback_done:
            # A model can announce an end without calling a tool, even while
            # answering a question. Do not turn that hallucination into a hangup
            # or silently wait. Recover once per caller turn to avoid a loop.
            false_end = bool(re.search(
                r"\b(?:this|the) call (?:has ended|is (?:over|ended))\b",
                spoken, re.I,
            ))
            if (
                false_end
                and self._unarmed_close_repair_turn != self._language_user_turn
                and self._adapter is not None
            ):
                self._unarmed_close_repair_turn = self._language_user_turn
                self._pending_followup_instruction = (
                    "The call is still connected. Your last farewell was premature; no end action was accepted. "
                    "Briefly apologize in the configured language and answer the caller's last question "
                    "using the business facts. If unclear, ask one clarification instead of guessing. "
                    "Continue the next unfinished script objective. Do not repeat the greeting or farewell. "
                    "Only after the objective and agreed next step are complete, call end_call with "
                    "reason goal_complete and a short farewell in the same turn."
                )
                log_pstn("end_call.recover_unarmed_farewell", call_id=self.call_id)
            return
        if not explicit_end and (looks_like_question(spoken) or not agent_spoke_closing(spoken)):
            return
        accepted = await self._gate_end_call_payload(
            {
                "should_end": False,
                "reason": "none",
                "farewell": spoken,
            }
        )
        if accepted:
            self._commit_pending_hangup(accepted, source="repair")
            log_pstn("end_call.repaired_missed_tool", call_id=self.call_id)
            await self._notify_hangup("initiated", str(accepted.get("reason") or "agent_hangup"))
            if explicit_end and (looks_like_question(spoken) or not agent_spoke_closing(spoken)):
                self._pending_farewell_text = self._localized_farewell()
                self._pending_followup_instruction = (
                    "The caller declined or withdrew consent. Say a brief respectful goodbye only, "
                    "in the configured language. No callback promise, no question, no pitch."
                )
                self._farewell_response_active = True
                self._ending_at = time.monotonic()

    async def _stream_acoustic_filler_if_needed(self, tool_name: str) -> None:
        """Stream an acoustic telephony filler if supported to eliminate dead air during tool routing."""
        try:
            log_pstn("tool_router.acoustic_filler", call_id=self.call_id, tool=tool_name)
            if self.on_agent_wire is not None:
                frame_samples = int(self.sample_rate * 0.02)
                filler_bytes = b"\x00" * (frame_samples * 2 if self.tts_output_codec == "linear16" else frame_samples)
                res = self.on_agent_wire(filler_bytes)
                if asyncio.iscoroutine(res):
                    await res
        except Exception as exc:
            log_pstn("tool_router.acoustic_filler.failed", call_id=self.call_id, error=str(exc))

    async def _handle_event(self, event: dict[str, Any]) -> None:
        kind = str(event.get("type") or "")
        if self._closed or self.controller.state == CallState.ENDED:
            return
        if kind == "response_done" and event.get("usage_only"):
            # A billing trailer is independent of the currently audible turn,
            # including trailers for an interrupted or superseded response.
            usage = event.get("usage")
            if isinstance(usage, dict) and usage and self.call_id:
                self._run_post_turn(record_realtime_voice_usage(
                    call_id=self.call_id, usage=usage,
                    llm_model=self._live_model or "gpt-realtime-2.1-mini",
                    started_at=self._started_at,
                ))
            return
        if self._hangup_started and kind not in {"cancelled"}:
            return
        if kind in {"audio_delta", "assistant_transcript_delta", "assistant_transcript", "function_call"}:
            if self._is_stale_openai_event(event):
                return
            self._response_activity_at = time.monotonic()
        if kind == "speech_started":
            agent_out = self._agent_audio_playing()
            if self._deferred_greeting_playing:
                log_pstn("realtime_voice.echo_ignore", call_id=self.call_id, reason="deferred_greeting")
                return
            if self._deferred_greeting_armed:
                self._caller_speaking = True
                self._last_activity_at = time.monotonic()
                self._silence_prompted = False
                self._set_phase(PHASE_LISTENING)
                self._arm_pickup_finish(fast=True)
                return
            if agent_out and not self._aec_barge_open:
                log_pstn("realtime_voice.echo_ignore", call_id=self.call_id)
                return
            self._suppress_until_user = False
            self._caller_speaking = True
            self._last_activity_at = time.monotonic()
            self._silence_prompted = False
            if agent_out:
                await self._commit_local_barge()
            else:
                self._set_phase(PHASE_LISTENING)
            return
        if kind == "speech_stopped":
            self._caller_speaking = False
            self._last_activity_at = time.monotonic()
            agent_out = self._agent_audio_playing()
            if not (agent_out and not self._aec_barge_open):
                self._suppress_until_user = False
                if not self._deferred_greeting_armed:
                    pstn_media_flow.emit(
                        self.call_id or "", "vad_speech_stopped", "inbound",
                        turn_id=self.current_turn_id,
                    )
            if self._deferred_greeting_armed:
                self._arm_pickup_finish()
            return
        if kind == "user_transcript":
            text = str(event.get("text") or "").strip()
            if not text:
                return
            if event.get("final"):
                if self._should_drop_user_final(text):
                    log_pstn(
                        "realtime_voice.transcript_drop",
                        call_id=self.call_id,
                        text=text[:80],
                    )
                    return
                self._user_partial = text
                self._last_user_final_text = text
                self._language_user_turn += 1
                self._caller_speaking = False
                self._last_activity_at = time.monotonic()
                closing = caller_requested_hangup(text) or caller_firm_refusal(text)
                awaiting_close = bool(self._pending_end_call or self._close_listen_until)
                reopen = (not closing) and (
                    awaiting_close or self._resume_after_close
                )
                stay = (not closing) and (
                    (self._awaiting_presence_reply and _is_silence_prompt_ack(text))
                    or ((reopen or self._awaiting_presence_reply) and _is_presence_reply(text))
                )
                self._silence_prompted = False
                if awaiting_close and not closing:
                    from server.call.hangup_judge import agent_spoke_closing

                    farewell_already_spoken = bool(
                        self._farewell_complete
                        or agent_spoke_closing(self._assistant_text or "")
                        or agent_spoke_closing(self._last_ledger_assistant or "")
                    )
                    if (
                        self._uses_fast_hangup()
                        and not self._farewell_audio_engaged()
                        and farewell_already_spoken
                    ):
                        log_pstn("hangup.fast_ack_pending", call_id=self.call_id, text=text[:80])
                        await self._finish_hangup()
                        return
                    if self._firm_refusal_close and (
                        _is_simple_hello(text)
                        or bool(re.fullmatch(r"(?i)(?:hello[!,.]?\s*)+$", (text or "").strip()))
                    ):
                        await self._finish_hangup()
                        return
                    if _is_simple_hello(text) or not (
                        caller_wants_to_continue(text) or _is_presence_reply(text)
                    ):
                        self._resume_after_close = False
                        self._awaiting_presence_reply = False
                        self._close_listen_until = 0.0
                        if self.call_id and self._persist_user_turn_to_ledger():
                            from server.call.call_ledger import call_ledger

                            await call_ledger.append_user_turn(self.call_id, text)
                        log_pstn(
                            "hangup.fast_ack" if _is_simple_hello(text) or self._uses_fast_hangup() else "hangup.close_ack",
                            call_id=self.call_id,
                            text=text[:80],
                        )
                        if self._adapter is not None and not self._farewell_audio_engaged():
                            from server.realtime.models import is_gemini_live_voice_model

                            await self._ensure_hangup_farewell_audio(
                                prefer_side_session=is_gemini_live_voice_model(self._live_model or "")
                            )
                            if not self._farewell_audio_engaged():
                                return
                        await self._finish_hangup()
                        return
                    self._abort_in_progress_hangup()
                if closing:
                    self._resume_after_close = False
                    self._awaiting_presence_reply = False
                    self._cancel_callback()
                self._suppress_until_user = False
                first_user = not self._heard_user_turn
                self._heard_user_turn = True
                if not (_is_pickup_phrase(text) or _is_availability_check(text)):
                    self._heard_content_turn = True
                if caller_requested_callback(text) and not closing:
                    self._callback_request_text = text
                if not closing:
                    self._capture_callback_detail(text)
                    self._maybe_mirror_caller_language(text)
                self._sync_callback_close_state()
                if self.call_id:
                    from server.call.caller_detail_capture import caller_detail_memory_operations
                    from server.call.call_ledger import call_ledger
                    from server.call.memory_manager import memory_manager

                    line: dict[str, Any] = {}
                    if self._persist_user_turn_to_ledger():
                        line = await call_ledger.append_user_turn(self.call_id, text)
                    detail_ops = [] if closing else caller_detail_memory_operations(text)
                    if detail_ops and line:
                        try:
                            memory_manager.apply_proposals(
                                self.call_id,
                                detail_ops,
                                turn_seq=int(line.get("seq") or 0),
                                source="realtime_caller_detail",
                            )
                        except Exception as exc:
                            log_pstn(
                                "realtime_voice.caller_detail_memory_failed",
                                call_id=self.call_id,
                                error=str(exc)[:160],
                            )
                pstn_media_flow.emit(
                    self.call_id or "",
                    "stt_final",
                    "inbound",
                    detail=text[:200],
                    turn_id=self.current_turn_id,
                )
                if closing:
                    if caller_firm_refusal(text):
                        self._firm_refusal_close = True
                    await self._arm_hangup_from_transcript_closing(text)
                    return
                if stay:
                    self._resume_after_close = False
                    self._awaiting_presence_reply = False
                    await self._handle_stay_on_line(text)
                    return
                self._resume_after_close = False
                self._awaiting_presence_reply = False
                if self._adapter is not None:
                    from server.call.caller_detail_capture import unclear_name_phrase

                    if unclear_name_phrase(text):
                        log_pstn("realtime_voice.unclear_name", call_id=self.call_id)
                        try:
                            await self._adapter.cancel_response()
                        except Exception:
                            pass
                        try:
                            await self._start_injected_response(_UNCLEAR_NAME_FOLLOWUP)
                        except Exception as exc:
                            log_pstn(
                                "realtime_voice.unclear_name.failed",
                                call_id=self.call_id,
                                error=str(exc)[:160],
                            )
                            self._pending_followup_instruction = _UNCLEAR_NAME_FOLLOWUP
                    elif _is_pickup_phrase(text) or _is_availability_check(text):
                        await self._handle_pickup_or_availability(text, first_user=first_user)
            else:
                self._user_partial = text
            return
        if kind == "response_created":
            self._response_activity_at = time.monotonic()
            rid = self._event_response_id(event)
            if rid and (rid in self._ignored_response_ids or rid == self._openai_response_id):
                return
            if (
                self._greeting_waiting()
                or self._greeting_protected()
                or (self._pickup_suppressed() and not self._heard_content_turn)
            ) and self._adapter is not None:
                if rid:
                    self._ignored_response_ids.append(rid)
                try:
                    await self._adapter.cancel_response(response_id=rid or None)
                except Exception as exc:
                    log_pstn("greeting.deferred.cancel.failed", call_id=self.call_id, error=str(exc)[:160])
                return
            if not self._intro_noted and self._deferred_greeting_frames and self._adapter is not None:
                if rid:
                    self._ignored_response_ids.append(rid)
                try:
                    await self._adapter.cancel_response(response_id=rid or None)
                except Exception as exc:
                    log_pstn("greeting.deferred.cancel.failed", call_id=self.call_id, error=str(exc)[:160])
                return
            # A previous answer having audio is not evidence that this response
            # is stale. VAD responses can arrive before the caller transcript.
            if self._openai_response_id:
                self._ignored_response_ids.append(self._openai_response_id)
            self._followup_inflight = False
            self._suppress_until_user = False
            self._response_open = True
            self._barge_generation = None
            rid = self._event_response_id(event)
            if rid:
                self._openai_response_id = rid
            self.current_turn_id = self.current_turn_id or uuid.uuid4().hex[:12]
            self.current_generation_id = uuid.uuid4().hex[:12]
            self._assistant_text = ""
            self._response_had_audio = False
            self._out_pcm.clear()
            self._out_resampler.reset()
            self._tts_started_emitted = False
            if self.playback is not None and hasattr(self.playback, "set_current_generation"):
                self.playback.set_current_generation(self.current_generation_id)
            self._set_phase(PHASE_SPEAKING)
            pstn_media_flow.emit(self.call_id or "", "llm_started", "outbound", turn_id=self.current_turn_id)
            return
        if kind == "audio_delta":
            if self._is_stale_openai_event(event):
                return
            if self._deferred_greeting_playing:
                return
            if not self._intro_noted and self._deferred_greeting_frames:
                return
            pcm = event.get("pcm") or b""
            if pcm:
                self._response_had_audio = True
                self._set_tts_active(True)
                if not self._tts_started_emitted:
                    self._tts_started_emitted = True
                    pstn_media_flow.emit(
                        self.call_id or "",
                        "tts_started",
                        "outbound",
                        detail="openai-realtime",
                        turn_id=self.current_turn_id,
                    )
                pstn_media_flow.emit(
                    self.call_id or "",
                    "tts_audio",
                    "outbound",
                    bytes=len(pcm),
                    codec="pcm16",
                    sample_rate=REALTIME_PCM_RATE,
                    turn_id=self.current_turn_id,
                )
                await self._emit_realtime_pcm(pcm)
            return
        if kind == "assistant_transcript_delta":
            # Deltas may split words or contain only the space between words.
            # Sanitize the complete turn, not each fragment (which strips it).
            self._assistant_text += str(event.get("delta") or "")
            return
        if kind == "assistant_transcript":
            text = self._sanitize_live_assistant_text(str(event.get("text") or "").strip())
            if text:
                self._assistant_text = text
            return
        if kind == "function_call":
            tool_name = str(event.get("name") or "")
            arguments = event.get("arguments") or "{}"
            parsed_args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
            call_id = str(event.get("call_id") or "")

            if tool_name == "call_action":
                await self._handle_call_action(event)
                return
            if tool_name == "request_language_callback":
                await self._handle_language_callback_tool(event)
                return

            # --- DEDICATED VOXLY TOOL ROUTER DISPATCH ---
            is_dispatchable_tool = (
                bool(self._agent_tools and (
                    tool_name in self._agent_tools
                    or any(tool_name.lower().startswith(t.lower()) for t in self._agent_tools)
                ))
                or tool_name.startswith("nango_")
                or tool_name.startswith("composio_")
            )
            if is_dispatchable_tool and tool_name not in LIVE_HANGUP_TOOL_NAMES:
                log_pstn("tool_router.dispatch_start", call_id=self.call_id, tool=tool_name)

                # 1. FAIL-CLOSED TENANT CHECK (Fix #2: Zero "default" fallback)
                if (not self._tenant_id or not self._agent_id) and self.call_id:
                    try:
                        from server.call.call_ledger import call_ledger
                        meta = call_ledger.read_meta(self.call_id) or {}
                        if not self._tenant_id:
                            self._tenant_id = meta.get("tenant_id")
                        if not self._agent_id:
                            self._agent_id = meta.get("agent_id")
                    except Exception:
                        pass

                if not self._tenant_id:
                    log_pstn("tool_router.rejected_missing_tenant", call_id=self.call_id, tool=tool_name)
                    if call_id and self._adapter is not None:
                        try:
                            await self._adapter.submit_function_output(
                                call_id=call_id,
                                output=json.dumps({"error": "Unauthorized: Missing tenant context"}),
                                name=tool_name,
                            )
                        except Exception:
                            pass
                    return

                # 2. Trigger acoustic telephony bridge (no dead air)
                await self._stream_acoustic_filler_if_needed(tool_name)

                # 3. Route through Voxly Tool Router
                from server.services.tool_router import tool_router

                tool_output = await tool_router.route_and_execute(
                    tenant_id=str(self._tenant_id),
                    agent_id=str(self._agent_id) if self._agent_id else None,
                    call_id=str(self.call_id or ""),
                    tool_name=tool_name,
                    arguments=parsed_args,
                )

                # 4. Submit output back to speech adapter
                if call_id and self._adapter is not None:
                    try:
                        await self._adapter.submit_function_output(
                            call_id=call_id,
                            output=json.dumps(tool_output),
                            name=tool_name,
                        )
                    except Exception:
                        pass
                log_pstn("tool_router.dispatch_complete", call_id=self.call_id, tool=tool_name)
                return

            if tool_name not in LIVE_HANGUP_TOOL_NAMES:
                return
            parsed = parse_live_hangup_tool(tool_name, event.get("arguments"))
            accepted: dict[str, Any] | None = None
            if parsed is not None and not parsed.get("should_end"):
                log_pstn("end_call.tool_declined", call_id=self.call_id, tool=tool_name)
            elif parsed and parsed.get("should_end"):
                if self._pending_end_call or self._farewell_response_active:
                    accepted = self._pending_end_call or parsed
                    log_pstn("hangup.duplicate_tool", call_id=self.call_id, tool=tool_name)
                else:
                    accepted = await self._gate_end_call_payload(parsed, tool_sourced=True)
                    if accepted:
                        await self._arm_accepted_hangup(accepted, tool_sourced=True)
            call_id = str(event.get("call_id") or "")
            if call_id and self._adapter is not None:
                try:
                    await self._adapter.submit_function_output(
                        call_id=call_id,
                        output=json.dumps(
                            {
                                "ok": bool(accepted or self._farewell_response_active),
                                "deferred": bool(self._pending_followup_instruction),
                                "missing": self._callback_collecting_field,
                            }
                        ),
                        name=tool_name or "request_end_call",
                    )
                except Exception:
                    pass
            return
        if kind in ("response_done", "cancelled"):
            if self._is_stale_openai_event(event):
                return
            self._assistant_text = self._sanitize_live_assistant_text(self._assistant_text)
            if kind == "response_done" and not event.get("failed") and not event.get("provider_interrupted"):
                # Preserve the final partial frame of ordinary answers too.
                await self._flush_agent_pcm_to_wire()
            if event.get("provider_interrupted"):
                await self.interrupt_tts(cancel_provider=False)
                if self._on_barge:
                    try:
                        await asyncio.wait_for(self._on_barge(), timeout=1.0)
                    except Exception as exc:
                        log_pstn("playback.remote_clear.failed", call_id=self.call_id, error=str(exc)[:160])
                if not self._hangup_flow_active():
                    self._abort_in_progress_hangup()
            self._set_tts_active(False)
            self._response_open = False
            self._followup_inflight = False
            self._last_activity_at = time.monotonic()
            if kind == "response_done" and event.get("failed"):
                await self._runtime_end("response_failure")
                return
            if kind == "cancelled":
                self._response_open = False
                self._suppress_until_user = False
            if (
                kind == "response_done"
                and not event.get("usage_only")
                and self._assistant_text.strip()
                and not self._intro_noted
                and not self._deferred_greeting_frames
            ):
                noter = getattr(self._adapter, "note_assistant_text", None) if self._adapter else None
                if callable(noter):
                    try:
                        await noter(self._assistant_text.strip())
                        self._intro_noted = True
                    except Exception as exc:
                        log_pstn(
                            "realtime_voice.note_assistant.failed",
                            call_id=self.call_id,
                            error=str(exc)[:160],
                        )
            if (
                kind == "response_done"
                and not event.get("usage_only")
                and self._assistant_text
                and self.call_id
            ):
                from server.call.call_ledger import call_ledger

                line = self._assistant_text.strip()
                if line and is_generic_inbound_greeting(line):
                    line = ""
                if (
                    line
                    and line != self._last_ledger_assistant
                    and self._persist_live_transcript_ledger()
                ):
                    self._last_ledger_assistant = line
                    self._run_post_turn(call_ledger.append_assistant_turn(self.call_id, line))
            if kind == "response_done":
                await self._maybe_resume_callback_close()
                await self._maybe_hangup_missed_end_call()
            usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
            if usage and self.call_id:
                pstn_media_flow.emit(
                    self.call_id,
                    "llm_usage",
                    "outbound",
                    detail=str(usage.get("input_audio_tokens") or 0),
                    turn_id=self.current_turn_id,
                )
                if kind == "response_done":
                    try:
                        self._run_post_turn(record_realtime_voice_usage(
                            call_id=self.call_id,
                            usage=usage,
                            llm_model=self._live_model or "gpt-realtime-2.1-mini",
                            user_text=self._user_partial,
                            assistant_text=self._assistant_text,
                            started_at=self._started_at,
                        ))
                    except Exception as exc:
                        log_pstn(
                            "realtime_voice.usage.failed",
                            call_id=self.call_id,
                            error=str(exc)[:160],
                        )
            if kind == "response_done" and self._pending_followup_instruction and self._adapter is not None:
                if self._hangup_flow_active():
                    self._pending_followup_instruction = None
                else:
                    instruction = self._pending_followup_instruction
                    await self._start_injected_response(instruction)
                    return
            if kind == "response_done" and self._pending_end_call and not self._hangup_started:
                if self._firm_refusal_close:
                    self._pending_followup_instruction = None
                if self._farewell_response_active:
                    await self._finalize_hangup_after_farewell()
                    return
                await self._finalize_hangup_after_farewell()
                return
            if kind == "response_done":
                self._response_open = False
                if self._assistant_text.strip() or self._response_had_audio:
                    self._suppress_until_user = True
            if self._on_turn_audio_done:
                try:
                    await self._on_turn_audio_done()
                except Exception:
                    pass
            if self._phase != PHASE_ENDED:
                self._set_phase(PHASE_LISTENING)
            return
        if kind == "error":
            log_pstn("realtime_voice.error", call_id=self.call_id, error=str(event.get("message") or "")[:200])

    def _cancel_pickup_finish(self) -> None:
        task = self._pickup_finish_task
        self._pickup_finish_task = None
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()

    def _queue_pending_inbound(self, pcm16: bytes) -> None:
        self._pending_inbound.append(pcm16)
        self._pending_inbound_bytes += len(pcm16)
        while self._pending_inbound and self._pending_inbound_bytes > _PENDING_INBOUND_MAX_BYTES:
            dropped = self._pending_inbound.pop(0)
            self._pending_inbound_bytes -= len(dropped)

    async def _flush_pending_inbound(self) -> None:
        pending = self._pending_inbound
        self._pending_inbound = []
        self._pending_inbound_bytes = 0
        if not pending:
            return
        log_pstn(
            "realtime_voice.inbound.flush",
            call_id=self.call_id,
            frames=len(pending),
        )
        for pcm in pending:
            if self._closed:
                return
            await self.feed_user_pcm16(pcm)

    def _note_pickup_rms(self, rms: int) -> None:
        self._pickup_rms_logs += 1
        if self._pickup_rms_logs not in (1, 10, 25, 50) and self._pickup_rms_logs < 50:
            return
        if self._pickup_rms_logs > 50:
            return
        log_pstn(
            "realtime_voice.pickup_rms",
            call_id=self.call_id,
            n=self._pickup_rms_logs,
            rms=int(rms),
            speech_ms=int(self._pickup_speech_ms),
            quiet_ms=int(self._pickup_quiet_ms),
            dip_ms=int(self._pickup_dip_ms),
        )

    def _cancel_pickup_fallback(self) -> None:
        task = self._pickup_fallback_task
        self._pickup_fallback_task = None
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()

    def _arm_pickup_fallback(self) -> None:
        if not self._deferred_greeting_armed or self._closed:
            return
        self._cancel_pickup_fallback()
        self._pickup_fallback_task = asyncio.create_task(
            self._pickup_fallback_greet(),
            name=f"rt-pickup-fallback-{self.call_id}",
        )

    async def _pickup_fallback_greet(self) -> None:
        try:
            await asyncio.sleep(_PICKUP_FALLBACK_SEC)
        except asyncio.CancelledError:
            return
        if self._closed or not self._deferred_greeting_armed:
            return
        log_pstn(
            "realtime_voice.pickup_fallback",
            call_id=self.call_id,
            speech_ms=int(self._pickup_speech_ms),
        )
        self._schedule_deferred_greeting()

    def _arm_pickup_finish(self, *, fast: bool = False) -> None:
        if not self._deferred_greeting_armed or self._closed:
            return
        min_ms = _PICKUP_MIN_SPEECH_FAST_MS if fast else _PICKUP_MIN_SPEECH_MS
        if not fast and self._pickup_speech_ms < min_ms:
            return
        debounce = _PICKUP_VAD_FAST_DEBOUNCE_SEC if fast else _PICKUP_VAD_DEBOUNCE_SEC
        self._cancel_pickup_finish()
        self._pickup_finish_task = asyncio.create_task(
            self._debounce_pickup_then_greet(debounce),
            name=f"rt-pickup-finish-{self.call_id}",
        )

    async def _debounce_pickup_then_greet(self, debounce_sec: float = _PICKUP_VAD_DEBOUNCE_SEC) -> None:
        try:
            await asyncio.sleep(debounce_sec)
        except asyncio.CancelledError:
            return
        if self._closed or not self._deferred_greeting_armed or self._caller_speaking:
            return
        self._schedule_deferred_greeting()

    def _schedule_deferred_greeting(self) -> None:
        if not self._deferred_greeting_armed or self._closed:
            return
        self._cancel_pickup_finish()
        self._cancel_pickup_fallback()
        task = self._deferred_greeting_task
        if task is not None and not task.done():
            return
        self._deferred_greeting_task = asyncio.create_task(
            self._on_first_user_speech_deferred_greeting(),
            name=f"rt-deferred-greeting-{self.call_id}",
        )

    async def _on_first_user_speech_deferred_greeting(self) -> None:
        if not self._deferred_greeting_armed or self._closed:
            return
        self._deferred_greeting_armed = False
        log_pstn(
            "realtime_voice.pickup_consumed",
            call_id=self.call_id,
            speech_ms=int(self._pickup_speech_ms),
        )
        if self._adapter is not None:
            try:
                await self._adapter.cancel_response()
            except Exception as exc:
                log_pstn("greeting.deferred.cancel.failed", call_id=self.call_id, error=str(exc)[:160])
        await self._play_deferred_greeting()

    async def _wait_greeting_tail(self) -> None:
        """Keep VAD off until leftover greeting RTP has left the phone."""
        queued_ms = 0.0
        if self.playback is not None:
            try:
                queued_ms = float(self.playback.queued_ms())
            except Exception:
                queued_ms = 0.0
        hold_s = min(0.5, max(0.0, queued_ms / 1000.0 + 0.04 if queued_ms else 0.0))
        if hold_s <= 0:
            return
        self._greeting_protect_until = time.monotonic() + hold_s
        try:
            await asyncio.sleep(hold_s)
        except asyncio.CancelledError:
            return

    async def _play_deferred_greeting(self) -> None:
        frames = self._deferred_greeting_frames or []
        text = (self._deferred_greeting_text or "").strip()
        if not frames or not text or self._closed:
            return

        pickup = (self._pickup_user_text or self._last_user_final_text or "").strip()
        if pickup and (caller_requested_hangup(pickup) or caller_firm_refusal(pickup)):
            self._deferred_greeting_armed = False
            self._deferred_greeting_playing = False
            if self.call_id and self._persist_user_turn_to_ledger():
                from server.call.call_ledger import call_ledger

                await call_ledger.append_user_turn(self.call_id, pickup)
            await self._arm_hangup_from_transcript_closing(pickup)
            return

        self._deferred_greeting_playing = True
        self._set_phase(PHASE_INTRO)
        self._set_tts_active(True)
        self.current_turn_id = self.current_turn_id or uuid.uuid4().hex[:12]
        self.current_generation_id = uuid.uuid4().hex[:12]
        if self.playback is not None and hasattr(self.playback, "set_current_generation"):
            self.playback.set_current_generation(self.current_generation_id)
        log_pstn(
            "greeting.deferred.play",
            call_id=self.call_id,
            frames=len(frames),
            chars=len(text),
        )
        try:
            for wire in frames:
                if self._closed:
                    break
                if self.call_id:
                    self._archive.enqueue(self.call_id, "agent", wire)
                self._wire_frames_out += 1
                await self.on_agent_wire(wire)
        finally:
            self._set_tts_active(False)
            self._deferred_greeting_playing = False

        if self._closed:
            return

        await self._wait_greeting_tail()

        noter = getattr(self._adapter, "note_assistant_text", None) if self._adapter else None
        history_clean = bool(getattr(self._adapter, "opening_history_clean", False)
                             and getattr(self._adapter, "supports_external_opening_note", False))
        if callable(noter) and not history_clean:
            try:
                await noter(text)
            except Exception as exc:
                log_pstn(
                    "realtime_voice.note_assistant.failed",
                    call_id=self.call_id,
                    error=str(exc)[:160],
                )
        delivered = getattr(self._adapter, "note_opening_delivered", None) if self._adapter else None
        if callable(delivered):
            try:
                if history_clean:
                    await delivered(spoken_line=text)
                elif not history_clean:
                    await delivered()
            except Exception as extra:
                log_pstn(
                    "realtime_voice.opening_delivered.failed",
                    call_id=self.call_id,
                    error=str(extra)[:160],
                )
        if pickup and self.call_id and self._persist_user_turn_to_ledger():
            from server.call.call_ledger import call_ledger

            await call_ledger.append_user_turn(self.call_id, pickup)
        self._intro_noted = True
        self._pickup_user_text = ""
        self._user_partial = ""
        if self._adapter is not None:
            try:
                await self._adapter.cancel_response()
            except Exception as exc:
                log_pstn("greeting.deferred.cancel.failed", call_id=self.call_id, error=str(exc)[:160])
            clearer = getattr(self._adapter, "clear_input_audio", None)
            if callable(clearer):
                try:
                    await clearer()
                except Exception:
                    pass
        auto_response = getattr(self._adapter, "set_auto_response", None) if self._adapter else None
        if callable(auto_response):
            try:
                await auto_response(True)
            except Exception as exc:
                log_pstn(
                    "greeting.deferred.vad_restore.failed",
                    call_id=self.call_id,
                    error=str(exc)[:160],
                )
        self._greeting_protect_until = 0.0
        if self.call_id and self._persist_live_transcript_ledger():
            from server.call.call_ledger import call_ledger

            await call_ledger.append_assistant_turn(self.call_id, text)
            self._last_ledger_assistant = text
        log_pstn("greeting.deferred.done", call_id=self.call_id)
        self._set_phase(PHASE_LISTENING)

    async def _emit_realtime_pcm(self, pcm24: bytes) -> None:
        if self.emission_blocked() or not pcm24:
            return
        pcm_out = self._out_resampler.feed(pcm24)
        if not pcm_out:
            return
        if self.current_output_codec == "PCMU":
            wire = pcm16_to_mulaw(pcm_out, sample_rate=self.sample_rate)
            self._out_pcm.extend(wire)
        else:
            self._out_pcm.extend(pcm_out)
        frame = self._frame_bytes()
        while len(self._out_pcm) >= frame:
            chunk = bytes(self._out_pcm[:frame])
            del self._out_pcm[:frame]
            if self.call_id:
                self._archive.enqueue(self.call_id, "agent", chunk)
            self._wire_frames_out += 1
            await self.on_agent_wire(chunk)

    async def _flush_agent_pcm_to_wire(self) -> None:
        """Send leftover farewell samples so hangup does not drop the last syllable."""
        leftover = b""
        try:
            leftover = self._out_resampler.flush()
        except Exception:
            leftover = b""
        if leftover:
            if self.current_output_codec == "PCMU":
                try:
                    leftover = pcm16_to_mulaw(leftover, sample_rate=self.sample_rate)
                except Exception:
                    leftover = b""
            if leftover:
                self._out_pcm.extend(leftover)
        frame = self._frame_bytes()
        if self._out_pcm and len(self._out_pcm) < frame:
            silence = b"\xff" if self.current_output_codec == "PCMU" else b"\x00"
            self._out_pcm.extend(silence * (frame - len(self._out_pcm)))
        while len(self._out_pcm) >= frame:
            chunk = bytes(self._out_pcm[:frame])
            del self._out_pcm[:frame]
            if self.call_id:
                self._archive.enqueue(self.call_id, "agent", chunk)
            self._wire_frames_out += 1
            try:
                await self.on_agent_wire(chunk)
            except Exception:
                break

    async def _drain_agent_archive(self) -> None:
        leftover = b""
        try:
            leftover = self._out_resampler.flush()
        except Exception:
            leftover = b""
        if leftover:
            if self.current_output_codec == "PCMU":
                try:
                    leftover = pcm16_to_mulaw(leftover, sample_rate=self.sample_rate)
                except Exception:
                    leftover = b""
            if leftover:
                self._out_pcm.extend(leftover)
        if self._out_pcm and self.call_id:
            self._archive.enqueue(self.call_id, "agent", bytes(self._out_pcm))
            self._out_pcm.clear()
        try:
            await self._archive.close()
        except Exception:
            pass

    async def _stop_live_media_session(self) -> None:
        """Stop Gemini/OpenAI Live websocket and pump — caller leg may already be down."""
        sidecar_sec = 0.0
        if self._caller_stt is not None:
            sidecar_sec = float(self._caller_stt.billed_audio_sec or 0)
            try:
                await self._caller_stt.close()
            except Exception as exc:
                log_pstn("realtime_voice.caller_stt.close_failed", call_id=self.call_id, error=str(exc)[:120])
            self._caller_stt = None
        try:
            await self._finalize_live_transcript_usage(sidecar_sec=sidecar_sec or None)
        except Exception as exc:
            log_pstn("realtime_voice.live_tx_usage.failed", call_id=self.call_id, error=str(exc)[:120])
        if self._pump_task and self._pump_task is not asyncio.current_task() and not self._pump_task.done():
            self._pump_task.cancel()
            try:
                await self._pump_task
            except (asyncio.CancelledError, Exception):
                pass
        self._pump_task = None
        if self._adapter is not None:
            try:
                await self._adapter.close()
            except Exception as exc:
                log_pstn("hangup.live_close.failed", call_id=self.call_id, error=str(exc)[:160])
        self._adapter = None
        if self.call_id:
            try:
                from server.realtime.voice_manager import realtime_voice_manager

                await realtime_voice_manager.destroy(self.call_id)
            except Exception as exc:
                log_pstn("hangup.live_destroy.failed", call_id=self.call_id, error=str(exc)[:160])

    def _run_post_turn(self, work) -> None:
        async def run():
            try:
                await work
            except Exception as exc:
                log_pstn("post_turn.failed", call_id=self.call_id, error=str(exc)[:160])
        task = asyncio.create_task(run(), name=f"rt-post-turn-{self.call_id}")
        self._post_turn_tasks.add(task)
        task.add_done_callback(self._post_turn_tasks.discard)

    async def _background_after_fast_hangup(self, reason: str, spoke_farewell: bool) -> None:
        from server.call.close_call_executor import canonical_lifecycle_reason
        from server.call.callback_close import mark_hangup_executed
        from server.services.pstn_media_flow import pstn_media_flow

        canonical = canonical_lifecycle_reason(reason)
        try:
            await self._stop_live_media_session()
            if self._post_turn_tasks:
                await asyncio.gather(*tuple(self._post_turn_tasks), return_exceptions=True)
            await self._drain_agent_archive()
            try:
                await self._archive.close()
            except Exception:
                pass
            if self.call_id:
                from server.call.call_lifecycle_service import call_lifecycle_service

                await call_lifecycle_service.end(self.call_id, reason=canonical)
                pstn_media_flow.emit(
                    self.call_id,
                    "hangup_complete",
                    "internal",
                    detail=canonical,
                    extra={"fast_hangup": True, "spoke_farewell": spoke_farewell},
                )
            mark_hangup_executed(self.call_id)
            log_pstn("hangup.background.done", call_id=self.call_id, reason=canonical)
        except Exception as exc:
            log_pstn("hangup.background.failed", call_id=self.call_id, error=str(exc)[:160])

    async def _fast_disconnect_after_farewell(self, reason: str, spoke_farewell: bool) -> None:
        """Telnyx hangup + Live teardown first; ledger/lifecycle in background."""
        from server.services.pstn_media_flow import pstn_media_flow

        self._cancel_hangup_force_task()
        self._close_listen_until = 0.0
        self._run_post_turn(self._notify_hangup("disconnecting", reason))
        if self.call_id:
            pstn_media_flow.emit(
                self.call_id,
                "hangup_closing",
                "internal",
                detail=reason,
                status="processing",
            )
        if self._on_remote_hangup:
            try:
                await self._on_remote_hangup()
            except (Exception, asyncio.CancelledError):
                # Do not latch success on a failed/cancelled provider command.
                self._hangup_started = False
                raise
        self._closed = True
        self._set_phase(PHASE_CLOSING)
        self.controller.end(reason)
        self._set_phase(PHASE_ENDED)
        log_pstn("realtime_voice.ended", call_id=self.call_id, end_reason=reason, fast_hangup=True)
        task = self._background_hangup_task
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()
        self._background_hangup_task = asyncio.create_task(
            self._background_after_fast_hangup(reason, spoke_farewell),
            name=f"rt-hangup-bg-{self.call_id}",
        )
        _BACKGROUND_HANGUP_TASKS.add(self._background_hangup_task)
        self._background_hangup_task.add_done_callback(_BACKGROUND_HANGUP_TASKS.discard)

    async def _finish_hangup(self) -> None:
        if self._hangup_started or self._phase == PHASE_ENDED:
            return
        if self._caller_speaking and not self._farewell_complete:
            log_pstn("hangup.skip_caller_talking", call_id=self.call_id)
            return
        self._hangup_started = True
        try:
            self.controller.state = CallState.ENDING
            self._ending_at = self._ending_at or time.monotonic()
            from server.call.hangup_judge import agent_spoke_closing
            from server.call.natural_hangup import (
                HANGUP_PLAYBACK_TIMEOUT_SEC,
                wait_for_farewell_playback,
            )

            reason = str((self._pending_end_call or {}).get("reason") or "agent_hangup")
            farewell_required = bool((self._pending_end_call or {}).get("farewell_required", True))
            spoke = bool(self._response_had_audio)
            if not farewell_required:
                spoke = spoke or bool(
                    self._pending_farewell_text
                    or agent_spoke_closing(self._assistant_text or "")
                    or agent_spoke_closing(self._last_ledger_assistant or "")
                )
            await self._flush_agent_pcm_to_wire()
            playback_cap = HANGUP_PLAYBACK_TIMEOUT_SEC
            wait_start = 0.0
            heard = await wait_for_farewell_playback(
                self._farewell_still_on_the_line,
                timeout_sec=playback_cap,
                wait_for_start_sec=wait_start,
            )
            if not heard and spoke:
                log_pstn("hangup.playback_no_audio", call_id=self.call_id, spoke=True)
            if self._closed or (self._caller_speaking and not self._farewell_complete) or not self._hangup_started:
                if self._hangup_started and self._caller_speaking:
                    self._hangup_started = False
                    log_pstn("hangup.defer_caller_speaking", call_id=self.call_id)
                    return
                if self._hangup_started and not self._closed:
                    self._abort_in_progress_hangup()
                return
            await self._fast_disconnect_after_farewell(reason, spoke or heard)

        except (Exception, asyncio.CancelledError):
            self._hangup_started = False
            raise

    async def speak(
        self,
        text: str,
        *,
        speaker: str | None = None,
        language_code: str | None = None,
    ) -> None:
        _ = speaker
        _ = language_code
        if self._adapter is None or self.emission_blocked() or not (text or "").strip():
            return
        self.current_turn_id = uuid.uuid4().hex[:12]
        self.current_generation_id = uuid.uuid4().hex[:12]
        if self.playback is not None and hasattr(self.playback, "set_current_generation"):
            self.playback.set_current_generation(self.current_generation_id)
        await self._adapter.start_response(
            instructions=f"Speak this exactly, then wait: {text.strip()}"
        )

    async def interrupt_tts(
        self,
        *,
        skip_playback_clear: bool = False,
        already_invalidated: bool = False,
        cancel_provider: bool = True,
    ) -> None:
        old_gen = self.current_generation_id
        if not already_invalidated and self.playback is not None and hasattr(self.playback, "invalidate_generation"):
            try:
                self.playback.invalidate_generation(old_gen)
            except Exception:
                pass
        if not skip_playback_clear and self.playback is not None and hasattr(self.playback, "clear"):
            try:
                self.playback.clear()
            except Exception:
                pass
        self._set_tts_active(False)
        self._out_pcm.clear()
        self._out_resampler.reset()
        if self._adapter is not None and cancel_provider:
            try:
                clearer = getattr(self._adapter, "clear_output_audio", None)
                if callable(clearer):
                    await clearer()
            except Exception:
                pass
            try:
                await self._adapter.cancel_response()
            except Exception as exc:
                log_pstn("LLM_CANCEL.failed", call_id=self.call_id, error=str(exc)[:120])
        log_pstn("QUEUE_DRAIN", call_id=self.call_id, generation_id=old_gen)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.controller.end()
        for task in (self._runtime_task, self._deferred_greeting_task, self._pickup_finish_task, self._pickup_fallback_task):
            if task and task is not asyncio.current_task() and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._set_phase(PHASE_ENDED)
        self._set_tts_active(False)
        await self._drain_agent_archive()
        try:
            await self.interrupt_tts()
        except Exception:
            pass
        try:
            await self._archive.close()
        except Exception:
            pass
        if self._pump_task and self._pump_task is not asyncio.current_task() and not self._pump_task.done():
            self._pump_task.cancel()
            try:
                await self._pump_task
            except (asyncio.CancelledError, Exception):
                pass
        from server.realtime.voice_manager import realtime_voice_manager

        await realtime_voice_manager.destroy(self.call_id)
        self._adapter = None
        log_pstn("CLEANUP", call_id=self.call_id, wire_frames_out=self._wire_frames_out, pipeline="realtime_voice")
