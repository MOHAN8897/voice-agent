"""F06: native selection first, typed proof before any action claim is spoken.

The 2026-10-25 audit showed Sarvam V1 returns zero native tool calls whenever
the full live-turn response schema is present. These tests pin the two-phase
contract, the typed proof carried into the speech phase, and the scoped
developer instruction that no longer asks course enquiries for a delivery
address.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.call import live_turn_orchestrator as module
from server.call.action_proof import (
    caller_requests_external_submission,
    claim_has_proof,
    proof_for_tool_result,
    replace_unavailable_action_promises,
    unavailable_action_line_for,
    unproven_claim,
)
from server.call.live_turn_schema import LIVE_TURN_JSON_SCHEMA
from server.providers.base import StageSelection
from server.services import tool_router
from server.services.saas import composed_costing

TOOL = {
    "type": "function",
    "name": "CRM_CREATE_ENQUIRY",
    "description": "Save an enquiry",
    "parameters": {
        "type": "object",
        "properties": {"customer_name": {"type": "string"}},
        "required": ["customer_name"],
    },
}
TOOL_CALL = {
    "id": "call-1",
    "type": "function",
    "function": {"name": "CRM_CREATE_ENQUIRY", "arguments": json.dumps({"customer_name": "Ravi"})},
}
END_CALL = {
    "decision": "continue",
    "reason": "none",
    "evidence": "",
    "remaining_request": "",
    "contact_preference": "none",
}


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(
            use_provider_registry=True,
            composed_first_attempt_max_tokens=1280,
            composed_retry_max_tokens=2560,
        ),
    )
    monkeypatch.setattr(composed_costing, "record_composed_stage_usage", lambda *args: None)


def _ctx():
    return SimpleNamespace(
        pipeline="composed_voice",
        tenant_id="tenant",
        agent_id="agent",
        call_id="call",
        callback_request_text="",
        resolved_stack=SimpleNamespace(
            llm=StageSelection(
                "sarvam", "sarvam-105b-conversations", {"api_mode": "chat_completions_v1"}
            )
        ),
    )


async def _run(monkeypatch, adapter, execute=None, tools=None):
    import server.providers

    registry = SimpleNamespace(
        get_llm=lambda _provider: adapter,
        is_provider_enabled=lambda *_args: True,
        is_model_allowed=lambda *_args: True,
    )
    monkeypatch.setattr(server.providers, "get_provider_registry", lambda: registry)
    orchestrator = module.LiveTurnOrchestrator()
    monkeypatch.setattr(
        orchestrator, "_load_composed_tenant_tools", AsyncMock(return_value=[TOOL] if tools is None else tools)
    )
    if execute is not None:
        monkeypatch.setattr(
            orchestrator, "_execute_composed_tools", AsyncMock(side_effect=execute)
        )
    events = [
        event
        async for event in orchestrator._stream_llm(
            ctx=_ctx(),
            call_id="call",
            transcript="Please save my enquiry",
            input_messages=[{"role": "user", "content": "Please save my enquiry"}],
        )
    ]
    return events


class SelectingAdapter:
    provider_id = "sarvam"
    selects_tools_without_schema = True

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def stream_live_turn(self, **kwargs):
        self.calls.append(("select", kwargs))
        yield {"delta": "SELECTION PROSE THAT MUST NOT BE SPOKEN"}
        yield {
            "done": True,
            "text": "SELECTION PROSE THAT MUST NOT BE SPOKEN",
            "tool_calls": [TOOL_CALL],
        }

    async def stream_structured_turn(self, **kwargs):
        self.calls.append(("speech", kwargs))
        yield {"delta": "Saved your enquiry."}
        yield {
            "done": True,
            "text": "Saved your enquiry.",
            "end_call": END_CALL,
            "action_claimed": "enquiry_saved",
        }


class NoSelectionAdapter(SelectingAdapter):
    async def stream_live_turn(self, **kwargs):
        self.calls.append(("select", kwargs))
        yield {"done": True, "text": ""}


class PlainSpeechAdapter(SelectingAdapter):
    uses_plain_live_speech = True

    async def stream_live_turn(self, **kwargs):
        if kwargs.get("tool_choice") == "auto":
            self.calls.append(("select", kwargs))
            yield {"done": True, "text": "", "tool_calls": [TOOL_CALL]}
        else:
            self.calls.append(("speech", kwargs))
            yield {"delta": "The service costs 499 rupees."}
            yield {"done": True, "text": "The service costs 499 rupees."}

    async def stream_structured_turn(self, **kwargs):
        raise AssertionError("The audited model must not be forced into the unstable live JSON contract")
        yield  # pragma: no cover


@pytest.mark.asyncio
@pytest.mark.parametrize("connected", [False, True])
async def test_native_speech_preserves_selected_model_and_post_tool_proof(monkeypatch, connected):
    adapter = PlainSpeechAdapter()

    async def execute(**kwargs):
        kwargs["turn_state"]["action_proofs"] = {"enquiry_saved"}
        return list(kwargs["messages"])

    events = await _run(monkeypatch, adapter, execute=execute, tools=[TOOL] if connected else [])
    speech = adapter.calls[-1][1]
    assert speech["schema"] is None
    assert speech["model"] == "sarvam-105b-conversations"
    assert speech["api_mode"] == "chat_completions_v1"
    assert speech["speech_only"] is True
    assert speech["buffer_response"] is True
    assert any("Speech delivery contract" in str(m.get("content")) for m in speech["input_messages"])
    if not connected:
        assert any("No external action tools are connected" in str(m.get("content")) for m in speech["input_messages"])
    done = next(event for event in events if event.get("done"))
    assert done["text"] == "The service costs 499 rupees."
    assert done.get("action_proofs", []) == (["enquiry_saved"] if connected else [])
    if connected:
        assert [kind for kind, _ in adapter.calls] == ["select", "speech"]
        assert speech["tool_choice"] == "none"


@pytest.mark.asyncio
async def test_unconfirmed_tool_outcome_reaches_the_native_delivery_guard(monkeypatch):
    async def execute(**kwargs):
        kwargs["turn_state"]["action_outcome_unconfirmed"] = True
        return list(kwargs["messages"])

    events = await _run(monkeypatch, PlainSpeechAdapter(), execute=execute, tools=[TOOL])
    done = next(event for event in events if event.get("done"))
    assert done["action_outcome_unconfirmed"] is True
    assert done["action_proofs"] == []


@pytest.mark.asyncio
async def test_sarvam_selects_without_schema_then_speaks_with_typed_proof(monkeypatch):
    adapter = SelectingAdapter()

    async def execute(**kwargs):
        kwargs["turn_state"]["action_proofs"] = {"enquiry_saved"}
        return list(kwargs["messages"])

    events = await _run(monkeypatch, adapter, execute=execute)

    assert [kind for kind, _ in adapter.calls] == ["select", "speech"]
    selection = adapter.calls[0][1]
    assert selection["schema"] is None
    assert selection["tools"] == [TOOL]
    assert selection["tool_choice"] == "auto"
    speech = adapter.calls[1][1]
    assert speech["tools"] == [TOOL]
    assert speech["tool_choice"] == "none"
    assert "SELECTION PROSE" not in "".join(str(event.get("delta") or "") for event in events)
    done = next(event for event in events if event.get("done"))
    assert done["text"] == "Saved your enquiry."
    assert done["action_proofs"] == ["enquiry_saved"]
    assert done["order_proof"] is False


@pytest.mark.asyncio
async def test_no_selected_action_still_produces_a_validated_speech_turn(monkeypatch):
    adapter = NoSelectionAdapter()
    events = await _run(monkeypatch, adapter)

    assert [kind for kind, _ in adapter.calls] == ["select", "speech"]
    assert adapter.calls[0][1]["schema"] is None
    assert "tools" not in adapter.calls[1][1]
    assert adapter.calls[1][1]["schema"] is LIVE_TURN_JSON_SCHEMA
    done = next(event for event in events if event.get("done"))
    assert done["action_proofs"] == []
    assert done["order_proof"] is False


@pytest.mark.asyncio
async def test_completed_native_selection_marks_progress_before_second_request(monkeypatch):
    events = await _run(monkeypatch, NoSelectionAdapter())
    # Otherwise the PSTN first-reply watchdog can cancel/re-ask the caller
    # between two healthy provider requests, before speech validation starts.
    assert events[0] == {"status": "reply_buffered"}


@pytest.mark.asyncio
async def test_authorized_tool_result_becomes_a_typed_proof_and_scoped_instruction(monkeypatch):
    gateway = AsyncMock(return_value={"status": "success", "id": "enquiry-1"})
    monkeypatch.setattr(tool_router.tool_router, "route_and_execute", gateway)
    orchestrator = module.LiveTurnOrchestrator()
    ctx = SimpleNamespace(tenant_id="tenant", agent_id="agent", call_id="call")
    turn_state: dict = {}
    output = await orchestrator._execute_composed_tools(
        ctx=ctx,
        messages=[{"role": "user", "content": "Please save my enquiry"}],
        tool_calls=[TOOL_CALL],
        allowed_tools={"CRM_CREATE_ENQUIRY"},
        turn_state=turn_state,
    )
    assert turn_state["action_proofs"] == {"enquiry_saved"}
    developer = next(message for message in output if message["role"] == "developer")
    assert "enquiry_saved" in developer["content"]
    # A course/enquiry workflow must never be asked for a delivery address.
    assert "delivery address" not in developer["content"]
    gateway.assert_awaited_once_with(
        tenant_id="tenant",
        agent_id="agent",
        call_id="call",
        tool_name="CRM_CREATE_ENQUIRY",
        arguments={"customer_name": "Ravi"},
        timing="in_call",
    )


@pytest.mark.asyncio
async def test_denied_or_uncertain_action_proves_nothing(monkeypatch):
    gateway = AsyncMock(return_value={"status": "unknown"})
    monkeypatch.setattr(tool_router.tool_router, "route_and_execute", gateway)
    orchestrator = module.LiveTurnOrchestrator()
    ctx = SimpleNamespace(tenant_id="tenant", agent_id="agent", call_id="call")
    turn_state: dict = {}
    output = await orchestrator._execute_composed_tools(
        ctx=ctx,
        messages=[],
        tool_calls=[TOOL_CALL],
        allowed_tools={"SOME_OTHER_TOOL"},
        turn_state=turn_state,
    )
    assert not turn_state.get("action_proofs")
    assert turn_state["action_outcome_unconfirmed"] is True
    developer = next(message for message in output if message["role"] == "developer")
    assert "No action was completed" in developer["content"]
    gateway.assert_not_awaited()


def test_typed_claims_require_the_matching_proof():
    assert proof_for_tool_result("CRM_CREATE_ENQUIRY", {"status": "success"}) == "enquiry_saved"
    assert (
        proof_for_tool_result("GOOGLECALENDAR_CREATE_EVENT", {"status": "success", "confirmed": False})
        == "appointment_requested"
    )
    assert (
        proof_for_tool_result("GOOGLECALENDAR_CREATE_EVENT", {"status": "success"})
        == "appointment_confirmed"
    )
    assert proof_for_tool_result("CRM_CREATE_ENQUIRY", {"status": "error"}) is None
    assert proof_for_tool_result("SOME_READ_TOOL", {"status": "success"}) is None
    assert claim_has_proof("enquiry_saved", {"appointment_requested"})
    assert not claim_has_proof("appointment_confirmed", {"appointment_requested"})
    assert unproven_claim("Your appointment is confirmed.", {"appointment_requested"}) == (
        "appointment_confirmed"
    )
    assert unproven_claim("I have noted your enquiry.", {"enquiry_saved"}) is None


@pytest.mark.parametrize("language,promise", [
    ("en-IN", "I will submit your enquiry for team review."),
    ("te-IN", "ఈ enquiry ని మా team review కోసం save చేస్తాము, కానీ booking confirm కాదు."),
    ("hi-IN", "Enquiry save करने से पहले, क्या आप अपना नाम बताएंगे?"),
    ("ta-IN", "உங்க enquiry-யை team review-க்காக submit பண்றேன்."),
    ("kn-IN", "ನಾನು ಈ enquiry-ನ ನಮ್ಮ ತಂಡದ review-ಗೆ ಕಳಿಸ್ತೀನಿ."),
])
def test_disconnected_action_promises_are_replaced_without_losing_price(language,promise):
    text="The fee is 6499 rupees. "+promise
    result=replace_unavailable_action_promises(text,language)
    assert "The fee is 6499 rupees." in result
    assert promise not in result


@pytest.mark.parametrize("language,text", [
    ("en-IN", "I can note your details in this call. I cannot submit this enquiry externally."),
    ("te-IN", "నేను team కి ఈ enquiry submit చేయలేను."),
    ("hi-IN", "मेरे पास enquiry save करने की सुविधा नहीं है।"),
    ("ta-IN", "என்னால enquiry-யை team-க்கு அனுப்ப முடியாதுங்க."),
    ("kn-IN", "ನನಗೆ ಈ request team ಗೆ submit ಮಾಡಲು ಸಾಧ್ಯವಿಲ್ಲ."),
])
def test_disconnected_boundary_preserves_honest_limitations(language,text):
    assert replace_unavailable_action_promises(text,language)==text


@pytest.mark.parametrize("language,text", [
    ("en-IN", "Our team will contact you soon."),
    ("te-IN", "మా team వైపు నుండి మీకు త్వరలో update వస్తుంది."),
    ("ta-IN", "உங்க request-க்காக நாளைக்கு ஒரு callback ஏற்பாடு பண்ணட்டுமா?"),
    ("kn-IN", "ನಮ್ಮ team ಇಂದ ನಿಮಗೆ direct ಆಗಿ contact ಮಾಡ್ತಾರೆ."),
    ("kn-IN", "ನಮ್ಮ team ಇದರ ಬಗ್ಗೆ check ಮಾಡ್ತಾರೆ."),
])
def test_unverified_write_cannot_imply_a_later_callback_or_manual_review(language,text):
    assert replace_unavailable_action_promises(text,language,unconfirmed=True)!=text


@pytest.mark.parametrize("language", ["en-IN","te-IN","hi-IN","ta-IN","kn-IN"])
def test_authoritative_unavailable_boundary_never_claims_a_completed_action(language):
    assert unproven_claim(unavailable_action_line_for(language),set()) is None


def test_unconfirmed_outcome_has_no_unexecuted_next_step_in_any_paraphrase():
    text = "The fee is 6499 rupees. They will sort it out. Please try submitting again later."
    out=replace_unavailable_action_promises(text,"en-IN",unconfirmed=True)
    assert "6499 rupees" in out
    assert "They will" not in out
    assert "again later" not in out


@pytest.mark.parametrize("text", [
    "Please submit this enquiry for team review. Do not claim a booking is confirmed.",
    "ఈ enquiry ని team review కోసం submit చేయండి. Booking confirm అని చెప్పకండి.",
    "यह enquiry team review के लिए submit कीजिए। Booking confirm मत बताइए।",
    "இந்த enquiry-யை team reviewக்கு submit செய்யுங்க. Booking confirmன்னு சொல்லாதீங்க.",
    "ಈ enquiry team reviewಗೆ submit ಮಾಡಿ. Booking confirm ಅಂತ ಹೇಳಬೇಡಿ.",
])
def test_explicit_submission_request_has_a_deterministic_capability_boundary(text):
    assert caller_requests_external_submission(text)


@pytest.mark.parametrize("text", [
    "Do not save my enquiry. What is the price?",
    "నా enquiry save చేయకండి. ధర ఎంత?",
    "मेरी enquiry save मत कीजिए। कीमत क्या है?",
    "என் enquiry save செய்யாதீங்க. விலை என்ன?",
    "ನನ್ನ enquiry save ಮಾಡಬೇಡಿ. ಬೆಲೆ ಎಷ್ಟು?",
])
def test_no_save_instruction_does_not_become_a_submission_request(text):
    assert not caller_requests_external_submission(text)


def test_negated_claims_and_ordinary_answers_are_not_action_claims():
    # Observed in the 2026-10-25 Standard rerun: an honest saved-enquiry reply
    # that also said "this is not a confirmed order or booking" was replaced.
    proven = {"enquiry_saved"}
    assert (
        unproven_claim(
            "Your enquiry is saved with reference AUDIT-ENQUIRY-1. The team will "
            "review it, but this is not a confirmed order or booking.",
            proven,
        )
        is None
    )
    assert unproven_claim("This is not a confirmed order or booking.", set()) is None
    assert unproven_claim("Your order is not confirmed yet.", set()) is None
    assert unproven_claim("I have not saved your details.", set()) is None
    assert unproven_claim("There is no placement guarantee.", set()) is None
    assert unproven_claim("Your order is confirmed.", set()) == "order_confirmed"


@pytest.mark.parametrize("text", [
    "This isn't a confirmed booking.",
    "यह कोई confirmed booking या order नहीं है।",
    "Yeh koi confirmed slot ya paid order nahi hai.",
    "ಇದು confirmed visit ಅಲ್ಲ, ಬರೀ enquiry ಅಷ್ಟೇ.",
    "ಇದು confirmed booking ಅಥವಾ paid order ಅಲ್ಲ.",
    "இது ஒரு confirmed visit இல்ல, வெறும் enquiry தான்.",
    "இது ஒரு confirmed slot கிடையாதுங்க, வெறும் enquiry தான்.",
])
def test_postposed_and_mixed_language_negations_preserve_proven_enquiry(text):
    assert unproven_claim(text, {"enquiry_saved"}) is None


@pytest.mark.parametrize("text,claim", [
    ("Your order is confirmed with no refund.", "order_confirmed"),
    ("Your appointment is confirmed, but payment is not done.", "appointment_confirmed"),
    ("There is no guarantee. Your order is confirmed.", "order_confirmed"),
    ("No refund, but your order is confirmed.", "order_confirmed"),
    ("Your order is confirmed and not refundable.", "order_confirmed"),
    ("Your order is confirmed. Booking is not confirmed.", "order_confirmed"),
])
def test_negation_of_other_properties_never_authorizes_a_claim(text,claim):
    assert unproven_claim(text, set()) == claim


def test_recorded_claim_replacement_keeps_the_rest_of_the_answer():
    from server.call.action_proof import replace_unproven_claims

    text = "Your enquiry is saved. The fee is 4999 rupees for six weeks."
    out = replace_unproven_claims(text, set(), "en-IN")
    assert "Your enquiry is saved" not in out
    assert "4999 rupees for six weeks" in out
    assert "couldn't confirm" in out
    # With proof the same words stay untouched.
    assert replace_unproven_claims(text, {"enquiry_saved"}, "en-IN") == text


def test_all_unproven_recorded_claims_are_removed_without_losing_separate_answers():
    from server.call.action_proof import replace_unproven_claims

    text = "The fee is 499 rupees. Your enquiry is saved. Your details are submitted."
    out = replace_unproven_claims(text, set(), "en-IN")
    assert "The fee is 499 rupees." in out
    assert "enquiry is saved" not in out
    assert "details are submitted" not in out
    assert unproven_claim(out, set()) is None
