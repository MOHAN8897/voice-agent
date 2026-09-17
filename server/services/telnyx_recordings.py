"""Download Telnyx Call Control recordings into the local call archive."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from server.services.pstn_debug import log_pstn
from server.services.telnyx_client import TelnyxApiError, TelnyxClient, telnyx_call_registry
from server.utils.logger import logger


async def start_call_recording(call_control_id: str) -> None:
    """Ask Telnyx to save a dual-channel WAV of the live call (profile recording may already be on)."""
    if not call_control_id:
        return
    row = telnyx_call_registry.get(call_control_id) or {}
    if row.get("recording_start_requested") or row.get("skip_stream") or row.get("voice_check"):
        return
    telnyx_call_registry.upsert(call_control_id, {"recording_start_requested": True})
    try:
        await TelnyxClient().start_recording(call_control_id)
        log_pstn("recording.start", control=call_control_id)
    except TelnyxApiError as exc:
        telnyx_call_registry.upsert(
            call_control_id,
            {"recording_start_error": str(exc)[:200]},
        )
        logger.warning("[TELNYX] record_start failed %s: %s", call_control_id, str(exc)[:200])


def _recording_url(payload: dict[str, Any]) -> tuple[str, str]:
    urls = (
        payload.get("recording_urls")
        or payload.get("public_recording_urls")
        or payload.get("download_urls")
        or {}
    )
    if not isinstance(urls, dict):
        urls = {}
    wav = str(urls.get("wav") or urls.get("WAV") or "").strip()
    if wav:
        return wav, ".wav"
    mp3 = str(urls.get("mp3") or urls.get("MP3") or "").strip()
    if mp3:
        return mp3, ".mp3"
    media = str(payload.get("media_url") or payload.get("url") or "").strip()
    if media.lower().endswith(".mp3"):
        return media, ".mp3"
    if media:
        return media, ".wav"
    return "", ""


def _pending_dir() -> Path:
    from server.config.env import get_settings

    path = get_settings().data_path / "telnyx-pending-recordings"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _pending_path(call_control_id: str, suffix: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (call_control_id or ""))[:80]
    ext = ".mp3" if str(suffix or "").lower().endswith("mp3") else ".wav"
    return _pending_dir() / f"{safe or 'unknown'}{ext}"


def _internal_call_id(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    return str(row.get("internal_call_id") or row.get("call_id") or "").strip()


async def _download_recording(url: str) -> bytes:
    if not url:
        return b""
    headers: dict[str, str] = {}
    try:
        headers = TelnyxClient()._headers()
    except Exception:
        headers = {}
    timeout = httpx.Timeout(connect=15.0, read=60.0, write=15.0, pool=15.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for hdrs in ((headers if headers else {}), {}):
            try:
                response = await client.get(url, headers=hdrs)
                if response.status_code < 400 and response.content:
                    return response.content
            except Exception as exc:
                logger.warning("[TELNYX] recording download failed: %s", str(exc)[:160])
    return b""


def _commit_recording(
    *,
    call_id: str,
    call_control_id: str,
    body: bytes,
    suffix: str,
    payload: dict[str, Any],
    url: str,
) -> None:
    from server.call.audio_archive import audio_archive
    from server.call.call_ledger import call_ledger

    dest = audio_archive.save_telnyx_recording(call_id, body, suffix=suffix)
    meta = call_ledger.read_meta(call_id) or {"call_id": call_id}
    usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
    channels = str(payload.get("channels") or "").strip().lower()
    meta["telnyx_recording"] = {
        "path": dest.name,
        "url": url,
        "bytes": dest.stat().st_size if dest.exists() else len(body),
        "control": call_control_id,
        "channels": channels or None,
        "review": audio_archive.telnyx_review_path(call_id).name
        if audio_archive._nonempty(audio_archive.telnyx_review_path(call_id))
        else None,
    }
    meta["usage"] = usage
    call_ledger.write_meta(call_id, meta)
    log_pstn(
        "recording.saved",
        control=call_control_id,
        call_id=call_id,
        bytes=dest.stat().st_size if dest.exists() else len(body),
        path=dest.name,
    )


def _stash_pending(
    call_control_id: str,
    *,
    body: bytes,
    suffix: str,
    url: str,
    payload: dict[str, Any],
) -> None:
    dest = _pending_path(call_control_id, suffix)
    dest.write_bytes(body)
    telnyx_call_registry.upsert(
        call_control_id,
        {
            "pending_recording": {
                "path": str(dest),
                "suffix": suffix,
                "url": url,
                "channels": str(payload.get("channels") or "").strip().lower() or None,
            }
        },
    )
    log_pstn(
        "recording.pending",
        control=call_control_id,
        bytes=len(body),
        path=dest.name,
    )


async def attach_pending_recording(call_control_id: str, call_id: str) -> None:
    """Move a recording that arrived before internal_call_id into the call archive."""
    if not call_control_id or not call_id:
        return
    row = telnyx_call_registry.get(call_control_id) or {}
    pending = row.get("pending_recording")
    if not isinstance(pending, dict):
        return
    suffix = str(pending.get("suffix") or ".wav")
    url = str(pending.get("url") or "")
    body = b""
    path = Path(str(pending.get("path") or ""))
    if path.is_file():
        try:
            body = path.read_bytes()
        except OSError:
            body = b""
    if not body:
        body = await _download_recording(url)
    if not body:
        log_pstn("recording.pending.empty", control=call_control_id, call_id=call_id)
        return
    payload = {"channels": pending.get("channels"), "recording_urls": {"wav": url} if url else {}}
    _commit_recording(
        call_id=call_id,
        call_control_id=call_control_id,
        body=body,
        suffix=suffix,
        payload=payload,
        url=url,
    )
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass
    telnyx_call_registry.upsert(call_control_id, {"pending_recording": None})


async def ingest_recording_saved(call_control_id: str, payload: dict[str, Any]) -> None:
    """Persist Telnyx's saved recording next to the local mix for history playback."""
    url, suffix = _recording_url(payload)
    if not url:
        logger.info("[TELNYX] recording.saved without URL control=%s", call_control_id)
        return
    telnyx_call_registry.upsert(
        call_control_id,
        {"recording_urls": payload.get("recording_urls") or {"wav": url}},
    )
    body = await _download_recording(url)
    if not body:
        log_pstn("recording.download.empty", control=call_control_id)
        return
    call_id = _internal_call_id(telnyx_call_registry.get(call_control_id))
    if not call_id:
        _stash_pending(call_control_id, body=body, suffix=suffix, url=url, payload=payload)
        call_id = _internal_call_id(telnyx_call_registry.get(call_control_id))
        if not call_id:
            return
        await attach_pending_recording(call_control_id, call_id)
        return
    _commit_recording(
        call_id=call_id,
        call_control_id=call_control_id,
        body=body,
        suffix=suffix,
        payload=payload,
        url=url,
    )
