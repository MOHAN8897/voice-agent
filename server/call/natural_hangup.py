"""Natural hangup timing — finish the farewell on the line, then disconnect.

A human close is: last word → short pause → put the phone down.
Hanging up when TTS *synthesis* ends cuts the last syllables on PSTN.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

# Last RTP / provider buffer can still be playing after local TTS flush.
HANGUP_PLAYBACK_TIMEOUT_SEC = 12.0
# Brief silence after the last word — like a person pausing before hanging up.
HANGUP_TRAIL_SILENCE_SEC = 0.55
HANGUP_TRAIL_SILENCE_MS = int(HANGUP_TRAIL_SILENCE_SEC * 1000)
_POLL_SEC = 0.05


async def wait_for_farewell_playback(
    is_playing: Callable[[], bool],
    *,
    timeout_sec: float = HANGUP_PLAYBACK_TIMEOUT_SEC,
    poll_sec: float = _POLL_SEC,
    wait_for_start_sec: float = 0.0,
) -> bool:
    """Block until farewell audio is no longer on the wire. True if any play was seen."""
    deadline = time.monotonic() + max(0.05, timeout_sec)
    start_deadline = time.monotonic() + max(0.0, wait_for_start_sec)
    heard = False
    while time.monotonic() < deadline:
        try:
            playing = bool(is_playing())
        except Exception:
            playing = False
        if playing:
            heard = True
            await asyncio.sleep(poll_sec)
            continue
        if heard:
            return True
        if time.monotonic() < start_deadline:
            await asyncio.sleep(poll_sec)
            continue
        return False
    return heard


async def pause_before_disconnect(*, should_pause: bool, trail_sec: float | None = None) -> None:
    """Hold the line after the last word so disconnect is not a hard cut."""
    pause = HANGUP_TRAIL_SILENCE_SEC if trail_sec is None else trail_sec
    if should_pause and pause > 0:
        await asyncio.sleep(pause)
