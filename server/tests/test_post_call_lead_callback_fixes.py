"""Call review 35002575: summary direction/language, lead progress, callback clamp, opening line, warnings.

Every case is tenant- and language-agnostic: Telugu, Hindi and English inputs run
through the same structural checks.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from server.call import post_call_pipeline as pcp
from server.call.call_ledger import call_ledger
from server.call.callback_day_parts import clamp_to_calling_window, resolve_callback_window
from server.call.memory_manager import memory_manager
from server.call.outcome_schema import OUTCOME_JSON_SCHEMA, derive_status_tags, normalize_unanswered_questions
from server.config.env import get_settings
from server.db.models.entities import CallCallback
from server.db.models.followup_models import FollowUpJob
from server.db.models.saas_models import Lead
from server.services.saas import followup_service as svc
from server.services.saas import lead_sync
from server.services.saas.agent_call_warnings import summarize_outcomes
from server.services.saas.followup_policy import FollowUpConfig
from server.services.saas.lead_scoring import score_outcome
from server.tests.test_durable_followups import enable, queue  # noqa: F401 -- shared sqlite fixture

IST = ZoneInfo("Asia/Kolkata")
ASKED_AT = datetime(2026, 10, 30, 18, 13, 49, tzinfo=timezone.utc)
EXPECTED = datetime(2026, 10, 31, 17, 0, tzinfo=IST)
TOMORROW_EVENING = [
    "రేపు ఈవెనింగ్ కాల్ చేయండి.",
    "कल शाम को कॉल कीजिए।",
    "Call me tomorrow evening.",
]


# --- Issue 11: summary direction and call-language summary ---------------------------

OUTBOUND_TE = {"direction": "outbound", "language": "te-IN"}


def test_summary_prompt_states_direction_and_language():
    header = pcp._call_header(OUTBOUND_TE)
    assert "outbound" in header and "you called them" in header and "Telugu" in header
    assert "they called you" in pcp._call_header({"direction": "inbound", "language": "hi-IN"})


@pytest.mark.parametrize("meta,summary,wrong", [
    ({"direction": "outbound"}, "The caller initiated the call to ask about cards.", True),
    ({"direction": "outbound"}, "The agent called the customer about cards.", False),
    ({"direction": "inbound"}, "The agent called the customer about cards.", True),
    ({"direction": "inbound"}, "The caller initiated the call to ask about cards.", False),
])
def test_wrong_direction_is_detected(meta, summary, wrong):
    assert ("wrong_direction" in pcp.summary_problems({"summary_en": summary}, meta)) is wrong


@pytest.mark.parametrize("language,local,missing", [
    ("te-IN", "", True),
    ("te-IN", "Customer wants 500 cards.", True),  # English wearing the Telugu label
    ("te-IN", "కస్టమర్ 500 కార్డులు కావాలన్నారు.", False),
    ("hi-IN", "ग्राहक को 500 कार्ड चाहिए।", False),
    ("en-IN", "", False),
])
def test_call_language_summary_is_required_for_non_english_calls(language, local, missing):
    problems = pcp.summary_problems({"summary_en": "Fine.", "summary_te": local}, {"language": language})
    assert ("missing_local_summary" in problems) is missing


async def test_retry_fills_local_summary_and_fixes_direction_without_losing_english():
    payload = {"summary_en": "The caller initiated the call. Saikiran wants 500 cards.", "summary_te": ""}
    retry = AsyncMock(return_value={"summary_en": "", "summary_te": "సాయికిరణ్ 500 కార్డులు కావాలన్నారు."})
    await pcp._repair_summaries(payload, OUTBOUND_TE, retry, [{"role": "user", "content": "x"}])
    retry.assert_awaited_once()
    assert payload["summary_te"].startswith("సాయికిరణ్")
    # The empty retried English summary did not replace the first; the clause was corrected.
    assert payload["summary_en"] == "The agent called the customer. Saikiran wants 500 cards."
    assert payload["summary_checks"] == []


async def test_empty_retry_keeps_english_and_records_the_missing_summary():
    payload = {"summary_en": "The agent called the customer about cards.", "summary_te": ""}
    retry = AsyncMock(return_value={"summary_en": "", "summary_te": ""})
    await pcp._repair_summaries(payload, {"direction": "outbound", "language": "ta-IN"}, retry, [])
    assert payload["summary_en"] == "The agent called the customer about cards."
    assert payload["summary_checks"] == ["missing_local_summary"]


async def test_clean_summary_is_not_retried():
    retry = AsyncMock()
    payload = {"summary_en": "The agent called the customer.", "summary_te": "ఏజెంట్ కాల్ చేశారు."}
    await pcp._repair_summaries(payload, OUTBOUND_TE, retry, [])
    retry.assert_not_awaited()


@pytest.mark.asyncio
async def test_pipeline_keeps_call_language_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    cid = "te-summary"
    await call_ledger.init(cid, {"call_id": cid, "direction": "outbound", "language": "te-IN"})
    await call_ledger.append_user_turn(cid, "నాకు 500 కార్డ్స్ కావాలి")
    memory_manager.init(cid)
    answers = [
        {"disposition": "interested", "disposition_confidence": 0.9, "summary_te": "",
         "summary_en": "The caller initiated the call and wants 500 cards.", "next_action": None,
         "extracted_fields": [], "objections": [], "unanswered_questions": ["Is the company a roadside business?"]},
        {"summary_en": "The agent called the customer, who wants 500 cards.", "summary_te": "కస్టమర్ 500 కార్డ్స్ కావాలన్నారు."},
    ]
    adapter = type("A", (), {"structured_completion": AsyncMock(side_effect=answers)})()
    with patch("server.providers.get_provider_registry") as reg:
        reg.return_value.get_llm.return_value = adapter
        outcome = await pcp.process_now(cid)
    first_prompt = adapter.structured_completion.await_args_list[0].args[0]
    assert "Direction: outbound" in first_prompt[1]["content"]
    assert outcome["summary_te"] == "కస్టమర్ 500 కార్డ్స్ కావాలన్నారు."
    assert outcome["summary_language"] == "te-IN"
    assert "initiated" not in outcome["summary_en"]
    assert outcome["unanswered_questions"] == ["Is the company a roadside business?"]
    assert json.loads(pcp.call_summary_path(cid).read_text(encoding="utf-8"))["summary_te"]
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


def test_schema_and_tags_carry_handoff_and_unanswered_questions():
    assert "unanswered_questions" in OUTCOME_JSON_SCHEMA["required"]
    assert "followup:handoff" in OUTCOME_JSON_SCHEMA["properties"]["tags"]["items"]["enum"]
    assert "followup:handoff" in derive_status_tags("callback_required", {"handoff_requested": "true"})
    assert normalize_unanswered_questions(["Do you deliver?", "do you deliver", " ", *[f"Price {i}?" for i in range(9)]]) == [
        "Do you deliver?", "Price 0?", "Price 1?", "Price 2?", "Price 3?"]


# --- Issue 12: lead stage, name and interest score -----------------------------------

CALL_OUTCOME = {
    "disposition": "callback_required", "disposition_confidence": 0.95,
    "facts": {"caller_name": "Saikiran", "phone": "919398247132", "quantity": "500", "slot": "tomorrow evening"},
    "status_tags": ["followup:callback", "intent:purchase", "outcome:callback_required"],
    "tags": ["intent:purchase"], "contact_preference": "callback",
}


@pytest.mark.parametrize("outcome,stage", [
    ({"disposition": "interested", "tags": ["intent:purchase"], "facts": {"quantity": "500"}}, "qualified"),
    ({"disposition": "interested", "tags": ["intent:purchase"], "facts": {"quantity": "bulk"}}, "contacted"),
    ({"disposition": "callback_required", "facts": {"callback_requested": "true"}}, "qualified"),
    ({"disposition": "interested", "status_tags": ["followup:handoff"]}, "qualified"),
    ({"disposition": "interested", "facts": {"handoff_requested": "true"}}, "qualified"),
    ({"disposition": "interested"}, "contacted"),
])
def test_engagement_moves_the_stage_forward(outcome, stage):
    assert lead_sync.outcome_stage(outcome) == stage


@pytest.mark.parametrize("stored,captured,replace", [
    ("Sai", "Saikiran", True),
    ("sai", "Sai Kiran", True),
    ("", "Saikiran", True),
    ("New lead", "Saikiran", True),
    ("Saikiran", "Sai", False),
    ("Tenant-approved name", "Unverified transcript name", False),
    ("Ramesh", "Suresh Kumar", False),
])
def test_only_a_missing_or_shorter_name_is_replaced(stored, captured, replace):
    assert lead_sync.better_name(stored, captured) is replace


async def test_lead_advances_and_takes_the_full_name(queue, monkeypatch):  # noqa: F811
    monkeypatch.setattr(lead_sync, "_session_factory", lambda: queue.factory)
    async with queue.factory() as session:
        row = Lead(tenant_id=queue.principal.tenant_id, agent_id=str(queue.aid), name="Sai", phone="+91 93982 47132", stage="contacted")
        session.add(row)
        await session.commit()
        lead_id = row.lead_id
    result = await lead_sync.sync_outcome_to_lead(outcome=CALL_OUTCOME, tenant_id=queue.principal.tenant_id,
                                                  agent_id=queue.aid, meta={"direction": "outbound"}, call_id="c-1")
    assert result["stage"] == "qualified" and result["action"] == "advanced"
    async with queue.factory() as session:
        assert (await session.get(Lead, lead_id)).name == "Saikiran"
    # A later plain callback never moves it back.
    later = {**CALL_OUTCOME, "status_tags": [], "tags": [], "facts": {"phone": "919398247132"}, "contact_preference": "none"}
    again = await lead_sync.sync_outcome_to_lead(outcome=later, tenant_id=queue.principal.tenant_id,
                                                 agent_id=queue.aid, meta={}, call_id="c-2")
    assert again["stage"] == "qualified"


def test_interest_score_reads_summary_tags():
    result = score_outcome(CALL_OUTCOME)
    interest = next(c for c in result["components"] if c["signal"] == "interest")
    assert interest["points"] == interest["max"] and interest["evidence"] == "intent:purchase"
    plain = score_outcome({**CALL_OUTCOME, "status_tags": [], "tags": []})
    assert next(c for c in plain["components"] if c["signal"] == "interest")["points"] == 0


# --- Issue 13: callback time window and the final clamp ------------------------------

@pytest.mark.parametrize("text", TOMORROW_EVENING)
def test_tomorrow_evening_resolves_to_5pm_ist(text):
    resolved = resolve_callback_window(text, now=ASKED_AT, timezone_name="Asia/Kolkata")
    assert datetime.fromisoformat(resolved["scheduledAt"]) == EXPECTED
    via_policy = svc.resolve_vague_time(FollowUpConfig(), ASKED_AT, text)
    assert datetime.fromisoformat(via_policy["scheduledAt"]) == EXPECTED


@pytest.mark.parametrize("local,expected", [
    (datetime(2026, 10, 31, 8, 4, tzinfo=IST), datetime(2026, 10, 31, 9, 0, tzinfo=IST)),
    (datetime(2026, 10, 31, 21, 0, tzinfo=IST), datetime(2026, 11, 2, 9, 0, tzinfo=IST)),  # Sunday not allowed
    (datetime(2026, 10, 31, 17, 0, tzinfo=IST), datetime(2026, 10, 31, 17, 0, tzinfo=IST)),
    (datetime(2026, 11, 1, 12, 0, tzinfo=IST), datetime(2026, 11, 2, 9, 0, tzinfo=IST)),
])
def test_clamp_moves_to_the_next_legal_window(local, expected):
    clamped = clamp_to_calling_window(local, timezone_name="Asia/Kolkata", weekdays=[0, 1, 2, 3, 4, 5])
    assert clamped == expected


@pytest.mark.parametrize("text", TOMORROW_EVENING)
async def test_captured_callback_is_scheduled_in_the_evening_window(queue, monkeypatch, text):  # noqa: F811
    monkeypatch.setattr(svc, "now_utc", lambda: ASKED_AT)
    await svc.save_policy(queue.principal, queue.aid, FollowUpConfig(enabled=True, callbackMode="automatic"), 0, True)
    async with queue.factory() as session:
        callback = CallCallback(callback_id=uuid.uuid4(), tenant_id=queue.principal.tenant_id, agent_id=str(queue.aid),
            original_call_id=uuid.uuid4(), to_e164="+919398247132", dial_request_id="requested:x", mode="requested", status="requested")
        session.add(callback)
        await session.flush()
        await svc.capture_request(session, callback, request_text=text, requested_when=text)
        await session.commit()
        job = await session.scalar(select(FollowUpJob))
    due = svc.utc(job.due_at).astimezone(IST)
    assert job.status == "scheduled"
    assert EXPECTED <= due < EXPECTED + timedelta(minutes=16)


async def test_every_job_save_is_clamped_to_legal_hours(queue):  # noqa: F811
    early = datetime(2026, 10, 31, 2, 34, tzinfo=timezone.utc)  # 08:04 IST, the reported bug
    async with queue.factory() as session:
        row = FollowUpJob(tenant_id=queue.principal.tenant_id, agent_id=queue.aid, origin_key="o", source_id="s",
            kind="callback", phone="+919398247132", status="scheduled", reason="x", due_at=early,
            expires_at=early + timedelta(days=2), payload={"timezone": "Asia/Kolkata"})
        session.add(row)
        await session.commit()
        assert svc.utc(row.due_at).astimezone(IST).time().isoformat() == "09:00:00"
        row.due_at = datetime(2026, 10, 31, 16, 0, tzinfo=timezone.utc)  # 21:30 IST
        await session.commit()
        assert svc.utc(row.due_at).astimezone(IST) == datetime(2026, 11, 1, 9, 0, tzinfo=IST)


async def test_extractor_uses_the_day_part_window_before_any_model(queue):  # noqa: F811
    row = FollowUpJob(id=uuid.uuid4(), payload={"requestText": TOMORROW_EVENING[0], "requestedAt": ASKED_AT.isoformat(),
                                               "timezone": "Asia/Kolkata", "llm": {}})
    due = await svc._extract_time(row, FollowUpConfig())
    assert due is not None and EXPECTED <= due.astimezone(IST) < EXPECTED + timedelta(minutes=16)


# --- Issue 14: the played opening is the first transcript line -----------------------

async def test_opening_is_written_once_at_its_play_time(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    cid = "opening-line"
    await call_ledger.init(cid, {"call_id": cid})
    played = "2026-10-30T18:10:30.700000Z"
    await call_ledger.append_user_turn(cid, "హలో", ts="2026-10-30T18:10:46.061181Z")
    first = await call_ledger.append_opening_turn(cid, "నమస్తే, నా పేరు Meera.", ts=played)
    assert first and first["seq"] == 0
    assert await call_ledger.append_opening_turn(cid, "నమస్తే, నా పేరు Meera.", ts=played) is None
    rows = call_ledger.read_lines(cid)
    assert [r["role"] for r in rows] == ["assistant", "user"]
    assert rows[0]["ts"] == played and rows[0]["opening"] is True
    assert rows[1]["seq"] == 1  # Existing seqs (memory events point at them) never move.
    nxt = await call_ledger.append_assistant_turn(cid, "చెప్పండి")
    assert nxt["seq"] == 2
    get_settings.cache_clear()


async def test_opening_already_written_by_a_voice_path_is_not_duplicated(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    cid = "opening-dup"
    await call_ledger.init(cid, {"call_id": cid})
    await call_ledger.append_assistant_turn(cid, "Hello, this is Meera.")
    assert await call_ledger.append_opening_turn(cid, "Hello, this is Meera.") is None
    assert len(call_ledger.read_lines(cid)) == 1
    get_settings.cache_clear()


# --- Warnings: skipped integrations and unanswered questions -------------------------

def test_skipped_action_reports_the_missing_details():
    outcome = {"summary_en": "Recap.", "extracted_fields": {"caller_name": "Saikiran", "phone": "9198"}}
    assert pcp.missing_post_call_details("GMAIL_CREATE_DRAFT", outcome, {}) == ["caller email"]


def test_warnings_aggregate_recent_outcomes():
    skipped = {"action": "GMAIL_CREATE_DRAFT", "result": {"status": "skipped", "message": "x"}}
    outcomes = [
        ("c2", "2026-10-30T18:00:00Z", {"integration_results": [skipped], "unanswered_questions": ["Is it a big company?"]}),
        ("c1", "2026-10-29T18:00:00Z", {"integration_results": [skipped, {"action": "X", "result": {"status": "ok"}}],
                                        "unanswered_questions": ["is it a big company", "Bulk discount?"]}),
    ]
    summary = summarize_outcomes(outcomes)
    assert summary["callsChecked"] == 2
    assert summary["skippedActions"] == [{"action": "GMAIL_CREATE_DRAFT", "count": 2, "missing": ["call summary", "caller email"],
                                          "lastCallId": "c2", "lastAt": "2026-10-30T18:00:00Z"}]
    assert [q["question"] for q in summary["unansweredQuestions"]] == ["Is it a big company?", "Bulk discount?"]
    assert summary["unansweredQuestions"][0]["count"] == 2


def test_saved_human_handoff_or_callback_qualifies_the_lead():
    outcome = {"disposition": "interested"}
    assert lead_sync.outcome_stage(outcome, {"human_handoff": {"contactRole": "manager", "callerWords": "x"}}) == "qualified"
    assert lead_sync.outcome_stage(outcome, {"callback_request": {"status": "requested"}}) == "qualified"
    assert lead_sync.outcome_stage(outcome, {"callback_request": {"status": "requested"}, "callback_cancelled": True}) == "contacted"


@pytest.mark.asyncio
async def test_saved_handoff_is_a_followup_tag_not_an_objection(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    memory_manager.reset_for_tests()
    cid = "handoff-outcome"
    handoff = {"contactRole": "manager", "callerWords": "मैनेजर से बात कराइए", "requestedTime": "कल शाम"}
    await call_ledger.init(cid, {"call_id": cid, "direction": "outbound", "language": "en-IN", "human_handoff": handoff})
    await call_ledger.append_user_turn(cid, "Please have your manager call me.")
    memory_manager.init(cid)
    answer = {"disposition": "interested", "disposition_confidence": 0.9, "summary_te": "",
              "summary_en": "The agent called the customer, who asked for the manager.", "next_action": None,
              "extracted_fields": [], "unanswered_questions": [],
              "objections": ["Caller requested to speak directly with the manager or owner.", "Price is high."]}
    adapter = type("A", (), {"structured_completion": AsyncMock(return_value=answer)})()
    with patch("server.providers.get_provider_registry") as reg:
        reg.return_value.get_llm.return_value = adapter
        outcome = await pcp.process_now(cid)
    assert outcome["objections"] == ["Price is high."]
    assert outcome["disposition"] == "callback_required"
    assert outcome["facts"]["handoff_requested"] == "true"
    assert "followup:handoff" in outcome["status_tags"]
    assert outcome["human_handoff"] == handoff
    assert lead_sync.outcome_stage(outcome) == "qualified"
    memory_manager.reset_for_tests()
    get_settings.cache_clear()
