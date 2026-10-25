"""Terminal speech never reaches TTS before the server approves the close."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from server.call.close_decision import parse_close_proposal
from server.call.end_call_validate import parse_end_call_payload
from server.call.live_turn_orchestrator import live_turn_orchestrator
from server.call.live_turn_schema import LIVE_TURN_JSON_SCHEMA, SpokenResponseExtractor
from server.config.env import get_settings

CLOSE_END_CALL = {
    "decision": "close",
    "reason": "firm_refusal",
    "evidence": "నాకు ఇవేమీ అక్కర్లేదండి",
    "remaining_request": "",
    "contact_preference": "end_call",
}

TE_SERVER_FAREWELL = "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం."


def test_schema_proves_the_close_before_it_decides_or_speaks():
    assert list(LIVE_TURN_JSON_SCHEMA["properties"])[0] == "end_call"
    end_call = LIVE_TURN_JSON_SCHEMA["properties"]["end_call"]
    order = list(end_call["properties"])
    assert order.index("evidence") < order.index("reason") < order.index("decision")
    # The order claim is readable before speech too, so an unproven
    # confirmation can be held until the server has proof.
    assert list(LIVE_TURN_JSON_SCHEMA["properties"])[:3] == [
        "end_call",
        "order_claimed",
        "spoken_response",
    ]
    assert "order_claimed" in LIVE_TURN_JSON_SCHEMA["required"]
    assert "should_end" not in end_call["properties"]
    # The server owns the farewell: the model cannot supply one.
    assert "farewell" not in end_call["properties"]
    assert end_call["required"] == order


def test_compact_memory_envelope_fits_the_reply_budget():
    ops = LIVE_TURN_JSON_SCHEMA["properties"]["memory_update"]["properties"]["operations"]
    assert ops["maxItems"] == 3
    assert ops["items"]["properties"]["value"]["maxLength"] == 150


def test_preview_reads_the_decision_before_any_spoken_text():
    extractor = SpokenResponseExtractor()
    assert extractor.preview_decision() is None
    extractor.feed(
        '{"end_call": {"evidence": "నాకు ఇవేమీ అక్కర్లేదు", "reason": "firm_refusal", '
        '"decision": "close"'
    )
    assert extractor.preview_decision() == "close"

    other = SpokenResponseExtractor()
    other.feed(
        '{"end_call": {"evidence": "", "reason": "none", "decision": "continue",'
    )
    assert other.preview_decision() == "continue"


def test_preview_ignores_a_decision_shaped_fragment_in_the_evidence():
    extractor = SpokenResponseExtractor()
    extractor.feed(
        '{"end_call": {"evidence": "he said \\"decision\\": \\"close\\"", '
        '"reason": "none", '
    )
    assert extractor.preview_decision() is None


def test_preview_is_unknown_when_the_model_ignores_schema_order():
    extractor = SpokenResponseExtractor()
    extractor.feed('{"spoken_response": "Goodbye.", "end_call": {"decision": "close"}}')
    assert extractor.preview_decision() is None


def test_compact_end_call_derives_should_end_from_decision():
    proposal = parse_close_proposal(CLOSE_END_CALL)
    assert proposal.should_end is True
    assert proposal.conflict is False
    parsed = parse_end_call_payload(CLOSE_END_CALL)
    assert parsed["should_end"] is True
    assert parsed["contact_preference"] == "end_call"


def test_legacy_should_end_payload_still_parses():
    parsed = parse_end_call_payload(
        {"should_end": True, "reason": "goodbye", "farewell": "Goodbye."}
    )
    assert parsed["should_end"] is True
    assert parsed["decision"] == "close"
    assert parsed["conflict"] is False


def test_conflicting_decision_and_should_end_are_still_rejected():
    parsed = parse_end_call_payload(
        {**CLOSE_END_CALL, "decision": "continue", "should_end": True}
    )
    assert parsed["conflict"] is True


@pytest.fixture(autouse=True)
def _no_archive(monkeypatch):
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _run_turn(
    chunks,
    *,
    transcript: str = "నాకు ఇవేమీ అక్కర్లేదండి",
    language_code: str = "te-IN",
    gate: dict,
):
    async def fake_stream(**_kwargs):
        for chunk in chunks:
            yield chunk

    async def no_memory(_call_id, **_kwargs):
        return None, None

    with (
        patch.object(live_turn_orchestrator, "_stream_llm", fake_stream),
        patch.object(live_turn_orchestrator, "_memory_blocks", no_memory),
        patch.object(live_turn_orchestrator, "_gate_end_call", lambda *a, **k: gate),
    ):
        return [
            chunk
            async for chunk in live_turn_orchestrator.handle_user_turn_stream(
                transcript=transcript,
                language_code=language_code,
                session_id="close-gate",
                call_id="close-gate",
            )
        ]


def _deltas(chunks) -> str:
    return "".join(str(chunk.get("delta") or "") for chunk in chunks)


def _done(chunks) -> dict:
    return next(chunk for chunk in chunks if chunk.get("done"))


@pytest.mark.asyncio
async def test_approved_close_speaks_the_server_farewell_not_the_model_text():
    model_text = "ధన్యవాదాలు. వీడ్కోలు."
    chunks = await _run_turn(
        [
            {"delta": model_text, "close_preview": "close"},
            {"done": True, "text": model_text, "end_call": CLOSE_END_CALL},
        ],
        gate={
            "should_end": True,
            "reason": "firm_refusal",
            "farewell": TE_SERVER_FAREWELL,
            "contact_preference": "end_call",
        },
    )
    assert _deltas(chunks) == ""
    done = _done(chunks)
    assert done["text"] == TE_SERVER_FAREWELL
    assert model_text not in done["text"]
    assert done["replace_speech"] is True


@pytest.mark.asyncio
async def test_rejected_close_replaces_the_farewell_with_a_continuation_line():
    chunks = await _run_turn(
        [
            {"delta": "Goodbye. Thank you.", "close_preview": "close"},
            {
                "done": True,
                "text": "Goodbye. Thank you.",
                "end_call": {**CLOSE_END_CALL, "evidence": "tell me more"},
            },
        ],
        transcript="I never said I am not interested, please tell me more.",
        language_code="en-IN",
        gate={
            "should_end": False,
            "reason": "none",
            "farewell": "",
            "contact_preference": "none",
            "reject_code": "remaining_request",
        },
    )
    assert _deltas(chunks) == ""
    assert "Goodbye" not in _done(chunks)["text"]
    assert _done(chunks)["text"] == "Of course — please go ahead."
    assert _done(chunks)["replace_speech"] is True


@pytest.mark.asyncio
async def test_rejected_close_never_speaks_model_text_even_without_a_terminal_phrase():
    model_text = "The fee is eight thousand rupees."
    chunks = await _run_turn(
        [
            {"delta": model_text, "close_preview": "close"},
            {
                "done": True,
                "text": model_text,
                "end_call": CLOSE_END_CALL,
            },
        ],
        transcript="How much is the fee?",
        language_code="en-IN",
        gate={"should_end": False, "reason": "none", "farewell": "", "contact_preference": "none"},
    )
    assert _deltas(chunks) == ""
    assert _done(chunks)["text"] == "Of course — please go ahead."
    assert model_text not in _done(chunks)["text"]


@pytest.mark.asyncio
async def test_open_preview_keeps_streaming_the_reply():
    chunks = await _run_turn(
        [
            {"delta": "The fee is eight thousand rupees. ", "close_preview": "continue"},
            {"delta": "We are open daily.", "close_preview": "continue"},
            {
                "done": True,
                "text": "The fee is eight thousand rupees. We are open daily.",
                "end_call": {**CLOSE_END_CALL, "decision": "continue", "reason": "none"},
            },
        ],
        transcript="How much is the fee?",
        language_code="en-IN",
        gate={"should_end": False, "reason": "none", "farewell": "", "contact_preference": "none"},
    )
    streamed = "".join(
        str(chunk.get("delta") or "") for chunk in chunks if not chunk.get("done")
    )
    assert "eight thousand" in streamed


@pytest.mark.asyncio
async def test_unreadable_preview_buffers_until_the_gate_answers():
    chunks = await _run_turn(
        [
            {"delta": "Goodbye. Thank you."},
            {
                "done": True,
                "text": "Goodbye. Thank you.",
                "end_call": {**CLOSE_END_CALL, "decision": "continue", "reason": "none"},
            },
        ],
        transcript="okay thanks",
        language_code="en-IN",
        gate={"should_end": False, "reason": "none", "farewell": "", "contact_preference": "none"},
    )
    statuses = [chunk.get("status") for chunk in chunks if chunk.get("status")]
    assert "reply_buffered" in statuses
    assert _deltas(chunks) == ""
    assert "Goodbye" not in _done(chunks)["text"]


@pytest.mark.asyncio
async def test_real_7ac554ab_rejected_closes_never_heard_the_model_goodbye():
    # Turn 1 of call 7ac554ab: the model answered the price question and ended
    # its own reply with "ధన్యవాదాలు. నమస్కారం."; the gate correctly rejected the
    # close, yet the farewell was still spoken. Every turn in that call hit this.
    caller = "ఉందండి, చెప్పండి మీరు ఏమేమి చేస్తారు? విష్టు లాఫ్ట్స్ ఎంతకి ఇస్తున్నారు?"
    model_text = (
        "విజిటింగ్ కార్డ్స్ ఒక్కోటి twenty five rupees అండి. ఇవి post ద్వారా delivery "
        "అవుతాయి. ప్రస్తుతానికి మీకు interest లేదనుకుంటా, సరేనండి. మీ సమయం ఇచ్చినందుకు "
        "ధన్యవాదాలు. నమస్కారం."
    )
    chunks = await _run_turn(
        [
            {"delta": model_text, "close_preview": "close"},
            {
                "done": True,
                "text": model_text,
                "end_call": {
                    "decision": "close",
                    "reason": "firm_refusal",
                    "evidence": "interest లేదు",
                    "remaining_request": "",
                    "contact_preference": "end_call",
                },
            },
        ],
        transcript=caller,
        language_code="te-IN",
        gate={
            "should_end": False,
            "reason": "none",
            "farewell": "",
            "contact_preference": "none",
            "reject_code": "no_evidence",
        },
    )
    done = _done(chunks)
    assert _deltas(chunks) == ""
    assert done["text"] == "తప్పకుండా, చెప్పండి."
    assert "నమస్కారం" not in done["text"]
    assert "ధన్యవాదాలు" not in done["text"]


def test_server_farewell_uses_tenant_policy_then_language_pack():
    from server.call.call_end_policy import server_farewell_for

    assert server_farewell_for("te-IN") == TE_SERVER_FAREWELL
    assert (
        server_farewell_for("te-IN", policy={"farewell": "మళ్లీ కలుద్దాం."})
        == "మళ్లీ కలుద్దాం."
    )
    callback = server_farewell_for("en-IN", contact_preference="callback")
    assert "callback request is noted" in callback.lower()


def test_order_claim_preview_is_read_before_spoken_text():
    extractor = SpokenResponseExtractor()
    extractor.feed(
        '{"end_call": {"evidence": "", "reason": "none", "decision": "continue", '
        '"remaining_request": "", "contact_preference": "none"}, "order_claimed": true, '
        '"spoken_response": "Your order is confirmed.'
    )
    assert extractor.preview_order_claim() is True
    quiet = SpokenResponseExtractor()
    quiet.feed('{"end_call": {"evidence": "", "reason": "none", "decision": "continue"')
    assert quiet.preview_order_claim() is None


@pytest.mark.asyncio
async def test_unproven_order_claim_is_held_and_replaced(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    model_text = "Your order is confirmed. We will deliver tomorrow."
    chunks = await _run_turn(
        [
            {"delta": model_text, "close_preview": "continue", "order_preview": True},
            {
                "done": True,
                "text": model_text,
                "end_call": {
                    "decision": "continue",
                    "reason": "none",
                    "evidence": "",
                    "remaining_request": "",
                    "contact_preference": "none",
                },
            },
        ],
        transcript="I want 500 visiting cards",
        language_code="en-IN",
        gate={"should_end": False, "reason": "none", "farewell": "", "contact_preference": "none"},
    )
    done = _done(chunks)
    assert _deltas(chunks) == ""
    assert done["text"] == "Let me verify those details before I confirm anything."
    assert done["replace_speech"] is True
    assert "confirmed" not in done["text"].lower()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_confirmation_streams_only_after_the_server_recorded_the_order(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    from server.call.order_confirmation import record_order_confirmation

    assert record_order_confirmation(
        call_id="close-gate",
        tenant_id="tenant",
        agent_id="agent",
        arguments={
            "quantity": 500,
            "customer_name": "Ravi",
            "delivery_address": "12 MG Road, Hyderabad",
        },
    )["status"] == "ok"
    model_text = "Your order is confirmed. We will deliver tomorrow."
    chunks = await _run_turn(
        [
            {"delta": model_text, "close_preview": "continue", "order_preview": True},
            {
                "done": True,
                "text": model_text,
                "end_call": {
                    "decision": "continue",
                    "reason": "none",
                    "evidence": "",
                    "remaining_request": "",
                    "contact_preference": "none",
                },
            },
        ],
        transcript="I want 500 visiting cards",
        language_code="en-IN",
        gate={"should_end": False, "reason": "none", "farewell": "", "contact_preference": "none"},
    )
    assert _deltas(chunks) == model_text
    assert _done(chunks)["text"] == model_text
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_text_only_order_claim_without_the_flag_is_still_replaced(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    model_text = "Your order is confirmed."
    chunks = await _run_turn(
        [
            {"delta": model_text, "close_preview": "continue"},
            {
                "done": True,
                "text": model_text,
                "end_call": {
                    "decision": "continue",
                    "reason": "none",
                    "evidence": "",
                    "remaining_request": "",
                    "contact_preference": "none",
                },
            },
        ],
        transcript="I want 500 visiting cards",
        language_code="en-IN",
        gate={"should_end": False, "reason": "none", "farewell": "", "contact_preference": "none"},
    )
    assert _done(chunks)["text"] == "Let me verify those details before I confirm anything."
    assert _done(chunks)["replace_speech"] is True
    get_settings.cache_clear()
