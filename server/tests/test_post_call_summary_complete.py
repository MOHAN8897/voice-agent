"""Call summaries are never half summaries.

* A provider that stops at its token limit (finish_reason "length" / Responses
  status "incomplete") is retried with a larger budget instead of having its cut
  JSON "repaired" into a summary that ends mid-sentence.
* Summaries are not sliced to a fixed character count anywhere on the way to the
  console.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from server.call import post_call_pipeline as pipeline
from server.providers.base import StructuredOutputTruncated
from server.providers.openai_llm import responses_truncation_reason

FULL = (
    "The caller asked about two-bedroom flats near the lake and shared a budget of 80 lakh. "
    "The agent explained the available towers and the payment plan. "
    "The caller worried about the possession date, and the agent confirmed it is March 2027. "
    "They agreed on a site visit on Saturday at 11 am. "
    "The call ended politely with the caller thanking the agent."
)


def _payload(summary: str = FULL) -> dict:
    return {
        "disposition": "site_visit_planned", "disposition_confidence": 0.9, "summary_te": "",
        "summary_en": summary, "next_action": "Confirm the Saturday visit.", "extracted_fields": [],
        "objections": [], "notes": None, "tags": [], "custom_tags": [],
    }


class _Adapter:
    """Truncates until the budget reaches ``needs`` tokens, then answers in full."""

    def __init__(self, needs: int):
        self.needs = needs
        self.budgets: list[int] = []

    async def structured_completion(self, messages, schema, config, *, schema_name, max_output_tokens, **_):
        self.budgets.append(max_output_tokens)
        if max_output_tokens < self.needs:
            raise StructuredOutputTruncated("openai", max_output_tokens, "max_output_tokens")
        return _payload()


def _run(adapter, monkeypatch):
    monkeypatch.setattr("server.providers.get_provider_registry",
                        lambda: SimpleNamespace(get_llm=lambda _p: adapter,
                                                is_provider_enabled=lambda *_: False,
                                                is_model_allowed=lambda *_: False))

    async def no_sleep(*_a, **_k):
        return None

    monkeypatch.setattr(pipeline.asyncio, "sleep", no_sleep)
    transcript = [{"role": "user", "text": "Hi, I want a flat."}, {"role": "assistant", "text": "Sure."}]
    return asyncio.run(pipeline._generate_outcome(transcript, {}, {}, model="gpt-test"))


def test_length_stop_retries_with_a_larger_budget_and_keeps_the_whole_summary(monkeypatch):
    adapter = _Adapter(needs=4096)
    payload, error = _run(adapter, monkeypatch)
    assert error is None
    assert adapter.budgets == [2048, 4096]
    assert payload["summary_en"] == FULL


def test_first_budget_is_large_enough_for_a_reasoning_model(monkeypatch):
    adapter = _Adapter(needs=0)
    _run(adapter, monkeypatch)
    # The old fixed 1200-token cap was shared with reasoning tokens.
    assert adapter.budgets[0] >= 2048


def test_always_truncated_falls_back_without_cutting_a_turn(monkeypatch):
    adapter = _Adapter(needs=10**9)
    payload, error = _run(adapter, monkeypatch)
    assert error and "truncated" in error
    assert payload["summary_en"].startswith("Automatic summary generation failed.")
    assert payload["summary_en"].endswith("Assistant: Sure.")


def test_empty_structured_answer_is_retried_not_saved_blank(monkeypatch):
    calls = {"n": 0}

    class Flaky:
        async def structured_completion(self, *_a, **_k):
            calls["n"] += 1
            return {} if calls["n"] == 1 else _payload()

    payload, error = _run(Flaky(), monkeypatch)
    assert error is None and payload["summary_en"] == FULL and calls["n"] == 2


def test_finish_summary_never_cuts_and_closes_the_last_sentence():
    assert pipeline.finish_summary(FULL) == FULL
    assert pipeline.finish_summary("The caller asked for a callback") == "The caller asked for a callback."
    assert pipeline.finish_summary("  Spaced   out.  ") == "Spaced out."
    long_text = " ".join(["The caller explained one more detail."] * 60)
    assert pipeline.finish_summary(long_text) == long_text


def test_transcript_fallback_keeps_whole_turns():
    turns = [f"User: sentence number {i} is here." for i in range(400)]
    text = pipeline._transcript_review(turns)
    assert len(text) <= 2100
    body = text.split("Transcript review: ", 1)[1]
    assert body.endswith("more turns in the full transcript.)")
    kept = body.rsplit(" (", 1)[0]
    # Every kept turn is whole: the text before the "more turns" note ends a turn.
    assert kept.endswith(" is here.")


@pytest.mark.parametrize("response,expected", [
    (SimpleNamespace(status="incomplete", incomplete_details=SimpleNamespace(reason="max_output_tokens")), "max_output_tokens"),
    ({"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}, "max_output_tokens"),
    (SimpleNamespace(status="incomplete", incomplete_details=SimpleNamespace(reason="content_filter")), None),
    (SimpleNamespace(status="completed", incomplete_details=None), None),
    (SimpleNamespace(), None),
])
def test_openai_incomplete_response_is_detected(response, expected):
    assert responses_truncation_reason(response) == expected


def test_openai_adapter_raises_instead_of_repairing_cut_json(monkeypatch):
    from server.providers import openai_llm

    cut = '{"disposition": "interested", "summary_en": "The caller asked about the price and'
    response = SimpleNamespace(status="incomplete", incomplete_details=SimpleNamespace(reason="max_output_tokens"),
                               output_text=cut, output=[], usage=None)

    class Client:
        class responses:  # noqa: N801
            @staticmethod
            async def create(**_kw):
                return response

    async def noop(*_a, **_k):
        return None

    monkeypatch.setattr("server.utils.http_clients.get_openai_client", lambda: Client)
    monkeypatch.setattr("server.services.saas.post_call_costs.record_post_call_response", noop)
    adapter = openai_llm.OpenAILLMAdapter()
    with pytest.raises(StructuredOutputTruncated):
        asyncio.run(adapter.structured_completion([{"role": "user", "content": "x"}], {"type": "object"},
                                                  max_output_tokens=50))


def test_list_and_feed_enrichment_return_the_full_summary(monkeypatch):
    from server.routes import calls as calls_routes

    monkeypatch.setattr("server.call.post_call_pipeline.read_outcome",
                        lambda _cid: {"summary_en": FULL, "extracted_fields": []})
    monkeypatch.setattr(calls_routes.call_ledger, "review_fields", lambda _cid: {})
    calls_routes._ENRICH_CALL_CACHE.pop("call-full-summary", None)
    try:
        out = calls_routes._enrich_call_list_item({"call_id": "call-full-summary", "summary": None})
    except Exception as exc:  # pragma: no cover - surfaced with context
        pytest.fail(f"enrichment failed: {exc}")
    assert out.get("summary") == FULL
