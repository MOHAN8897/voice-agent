"""Regression for call 35002575 (te-IN, composed stack): the guard decisions on its real turns.

The caller turns and agent replies below are the call's transcript.jsonl, in order.
Each agent reply is replayed through the live reply guards with the caller's words
since the agent's previous reply, exactly as the orchestrator joins them.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from server.call.reply_guard import (
    audio_issue_evidence,
    caller_turn_since_agent,
    guard_reply,
    known_slots,
    asked_slots,
    recent_agent_replies,
)

BRAIN = """--- SPOKEN LANGUAGE (te-IN) ---
Slow-down (once): `కొంచెం నెమ్మదిగా చెప్తారా?`
Unclear audio (garbled STT, not a language change): `చివరి మాట వినిపించలేదు. మళ్లీ చెప్తారా?` then wait for clarification.
Style anchors, not extra facts: ‘ఆ విషయం నాకు తెలియదు.’ for a missing fact; ‘మీకు ఏ details కావాలి?’ only when their request is unclear.
--- CALLING SCRIPT ---
--- AGENT IDENTITY ---
You are Meera, representing subhasri sells.
Role: sales. Objective: Sell digital products at best prices, negotiate with callers to buy products, and note down the details of interested buyers
--- COMPANY & OFFER ---
Digital products include icards and visiting cards
Price is 25 rs per visiting card
Accepted payment methods include cards and cod available
Digital icards and visiting cards are delivered through the post
--- CALL TO ACTION ---
Note down the details of interested buyers including their name, delivery address, and quantity required.
--- UNKNOWN INFORMATION ---
If asked about any detail not provided in the facts, state that the information is currently unavailable. Do not invent callbacks, additional pricing, discounts, policies, links, or capabilities.
--- GUARDRAILS ---
- Never invent prices, availability, or policies.
"""

# (seq, role, text) from data/calls/35002575-.../transcript.jsonl
TURNS = [
    (4, "user", "మీ పేరు చెప్పండి ఒకసారి."),
    (5, "user", "మీ పేరు చెప్పండి ఒకసారి. ఓకే, మీరు ఎంత?"),
    (6, "user", "మీ పేరు చెప్పండి ఒకసారి. ఓకే, మీరు ఎంత? ఓకే, మీరు ఎంతమంది ఎంప్లాయిస్ అండి?"),
    (7, "user", "ఓకే, మీరు ఎంతమంది ఎంప్లాయిస్ అండి?"),
    (8, "assistant", "ఆ విషయం నాకు తెలియదు. ప్రస్తుతానికి ఆ information అందుబాటులో లేదు."),
    (9, "user", "మీకు పెద్ద కంపెనీయా లేదంటే నార్మల్ గా రోడ్ సైడ్ బిజినెస్ ఆ?"),
    (10, "assistant", "మేము చిన్న business, రోడ్ సైడ్ బిజినెస్. మా digital products, అంటే icards మరియు visiting cards గురించి చెప్తాను. మీకు interest ఉందా చెప్తారా?"),
    (11, "user", "ఓకే ఓకే."),
    (12, "assistant", "కొంచెం నెమ్మదిగా చెప్తారా? సరే. మా visiting cards ఒక్కొక్కటి ₹25 ఉంటాయి, ఇవి post ద్వారా delivery అవుతాయి. మీకు order ఏమైనా కావాలా?"),
    (13, "user", "ఓకే ఓకే ఓకే"),
    (14, "user", "ఓకే ఓకే, మీరు ఇప్పుడు మీ దగ్గర ఉండే ప్రోడక్ట్స్ ఏంటి? వాటి వాల్యూస్ ఏంటి?"),
    (15, "assistant", "మా దగ్గర icards మరియు visiting cards ఉన్నాయి. Visiting cards ఒక్కొక్కటి ₹25 ఉంటాయి. మీకు వీటిలో ఏవి కావాలో చెప్పండి.?"),
    (16, "user", "ఓకే నాకు నేను కొంచెం బల్క్లో తీసుకుంటాను, నాకేమన్నా డిస్కౌంట్స్ ప్రొవైడ్ చేయగలుగుతారా మీరు?"),
    (17, "assistant", "ఆ విషయం నాకు తెలియదు. ప్రస్తుతానికి bulk discounts గురించి information అందుబాటులో లేదు. మీకు order కావాలంటే చెప్పండి."),
    (18, "user", "ఓకే ఓకే"),
    (19, "assistant", "ప్రస్తుతం bulk discounts గురించి information అందుబాటులో లేదు."),
    (24, "user", "సో ఒకసారి మీ మీ మేనేజర్ కానీ మీ ఓనర్ కానీ కానీ ఒకసారి కాంటాక్ట్ నా ఫోన్ కలపగలుగుతారా?"),
    (25, "assistant", "Manager లేదా owner తో మాట్లాడాలని మీరు అడిగారు. కానీ ప్రస్తుతం వారితో direct గా call connect చేయడం కుదరదు. మీకు ఏవైనా details కావాలంటే చెప్పండి, నేను note చేసుకుంటాను."),
    (26, "user", "అవును"),
    (27, "assistant", "సరే. మీకు ఎన్ని visiting cards కావాలో చెప్తారా?"),
    (28, "user", "ఓకే నాకు ఒక 100 విజిటింగ్ కార్స్ కావాలి."),
    (29, "user", "ఓకే నాకు ఒక 100 విజిటింగ్ కార్స్ కావాలి. ఇది చెప్పండి మీ"),
    (30, "user", "ఇది చెప్పండి, మీ మేనేజర్ కి చెప్పండి నా కాల్ బ్యాక్ చేయమని."),
    (31, "user", "ఇది చెప్పండి, మీ మేనేజర్ కి చెప్పండి నా కాల్ బ్యాక్ చేయమని. ఆ పేరు."),
    (32, "user", "నా పేరు Saikiran"),
    (33, "assistant", "సరే Saikiran గారు, ఒక్కో visiting card price ₹25 ఉంటుంది, ఇవి post ద్వారా delivery అవుతాయి. మీకు ఎన్ని కావాలో చెప్తారా.?"),
    (34, "user", "పర్లేదండి పర్లేదండి"),
    (35, "user", "పర్లేదండి పర్లేదండి ఓకే అండి పర్లేదు"),
    (36, "assistant", "పర్లేదండి. మీకు ఎన్ని cards కావాలో చెప్తారా?"),
    (37, "user", "ఓకే అండి పర్లేదు."),
    (38, "assistant", "మీకు ఎన్ని cards కావాలో చెప్పలేదు కదా. ఒకసారి quantity చెప్తారా, అప్పుడు నేను మీ details note చేసుకుంటాను."),
    (39, "user", "ఒక 500 కావాలి."),
    (40, "user", "ఒక 500 కావాలి. ఫైవ్ హండ్రెడ్"),
    (41, "assistant", "సరే, 500 visiting cards. ఒక్కో దానికి ₹25 అవుతుంది, ఇవి post ద్వారా delivery అవుతాయి. మీ పేరు Saikiran గారు కదా, ఇంకా మీ delivery address చెప్తారా, order confirm చేస్తాను."),
    (42, "user", "యా అండి ఓకే"),
    (43, "user", "యా అండి ఓకే అవును అవునండి అవు"),
    (44, "assistant", "సరే. మీ delivery address చెప్తారా, order confirm చేస్తాను."),
    (45, "user", "అవును అవునండి అవునండి."),
    (46, "assistant", "మీ delivery address చెప్పండి, order confirm చేస్తాను."),
    (47, "user", "యా ఓకే అండి థ్యాంక్ యూ"),
    (48, "assistant", "సరే, మీ order confirm చేయడానికి మీ delivery address చెప్పండి. Payment కోసం cards లేదా cash on delivery తీసుకోవచ్చు."),
    (49, "user", "ఆ ఇప్పుడు ప్రెసెంట్ నేను తర్వాత చెప్తా అండి, నాకు కొంచెం బిజీలో ఉన్నాను తర్వాత కాల్ చేయండి నాకు."),
    (50, "user", "హలో హలో"),
    (51, "assistant", "సరే, అర్థమైంది. మీరు తర్వాత free ఉన్నప్పుడు call చేయమని చెప్పండి, నేను note చేసుకుంటాను."),
    (52, "user", "హలో"),
    (53, "assistant", "మీకు ఏ time కి call చేయమంటారు?"),
    (54, "user", "రేపు ఈవెనింగ్ కాల్ చేయండి."),
    (55, "assistant", "సరే, రేపు ఈవెనింగ్ callback note చేసుకున్నాను. మా team దాన్ని confirm చేస్తారు."),
]


def _replay():
    """Replay every agent reply; returns {seq: (caller_turn, spoken, reasons)}."""
    history: list[dict] = []
    state: dict = {}
    facts: dict = {}
    pending: list[str] = []
    out = {}
    for seq, role, text in TURNS:
        if role == "user":
            pending.append(text)
            continue
        caller = caller_turn_since_agent(history + [{"role": "user", "content": p} for p in pending[:-1]], pending[-1])
        previous = recent_agent_replies(history, 1)
        quantity_asked = bool(previous and "quantity" in asked_slots(previous[-1]))
        spoken, reasons = guard_reply(
            text, caller=caller, language="te-IN", brain=BRAIN, history=history, state=state,
            audio_evidence=audio_issue_evidence(caller),
            known=known_slots(facts, caller, quantity_asked=quantity_asked),
        )
        out[seq] = (caller, spoken, reasons)
        from server.call.caller_detail_capture import caller_detail_memory_operations

        for op in caller_detail_memory_operations(caller, quantity_asked=quantity_asked):
            if op.get("key"):
                facts[op["key"]] = op["value"]
        history.extend({"role": "user", "content": p} for p in pending)
        history.append({"role": "assistant", "content": spoken})
        pending = []
    return out


@pytest.fixture(scope="module")
def replay():
    return _replay()


def test_issue_1_invented_roadside_business_becomes_the_unknown_line(replay):
    _, spoken, reasons = replay[10]
    assert reasons == ["business_claim:size_or_kind"]
    assert spoken.startswith("ఆ విషయం నాకు తెలియదు.")
    assert "రోడ్ సైడ్" not in spoken and "చిన్న business" not in spoken
    # The honest "don't know" at seq 8 is untouched.
    assert replay[8][2] == []


def test_issue_2_the_quantity_in_fragments_reaches_the_reply_and_memory(replay):
    caller, spoken, reasons = replay[33]
    assert "100" in caller and "Saikiran" in caller and caller.count("100") == 1
    # The caller already said 100: the third "how many?" is not asked.
    assert "known_slot:quantity" in reasons
    assert "ఎన్ని" not in spoken
    from server.call.caller_detail_capture import caller_detail_memory_operations

    assert {"op": "set_fact", "key": "quantity", "value": "100"} in caller_detail_memory_operations(caller)


def test_issue_4_ok_ok_never_earns_the_slow_down_line(replay):
    caller, spoken, reasons = replay[12]
    assert caller == "ఓకే ఓకే."
    assert reasons == ["canned_audio_line"]
    assert "నెమ్మదిగా" not in spoken
    assert "₹25" in spoken


def test_issue_5_the_bulk_discount_line_is_not_said_twice(replay):
    _, spoken, reasons = replay[19]
    assert reasons == ["near_repeat"]
    assert "discounts" not in spoken
    assert replay[17][2] == []


def test_issue_6_address_is_not_asked_three_times_on_bare_yeses(replay):
    assert replay[41][2] == []
    assert replay[44][2] == ["repeat_ask:address"] and replay[44][1] == "సరే, చెప్పండి."
    assert replay[46][2] == ["offer_later:address"]
    assert replay[46][1] == "పర్వాలేదు, అది తర్వాత కూడా చెప్పొచ్చు."
    assert "address" not in replay[48][1] and "Payment" in replay[48][1]


def test_issue_7_the_callers_filler_is_not_echoed(replay):
    _, spoken, reasons = replay[36]
    assert "filler_echo" in reasons
    assert not spoken.startswith("పర్లేదండి")


def test_ordinary_turns_pass_through_unchanged(replay):
    for seq in (8, 15, 17, 25, 27, 41, 53, 55):
        assert replay[seq][2] == [], (seq, replay[seq])
        assert replay[seq][1] == next(t for s, r, t in TURNS if s == seq)


def test_bulk_is_never_stored_as_the_quantity(tmp_path, monkeypatch):
    from server.call.memory_manager import memory_manager
    from server.config.env import get_settings

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    memory_manager.reset_for_tests()
    memory_manager.init("c35002575")
    try:
        # Turn 16's model write, verbatim from memory_events.jsonl.
        event = memory_manager.apply_proposals(
            "c35002575", [{"op": "set_fact", "key": "quantity", "value": "బల్క్"}], turn_seq=16)["event"]
        assert event["applied"] is False
        assert memory_manager.peek_snapshot("c35002575")["facts"] == {}
    finally:
        memory_manager.reset_for_tests()
        get_settings.cache_clear()


# --- the orchestrator wiring ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_replies_to_joined_fragments_and_speaks_the_guarded_text(monkeypatch, tmp_path):
    from server.agent.conversation_manager import conversation_manager
    from server.call import call_context
    from server.call.live_turn_orchestrator import live_turn_orchestrator
    from server.call.memory_manager import memory_manager
    from server.config.env import get_settings

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "false")
    get_settings.cache_clear()
    memory_manager.reset_for_tests()
    session = "s-35002575"
    conversation_manager.clear(session)
    conversation_manager.add_turn(session, "అవును", "సరే. మీకు ఎన్ని visiting cards కావాలో చెప్తారా?")
    for fragment in ("ఓకే నాకు ఒక 100 విజిటింగ్ కార్స్ కావాలి.",
                     "ఇది చెప్పండి, మీ మేనేజర్ కి చెప్పండి నా కాల్ బ్యాక్ చేయమని. ఆ పేరు."):
        conversation_manager.add_user_only(session, fragment)
    ctx = SimpleNamespace(call_id="c-join", session_id=session, compiled_brain_text=BRAIN, pipeline="test",
                          resolved_stack=SimpleNamespace(language="te-IN", llm=None, tts=None), status="ended")
    monkeypatch.setattr(call_context, "get", lambda call_id: ctx if call_id == "c-join" else None)
    seen = {}
    reply = "మేము చిన్న business. మీకు ఎన్ని కావాలో చెప్తారా?"

    async def fake_stream(*, ctx, **kwargs):
        seen["transcript"] = kwargs["transcript"]
        yield {"done": True, "text": reply, "end_call": {"should_end": False, "reason": "none", "farewell": ""}}

    # Patch the instance: the routing and provider stack are not under test here.
    monkeypatch.setattr(live_turn_orchestrator, "_stream_llm", fake_stream)
    monkeypatch.setattr(live_turn_orchestrator, "_maybe_callback_close_hint", lambda *a, **k: None)
    chunks = [c async for c in live_turn_orchestrator.handle_user_turn_stream(
        transcript="నా పేరు Saikiran", language_code="te-IN", session_id=session, call_id="c-join")]
    done = next(c for c in chunks if c.get("done"))
    assert "100" in seen["transcript"] and seen["transcript"].endswith("నా పేరు Saikiran")
    assert done["replace_speech"] is True
    assert done["text"] == "ఆ విషయం నాకు తెలియదు."
    history = conversation_manager.get_history(session)
    # History keeps the raw final; the earlier fragments are already there once.
    assert [m["content"] for m in history if m["role"] == "user"][-1] == "నా పేరు Saikiran"
    conversation_manager.clear(session)
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_native_control_turn_still_captures_the_stated_quantity_and_name(monkeypatch, tmp_path):
    from server.call import call_context
    from server.call.live_turn_orchestrator import live_turn_orchestrator
    from server.call.memory_manager import memory_manager
    from server.config.env import get_settings

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_WORKING_MEMORY", "true")
    get_settings.cache_clear()
    memory_manager.reset_for_tests()
    memory_manager.init("c-native")
    ctx = SimpleNamespace(semantic_control_enabled=True, turns=[], heartbeat=lambda: None)
    monkeypatch.setattr(call_context, "get", lambda call_id: ctx)

    async def assistant_line(*_a, **_k):
        return {"seq": 33, "role": "assistant"}

    async def trace(*_a, **_k):
        return None

    from server.call import live_turn_orchestrator as module

    monkeypatch.setattr(module.call_ledger, "append_assistant_turn", assistant_line)
    monkeypatch.setattr(module.call_ledger, "append_trace_turn", trace)
    monkeypatch.setattr(module, "maybe_refresh_rolling_summary", lambda *a, **k: _noop())
    await live_turn_orchestrator._after_assistant(
        "c-native", "సరే Saikiran గారు.", 100,
        memory_update={"operations": [{"op": "set_fact", "key": "quantity", "value": "బల్క్", "evidence": "బల్క్"}]},
        turn_seq=32,
        user_text="ఓకే నాకు ఒక 100 విజిటింగ్ కార్స్ కావాలి. ఇది చెప్పండి, మీ మేనేజర్ కి చెప్పండి. నా పేరు Saikiran",
    )
    facts = memory_manager.peek_snapshot("c-native")["facts"]
    assert facts.get("quantity") == "100"
    assert facts.get("caller_name") == "Saikiran"
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


async def _noop():
    return None
