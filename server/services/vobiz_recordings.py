"""Fetch account-owned carrier recordings after a Vobiz call ends."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from server.services.vobiz_client import VobizApiError, VobizConfigError

logger = logging.getLogger(__name__)
_jobs: dict[str, asyncio.Task] = {}
_downloads = asyncio.Semaphore(4)
_MEDIA_HOSTS = {"media.vobiz.ai", "recordings.vobiz.ai", "storage.vobiz.ai"}
_MAX_BYTES = 128 * 1024 * 1024


async def _find_recording(client: Any, call_uuid: str, recording_id: str = "") -> dict[str, Any]:
    base = f"/Account/{quote(client.auth_id, safe='')}/Recording/"
    if recording_id and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", recording_id):
        data = await client._request("GET", f"{base}{recording_id}/")
        row = data.get("data", data)
        return row if isinstance(row, dict) and row.get("call_uuid") == call_uuid else {}
    # The API documents limit/offset, not a call UUID filter. Always match the
    # returned owner-scoped recording to this exact call before downloading it.
    for offset in range(0, 500, 100):
        data = await client._request("GET", base, params={"limit": 100, "offset": offset})
        rows = data.get("objects", [])
        if not isinstance(rows, list):
            return {}
        for row in rows:
            if isinstance(row, dict) and row.get("call_uuid") == call_uuid:
                return row
        if len(rows) < 100:
            break
    return {}


async def retrieve_recording(call_id: str) -> bool:
    from server.call.call_ledger import call_ledger
    from server.call.paths import call_dir
    from server.services.saas.voice_kyc_service import vobiz_client_for_call
    from server.services.vobiz_client import vobiz_call_registry

    meta = call_ledger.read_meta(call_id)
    call_uuid = str(meta.get("vobiz_call_uuid") or "")
    if meta.get("channel") != "pstn" or not call_uuid:
        return False
    dest_dir = call_dir(call_id)
    if any((dest_dir / f"vobiz_recording.{ext}").is_file() for ext in ("wav", "mp3")):
        return True
    local = await asyncio.to_thread(vobiz_call_registry.get, call_uuid) or {}
    client = await vobiz_client_for_call({**local, **meta})
    row = await _find_recording(client, call_uuid, str(meta.get("vobiz_recording_id") or local.get("recording_id") or ""))
    url = str(row.get("recording_url") or "")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in _MEDIA_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        return False
    fmt = str(row.get("recording_format") or row.get("file_format") or "").lower()
    if fmt not in {"wav", "mp3"}:
        fmt = "wav" if parsed.path.lower().endswith(".wav") else "mp3"
    headers = client._headers()
    async with _downloads, httpx.AsyncClient(timeout=httpx.Timeout(15.0), follow_redirects=False) as http, http.stream("GET", url, headers=headers) as response:
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > _MAX_BYTES:
                raise ValueError("Carrier recording exceeds the size limit")
            body.extend(chunk)
    is_wav = body[:4] == b"RIFF" and body[8:12] == b"WAVE"
    if not body or not (is_wav or body[:3] == b"ID3" or (body[0] == 0xff and len(body) > 1 and body[1] & 0xe0 == 0xe0)):
        raise ValueError("Carrier did not return an audio recording")
    fmt = "wav" if is_wav else "mp3"
    dest = dest_dir / f"vobiz_recording.{fmt}"

    def save() -> None:
        pending = dest.with_suffix(dest.suffix + ".part")
        pending.write_bytes(body)
        pending.replace(dest)

    await asyncio.to_thread(save)
    meta = call_ledger.read_meta(call_id)
    meta.update(recording_source="vobiz", vobiz_recording_id=row.get("recording_id"), recording_fetch_status="ready")
    call_ledger.write_meta(call_id, meta)
    return True


def schedule_recording_retrieval(call_id: str) -> None:
    if call_id in _jobs:
        return

    async def run() -> None:
        for delay in (0, 2, 5, 15, 30, 60):
            if delay:
                await asyncio.sleep(delay)
            try:
                if await asyncio.wait_for(retrieve_recording(call_id), timeout=25):
                    return
            except (httpx.HTTPError, VobizApiError, VobizConfigError, OSError, RuntimeError, ValueError, TimeoutError) as exc:
                logger.info("Carrier recording pending call=%s error_type=%s", call_id, type(exc).__name__)

    task = asyncio.create_task(run(), name=f"carrier-recording-{call_id}")
    _jobs[call_id] = task
    task.add_done_callback(lambda done: _jobs.pop(call_id, None))
