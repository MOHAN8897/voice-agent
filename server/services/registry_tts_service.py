"""TTS synthesis via provider registry — respects per-call stack (Cartesia, Sarvam, …)."""
from __future__ import annotations

from typing import Any

from server.config.constants import constants
from server.config.env import get_settings
from server.providers import get_provider_registry, resolve_stack_for_session
from server.providers.base import TTSConfig
from server.services.sarvam_tts_service import synthesize as sarvam_synthesize
from server.services.runtime_settings import runtime_settings
from server.services.tts_config import TtsConfigError, resolve_tts_config
from server.utils.errors import AppError, ErrorCode
from server.utils.logger import log_tts
from server.utils.pcm_wav import pcm16_to_wav


def _stack_for_tts(*, call_id: str | None, session_id: str, language_code: str):
    if call_id:
        from server.call.call_context import get as get_call_ctx

        ctx = get_call_ctx(call_id)
        if ctx:
            return ctx.resolved_stack
    return resolve_stack_for_session(session_id, language=language_code)


def _resolve_cartesia_voice(
    *,
    session_id: str,
    stack,
    speaker: str | None,
) -> str:
    settings = get_settings()
    runtime = runtime_settings.get(session_id)
    stack_speaker = stack.tts.config.get("speaker") if stack.tts.config else None
    return (
        speaker
        or runtime.get("ttsSpeaker")
        or stack_speaker
        or settings.cartesia_tts_voice_id
        or constants.CARTESIA_DEFAULT_VOICE_ID
    )


async def synthesize_via_registry(
    *,
    text: str,
    language_code: str = "te-IN",
    session_id: str = "default",
    call_id: str | None = None,
    speaker: str | None = None,
    pace: float | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Returns {audio_bytes, content_type, speaker, language_code, request_id, provider}."""
    settings = get_settings()
    from server.services.spoken_numbers import prepare_spoken_reply

    stack = _stack_for_tts(call_id=call_id, session_id=session_id, language_code=language_code)
    provider_id = stack.tts.provider
    text = prepare_spoken_reply((text or "").strip(), provider=provider_id)
    if not text:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Text is required for TTS", status_code=400)

    if not settings.use_provider_registry:
        return await sarvam_synthesize(
            text=text,
            language_code=language_code,
            speaker=speaker,
            pace=pace,
            model=model,
            temperature=temperature,
            session_id=session_id,
        )

    registry = get_provider_registry()

    if provider_id == "sarvam" or not registry.is_provider_enabled(provider_id, "tts"):
        try:
            cfg = resolve_tts_config(
                session_id,
                language_code=language_code,
                speaker=speaker,
                model=model or stack.tts.model,
                pace=pace,
                temperature=temperature,
            )
        except TtsConfigError as e:
            raise AppError(ErrorCode.VALIDATION_ERROR, str(e), status_code=400) from e
        result = await sarvam_synthesize(
            text=text,
            language_code=cfg["language_code"],
            speaker=cfg["speaker"],
            pace=cfg["pace"],
            model=cfg["model"],
            temperature=cfg.get("temperature"),
            session_id=session_id,
        )
        result["provider"] = "sarvam"
        return result

    tts = registry.get_tts(provider_id)
    if not hasattr(tts, "synthesize_rest"):
        raise AppError(
            ErrorCode.PROVIDER_ERROR,
            f"TTS provider {provider_id} has no REST synthesize",
            status_code=502,
        )

    if provider_id == "cartesia":
        voice_id = _resolve_cartesia_voice(session_id=session_id, stack=stack, speaker=speaker)
        try:
            cartesia_cfg = resolve_tts_config(
                session_id,
                language_code=language_code,
                speaker=voice_id,
                model=model or stack.tts.model,
                pace=pace,
                temperature=temperature,
                call_id=call_id,
            )
        except TtsConfigError:
            cartesia_cfg = {}
        config = TTSConfig(
            provider=provider_id,
            model=model or stack.tts.model,
            language=language_code,
            speaker=voice_id,
            pace=pace,
            temperature=temperature,
            emotion=cartesia_cfg.get("emotion"),
            speed=cartesia_cfg.get("speed"),
            volume=cartesia_cfg.get("volume"),
        )
    else:
        try:
            runtime_cfg = resolve_tts_config(
                session_id,
                language_code=language_code,
                speaker=speaker,
                model=model or stack.tts.model,
                pace=pace,
                temperature=temperature,
            )
        except TtsConfigError:
            runtime_cfg = {
                "speaker": speaker or stack.tts.config.get("speaker"),
                "pace": pace,
                "temperature": temperature,
            }
        config = TTSConfig(
            provider=provider_id,
            model=model or stack.tts.model,
            language=language_code,
            speaker=runtime_cfg.get("speaker") or stack.tts.config.get("speaker", "shubh"),
            pace=runtime_cfg.get("pace"),
            temperature=runtime_cfg.get("temperature"),
        )

    log_tts(
        "Registry TTS",
        provider=provider_id,
        model=config.model,
        session=session_id,
        call=call_id or "",
        chars=len(text),
    )
    audio_bytes = await tts.synthesize_rest(text, config)

    pcm_for_archive = audio_bytes
    content_type = "audio/wav"
    if provider_id == "cartesia":
        audio_bytes = pcm16_to_wav(pcm_for_archive, sample_rate=16000)
        if call_id:
            from server.call.audio_archive import audio_archive

            audio_archive.set_agent_sample_rate(call_id, 16000)

    return {
        "audio_bytes": audio_bytes,
        "content_type": content_type,
        "request_id": None,
        "speaker": config.speaker,
        "language_code": language_code,
        "provider": provider_id,
        "pcm_for_archive": pcm_for_archive if provider_id == "cartesia" else None,
    }
