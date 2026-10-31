"""Mid-call English fallback: detection, call state, reply-model input, speech stages.

A caller who asks for English, says they cannot follow the call language, or keeps
answering only in English moves the live call to en-IN for the rest of the call.
Other languages become a recorded callback while the call carries on.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.call import language_switch as ls
from server.call.call_ledger import call_ledger
from server.config.env import get_settings


def _live_ctx(language: str = "te-IN", **extra):
    base = dict(call_id=str(uuid.uuid4()), tenant_id=str(uuid.uuid4()), agent_id=str(uuid.uuid4()),
                status="active", contact_preference="none", call_end_policy=None,
                supports_language_switch=True, resolved_stack=SimpleNamespace(language=language))
    return SimpleNamespace(**{**base, **extra})


# -- Detection ------------------------------------------------------------------------

@pytest.mark.parametrize(("text", "language"), [
    ("Sorry, I don't understand Telugu", "te-IN"),
    ("I can't follow Tamil", "ta-IN"),
    ("తెలుగు రాదు", "te-IN"),
    ("Telugu raadu andi", "te-IN"),
    ("मुझे तमिल समझ नहीं आती", "ta-IN"),
    ("Kannada nahi aata", "kn-IN"),
    ("தமிழ் தெரியாது", "ta-IN"),
    ("ಕನ್ನಡ ಬರಲ್ಲ", "kn-IN"),
    ("मुझे मराठी समझ नहीं आता", "mr-IN"),
    ("Sorry, I don't understand what you are saying", "te-IN"),
    ("I am not able to follow, sorry", "hi-IN"),
])
def test_caller_cannot_follow_the_call_language(text, language):
    assert ls.caller_cannot_follow(text, language)


@pytest.mark.parametrize(("text", "language"), [
    ("no no, I know Telugu", "te-IN"),
    ("Telugu is fine, continue", "te-IN"),
    ("నాకు అర్థం కాలేదు, మళ్ళీ చెప్పండి", "te-IN"),  # asks to repeat, in the call language
    ("I don't understand the price", "en-IN"),       # already English
    ("मुझे हिंदी नहीं आती", "te-IN"),                    # another language, not the call's
    ("kya hai ye samajh nahi aaya", "te-IN"),          # unnamed, and not English
])
def test_content_confusion_and_other_languages_are_not_a_barrier(text, language):
    assert not ls.caller_cannot_follow(text, language)


# -- Decisions on a call that can switch live ----------------------------------------

def test_asking_for_english_switches_the_live_call():
    ctx = _live_ctx()
    decision = ls.decide_language_switch(ctx, "Sorry, I don't understand Telugu. Can you speak in English please?", "te-IN")
    assert (decision.action, decision.language, decision.reason) == ("switch", "en-IN", "asked")


@pytest.mark.parametrize("language,text", [
    ("te-IN", "తెలుగు రాదు"),
    ("hi-IN", "Sorry, I don't understand Hindi"),
    ("ta-IN", "தமிழ் தெரியாது"),
    ("kn-IN", "ಕನ್ನಡ ಬರಲ್ಲ"),
    ("ml-IN", "I can't understand Malayalam"),
    ("bn-IN", "I don't understand Bengali"),
    ("gu-IN", "I don't understand Gujarati"),
    ("pa-IN", "I don't understand Punjabi"),
    ("mr-IN", "I don't understand Marathi"),
])
def test_cannot_follow_falls_back_to_english_in_every_language(language, text):
    decision = ls.decide_language_switch(_live_ctx(language), text, language)
    assert (decision.action, decision.language, decision.reason) == ("switch", "en-IN", "cannot_follow")


def test_two_english_only_answers_switch_to_english():
    ctx = _live_ctx()
    assert ls.decide_language_switch(ctx, "What is the price of the visiting cards please", "te-IN") is None
    decision = ls.decide_language_switch(ctx, "And how long will the delivery take to my place", "te-IN")
    assert (decision.action, decision.language, decision.reason) == ("switch", "en-IN", "answered_in_english")


def test_english_streak_is_broken_by_a_turn_in_the_call_language():
    ctx = _live_ctx()
    assert ls.decide_language_switch(ctx, "What is the price of the visiting cards please", "te-IN") is None
    assert ls.decide_language_switch(ctx, "సరే, delivery ఎప్పుడు అవుతుంది?", "te-IN") is None
    assert ls.decide_language_switch(ctx, "And how long will the delivery take to my place", "te-IN") is None


def test_asking_for_the_call_language_again_switches_back():
    ctx = _live_ctx()
    ctx.active_language = "en-IN"
    decision = ls.decide_language_switch(ctx, "Telugu lo matladandi", "en-IN")
    assert (decision.action, decision.language) == ("switch", "te-IN")


def test_other_language_is_a_callback_and_the_call_continues():
    ctx = _live_ctx()
    decision = ls.decide_language_switch(ctx, "Hindi lo matladandi", "te-IN")
    assert (decision.action, decision.language, decision.switch_to) == ("callback", "hi-IN", "")
    assert "హిందీ" in decision.text  # confirmed in the active language (Telugu)


def test_callback_request_from_a_caller_who_cannot_follow_also_moves_to_english():
    ctx = _live_ctx()
    decision = ls.decide_language_switch(ctx, "I don't understand Telugu, call me back in Hindi", "te-IN")
    assert (decision.action, decision.language, decision.switch_to) == ("callback", "hi-IN", "en-IN")
    assert decision.text == ls.close_line("te-IN", "hi-IN")


def test_callback_ask_in_english_after_the_switch():
    ctx = _live_ctx()
    ctx.active_language = "en-IN"
    decision = ls.decide_language_switch(
        ctx, "Actually I am more comfortable in Hindi. Can someone call me back in Hindi tomorrow evening?", "en-IN")
    assert (decision.action, decision.language) == ("callback", "hi-IN")
    assert decision.text == "Sure, I'll arrange a call back for you in Hindi."


def test_opt_out_wins_over_a_switch_or_callback():
    assert ls.decide_language_switch(_live_ctx(), "Don't call me again. Speak English", "te-IN") is None
    assert ls.decide_language_switch(_live_ctx(contact_preference="do_not_call"), "in English please", "te-IN") is None
    assert ls.decide_language_switch(_live_ctx(), "Stop calling me, call me back in Hindi never", "te-IN") is None


def test_sustained_other_language_offers_a_callback_without_claiming_one_language_only():
    ctx = _live_ctx("ta-IN")
    assert ls.decide_language_switch(ctx, "मुझे इसकी कीमत जाननी है कृपया बताइए", "ta-IN") is None
    offer = ls.decide_language_switch(ctx, "डिलीवरी कब तक होगी बताइए", "ta-IN")
    assert offer.action == "offer" and offer.language == "hi-IN"
    assert "மட்டும்" not in offer.text and "ஹிந்தி" in offer.text
    accepted = ls.decide_language_switch(ctx, "சரி", "ta-IN")
    assert (accepted.action, accepted.language) == ("callback", "hi-IN")


def test_unsupported_language_is_still_a_once_only_hint():
    ctx = _live_ctx("hi-IN")
    assert ls.decide_language_switch(ctx, "Urdu mein baat karo", "hi-IN").action == "hint"
    assert ls.decide_language_switch(ctx, "Urdu mein baat karo please", "hi-IN") is None


# -- Applying a switch: state, meta, listener ---------------------------------------

@pytest.fixture
def ledger_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def _meta(ctx, language="te-IN"):
    call_ledger.meta_path(ctx.call_id).parent.mkdir(parents=True, exist_ok=True)
    call_ledger.write_meta(ctx.call_id, {"call_id": ctx.call_id, "language": language, "direction": "inbound",
                                         "caller_id": "+919000000001"})


async def test_switch_turn_records_active_language_and_notifies_the_voice_loop(ledger_dir):
    heard: list[str] = []
    ctx = _live_ctx(language_switch_listener=heard.append)
    _meta(ctx)
    turn = await ls.server_language_switch_turn(ctx, "Can you speak English please?", "te-IN")
    assert turn["active_language"] == "en-IN" and "ACTIVE LANGUAGE" in turn["hint"]
    assert "end_call" not in turn  # the call carries on
    assert ctx.active_language == "en-IN" and heard == ["en-IN"]
    meta = call_ledger.read_meta(ctx.call_id)
    assert meta["language"] == "te-IN"  # configured language (post-call summary) unchanged
    assert meta["active_language"] == "en-IN"
    (switch,) = meta["language_switches"]
    assert (switch["from"], switch["to"], switch["reason"]) == ("te-IN", "en-IN", "asked") and switch["at"]

    back = await ls.server_language_switch_turn(ctx, "Telugu lo cheppandi", "en-IN")
    assert back["active_language"] == "te-IN" and ctx.active_language == ""
    meta = call_ledger.read_meta(ctx.call_id)
    assert meta["active_language"] == "te-IN" and [s["to"] for s in meta["language_switches"]] == ["en-IN", "te-IN"]


async def test_callback_turn_records_item_confirms_and_keeps_the_call_open(ledger_dir, monkeypatch):
    from server.services.saas import language_switch_service as svc

    record = AsyncMock(return_value={"id": "item-1"})
    monkeypatch.setattr(svc, "record_language_switch", record)
    ctx = _live_ctx()
    ctx.active_language = "en-IN"
    _meta(ctx)
    turn = await ls.server_language_switch_turn(ctx, "Please call me back in Hindi", "en-IN")
    assert "end_call" not in turn and turn["active_language"] == "en-IN"
    assert "Sure, I'll arrange a call back for you in Hindi." in turn["hint"]
    assert "do not end the call" in turn["hint"]
    kwargs = record.await_args.kwargs
    assert (kwargs["requested_language"], kwargs["original_language"]) == ("hi-IN", "te-IN")
    # The same request later is not recorded twice.
    assert await ls.server_language_switch_turn(ctx, "Hindi please, call me back", "en-IN") is None
    assert record.await_count == 1


async def test_failed_callback_save_never_promises(ledger_dir, monkeypatch):
    from server.services.saas import language_switch_service as svc

    monkeypatch.setattr(svc, "record_language_switch", AsyncMock(side_effect=RuntimeError("db down")))
    ctx = _live_ctx()
    _meta(ctx)
    turn = await ls.server_language_switch_turn(ctx, "Hindi lo matladandi", "te-IN")
    assert "could not be saved" in turn["hint"] and "Do not promise a callback" in turn["hint"]
    assert "Begin your reply" not in turn["hint"]


# -- Reply-model input: one late note, replaced, never stacked -----------------------

def _messages(brain: str):
    from server.agent.instruction_builder import build_live_input

    return build_live_input(compiled_brain_text=brain, history=[{"role": "user", "content": "హలో"},
                            {"role": "assistant", "content": "నమస్కారం"}], transcript="speak English", enable_cache=True)


def test_active_language_note_is_one_late_message_and_the_static_prefix_is_unchanged():
    brain = "--- SPOKEN LANGUAGE (te-IN) ---\nPrimary language: Telugu (te-IN)."
    ctx = _live_ctx(active_language="en-IN")
    original = _messages(brain)
    prefix = json.dumps(original[0], ensure_ascii=False)
    once = ls.with_active_language(original, ctx)
    twice = ls.with_active_language(once, ctx)
    for messages in (once, twice):
        notes = [m for m in messages if ls._message_text(m).startswith(ls.ACTIVE_LANGUAGE_HEADER)]
        assert len(notes) == 1
        assert messages[-2] is notes[0] and messages[-1]["role"] == "user"
        assert json.dumps(messages[0], ensure_ascii=False) == prefix
        assert len(messages) == len(original) + 1
    text = ls._message_text(notes[0])
    assert text.startswith("--- ACTIVE LANGUAGE (en-IN) ---")
    assert "--- SPOKEN LANGUAGE (en-IN) ---" in text and "from Telugu to English" in text
    # Switching back removes the note rather than adding a Telugu one.
    ctx.active_language = ""
    assert ls.with_active_language(twice, ctx) == original


def test_no_note_before_any_switch():
    original = _messages("brain")
    assert ls.with_active_language(original, _live_ctx()) == original


# -- Brain rule at the source and in published brains --------------------------------

def test_published_brains_lose_the_never_switch_rule_at_render():
    from server.brain.compiled_brain_artifact import canonicalize_platform_rules

    old = ("Primary language: Telugu (te-IN). Speak naturally. Reply in Telugu even if the caller switches language "
           "or asks for another one; never switch mid-call. The platform offers a call back in the requested language.\n"
           "If the caller speaks another language and you cannot follow: use the language-mismatch line once, then wait. "
           "Ordinary English mixing does not require a language reminder.\n"
           "Language: te-IN. Style: warm. Only if a language barrier prevents understanding: say once 'x' — do not switch languages.")
    out = canonicalize_platform_rules(old)
    assert "never switch mid-call" not in out and "do not switch languages" not in out
    assert "Reply in Telugu unless a later ACTIVE LANGUAGE note names another language" in out
    assert "English or mixed speech is never a mismatch" in out and "never switch on your own" in out


def test_fresh_spoken_pack_follows_the_active_language_note():
    from server.prompts.agent_voice_rules import spoken_pack_for

    for code in ("te-IN", "hi-IN", "ta-IN", "kn-IN", "ml-IN", "mr-IN", "bn-IN", "gu-IN", "pa-IN", "en-IN"):
        pack = spoken_pack_for(code, include_brevity=False, core_only=True)
        assert "ACTIVE LANGUAGE note" in pack and "never switch mid-call" not in pack


# -- Fixed lines follow the active language -------------------------------------------

def test_tenant_farewell_in_the_call_script_gives_way_after_an_english_switch():
    from server.call.call_end_policy import server_farewell_for

    policy = {"farewell": "మీ సమయానికి ధన్యవాదాలు, శుభదినం.", "farewellSource": "tenant"}
    assert server_farewell_for("te-IN", policy=policy) == policy["farewell"]
    english = server_farewell_for("en-IN", policy=policy)
    assert english == "Thank you for your time. Goodbye."
    assert server_farewell_for("en-IN", policy={"farewell": "Thanks, have a great day!", "farewellSource": "tenant"}) \
        == "Thanks, have a great day!"


# -- Voices -------------------------------------------------------------------------

def test_voice_kept_when_it_speaks_english_else_closest_voice():
    from server.providers import voice_inventory as inv

    assert inv.voice_for_language("sarvam", "bulbul:v3", "priya", "en-IN") == ("priya", False)
    assert inv.voice_for_language("gnani", "timbre-v3.0", "Vasudha", "en-IN") == ("Vasudha", False)
    # Cartesia Indian-accent voices speak en-IN (live-checked); kept as is.
    assert inv.voice_for_language("cartesia", "sonic-3.5", "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc", "en-IN")[1] is False


def test_voice_substitution_keeps_gender_and_prefers_a_native_persona(monkeypatch):
    from server.providers import voice_inventory as inv

    rows = [
        {"providerVoiceId": "telugu_f", "languages": ["te-IN"], "gender": "female"},
        {"providerVoiceId": "english_m", "languages": ["en-IN", "te-IN"], "gender": "male"},
        {"providerVoiceId": "multi_f", "languages": ["en-IN", "te-IN"], "gender": "female"},
        {"providerVoiceId": "native_en_f", "languages": ["en-IN", "te-IN"], "gender": "female",
         "preferredLanguages": ["en-IN"]},
    ]
    monkeypatch.setattr(inv, "voices_for_model", lambda provider, model: rows)
    assert inv.voice_for_language("x", "m", "telugu_f", "en-IN") == ("native_en_f", True)
    assert inv.voice_for_language("x", "m", "custom-clone", "en-IN") == ("custom-clone", False)


# -- TTS session: one open socket re-tuned with a config message ---------------------

class _Socket:
    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))


def _tts_session(provider: str, model: str, speaker: str, language: str = "te-IN", active: str = "en-IN"):
    from server.services.pstn_turn_tts import PstnTurnTtsSession

    voice = SimpleNamespace(call_id="c1", _resolve_language=lambda: active)
    session = PstnTurnTtsSession.__new__(PstnTurnTtsSession)
    session._voice, session._opened, session._closed = voice, True, False
    session._tts, session._model = _Socket(), model
    session._unary_config = session._stream_config = None
    session._merged = {"provider": provider, "model": model, "speaker": speaker, "language_code": language,
                       "output_audio_codec": "linear16", "speech_sample_rate": "16000"}
    return session


@pytest.mark.parametrize(("provider", "model", "speaker"), [
    ("sarvam", "bulbul:v3", "priya"),
    ("gnani", "timbre-v3.0", "Vasudha"),
    ("cartesia", "sonic-3.5", "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"),
])
async def test_open_tts_session_sends_an_english_config_with_the_same_voice(provider, model, speaker):
    session = _tts_session(provider, model, speaker)
    await session.sync_language()
    (config,) = session._tts.sent
    assert config["type"] == "config"
    assert config["data"]["language_code"] == "en-IN" and config["data"]["speaker"] == speaker
    assert "provider" not in config["data"]
    await session.sync_language()  # already in the active language: nothing more is sent
    assert len(session._tts.sent) == 1


async def test_tts_session_switches_back_to_the_call_language():
    session = _tts_session("gnani", "timbre-v3.0", "Vasudha", language="en-IN", active="te-IN")
    await session.sync_language()
    assert session._tts.sent[-1]["data"]["language_code"] == "te-IN"


# -- Voice loop: active language and STT re-tune --------------------------------------

def test_voice_loop_resolves_the_active_language(monkeypatch):
    from server.call import call_context
    from server.services.pstn_voice_core import PstnVoiceLoop

    ctx = _live_ctx()
    loop = PstnVoiceLoop.__new__(PstnVoiceLoop)
    loop.call_id = ctx.call_id
    loop._cached_resolve_language = "te-IN"
    monkeypatch.setattr(call_context, "get", lambda call_id: ctx if call_id == ctx.call_id else None)
    assert loop._resolve_language() == "te-IN"
    ctx.active_language = "en-IN"
    assert loop._resolve_language() == "en-IN"


class _Cm:
    def __init__(self, ws):
        self.ws, self.closed = ws, False

    async def __aenter__(self):
        return self.ws

    async def __aexit__(self, *exc):
        self.closed = True


async def test_stt_reopens_in_the_active_language_then_retires_the_old_socket(monkeypatch):
    from server.call import call_context
    from server.routes import ws as ws_routes
    from server.services import pstn_voice_core as core

    ctx = _live_ctx(active_language="en-IN")
    monkeypatch.setattr(call_context, "get", lambda call_id: ctx if call_id == ctx.call_id else None)
    opened: list[str] = []
    new_cm = _Cm("new-socket")

    def fake_connect(**kwargs):
        opened.append(kwargs["language_code"])
        return new_cm

    monkeypatch.setattr(ws_routes, "_connect_stt_upstream", fake_connect)
    monkeypatch.setattr(core, "STT_SWITCH_GRACE_S", 0)
    loop = core.PstnVoiceLoop.__new__(core.PstnVoiceLoop)
    old_cm = _Cm("old-socket")
    loop.call_id, loop.session_id, loop.config_session_id, loop.sample_rate = ctx.call_id, "s", "s", 8000
    loop.stack_override, loop._closed, loop._phase = {}, False, core.PHASE_LISTENING
    loop._stt, loop._stt_cm, loop._stt_language, loop._stt_swapped = "old-socket", old_cm, "te-IN", False
    await loop._switch_stt_language()
    assert opened == ["en-IN"]
    assert (loop._stt, loop._stt_cm, loop._stt_language) == ("new-socket", new_cm, "en-IN")
    assert old_cm.closed and not new_cm.closed
    # The supervisor restarts its reader on the new socket instead of counting a failure.
    assert loop._take_stt_swap() is True and loop._take_stt_swap() is False


async def test_failed_stt_reopen_keeps_listening_in_the_old_language(monkeypatch):
    from server.call import call_context
    from server.routes import ws as ws_routes
    from server.services import pstn_voice_core as core

    ctx = _live_ctx(active_language="en-IN")
    monkeypatch.setattr(call_context, "get", lambda call_id: ctx if call_id == ctx.call_id else None)

    class _Broken:
        async def __aenter__(self):
            raise ConnectionError("refused")

    monkeypatch.setattr(ws_routes, "_connect_stt_upstream", lambda **kw: _Broken())
    loop = core.PstnVoiceLoop.__new__(core.PstnVoiceLoop)
    old_cm = _Cm("old-socket")
    loop.call_id, loop.session_id, loop.config_session_id, loop.sample_rate = ctx.call_id, "s", "s", 8000
    loop.stack_override, loop._closed, loop._phase = {}, False, core.PHASE_LISTENING
    loop._stt, loop._stt_cm, loop._stt_language, loop._stt_swapped = "old-socket", old_cm, "te-IN", False
    await loop._switch_stt_language()
    assert (loop._stt, loop._stt_language) == ("old-socket", "te-IN") and not old_cm.closed


# -- Orchestrator: the switched turn reaches the reply model in English --------------

async def test_live_turn_reaches_the_reply_model_in_the_active_language(ledger_dir, monkeypatch):
    from server.call import call_context
    from server.call.live_turn_orchestrator import live_turn_orchestrator

    ctx = _live_ctx(session_id="lls-session", pipeline="realtime_text", turns=[], heartbeat=lambda: None)
    _meta(ctx)
    call_context.put(ctx)
    seen: dict = {}

    async def fake_stream(self, **kwargs):
        seen.update(kwargs)
        yield {"delta": "Sure, let's continue in English."}
        yield {"done": True, "text": "Sure, let's continue in English.", "finish_reason": "stop"}

    monkeypatch.setattr(type(live_turn_orchestrator), "_stream_llm", fake_stream)
    # Other suites patch the shared instance; pin it here too so the run order never matters.
    import types

    monkeypatch.setattr(live_turn_orchestrator, "_stream_llm", types.MethodType(fake_stream, live_turn_orchestrator))
    try:
        chunks = [c async for c in live_turn_orchestrator.handle_user_turn_stream(
            transcript="Sorry, I don't understand Telugu. Can you speak English?", language_code="te-IN",
            session_id="lls-session", call_id=ctx.call_id)]
    finally:
        call_context.clear_all()
    assert seen["language_code"] == "en-IN"
    assert "ACTIVE LANGUAGE" in seen["user_instructions"]
    done = [c for c in chunks if c.get("done")]
    assert done and not (done[-1].get("end_call") or {}).get("should_end")
    assert ctx.active_language == "en-IN"
