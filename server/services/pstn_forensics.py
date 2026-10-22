"""Live + post-call PSTN forensics for Test Studio / manual debugging (audit §7)."""
from __future__ import annotations

import time
from typing import Any

from server.services.pstn_debug import milestones_for


def _ledger_call_id(call_id: str | None, reg: dict[str, Any]) -> str:
    """Map Telnyx call_control_id to internal UUID used under data/calls/."""
    cid = (call_id or "").strip()
    internal = str(reg.get("internal_call_id") or "").strip()
    if internal:
        return internal
    # Windows cannot use v3:… as a directory name — never pass control ids to call_ledger.
    if cid and ":" not in cid:
        return cid
    return ""


def _find_registry_row(call_id: str | None) -> tuple[str, dict[str, Any]]:
    from server.services.telnyx_client import telnyx_call_registry

    cid = (call_id or "").strip()
    if cid:
        direct = telnyx_call_registry.get(cid)
        if direct:
            return cid, direct
        for row in telnyx_call_registry.list_recent(None):
            if str(row.get("internal_call_id") or "") == cid:
                return str(row.get("call_control_id") or ""), row
    return "", {}


def _voice_loop(call_id: str | None, external_id: str) -> Any | None:
    from server.services.telnyx_pstn_bridge import active_telnyx_bridges

    bridge = active_telnyx_bridges.get(external_id) if external_id else None
    if bridge and getattr(bridge, "_voice", None):
        return bridge._voice
    if call_id:
        for bridge in list(active_telnyx_bridges.values()):
            if getattr(bridge, "call_id", None) == call_id:
                return getattr(bridge, "_voice", None)
    return None


