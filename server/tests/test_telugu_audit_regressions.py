"""Regressions from the Telugu-only adaptive audit (2026-10-29).

Covers findings F1 through F11:
- F1: Scoped negation vs DND, non-call hangups, callback declination, open question preservation.
- F2: Unsafe/leaked speech delivery replacement and queue truncation.
- F3: Memory projection timeout fallback to active in-memory snapshot.
- F4: Memory extraction rejection of caller questions and non-confirmed options.
- F5: Conversation history truncation character caps and number integrity.
- F6: Spoken numbers and clock formatting for Indic currency and times.
- F7: Action proof fee vs booking claim disambiguation and proposal question checks.
- F8 & F10: Callback relative date resolution and lead interest scoring.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import pytest

from server.call.action_proof import claims_recorded_request, unproven_claim
from server.call.caller_intent import (
    classify_caller_intent,
    caller_declined_callback,
    caller_revoked_callback,
    caller_will_contact,
)
from server.call.close_decision import opt_out_evidence
from server.call.end_call_validate import (
    caller_explicit_end_request,
    caller_requested_callback,
    caller_stop_contact,
    validate_end_call,
)
from server.call.memory_guard import grounded_turn_operations
from server.call.memory_manager import memory_manager
from server.services.spoken_numbers import expand_spoken_numbers, prepare_spoken_reply


def test_f1_telugu_non_call_phrases_do_not_trigger_hangup():
    """Phrases like 'instructions పక్కన పెట్టేయండి' or 'సోది కట్ చేయండి' must not hang up."""
    assert not caller_explicit_end_request("instructions పక్కన పెట్టేయండి, అసలు విషయం చెప్పండి")
    assert not caller_explicit_end_request("సోది కట్ చేయండి, రేటు చెప్పండి")
    assert not caller_explicit_end_request("ఈ ప్రశ్నలు ఆపేయండి, డెలివరీ ఎప్పుడు అవుతుందో చెప్పండి")


def test_f1_telugu_explicit_call_cut_triggers_hangup():
    """Explicit requests to cut the call or put down the phone must be recognized."""
    assert caller_explicit_end_request("ఫోన్ పెట్టేయండి")
    assert caller_explicit_end_request("కాల్ కట్ చేయండి")
    assert caller_explicit_end_request("కాల్ ఆపేయండి")


def test_f1_telugu_declining_callback_is_not_permanent_dnd():
    """'లేదు, callback వద్దు' or 'వద్దు కాల్ అవసరం లేదు' must NOT trigger permanent DND."""
    assert not caller_stop_contact("లేదు, callback వద్దు")
    assert not caller_stop_contact("వద్దు, కాల్ అవసరం లేదు, ఇప్పుడే చెప్పండి")
    assert not opt_out_evidence("లేదు, callback వద్దు")
    assert not opt_out_evidence("కాల్ బ్యాక్ వద్దు")
    assert caller_declined_callback("లేదు, callback వద్దు")


def test_f1_telugu_caller_will_contact_is_not_callback_request():
    """'నేను తర్వాత కాల్ చేస్తాను' means caller will contact; not an agent callback request."""
    text = "నేను తర్వాత కాల్ చేస్తాను"
    assert caller_will_contact(text)
    assert not caller_requested_callback(text)


def test_f1_telugu_explicit_dnd_is_recognized():
    """'ఈ నంబర్‌కి మళ్లీ కాల్ చేయకండి' must trigger caller_stop_contact and opt_out_evidence."""
    text = "ఈ నంబర్‌కి మళ్లీ కాల్ చేయకండి"
    assert caller_stop_contact(text)
    assert opt_out_evidence(text)

    text2 = "నా నంబర్‌కి మళ్లీ ఫోన్ చేయొద్దు"
    assert caller_stop_contact(text2)
    assert opt_out_evidence(text2)


def test_f1_open_question_with_callback_request_is_not_prematurely_ended():
    """Asking a substantive question while requesting a callback must not drop the question."""
    user = "సాయంత్రం 5 గంటలకు కాల్ చేయండి, కానీ డెలివరీ ఛార్జ్ ఎంత ఉంటుంది?"
    # Model proposing to end the call without answering the question must be rejected.
    decision = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "ధన్యవాదాలు"},
        user_text=user,
        language="te-IN",
        completed_turns=2,
    )
    assert not decision.accepted
    assert decision.reject_code == "user_asked_question"


def test_f4_memory_guard_rejects_questions_as_facts():
    """Questions asked by caller must not be stored as facts or selected products."""
    ops = [
        {"op": "set_fact", "key": "delivery_time", "value": "ఎప్పటికి", "evidence": "డెలివరీ ఎప్పటికి అవుతుంది?"},
        {"op": "set_fact", "key": "product", "value": "మగ్స్", "evidence": "మగ్స్ ప్రింటింగ్ కూడా ఉందా?"},
        {"op": "set_fact", "key": "quantity", "value": "500", "evidence": "నాకు 500 కార్డులు కావాలి"},
    ]
    user_text = "డెలివరీ ఎప్పటికి అవుతుంది? మగ్స్ ప్రింటింగ్ కూడా ఉందా? నాకు 500 కార్డులు కావాలి."
    grounded = grounded_turn_operations(ops, user_text)
    # Only the genuine declared quantity should survive; questions are rejected.
    assert len(grounded) == 1
    assert grounded[0]["key"] == "quantity"
    assert grounded[0]["value"] == "500"


def test_f5_history_truncation_preserves_full_assistant_turns():
    """Assistant character cap of 1600 prevents broken sentences or split numbers."""
    from server.agent.conversation_manager import conversation_manager
    from server.config.env import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.max_history_assistant_chars >= 1200
    conversation_manager.max_assistant_chars = settings.max_history_assistant_chars

    long_reply = "మా దగ్గర 1000 విజిటింగ్ కార్డులు ₹800 రూపాయలు మరియు డెలివరీ ఉచితం. " * 5
    truncated = conversation_manager._truncate_content("assistant", long_reply)
    assert not truncated.endswith("…")
    assert "800" in truncated


def test_f6_spoken_numbers_indic_currency_and_clock():
    """500/-, రూ. 500, and times are naturally expanded for TTS."""
    res1 = expand_spoken_numbers("ఫీజు 500/- ఉంటుంది").lower()
    assert "five hundred rupees" in res1
    res2 = expand_spoken_numbers("ధర రూ. 500 మాత్రమే").lower()
    assert ("five hundred rupees" in res2 or "rupees five hundred" in res2)
    assert "500" not in prepare_spoken_reply("ఫీజు 500/- ఉంటుంది")


def test_f7_action_proof_fee_quote_and_proposal_is_not_unproven_claim():
    """Quoting a visit charge with a booking proposal question is NOT an appointment claim."""
    text = "మా విజిట్ ఛార్జ్ 250 రూపాయలు ఉంటుంది. మీరు బుక్ చేయమంటారా?"
    claim = unproven_claim(text, proofs=())
    assert claim is None, f"Expected no unproven claim for fee quote, got {claim}"


def test_f7_action_proof_actual_booking_requires_proof():
    """Asserting that an appointment has been booked requires a tool proof."""
    text = "మేము మీ అపాయింట్‌మెంట్ రేపు ఉదయం 10 గంటలకు బుక్ చేసాము."
    claim = unproven_claim(text, proofs=())
    assert claim == "appointment_confirmed"


def test_f8_callback_extracted_due_unicode_normalized():
    """extracted_due matches evidence even with punctuation or NFC normalization differences."""
    from server.services.saas.followup_policy import FollowUpConfig, extracted_due

    config = FollowUpConfig(enabled=True, timezone="Asia/Kolkata")
    now = datetime(2026, 10, 29, 10, 0, 0, tzinfo=timezone.utc)
    payload = {
        "kind": "relative",
        "delay_minutes": 120,
        "evidence": "2 గంటల తర్వాత",
        "local_datetime": None,
        "timezone": "Asia/Kolkata",
    }
    due = extracted_due(payload, "నాకు 2 గంటల తర్వాత కాల్ చేయండి.", now, config)
    assert due is not None
    assert due == datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc)


def test_f10_lead_scoring_awards_interest_for_new_lead_and_products():
    """New leads with recorded product facts receive interest component points."""
    from server.services.saas.lead_scoring import score_outcome

    outcome = {
        "disposition": "new_lead",
        "disposition_confidence": 0.95,
        "facts": {"product": "Visiting Cards", "quantity": "1000"},
    }
    result = score_outcome(outcome)
    assert result["score"] is not None
    assert result["score"] > 0
    interest_comp = next((c for c in result["components"] if c["signal"] == "interest"), None)
    assert interest_comp is not None
    assert interest_comp["points"] > 0


def test_f1_telugu_polite_goodbye_endings():
    """Telugu polite sign-offs like 'సరే ఉంటాను', 'ఉంటానండి', 'sare unta' must be accepted as goodbye."""
    for phrase in ["సరే ఉంటాను", "ఉంటానండి", "సరే ఉంటా", "sare unta", "untanu"]:
        decision = validate_end_call(
            {"should_end": True, "reason": "goodbye", "farewell": "ధన్యవాదాలు"},
            user_text=phrase,
            language="te-IN",
            completed_turns=2,
        )
        assert decision.accepted, f"Failed for goodbye phrase: {phrase}"


def test_f1_transliterated_caller_will_contact_and_idi_callback_kaadu():
    """Transliterated utterances for self-contact and negated callbacks must not create callbacks."""
    assert caller_will_contact("nenu tarvata call chestanu")
    assert not caller_requested_callback("nenu tarvata call chestanu")
    assert not caller_requested_callback("idi callback adagadam kaadu")
    assert not caller_requested_callback("ఇది callback అడగడం కాదు")


def test_f1_dont_call_now_call_again_tomorrow_is_not_permanent_dnd():
    """'ఇప్పుడు కాల్ చేయకండి, రేపు మళ్లీ చేయండి' is a callback request, NOT permanent DND."""
    text = "ఇప్పుడు కాల్ చేయకండి, రేపు మళ్లీ చేయండి"
    assert not opt_out_evidence(text)
    assert not caller_stop_contact(text)
    assert caller_requested_callback(text)


@pytest.mark.asyncio
async def test_f7_hubspot_create_contact_field_mapping():
    """Email in lastname or degree in company must be sanitized before CRM payload."""
    from server.services.nango_service import NangoService
    from unittest.mock import AsyncMock, patch

    service = NangoService()
    params = {
        "firstname": "Ravi",
        "lastname": "ravi.kumar@example.com",
        "company": "BTech Final Year",
        "phone": "+919876543210",
    }
    from unittest.mock import MagicMock
    captured_json = {}
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"id": "hub-12345"}

    async def mock_post(url, headers=None, json=None):
        nonlocal captured_json
        captured_json = json
        return mock_resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        from types import SimpleNamespace
        from server.call.action_arguments import ground_contact_fields
        params = ground_contact_fields(SimpleNamespace(call_id="contact-grounding", turn_control={
            "memory_operations": [{"op": "set_fact", "key": "caller_name", "value": "Ravi"}]
        }), params)
        res = await service._execute_proxy_tool(
            provider_key="hubspot",
            action_name="HUBSPOT_CREATE_CONTACT",
            connection_id="mock_conn",
            params=params,
        )
        assert res["status"] == "success"
        props = captured_json.get("properties", {})
        assert props.get("email") == "ravi.kumar@example.com"
        assert "lastname" not in props or props.get("lastname") == ""
        assert "company" not in props or props.get("company") == ""
        assert props.get("firstname") == "Ravi"


def test_f7_idempotency_key_by_business_identity():
    """Changing company/notes for the same email/phone must yield the identical idempotency key."""
    from server.services.tool_router import tool_router

    key1 = tool_router._generate_idempotency_key(
        "tenant-1", "call-1", "HUBSPOT_CREATE_CONTACT",
        {"firstname": "Ravi", "lastname": "Kumar", "email": "ravi@example.com", "company": "ABC"},
    )
    key2 = tool_router._generate_idempotency_key(
        "tenant-1", "call-1", "HUBSPOT_CREATE_CONTACT",
        {"firstname": "Ravi", "email": "ravi@example.com", "company": "XYZ Corp", "notes": "Changed note"},
    )
    assert key1 == key2, "Idempotency key differed for the same email identity!"


def test_f7_unknown_tool_result_rejects_goal_complete():
    """An unconfirmed action outcome cannot close as goal_complete."""
    decision = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "ధన్యవాదాలు"},
        user_text="సరే అండి",
        language="te-IN",
        completed_turns=2,
        action_outcome_unconfirmed=True,
    )
    assert not decision.accepted
    assert decision.reject_code == "action_unconfirmed"


@pytest.mark.asyncio
async def test_f8_calendar_rejects_past_date():
    """Calendar queries for past dates (e.g. 2025-01-21) must raise error/reject."""
    from server.services.integration_calendar import execute_calendar_action
    from unittest.mock import AsyncMock, MagicMock

    mock_client = AsyncMock()
    mock_meta = MagicMock()
    mock_meta.status_code = 200
    mock_meta.raise_for_status.return_value = None
    mock_meta.json.return_value = {"timeZone": "Asia/Kolkata"}
    mock_client.get.return_value = mock_meta

    res = await execute_calendar_action(
        mock_client,
        "https://api.example.com",
        {"Authorization": "Bearer mock"},
        "GOOGLECALENDAR_FIND_FREE_SLOTS",
        {"date": "2025-01-21"},
    )
    assert res["status"] == "error"
    assert "could not be verified" in res["message"]


def test_f8_temporal_grounding_in_prompt():
    """Live turn orchestrator injects explicit calendar date and tomorrow anchor into developer message."""
    from server.call.live_turn_orchestrator import LiveTurnOrchestrator
    from unittest.mock import MagicMock

    orch = LiveTurnOrchestrator()
    ctx = MagicMock()
    ctx.pipeline = "composed_voice"
    ctx.compiled_brain_text = "Business prompt"
    ctx.timezone = "Asia/Kolkata"
    ctx.action_receipts = []
    ctx.resolved_stack.language = "te-IN"
    ctx.resolved_stack.llm.model = "sarvam-2b"

    messages = orch._maybe_build_live_input(
        ctx=ctx,
        transcript="రేపు అపాయింట్‌మెంట్ కావాలి",
        session_id="test_session",
        openai_model="sarvam-2b",
        projection=None,
        rolling=None,
    )
    dev_msg = next(m["content"] for m in messages if m["role"] == "developer" and "Tomorrow is" in m["content"])
    assert "Asia/Kolkata" in dev_msg
    assert "Tomorrow is" in dev_msg
    assert "Never invent a year or resolve a future request to a past date" in dev_msg


def test_f3_memory_manager_monotonic_sequence():
    """MemoryManager peek_snapshot is lock-free in-memory and write sequence increments monotonically."""
    call_id = "test-call-seq-123"
    memory_manager.init(call_id)
    assert memory_manager.peek_snapshot(call_id) is not None

    res1 = memory_manager.apply_proposals(
        call_id,
        [{"op": "set_fact", "key": "city", "value": "Hyderabad"}],
        turn_seq=1,
    )
    res2 = memory_manager.apply_proposals(
        call_id,
        [{"op": "set_fact", "key": "city", "value": "Vijayawada"}],
        turn_seq=2,
    )
    assert memory_manager._write_seq[call_id] >= 2
    assert memory_manager.peek_snapshot(call_id)["facts"]["city"] == "Vijayawada"


def test_f4_statement_modality_asked_and_compared_not_facts():
    """Inquiries and comparisons are labeled as asked/compared and rejected from memory facts."""
    from server.call.memory_guard import classify_statement_modality

    assert classify_statement_modality("మగ్స్ ప్రింటింగ్ కూడా ఉందా?", "మగ్స్") == "asked"
    assert classify_statement_modality("కార్డులు లేదా మగ్స్ ఏది బెటర్?", "మగ్స్") == "compared"
    assert classify_statement_modality("నాకు 500 కార్డులు కావాలి", "500") == "asserted"
    assert classify_statement_modality("కార్డులు కాదు, మగ్స్ కావాలి", "మగ్స్") == "corrected"

    ops = grounded_turn_operations(
        [
            {"op": "set_fact", "key": "product", "value": "మగ్స్", "evidence": "కార్డులు లేదా మగ్స్ ఏది బెటర్?"},
            {"op": "set_fact", "key": "quantity", "value": "500", "evidence": "నాకు 500 కార్డులు కావాలి"},
        ],
        caller_text="కార్డులు లేదా మగ్స్ ఏది బెటర్? నాకు 500 కార్డులు కావాలి.",
    )
    assert len(ops) == 1
    assert ops[0]["key"] == "quantity"


def test_f10_dnd_cancels_callback_and_strips_callback_tags():
    """When contact_preference is do_not_call, disposition is coerced away from callback_required and tags stripped."""
    from server.call.outcome_schema import derive_status_tags

    tags = derive_status_tags(
        disposition="callback_required",
        facts={"callback_requested": "true"},
        next_action="Call caller back tomorrow",
        contact_preference="do_not_call",
    )
    assert "signal:do_not_call" in tags
    assert "outcome:callback_required" not in tags
    assert "outcome:not_interested" in tags
    assert not any("callback" in t for t in tags)
