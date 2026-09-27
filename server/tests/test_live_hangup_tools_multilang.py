"""Live hangup tools — parser + gate across languages (tool-sourced trust)."""
from __future__ import annotations

import pytest

from server.call.end_call_validate import caller_firm_refusal, validate_end_call
from server.call.hangup_judge import agent_spoke_closing
from server.realtime.hangup_tools import (
    LIVE_HANGUP_TOOL_NAMES,
    parse_live_hangup_tool,
    parse_request_end_call_tool,
    realtime_hangup_tool_declarations,
)


def _tool_end(raw: dict, user: str, *, lang: str = "te-IN"):
    return validate_end_call(
        raw,
        user_text=user,
        language=lang,
        completed_turns=2,
        tool_sourced=True,
    )


def test_realtime_declarations_include_request_end_call_and_legacy():
    names = {t["name"] for t in realtime_hangup_tool_declarations()}
    assert "request_end_call" in names
    assert "end_call" in names
    assert LIVE_HANGUP_TOOL_NAMES == frozenset({"end_call", "request_end_call"})


def test_parse_request_end_call_customer_declined():
    parsed = parse_request_end_call_tool(
        {"reason": "customer_declined", "farewell_required": True, "farewell_text": ""}
    )
    assert parsed is not None
    assert parsed["should_end"] is True
    assert parsed["reason"] == "firm_refusal"


def test_parse_live_hangup_tool_end_call_alias():
    parsed = parse_live_hangup_tool(
        "end_call",
        {"should_end": True, "reason": "firm_refusal", "farewell": "Thanks."},
    )
    assert parsed and parsed["reason"] == "firm_refusal"


def test_telugu_refusal_regex_repair_path():
    user = "అంటే ప్రస్తుతానికి నాకు ఏ ఇంట్రెస్ట్ లేదు. నాకు బైక్ బాగానే ఉంది ప్రస్తుతానికి."
    assert caller_firm_refusal(user)


def test_telugu_tool_trust_without_latin_refusal_regex():
    user = "అంటే ప్రస్తుతానికి నాకు ఏ ఇంట్రెస్ట్ లేదు. నాకు బైక్ బాగానే ఉంది ప్రస్తుతానికి."
    d = _tool_end(
        parse_request_end_call_tool({"reason": "customer_declined"}) or {},
        user,
    )
    assert d.accepted is True
    assert d.reason == "firm_refusal"


def test_hindi_tool_customer_declined():
    user = "नहीं, मुझे interest नहीं है, बाइक ठीक है।"
    d = _tool_end(
        {"should_end": True, "reason": "firm_refusal", "farewell": "धन्यवाद।"},
        user,
        lang="hi-IN",
    )
    assert d.accepted is True
    assert d.reason == "firm_refusal"


def test_english_tool_goodbye():
    d = _tool_end(
        {"should_end": True, "reason": "goodbye", "farewell": "Goodbye."},
        "that's all, thanks",
        lang="en-IN",
    )
    assert d.accepted is True
    assert d.reason == "goodbye"


def test_tool_goodbye_trusts_hindi_without_english_regex():
    d = _tool_end(
        {"should_end": True, "reason": "goodbye", "farewell": "अलविदा।"},
        "मैं जा रहा हूँ",
        lang="hi-IN",
    )
    assert d.accepted is True
    assert d.reason == "goodbye"


def test_tool_goodbye_without_stt_text():
    d = _tool_end(
        {"should_end": True, "reason": "goodbye", "farewell": "Goodbye."},
        "",
        lang="en-IN",
    )
    assert d.accepted is True
    assert d.reason == "goodbye"


def test_tool_firm_refusal_without_stt_text():
    d = _tool_end(
        parse_request_end_call_tool({"reason": "customer_declined"}) or {},
        "",
        lang="te-IN",
    )
    assert d.accepted is True
    assert d.reason == "firm_refusal"


def test_tool_goodbye_still_blocks_continue():
    d = _tool_end(
        {"should_end": True, "reason": "goodbye", "farewell": "Goodbye."},
        "yes please tell me more",
        lang="en-IN",
    )
    assert d.accepted is False


def test_tool_firm_refusal_rejects_bare_thanks():
    d = _tool_end(
        {"should_end": True, "reason": "firm_refusal", "farewell": "Goodbye."},
        "Thank you.",
        lang="en-IN",
    )
    assert d.accepted is False
    assert d.reject_code == "no_evidence"


def test_telugu_agent_closing_detected():
    assert agent_spoke_closing("సరే అండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు.")


@pytest.mark.asyncio
async def test_hangup_tool_without_live_native_transcript_events():
    """Gemini PSTN: hangup arms from request_end_call only (no user_transcript / Live STT)."""
    from unittest.mock import AsyncMock

    from server.realtime.testing import FakeRealtimeVoiceAdapter

    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=None,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=FakeRealtimeVoiceAdapter(),
        stack_override={"pipeline": "realtime_voice", "language": "te-IN"},
    )
    await loop._handle_event(
        {
            "type": "function_call",
            "name": "request_end_call",
            "call_id": "fn-no-stt",
            "arguments": '{"reason": "customer_declined", "farewell_required": true}',
        }
    )
    assert loop._pending_end_call is not None
    assert loop._pending_end_call.get("reason") == "firm_refusal"
    assert loop._hangup_arm_source == "tool"
    assert loop._last_user_final_text == ""


@pytest.mark.asyncio
async def test_loop_accepts_request_end_call_telugu_refusal():
    from unittest.mock import AsyncMock

    from server.realtime.testing import FakeRealtimeVoiceAdapter

    from server.services.pstn_realtime_voice_core import (
        FAST_REFUSAL_POST_FAREWELL_SEC,
        PstnRealtimeVoiceLoop,
    )

    adapter = FakeRealtimeVoiceAdapter()
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=None,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "language": "te-IN"},
    )
    user = "అంటే ప్రస్తుతానికి నాకు ఏ ఇంట్రెస్ట్ లేదు. నాకు బైక్ బాగానే ఉంది ప్రస్తుతానికి."
    await loop._handle_event({"type": "user_transcript", "text": user, "final": True})
    await loop._handle_event(
        {
            "type": "function_call",
            "name": "request_end_call",
            "call_id": "fn-te",
            "arguments": '{"reason": "customer_declined", "farewell_required": true}',
        }
    )
    assert loop._pending_end_call is not None
    assert loop._pending_end_call.get("reason") == "firm_refusal"
    assert loop._firm_refusal_close is True
    assert loop._close_listen_sec() == 0.0


def test_pstn_loop_arm_flags_on_tool_accept(monkeypatch):
    from unittest.mock import AsyncMock

    from server.realtime.testing import FakeRealtimeVoiceAdapter

    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=None,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=FakeRealtimeVoiceAdapter(),
        stack_override={"pipeline": "realtime_voice"},
    )
    loop._apply_hangup_close_flags("firm_refusal")
    assert loop._firm_refusal_close is True
    assert loop._uses_fast_hangup()
    loop._firm_refusal_close = False
    loop._apply_hangup_close_flags("goodbye")
    assert loop._fast_script_farewell is True
