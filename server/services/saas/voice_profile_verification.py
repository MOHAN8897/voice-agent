"""Bounded, synthetic checks of a saved composed stack; never place a call."""
from __future__ import annotations

import asyncio
import base64
import copy
import json
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from websockets.exceptions import WebSocketException

from server.db.connection import get_session_factory
from server.db.models.entities import ConfigVersion, TierAssignment
from server.services.saas import voice_stack_profiles as profiles

PROBE_ERRORS = (ValueError, RuntimeError, TypeError, OSError, httpx.HTTPError, WebSocketException)

async def probe_profile(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    from server.config.env import get_settings
    from server.providers import get_provider_registry
    from server.providers.base import StackSelection, StageSelection, STTConfig
    from server.providers.llm_protocol import native_audio_provider, text_llm_api_mode
    from server.services.audio_transcode import mulaw_to_pcm16, pcm16_to_mulaw
    from server.services.pstn_prewarm import _synthesize_greeting_frames

    checks = {key: {"passed": False, "detail": "Check has not completed."} for key in profiles._EVIDENCE_KEYS}
    registry = get_provider_registry()
    blockers = profiles._runtime_profile_blockers(profile)
    checks["credentialRefConfigured"] = {"passed": not blockers, "detail":
        "Configured server credential references and approved stage tuples checked." if not blockers
        else "Resolve provider, model or voice configuration before running live checks."}
    if blockers:
        return checks
    llm = profile["llm"]
    if native_audio_provider(llm["provider"], llm["modelId"], llm["apiMode"]):
        checks["sarvamModelAccess"]["detail"] = "Use Test Studio to verify a native audio session; this check supports composed stacks."
        return checks
    mode = text_llm_api_mode(llm["provider"], llm["modelId"], llm["apiMode"])
    adapter = registry.get_llm(llm["provider"])
    locale = profile["supportedLanguages"][0]

    async def text_probe(tools: bool = False) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"model": llm["modelId"], "api_mode": mode,
                                  "max_output_tokens": 512, "buffer_response": True}
        message = "Reply with READY only. This is a synthetic connection check."
        if tools:
            message = "Call readiness_probe with status READY. This synthetic tool has no side effects."
            kwargs.update(tools=[{"type": "function", "function": {"name": "readiness_probe",
                "description": "Synthetic readiness check; no business operation.", "parameters": {
                    "type": "object", "properties": {"status": {"type": "string", "enum": ["READY"]}},
                    "required": ["status"], "additionalProperties": False}}}], tool_choice="auto")
        final = {}
        async for event in adapter.stream_live_turn(input_messages=[{"role": "user", "content": message}], **kwargs):
            if event.get("done"):
                final = event
        if tools:
            calls = final.get("tool_calls") or []
            if not any((c.get("function") or {}).get("name") == "readiness_probe"
                and json.loads((c.get("function") or {}).get("arguments") or "{}").get("status") == "READY" for c in calls):
                raise ValueError("Synthetic tool arguments were not returned")
        else:
            if not str(final.get("text") or "").strip():
                raise ValueError("No completed text response")
        return final

    async def llm_checks() -> None:
        try:
            responses = await asyncio.wait_for(asyncio.gather(text_probe(), text_probe(), return_exceptions=True), timeout=35)
            if any(isinstance(response, BaseException) for response in responses):
                raise ValueError("A concurrent text probe failed")
            checks["sarvamModelAccess"] = {"passed": True, "detail": "Two completed text responses from the exact saved model."}
            limit = get_settings().saas_max_concurrent_pstn
            checks["capacityVerified"] = {"passed": limit > 0, "detail":
                f"Two concurrent synthetic text turns passed; server call limit is {limit}. This is a smoke check, not a peak-load certification."}
        except PROBE_ERRORS as exc:
            checks["sarvamModelAccess"]["detail"] = f"Text check failed ({type(exc).__name__})."
        try:
            await asyncio.wait_for(text_probe(True), timeout=35)
            checks["toolsVerified"] = {"passed": True, "detail": "Native tool name and arguments decoded; no tool was executed."}
        except PROBE_ERRORS as exc:
            checks["toolsVerified"]["detail"] = f"Tool check failed ({type(exc).__name__})."

    async def speech_checks() -> None:
        # Validate all advertised voices statically above, then exercise every
        # configured speech model using its real call-owned synthesis path.
        for engine in profile["engines"]:
            for model in engine["models"]:
                voice = next((v for v in model["voices"] if locale in v.get("languages", [])), None)
                if voice is None:
                    raise ValueError("No speech voice supports the primary locale")
                stack = StackSelection(
                    stt=StageSelection(profile["stt"]["provider"], profile["stt"]["model"]),
                    llm=StageSelection(llm["provider"], llm["modelId"], {"api_mode": mode}),
                    tts=StageSelection(model["provider"], model["model"], {
                        "speaker": voice["providerVoiceId"], "api_mode": model["apiMode"]}), language=locale)
                frames, _ = await asyncio.wait_for(_synthesize_greeting_frames(
                    greeting="This is a voice connection check. Thank you.", session_id="readiness-probe",
                    pseudo_call_id="readiness-probe", sample_rate=16000, tts_output_codec="linear16",
                    language=locale, resolved_stack=stack, pipeline="composed_voice"), timeout=45)
                pcm = b"".join(frames)
                if len(pcm) <= 3200 or len(pcm) % 2:
                    raise ValueError("No usable PCM sample returned")
                wire = pcm16_to_mulaw(pcm, 16000)
                if not wire or not mulaw_to_pcm16(wire, 16000):
                    raise ValueError("Media conversion failed")
        checks["ttsCatalogVerified"] = {"passed": True, "detail": "All model/voice/locale mappings checked; each speech model returned PCM."}
        checks["mediaFormatsVerified"] = {"passed": True, "detail": "Synthesized 16 kHz PCM encoded to 8 kHz G.711 and decoded successfully. No carrier call made."}
        try:
            async with registry.get_stt(profile["stt"]["provider"]).connect_realtime(
                STTConfig(profile["stt"]["provider"], profile["stt"]["model"], language=locale)) as socket:
                audio = pcm + b"\0" * 32000
                for offset in range(0, len(audio), 6400):
                    await socket.send(json.dumps({"event": "audio_input", "audio": base64.b64encode(audio[offset:offset+6400]).decode()}))
                # The live connector uses VAD endpointing. Manual flush is
                # rejected on that mode; trailing silence finalizes the sample.
                async with asyncio.timeout(20):
                    while True:
                        event = json.loads(await socket.recv())
                        if (event.get("event") or event.get("type")) == "error":
                            raise RuntimeError("Speech recognition rejected the sample")
                        text = event.get("text") or (event.get("data") or {}).get("text")
                        if text and (event.get("event") or event.get("type")) == "transcript.final":
                            break
            checks["sttVerified"] = {"passed": True, "detail": "Streaming recognition returned a final transcript for synthesized test speech."}
        except PROBE_ERRORS as exc:
            checks["sttVerified"]["detail"] = f"Streaming recognition failed ({type(exc).__name__})."

    async def bounded_speech() -> None:
        try:
            await asyncio.wait_for(speech_checks(), timeout=70)
        except PROBE_ERRORS as exc:
            checks["ttsCatalogVerified"]["detail"] = f"Speech check failed ({type(exc).__name__})."

    await asyncio.gather(llm_checks(), bounded_speech())
    return checks


