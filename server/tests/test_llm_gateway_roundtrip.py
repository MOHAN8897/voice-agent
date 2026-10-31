"""Offline HTTP-to-HTTP tests of actual model adapters and durable tool execution."""
from __future__ import annotations

import importlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from server.db import connection
from server.db.models.integration_models import ToolExecution
from server.providers import gemini_llm, sarvam_llm
from server.providers.base import StageSelection
from server.services import tool_router
from server.services.nango_service import NangoService
from server.services.tool_schema_registry import get_tools_for_tenant
from server.tests.test_integration_security_hardening import AID, FOREIGN, TID
from server.tests.test_integration_security_hardening import db as integration_db  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,model,mode", [
    ("gemini", "gemini-3.8-flash", "streaming_rest"),
    ("sarvam", "sarvam-105b-conversations", "chat_completions_v1"),
])
async def test_selected_model_gateway_roundtrip_is_authorized_and_write_is_not_repeated(
    integration_db, monkeypatch, provider, model, mode,  # noqa: F811 - imported pytest fixture
):
    import server.providers

    module = importlib.import_module("server.call.live_turn_orchestrator")
    monkeypatch.setattr(connection, "get_session_factory", lambda: integration_db)
    router = tool_router.DialtactToolRouter()
    router.nango = NangoService(secret_key="offline-test-key")
    monkeypatch.setattr(tool_router, "tool_router", router)
    requests, writes = [], []
    args = {"channel": "C-test", "text": "Requested appointment follow-up"}
    response_text = json.dumps({"spoken_response": "Your team has the request.",
        "memory_update": {"operations": []}, "end_call": {"should_end": False}})

    def handle(request):
        payload = json.loads(request.content)
        if request.url.host == "api.nango.dev":
            assert request.url.path == "/proxy/chat.postMessage"
            assert request.headers["connection-id"] == "owned"
            assert payload == args
            writes.append(request)
            return httpx.Response(200, json={"ok": True, "ts": "message-confirmed"})
        assert request.url.host in {"generativelanguage.googleapis.com", "api.sarvam.ai"}
        requests.append(payload)
        action_turn = len(requests) % 2 == 1
        call_id = f"action-{len(requests)}"
        if provider == "gemini":
            assert f"models/{model}:streamGenerateContent" in request.url.path
            if action_turn:
                parts = [{"functionCall": {"id": call_id, "name": "SLACK_SEND_MESSAGE", "args": args},
                    "thoughtSignature": "signed-model-history"}]
            else:
                history = payload["contents"][-2:]
                assert history[0]["parts"][0]["thoughtSignature"] == "signed-model-history"
                result = history[1]["parts"][0]["functionResponse"]
                assert result["id"] == f"action-{len(requests)-1}"
                assert result["response"]["message_id"] == "message-confirmed"
                parts = [{"text": response_text}]
            packet = {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}]}
        else:
            assert request.url.path == "/v1/chat/completions" and payload["model"] == model
            if action_turn:
                delta = {"tool_calls": [{"index": 0, "id": call_id, "type": "function", "function": {
                    "name": "SLACK_SEND_MESSAGE", "arguments": json.dumps(args)}}]}
            else:
                result = payload["messages"][-1]
                assert result["role"] == "tool" and result["tool_call_id"] == f"action-{len(requests)-1}"
                assert json.loads(result["content"])["message_id"] == "message-confirmed"
                delta = {"content": response_text}
            packet = {"choices": [{"delta": delta, "finish_reason": "tool_calls" if action_turn else "stop"}]}
        return httpx.Response(200, text="data: " + json.dumps(packet) + "\n\ndata: [DONE]\n\n",
            headers={"content-type": "text/event-stream"})

    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(handle), **kwargs))
    monkeypatch.setattr(gemini_llm, "_api_key", lambda: "offline-test-key")
    adapter = gemini_llm.GeminiLLMAdapter() if provider == "gemini" else sarvam_llm.SarvamLLMAdapter(api_key="offline-test-key")
    registry = SimpleNamespace(get_llm=lambda selected: adapter if selected == provider else pytest.fail("Provider changed"),
        is_provider_enabled=lambda *_: True, is_model_allowed=lambda *_: True)
    monkeypatch.setattr(server.providers, "get_provider_registry", lambda: registry)
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(use_provider_registry=True, composed_first_attempt_max_tokens=1280, composed_retry_max_tokens=2560))
    orchestrator = module.LiveTurnOrchestrator()
    tools = [tool for tool in get_tools_for_tenant(["SLACK"]) if tool["name"] == "SLACK_SEND_MESSAGE"]
    monkeypatch.setattr(orchestrator, "_load_composed_tenant_tools", AsyncMock(return_value=tools))
    ctx = SimpleNamespace(pipeline="composed_voice", tenant_id=str(TID), agent_id=str(AID), call_id="offline-call",
        callback_request_text="", resolved_stack=SimpleNamespace(llm=StageSelection(provider, model, {"api_mode": mode})))
    for _ in range(2):
        events = [event async for event in orchestrator._stream_llm(ctx=ctx, transcript="Send the follow-up",
            structured_live_turn=True, input_messages=[{"role": "user", "content": "Send the follow-up"}])]
        assert events[-1]["text"] == "Your team has the request."
    assert len(requests) == 4 and len(writes) == 1
    async with integration_db() as session:
        execution = (await session.execute(select(ToolExecution))).scalar_one()
        assert execution.status == "succeeded" and execution.tenant_id == TID
    denied = await router.route_and_execute(tenant_id=str(TID), agent_id=str(FOREIGN), call_id="offline-call",
        tool_name="SLACK_SEND_MESSAGE", arguments=args)
    assert denied["status"] == "error" and len(writes) == 1


