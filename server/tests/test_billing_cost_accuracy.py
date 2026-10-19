from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.services.saas.billing_wallet_service import _resolve_call_wallet_debit
from server.services.saas.cost_insights import build_insights, model_cost
from server.services.vobiz_billing import cdr_billing_fields


def test_locked_retail_price_is_independent_of_supplier_usage():
    cents, paise, mode = _resolve_call_wallet_debit(call_id="test", channel="pstn", duration_sec=90,
        settings=SimpleNamespace(), stored_rate_cents=12, stored_rate_micros=120000,
        stored_rate_inr_paise=900, stored_fx=75)
    assert (cents, paise, mode) == (18, 1350, "catalog_prorated")
    assert _resolve_call_wallet_debit(call_id="test", channel="pstn", duration_sec=0, settings=SimpleNamespace())[:2] == (0, 0)


def test_connected_clock_excludes_ringing_and_teardown(monkeypatch):
    from server.call.call_lifecycle_service import _billable_duration_sec
    connected = datetime(2026, 10, 19, 10, tzinfo=timezone.utc)
    meta = {"channel": "pstn", "billing_timing_version": 2, "connected_at": connected.isoformat(),
        "disconnected_at": (connected + timedelta(seconds=90)).isoformat()}
    monkeypatch.setattr("server.call.call_ledger.call_ledger.read_meta", lambda _cid: meta)
    assert _billable_duration_sec("call", connected + timedelta(seconds=130), 160) == 90
    meta["carrier_billable_duration_sec"] = 88
    assert _billable_duration_sec("call", connected + timedelta(seconds=130), 160) == 88
    meta["carrier_billable_duration_sec"] = 0
    assert _billable_duration_sec("call", connected + timedelta(seconds=130), 160) == 0


def test_browser_setup_failure_never_starts_customer_clock(monkeypatch):
    from server.call.call_lifecycle_service import _billable_duration_sec
    monkeypatch.setattr("server.call.call_ledger.call_ledger.read_meta", lambda _cid: {"channel":"browser", "billing_timing_version":2})
    assert _billable_duration_sec("call", datetime.now(timezone.utc), 45) == 0


@pytest.mark.asyncio
async def test_browser_supplier_cost_has_no_carrier(monkeypatch, tmp_path):
    from server.call.call_ledger import call_ledger
    from server.config.env import get_settings
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        await call_ledger.init("web", {"channel":"browser", "pipeline":"realtime_voice", "usage":{"model_cost_usd":.1, "fx_rate_inr":80}})
        call_ledger.stamp_ended_usage("web", reason="stop", duration_sec=60)
        usage = call_ledger.read_meta("web")["usage"]
        assert usage["cost_usd"] == pytest.approx(.1)
        assert usage["telephony_usd"] == usage["telnyx_usd"] == usage["vobiz_usd"] == 0
        assert usage["carrier_cost_source"] == "not_applicable"
    finally:
        get_settings.cache_clear()


def test_vobiz_cdr_uses_talk_seconds_and_cost_not_ring_duration():
    cid = "synthetic-call"
    fields = cdr_billing_fields({"data":{"uuid":cid, "duration":120, "billsec":60, "ring_time":60,
        "total_cost":"1.30", "currency":"INR"}}, cid)
    assert fields["carrier_billable_duration_sec"] == 60
    assert fields["carrier_billing"]["amount"] == 1.3
    assert fields["carrier_billing"]["includes_streaming"]
    assert not cdr_billing_fields({"data":{"uuid":"other", "billsec":120, "total_cost":1}}, cid)


@pytest.mark.parametrize("value", [None, -1, "NaN", "Infinity", True, "bad"])
def test_invalid_cdr_cannot_change_billing_clock(value):
    assert not cdr_billing_fields({"data":{"uuid":"call", "billsec":value}}, "call")


def test_cdr_zero_billsec_is_valid_and_total_duration_is_not_a_fallback():
    assert cdr_billing_fields({"data":{"uuid":"call", "billsec":0, "duration":60}}, "call")["carrier_billable_duration_sec"] == 0
    assert not cdr_billing_fields({"data":{"uuid":"call", "duration":60}}, "call")


def rates():
    return {"fx_rate_inr":80, "pstn_rate_usd_micros_per_min":200000, "pstn_rate_inr_paise_per_min":1600,
        "web_agent_rate_usd_micros_per_min":100000, "web_agent_rate_inr_paise_per_min":800}