async def verify_saved_profile(*, environment: str, tier: str, expected_revision: int, actor: str) -> dict[str, Any]:
    tier = profiles.canonical_voice_tier(tier)
    record = (await profiles.load_profile_records(environment, [tier])).get(tier)
    if record is None or int(record["revision"]) != expected_revision:
        raise profiles.VoiceProfileError("revision_conflict", "Reload the saved setup before verification.", status_code=409)
    if profiles.is_native_profile(record["profile"]):
        return await _verify_native_profile(environment=environment, tier=tier, record=record, actor=actor)
    checks = await probe_profile(copy.deepcopy(record["profile"]))
    factory = get_session_factory()
    if factory is None:
        raise profiles.VoiceProfileError("durable_store_unavailable", "Verification requires the configuration store.", status_code=503)
    async with factory() as db:
        row = (await db.execute(select(TierAssignment).where(TierAssignment.environment == environment,
            TierAssignment.tier == tier).with_for_update())).scalar_one_or_none()
        current = profiles._profile_record(row)
        if current is None or int(current["revision"]) != expected_revision:
            raise profiles.VoiceProfileError("revision_conflict", "The setup changed during verification. Run the checks again.", status_code=409)
        evidence = {key: checks[key]["passed"] is True for key in profiles._EVIDENCE_KEYS}
        changed = evidence != current["profile"].get("evidence")
        current["profile"]["evidence"] = evidence
        # A successful recheck of the same approved runtime is metadata only.
        # It must not invalidate every tenant's saved voice selection.
        current["revision"] = expected_revision + int(changed)
        current["verification"] = {"checkedAt": datetime.now(timezone.utc).isoformat(), "checks": checks}
        row.stack_payload = {**row.stack_payload, "composed_voice_profile": current}
        flag_modified(row, "stack_payload")
        db.add(ConfigVersion(resource_type="voice_profile_verification", resource_id=f"{environment}:{tier}",
            version=current["revision"], payload={"actor": actor, **current["verification"]}))
        await db.commit()
        from server.db.tier_store import _cache_put
        _cache_put(environment, tier, row.stack_payload)
    profiles.invalidate_profile_caches(tier)
    return {"profile": await profiles.profile_view(tier, environment, include_internal=True), "checks": checks}


