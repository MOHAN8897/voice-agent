"""Outbound playback control — provider-agnostic is_active / clear / generation."""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol


class PlaybackController(Protocol):
    def is_active(self) -> bool: ...

    def queued_ms(self) -> float: ...

    def clear(self) -> int:
        """Drain local buffered audio. Returns frames/items drained."""
        ...

    def invalidate_generation(self, generation_id: str | None) -> None: ...

    def current_generation(self) -> str | None: ...

    def set_current_generation(self, generation_id: str | None) -> None: ...


class EstimatedPlaybackTracker:
    """For Exotel/Plivo: estimate remaining play time from bytes sent (no local queue)."""

    def __init__(self, *, frame_ms: float = 20.0, post_send_hold_ms: float = 150.0) -> None:
        self._frame_ms = frame_ms
        self._post_send_hold_ms = post_send_hold_ms
        self._queued_frames = 0
        self._last_send_at = 0.0
        self._current_generation: str | None = None
        self._invalid: set[str] = set()

    def note_sent_frames(self, n: int = 1) -> None:
        if n <= 0:
            return
        now = time.monotonic()
        # Drain estimate for time elapsed since last send.
        if self._last_send_at > 0 and self._queued_frames > 0:
            elapsed_ms = (now - self._last_send_at) * 1000.0
            drained = int(elapsed_ms / self._frame_ms)
            self._queued_frames = max(0, self._queued_frames - drained)
        self._queued_frames += n
        self._last_send_at = now

    def is_active(self) -> bool:
        self._decay()
        if self._queued_frames > 0:
            return True
        # Bias slightly long so finals don't launch while provider buffer still plays.
        if self._last_send_at > 0:
            hold_s = self._post_send_hold_ms / 1000.0
            if (time.monotonic() - self._last_send_at) < hold_s:
                return True
        return False

    def queued_ms(self) -> float:
        self._decay()
        base = float(self._queued_frames * self._frame_ms)
        if self._queued_frames <= 0 and self._last_send_at > 0:
            remain = self._post_send_hold_ms - (time.monotonic() - self._last_send_at) * 1000.0
            return max(0.0, remain)
        return base

    def clear(self) -> int:
        n = self._queued_frames
        self._queued_frames = 0
        self._last_send_at = 0.0
        return n

    def invalidate_generation(self, generation_id: str | None) -> None:
        if generation_id:
            self._invalid.add(generation_id)
            if len(self._invalid) > 16:
                # Keep newest-ish by discarding arbitrary old ids when oversized.
                self._invalid = set(list(self._invalid)[-12:])

    def is_generation_valid(self, generation_id: str | None) -> bool:
        if not generation_id:
            return True
        return generation_id not in self._invalid

    def current_generation(self) -> str | None:
        return self._current_generation

    def set_current_generation(self, generation_id: str | None) -> None:
        self._current_generation = generation_id

    def _decay(self) -> None:
        if self._last_send_at <= 0 or self._queued_frames <= 0:
            return
        elapsed_ms = (time.monotonic() - self._last_send_at) * 1000.0
        drained = int(elapsed_ms / self._frame_ms)
        if drained > 0:
            self._queued_frames = max(0, self._queued_frames - drained)
            self._last_send_at = time.monotonic()


class TelnyxQueuePlayback:
    """Wraps Telnyx outbound queue + generation invalidation."""

    defer_heard_until_sent = True

    def __init__(
        self,
        *,
        queue_size: Callable[[], int],
        drain: Callable[[], int],
        frame_ms: float = 20.0,
        sending: Callable[[], bool] | None = None,
        wait_for_capacity: Callable[..., Any] | None = None,
    ) -> None:
        self._queue_size = queue_size
        self._drain = drain
        self._frame_ms = frame_ms
        self._sending = sending or (lambda: False)
        self.wait_for_capacity = wait_for_capacity
        self._current_generation: str | None = None
        self._invalid: set[str] = set()

    def is_active(self) -> bool:
        return self._queue_size() > 0 or bool(self._sending())

    def queued_ms(self) -> float:
        return float((self._queue_size() + int(bool(self._sending()))) * self._frame_ms)

    def clear(self) -> int:
        return int(self._drain())

    def invalidate_generation(self, generation_id: str | None) -> None:
        if generation_id:
            self._invalid.add(generation_id)

    def is_generation_valid(self, generation_id: str | None) -> bool:
        if not generation_id:
            return True
        return generation_id not in self._invalid

    def current_generation(self) -> str | None:
        return self._current_generation

    def set_current_generation(self, generation_id: str | None) -> None:
        self._current_generation = generation_id