def test_average_weights_minutes_and_shows_missing_usage_and_setup_overhead():
    now = datetime.now(timezone.utc)
    rows = [{"call_id":"one", "tenant_id":"tenant-a", "channel":"pstn", "duration_sec":60},
        {"call_id":"two", "tenant_id":"tenant-b", "channel":"pstn", "duration_sec":180},
        {"call_id":"missing", "tenant_id":"tenant-a", "channel":"pstn", "duration_sec":60},
        {"call_id":"web", "tenant_id":"tenant-a", "channel":"browser", "duration_sec":60}]
    metadata = {}
    for row, cost in zip(rows, [1, 9, None, .5]):
        metadata[row["call_id"]] = {"tenant_id":row["tenant_id"], "usage":{"cost_accounting_version":2,
            "model_cost_usd":cost, "fx_rate_inr":80, "llm_model":"gemini-3.8-live"},
            "carrier_billing":{"source":"vobiz_cdr", "amount":0, "currency":"INR"}}
    result = build_insights(rows, rates(), since=now-timedelta(days=30), now=now,
        ledger=SimpleNamespace(read_meta=lambda cid:metadata[cid]), overhead_rows=[{"cost_usd":.3,"cost_inr":24}])
    pstn, web = result["channels"]
    assert pstn["averageUsdPerMin"] == pytest.approx(2.575)  # (1 + 9 + .3) / 4 minutes.
    assert pstn["coveragePercent"] == 66.7
    assert pstn["missingCostCalls"] == 1 and pstn["carrierCdrCalls"] == 2
    assert web["averageUsdPerMin"] == .5 and web["carrierUsd"] == 0
    assert len(result["samples"]) == 3
    assert all("phone" not in row and "transcript" not in row for row in result["samples"])


def test_empty_cost_data_has_no_invented_average():
    now = datetime.now(timezone.utc)
    result = build_insights([], rates(), since=now-timedelta(days=30), now=now, overhead_rows=[])
    assert all(channel["averageUsdPerMin"] is None for channel in result["channels"])


def test_historical_gemini_snapshots_can_be_reconstructed_read_only():
    usage = {"llm_model":"gemini-3.8-live", "model_cost_usd":3,
        "response_usage":{"one":{"cost_usd":1}, "two":{"cost_usd":3}}}
    assert model_cost(usage) == (Decimal(4), "reconstructed_responses")
    assert usage["model_cost_usd"] == 3
    assert model_cost({"llm_model":"gemini-3.8-live", "model_cost_usd":3})[0] is None


@pytest.mark.asyncio
async def test_cdr_api_failure_keeps_call_available(monkeypatch):
    from server.services.vobiz_billing import reconcile_vobiz_call
    monkeypatch.setattr("server.call.call_ledger.call_ledger.read_meta", lambda _cid:{"channel":"pstn", "vobiz_call_uuid":"call"})
    fake = SimpleNamespace(configured=True, get_call_cdr=AsyncMock(side_effect=RuntimeError("unavailable")))
    monkeypatch.setattr("server.services.vobiz_client.VobizClient", lambda:fake)
    monkeypatch.setattr("server.services.vobiz_billing.asyncio.sleep", AsyncMock())
    assert not await reconcile_vobiz_call("call")
    assert fake.get_call_cdr.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["customer_admin", "customer_viewer", "voice_engineer"])
async def test_cost_insights_rejects_non_billing_roles(role, monkeypatch):
    import time
    from fastapi import HTTPException
    from server.auth.session import SessionData
    from server.routes.dev_admin import billing_cost_insights
    loader = AsyncMock(side_effect=AssertionError("must not load tenant data"))
    monkeypatch.setattr("server.services.saas.cost_insights.load_cost_insights", loader)
    session = SessionData(kind="dev", subject="synthetic", tenant_id="tenant", role=role, issued_at=int(time.time()))
    with pytest.raises(HTTPException) as caught:
        await billing_cost_insights(days=30, session=session)
    assert caught.value.status_code == 403
    loader.assert_not_awaited()


@pytest.mark.asyncio
async def test_cost_insights_allows_platform_billing_admin(monkeypatch):
    import time
    from server.auth.session import SessionData
    from server.auth.rbac import ROLE_PLATFORM_ADMIN
    from server.routes.dev_admin import billing_cost_insights
    loader = AsyncMock(return_value={"channels":[]})
    monkeypatch.setattr("server.services.saas.cost_insights.load_cost_insights", loader)
    monkeypatch.setattr("server.routes.dev_admin._require_db", lambda:None)
    session = SessionData(kind="dev", subject="synthetic", tenant_id="tenant", role=ROLE_PLATFORM_ADMIN, issued_at=int(time.time()))
    assert await billing_cost_insights(days=7, session=session) == {"channels":[]}
    loader.assert_awaited_once_with(7)


