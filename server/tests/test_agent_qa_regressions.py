"""Regressions found by the NatureVeda multilingual agent QA run (2026-10-31)."""
from types import SimpleNamespace

import pytest

from server.call.action_proof import unproven_claim
from server.services.nango_service import _credential_refresh_failed
from server.services.pstn_text_chunker import drain_complete_sentences
from server.services.voice_pipeline_limits import collapse_repeated_spoken_reply


@pytest.mark.parametrize("text,claim", [
    ("आपकी enquiry save हो गई है।", "enquiry_saved"),
    ("మీ enquiry save అయింది.", "enquiry_saved"),
    ("आपका order place हो गया है।", "order_confirmed"),
    ("ಆರ್ಡರ್ ಕನ್ಫರ್ಮ್ ಆಗಿದೆ.", "order_confirmed"),
])
def test_code_mixed_done_claims_need_proof(text, claim):
    assert unproven_claim(text, []) == claim


@pytest.mark.parametrize("text", [
    "क्या मैं आपका order place कर दूँ?",
    "आपकी enquiry save नहीं हो पाई।",
    "मैं आपका order place कर दूँगी, ठीक है?",
])
def test_offers_questions_and_negations_are_not_claims(text):
    assert unproven_claim(text, []) is None


def test_email_address_is_one_tts_chunk_while_streaming():
    pending, spoken = "", []
    for delta in ("మీ email mohansaiteja.99@gmail.", "com", " కి details పంపించాను.", " Thanks for your time today."):
        pending += delta
        ready, pending = drain_complete_sentences(pending)
        spoken += ready
    assert spoken[0] == "మీ email mohansaiteja.99@gmail.com కి details పంపించాను."


def test_glued_sentence_fix_keeps_domains_intact():
    out = collapse_repeated_spoken_reply("Mail sent to a.b@gmail.com today.Visit www.natureveda.in")
    assert "gmail.com" in out and "www.natureveda.in" in out and "today. Visit" in out


@pytest.mark.parametrize("status,text,expected", [
    (400, "Failed to get connection credentials: The external API returned an error when trying to refresh the access token.", True),
    (424, '{"error":{"code":"connection_refresh_backoff","message":"A recent refresh attempt failed."}}', True),
    (400, "Invalid to header", False),
])
def test_gmail_token_refresh_failure_is_a_reauthorization(status, text, expected):
    assert _credential_refresh_failed(SimpleNamespace(status_code=status, text=text)) is expected


def test_review_runs_only_where_it_can_fix_something():
    from server.call.spoken_fact_review import review_resolves, review_triggers
    src = "Hair Oil - 499 rupees (200 ml). Face Cream - 599 rupees (50 g)."
    assert review_triggers("I need your name and delivery address. Could you share those?", "en-IN", src, []) == set()
    assert review_triggers("The face cream is 599 rupees for 50 g.", "en-IN", src, []) == set()
    assert review_triggers("The total is 1,597 rupees.", "en-IN", src, []) == {"number"}
    assert review_triggers("We have a festive discount this week.", "en-IN", src, []) == {"fact"}
    assert review_triggers("क्या आप इसका order place करना चाहेंगी?", "en-IN", src, []) == {"script"}
    # A wrong total is corrected; a correct one padded with extra prices is not a correction.
    assert review_resolves({"number"}, "Total is 1,497.", "Total is 1,597.", "en-IN", src, [])
    assert not review_resolves({"number"}, "Total is 1,597.", "Total is 1,597: 2 at 499, 1 at 599.", "en-IN", src, [])


@pytest.mark.asyncio
async def test_review_that_invents_an_action_keeps_the_draft(monkeypatch):
    from server.call import spoken_fact_review
    from server import providers

    class Adapter:
        async def stream_live_turn(self, **_kw):
            yield {"done": True, "text": "I am placing the order now and will confirm the details shortly."}

    monkeypatch.setattr(providers, "get_provider_registry", lambda: SimpleNamespace(get_llm=lambda _p: Adapter()))
    ctx = SimpleNamespace(compiled_brain_text="--- AGENT IDENTITY ---\nYou are Priya.", call_id="c1", session_id="s1",
                          resolved_stack=SimpleNamespace(llm=SimpleNamespace(provider="sarvam", model="m", config={})),
                          turn_action_results=[], action_receipts=[], turn_control=None, available_tools=[])
    draft = "We do have a festive offer. I need your name and address to place it. What is your name?"
    out = await spoken_fact_review.review_spoken_turn(ctx, caller="Yes, go ahead.", draft=draft, language="en-IN")
    assert out == draft


