"""PSTN dial metadata must not merge Test Studio stack when inherit is false."""
from __future__ import annotations

from server.services.pstn_voice_core import pstn_call_options


def test_pstn_call_options_platform_stack_when_not_inheriting(monkeypatch):
    monkeypatch.setattr(
        "server.services.test_studio_config.saved_call_config",
        lambda _sid: {
            "stack_override": {
                "pipeline": "realtime_voice",
                "llm": {"provider": "openai", "model": "gpt-realtime-2.1-mini"},
            }
        },
    )
    gemini = {
        "pipeline": "realtime_voice",
        "llm": {"provider": "gemini", "model": "gemini-3.8-live"},
    }
    opts = pstn_call_options(
        {
            "agent_id": "a1",
            "inherit_test_studio_config": False,
            "source_session_id": "test-studio:a1",
            "stack_override": gemini,
        }
    )
    assert opts["stack_override"]["llm"]["provider"] == "gemini"


def test_pstn_call_options_merges_when_inheriting(monkeypatch):
    monkeypatch.setattr(
        "server.services.test_studio_config.saved_call_config",
        lambda _sid: {
            "stack_override": {
                "pipeline": "realtime_voice",
                "llm": {"provider": "openai", "model": "gpt-realtime-2.1-mini"},
            }
        },
    )
    gemini = {
        "pipeline": "realtime_voice",
        "llm": {"provider": "gemini", "model": "gemini-3.8-live"},
    }
    opts = pstn_call_options(
        {
            "agent_id": "a1",
            "inherit_test_studio_config": True,
            "source_session_id": "test-studio:a1",
            "stack_override": gemini,
        }
    )
    assert opts["stack_override"]["llm"]["provider"] == "gemini"


def test_gemini_realtime_dial_keeps_test_studio_config_session():
    """Test Studio Gemini Live PSTN must lock brain from test-studio:{agent}, not published agent."""
    opts = pstn_call_options(
        {
            "agent_id": "fb93adcd-2f61-4b69-b1b7-f34ed3a61b7e",
            "inherit_test_studio_config": True,
            "source_session_id": "test-studio:fb93adcd-2f61-4b69-b1b7-f34ed3a61b7e",
            "stack_override": {
                "pipeline": "realtime_voice",
                "llm": {"provider": "gemini", "model": "gemini-3.8-live"},
            },
        }
    )
    assert opts["config_session_id"] == "test-studio:fb93adcd-2f61-4b69-b1b7-f34ed3a61b7e"
    assert opts["stack_override"]["llm"]["model"] == "gemini-3.8-live"
