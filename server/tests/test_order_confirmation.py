"""Order proof: validation, idempotency, tenant scope and the outcome guard."""
from __future__ import annotations

import json

import pytest
from types import SimpleNamespace

from server.call.order_confirmation import (
    claims_order_confirmation,
    enforce_order_proof,
    order_details_present,
    order_unconfirmed_line_for,
    read_order_proof,
    record_order_confirmation,
    validate_order_arguments,
)


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from server.config.env import get_settings

    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def _record(call_id="call-order", arguments=None, tenant_id="tenant-1", agent_id="agent-1"):
    return record_order_confirmation(
        call_id=call_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        arguments=arguments
        or {
            "quantity": 500,
            "customer_name": "Ravi",
            "delivery_address": "12 MG Road, Hyderabad",
            "product": "visiting cards",
        },
    )


def test_missing_details_are_rejected_with_codes_only():
    fields, code = validate_order_arguments(
        {"quantity": 0, "customer_name": "R", "delivery_address": "MG"}
    )
    assert fields is None and code == "invalid_quantity"
    _fields, code = validate_order_arguments(
        {"quantity": 10, "customer_name": " ", "delivery_address": "12 MG Road"}
    )
    assert code == "missing_customer_name"
    _fields, code = validate_order_arguments(
        {"quantity": 10, "customer_name": "Ravi", "delivery_address": "MG"}
    )
    assert code == "missing_delivery_address"


def test_confirmed_order_is_persisted_and_readable(_data_dir):
    result = _record()
    assert result == {
        "status": "ok",
        "order_confirmed": True,
        "already_confirmed": False,
        "quantity": 500,
    }
    proof = read_order_proof("call-order")
    assert order_details_present(proof)
    assert proof["customer_name"] == "Ravi"
    assert proof["delivery_address"] == "12 MG Road, Hyderabad"
    on_disk = json.loads(
        (_data_dir / "calls" / "call-order" / "order_confirmation.json").read_text(encoding="utf-8")
    )
    assert on_disk["status"] == "confirmed"
    assert on_disk["tenant_id"] == "tenant-1"
    assert on_disk["agent_id"] == "agent-1"


def test_duplicate_call_returns_the_first_confirmed_order():
    _record()
    second = record_order_confirmation(
        call_id="call-order",
        tenant_id="tenant-1",
        agent_id="agent-1",
        arguments={
            "quantity": 99,
            "customer_name": "Someone Else",
            "delivery_address": "Somewhere else entirely",
        },
    )
    assert second["status"] == "ok"
    assert second["already_confirmed"] is True
    assert second["quantity"] == 500
    proof = read_order_proof("call-order")
    assert proof["quantity"] == 500
    assert proof["customer_name"] == "Ravi"


def test_invalid_arguments_do_not_create_proof():
    result = _record(arguments={"quantity": 5, "customer_name": "Ravi"})
    assert result["status"] == "error"
    assert result["code"] == "missing_delivery_address"
    assert read_order_proof("call-order") is None


def test_proof_is_scoped_to_the_owning_tenant():
    _record()
    assert read_order_proof("call-order", tenant_id="tenant-1") is not None
    assert read_order_proof("call-order", tenant_id="tenant-2") is None


def test_missing_context_is_unauthorized():
    result = record_order_confirmation(
        call_id="call-order",
        tenant_id=None,
        agent_id="agent-1",
        arguments={"quantity": 1, "customer_name": "Ravi", "delivery_address": "12 MG Road"},
    )
    assert result == {
        "status": "error",
        "code": "unauthorized",
        "message": "This action is unavailable.",
    }


def test_claim_detector_matches_confirmation_but_not_questions():
    assert claims_order_confirmation("Your order is confirmed.")
    assert claims_order_confirmation("We have placed your booking.")
    assert claims_order_confirmation("మీ ఆర్డర్ నిర్ధారించబడింది.")
    assert not claims_order_confirmation("Shall I confirm your order?")
    assert not claims_order_confirmation("I will confirm the delivery address.")
    assert not claims_order_confirmation("The fee is eight thousand rupees.")


def test_unproven_conversion_is_downgraded_and_order_facts_removed():
    outcome = {
        "disposition": "converted",
        "summary_en": "The caller placed an order.",
        "facts": {"order_confirmed": "true", "product": "visiting cards"},
        "extracted_fields": {"order_confirmed": "true", "product": "visiting cards"},
    }
    reason = enforce_order_proof(outcome, None)
    assert reason == "order_proof_missing"
    assert outcome["disposition"] == "interested"
    assert outcome["facts"] == {"product": "visiting cards"}
    assert outcome["extracted_fields"] == {"product": "visiting cards"}


def test_proven_conversion_survives():
    outcome = {"disposition": "converted", "facts": {"order_confirmed": "true"}}
    proof = {
        "status": "confirmed",
        "quantity": 500,
        "customer_name": "Ravi",
        "delivery_address": "12 MG Road",
    }
    assert enforce_order_proof(outcome, proof) is None
    assert outcome["disposition"] == "converted"
    assert outcome["facts"]["order_confirmed"] == "true"


def test_qualified_is_only_downgraded_when_the_outcome_claims_an_order():
    narrative = {"disposition": "qualified", "summary_en": "The order was confirmed on the call."}
    assert enforce_order_proof(narrative, None) == "order_proof_missing"
    assert narrative["disposition"] == "interested"

    normal = {"disposition": "qualified", "summary_en": "Caller meets the criteria for a demo."}
    assert enforce_order_proof(normal, None) is None
    assert normal["disposition"] == "qualified"


def test_server_lines_are_localized():
    assert order_unconfirmed_line_for("te-IN")
    assert order_unconfirmed_line_for("hi-IN")
    assert order_unconfirmed_line_for("en-IN") == "Let me verify those details before I confirm anything."


@pytest.mark.asyncio
async def test_composed_tool_round_trip_records_proof_without_the_gateway(monkeypatch):
    from unittest.mock import AsyncMock

    from server.call import live_turn_orchestrator as module
    from server.services import tool_router

    gateway = AsyncMock(side_effect=AssertionError("native tool must not hit Nango"))
    monkeypatch.setattr(tool_router.tool_router, "route_and_execute", gateway)
    orchestrator = module.LiveTurnOrchestrator()
    ctx = SimpleNamespace(tenant_id="tenant-1", agent_id="agent-1", call_id="call-order")
    turn_state: dict = {}
    messages = await orchestrator._execute_composed_tools(
        ctx=ctx,
        messages=[{"role": "user", "content": "I want 500 visiting cards"}],
        tool_calls=[
            {
                "id": "c1",
                "function": {
                    "name": "CONFIRM_ORDER",
                    "arguments": json.dumps(
                        {
                            "quantity": 500,
                            "customer_name": "Ravi",
                            "delivery_address": "12 MG Road, Hyderabad",
                        }
                    ),
                },
            }
        ],
        allowed_tools={"CONFIRM_ORDER"},
        turn_state=turn_state,
    )
    assert turn_state["order_proof"] is True
    tool_result = json.loads(messages[-1]["content"])
    assert tool_result["status"] == "ok"
    assert order_details_present(read_order_proof("call-order"))
    gateway.assert_not_awaited()
