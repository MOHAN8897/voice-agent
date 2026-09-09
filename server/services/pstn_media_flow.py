"""In-memory, secret-safe live PSTN media-flow telemetry."""
from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any


SUPPORTED_TELNYX_CODECS = frozenset({"PCMU", "PCMA", "L16"})


@dataclass(frozen=True)
class CallMediaConfig:
    codec: str = "PCMU"
    sample_rate: int = 8000
    channels: int = 1
    frame_ms: int = 20

    def __post_init__(self) -> None:
        codec = self.codec.upper()
        object.__setattr__(self, "codec", codec)
        if codec not in SUPPORTED_TELNYX_CODECS:
            raise ValueError(f"unsupported Telnyx media codec: {codec}")
        if self.channels != 1:
            raise ValueError("PSTN media must be mono")
        if codec in {"PCMU", "PCMA"} and self.sample_rate != 8000:
            raise ValueError(f"{codec} requires 8000 Hz")
        if codec == "L16" and self.sample_rate != 16000:
            raise ValueError("L16 requires 16000 Hz")

    @property
    def frame_bytes(self) -> int:
        samples = int(self.sample_rate * self.frame_ms / 1000)
        return samples * (2 if self.codec == "L16" else 1) * self.channels

    def duration_ms(self, byte_count: int) -> float:
        bytes_per_sample = 2 if self.codec == "L16" else 1
        return byte_count * 1000.0 / (self.sample_rate * self.channels * bytes_per_sample)


