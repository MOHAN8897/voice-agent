"""
Provider adapter contracts and shared types — server/providers/base.py
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

TierName = Literal["low", "medium", "premium"]
ConfigMode = Literal["env", "frontend"]
ProviderStage = Literal["stt", "llm", "tts"]


@dataclass(frozen=True)
class StageSelection:
    provider: str
    model: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StackSelection:
    stt: StageSelection
    llm: StageSelection
    tts: StageSelection
    language: str = "te-IN"
    voice_preset: str | None = None


@dataclass(frozen=True)
class ResolvedStack:
    combination_id: str
    tier: TierName | None
    mode: ConfigMode
    stt: StageSelection
    llm: StageSelection
    tts: StageSelection
    language: str
    voice_preset: str | None = None

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "combination_id": self.combination_id,
            "tier": self.tier,
            "mode": self.mode,
            "language": self.language,
            "voice_preset": self.voice_preset,
            "stt": {"provider": self.stt.provider, "model": self.stt.model, "config": self._safe_config(self.stt.config)},
            "llm": {"provider": self.llm.provider, "model": self.llm.model, "config": self._safe_config(self.llm.config)},
            "tts": {"provider": self.tts.provider, "model": self.tts.model, "config": self._safe_config(self.tts.config)},
        }

    @staticmethod
    def _safe_config(cfg: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in cfg.items() if k not in ("api_key", "secret")}


@dataclass
class TranscriptResult:
    text: str
    language: str | None = None
    is_final: bool = True


@dataclass
class STTConfig:
    provider: str
    model: str
    language: str = "te-IN"
    mode: Literal["rest", "realtime"] = "realtime"
    stream_type: str = "fast"
    sample_rate: int = 16000
    vad_config: dict[str, Any] | None = None


@dataclass
class LLMConfig:
    provider: str
    model: str
    temperature: float | None = None
    max_tokens: int | None = None


@dataclass
class TTSConfig:
    provider: str
    model: str
    language: str = "te-IN"
    speaker: str = "shubh"
    pace: float | None = None
    temperature: float | None = None
    # Cartesia Sonic generation_config (director knobs — not an LLM text prompt)
    emotion: str | None = None
    speed: float | None = None
    volume: float | None = None


@runtime_checkable
class STTAdapter(Protocol):
    provider_id: str

    def supported_languages(self) -> list[str]: ...

    async def transcribe_rest(self, audio: bytes, config: STTConfig) -> TranscriptResult: ...

    def connect_realtime(self, config: STTConfig): ...


@runtime_checkable
class LLMAdapter(Protocol):
    provider_id: str

    def supports_structured_output(self) -> bool: ...

    def supports_prompt_caching(self) -> bool: ...

    def stream_live_turn(
        self,
        input_messages: list[dict] | None = None,
        schema: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict]: ...

    def stream_structured_turn(
        self,
        input_messages: list[dict] | None = None,
        schema: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict]: ...

    async def structured_completion(
        self,
        input_messages: list[dict],
        schema: dict,
        config: LLMConfig | None = None,
        *,
        schema_name: str = "structured",
    ) -> dict: ...


@runtime_checkable
class TTSAdapter(Protocol):
    provider_id: str

    def connect_stream(self, config: TTSConfig): ...