async def _verify_native_profile(*, environment: str, tier: str, record: dict[str, Any], actor: str) -> dict[str, Any]:
    """Native audio is gated by the runtime registry, not synthetic stage probes.

    The composed probes (separate STT, text model and TTS) do not apply to one
    live audio model, so readiness excludes them for native profiles. This runs
    the static registry/voice check, records it, and points the operator to
    Test Studio for a live audio session. It never fabricates stage evidence.
    """
    blockers = profiles._runtime_profile_blockers(copy.deepcopy(record["profile"]))
    passed = not blockers
    na = "Not applicable to native audio; confirm call quality with a Test Studio session."
    checks: dict[str, dict[str, Any]] = {key: {"passed": None, "notApplicable": True, "detail": na} for key in profiles._EVIDENCE_KEYS}
    checks["credentialRefConfigured"] = {
        "passed": passed,
        "detail": "Provider, live model and voices are configured and approved." if passed
        else "; ".join(b["message"] for b in blockers),
    }
    factory = get_session_factory()
    if factory is None:
        raise profiles.VoiceProfileError("durable_store_unavailable", "Verification requires the configuration store.", status_code=503)
    async with factory() as db:
        row = (await db.execute(select(TierAssignment).where(TierAssignment.environment == environment,
            TierAssignment.tier == tier).with_for_update())).scalar_one_or_none()
        current = profiles._profile_record(row)
        if current is None or int(current["revision"]) != int(record["revision"]):
            raise profiles.VoiceProfileError("revision_conflict", "The setup changed during verification. Run the checks again.", status_code=409)
        current["verification"] = {"checkedAt": datetime.now(timezone.utc).isoformat(), "checks": checks, "native": True}
        row.stack_payload = {**row.stack_payload, "composed_voice_profile": current}
        flag_modified(row, "stack_payload")
        db.add(ConfigVersion(resource_type="voice_profile_verification", resource_id=f"{environment}:{tier}",
            version=current["revision"], payload={"actor": actor, **current["verification"]}))
        await db.commit()
        from server.db.tier_store import _cache_put
        _cache_put(environment, tier, row.stack_payload)
    profiles.invalidate_profile_caches(tier)
    return {"profile": await profiles.profile_view(tier, environment, include_internal=True), "checks": checks}
