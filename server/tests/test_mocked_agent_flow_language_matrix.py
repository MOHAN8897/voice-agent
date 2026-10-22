"""Three offline compiled-brain, prewarm, and hangup checks for each supported locale."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from server.brain.compiled_brain_artifact import assemble_unified_brain
from server.brain.brain_prompt_validate import assert_rendered_brain_valid
from server.call.hangup_judge import default_farewell_for
from server.config.constants import Constants
from server.prompts.agent_voice_rules import LANGUAGE_LOCK, opening_line_for
from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.pstn_realtime_greeting_prewarm import prewarm_greeting_response_instructions
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop
from server.services.pstn_text_chunker import extract_prewarm_greeting


LOCALES = tuple(Constants.SUPPORTED_LANGUAGES)
_OPENING_BRAIN = "--- AGENT IDENTITY ---\nYou are Sam, calling from Acme.\n--- OPENING ---\n"


@pytest.mark.parametrize("locale", LOCALES)
def test_compiled_brain_language_lock_and_hangup_contract(locale: str) -> None:
    brain = assemble_unified_brain(
        language=locale,
        script=f"--- AGENT IDENTITY ---\nYou are a helpful representative.\n@language: {locale}\n",
    )

    assert f"--- SPOKEN LANGUAGE ({locale}) ---" in brain
    assert LANGUAGE_LOCK[locale] in brain
    assert "request_end_call" in brain or "end_call" in brain
    assert_rendered_brain_valid(brain, locale)


@pytest.mark.parametrize("locale", LOCALES)
def test_prewarm_uses_the_compiled_locale_and_exact_opening(locale: str) -> None:
    opening = opening_line_for(
        locale,
        agent_name="Sam",
        company_name="Acme",
        work_scope="",
        direction="outbound",
    )
    prompt = prewarm_greeting_response_instructions(locale, opening)

    assert LANGUAGE_LOCK[locale] in prompt
    assert f'Opening line: "{opening}"' in prompt
    assert extract_prewarm_greeting(
        _OPENING_BRAIN + opening,
        locale,
        direction="outbound",
    ) == opening
    assert "Do not hang up" in prompt
    assert "Do not use tools" in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", LOCALES)
async def test_mocked_integration_talks_and_hangs_up_after_farewell_audio(locale: str) -> None:
    adapter = FakeRealtimeVoiceAdapter()
    wire_frames: list[bytes] = []

    async def on_wire(data: bytes) -> None:
        wire_frames.append(data)

    loop = PstnRealtimeVoiceLoop(
        session_id=f"mock-{locale}",
        call_id=None,
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        tenant_id="tenant-test",
        agent_id="agent-test",
        agent_tools={"googlecalendar_find_free_slots"},
        stack_override={"pipeline": "realtime_voice", "language": locale},
    )
    finish_hangup = AsyncMock()
    loop._finish_hangup = finish_hangup
    farewell = default_farewell_for(locale)

    try:
        with patch(
            "server.services.tool_router.tool_router.route_and_execute",
            new_callable=AsyncMock,
            return_value={"status": "success", "slots": [{"start": "14:00", "end": "15:00"}]},
        ) as route:
            await loop._handle_event(
                {
                    "type": "function_call",
                    "name": "googlecalendar_find_free_slots",
                    "call_id": f"tool-{locale}",
                    "arguments": json.dumps({"date": "2030-01-02"}),
                }
            )

        route.assert_awaited_once_with(
            tenant_id="tenant-test",
            agent_id="agent-test",
            call_id="",
            tool_name="googlecalendar_find_free_slots",
            arguments={"date": "2030-01-02"},
        )
        assert any(f"tool-{locale}" in item for item in adapter.started_responses)

        # A model-simulated spoken farewell is sent before the end-call tool in this turn.
        await loop._handle_event({"type": "audio_delta", "pcm": b"\x01\x00" * 2400})
        await loop._handle_event({"type": "assistant_transcript_delta", "delta": farewell})
        await loop._handle_event(
            {
                "type": "function_call",
                "name": "request_end_call",
                "call_id": f"hangup-{locale}",
                "arguments": json.dumps({"should_end": True, "reason": "goodbye", "farewell": farewell}),
            }
        )

        assert loop._pending_end_call is not None
        assert loop._pending_farewell_text == farewell
        assert not loop._hangup_started
        finish_hangup.assert_not_awaited()

        # The transport disconnect is reached only after the farewell response completes.
        await loop._handle_event({"type": "response_done"})
        assert wire_frames, "mock agent audio should reach the telephony wire callback"
        assert loop._farewell_complete is True
        finish_hangup.assert_awaited_once()
    finally:
        await loop.close()