def test_a_confirmed_booking_also_proves_the_request_was_recorded():
    assert unproven_claim("Your request has been noted and the call is booked for 11 AM.", ["appointment_confirmed"]) is None
    assert unproven_claim("Your request has been noted.", []) == "enquiry_saved"


def test_repeat_stripping_keeps_email_addresses_whole():
    from server.call.reply_guard import sentences
    assert sentences("I noted mohansaiteja.99@gmail.com, but cannot verify it. Price is 80.5 rupees.") == [
        "I noted mohansaiteja.99@gmail.com, but cannot verify it.", "Price is 80.5 rupees."]


@pytest.mark.parametrize("text,fixed", [
    ("देखिए, 2 bottles hair oil और 1 face cream का total ₹1497 होगा। Hair oil 499 रुपये है और face cream 599 रुपये की है।", "₹1597"),
    ("2 Hair Oil at ₹499 and 1 Face Cream at ₹599 come to ₹1,497.", "₹1,597"),
])
def test_wrong_multi_item_total_is_corrected(text, fixed):
    from server.call.spoken_fact_review import correct_stated_total
    src = "Hair Oil - 499 rupees (200 ml). Face Cream - 599 rupees (50 g)."
    assert fixed in correct_stated_total(text, src)


@pytest.mark.parametrize("text", [
    "The total for two bottles of Hair Oil at 499 rupees and one Face Cream at 599 rupees is 1,597 rupees.",
    "Hair oil 200 ml ₹499, face cream 50 g ₹599.",
    "2 Hair Oil at ₹499 and 1 Face Cream at ₹599 come to ₹1,597.",
])
def test_correct_or_ambiguous_totals_are_left_alone(text):
    from server.call.spoken_fact_review import correct_stated_total
    assert correct_stated_total(text, "Hair Oil - 499 rupees (200 ml). Face Cream - 599 rupees (50 g).") == text


@pytest.mark.asyncio
@pytest.mark.parametrize("reselect,expected", [
    ({"done": True, "text": "", "tool_calls": [{"name": "CONFIRM_ORDER"}]}, "after_tools"),
    ({"done": True, "text": "Shall I confirm 2 hair oil and 1 face cream?"}, "Shall I confirm 2 hair oil and 1 face cream?"),
])
async def test_empty_speech_pass_reoffers_the_tools(reselect, expected):
    """Sarvam returns null content when the model calls a tool it was not offered."""
    from server.call.live_turn_orchestrator import LiveTurnOrchestrator

    orch = LiveTurnOrchestrator.__new__(LiveTurnOrchestrator)

    async def empty_speech(**_kw):
        yield {"done": True, "text": "", "empty_provider_response": True}

    async def selection(**_kw):
        yield reselect

    async def after_tools(**_kw):
        yield {"done": True, "text": "after_tools"}

    orch._stream_composed_speech = empty_speech
    orch._stream_composed_turn = selection
    orch._composed_speech_after_tools = after_tools
    llm = SimpleNamespace(provider="sarvam", model="m")
    out = [c async for c in orch._speech_or_reselect(
        ctx=None, adapter=SimpleNamespace(stream_live_turn=None), llm_sel=llm, stream_kwargs={}, selection_kwargs={},
        messages=[], tool_schemas=[],
        call_id="c", record_request_usage=lambda _c: None, selection_text="", allow_retry=False)]
    assert out[-1]["text"] == expected


def test_answer_plan_adds_the_combined_total():
    from server.call.business_answer_plan import with_combined_total
    plan = with_combined_total([{"calculated_total": "998"}, {"calculated_total": "599"}, {"status": "not_stated"}])
    assert plan[-1]["calculated_grand_total"] == "1597"
    assert with_combined_total([{"calculated_total": "998"}]) == [{"calculated_total": "998"}]


@pytest.mark.parametrize("text,expected", [
    ("2 bottles hair oil और 1 face cream का total ₹1,497 होगा।", "₹1,597"),
    ("మొత్తం 1,497 రూపాయలు అవుతుంది.", "1,597 రూపాయలు"),
    ("Your pincode 500072 is noted.", "500072"),
    ("Total ₹1,597 होगा।", "₹1,597"),
])
def test_stated_total_follows_the_server_sum(text, expected):
    from server.call.business_answer_plan import with_combined_total
    from server.call.spoken_fact_review import correct_total_from_plan
    plan = with_combined_total([{"calculated_total": "998"}, {"calculated_total": "599"}])
    assert expected in correct_total_from_plan(text, plan, "Hair Oil - 499 rupees. Face Cream - 599 rupees.")


