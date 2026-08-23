from unittest.mock import patch

from server.agent.conversation_manager import conversation_manager
from server.agent.instruction_builder import build_brain_request_input
from server.agent.session_memory import session_memory
from server.services.memory_summarizer import compact_history_summary, should_update_summary
from server.services.prompt_cache_key import caching_enabled


def test_get_context_for_brain_limits_turns():
    cm = conversation_manager.__class__(max_messages=20)
    sid = "ctx-test"
    for i in range(5):
        cm.add_turn(sid, f"user-{i}", f"assistant-{i}")
    ctx = cm.get_context_for_brain(sid, max_turns=2)
    assert len(ctx) == 4
    assert ctx[0]["content"] == "user-3"
    cm.clear(sid)


def test_session_summary_compaction():
    history = [
        {"role": "user", "content": "నాకు flat కావాలి"},
        {"role": "assistant", "content": "ఏ area?"},
        {"role": "user", "content": "Gachibowli"},
    ]
    summary = compact_history_summary(history)
    assert "Earlier in this call" in summary
    assert "Gachibowli" in summary


def test_should_update_summary_every_n():
    assert should_update_summary(4, 4) is True
    assert should_update_summary(3, 4) is False


def test_build_brain_request_input_includes_summary():
    msgs = build_brain_request_input(
        brain_prompt="brain",
        history=[],
        transcript="hi",
        session_summary="Earlier in this call the user said: hello",
    )
    assert len(msgs) == 3
    assert "[Session summary]" in msgs[1]["content"][0]["text"]


def test_caching_requires_min_tokens():
    assert caching_enabled("gpt-5.6-luna", 1024) is True
    assert caching_enabled("gpt-5.6-luna", 1023) is False
    assert caching_enabled("gpt-5.5", 2000) is False


def test_session_memory_clear():
    session_memory.set_summary("s1", "summary text")
    session_memory.clear("s1")
    assert session_memory.get_summary("s1") == ""


def test_after_turn_memory_updates_summary(monkeypatch):
    from server.services import openai_brain_service as svc

    monkeypatch.setenv("ENABLE_SESSION_SUMMARY", "true")
    monkeypatch.setenv("SUMMARY_EVERY_N_TURNS", "1")
    svc.get_settings.cache_clear()

    sid = "mem-turn"
    conversation_manager.clear(sid)
    session_memory.clear(sid)
    conversation_manager.add_turn(sid, "hello", "hi")

    svc._after_turn_memory(sid)
    assert session_memory.get_summary(sid)

    conversation_manager.clear(sid)
    session_memory.clear(sid)
    svc.get_settings.cache_clear()


def test_factory_defaults_cache_eligible():
    from server.agent.brain_prompt_composer import compose_brain_prompt, estimate_tokens

    text = compose_brain_prompt()
    assert estimate_tokens(text) >= 1024


def test_partial_override_empty_user_with_business():
    from server.services import openai_brain_service as svc

    with patch.object(svc.instruction_store, "get_behaviour", return_value="STORED-BEHAVIOUR"):
        use_stored, ui, bi, _, bp = svc._resolve_instruction_overrides("s1", "", "Biz facts", None)
    assert use_stored is False
    assert ui == "STORED-BEHAVIOUR"
    assert bi == "Biz facts"
    assert bp is None

    from server.agent.brain_prompt_composer import compose_brain_prompt, estimate_tokens

    text = compose_brain_prompt()
    assert estimate_tokens(text) >= 1024


def test_empty_instruction_fields_use_stored_brain(monkeypatch):
    from server.services import openai_brain_service as svc

    stored = "STORED-BRAIN-MARKER"
    with patch.object(svc.instruction_store, "get_brain_prompt", return_value=stored) as mock_get, patch(
        "server.services.openai_brain_service.compose_brain_prompt"
    ) as mock_compose, patch.object(svc.conversation_manager, "get_context_for_brain", return_value=[]):
        use_stored, ui, bi, rs, bp = svc._resolve_instruction_overrides("s1", "", "", "")
        assert use_stored is True
        assert ui == ""
        assert bp is None
        use_stored2, _, _, _, bp2 = svc._resolve_instruction_overrides("s1", None, None, None)
        assert use_stored2 is True
        assert bp2 is None
        _, _, _, _, bp3 = svc._resolve_instruction_overrides("s1", None, None, None, brain_prompt="CUSTOM-PROMPT")
        assert bp3 == "CUSTOM-PROMPT"
        svc._prepare_brain_context(
            session_id="s1",
            transcript="hi",
            language_code="te-IN",
            user_instructions="",
            business_instructions=None,
            response_style=None,
            openai_model="gpt-5.6-luna",
            use_stored_brain=True,
        )
        mock_get.assert_called_once()
        mock_compose.assert_not_called()
