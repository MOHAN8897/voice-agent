"""Call 35002575 review: one consistent compiled brain, turn timing and slow-reply holding."""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from server.brain.brief_contract import estimate_speech_seconds, opening_length_issue
from server.brain.compiled_brain_artifact import (
    assemble_unified_brain,
    canonicalize_platform_rules,
    refresh_platform_sections,
)
from server.prompts.agent_voice_rules import (
    CALLBACK_RULE,
    OUTBOUND_OPENING_LEAD,
    SLOW_DOWN_FALLBACK,
    SPOKEN_PACKS,
    UNCLEAR_FALLBACK,
    spoken_pack_for,
)
from server.services.pstn_backchannel import (
    HOLDING_PHRASES,
    PstnBackchannelController,
    holding_phrase_for,
)
from server.services.pstn_media_flow import pstn_turn_timing, trace_turn_timing
from server.services.pstn_text_chunker import split_first_sentence

LANGS = ("te-IN", "hi-IN", "ta-IN", "kn-IN", "ml-IN", "mr-IN", "bn-IN", "gu-IN", "pa-IN", "en-IN", "en-US")

# Shape of a stored publication: a script-owned language marker renamed to a pack
# header, platform rules frozen and bulletized inside the business GUARDRAILS.
_LEGACY_SCRIPT = """--- ENTITY TAGS ---
@agent_name: Asha
@role: sales
@direction: outbound
@opening_line: Hello, this is Asha.

--- CANONICAL OPENING ---
After the callee speaks, say once (in the configured language):
Hello, this is Asha.

--- UNKNOWN INFORMATION ---
If asked about any detail not provided, say it is unavailable. Do not invent callbacks, discounts, policies, or capabilities.

--- SPOKEN LANGUAGE ({lang}) ---
Use the selected {lang} language pack.

--- GUARDRAILS ---
Platform safety, tool permissions and call-end policy take precedence.

- -- OUTBOUND WORKFLOW ---
- 1. The platform prepares and plays CANONICAL OPENING once at media readiness.
- 4. If busy, acknowledge and use only a permitted next step. If not interested, thank them and close.
- -- LEAD CAPTURE ---
- Acknowledge details briefly. Do not read the dialed number aloud.
- If they are busy, follow only a source-permitted next step; do not assume a callback is allowed.
- -- PROFESSIONAL CLOSE ---
- Follow CALL END POLICY for refusal, confirmed endings and completed next steps."""


def _legacy_brain(lang: str) -> str:
    return assemble_unified_brain(language=lang, script=_LEGACY_SCRIPT.format(lang=lang)) + (
        "\n\n--- PLATFORM CALL RULES ---\nPlatform rules active — 49 constraint blocks (redacted)"
    )


@pytest.mark.parametrize("lang", ["te-IN", "hi-IN", "en-IN"])
def test_script_owned_language_marker_never_becomes_a_second_pack(lang):
    raw = _LEGACY_SCRIPT.format(lang=lang)
    # Stored publications already contain the script marker inside CALLING SCRIPT.
    stored = refresh_platform_sections(
        f"--- SAFETY ---\nx\n\n{spoken_pack_for(lang, include_brevity=False, core_only=True)}\n\n"
        f"--- CALLING SCRIPT ---\n{raw}\n\n--- STATIC OUTPUT RULES ---\n- y", lang)
    for text in (stored, _legacy_brain(lang)):
        assert len(re.findall(r"--- SPOKEN LANGUAGE \(", text)) == 1
        assert text.count("CONVERSATIONAL REGISTER") == 1


def test_legacy_brain_has_one_callback_rule_and_no_contradictions():
    text = refresh_platform_sections(_legacy_brain("te-IN"), "te-IN")
    assert text.count(CALLBACK_RULE) == 1
    assert "do not assume a callback is allowed" not in text
    assert "If busy, acknowledge and use only a permitted next step" not in text
    assert "invent callbacks" not in text and "Do not invent discounts" in text
    assert "- 4. If not interested, thank them and close." in text
    # The rule lands under PROFESSIONAL CLOSE, in that section's bullet style.
    assert f"- -- PROFESSIONAL CLOSE ---\n- Follow CALL END POLICY" in text
    assert f"\n- {CALLBACK_RULE}" in text
    assert "constraint blocks (redacted)" not in text
    assert "After the callee speaks, say once" not in text
    assert f"--- CANONICAL OPENING ---\n{OUTBOUND_OPENING_LEAD}\nHello, this is Asha." in text


def test_canonicalization_is_idempotent_and_byte_stable():
    once = refresh_platform_sections(_legacy_brain("hi-IN"), "hi-IN")
    assert refresh_platform_sections(once, "hi-IN") == once
    assert canonicalize_platform_rules(once) == once