@dataclass
class FlowEvent:
    seq: int
    timestamp: float
    stage: str
    direction: str
    call_id: str | None
    external_id: str | None
    ws_id: str | None
    turn_id: str | None = None
    generation_id: str | None = None
    codec: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    bytes: int = 0
    frames: int = 0
    duration_ms: float = 0
    queue_size: int = 0
    level_dbfs: float | None = None
    status: str = "healthy"
    detail: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class PstnMediaFlowStore:
    def __init__(self) -> None:
        self._calls: dict[str, dict[str, Any]] = {}
        self._aliases: dict[str, str] = {}
        self._seq = 0

    def start(
        self,
        *,
        external_id: str,
        ws_id: str | None,
        configured: CallMediaConfig,
        call_id: str | None = None,
    ) -> None:
        if len(self._calls) >= 30:
            oldest = min(self._calls, key=lambda item: self._calls[item].get("updated_at") or 0)
            stale = self._calls.pop(oldest)
            for alias in (stale.get("call_id"), stale.get("external_id")):
                if alias:
                    self._aliases.pop(alias, None)
        key = call_id or external_id
        now = time.time()
        self._calls[key] = {
            "call_id": call_id,
            "external_id": external_id,
            "ws_id": ws_id,
            "started_at": now,
            "updated_at": now,
            "configured": asdict(configured),
            "negotiated": None,
            "stages": {},
            "metrics": {
                "inbound_frames": 0,
                "inbound_bytes": 0,
                "outbound_generated_frames": 0,
                "outbound_sent_frames": 0,
                "outbound_bytes": 0,
                "queue_size": 0,
                "queue_duration_ms": 0,
                "dropped_frames": 0,
                "interrupted_frames": 0,
            },
            "events": deque(maxlen=500),
            "failures": [],
            "active": True,
        }
        self._aliases[external_id] = key
        if call_id:
            self._aliases[call_id] = key

    def bind_call_id(self, external_id: str, call_id: str) -> None:
        key = self._aliases.get(external_id, external_id)
        row = self._calls.get(key)
        if not row:
            return
        row["call_id"] = call_id
        self._aliases[call_id] = key

    def negotiate(self, identifier: str, actual: CallMediaConfig) -> list[str]:
        row = self._row(identifier)
        if not row:
            return ["MEDIA_FLOW_NOT_STARTED"]
        row["negotiated"] = asdict(actual)
        expected = CallMediaConfig(**row["configured"])
        failures: list[str] = []
        if actual.codec != expected.codec:
            failures.append(f"CODEC_MISMATCH expected={expected.codec} negotiated={actual.codec}")
        if actual.sample_rate != expected.sample_rate:
            failures.append(
                f"SAMPLE_RATE_MISMATCH expected={expected.sample_rate} negotiated={actual.sample_rate}"
            )
        if actual.channels != expected.channels:
            failures.append(f"CHANNEL_MISMATCH expected={expected.channels} negotiated={actual.channels}")
        row["failures"].extend(f for f in failures if f not in row["failures"])
        return failures

    def emit(self, identifier: str, stage: str, direction: str, **kwargs: Any) -> None:
        row = self._row(identifier)
        if not row:
            return
        self._seq += 1
        event = FlowEvent(
            seq=self._seq,
            timestamp=time.time(),
            stage=stage,
            direction=direction,
            call_id=row.get("call_id"),
            external_id=row.get("external_id"),
            ws_id=row.get("ws_id"),
            **kwargs,
        )
        row["updated_at"] = event.timestamp
        row["events"].append(asdict(event))
        row["stages"][stage] = {
            "status": event.status,
            "last_event_at": event.timestamp,
            "codec": event.codec,
            "sample_rate": event.sample_rate,
            "channels": event.channels,
            "bytes": event.bytes,
            "frames": event.frames,
            "duration_ms": event.duration_ms,
            "queue_size": event.queue_size,
            "level_dbfs": event.level_dbfs,
            "detail": event.detail,
        }
        metrics = row["metrics"]
        if stage == "inbound_audio":
            metrics["inbound_frames"] += event.frames
            metrics["inbound_bytes"] += event.bytes
        elif stage == "outbound_queued":
            metrics["outbound_generated_frames"] += event.frames
        elif stage == "outbound_sent":
            metrics["outbound_sent_frames"] += event.frames
            metrics["outbound_bytes"] += event.bytes
        metrics["queue_size"] = event.queue_size
        negotiated = row.get("negotiated")
        if negotiated:
            metrics["queue_duration_ms"] = event.queue_size * int(negotiated.get("frame_ms") or 20)
        if event.status == "failed" and event.detail and event.detail not in row["failures"]:
            row["failures"].append(event.detail)

    def increment(self, identifier: str, key: str, amount: int) -> None:
        row = self._row(identifier)
        if row:
            row["metrics"][key] = int(row["metrics"].get(key) or 0) + amount

    def finish(self, identifier: str) -> None:
        row = self._row(identifier)
        if row:
            row["active"] = False
            row["updated_at"] = time.time()

    def snapshot(self, identifier: str | None = None) -> dict[str, Any] | None:
        row = self._row(identifier) if identifier else self.latest()
        if not row:
            return None
        out = {**row, "events": list(row["events"])}
        elapsed = max(0.001, (out.get("updated_at") or time.time()) - (out.get("started_at") or time.time()))
        metrics = dict(out.get("metrics") or {})
        metrics["inbound_packets_per_sec"] = round(metrics.get("inbound_frames", 0) / elapsed, 1)
        metrics["inbound_bytes_per_sec"] = round(metrics.get("inbound_bytes", 0) / elapsed, 1)
        metrics["outbound_packets_per_sec"] = round(metrics.get("outbound_sent_frames", 0) / elapsed, 1)
        metrics["outbound_bytes_per_sec"] = round(metrics.get("outbound_bytes", 0) / elapsed, 1)
        out["metrics"] = metrics
        out["latencies"] = self._latencies(out["events"])
        out["health"] = self._health(out)
        return out

    def latest(self) -> dict[str, Any] | None:
        if not self._calls:
            return None
        return max(self._calls.values(), key=lambda row: row.get("updated_at") or 0)

    def _row(self, identifier: str | None) -> dict[str, Any] | None:
        if not identifier:
            return None
        key = self._aliases.get(identifier, identifier)
        return self._calls.get(key)

    @staticmethod
    def _latencies(events: list[dict[str, Any]]) -> dict[str, int | None]:
        # Scope response metrics to the latest turn. Greeting audio and earlier
        # turns must not produce misleading zero/negative first-audio timings.
        starts = [i for i, event in enumerate(events) if event.get("stage") == "llm_started"]
        turn_start = starts[-1] if starts else len(events)
        first: dict[str, float] = {}
        for event in events[turn_start:]:
            first.setdefault(str(event.get("stage")), float(event.get("timestamp") or 0))

        # STT capture occurs before llm_started; use the most recent final and
        # nearest preceding audio evidence, never a greeting's TTS events.
        before = events[:turn_start]
        for i in range(len(before) - 1, -1, -1):
            if before[i].get("stage") == "stt_final":
                first["stt_final"] = float(before[i].get("timestamp") or 0)
                for audio in reversed(before[:i]):
                    if audio.get("stage") == "stt_audio":
                        first["stt_audio"] = float(audio.get("timestamp") or 0)
                        break
                break

        def delta(start: str, end: str) -> int | None:
            if start not in first or end not in first:
                return None
            if first[end] < first[start]:
                return None
            return round((first[end] - first[start]) * 1000)

        return {
            "stt_final_to_llm_ms": delta("stt_final", "llm_started"),
            "stt_final_to_first_audio_ms": delta("stt_final", "outbound_sent"),
            "stt_final_ms": delta("stt_audio", "stt_final"),
            "llm_first_token_ms": delta("llm_started", "llm_first_token"),
            "tts_first_audio_ms": delta("llm_first_token", "tts_audio"),
            "telnyx_first_outbound_ms": delta("tts_audio", "outbound_sent"),
        }

    @staticmethod
    def _health(row: dict[str, Any]) -> dict[str, Any]:
        stages = row.get("stages") or {}
        checks = {
            "telnyx_inbound": "inbound_audio" in stages,
            "stt": "stt_audio" in stages or "stt_final" in stages,
            "llm": "llm_started" in stages,
            "tts": "tts_audio" in stages,
            "conversion": "converter" in stages and stages["converter"].get("status") != "failed",
            "queue": (row.get("metrics") or {}).get("queue_duration_ms", 0) < 1000,
            "telnyx_outbound": "outbound_sent" in stages,
        }
        derived_failures = list(row.get("failures") or [])
        metrics = row.get("metrics") or {}
        if metrics.get("queue_duration_ms", 0) >= 1000:
            derived_failures.append("AUDIO_BACKLOG")
        if "tts_audio" in stages and "outbound_sent" not in stages:
            derived_failures.append("OUTBOUND_TRANSMISSION_FAILURE")
        if "inbound_audio" in stages and "stt_audio" not in stages:
            derived_failures.append("STT_INPUT_FAILURE")
        score = round(sum(checks.values()) / len(checks) * 100)
        return {
            "score": score,
            "checks": checks,
            "failures": list(dict.fromkeys(derived_failures)),
            "claim": "Outbound media successfully transmitted" if checks["telnyx_outbound"] else None,
        }


pstn_media_flow = PstnMediaFlowStore()


def new_ws_id() -> str:
    return uuid.uuid4().hex[:12]