@pytest.mark.asyncio
async def test_unused_prewarm_cost_persists_and_connected_usage_is_not_counted_twice(monkeypatch, tmp_path):
    from server.services.saas import prewarm_cost_records as records
    from server.services.saas.cost_insights import read_unused_prewarm
    monkeypatch.setattr(records, "record_directory", lambda:tmp_path)
    monkeypatch.setattr("server.services.usage_pricing.resolve_fx_rate_inr", lambda:{"rate":80})
    key = await records.record_prepared("attempt", tenant_id="tenant", usage={"input_tokens":100,"output_tokens":50}, model="gemini-3.8-live")
    await records.mark_usage(key)
    now = datetime.now(timezone.utc)
    assert len(read_unused_prewarm(now-timedelta(days=1), now)) == 1
    await records.mark_usage(key, call_id="connected-call")
    await records.mark_usage(key)
    assert read_unused_prewarm(now-timedelta(days=1), datetime.now(timezone.utc)) == []


@pytest.mark.parametrize("bad_meta", [None, [], {"tenant_id":"tenant", "usage":[]},
    {"tenant_id":"tenant", "usage":{"llm_model":"gemini-3.8-live", "response_usage":[1]}},
    {"tenant_id":"tenant", "usage":{"llm_model":"gemini-3.8-live", "response_usage":{"one":{"cost_usd":1}}, "prewarm_input_tokens":"bad"}}])
def test_malformed_cost_records_are_excluded_without_breaking_report(bad_meta):
    now = datetime.now(timezone.utc)
    rows = [{"call_id":"one", "tenant_id":"tenant", "channel":"browser", "duration_sec":60}]
    report = build_insights(rows, rates(), since=now-timedelta(days=7), now=now,
        ledger=SimpleNamespace(read_meta=lambda _:bad_meta), overhead_rows=[])
    assert report["channels"][1]["missingCostCalls"] == 1
    assert report["channels"][1]["averageUsdPerMin"] is None


def test_partial_call_cohort_does_not_absorb_full_window_setup_costs():
    now = datetime.now(timezone.utc)
    report = build_insights([], rates(), since=now-timedelta(days=30), now=now, capped=True,
        overhead_rows=[{"cost_usd":10,"cost_inr":800}])
    assert report["channels"][0]["unconnectedPrewarmUsd"] == 0


@pytest.mark.asyncio
async def test_late_and_out_of_order_usage_preserves_carrier_and_end_clock(monkeypatch, tmp_path):
    from server.call.call_ledger import call_ledger
    from server.config.env import get_settings
    from server.services.pstn_realtime_voice_core import record_realtime_voice_usage
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    monkeypatch.setattr("server.services.usage_pricing.resolve_fx_rate_inr", lambda **kw:{"rate":80})
    try:
        cid = "late-usage"
        ended = "2026-10-19T10:01:00+00:00"
        await call_ledger.init(cid, {"channel":"pstn", "telephony_provider":"vobiz",
            "ended_at":ended, "disconnected_at":ended, "duration_sec":60,
            "carrier_billing":{"source":"vobiz_cdr", "amount":1.3,"currency":"INR"}})
        args = {"call_id":cid,"llm_model":"gemini-3.8-live"}
        usage = {"input_tokens":573,"input_audio_tokens":222,"output_tokens":33,"output_audio_tokens":33,
            "usage_scope":"response","usage_id":"first"}
        await record_realtime_voice_usage(**args, usage=usage)
        assert await record_realtime_voice_usage(**args, usage={**usage,"input_tokens":500}) is None
        assert await record_realtime_voice_usage(**args, usage=usage) is None
        await record_realtime_voice_usage(**args, usage={**usage,"usage_id":"second","input_tokens":632,"input_audio_tokens":255})
        meta = call_ledger.read_meta(cid)
        assert meta["ended_at"] == ended and meta["duration_sec"] == 60
        assert meta["usage"]["input_tokens"] == 1205
        assert meta["usage"]["output_tokens"] == 66
        assert meta["usage"]["model_cost_usd"] == pytest.approx(.002769)
        assert meta["usage"]["cost_usd"] == pytest.approx(.002769 + 1.3 / 80)
    finally:
        get_settings.cache_clear()


def test_billing_marker_failure_cannot_interrupt_media_teardown(monkeypatch):
    from server.call.billing_timing import mark_call_connected, mark_call_disconnected
    monkeypatch.setattr("server.call.call_ledger.call_ledger.read_meta", lambda _: (_ for _ in ()).throw(OSError()))
    mark_call_connected("call")
    mark_call_disconnected("call")