def test_inbound_opening_lead_is_left_to_the_agent():
    script = _LEGACY_SCRIPT.replace("@direction: outbound", "@direction: inbound").format(lang="en-IN")
    text = canonicalize_platform_rules(script)
    assert "After the callee speaks, say once" in text


@pytest.mark.parametrize("lang", LANGS)
def test_slow_down_and_unclear_lines_carry_evidence_conditions(lang):
    pack = spoken_pack_for(lang, include_brevity=False, core_only=True)
    slow = next(line for line in pack.splitlines() if SLOW_DOWN_FALLBACK[lang] in line)
    unclear = next(line for line in pack.splitlines() if UNCLEAR_FALLBACK[lang] in line)
    assert "never after a short reply" in slow
    assert "garbled or cut off" in unclear and "never for a clear short reply" in unclear
    assert "never as a closing question" not in pack


@pytest.mark.parametrize("lang", LANGS)
def test_every_pack_language_supports_the_new_rules(lang):
    assert lang in SPOKEN_PACKS
    assert holding_phrase_for(lang) == HOLDING_PHRASES[lang]


async def _fresh(brief: str, lang: str, direction: str, role: str):
    from server.brain.agent_script_compiler import compile_agent_from_brief

    compiled, result, *_ = await compile_agent_from_brief(
        brief=brief, language=lang, interpret_brief=False, direction=direction,
        generation_config={"callDirection": direction, "agentRole": role})
    return compiled, result


@pytest.mark.parametrize("lang,direction,role", [
    ("te-IN", "outbound", "sales"), ("hi-IN", "inbound", "support"), ("en-IN", "outbound", "appointment"),
])
def test_fresh_compile_has_one_rule_set(lang, direction, role):
    brief = ("Agent name is Arjun from GreenHome Solar. Offer a free rooftop solar site survey. "
             "Price of the survey is 0 rupees. Note a preferred day.")
    compiled, _result = asyncio.run(_fresh(brief, lang, direction, role))
    assert compiled.count(CALLBACK_RULE) == 1
    assert compiled.count("--- SPOKEN LANGUAGE (") == 1
    assert "do not assume a callback" not in compiled
    assert "Volunteer a callback only when" not in compiled
    assert "answer honestly if asked whether you are AI" not in compiled.split("--- STATIC OUTPUT RULES ---")[0]
    if direction == "outbound":
        assert OUTBOUND_OPENING_LEAD in compiled
        assert "runtime authorizes the opening" not in compiled
    # The live render changes no rule text, and is byte-stable on every turn.
    live = refresh_platform_sections(compiled, lang)
    assert live.split() == compiled.split()
    assert refresh_platform_sections(live, lang) == live


def test_long_opening_is_a_warning_not_a_cut():
    long_opening = ("Hello, my name is Meera calling from subhasri sells. I am reaching out to see if you would be "
                    "interested in purchasing our digital products like icards and visiting cards at the best prices. "
                    "Do you have a moment to talk about this?")
    assert estimate_speech_seconds(long_opening) > 8
    issue = opening_length_issue(long_opening)
    assert issue and issue["severity"] == "warning" and issue["code"] == "opening_too_long"
    assert opening_length_issue("Hello, this is Asha from GreenHome. Is now a good time?") is None
    brief = f'Agent name is Meera from subhasri sells. Sell visiting cards. Exact opening: "{long_opening}"'
    compiled, result = asyncio.run(_fresh(brief, "en-IN", "outbound", "sales"))
    assert long_opening in compiled
    assert [item["code"] for item in result.issues].count("opening_too_long") == 1


def test_split_first_sentence():
    assert split_first_sentence("") == []
    assert split_first_sentence("Only one sentence here.") == ["Only one sentence here."]
    # A short reply (a farewell, a yes) stays one request.
    assert split_first_sentence("Thanks for your time. Goodbye.") == ["Thanks for your time. Goodbye."]
    long_reply = ("Cards cost twenty five rupees each. Delivery is by post within a week, and you can pay "
                  "by card or cash on delivery. Shall I note your order?")
    first, rest = split_first_sentence(long_reply)
    assert first == "Cards cost twenty five rupees each."
    assert rest.startswith("Delivery is by post") and rest.endswith("Shall I note your order?")
    te = split_first_sentence("ఒక్కో card ఇరవై ఐదు రూపాయలు. Delivery post ద్వారా వారం లోపల అవుతుంది. "
                              "Payment card లేదా cash on delivery ద్వారా చేయొచ్చు. మీ order note చేయమంటారా?")
    assert len(te) == 2


