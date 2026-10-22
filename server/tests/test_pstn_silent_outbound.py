"""Regression tests for the silent-outbound-call failures.

Each test pins one real defect found on a live Telnyx outbound call where the
callee heard nothing:
  1. every brain writer format must be readable by the PSTN greeting extractor
  2. a greeting that resolves to nothing must be logged, not silently dropped
  3. a lost carrier socket must end the call, not leave it running mute
  4. an answered call that never produces audio must be ended, not billed
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from server.services.pstn_text_chunker import (  # noqa: E402
    extract_opening_greeting,
    extract_prewarm_greeting,
)

GENERIC_FALLBACK_EN = "Hi, this is a courtesy call. Do you have a moment?"


# --- 1. writer/reader format agreement -------------------------------------


@pytest.mark.parametrize(
    "label,brain,expected",
    [
        (
            "saas studio writes 'Opening greeting:'",
            "<!-- section:identity_purpose:1 -->\nRole: Voice agent\n"
            "Opening greeting: Hi, this is Priya from Vertex Education about admissions."
            " Do you have a moment?\n",
            "Hi, this is Priya from Vertex Education about admissions. Do you have a moment?",
        ),
        (
            "voxly console writes 'OPENING LINE' + line",
            "<!-- section:facts:2 -->\nOPENING LINE\n"
            "Hi, I am Alex from Spandana Private Limited regarding fees. Do you have a moment?\n",
            "Hi, I am Alex from Spandana Private Limited regarding fees. Do you have a moment?",
        ),
        (
            "brief compiler writes 'Example opening:'",
            "--- OPENING ---\n"
            "Example opening: Hi, this is Alex calling from Spandana about fees."
            " Do you have a moment?\nONE spoken reply per turn.\n",
            "Hi, this is Alex calling from Spandana about fees. Do you have a moment?",
        ),
        (
            "legacy block form still wins",
            "--- CANONICAL OPENING ---\nHi, this is Kiran from Vertex. Do you have a moment?\n--- END ---\n",
            "Hi, this is Kiran from Vertex. Do you have a moment?",
        ),
    ],
)
def test_every_brain_writer_format_yields_a_real_greeting(label, brain, expected):
    """A brain that stores an opening must never fall back to a generic greeting."""
    assert extract_opening_greeting(brain, "en-IN", direction="outbound") == expected, label
    assert extract_prewarm_greeting(brain, "en-IN", direction="outbound") == expected, label


def test_brain_without_an_opening_still_falls_back():
    """No opening anywhere must keep the generic fallback, not raise or return None."""
    brain = "VOICE CALL MODE\n- Be brief.\n- Sound natural.\n"
    assert extract_opening_greeting(brain, "en-IN", direction="outbound") == GENERIC_FALLBACK_EN


def test_policy_lines_are_not_mistaken_for_a_greeting():
    """Labelled lines must still reject policy text, not speak instructions aloud."""
    for brain in (
        "Opening: NEVER read this aloud, it is internal policy.\n",
        "Opening greeting: NEVER read this aloud.\n",
        "opening_line: NEVER say this\n",
        "Opening: VOICE CALL MODE\n",
    ):
        assert extract_opening_greeting(brain, "en-IN", direction="outbound") == (
            GENERIC_FALLBACK_EN
        ), brain


# --- 2. observability for an unresolved greeting ----------------------------


def test_prewarm_logs_when_the_provider_returns_no_audio(monkeypatch):
    """Empty frames used to return silently, which is why this reached a live call."""
    import server.services.pstn_prewarm as prewarm_mod

    logged: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        prewarm_mod, "log_pstn", lambda event, **kw: logged.append((event, kw)), raising=False
    )
    monkeypatch.setattr(
        prewarm_mod,
        "extract_prewarm_greeting",
        lambda *a, **k: "Hi, this is Alex from Spandana. Do you have a moment?",
        raising=False,
    )
    monkeypatch.setattr(prewarm_mod, "pstn_call_options", lambda *a, **k: {}, raising=False)

    class _Agent:
        agent_id = "a"
        languages = ["en-IN"]
        environment = "development"

    class _Stack:
        class llm:  # noqa: N801
            model = "gemini-3.8-live"

    class _Svc:
        async def _resolve_agent(self, agent_id=None):
            return {"agent_id": "a", "languages": ["en-IN"], "environment": "development"}

        def _coerce_pipeline_stack(self, *a, **k):
            return _Stack()

        def _resolve_locked_stack(self, *a, **k):
            return object()

        async def _lock_compiled_brain(self, *a, **k):
            return "v1", "Opening greeting: Hi there.", "src"

    class _Adapter:
        def is_open(self):
            return True

    class _Mgr:
        def get(self, key):
            return _Adapter()

        async def create(self, *a, **k):
            return _Adapter()

    async def _no_frames(*a, **k):
        return [], None, None

    import server.realtime.voice_manager as vmod

    monkeypatch.setattr(vmod, "realtime_voice_manager", _Mgr(), raising=False)
    monkeypatch.setattr(
        "server.call.call_lifecycle_service.call_lifecycle_service", _Svc(), raising=False
    )
    import server.realtime.models as models_mod

    monkeypatch.setattr(models_mod, "pipeline_mode", lambda **k: "realtime_voice", raising=False)
    import server.services.pstn_realtime_greeting_prewarm as gp

    monkeypatch.setattr(gp, "synthesize_gemini_greeting_on_side_session", _no_frames, raising=False)

    async def _go():
        return await prewarm_mod._build_prewarm_bundle("telnyx", "ctl-1", {}, "rt-1")

    bundle = asyncio.run(_go())
    assert bundle.greeting_wire_frames == []
    events = [e for e, _ in logged]
    assert "prewarm.greeting.realtime.empty" in events, (
        "a provider that returns no audio must be logged, not silently dropped"
    )


def test_outbound_without_frames_is_logged():
    """`greeting.deferred.miss` only fired for one of several no-greeting shapes."""
    import server.services.pstn_realtime_voice_core as core

    src = open(core.__file__, encoding="utf-8").read()
    assert '"no_prewarm_frames"' in src and '"no_greeting_text"' in src, (
        "every no-greeting shape must leave a trace, not skip the log entirely"
    )


# --- 3/4. the bridge must not leave a billable mute call ---------------------


def test_bridge_defines_a_first_audio_watchdog():
    """An answered call with no agent audio must be ended, not left billing."""
    import server.services.telnyx_pstn_bridge as bridge

    assert bridge.FIRST_OUTBOUND_AUDIO_GRACE_SEC > 0
    assert hasattr(bridge.TelnyxPstnBridge, "_watch_first_outbound_audio")


def test_first_audio_grace_is_configurable_and_bounded():
    """A hard-coded grace period would either hang up healthy slow calls or bill mute ones."""
    from server.config.env import get_settings
    import server.services.telnyx_pstn_bridge as bridge

    assert get_settings().telnyx_first_audio_grace_sec > 0
    # The env value seeds the module default the watchdog actually reads.
    assert bridge.FIRST_OUTBOUND_AUDIO_GRACE_SEC > 0
    original = get_settings().telnyx_first_audio_grace_sec
    try:
        get_settings().telnyx_first_audio_grace_sec = 0.0
        assert bridge._default_first_audio_grace_sec() == bridge._DEFAULT_FIRST_AUDIO_GRACE_SEC
        get_settings().telnyx_first_audio_grace_sec = 3.5
        assert bridge._default_first_audio_grace_sec() == 3.5
    finally:
        get_settings().telnyx_first_audio_grace_sec = original


def test_bridge_ends_the_call_when_the_media_socket_dies():
    """A dropped socket previously closed the bridge and left the call up mute."""
    import server.services.telnyx_pstn_bridge as bridge

    src = open(bridge.__file__, encoding="utf-8").read()
    assert "ClientDisconnected" in src
    assert "media.out.socket_lost" in src
    # The socket-loss branch must hang up rather than only closing the websocket.
    branch = src.split("media.out.socket_lost", 1)[1][:900]
    assert "_provider_hangup()" in branch, "a lost media socket must end the call"


def test_watchdog_is_cancelled_during_cleanup():
    """A completed call must not leave the watchdog sleeping in the background."""
    import server.services.telnyx_pstn_bridge as bridge

    src = open(bridge.__file__, encoding="utf-8").read()
    cleanup = src.split("async def _cleanup", 1)[1]
    assert "_silence_watchdog_task" in cleanup
    assert "watchdog.cancel()" in cleanup


# --- the greeting the callee actually heard ---------------------------------


def test_generic_fallback_carries_no_agent_identity():
    """Documents the shipped failure: a name-less opening, which is the bug symptom."""
    fallback = extract_prewarm_greeting("no opening here", "en-IN", direction="outbound")
    assert fallback == GENERIC_FALLBACK_EN
    assert "Alex" not in fallback and "Spandana" not in fallback


def test_json_fixture_of_the_shipped_failure_is_readable():
    """A real published SaaS brain shape must now yield its configured greeting."""
    brain = json.dumps({"facts": ""}) and (
        "<!-- section:identity_purpose:a -->\n"
        "Role: Voice agent\n"
        "Opening greeting: Hi, this is Alex from Spandana Private Limited about fees."
        " Do you have a moment?\n"
        "<!-- section:facts:b -->\n1. Greet the customer\n"
    )
    assert "Spandana" in (extract_prewarm_greeting(brain, "en-IN", direction="outbound") or "")


# --- greeting quality, found while verifying the fix -------------------------


def test_opening_block_does_not_absorb_neighbouring_sections():
    """A matched `--- CANONICAL OPENING ---` block must not also scan the next 800 chars.

    The fallback window used to run even after the fenced block matched, so policy
    lines and the longest-first sort made `RUNTIME TAGS` outrank the real greeting.
    """
    brain = (
        "--- CANONICAL OPENING ---\n"
        "Hi, this is Priya. Do you have a moment?\n"
        "--- END ---\n"
        "RUNTIME TAGS (fill when known; never read empty tags aloud)\n"
        "{{callback_phone}}: Phone number to call or text back\n"
        "Counsel using COMPANY & OFFER facts. Do not invent prices.\n"
    )
    got = extract_opening_greeting(brain, "en-IN", direction="outbound")
    assert got == "Hi, this is Priya. Do you have a moment?"


def test_a_greeting_is_never_doubled_by_the_enricher():
    """Prepending an intro to a line that already introduces the agent doubled it."""
    brain = (
        "--- AGENT IDENTITY ---\n"
        "You are Priya, calling from Spandana Private Limited.\n"
        "--- CANONICAL OPENING ---\n"
        "Hi, this is Priya. Do you have a moment?\n"
        "--- END ---\n"
    )
    got = extract_prewarm_greeting(brain, "en-IN", direction="outbound")
    assert got is not None
    assert got.lower().count("priya") == 1, f"agent name repeated: {got!r}"
    assert "Spandana" in got, "the company is still added when the line omits it"


def test_agent_copula_is_not_mistaken_for_the_agent_name():
    """"Agent is Priya" used to produce "Is Priya", which was then spoken aloud."""
    from server.brain.agent_script_compiler import extract_agent_name_from_brief

    assert extract_agent_name_from_brief("Agent is Priya. Call parents about fees.") != "Is Priya"