@pytest.mark.asyncio
async def test_post_call_transcription_prices_tokens_and_keeps_vobiz_in_total(monkeypatch, tmp_path):
    from server.call.call_ledger import call_ledger
    from server.call.post_call_transcription import _apply_transcript_billing
    from server.config.env import get_settings
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    monkeypatch.setattr("server.services.usage_pricing.resolve_fx_rate_inr", lambda **kw:{"rate":80})
    try:
        await call_ledger.init("transcript-cost", {"channel":"pstn", "pipeline":"realtime_voice", "telephony_provider":"vobiz",
            "usage":{"llm_model":"gemini-3.8-live", "model_cost_usd":.1,"duration_sec":60, "vobiz_usd":.02,"telephony_usd":.02},
            "carrier_billing":{"source":"vobiz_cdr", "currency":"USD", "amount":.02},
            "post_call_transcript":{"status":"complete"}})
        await _apply_transcript_billing("transcript-cost", path=tmp_path / "recording.wav", model="gemini-3.5-transcribe",
            usage_meta={"input_tokens":1500,"output_tokens":175})
        usage = call_ledger.read_meta("transcript-cost")["usage"]
        assert usage["post_call_transcript_usd"] == pytest.approx(.0051)
        assert usage["post_call_transcript_cost_source"] == "reported_tokens"
        assert usage["cost_usd"] == pytest.approx(.1251)
        call_ledger.stamp_ended_usage("transcript-cost", reason="ended", duration_sec=120)
        usage = call_ledger.read_meta("transcript-cost")["usage"]
        assert usage["post_call_transcript_usd"] == pytest.approx(.0051)
        assert usage["cost_usd"] == pytest.approx(.1251)
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_post_call_costs_are_isolated_idempotent_and_included_in_average(monkeypatch, tmp_path):
    import asyncio
    from server.call.call_ledger import call_ledger
    from server.config.env import get_settings
    from server.services.saas.post_call_costs import capture_post_call_cost, record_post_call_response
    from server.services.usage_pricing import cost_llm_usd
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    monkeypatch.setattr("server.services.usage_pricing.resolve_fx_rate_inr", lambda **kw:{"rate":80})
    try:
        for cid in ("call-a", "call-b"):
            await call_ledger.init(cid, {"tenant_id":"tenant", "channel":"browser", "ended_at":"2026-10-19T10:01:00Z", "duration_sec":60,
                "usage":{"cost_accounting_version":2,"llm_model":"gemini-3.8-live","model_cost_usd":.1,"fx_rate_inr":80}})
        response = SimpleNamespace(id="response-one", usage={"input_tokens":1000,"output_tokens":100,
            "input_tokens_details":{"cached_tokens":800,"cache_write_tokens":0}})
        async def record(cid):
            with capture_post_call_cost(cid):
                await record_post_call_response(response, "gpt-5.6-luna")
                await record_post_call_response(response, "gpt-5.6-luna")
        await asyncio.gather(record("call-a"), record("call-b"))
        from server.providers.openai_llm import OpenAILLMAdapter
        from server.providers.base import LLMConfig
        parsed_response = SimpleNamespace(id="response-two", usage=response.usage, output_text='{"value":1}')
        client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=parsed_response)))
        monkeypatch.setattr("server.utils.http_clients.get_openai_client", lambda:client)
        with capture_post_call_cost("call-a"):
            payload = await OpenAILLMAdapter().structured_completion([], {}, LLMConfig(provider="openai", model="gpt-5.6-luna"))
            assert payload == {"value":1}
        # No context means no call attribution, even for unrelated completions.
        await record_post_call_response(SimpleNamespace(id="other",usage=response.usage), "gpt-5.6-luna")
        expected = cost_llm_usd(llm_model="gpt-5.6-luna",input_tokens=1000,output_tokens=100,cached_tokens=800)["total_usd"]
        for cid in ("call-a", "call-b"):
            usage = call_ledger.read_meta(cid)["usage"]
            count = 2 if cid == "call-a" else 1
            assert len(usage["post_call_analysis_responses"]) == count
            assert usage["post_call_analysis_usd"] == pytest.approx(expected * count)
            assert usage["cost_usd"] == pytest.approx(.1 + expected * count)
        now = datetime.now(timezone.utc)
        result = build_insights([{"call_id":"call-a","tenant_id":"tenant","channel":"browser","duration_sec":60}],
            rates(), since=now-timedelta(days=30), now=now, overhead_rows=[])
        assert result["channels"][1]["averageUsdPerMin"] == pytest.approx(.1 + expected * 2)
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_post_call_accounting_failure_does_not_retry_successful_generation(monkeypatch):
    from server.services.saas.post_call_costs import capture_post_call_cost, record_post_call_response
    monkeypatch.setattr("server.call.call_ledger.call_ledger.read_meta", lambda _: (_ for _ in ()).throw(OSError()))
    with capture_post_call_cost("call"):
        await record_post_call_response(SimpleNamespace(usage={"input_tokens":100,"output_tokens":10}), "gpt-5.6-luna")