def test_turn_timing_reaches_trace_by_transcript():
    pstn_turn_timing.clear("c1")
    pstn_turn_timing.record("c1", "need 100 cards", stt_final_ms=180)
    pstn_turn_timing.record("c1", "need 100 cards", llm_ttft_ms=900)
    pstn_turn_timing.record("c1", "need 100 cards", tts_first_audio_ms=350, e2e_ms=1500)
    pstn_turn_timing.record("c1", "a later turn", stt_final_ms=90)
    timing = trace_turn_timing("c1", "need 100 cards", stt_final_ms=None, llm_ttft_ms=None, e2e_ms=None)
    assert timing == {"stt_final_ms": 180, "llm_ttft_ms": 900, "tts_first_audio_ms": 350, "e2e_ms": 1500}
    # Popped once; a non-voice path keeps the orchestrator's own values.
    assert trace_turn_timing("c1", "need 100 cards", llm_ttft_ms=42, e2e_ms=42)["llm_ttft_ms"] == 42
    assert trace_turn_timing("c1", "a later turn")["stt_final_ms"] == 90


def test_live_trace_block_uses_measured_timing():
    source = Path(__file__).resolve().parents[1] / "call" / "live_turn_orchestrator.py"
    text = source.read_text(encoding="utf-8")
    assert "trace_turn_timing(call_id, user_text" in text
    assert '"tts_first_audio_ms": None,' not in text


class _FakeVoice:
    def __init__(self):
        self._closed = False
        self._turn_busy = True
        self.current_turn_id = "t1"
        self._phase = "thinking"
        self._active_tts_session = SimpleNamespace(has_sent_text=False)
        self._last_user_partial_at = 0.0
        self._backchannel_lock = asyncio.Lock()
        self._backchannel_task = None
        self._backchannel_playing = False
        self._turn_audio_delivered = False
        self.call_id = "c-hold"
        self.frames: list[bytes] = []

    def emission_blocked(self):
        return False

    def _resolve_language(self):
        return "te-IN"

    async def _emit_agent_wire(self, frame):
        self.frames.append(frame)
        self._turn_audio_delivered = True


def test_holding_line_plays_once_and_never_on_consecutive_turns(monkeypatch):
    import server.services.pstn_backchannel as bc

    monkeypatch.setattr(bc, "HOLD_AFTER_S", 0.01)

    async def run():
        voice = _FakeVoice()
        ctl = PstnBackchannelController(voice)
        ctl._hold_frames = [b"a", b"b"]
        ctl.start_hold("t1")
        await asyncio.sleep(0.05)
        assert voice.frames == [b"a", b"b"]
        # The holding line is not a delivered reply (watchdog / outage fallback).
        assert voice._turn_audio_delivered is False
        voice.current_turn_id = "t2"
        ctl.start_hold("t2")
        await asyncio.sleep(0.05)
        assert voice.frames == [b"a", b"b"]
        voice.current_turn_id = "t3"
        ctl.start_hold("t3")
        await asyncio.sleep(0.05)
        assert len(voice.frames) == 4

    asyncio.run(run())


def test_holding_line_skipped_when_reply_already_speaking_or_caller_talking(monkeypatch):
    import time

    import server.services.pstn_backchannel as bc

    monkeypatch.setattr(bc, "HOLD_AFTER_S", 0.01)

    async def run():
        voice = _FakeVoice()
        ctl = PstnBackchannelController(voice)
        ctl._hold_frames = [b"a"]
        voice._active_tts_session = SimpleNamespace(has_sent_text=True)
        ctl.start_hold("t1")
        await asyncio.sleep(0.05)
        voice._active_tts_session = SimpleNamespace(has_sent_text=False)
        voice._last_user_partial_at = time.monotonic() + 1
        voice.current_turn_id = "t2"
        ctl.start_hold("t2")
        await asyncio.sleep(0.05)
        # An unfired line is simply dropped when the reply is ready first.
        voice._last_user_partial_at = 0.0
        monkeypatch.setattr(bc, "HOLD_AFTER_S", 5)
        voice.current_turn_id = "t3"
        ctl.start_hold("t3")
        await ctl.settle_hold()
        assert voice.frames == []

    asyncio.run(run())


_CALL = Path(__file__).resolve().parents[2] / "data" / "calls" / "35002575-2555-4b96-9058-6d345942a13d" / "meta.json"


@pytest.mark.skipif(not _CALL.exists(), reason="call evidence not present")
def test_call_35002575_live_brain_is_smaller_and_consistent():
    from server.agent.brain_prompt_composer import estimate_tokens

    stored = json.loads(_CALL.read_text(encoding="utf-8"))["compiled_brain_text"]
    live = refresh_platform_sections(stored, "te-IN")
    assert estimate_tokens(live) < estimate_tokens(stored) - 800
    assert live.count("CONVERSATIONAL REGISTER") == 1
    assert live.count(CALLBACK_RULE) == 1
    assert "do not assume a callback is allowed" not in live
