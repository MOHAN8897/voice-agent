"""Selected stacks must remain selected through admission and integration execution."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.providers.base import StackSelection, StageSelection
from server.providers.resolver import StackResolver
from server.utils.errors import AppError


def selected_stack():
    return StackSelection(stt=StageSelection("sarvam", "saaras:v3-realtime", {}),
        llm=StageSelection("gemini", "gemini-3.8-flash", {}),
        tts=StageSelection("sarvam", "bulbul:v3", {}), language="te-IN")


@pytest.mark.parametrize("failed_stage", ["stt", "llm", "tts"])
def test_resolver_never_substitutes_disabled_selected_stage(monkeypatch, failed_stage):
    from server.services.dev_fallback_store import dev_fallback_store
    from server.services.dev_secrets_store import dev_secrets_store

    monkeypatch.setattr(dev_secrets_store, "effective", lambda _key, default: default)
    monkeypatch.setattr(dev_fallback_store, "get_chains", lambda: {failed_stage: ["alternative"]})
    original = selected_stack()
    requested = getattr(original, failed_stage).provider
    registry = SimpleNamespace(
        is_provider_enabled=lambda provider, stage: not (provider == requested and stage == failed_stage),
        is_model_allowed=lambda *_: True,
        get_catalog=lambda: {"providers": [{"id": "alternative", "models": {
            failed_stage: [{"id": "replacement", "default": True}]}}]},
    )
    resolver = StackResolver(SimpleNamespace(voice_agent_config_mode="frontend", voice_agent_tier="medium"), registry)
    with pytest.raises(AppError):
        resolver.resolve(user_selection=original, language="te-IN")
    assert getattr(original, failed_stage).provider == requested


def test_unconfigured_custom_tier_cannot_inherit_medium_stack(monkeypatch):
    from server.db import tier_store
    from server.services.dev_secrets_store import dev_secrets_store

    monkeypatch.setattr(tier_store, "get_cached_tier_stack", lambda *_: None)
    monkeypatch.setattr(dev_secrets_store, "effective", lambda _key, default: default)
    registry = SimpleNamespace(is_provider_enabled=lambda *_: True, is_model_allowed=lambda *_: True)
    settings = SimpleNamespace(voice_agent_config_mode="env", voice_agent_tier="medium")
    with pytest.raises(AppError, match="tier"):
        StackResolver(settings, registry).resolve(tier="custom_standard")


@pytest.mark.asyncio
async def test_invalid_saved_voice_never_routes_to_platform_default(monkeypatch):
    from server.services.saas import pstn_saas_stack, voice_stack_profiles

    monkeypatch.setattr(pstn_saas_stack, "load_agent_voice_config", AsyncMock(return_value={}))
    monkeypatch.setattr(voice_stack_profiles, "load_profile_records", AsyncMock(return_value={}))
    monkeypatch.setattr(voice_stack_profiles, "resolve_agent_selection", AsyncMock(
        side_effect=voice_stack_profiles.VoiceProfileError("voice_selection_invalid", "Selected voice changed.")))
    fallback = AsyncMock()
    monkeypatch.setattr(pstn_saas_stack, "resolve_platform_phone_stack", fallback)
    with pytest.raises(voice_stack_profiles.VoiceProfileError, match="Selected voice changed"):
        await pstn_saas_stack.saas_stack_override_for_agent({
            "agent_id": "test-agent", "default_tier": "low", "environment": "development", "languages": ["te-IN"]})
    fallback.assert_not_awaited()


def test_composed_gemini_model_survives_pipeline_alignment():
    from server.realtime.models import coerce_live_llm_selection

    assert coerce_live_llm_selection("gemini", "gemini-3.8-flash",
        stack_override={"pipeline": "composed_voice"}) == ("gemini", "gemini-3.8-flash")


def test_conversation_model_cannot_be_sent_to_sarvam_v2():
    from server.providers.sarvam_llm import SarvamLLMAdapter

    with pytest.raises(ValueError, match="model|V2"):
        SarvamLLMAdapter._url("sarvam-105b-conversations", {"api_mode": "chat_completions_v2"})


@pytest.mark.asyncio
async def test_public_call_start_rejects_forged_internal_profile_snapshot(monkeypatch):
    from fastapi import HTTPException

    from server.routes import calls

    start = AsyncMock()
    monkeypatch.setattr(calls.call_lifecycle_service, "start", start)
    monkeypatch.setattr(calls, "get_settings", lambda: SimpleNamespace(saas_auth_enabled=False))
    body = calls.CallStartBody(stack_override={"pipeline": "composed_voice",
        "_voice_stack_snapshot": {"tier": "low", "retailRate": {"complete": True}}})
    with pytest.raises(HTTPException) as exc:
        await calls.call_start(body, request=SimpleNamespace(), _auth=None)
    assert exc.value.status_code in {400, 403, 422}
    start.assert_not_awaited()


@pytest.mark.parametrize("provider,model,pipeline", [
    ("gemini", "gemini-3.8-flash", "realtime_text"),
    ("sarvam", "sarvam-105b-conversations", "realtime_voice"),
    ("openai", "gemini-3.8-live", "realtime_voice"),
])
def test_selected_model_cannot_be_coerced_into_a_different_native_stack(provider, model, pipeline):
    from server.realtime.models import coerce_live_llm_selection

    with pytest.raises(ValueError, match="selected|native audio"):
        coerce_live_llm_selection(provider, model, stack_override={"pipeline": pipeline,
            "llm": {"provider": provider, "model": model}})


def test_session_names_are_tenant_bound_and_canonicalization_is_idempotent():
    from server.auth.call_sessions import tenant_session_id

    own = tenant_session_id("own", "client-key")
    assert own == tenant_session_id("own", own)
    assert own != tenant_session_id("other", "client-key")
    assert tenant_session_id("own", None) != tenant_session_id("own", None)


@pytest.mark.parametrize("stage", ["stt", "llm", "tts"])
def test_direct_adapter_getters_reject_unconfigured_catalog_entry(stage):
    from server.providers.registry import ProviderRegistry

    registry = ProviderRegistry.__new__(ProviderRegistry)
    registry._catalog = {"providers": [{"id": "selected", "enabled": True, "configured": False}]}
    registry._stt = registry._llm = registry._tts = {"selected": object()}
    with pytest.raises(KeyError):
        getattr(registry, f"get_{stage}")("selected")


def test_nested_stack_config_secrets_are_never_serialized():
    from server.providers.base import ResolvedStack

    config = {"api_key": "private", "nested": [{"Authorization": "private", "api-subscription-key": "private",
        "connectionId": "private", "webhookUrl": "private", "temperature": 0.3}], "model": "approved"}
    assert ResolvedStack._safe_config(config) == {"nested": [{"temperature": 0.3}], "model": "approved"}
    assert config["nested"][0]["Authorization"] == "private"


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign", [False, True])
async def test_failed_call_preflight_never_ends_the_existing_call(monkeypatch, foreign):
    from server.call import call_context
    from server.call.call_lifecycle_service import CallLifecycleService
    from server.services import test_studio_config

    service = CallLifecycleService()
    monkeypatch.setattr(service, "_resolve_agent", AsyncMock(return_value={"agent_id": "agent", "tenant_id": "own"}))
    monkeypatch.setattr(test_studio_config, "saved_call_config", lambda _: {})
    monkeypatch.setattr(call_context, "get_active_for_session", lambda _: SimpleNamespace(
        call_id="healthy", tenant_id="other" if foreign else "own"))
    def fail(**_):
        raise AppError("validation_error", message="Invalid selected stack", status_code=409)
    monkeypatch.setattr(service, "_resolve_locked_stack", fail)
    end = AsyncMock()
    monkeypatch.setattr(service, "end", end)
    with pytest.raises(AppError):
        await service.start(agent_id="agent", session_id="healthy-session")
    end.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_starts_for_one_session_are_serialized_before_preflight(monkeypatch):
    import asyncio

    from server.call import call_context
    from server.call.call_lifecycle_service import CallLifecycleService
    from server.services import test_studio_config

    service = CallLifecycleService()
    entered, release = asyncio.Event(), asyncio.Event()
    active, maximum = 0, 0

    async def resolve(*_args, **_kwargs):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        entered.set()
        await release.wait()
        active -= 1
        raise AppError("validation_error", message="Synthetic admission failure", status_code=409)

    monkeypatch.setattr(service, "_resolve_agent", resolve)
    monkeypatch.setattr(test_studio_config, "saved_call_config", lambda _: {})
    monkeypatch.setattr(call_context, "get_active_for_session", lambda _: None)
    first = asyncio.create_task(service.start(session_id="concurrent-admission-test"))
    await entered.wait()
    second = asyncio.create_task(service.start(session_id="concurrent-admission-test"))
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(first, second, return_exceptions=True)
    assert all(isinstance(result, AppError) for result in results)
    assert maximum == 1


@pytest.mark.parametrize("fx,price", [(None, 5), (0, 5), (float("nan"), 5), (90, 0), (90, float("inf")), (90, 0.00001)])
def test_custom_profile_cannot_inherit_a_parent_or_invent_exchange_rates(fx, price):
    from server.services.saas.voice_stack_profiles import _native_tier_retail_rate

    assert _native_tier_retail_rate({"fx_rate_inr": fx, "pstn_medium_rate_usd_micros_per_min": 10000,
        "pstn_medium_rate_inr_paise_per_min": 900, "version": 1}, "medium_copy",
        {"revision": 7, "profile": {"retailRateInr": price}}) is None
