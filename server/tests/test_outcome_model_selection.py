"""Call outcomes use the call's own text LLM first, so one provider outage cannot blank every status."""
from types import SimpleNamespace

from server.call import post_call_pipeline as pipeline


def _registry(enabled: bool):
    return SimpleNamespace(is_provider_enabled=lambda *_: enabled, is_model_allowed=lambda *_: enabled)


def test_sarvam_call_marks_status_with_sarvam_then_openai(monkeypatch):
    monkeypatch.setattr("server.providers.get_provider_registry", lambda: _registry(True))
    meta = {"resolved_stack": {"llm": {"provider": "sarvam", "model": "sarvam-105b-conversations",
                                       "config": {"api_mode": "chat_completions_v1"}}}}
    assert pipeline._outcome_models(meta, openai_model="gpt-x") == [
        ("sarvam", "sarvam-105b-conversations", "chat_completions_v1"), ("openai", "gpt-x", None)]


def test_disabled_or_realtime_call_model_falls_back_to_openai_only(monkeypatch):
    monkeypatch.setattr("server.providers.get_provider_registry", lambda: _registry(False))
    meta = {"resolved_stack": {"llm": {"provider": "sarvam", "model": "sarvam-105b-conversations"}}}
    assert pipeline._outcome_models(meta, openai_model="gpt-x") == [("openai", "gpt-x", None)]
    assert pipeline._outcome_models({}, openai_model="gpt-x") == [("openai", "gpt-x", None)]