@pytest.mark.asyncio
async def test_profile_save_keeps_existing_approved_global_rate_version_immutable(integration_db, monkeypatch):  # noqa: F811
    from server.db import tier_store
    from server.db.models.entities import Base, ConfigVersion, TierAssignment
    from server.db.models.saas_models import BillingRateVersion
    from server.services.saas import voice_stack_profiles as profiles
    from server.services.saas.voice_stack_defaults import recommended_composed_profile

    async with integration_db.kw["bind"].begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[
            TierAssignment.__table__, ConfigVersion.__table__, BillingRateVersion.__table__]))
    profile = recommended_composed_profile("medium")
    profile["retailRateInr"] = 8.25
    record = {"revision": 7, "profile": profile, "publicAliases": profiles._choice_keys(profile)}
    async with integration_db() as session:
        session.add(TierAssignment(environment="development", tier="medium", combination_id="existing",
            stack_payload={"composed_voice_profile": record}))
        session.add(BillingRateVersion(version=3, pstn_rate_usd_cents_per_min=10, web_agent_rate_usd_cents_per_min=5,
            did_monthly_usd_cents=100, fx_rate_inr=90, created_by="test", reason="Approved rates",
            pstn_medium_rate_inr_paise_per_min=500, pstn_medium_rate_usd_micros_per_min=55556))
        await session.commit()
    monkeypatch.setattr(profiles, "get_session_factory", lambda: integration_db)
    monkeypatch.setattr(profiles, "profile_view", AsyncMock(return_value={"revision": 8}))
    monkeypatch.setattr(tier_store, "_cache_put", lambda *_: None)
    await profiles.save_composed_profile(environment="development", tier="medium", expected_revision=7,
        payload=profile, actor="offline-operator")
    async with integration_db() as session:
        rate = (await session.execute(select(BillingRateVersion))).scalar_one()
        assert rate.version == 3 and rate.pstn_medium_rate_inr_paise_per_min == 500
        assert rate.pstn_medium_rate_usd_micros_per_min == 55556
        saved = (await session.execute(select(TierAssignment))).scalar_one()
        assert saved.stack_payload["composed_voice_profile"]["revision"] == 8
        assert saved.stack_payload["composed_voice_profile"]["profile"]["retailRateInr"] == 8.25
