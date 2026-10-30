"""An admin change to a tier's stack or price never alters a call already in progress.

A call is admitted with a snapshot: the resolved stack, the voice profile
revision and the rate version are pinned on the call row and in its ledger
meta. Later admin edits apply to the next call only.
"""
from unittest.mock import AsyncMock, Mock

import pytest

from server.call import call_context
from server.call.call_ledger import call_ledger
from server.call.call_lifecycle_service import CallLifecycleService
from server.config.env import get_settings

TENANT = "00000000-0000-4000-8000-000000000001"
COMPILED = (
    "@language: te-IN\n"
    "--- SPOKEN LANGUAGE (te-IN) ---\nSpeak only Telugu.\n\n"
    "--- CALLING SCRIPT ---\n--- AGENT IDENTITY ---\nYou are a test agent.\n\n"
    "--- CALL END POLICY ---\nClose only on an explicit goodbye.\n\n"
    "--- STATIC OUTPUT RULES ---\nRules.\n\n"
    "Language: te-IN"
)


@pytest.fixture
def lifecycle(monkeypatch, tmp_path):
    from server.call.call_store import call_store
    from server.realtime.manager import realtime_text_manager
    from server.realtime.voice_manager import realtime_voice_manager
    from server.services import test_studio_config
    from server.services.saas import billing_wallet_service, campaign_script

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    call_context.clear_all()
    service = CallLifecycleService()
    agent = {"agent_id": "pinned-agent", "tenant_id": TENANT, "languages": ["te-IN"]}
    monkeypatch.setattr(service, "_resolve_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(service, "_lock_compiled_brain", AsyncMock(return_value=("v1", COMPILED, "published")))
    monkeypatch.setattr(service, "_schedule_max_duration_watchdog", Mock())
    monkeypatch.setattr(test_studio_config, "saved_call_config", lambda _: {})
    insert = AsyncMock()
    monkeypatch.setattr(call_store, "insert", insert)
    max_duration = AsyncMock(return_value=900)
    monkeypatch.setattr(billing_wallet_service, "max_allowed_call_duration_sec", max_duration)
    monkeypatch.setattr(campaign_script, "campaign_call_script", AsyncMock(return_value=None))
    monkeypatch.setattr(realtime_text_manager, "create", AsyncMock())
    monkeypatch.setattr(realtime_voice_manager, "create", AsyncMock())
    yield service, insert, max_duration
    call_context.clear_all()
    call_ledger.reset_for_tests()
    get_settings.cache_clear()


def _stack(tts_model: str):
    from server.providers.base import ResolvedStack, StageSelection

    return ResolvedStack(
        combination_id=f"profile-{tts_model}", tier="medium", mode="env", language="te-IN",
        stt=StageSelection("sarvam", "saaras:v3-realtime", {"mode": "realtime"}),
        llm=StageSelection("sarvam", "sarvam-105b-conversations", {"api_mode": "chat_completions_v1"}),
        tts=StageSelection("sarvam", tts_model, {"api_mode": "websocket", "speaker": "shubh"}),
    )


def _override(stack, revision: int, paise: int, version: int):
    snapshot = {"tier": "medium", "profileRevision": revision, "voiceId": "public-voice-1",
                "retailRate": {"complete": True, "usdMicrosPerMin": paise * 10_000 // 95,
                               "inrPaisePerMin": paise, "fxRateInr": 95.0, "version": version}}
    return {**stack.to_safe_dict(), "pipeline": "composed_voice", "voice_flow": "composed_stages",
            "_voice_stack_snapshot": snapshot}


@pytest.mark.asyncio
async def test_mid_call_admin_change_keeps_stack_revision_and_price(lifecycle, monkeypatch):
    from server.services.saas import billing_rates
    from server.services.saas.billing_wallet_service import _resolve_call_wallet_debit

    service, insert, max_duration = lifecycle
    old_stack = _stack("bulbul:v2")
    monkeypatch.setattr(service, "_resolve_locked_stack", Mock(return_value=old_stack))
    started = await service.start(agent_id="pinned-agent", tenant_id=TENANT, session_id="midcall-1",
                                  channel="pstn", tier="medium", stack_override=_override(old_stack, 3, 900, 7))
    call_id = started["call_id"]
    record = insert.await_args.args[0]
    # The call row pins both the rate version and the stack revision it was admitted with.
    assert record["rate_version"] == 7
    assert record["voice_profile_revision"] == 3
    assert record["applied_rate_inr_paise_per_min"] == 900
    # The duration watchdog is sized from the pinned price, not the env default.
    assert max_duration.await_args.kwargs["rate_inr_paise_per_min"] == 900

    # Admin now publishes a new stack (revision 4) and a new price (rate version 8).
    billing_rates.set_cached_rates({
        "version": 8, "pstn_rate_usd_cents_per_min": 50, "web_agent_rate_usd_cents_per_min": 50,
        "did_monthly_usd_cents": 100, "fx_rate_inr": 95.0, "pstn_rate_inr_paise_per_min": 4_750,
        "pstn_medium_rate_inr_paise_per_min": 4_750,
    })
    new_stack = _stack("bulbul:v3")
    monkeypatch.setattr(service, "_resolve_locked_stack", Mock(return_value=new_stack))

    # The live call is untouched: same stage selections, same price snapshot.
    ctx = call_context.get(call_id)
    assert ctx.resolved_stack is old_stack and ctx.resolved_stack.tts.model == "bulbul:v2"
    meta = call_ledger.read_meta(call_id)
    assert meta["rate_snapshot"]["version"] == 7 and meta["rate_snapshot"]["inrPaisePerMin"] == 900
    assert meta["voice_stack_snapshot"]["profileRevision"] == 3

    # Its charge at hangup uses the pinned rate: 120 s at ₹9/min = ₹18, not ₹95.
    _cents, paise, _mode = _resolve_call_wallet_debit(
        call_id=call_id, channel="pstn", duration_sec=120, settings=get_settings(),
        stored_rate_cents=record["applied_rate_usd_cents_per_min"],
        stored_rate_micros=record["applied_rate_usd_micros_per_min"],
        stored_rate_inr_paise=record["applied_rate_inr_paise_per_min"],
        stored_fx=record["applied_fx_rate_inr"],
    )
    assert paise == 1_800

    # The next call is admitted on the new stack and the new price.
    second = await service.start(agent_id="pinned-agent", tenant_id=TENANT, session_id="midcall-2",
                                 channel="pstn", tier="medium", stack_override=_override(new_stack, 4, 4_750, 8))
    next_record = insert.await_args.args[0]
    assert next_record["rate_version"] == 8 and next_record["voice_profile_revision"] == 4
    assert call_context.get(second["call_id"]).resolved_stack.tts.model == "bulbul:v3"
    # ...while the first call still holds its own snapshot.
    assert call_context.get(call_id).resolved_stack.tts.model == "bulbul:v2"
    billing_rates.clear_rates_cache()


@pytest.mark.asyncio
async def test_watchdog_duration_uses_pinned_rate(monkeypatch):
    import uuid
    from types import SimpleNamespace

    from server.services.saas import billing_wallet_service as wallet

    settings = SimpleNamespace(saas_auth_enabled=True, pstn_rate_usd_cents_per_min=1,
                               web_agent_rate_usd_cents_per_min=1, fx_rate_inr=95.0)
    monkeypatch.setattr(wallet, "get_settings", lambda: settings)
    monkeypatch.setattr(wallet, "get_or_create_wallet", AsyncMock(return_value=SimpleNamespace(
        balance_cents=0, balance_inr_paise=1_000)))  # ₹10
    # ₹10 at the pinned ₹5/min covers 120 s; the env default rate (1¢/min) would allow far longer.
    assert await wallet.max_allowed_call_duration_sec(uuid.uuid4(), global_cap_sec=900,
                                                      rate_inr_paise_per_min=500, rate_usd_micros_per_min=52_632,
                                                      fx_rate_inr=95.0) == 120
    assert await wallet.max_allowed_call_duration_sec(uuid.uuid4(), global_cap_sec=900) == 631
