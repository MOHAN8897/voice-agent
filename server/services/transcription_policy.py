"""Per-call transcription flags from resolved PSTN stack + env defaults."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from server.config.env import get_settings
from server.realtime.models import is_gemini_live_voice_model


@dataclass(frozen=True)
class TranscriptionPolicy:
    live_enabled: bool
    post_call_enabled: bool
    live_model: str
    post_call_model: str

    def persist_live_transcript_ledger(self, llm_model: str) -> bool:
        return bool(self.live_enabled)

    def gemini_use_openai_live_stt(self, llm_model: str) -> bool:
        return self.live_enabled and is_gemini_live_voice_model(llm_model or "")

    def openai_session_input_transcription(self) -> bool:
        return self.live_enabled


def _exclusive_live_post(live: bool, post: bool) -> tuple[bool, bool]:
    """Only one transcription mode may be active (live wins if both were set)."""
    if live and post:
        return True, False
    return live, post


def pstn_stack_from_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    """Dial-time PSTN override snapshot (includes transcription); falls back to resolved_stack."""
    if not meta:
        return {}
    override = meta.get("stack_override")
    if isinstance(override, dict) and override:
        return override
    rs = meta.get("resolved_stack")
    return rs if isinstance(rs, dict) else {}


def attach_normalized_stack_override(
    meta: dict[str, Any],
    stack_override: dict[str, Any] | None,
    *,
    language: str,
    tier: str = "medium",
) -> list[str]:
    """Persist normalized PSTN stack on call meta so billing matches SaaS phone stack."""
    if not stack_override:
        return []
    from server.services.pstn_stack import normalize_pstn_stack_override

    norm, adjustments = normalize_pstn_stack_override(
        stack_override,
        language=language,
        tier=tier or "medium",
    )
    if not norm:
        return adjustments
    meta["stack_override"] = norm
    rs = dict(meta.get("resolved_stack") or {})
    for key in ("transcription", "pipeline", "llm", "realtime_voice", "voice_flow", "language"):
        if key in norm:
            rs[key] = norm[key]
    meta["resolved_stack"] = rs
    return adjustments


def _transcription_block(stack: dict[str, Any] | None) -> dict[str, Any]:
    if not stack:
        return {}
    raw = stack.get("transcription")
    return raw if isinstance(raw, dict) else {}


def transcription_policy_from_stack(stack: dict[str, Any] | None) -> TranscriptionPolicy:
    settings = get_settings()
    block = _transcription_block(stack)
    post_default = bool(getattr(settings, "post_call_transcript_enabled", False))
    post_model = (
        str(block.get("post_call_model") or settings.post_call_transcript_model or "gemini-3.5-transcribe").strip()
    )
    live_model = str(block.get("live_model") or "gpt-4o-mini-transcribe").strip() or "gpt-4o-mini-transcribe"
    if "post_call_enabled" in block:
        post_call = bool(block.get("post_call_enabled"))
    else:
        post_call = post_default
    if "live_enabled" in block:
        live = bool(block.get("live_enabled"))
    else:
        live = False
    live, post_call = _exclusive_live_post(live, post_call)
    return TranscriptionPolicy(
        live_enabled=live,
        post_call_enabled=post_call,
        live_model=live_model,
        post_call_model=post_model,
    )


def transcription_policy_from_meta(meta: dict[str, Any] | None) -> TranscriptionPolicy:
    return transcription_policy_from_stack(pstn_stack_from_meta(meta))


def transcription_billing_tag(policy: TranscriptionPolicy, *, gemini_live: bool) -> str:
    if policy.live_enabled:
        return "live_openai_transcribe"
    if policy.post_call_enabled and gemini_live:
        return "post_call_gemini_transcribe"
    return "none"


def normalize_transcription_block(
    block: dict[str, Any] | None,
    *,
    adjustments: list[str] | None = None,
) -> dict[str, Any]:
    """Sanitize transcription section on realtime_voice stack overrides."""
    adj = adjustments if adjustments is not None else []
    settings = get_settings()
    src = block if isinstance(block, dict) else {}
    post_default = bool(getattr(settings, "post_call_transcript_enabled", False))
    raw_live = bool(src.get("live_enabled", False))
    raw_post = bool(src.get("post_call_enabled", post_default))
    live, post = _exclusive_live_post(raw_live, raw_post)
    if raw_live and raw_post:
        adj.append("transcription: only one mode allowed; kept live, disabled post-call")
    out: dict[str, Any] = {
        "post_call_enabled": post,
        "live_enabled": live,
    }
    live_model = str(src.get("live_model") or "gpt-4o-mini-transcribe").strip()
    if live_model != "gpt-4o-mini-transcribe":
        live_model = "gpt-4o-mini-transcribe"
        adj.append("transcription.live_model set to gpt-4o-mini-transcribe")
    out["live_model"] = live_model
    post_model = str(
        src.get("post_call_model") or settings.post_call_transcript_model or "gemini-3.5-transcribe"
    ).strip()
    out["post_call_model"] = post_model or "gemini-3.5-transcribe"
    return out