def test_order_tool_comes_with_an_order_flow():
    from server.brain.capabilities import apply_available_tools
    text = apply_available_tools("", [{"name": "CONFIRM_ORDER", "parameters": {"required": ["quantity"]}}])
    assert "after the yes, call CONFIRM_ORDER" in text
    assert "Order flow" not in apply_available_tools("", [{"name": "SAVE_ENQUIRY", "parameters": {}}])


@pytest.mark.parametrize("text", ["ನಾನು ಒಂದು face cream ಮತ್ತೆ ಎರಡು hair oil", "दो bottles hair oil और एक face cream",
                                  "రెండు hair oil, ఒక face cream", "two hair oils and a face cream", "બે hair oil અને એક cream"])
def test_quantity_words_count_in_every_language(text):
    from server.call.business_answer_plan import spoken_quantities
    assert {"1", "2"} <= spoken_quantities(text)


def test_pack_size_is_per_pack_and_counted_units_still_divide():
    from server.call.business_answer_plan import validate_answers, with_combined_total
    rows = ["Hair Oil - 499 rupees (200 ml).", "Face Cream - 599 rupees (50 g).", "Visiting cards cost 200 rupees per 100 cards."]
    item = lambda i, t, v, p, u, q: {"domain": "business_terms", "question": t, "row_id": i, "topic_quote": t, "value_quote": v,
                                     "unit_price_quote": p, "unit_quantity_quote": u, "requested_quantity_quote": q}
    plan = with_combined_total(validate_answers([item(0, "Hair Oil", "499 rupees", "499", "200", "2"),
                                                 item(1, "Face Cream", "599 rupees", "599", "50", "1")], rows, "ಒಂದು face cream ಎರಡು hair oil"))
    assert plan[-1]["calculated_grand_total"] == "1597"
    assert validate_answers([item(2, "Visiting cards", "200 rupees", "200", "100", "300")], rows, "300 cards")[0]["calculated_total"] == "600"


def test_a_re_asked_question_is_answered_again_not_acknowledged():
    from server.agent.conversation_manager import conversation_manager
    from server.call.live_turn_orchestrator import _avoid_verbatim_repeat
    conversation_manager.add_turn("qa-repeat", "how long is delivery?", "I do not have the delivery time.")
    ctx = SimpleNamespace(session_id="qa-repeat", resolved_stack=SimpleNamespace(language="en-IN"))
    assert _avoid_verbatim_repeat("I do not have the delivery time.", ctx, caller="Roughly how many days?") == "I do not have the delivery time."


def test_word_counted_total_is_checked():
    from server.call.spoken_fact_review import correct_stated_total
    text = "ആകെ 1,497 രൂപയാകും. രണ്ട് hair oil 499 രൂപ നിരക്കിലും ഒരു face cream 599 രൂപ നിരക്കിലുമാണ് വരുന്നത്."
    assert "1,597" in correct_stated_total(text, "Hair Oil - 499 rupees (200 ml). Face Cream - 599 rupees (50 g).")



def test_dictated_lead_phone_is_stored_in_e164():
    from server.services.saas.lead_sync import _extract_phone
    assert _extract_phone({"phone": "9876543210"}, {}) == "+919876543210"
    assert _extract_phone({"phone": "+91 98765 43210"}, {}) == "+919876543210"


def test_a_caller_quoted_wrong_total_is_still_corrected():
    from server.call.spoken_fact_review import correct_stated_total
    brain = "Hair Oil - 499 rupees (200 ml). Face Cream - 599 rupees (50 g)."
    reply = "1 face cream 599 रुपये का और 2 hair oil 499 रुपये के हिसाब से total ₹1,497 ही बनेगा।"
    assert "₹1,597" in correct_stated_total(reply, brain)


def test_echo_strip_never_leaves_a_one_word_reply():
    from server.call.reply_guard import strip_filler_echo
    assert strip_filler_echo("ठीक है, noted।", "ठीक है, कोई बात नहीं।") == "ठीक है, noted।"
