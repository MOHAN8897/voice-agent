"""Brain coherence: the compiled prompt must not give opposite instructions, and
fact lookup / fact review must not turn stated facts into unknowns or speak their
own critique. Found by the flow-matrix simulator (server/eval/conversation_sim/flow_matrix.py)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

SALES_BRIEF = """Agent name Priya. Company SunPeak Solar, a rooftop solar installer in Chennai.
You call homeowners who asked for a solar quote on our website.
A 3 kW rooftop system costs 1,95,000 rupees before the government subsidy of 78,000 rupees.
Goal: confirm they are still interested and book a free site survey.
Objections: if they say it is too expensive, explain the subsidy.
If they ask not to be called again, respect it."""


def test_locator_row_id_given_as_json_key_string_is_accepted():
    from server.call.business_answer_plan import validate_answers
    rows = ["Intro line.", "A 3 kW rooftop system costs 1,95,000 rupees."]
    raw = [dict(domain="business_terms", question="cost", row_id="1",
                topic_quote="3 kW rooftop system", value_quote="1,95,000 rupees"),
           dict(domain="business_terms", question="bool id", row_id=True,
                topic_quote="Intro", value_quote="line"),
           dict(domain="business_terms", question="bad id", row_id="x1",
                topic_quote="Intro", value_quote="line")]
    result = validate_answers(raw, rows, "How much does it cost?")
    assert result[0]["status"] == "stated" and result[0]["value"] == "1,95,000 rupees"
    assert [r["status"] for r in result[1:]] == ["not_stated", "not_stated"]


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", [
    "The draft does not fully answer the caller's implicit question about whether proceeding is reasonable.",
    "This reply should mention the subsidy.",
    "business_answer_plan marks cost as not_stated.",
])
async def test_fact_review_critique_never_replaces_the_draft(monkeypatch, verdict):
    from server.call.spoken_fact_review import review_spoken_turn
    from server.providers import get_provider_registry

    class Adapter:
        async def stream_live_turn(self, **kwargs):
            yield dict(done=True, text=verdict)

    monkeypatch.setattr(get_provider_registry(), "get_llm", lambda _: Adapter())
    ctx = SimpleNamespace(call_id="meta-review", session_id="meta-review", compiled_brain_text="Approved facts.",
                          resolved_stack=SimpleNamespace(llm=SimpleNamespace(provider="sarvam", model="m", config={})))
    draft = "Glad to hear that. Would you like to book the free site survey?"
    assert await review_spoken_turn(ctx, caller="Okay, sounds reasonable.", draft=draft, language="en-IN") == draft


@pytest.mark.asyncio
async def test_fact_review_real_correction_still_applies(monkeypatch):
    from server.call.spoken_fact_review import review_spoken_turn
    from server.providers import get_provider_registry

    class Adapter:
        async def stream_live_turn(self, **kwargs):
            yield dict(done=True, text="The inspection fee is not something I have; servicing is 599 rupees.")

    monkeypatch.setattr(get_provider_registry(), "get_llm", lambda _: Adapter())
    ctx = SimpleNamespace(call_id="real-review", session_id="real-review", compiled_brain_text="Approved facts.",
                          resolved_stack=SimpleNamespace(llm=SimpleNamespace(provider="sarvam", model="m", config={})))
    out = await review_spoken_turn(ctx, caller="Fee?", draft="Inspection is free.", language="en-IN")
    assert out.startswith("The inspection fee is not something I have")


@pytest.mark.parametrize("role,direction", [("sales", "outbound"), ("sales", "inbound"),
                                            ("appointment", "inbound"), ("support", "outbound")])
def test_platform_rules_never_forbid_a_caller_requested_callback(role, direction):
    from server.brain.agent_script_compiler import _platform_call_rules
    rules = _platform_call_rules(agent_name="Priya", role=role, direction=direction, language="en-IN")
    assert "do not assume a callback is allowed" not in rules
    # One callback rule for every role and direction (call 35002575 review).
    from server.prompts.agent_voice_rules import CALLBACK_RULE
    assert rules.count(CALLBACK_RULE) == 1
    # One objection rule, which defers to the business script and handles repeats.
    assert rules.count("--- OBJECTION HANDLING ---") == 1
    assert "same objection comes back" in rules


def test_sales_plan_expects_objections_even_when_brief_says_ask():
    from server.brain.agent_script_compiler import _conversation_plan
    plan = _conversation_plan(SALES_BRIEF, agent_name="Priya", company_name="SunPeak Solar",
                              work_scope=SALES_BRIEF, role="sales", direction="outbound")
    assert "Expect questions rather than objections" not in plan
    assert "Expect objections as well as questions" in plan


def test_support_plan_still_expects_questions_and_opt_out_clause_is_not_an_enquiry():
    from server.brain.agent_script_compiler import _conversation_plan
    support = "Agent Arjun of FreshCart. Answer delivery enquiries and refund questions."
    plan = _conversation_plan(support, agent_name="Arjun", company_name="FreshCart",
                              work_scope=support, role="support", direction="inbound")
    assert "Expect questions rather than objections" in plan
    opt_out_only = "Agent Ravi of Acme. Offer the annual plan. If they ask not to be called again, respect it."
    plan = _conversation_plan(opt_out_only, agent_name="Ravi", company_name="Acme",
                              work_scope=opt_out_only, role="other", direction="outbound")
    assert "Expect questions rather than objections" not in plan


@pytest.mark.asyncio
async def test_compiled_sales_brain_has_no_contradictory_callback_or_objection_lines():
    from server.brain.agent_script_compiler import compile_agent_from_brief
    compiled, *_ = await compile_agent_from_brief(
        brief=SALES_BRIEF, language="en-IN", direction="outbound", use_llm=False, interpret_brief=False,
        generation_config={"employeeName": "Priya", "agentRole": "sales", "callDirection": "outbound"})
    assert "do not assume a callback is allowed" not in compiled
    assert "Expect questions rather than objections" not in compiled
    assert "Expect objections as well as questions" in compiled
    from server.prompts.agent_voice_rules import CALLBACK_RULE
    assert compiled.count(CALLBACK_RULE) == 1


def test_employee_script_lists_permitted_next_steps_once():
    from server.brain.employee_script_pipeline import ExtractedBrief, SourcedFact, _business_requirements
    fact = lambda text: SourcedFact(text=text, evidence=text)
    extracted = ExtractedBrief(
        agent_name="Priya", company_name="SunPeak Solar", primary_goal=fact("Book a free site survey"),
        facts=[], workflow=[fact("For the survey take their name, area and preferred day")],
        permitted_next_steps=[fact("Book a free site survey."), fact("For the survey take their name, area and preferred day")],
        forbidden_actions=[], tone=None, conflicts=[], missing_critical_info=[])
    text = _business_requirements(extracted)
    assert text.splitlines()[0] == "For the survey take their name, area and preferred day"
    assert text.splitlines()[1].startswith("Permitted next steps to offer: Book a free site survey. Offering or noting a step never completes it")
    empty = extracted.model_copy(update={"workflow": [], "permitted_next_steps": []})
    assert _business_requirements(empty) == "Follow only the applicable business workflow."


def _registry(monkeypatch, responder):
    from server import providers

    class Adapter:
        async def stream_live_turn(self, **kwargs):
            yield {"done": True, "text": responder(kwargs["input_messages"][0]["content"])}

    registry = SimpleNamespace(is_provider_enabled=lambda *_: True, is_model_allowed=lambda *_: True,
                               get_llm=lambda *_: Adapter())
    monkeypatch.setattr(providers, "get_provider_registry", lambda: registry)


def _llm():
    return SimpleNamespace(provider="sarvam", model="pinned", config={})


@pytest.mark.asyncio
@pytest.mark.parametrize("caller_will_phone,expected", [(False, "callback"), (True, "self_callback")])
async def test_imperative_call_me_misread_as_self_callback_is_rechecked(monkeypatch, caller_will_phone, expected):
    import json
    from server.call import close_classifier

    def responder(system):
        if system.startswith("Understand telephone"):
            return json.dumps({"contact_action": "caller_callback", "contact_evidence": "Call me on Sunday evening at 7",
                               "when": "Sunday evening at 7", "finish": False, "open_request": ""})
        if system.startswith("Decide ONLY who will make the next phone call"):
            return json.dumps({"caller_will_phone": caller_will_phone})
        return json.dumps({"decision": "continue", "contact_intent": "self_callback"})

    _registry(monkeypatch, responder)
    result = await close_classifier.classify_close_turn(
        transcript="Call me on Sunday evening at 7.", agent_previous="When can we call you back?",
        language="en-IN", llm=_llm())
    assert result["contact_intent"] == expected
    if expected == "callback":
        assert result["decision"] == "close" and result["close_verified"] is True


@pytest.mark.asyncio
async def test_callback_without_time_asks_once_then_closes(monkeypatch):
    import json
    from server.call import call_context, close_classifier

    def responder(system):
        if system.startswith("Understand telephone"):
            return json.dumps({"contact_action": "business_callback", "contact_evidence": "call me later",
                               "when": "", "finish": True, "finish_evidence": "call me later", "open_request": ""})
        return json.dumps({"decision": "close", "reason": "done", "evidence": "call me later"})

    _registry(monkeypatch, responder)
    ctx = SimpleNamespace(call_id="cb-no-time", callback_when="", callback_time_prompted=False)
    monkeypatch.setattr(call_context, "get", lambda cid: ctx if cid == "cb-no-time" else None)
    first = await close_classifier.classify_close_turn(
        transcript="I am busy, call me later.", agent_previous="Is now a good time?", language="en-IN",
        llm=_llm(), call_id="cb-no-time")
    assert first["contact_intent"] == "callback" and first["decision"] == "continue"
    assert first["callback_time_needed"] is True and ctx.callback_time_prompted is True
    second = await close_classifier.classify_close_turn(
        transcript="Just call me later.", agent_previous="When would suit you?", language="en-IN",
        llm=_llm(), call_id="cb-no-time")
    assert second["contact_intent"] == "callback" and second["decision"] == "close"


def test_callback_with_time_or_agent_question_closes_immediately(monkeypatch):
    from server.call import call_context, close_classifier
    ctx = SimpleNamespace(call_id="cb", callback_when="", callback_time_prompted=False)
    monkeypatch.setattr(call_context, "get", lambda cid: ctx)
    timed = {"contact_intent": "callback", "decision": "close", "callback_time": "tomorrow at 6"}
    close_classifier._ask_callback_time_once(timed, "cb")
    assert timed["decision"] == "close"
    asked = {"contact_intent": "callback", "decision": "close", "callback_time": "", "agent_asked_time": True}
    close_classifier._ask_callback_time_once(asked, "cb")
    assert asked["decision"] == "close" and ctx.callback_time_prompted is False


def test_contact_rules_treat_already_have_it_as_whole_offer_refusal():
    from server.call.turn_control_prompt import CONTACT_REVIEW_RULES, CONTROL_RULES
    assert "already have" in CONTROL_RULES and "already have" in CONTACT_REVIEW_RULES
    assert '"agent_asked_time":false' in CONTACT_REVIEW_RULES


@pytest.mark.parametrize("text,kept", [
    ("Your order ID is FC10234.", "FC10234"), ("Order 10234 is noted.", "10234"),
    ("Delivery to PIN 500081.", "500081"), ("The fee is 15000 rupees.", "15000"),
])
def test_spoken_reply_keeps_order_ids_and_amounts(text, kept):
    from server.services.spoken_numbers import strip_spoken_phone_numbers
    assert kept in strip_spoken_phone_numbers(text)


@pytest.mark.parametrize("text", ["Call 9876543210.", "Call +91 98765 43210 now.", "Landline 040-23456789.",
                                  "Toll free 18001234567."])
def test_spoken_reply_still_strips_phone_numbers(text):
    from server.services.spoken_numbers import strip_spoken_phone_numbers
    out = strip_spoken_phone_numbers(text)
    assert not any(ch.isdigit() for ch in out)


def test_speech_contract_asks_callback_time_once_and_never_announces_hangup():
    import inspect
    from server.call import live_turn_orchestrator
    source = inspect.getsource(live_turn_orchestrator)
    assert "ask once for a convenient day or" in source
    assert "Never announce that you are ending, closing or hanging up the call" in source


def test_forbidden_actions_render_as_prohibitions():
    from server.brain.employee_script_pipeline import ExtractedBrief, SourcedFact, _guardrails
    fact = lambda text: SourcedFact(text=text, evidence=text)
    extracted = ExtractedBrief(
        agent_name="Priya", company_name=None, primary_goal=fact("Book a survey"), facts=[], workflow=[],
        permitted_next_steps=[], tone=None, conflicts=[], missing_critical_info=[],
        forbidden_actions=[fact("Call back if they ask not to be called again."), fact("Never give a medical diagnosis.")])
    lines = _guardrails(extracted).splitlines()
    # Seen live: the bare forbidden action under GUARDRAILS read as an instruction.
    assert lines[0] == "Never do this: call back if they ask not to be called again."
    assert lines[1] == "Never give a medical diagnosis."
    assert lines[-1].startswith("Platform safety")


@pytest.mark.parametrize("opening,language,expected", [
    ("Namaste, main Priya bol rahi hoon SunPeak Solar se.", "hi-IN", True),
    ("नमस्ते, मैं SunPeak Solar से Priya बोल रही हूँ।", "hi-IN", False),
    ("Hello, this is Priya from SunPeak Solar.", "en-IN", False),
    ("Vanakkam, naan Priya.", "ta-IN", True),
])
def test_romanized_indic_opening_detection(opening, language, expected):
    from server.brain.employee_script_pipeline import _romanized_indic_opening
    assert _romanized_indic_opening(opening, language) is expected
    # A tenant's own exact opening from the brief is never rewritten.
    assert _romanized_indic_opening(opening, language, brief=f'Say exactly: "{opening}"') is False


def _employee_fixture(monkeypatch, *, opening: str, repaired_opening: str):
    import copy
    from server.brain import generation_runtime
    from server.providers.base import LLMConfig

    fact = {"text": "Opening hours are 09:00 to 18:00.", "evidence": "Opening hours are 09:00 to 18:00."}
    extracted = {"agent_name": "Meera", "company_name": "Example Clinic",
                 "primary_goal": {"text": "Answer questions about opening hours.", "evidence": "Answer questions about opening hours."},
                 "facts": [fact], "workflow": [],
                 "permitted_next_steps": [{"text": "Answer questions about opening hours.", "evidence": "Answer questions about opening hours."}],
                 "forbidden_actions": [{"text": "Offer bookings.", "evidence": "Do not offer bookings."}],
                 "tone": None, "conflicts": [], "missing_critical_info": []}
    script = {"opening": opening, "call_flow": "Answer the opening-hours question from the facts.",
              "call_to_action": "Provide the opening hours.", "objection_handling": "Use known facts only; respect refusal.",
              "unknown_information": "Say you do not have unavailable details.", "closing": "Follow platform call-end policy."}
    calls = []

    async def complete(**kwargs):
        import json
        calls.append(kwargs["schema_name"])
        if kwargs["schema_name"] == "employee_brief_extract":
            return copy.deepcopy(extracted)
        if kwargs["schema_name"] == "employee_script_write":
            return copy.deepcopy(script)
        data = json.loads(kwargs["input_messages"][1]["content"][0]["text"])
        fixed = copy.deepcopy(script)
        if data.get("validation_feedback"):
            fixed["opening"] = repaired_opening
        return {"passed": True, "issues": [], "fixed_script": fixed}

    monkeypatch.setattr(generation_runtime, "generation_target", lambda: (
        SimpleNamespace(structured_completion=complete), LLMConfig(provider="gemini", model="test-model")))
    return calls


BRIEF_HI = ("Agent name is Meera. Company is Example Clinic. Answer questions about opening hours. "
            "Opening hours are 09:00 to 18:00. Do not offer bookings.")


@pytest.mark.asyncio
async def test_romanized_hindi_opening_gets_native_script_repair(monkeypatch):
    from server.brain.employee_script_pipeline import compile_employee_script
    native = "नमस्ते, मैं Example Clinic से Meera बोल रही हूँ। बताइए, कैसे मदद करूँ?"
    calls = _employee_fixture(monkeypatch, opening="Namaste, main Meera bol rahi hoon Example Clinic se.",
                              repaired_opening=native)
    _compiled, result = await compile_employee_script(brief=BRIEF_HI, language="hi-IN")
    assert native in result.agent_script
    assert calls.count("employee_script_review") == 2
    assert "Never do this: offer bookings." in result.agent_script
    assert "Permitted next steps" not in result.agent_script or "Answer questions about opening hours" in result.agent_script


@pytest.mark.asyncio
async def test_failed_native_repair_keeps_romanized_opening_instead_of_failing(monkeypatch):
    from server.brain.employee_script_pipeline import compile_employee_script
    romanized = "Namaste, main Meera bol rahi hoon Example Clinic se."
    _employee_fixture(monkeypatch, opening=romanized, repaired_opening="Namaste ji, Meera here from Example Clinic.")
    _compiled, result = await compile_employee_script(brief=BRIEF_HI, language="hi-IN")
    assert romanized in result.agent_script


@pytest.mark.asyncio
@pytest.mark.parametrize("third_reading,expected", [(True, "close"), (False, "continue")])
async def test_refusal_disagreement_is_broken_by_a_narrow_third_reading(monkeypatch, third_reading, expected):
    import json
    from server.call import close_classifier
    said = "మా roof మీద already solar ఉంది."

    def responder(system):
        if system.startswith("Understand telephone"):
            return json.dumps({"contact_action": "keep", "finish": False, "open_request": said})
        if system.startswith("Decide ONLY whether the caller's last turn rejects the WHOLE offer"):
            return json.dumps({"rejects_offer": third_reading, "evidence": said if third_reading else ""})
        return json.dumps({"decision": "close", "intent": "refusal", "reason": "refused", "explicit_end": False,
                           "evidence": said, "contact_intent": "none"})

    _registry(monkeypatch, responder)
    result = await close_classifier.classify_close_turn(
        transcript=said, agent_previous="ఇప్పుడు మాట్లాడటానికి time ఉందా?", language="te-IN", llm=_llm())
    assert result["decision"] == expected
    if expected == "close":
        assert result["reason"] == "not_interested" and result["contact_intent"] == "end_this_call"
        assert result["close_verified"] is True


@pytest.mark.asyncio
async def test_price_objection_never_reaches_the_refusal_tie_breaker(monkeypatch):
    import json
    from server.call import close_classifier
    asked = []

    def responder(system):
        asked.append(system[:40])
        if system.startswith("Understand telephone"):
            return json.dumps({"contact_action": "keep", "finish": False, "open_request": ""})
        return json.dumps({"decision": "continue", "intent": "other", "reason": "none"})

    _registry(monkeypatch, responder)
    result = await close_classifier.classify_close_turn(
        transcript="It is too expensive for me.", agent_previous="Is now a good time?", language="en-IN", llm=_llm())
    assert result["decision"] == "continue"
    assert not any(s.startswith("Decide ONLY whether the caller's last") for s in asked)


@pytest.mark.asyncio
async def test_placeholder_open_request_does_not_block_a_finish(monkeypatch):
    import json
    from server.call import close_classifier

    def responder(system):
        if system.startswith("Understand telephone"):
            return json.dumps({"contact_action": "keep", "finish": True, "finish_evidence": "That's all, bye",
                               "open_request": "none"})
        return json.dumps({"decision": "close", "reason": "goodbye", "explicit_end": True, "evidence": "That's all, bye"})

    _registry(monkeypatch, responder)
    result = await close_classifier.classify_close_turn(
        transcript="That's all, bye.", agent_previous="Anything else?", language="en-IN", llm=_llm())
    assert result["decision"] == "close" and result["remaining_request"] == ""


@pytest.mark.parametrize("text,claim", [
    ("Your details are noted, Kiran, and your free site survey in Velachery is booked for Saturday.", "appointment_confirmed"),
    ("Would you like to book the free site survey?", None),
    ("I have noted Saturday for the survey; the team will confirm it.", None),
    ("The free demo class is scheduled on Saturdays.", None),
])
def test_survey_booking_claim_needs_a_booking_proof(text, claim):
    from server.call.action_proof import unproven_claim
    assert unproven_claim(text, ["enquiry_saved"]) == claim


@pytest.mark.parametrize("language", ["en-IN", "hi-IN", "te-IN", "ta-IN", "kn-IN", "ml-IN", "gu-IN", "mr-IN", "bn-IN", "pa-IN"])
def test_callback_time_question_is_a_localized_question(language):
    from server.call.call_end_policy import callback_time_question_for
    from server.eval.conversation_sim.checks import check_reply
    line = callback_time_question_for(language)
    assert line.endswith("?")
    hard = check_reply(line, language=language, tts_provider="sarvam", tts_model="bulbul:v3").hard
    assert not [h for h in hard if h in {"wrong_indic_script", "no_native_script", "indic_script_in_english_call"}]


def test_orchestrator_asks_for_callback_time_only_when_reply_has_no_question():
    # The held-close time question moved into callback_close.callback_time_reply
    # (call 35002575 issue 8), which now also fixes the order: acknowledge, then ask.
    import inspect
    from server.call import callback_close, live_turn_orchestrator
    assert "callback_time_reply(ctx, raw_close, assistant_text, language_code)" in inspect.getsource(live_turn_orchestrator)
    source = inspect.getsource(callback_close.callback_time_reply)
    assert 'control.get("callback_time_needed")' in source and '"?" in text' in source


@pytest.mark.asyncio
async def test_native_repair_that_invents_a_number_is_not_used(monkeypatch):
    from server.brain.employee_script_pipeline import compile_employee_script
    romanized = "Namaste, main Meera bol rahi hoon Example Clinic se."
    _employee_fixture(monkeypatch, opening=romanized,
                      repaired_opening="नमस्ते, मैं Example Clinic से Meera, 24 घंटे आपकी सेवा में।")
    _compiled, result = await compile_employee_script(brief=BRIEF_HI, language="hi-IN")
    assert romanized in result.agent_script and "24 घंटे" not in result.agent_script


@pytest.mark.parametrize("opening,expected", [
    ("வணக்கம், I am Priya calling from SunPeak Solar. Am I speaking with the homeowner?", True),
    ("नमस्ते, मैं Arjun हूँ, एक AI support assistant. बताइए कैसे मदद करूँ?", False),
    ("Priya, SunPeak Solar.", False),
])
def test_mostly_english_indic_opening_needs_native_repair(opening, expected):
    from server.brain.employee_script_pipeline import _romanized_indic_opening
    language = "ta-IN" if "வ" in opening else "hi-IN"
    assert _romanized_indic_opening(opening, language, "", ("Priya", "SunPeak Solar", "Arjun")) is expected


@pytest.mark.parametrize("text,claim", [
    ("शनिवार को Velachery में आपका free site survey बुक कर दिया गया है।", "appointment_confirmed"),
    ("Velachery లో శనివారం ఉచిత సైట్ సర్వే బుక్ చేశాను.", "appointment_confirmed"),
    ("Survey बुक करवाना चाहें तो बताइए।", None),
    ("क्या हम आपके घर पर free site survey बुक कर सकते हैं?", None),
])
def test_code_mixed_booking_claims_are_caught(text, claim):
    from server.call.action_proof import unproven_claim
    assert unproven_claim(text, ["enquiry_saved"]) == claim


@pytest.mark.asyncio
@pytest.mark.parametrize("end_reason,model_disposition,expected", [
    ("not_interested", "new_lead", "not_interested"),
    ("not_interested", "site_visit_planned", "site_visit_planned"),
    ("goodbye", "new_lead", "new_lead"),
])
async def test_verified_refusal_close_sets_disposition(monkeypatch, tmp_path, end_reason, model_disposition, expected):
    from unittest.mock import AsyncMock
    from server.call import post_call_pipeline as pipeline
    from server.call.call_ledger import call_ledger
    from server.config.env import get_settings

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        call_id = f"refusal-{end_reason}-{model_disposition}"
        call_ledger.write_meta(call_id, {"direction": "outbound", "end_reason": end_reason})
        monkeypatch.setattr(pipeline, "_mark_outcome", AsyncMock())
        monkeypatch.setattr(pipeline.call_store, "update", AsyncMock())
        monkeypatch.setattr(pipeline, "_generate_outcome", AsyncMock(return_value=({
            "disposition": model_disposition, "summary_en": "Caller already has solar.", "extracted_fields": {},
        }, "ok")))
        result = await pipeline._run_outcome_locked(call_id)
        assert result["disposition"] == expected
    finally:
        get_settings.cache_clear()