def build_forensics_snapshot(call_id: str | None) -> dict[str, Any]:
    """Merge IDs, carrier leg, media metrics, and runtime hangup/language state."""
    from server.call.call_ledger import call_ledger
    from server.services.pstn_media_flow import pstn_media_flow

    cid = (call_id or "").strip()
    external_id, reg = _find_registry_row(cid)
    if not external_id and reg:
        external_id = ""
    flow = pstn_media_flow.snapshot(cid or external_id or None) or {}
    if not external_id:
        external_id = str(flow.get("external_id") or reg.get("call_control_id") or "")
    ledger_id = _ledger_call_id(cid, reg)
    meta = call_ledger.read_meta(ledger_id) if ledger_id else {}
    stored = (meta.get("pstn_forensics") or {}) if isinstance(meta.get("pstn_forensics"), dict) else {}

    # Dial/answer/first-send share the carrier clock. Passing both aliases
    # prefixes every milestone key and makes the latency calculation miss them.
    timeline = milestones_for(external_id or cid) if (external_id or cid) else {}
    latencies = flow.get("latencies") or {}
    metrics = flow.get("metrics") or {}

    voice = _voice_loop(cid, external_id)
    runtime: dict[str, Any] = {}
    if voice is not None:
        runtime = {
            "phase": getattr(voice, "_phase", None),
            "hangup_arm_source": getattr(voice, "_hangup_arm_source", None),
            "pending_end_reason": (getattr(voice, "_pending_end_call", None) or {}).get("reason"),
            "firm_refusal_close": getattr(voice, "_firm_refusal_close", False),
            "last_user_final": (getattr(voice, "_last_user_final_text", None) or "")[:120],
            "pickup_text": (getattr(voice, "_pickup_user_text", None) or "")[:120],
            "deferred_greeting_armed": getattr(voice, "_deferred_greeting_armed", False),
            "language": getattr(voice, "_resolve_language", lambda: None)(),
            "live_model": getattr(voice, "_live_model", None),
        }
        adapter = getattr(voice, "_adapter", None)
        if adapter is not None:
            runtime["effective_vad"] = (getattr(adapter, "last_session", None) or {}).get("effective_vad")

    leg = {
        "status": reg.get("status"),
        "media_status": reg.get("media_status"),
        "recording_status": reg.get("recording_status"),
        "last_event": reg.get("last_event"),
        "direction": reg.get("direction"),
        "stream_state": reg.get("stream_state"),
        "answered_handled": reg.get("answered_handled"),
        "dialed_at": reg.get("dialed_at"),
        "internal_call_id": reg.get("internal_call_id"),
        "dial_request_id": reg.get("dial_request_id"),
    }

    ids = {
        "call_id": ledger_id or reg.get("internal_call_id") or (cid if ":" not in cid else None),
        "call_control_id": external_id or None,
        "dial_request_id": meta.get("dial_request_id") or reg.get("dial_request_id"),
        "agent_id": meta.get("agent_id") or reg.get("agent_id"),
        "compiled_brain_version": meta.get("compiled_brain_version"),
        "brain_checksum": meta.get("compiled_brain_checksum") or stored.get("brain_checksum"),
        "callee_e164": meta.get("callee_e164") or reg.get("callee_e164") or reg.get("to"),
        "connected_at": meta.get("connected_at"),
    }

    playback = {
        "playout_underrun_count": metrics.get("playout_underrun_count"),
        "queue_depth_p95": metrics.get("queue_depth_p95"),
        "queue_depth_p99": metrics.get("queue_depth_p99"),
        "barge_in_discarded_frames": metrics.get("barge_in_discarded_frames"),
        "interrupted_frames": metrics.get("interrupted_frames"),
        "outbound_sent_frames": metrics.get("outbound_sent_frames"),
    }

    answer_to_first_sent_ms = None
    if timeline.get("answered") is not None and timeline.get("first_outbound_sent") is not None:
        answer_to_first_sent_ms = max(0, timeline["first_outbound_sent"] - timeline["answered"])

    hints: list[str] = []
    if (metrics.get("playout_underrun_count") or 0) > 0:
        hints.append("Playout underruns during expected speech — check model audio gaps or pacing.")
    if leg.get("media_status") in ("stopped", "error") and leg.get("status") not in ("hangup", "completed", "ended"):
        hints.append("Media stopped while telephone leg may still be up — reconcile stream before redialing.")
    if ids.get("dial_request_id"):
        hints.append("Reuse the same dialRequestId to test idempotent dial (must not place a second call).")

    return {
        "updated_at": time.time(),
        "active": bool(flow.get("active")),
        "ids": ids,
        "carrier_leg": leg,
        "timeline_ms_from_dial": timeline,
        "derived_ms": {
            "answer_to_first_audio_sent": answer_to_first_sent_ms,
            "stt_final": latencies.get("stt_final_ms"),
            "telnyx_first_outbound": latencies.get("telnyx_first_outbound_ms"),
            "tts_first_audio": latencies.get("tts_first_audio_ms"),
        },
        "playback": playback,
        "runtime": runtime,
        "stored_notes": stored.get("notes") or [],
        "debug_hints": hints,
        "compare_recording": {
            "has_recording": bool(meta.get("has_telnyx_recording")),
            "recording_source": meta.get("recording_source"),
            "steps": [
                "Compare carrier recording to playout underruns and timeline_ms_from_dial.first_outbound_sent.",
                "If server metrics look clean but recording gaps exist, suspect transport or Telnyx path.",
                "If underruns align with audible gaps, suspect model output pacing or queue starvation.",
            ],
        },
    }


def note(call_id: str | None, external_id: str | None, field: str, value: Any) -> None:
    """Attach a small note to in-memory forensics (persisted on meta flush)."""
    from server.call.call_ledger import call_ledger

    cid = (call_id or "").strip()
    key = cid or (external_id or "").strip()
    if not key:
        return
    _pending_notes.setdefault(key, []).append(
        {"t": time.time(), "field": field, "value": value},
    )
    if cid:
        meta = call_ledger.read_meta(cid) or {}
        block = meta.get("pstn_forensics") if isinstance(meta.get("pstn_forensics"), dict) else {}
        notes = list(block.get("notes") or [])
        notes.append({"t": time.time(), "field": field, "value": value})
        block["notes"] = notes[-40:]
        meta["pstn_forensics"] = block
        if field == "dial_request_id":
            meta["dial_request_id"] = value
        call_ledger.write_meta(cid, meta)


_pending_notes: dict[str, list[dict[str, Any]]] = {}


def flush_meta(call_id: str) -> None:
    """Persist latest snapshot onto call meta for post-call review."""
    from server.call.call_ledger import call_ledger

    snap = build_forensics_snapshot(call_id)
    meta = call_ledger.read_meta(call_id) or {}
    meta["pstn_forensics"] = snap
    call_ledger.write_meta(call_id, meta)
