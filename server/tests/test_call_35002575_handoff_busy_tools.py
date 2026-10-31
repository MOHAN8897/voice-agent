"""Call 35002575: person handoff (3), busy callers (8), plain fixed lines (9), unused tools (10)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import JSON, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.brain.capabilities import (
    apply_available_tools,
    authored_business_text,
    script_uses_scheduling,
    tools_used_by_script,
)
from server.call import call_context
from server.call.action_proof import (
    PROOF_ENQUIRY_SAVED,
    action_unconfirmed_line_for,
    proof_for_tool_result,
    replace_unavailable_action_promises,
    unproven_claim,
)
from server.call.call_end_policy import (
    callback_acknowledgement_for,
    callback_save_failed_for,
    callback_time_question_for,
    callback_time_reply_for,
    handoff_acknowledgement_for,
    server_farewell_for,
)
from server.call.callback_close import advance_callback_close, callback_time_reply, extract_callback_when
from server.call.enquiry import PLATFORM_ACTIONS, execute_platform_action
from server.call.human_handoff import (
    REQUEST_HUMAN_HANDOFF_TOOL,
    handoff_details,
    handoff_facts,
    is_handoff_key,
)
from server.db.models.entities import Call, CallCallback
from server.db.models.followup_models import FollowUpJob
from server.services.saas import callback_request_service as svc
from server.services.saas.tenant_guard import SubscriberPrincipal
from server.services.tool_schema_registry import get_tools_for_tenant, tool_definition, validate_tool_arguments

LANGUAGES = ("en-IN", "te-IN", "hi-IN", "ta-IN", "kn-IN", "ml-IN", "gu-IN", "mr-IN", "bn-IN", "pa-IN")
CALL_DIR = Path(__file__).resolve().parents[2] / "data" / "calls" / "35002575-2555-4b96-9058-6d345942a13d"


# --- Issue 3: a request for a person from the business ---------------------------------

def test_handoff_is_a_platform_action_with_a_validated_schema():
    assert "REQUEST_HUMAN_HANDOFF" in PLATFORM_ACTIONS
    assert tool_definition("request_human_handoff") == ("PLATFORM", REQUEST_HUMAN_HANDOFF_TOOL)
    assert validate_tool_arguments("REQUEST_HUMAN_HANDOFF", {
        "contact_role": "manager", "caller_words": "మీ మేనేజర్ కి చెప్పండి నా కాల్ బ్యాక్ చేయమని"}) is None
    assert validate_tool_arguments("REQUEST_HUMAN_HANDOFF", {"contact_role": "boss", "caller_words": "x"})
    assert validate_tool_arguments("REQUEST_HUMAN_HANDOFF", {"contact_role": "owner"})


def test_handoff_details_normalise_and_reject_unusable_requests():
    assert handoff_details({"contact_role": "owner", "caller_words": "  ask the owner to call  ",
                            "reason": "bulk discount"}) == {
        "contactRole": "owner", "callerWords": "ask the owner to call", "reason": "bulk discount"}
    # A "named person" without a name is a request for anyone from the business.
    assert handoff_details({"contact_role": "named_person", "caller_words": "x"})["contactRole"] == "any_person"
    assert handoff_details({"contact_role": "manager"}) is None
    assert handoff_details({"contact_role": "manager", "caller_words": "x", "extra": "y"}) is None
    assert handoff_details({"contact_role": "manager", "caller_words": 5}) is None


def test_handoff_result_proves_a_recorded_request_and_its_acknowledgement_survives_the_gate():
    assert proof_for_tool_result("REQUEST_HUMAN_HANDOFF", {"status": "ok"}) == PROOF_ENQUIRY_SAVED
    assert proof_for_tool_result("REQUEST_HUMAN_HANDOFF", {"status": "error"}) is None
    for language in LANGUAGES:
        line = handoff_acknowledgement_for(language)
        assert "connect" not in line.casefold()
        kept = replace_unavailable_action_promises(line, language, saved_request=True)
        assert line in kept, language
    # Without a saved request the same promise is still replaced by the honest limitation.
    assert handoff_acknowledgement_for("en-IN") not in replace_unavailable_action_promises(
        handoff_acknowledgement_for("en-IN"), "en-IN", saved_request=False, requested_unavailable=True)


def test_capabilities_tell_the_agent_to_pass_the_request_on_instead_of_refusing():
    text = apply_available_tools("--- CALL CAPABILITIES ---\nold\n", [REQUEST_HUMAN_HANDOFF_TOOL])
    assert "You cannot transfer this call" in text and "REQUEST_HUMAN_HANDOFF" in text
    assert "REQUEST_HUMAN_HANDOFF" not in apply_available_tools("--- CALL CAPABILITIES ---\nold\n", [])


@pytest.fixture
async def handoff_db(monkeypatch, tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'handoff.db'}")
    # SQLite test adapter only; production uses the existing PostgreSQL tables.
    columns = [c for table in (Call.__table__, CallCallback.__table__) for c in table.columns if isinstance(c.type, ARRAY)]
    original = [c.type for c in columns]
    for c in columns:
        c.type = JSON()
    try:
        async with engine.begin() as conn:
            for table in (Call.__table__, CallCallback.__table__, FollowUpJob.__table__):
                await conn.run_sync(lambda sync, t=table: t.create(sync))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(svc, "get_session_factory", lambda: factory)
        principal = SubscriberPrincipal(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role="customer_admin",
                                        email="test@example.invalid")
        ctx = SimpleNamespace(call_id=str(uuid.uuid4()), tenant_id=str(principal.tenant_id), agent_id=str(uuid.uuid4()),
                              callback_phone="+919000000001", callback_when="", callback_request_text="",
                              status="active", resolved_stack=SimpleNamespace(language="te-IN"),
                              call_end_policy=None)
        async with factory() as session:
            session.add(Call(call_id=uuid.UUID(ctx.call_id), tenant_id=principal.tenant_id,
                             agent_id=uuid.UUID(ctx.agent_id), combination_id="test", storage_path="test", status_tags=[]))
            await session.commit()
        yield factory, principal, ctx
    finally:
        await engine.dispose()
        for c, original_type in zip(columns, original):
            c.type = original_type


async def test_handoff_is_saved_as_its_own_task_never_queued_for_an_agent_dial(handoff_db, monkeypatch):
    factory, principal, ctx = handoff_db
    monkeypatch.setattr(call_context, "get", lambda call_id: ctx if call_id == ctx.call_id else None)
    result = await execute_platform_action(
        "REQUEST_HUMAN_HANDOFF", call_id=ctx.call_id, tenant_id=ctx.tenant_id, agent_id=ctx.agent_id,
        arguments={"contact_role": "manager", "reason": "bulk discount on 500 cards",
                   "caller_words": "మీ మేనేజర్ కి చెప్పండి నా కాల్ బ్యాక్ చేయమని"})
    assert result["status"] == "ok" and result["handoff_saved"] is True
    assert result["say"] == handoff_acknowledgement_for("te-IN")
    async with factory() as session:
        rows = (await session.scalars(select(CallCallback))).all()
        assert len(rows) == 1 and is_handoff_key(rows[0].dial_request_id)
        assert (await session.scalars(select(FollowUpJob))).all() == []
    [item] = await svc.list_callback_requests(principal, agent_id=ctx.agent_id)
    assert item["kind"] == "human_handoff"
    assert item["handoff"]["contactLabel"] == "Manager" and item["handoff"]["reason"].startswith("bulk")
    assert item["requestText"].startswith("మీ మేనేజర్")

    # The later busy / call-me-later close adds its time to the same task.
    ctx.callback_when, ctx.callback_request_text = "రేపు ఈవెనింగ్", "రేపు ఈవెనింగ్ కాల్ చేయండి."
    closed = await svc.prepare_callback_close(ctx, {"should_end": True, "contact_preference": "callback"},
                                              "te-IN", ctx.callback_request_text)
    assert closed["farewell"].startswith(callback_acknowledgement_for("te-IN"))
    async with factory() as session:
        assert len((await session.scalars(select(CallCallback))).all()) == 1
    [item] = await svc.list_callback_requests(principal, agent_id=ctx.agent_id)
    assert item["requestedWhen"] == "రేపు ఈవెనింగ్" and item["handoff"]["reason"].startswith("bulk")


async def test_invalid_handoff_is_reported_as_not_saved(handoff_db, monkeypatch):
    _, principal, ctx = handoff_db
    monkeypatch.setattr(call_context, "get", lambda call_id: ctx)
    result = await execute_platform_action("REQUEST_HUMAN_HANDOFF", call_id=ctx.call_id, tenant_id=ctx.tenant_id,
                                           agent_id=ctx.agent_id, arguments={"contact_role": "manager"})
    assert result["status"] == "error"
    assert await svc.list_callback_requests(principal) == []


def test_activity_feed_shows_the_handoff_distinctly():
    from server.services.saas.activity_feed_service import _callback_item

    row = SimpleNamespace(status="requested", original_call_id=uuid.uuid4(), to_e164="+919000000001",
                          callback_id=uuid.uuid4(), created_at=datetime.now(timezone.utc), agent_id="a",
                          dial_request_id="handoff:x", original_attempt_id=None)
    assert "person from the business" in _callback_item(row, {})["text"]
    row.dial_request_id = "requested:x"
    assert "asked for a callback" in _callback_item(row, {})["text"]
    facts = handoff_facts({"human_handoff": {"contactRole": "named_person", "contactName": "Ravi",
                                             "reason": "price", "callerWords": "ask Ravi"}})
    assert facts["handoffTo"] == "Ravi" and facts["requestText"] == "ask Ravi"


# --- Issue 8: busy callers -----------------------------------------------------------------

@pytest.mark.parametrize("language", LANGUAGES)
def test_busy_reply_is_a_short_acknowledgement_then_one_time_question(language):
    reply = callback_time_reply_for(language)
    assert reply.endswith(callback_time_question_for(language)) and reply.count("?") == 1
    ack = reply[: -len(callback_time_question_for(language))].strip()
    assert 0 < len(ack.split()) <= 5


def test_callback_without_time_gets_the_server_order_once():
    ctx = SimpleNamespace(callback_when="", callback_time_prompted=False)
    control = {"decision": "continue", "contact_intent": "callback", "contact_verified": True, "callback_time": ""}
    model_text = "సరే, అర్థమైంది. మీరు తర్వాత free ఉన్నప్పుడు call చేయమని చెప్పండి, నేను note చేసుకుంటాను."
    assert callback_time_reply(ctx, control, model_text, "te-IN") == callback_time_reply_for("te-IN")
    assert ctx.callback_time_prompted is True
    # Asked once: the caller's next answer (even a vague one) is accepted, not re-asked.
    assert callback_time_reply(ctx, control, model_text, "te-IN") is None


def test_callback_time_reply_leaves_timed_or_unrelated_turns_alone():
    fresh = lambda: SimpleNamespace(callback_when="", callback_time_prompted=False)  # noqa: E731
    timed = {"decision": "close", "contact_intent": "callback", "contact_verified": True, "callback_time": "tomorrow"}
    assert callback_time_reply(fresh(), timed, "ok", "en-IN") is None
    assert callback_time_reply(fresh(), {"decision": "continue", "contact_intent": "none"}, "ok", "en-IN") is None
    assert callback_time_reply(fresh(), None, "ok", "en-IN") is None
    asked = {"contact_intent": "callback", "contact_verified": True, "agent_asked_time": True}
    assert callback_time_reply(fresh(), asked, "ok", "en-IN") is None
    known = SimpleNamespace(callback_when="evening", callback_time_prompted=False)
    assert callback_time_reply(known, {"contact_intent": "callback", "contact_verified": True}, "ok", "en-IN") is None


def test_held_close_with_an_open_question_keeps_the_answer_and_adds_the_question():
    ctx = SimpleNamespace(callback_when="", callback_time_prompted=True)
    control = {"callback_time_needed": True, "remaining_request": "price of icards"}
    reply = callback_time_reply(ctx, control, "Icards are 30 rupees each.", "en-IN")
    assert reply == f"Icards are 30 rupees each. {callback_time_question_for('en-IN')}"
    assert callback_time_reply(ctx, {"callback_time_needed": True}, "Sure, I'll note it.", "hi-IN") == \
        callback_time_reply_for("hi-IN")


def test_regex_path_asks_for_the_time_before_allowing_the_close():
    ctx = SimpleNamespace(callback_close_phase="idle", callback_request_text="", callback_name="", callback_phone="",
                          callback_when="", callback_time_prompted=False)
    first = advance_callback_close(ctx, "I'm busy, call me later", None)
    assert first.missing == "timing" and "ask only when to call" in first.hint
    second = advance_callback_close(ctx, "hmm", None)
    assert second.missing is None and second.phase == "closing_allowed"


@pytest.mark.parametrize("text", ["రేపు ఈవెనింగ్ కాల్ చేయండి.", "कल शाम को कॉल करना", "நாளை மாலை அழைங்க", "call me at 5 pm"])
def test_callback_time_is_extracted_in_every_script(text):
    assert extract_callback_when(text)


# --- Issue 9: plain spoken lines ---------------------------------------------------------

_BOOKISH = ("అభ్యర్థన", "నమోదు", "అనురోధ", "अनुरोध", "दर्ज", "கோரிக்கை", "ವಿನಂತಿ", "ದಾಖಲಿ", "അഭ്യർത്ഥന",
            "രേഖപ്പെടുത്ത", "વિનંતી", "विनंती", "অনুরোধ", "ਬੇਨਤੀ", "ਦਰਜ", "నిర్ధారణ", "व्यवसाय", "సంస్థ")


@pytest.mark.parametrize("language", LANGUAGES)
def test_fixed_lines_are_everyday_speech_and_keep_their_meaning(language):
    lines = (callback_acknowledgement_for(language), callback_save_failed_for(language),
             handoff_acknowledgement_for(language), action_unconfirmed_line_for(language))
    for line in lines:
        assert line and not [word for word in _BOOKISH if word in line], (language, line)
    # Meaning anchors: the confirmation names the callback, the failure says it was not saved.
    assert "callback" in callback_acknowledgement_for(language).casefold()
    assert "callback" in callback_save_failed_for(language).casefold()
    # A fixed warning line must never itself read as an unproven action claim.
    assert unproven_claim(action_unconfirmed_line_for(language), set()) is None
    assert server_farewell_for(language, contact_preference="callback").startswith(callback_acknowledgement_for(language))


def test_telugu_callback_confirmation_matches_the_reviewed_wording():
    assert callback_acknowledgement_for("te-IN") == "సరే, మీ callback note చేసుకున్నాను."


# --- Issue 10: only tools the agent's own workflow uses ----------------------------------

def _brain(script: str, *, role: str = "sales", platform: str = "") -> str:
    return (
        "--- SAFETY ---\nbe safe\n--- CALLING SCRIPT ---\n--- ENTITY TAGS ---\n"
        f"@role: {role}\n@language: te-IN\n\n--- COMPANY & OFFER ---\n{script}\n"
        "--- SPOKEN LANGUAGE (te-IN) ---\nUse words like `booking`, `schedule`, `time`. "
        f"Example: `Booking కావాలంటే చెప్పండి.`\n{platform}\n"
        "--- GUARDRAILS ---\n- -- LEAD CAPTURE ---\n- Ask for scheduling details only when required.\n"
        "--- CALL CAPABILITIES ---\nx\n"
    )


SALES = "Digital visiting cards are 25 rupees each and are delivered by post. Note the buyer's name, address and quantity."


def test_platform_wording_is_not_evidence_that_the_business_schedules():
    brain = _brain(SALES)
    assert "booking" not in authored_business_text(brain).casefold()
    assert script_uses_scheduling(brain) is False


@pytest.mark.parametrize("script", [
    "Offer the caller a free site visit and book a slot that suits them.",
    "కాలర్ కి డెమో కోసం అపాయింట్‌మెంట్ బుక్ చేయండి. Visiting hours are 10 to 6.",
    "ग्राहक के लिए अपॉइंटमेंट बुक करें और समय पक्का करें।",
    "வாடிக்கையாளருக்கு அப்பாயின்ட்மென்ட் புக் பண்ணுங்க, நேரம் உறுதி செய்யுங்க.",
])
def test_a_script_that_books_keeps_its_calendar_tools(script):
    brain = _brain(script)
    assert script_uses_scheduling(brain) is True
    tools = get_tools_for_tenant(["GOOGLECALENDAR", "HUBSPOT"])
    assert tools_used_by_script(tools, brain) == tools


def test_unused_calendar_tools_are_dropped_and_other_tools_kept():
    tools = get_tools_for_tenant(["GOOGLECALENDAR", "CALENDLY", "HUBSPOT"])
    kept = [t["name"] for t in tools_used_by_script(tools, _brain(SALES))]
    assert kept and all(name.startswith("HUBSPOT_") for name in kept)


def test_unjudgeable_scripts_and_appointment_roles_keep_every_tool():
    tools = get_tools_for_tenant(["CALENDLY"])
    assert tools_used_by_script(tools, "no sections at all, just prose") == tools
    assert tools_used_by_script(tools, _brain("Short.")) == tools
    assert script_uses_scheduling(_brain(SALES, role="appointment")) is True


@pytest.mark.skipif(not (CALL_DIR / "meta.json").exists(), reason="call evidence not present")
def test_call_35002575_brain_drops_its_ten_calendar_schemas():
    brain = json.loads((CALL_DIR / "meta.json").read_text(encoding="utf-8"))["compiled_brain_text"]
    tools = get_tools_for_tenant(["GOOGLECALENDAR", "CALENDLY"])
    assert len(tools) == 10
    assert tools_used_by_script(tools, brain) == []
