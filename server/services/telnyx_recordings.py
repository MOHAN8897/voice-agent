"""Download Telnyx Call Control recordings into the local call archive."""
from __future__ import annotations

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


async def ingest_recording_saved(call_control_id: str, payload: dict[str, Any]) -> None:
    """Persist Telnyx's saved recording next to the local mix for history playback."""
    url, suffix = _recording_url(payload)
    if not url:
        logger.info("[TELNYX] recording.saved without URL control=%s", call_control_id)
        return
    row = telnyx_call_registry.get(call_control_id) or {}
    call_id = str(row.get("internal_call_id") or row.get("call_id") or "").strip()
    telnyx_call_registry.upsert(
        call_control_id,
        {"recording_urls": payload.get("recording_urls") or {"wav": url}},
    )
    if not call_id:
        logger.warning("[TELNYX] recording.saved with no internal call_id control=%s", call_control_id)
        return
    from server.call.audio_archive import audio_archive
    from server.call.call_ledger import call_ledger

    headers: dict[str, str] = {}
    try:
        headers = TelnyxClient()._headers()
    except Exception:
        headers = {}
    timeout = httpx.Timeout(connect=15.0, read=60.0, write=15.0, pool=15.0)
    body = b""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for hdrs in ((headers if headers else {}), {}):
            try:
                response = await client.get(url, headers=hdrs)
                if response.status_code < 400 and response.content:
                    body = response.content
                    break
            except Exception as exc:
                logger.warning("[TELNYX] recording download failed %s: %s", call_id, str(exc)[:160])
    if not body:
        log_pstn("recording.download.empty", control=call_control_id, call_id=call_id)
        return
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
