"""Agent QA: one agent spec, adaptive customer conversations, every supported language.

Agent-agnostic. A spec (fixtures/agent_qa_*.json) names the agent brief, the customer persona and
the scenarios; nothing here knows the business. Each session:

- creates the agent through the tenant console API (analyze-brief -> build-employee) in an isolated
  sim_<hex> schema, so the published brain is the one a real tenant would get;
- runs the real PSTN turn loop (PstnVoiceLoop._run_turn) with live mid-call language switching on,
  exactly as a phone call, except TTS is a text stub that records what the LLM streamed to it;
- lets a different model (Gemini) play the customer, one utterance at a time, reacting to the
  agent's actual reply, paced in wall-clock like a call (agent playback + caller speech time);
- executes the tenant's real, verified integrations (Gmail / Google Calendar via Nango) behind a
  guard that only allows the designated test mailbox, and cancels any calendar event it created;
- records per turn: LLM requests, first-chunk latency, TTS chunk gaps, active language, the
  spoken-language packs present in the prompt, working-memory facts and tool executions;
- judges with server truth (DND, callbacks, language-switch rows, leads, tool executions) plus a
  Gemini judge that never sees Sarvam's own grading.

  python -m server.eval.conversation_sim.agent_qa --spec natureveda --langs te-IN --scenarios dnd
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from server.eval.conversation_sim.environment import (ACTOR, ARTIFACTS, CASE, REQUESTS, is_credits_error,
                                                    require_sarvam_brain, rotate_sarvam_key, sarvam_preflight,
                                                    setup, write_json)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
LANGUAGES = ("en-IN", "te-IN", "hi-IN", "ta-IN", "kn-IN", "gu-IN", "ml-IN")
NAMES = {"te-IN": "Telugu", "hi-IN": "Hindi", "ta-IN": "Tamil", "kn-IN": "Kannada", "en-IN": "Indian English",
         "gu-IN": "Gujarati", "ml-IN": "Malayalam"}
IST = ZoneInfo("Asia/Kolkata")
CALLER_MODELS = ("gemini-3.5-flash", "gemini-3.5-flash-lite")
SARVAM_MODEL = "sarvam-105b-conversations"
JUDGES = (("gemini", "gemini-3.5-flash"), ("gemini", "gemini-3.5-flash-lite"))
PACK_RE = re.compile(r"--- SPOKEN LANGUAGE \(([a-z]{2}-[A-Z]{2})\) ---")
ACTIVE_RE = re.compile(r"ACTIVE LANGUAGE[^\n]*")

CURRENT: dict = {}
REJUDGE = False
SARVAM_ONLY = False


_GEMINI_EXHAUSTED = False


def _note_gemini_quota(provider: str, exc: Exception) -> None:
    """A daily free-tier cap does not reset within a run; stop spending retries on it."""
    global _GEMINI_EXHAUSTED
    if provider == "gemini" and "429" in str(exc):
        _GEMINI_EXHAUSTED = True


class CallerModelError(RuntimeError):
    """The simulated customer could not speak; the session says nothing about the agent."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def progress(event: str, **kw) -> None:
    print(json.dumps({"event": event, **kw}, ensure_ascii=False, default=str), flush=True)


def load_spec(name: str) -> dict:
    path = Path(name) if Path(name).is_file() else FIXTURES / f"agent_qa_{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# -- Integrations ----------------------------------------------------------------------------------

async def real_integrations(spec: dict) -> list[dict]:
    """Verified connection rows of the designated test tenant, read from the main schema."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine
    from server.config.env import get_settings
    from server.db import connection
    from server.db.models.integration_models import TenantIntegration

    cfg = spec.get("integrations") or {}
    if not cfg.get("tenant_id"):
        return []
    engine = create_async_engine(connection._to_async_url(get_settings().database_url))
    try:
        async with engine.connect() as db:
            rows = (await db.execute(select(TenantIntegration.app_name, TenantIntegration.connection_id,
                                            TenantIntegration.metadata_.label("metadata_"), TenantIntegration.status)
                                     .where(TenantIntegration.tenant_id == uuid.UUID(cfg["tenant_id"])))).all()
    finally:
        await engine.dispose()
    wanted = {a.upper() for a in cfg.get("apps", {})}
    return [{"app_name": r.app_name.upper(), "connection_id": r.connection_id, "metadata": r.metadata_ or {}}
            for r in rows if r.app_name.upper() in wanted and r.status == "ACTIVE"
            and (r.metadata_ or {}).get("gateway_verified") is True]


def install_integration_guard(spec: dict) -> None:
    """Real Nango execution, limited to the test mailbox; every call is recorded on the case."""
    from server.services.tool_router import tool_router

    nango = tool_router.nango
    original = nango.execute_in_call_tool
    allowed = {e.lower() for e in (spec.get("integrations") or {}).get("allowed_recipients", [])}

    async def guarded(*args, **kwargs):
        names = ("tenant_id", "action_name", "params", "timeout_sec")
        call = dict(zip(names, args)) | kwargs
        action, params = str(call.get("action_name") or ""), dict(call.get("params") or {})
        case = CURRENT.get("case")
        row = {"action": action, "params": copy.deepcopy(params), "turn": case["turn_index"] if case else None,
               "at": time.monotonic()}
        if case is not None:
            case["tool_calls"].append(row)
        recipients = [params.get(k) for k in ("to", "attendee_email") if params.get(k)]
        if any(str(r).strip().lower() not in allowed for r in recipients):
            row["result"] = {"status": "error", "message": "This recipient is not allowed in the test environment."}
            row["blocked"] = True
            return row["result"]
        if action.upper().startswith("GOOGLECALENDAR_CREATE"):
            params["summary"] = "[QA TEST] " + str(params.get("summary") or "")
            call["params"] = params
        started = time.monotonic()
        result = await original(**call)
        row["result"], row["elapsed_s"] = copy.deepcopy(result), round(time.monotonic() - started, 3)
        return result

    nango.execute_in_call_tool = guarded
    nango._qa_original = original


async def cleanup_calendar(case: dict) -> None:
    from server.services.tool_router import tool_router

    original = getattr(tool_router.nango, "_qa_original", None)
    for row in case["tool_calls"]:
        if not row["action"].upper().startswith("GOOGLECALENDAR_CREATE") or not isinstance(row.get("result"), dict):
            continue
        event_id = row["result"].get("event_id") or row["result"].get("id")
        if event_id and original:
            res = await original(tenant_id=case["tenant_id"], action_name="GOOGLECALENDAR_CANCEL_EVENT",
                                 params={"event_id": event_id})
            row["cleanup"] = res


# -- Agent creation --------------------------------------------------------------------------------

async def create_agent(spec: dict, lang: str, out: Path, integrations: list[dict]) -> dict:
    """The tenant console creation flow, then integrations and the follow-up policy."""
    import httpx
    from fastapi import FastAPI
    from server.brain.compiled_brain_service import compiled_brain_service
    from server.db.connection import get_session_factory
    from server.db.models.entities import Tenant
    from server.db.models.followup_models import AgentFollowUpPolicy
    from server.db.models.integration_models import AgentIntegration, TenantIntegration
    from server.db.models.saas_models import TenantMembership, User
    from server.routes import app_agents
    from server.services.saas.followup_policy import FollowUpConfig
    from server.services.saas.tenant_guard import SubscriberPrincipal
    from server.services.tenant_tool_cache import invalidate

    agent = spec["agent"]
    record_path = out / "agents" / f"{lang}.json"
    if record_path.is_file():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if await compiled_brain_service.get_active_for_agent(record["agent_id"]):
            return record
    tid, uid = uuid.uuid4(), uuid.uuid4()
    async with get_session_factory()() as db:
        db.add(Tenant(tenant_id=tid, name=f"qa {agent['name']} {lang}", status="active"))
        db.add(User(user_id=uid, email=f"qa-{uid.hex}@example.invalid", password_hash="qa-unusable",
                    status="active", email_verified_at=_now()))
        await db.flush()
        db.add(TenantMembership(user_id=uid, tenant_id=tid, role="customer_admin"))
        await db.commit()
    principal = SubscriberPrincipal(uid, tid, "customer_admin", f"qa-{uid.hex}@example.invalid")
    app = FastAPI()
    app.include_router(app_agents.router)
    app.dependency_overrides[app_agents.require_subscriber_jwt] = lambda: principal
    body = {"brief": agent["brief"], "language": lang, "employeeName": agent["name"], "agentRole": agent["role"],
            "industry": agent["industry"], "callDirection": agent["direction"], "mode": "instant_lead",
            "naturalSpokenStyle": True, "requestId": str(uuid.uuid4())}
    started = time.monotonic()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://qa.local", timeout=600) as client:
        for attempt in range(4):
            response = await client.post("/api/app/agents/analyze-brief", json=body)
            if response.status_code < 500 and response.status_code != 429:
                break
            await asyncio.sleep(20 * (attempt + 1))
        analysis = response.json()
        write_json(out / "agents" / f"{lang}-analysis.json", {"status": response.status_code, "body": analysis})
        if response.status_code != 200:
            raise RuntimeError(f"analyze-brief {lang}: HTTP {response.status_code} {str(analysis)[:300]}")
        # A tenant answers clarifications from what they know; unknown details stay unknown.
        body["clarificationAnswers"] = [
            {"field": q["field"], "question": q.get("question", q["field"]),
             "answer": (agent.get("clarification_answers") or {}).get(q["field"], agent["clarification_answer"])}
            for q in analysis.get("questions", []) if q.get("field")]
        build_attempts = []
        for attempt in range(4):
            response = await client.post("/api/app/agents/build-employee", json=body | {"retryFailed": attempt > 0})
            build_attempts.append({"status": response.status_code,
                                   "code": ((response.json().get("detail") or {}).get("error") or {}).get("code")
                                   if response.status_code != 200 else None})
            # 5xx/429 are transient; a 422 "try again" is what a tenant retries from the UI.
            retry = response.status_code >= 500 or response.status_code == 429 or (
                response.status_code == 422 and build_attempts[-1]["code"] == "brief_needs_clarification")
            if not retry:
                break
            progress("build_retry", language=lang, attempt=attempt + 1, status=response.status_code)
            await asyncio.sleep(10 * (attempt + 1))
        result = response.json()
        write_json(out / "agents" / f"{lang}-build.json", {"status": response.status_code, "body": result})
        if response.status_code != 200:
            raise RuntimeError(f"build-employee {lang}: HTTP {response.status_code} {str(result)[:300]}")
    aid = uuid.UUID(result["agentId"])
    snapshot = await compiled_brain_service.get_active_for_agent(str(aid))
    async with get_session_factory()() as db:
        for row in integrations:
            db.add(TenantIntegration(tenant_id=tid, app_name=row["app_name"], connection_id=row["connection_id"],
                                     status="ACTIVE", metadata_=row["metadata"]))
            tools = (spec.get("integrations") or {}).get("apps", {}).get(row["app_name"], [])
            db.add(AgentIntegration(tenant_id=tid, agent_id=aid, app_name=row["app_name"], action_whitelist=tools,
                                    timing_mode="in_call", enabled=True))
        cfg = FollowUpConfig(enabled=True, callbackMode="automatic", missedMode="off", timezone="Asia/Kolkata",
                             weekdays=list(range(7)), startTime="00:00", endTime="23:59", maxAttempts=2,
                             cooldownMinutes=30)
        db.add(AgentFollowUpPolicy(tenant_id=tid, agent_id=aid, config=cfg.model_dump(), authorized_by=uid,
                                   billing_tenant_id=tid, authorized_at=_now() - timedelta(days=1)))
        await db.commit()
    invalidate(str(tid))
    brain = (snapshot or {}).get("compiled_text") or ""
    (out / "agents" / f"{lang}-brain.txt").write_text(brain, encoding="utf-8")
    brain_path = str(out / "agents" / f"{lang}-brain.txt")
    record = {"language": lang, "tenant_id": str(tid), "agent_id": str(aid), "user_id": str(uid),
              "brain_version": (snapshot or {}).get("compiled_version"), "brain_chars": len(brain),
              "creation_s": round(time.monotonic() - started, 1), "build_attempts": build_attempts,
              "direction": agent["direction"],
              "name": agent["name"], "brain_path": brain_path}
    write_json(record_path, record)
    progress("agent_created", **record)
    return record


def _script_from_brain(brain: str) -> str:
    """The generated business script inside a compiled brain (AGENT IDENTITY .. GUARDRAILS)."""
    start = brain.index("--- AGENT IDENTITY ---")
    end = brain.index("--- CALL CAPABILITIES ---", start)
    return brain[start:end].strip()


def retarget_brain(brain: str, lang: str, agent: dict) -> str:
    """Re-run the pipeline's deterministic assembly for another language on a generated script.

    Only the opening (the platform's native template) and the LANGUAGE section change; the
    business sections are the ones the creation pipeline generated.
    """
    from server.brain.agent_script_compiler import reassemble_brain_from_script
    from server.brain.agent_script_compiler import _platform_call_rules
    from server.brain.script_entities import build_script_entities, with_entity_tags_section
    from server.call.call_end_policy import normalize_call_end_policy
    from server.prompts.agent_voice_rules import opening_line_for

    script = _script_from_brain(brain)
    company = re.search(r"^@company_name:\s*(.+)$", brain, re.M).group(1).strip()
    goal = re.search(r"^@work_scope:\s*(.+)$", brain, re.M).group(1).strip()
    opening = opening_line_for(lang, agent_name=agent["name"], company_name=company, work_scope="",
                               direction=agent["direction"])
    script = re.sub(r"--- CANONICAL OPENING ---\n.*?(?=\n--- )",
                    lambda _m: "--- CANONICAL OPENING ---\nSay once:\n" + opening, script, count=1, flags=re.S)
    script = re.sub(r"--- LANGUAGE ---\n.*?(?=\n--- )",
                    lambda _m: f"--- LANGUAGE ---\nUse the selected {lang} language pack. Follow the platform language policy.",
                    script, count=1, flags=re.S)
    rules = _platform_call_rules(agent_name=agent["name"], role=agent["role"], direction=agent["direction"], language=lang)
    script = with_entity_tags_section(script, build_script_entities(
        agent_name=agent["name"], company_name=company, work_scope=goal, role=agent["role"], language=lang,
        direction=agent["direction"], opening_line=opening))
    _script, compiled = reassemble_brain_from_script(
        script=script, language=lang, call_end_policy=normalize_call_end_policy(None, language=lang),
        platform_call_rules=rules, agent_name=agent["name"], role=agent["role"])
    return compiled


async def publish_saved_brain(spec: dict, lang: str, out: Path, integrations: list[dict], brain: str,
                              source: str) -> dict:
    """Tenant + agent + published snapshot from a brain the creation pipeline produced."""
    from server.brain.compiled_brain_artifact import checksum_instructions
    from server.brain.sections import STATIC_OUTPUT_RULES_VERSION
    from server.db.connection import get_session_factory
    from server.db.models.brain_models import CompiledBrainSnapshot
    from server.db.models.entities import Agent, Tenant
    from server.db.models.followup_models import AgentFollowUpPolicy
    from server.db.models.integration_models import AgentIntegration, TenantIntegration
    from server.db.models.saas_models import TenantMembership, User
    from server.services.saas.followup_policy import FollowUpConfig
    from server.services.tenant_tool_cache import invalidate

    agent = spec["agent"]
    tid, uid, aid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    version = "cb_qa_" + uuid.uuid4().hex[:16]
    async with get_session_factory()() as db:
        db.add(Tenant(tenant_id=tid, name=f"qa {agent['name']} {lang}", status="active"))
        db.add(User(user_id=uid, email=f"qa-{uid.hex}@example.invalid", password_hash="qa-unusable",
                    status="active", email_verified_at=_now()))
        await db.flush()
        db.add(TenantMembership(user_id=uid, tenant_id=tid, role="customer_admin"))
        db.add(Agent(agent_id=aid, tenant_id=tid, name=agent["name"], status="active", languages=[lang],
                     active_compiled_brain_version=version))
        db.add(CompiledBrainSnapshot(compiled_version=version, platform_version="qa", business_version="qa",
                                     static_rules_version=STATIC_OUTPUT_RULES_VERSION, compiled_text=brain,
                                     checksum=checksum_instructions(brain)))
        await db.flush()
        for row in integrations:
            db.add(TenantIntegration(tenant_id=tid, app_name=row["app_name"], connection_id=row["connection_id"],
                                     status="ACTIVE", metadata_=row["metadata"]))
            db.add(AgentIntegration(tenant_id=tid, agent_id=aid, app_name=row["app_name"],
                                    action_whitelist=(spec.get("integrations") or {}).get("apps", {}).get(row["app_name"], []),
                                    timing_mode="in_call", enabled=True))
        cfg = FollowUpConfig(enabled=True, callbackMode="automatic", missedMode="off", timezone="Asia/Kolkata",
                             weekdays=list(range(7)), startTime="00:00", endTime="23:59", maxAttempts=2, cooldownMinutes=30)
        db.add(AgentFollowUpPolicy(tenant_id=tid, agent_id=aid, config=cfg.model_dump(), authorized_by=uid,
                                   billing_tenant_id=tid, authorized_at=_now() - timedelta(days=1)))
        await db.commit()
    invalidate(str(tid))
    path = out / "agents" / f"{lang}-brain.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(brain, encoding="utf-8")
    record = {"language": lang, "tenant_id": str(tid), "agent_id": str(aid), "user_id": str(uid),
              "brain_version": version, "brain_chars": len(brain), "brain_source": source,
              "direction": agent["direction"], "name": agent["name"], "brain_path": str(path)}
    write_json(out / "agents" / f"{lang}.json", record)
    progress("agent_created", **record)
    return record


# -- Text TTS boundary ----------------------------------------------------------------------------

def install_boundaries():
    """Text TTS that records every chunk the LLM streamed; orchestration stays real."""

    class TextPlayback:
        until = 0.0

        def is_active(self):
            return time.monotonic() < self.until

        def set_current_generation(self, _generation):
            return None

    class TextTts:
        def __init__(self, voice):
            self.voice, self._closed = voice, False
            self.has_sent_text = self.audio_emitted = self.had_error = False
            self.failure_evidence = None
            self._chars_sent = 0

        async def prepare_for_turn(self):
            self.has_sent_text = self.audio_emitted = False

        async def open(self, **kwargs):
            case = CURRENT.get("case")
            if case is not None:
                case["tts_events"].append({"turn": case["turn_index"], "event": "open",
                                           "language": kwargs.get("language_code") or self.voice._resolve_language()})

        async def sync_language(self):
            case = CURRENT.get("case")
            if case is not None:
                case["tts_events"].append({"turn": case["turn_index"], "event": "sync_language",
                                           "language": self.voice._resolve_language()})

        async def send_text(self, text):
            self.has_sent_text = self.audio_emitted = True
            self._chars_sent += len(text)
            case = CURRENT.get("case")
            if case is not None:
                from server.call.call_context import get
                ctx = get(self.voice.call_id)
                case["speech"].append({"turn": case["turn_index"], "text": text, "at": time.monotonic(),
                                       "tts_language": self.voice._resolve_language(),
                                       "farewell": bool(ctx and ctx.agent_hangup_armed)})
            self.voice.playback.until = time.monotonic() + 0.015
            await self.voice._emit_agent_wire(b"\0" * 320)

        async def finish(self):
            return None

        async def end_turn(self):
            return None

        async def close(self):
            self._closed = True

    import server.services.pstn_turn_tts as tts
    tts.PstnTurnTtsSession = TextTts

    # The pipeline's own decision events and every verifier rewrite, per turn.
    import server.utils.logger as app_logger
    original_emit = app_logger._emit

    def observed_emit(level, category, prefix, msg, **kv):
        case = CURRENT.get("case")
        if case is not None and category == "pstn" and not msg.startswith(("playout.", "wire.")):
            case["events"].append({"turn": case["turn_index"], "event": msg,
                                   **{k: str(v)[:200] for k, v in kv.items() if k != "call_id"}})
        return original_emit(level, category, prefix, msg, **kv)

    app_logger._emit = observed_emit
    import server.call.spoken_fact_review as review
    original_review = review.review_spoken_turn

    async def observed_review(ctx, *, caller, draft, language):
        out = await original_review(ctx, caller=caller, draft=draft, language=language)
        case = CURRENT.get("case")
        if case is not None:
            case["reviews"].append({"turn": case["turn_index"], "draft": draft, "output": out,
                                    "changed": out != draft})
        return out

    review.review_spoken_turn = observed_review

    # Raw provider stream for diagnosis: which delta fields carried the tokens.
    import server.providers.sarvam_llm as sarvam_llm

    class ObservedJson:
        def __getattr__(self, name):
            return getattr(json, name)

        @staticmethod
        def loads(data, *args, **kwargs):
            value = json.loads(data, *args, **kwargs)
            case = CURRENT.get("case")
            if case is not None and isinstance(value, dict) and value.get("choices"):
                choice = value["choices"][0] if isinstance(value["choices"][0], dict) else {}
                fields = {k: v for k, v in (choice.get("delta") or {}).items() if v not in (None, "", [])}
                if fields or choice.get("finish_reason"):
                    rows = case["raw_streams"]
                    if not rows or rows[-1]["turn"] != case["turn_index"] or rows[-1].get("closed"):
                        rows.append({"turn": case["turn_index"], "fields": {}})
                    row = rows[-1]
                    for k, v in fields.items():
                        row["fields"][k] = (row["fields"].get(k, "") + (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)))[:800]
                    if choice.get("finish_reason"):
                        row["finish"], row["closed"] = choice["finish_reason"], True
            return value

    sarvam_llm.json = ObservedJson()
    return TextPlayback


# -- Customer ---------------------------------------------------------------------------------------

CALLER_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["utterance", "ending"],
                 "properties": {"utterance": {"type": "string"}, "ending": {"type": "boolean"}}}


def caller_system(spec: dict) -> str:
    return f"""You are role-playing a real Indian customer on a phone call with a company's representative.
{spec['customer']['persona']}
Speak exactly like a person on the phone: one short natural utterance per turn (usually 1-2 sentences),
reacting to what the representative ACTUALLY just said. Never list several questions at once. Never
describe actions or stage directions. Do not repeat a question that was already answered unless the
scenario tells you to check their memory. Never say the same thing twice; if your goal is done,
say goodbye and end the call. Email addresses, order numbers and digits stay in Latin
script exactly as given. Return JSON: utterance (what you say) and ending (true only when this
utterance closes the call from your side)."""


def language_instruction(lang: str, scenario: dict, elapsed: float) -> str:
    switch = scenario.get("switch_at_s")
    if lang.startswith("en"):
        base = "Speak Indian English, with an occasional common Hindi word."
    else:
        base = (f"Speak natural spoken {NAMES[lang]} in {NAMES[lang]} script, mixing common English words "
                "(price, order, delivery, details, call) the way urban callers do.")
    if switch and elapsed >= switch:
        target = scenario.get("switch_to", {}).get(lang) or scenario.get("switch_to", {}).get("*")
        if target:
            base = f"From now on speak {NAMES[target]}" + (
                " only, in plain English." if target.startswith("en") else f" in {NAMES[target]} script.")
    return base


async def caller_turn(spec: dict, scenario: dict, lang: str, history: list[dict], elapsed: float,
                      agent_closed: bool) -> dict:
    from server.providers import get_provider_registry
    from server.providers.base import LLMConfig

    goal = scenario["goal"].get(lang) if isinstance(scenario["goal"], dict) else scenario["goal"]
    other = scenario.get("other_language", {}).get(lang) or scenario.get("other_language", {}).get("*")
    if other:
        goal = goal.replace("{other_language}", NAMES[other])
    cues = sorted(int(n) for n in re.findall(r"elapsed_call_seconds (?:reaches )?(\d+)", goal))
    due = [n for n in cues if elapsed >= n]
    payload = {"scenario_goal": goal, "elapsed_call_seconds": round(elapsed),
               # Weaker customer models ignore time cues; say plainly which step is due now.
               "step_due_now": (f"elapsed_call_seconds is past {due[-1]}: do the goal's step tied to {due[-1]} "
                                "seconds in THIS utterance if you have not done it yet.") if due else
                               "Not yet at any timed step: keep the early part of the goal going.",
               "never_repeat": [h["text"] for h in history if h["speaker"] == "customer"][-3:],
               "minimum_call_seconds": spec["min_session_s"],
               "language": language_instruction(lang, scenario, elapsed),
               "now_in_India": _now().astimezone(IST).strftime("%A %d %B %Y, %I:%M %p"),
               "conversation_so_far": history,
               "rules": ("Follow the scenario goal; its timing cues use elapsed_call_seconds. Before "
                         "minimum_call_seconds, keep the call going naturally with relevant follow-ups or "
                         "small reactions. Never end the call yourself before minimum_call_seconds unless the "
                         "goal says so. After it, end naturally once the goal is met.")}
    token = ACTOR.set("caller")
    try:
        last = None
        from server.providers.resolver import resolve_stack
        sarvam_model = resolve_stack(tier="medium", language=lang).llm.model
        # Gemini plays the customer; once its daily quota is spent Sarvam does, in a separate role.
        callers = [("gemini", m) for m in CALLER_MODELS if not (_GEMINI_EXHAUSTED or SARVAM_ONLY)] + [("sarvam", sarvam_model)]
        for attempt in range(6):
            for provider, model in callers:
                try:
                    async with asyncio.timeout(60):
                        result = await get_provider_registry().get_llm(provider).structured_completion(
                            [{"role": "system", "content": caller_system(spec)},
                             {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                            CALLER_SCHEMA, LLMConfig(provider=provider, model=model, temperature=0.7),
                            schema_name="qa_customer", max_output_tokens=2000)
                    if isinstance(result, dict) and str(result.get("utterance") or "").strip():
                        result["caller_model"] = f"{provider}:{model}"
                        return result
                    last = "empty"
                except Exception as exc:  # noqa: BLE001 - a caller-model hiccup is retried, never scored.
                    last = f"{model} {type(exc).__name__}: {str(exc)[:160]}"
                    _note_gemini_quota(provider, exc)
            # Gemini quotas are per minute; waiting out the window beats failing the session.
            await asyncio.sleep(15 * (attempt + 1))
        raise CallerModelError(f"caller model failed: {last}")
    finally:
        ACTOR.reset(token)


# -- Session ----------------------------------------------------------------------------------------

def _agent_requests(start: int) -> list[dict]:
    return [r for r in REQUESTS[start:] if r["actor"] == "agent"]


def _prompt_facts(requests: list[dict]) -> dict:
    """Which spoken-language packs and ACTIVE LANGUAGE notes each agent request carried."""
    rows = []
    for r in requests:
        msgs = r["body"].get("messages") or []
        system = "\n".join(str(m.get("content") or "") for m in msgs if m.get("role") == "system")
        rows.append({"model": r["body"].get("model"), "system_chars": len(system),
                     "messages": len(msgs), "max_tokens": r["body"].get("max_tokens"),
                     "packs": PACK_RE.findall(system), "active_notes": ACTIVE_RE.findall(system)[:3],
                     "kind": "turn" if r["body"].get("stream") else "structured"})
    return {"count": len(rows), "requests": rows}


async def db_evidence(case: dict) -> dict:
    from sqlalchemy import inspect, select
    from server.db.connection import get_session_factory
    from server.db.models.entities import Call, CallCallback
    from server.db.models.followup_models import FollowUpJob
    from server.db.models.integration_models import ToolExecution
    from server.db.models.language_switch_models import LanguageSwitchRequest
    from server.db.models.phase5_models import DncEntry
    from server.db.models.saas_models import Lead

    tid, aid, cid = uuid.UUID(case["tenant_id"]), uuid.UUID(case["agent_id"]), uuid.UUID(case["call_id"])
    out = {}
    async with get_session_factory()() as db:
        for name, cls, filters in [
            ("call", Call, [Call.tenant_id == tid, Call.call_id == cid]),
            ("callbacks", CallCallback, [CallCallback.tenant_id == tid, CallCallback.original_call_id == cid]),
            ("jobs", FollowUpJob, [FollowUpJob.tenant_id == tid, FollowUpJob.agent_id == aid,
                                   FollowUpJob.phone == case["phone"]]),
            ("dnd", DncEntry, [DncEntry.tenant_id == tid, DncEntry.phone_e164 == case["phone"]]),
            ("leads", Lead, [Lead.tenant_id == tid]),
            ("tools", ToolExecution, [ToolExecution.tenant_id == tid, ToolExecution.call_id == str(cid)]),
            ("language_switch", LanguageSwitchRequest, [LanguageSwitchRequest.tenant_id == tid,
                                                       LanguageSwitchRequest.original_call_id == cid]),
        ]:
            rows = (await db.scalars(select(cls).where(*filters))).all()
            out[name] = [{a.key: getattr(r, a.key) for a in inspect(r).mapper.column_attrs} for r in rows]
    return out


def _pace(text: str, *, caller: bool) -> float:
    """Seconds this utterance takes on a phone line (caller speech + endpointing, or agent playback)."""
    if caller:
        return min(1.0 + 0.38 * len(text.split()), 12.0)
    return min(len(text) / 15.0, 14.0)


async def run_session(spec: dict, agent: dict, scenario: dict, playback_cls, index: int) -> dict:
    from server.agent.conversation_manager import conversation_manager
    from server.brain.capabilities import agent_available_tools
    from server.call.call_brain_lock import resolve_locked_compiled_brain
    from server.call.call_context import CallContext, put
    from server.call.call_end_policy import normalize_call_end_policy
    from server.call.call_ledger import call_ledger
    from server.call.call_lifecycle_service import call_lifecycle_service
    from server.call.call_store import call_store
    from server.call.memory_manager import memory_manager
    from server.call.paths import relative_storage_path
    from server.call.post_call_pipeline import read_outcome
    from server.call.turn_coordinator import drain
    from server.providers.resolver import resolve_stack
    from server.services.pstn_voice_core import PHASE_ENDED, PHASE_LISTENING, PstnVoiceLoop

    lang = agent["language"]
    stack = resolve_stack(tier="medium", language=lang)
    require_sarvam_brain(stack)
    cid, sid = str(uuid.uuid4()), "qa-" + uuid.uuid4().hex
    phone = f"+9197{uuid.uuid4().int % 10**8:08d}"
    version, brain, _source = await resolve_locked_compiled_brain(agent["agent_id"], session_id=sid)
    if not brain:
        raise RuntimeError("Published brain unavailable at admission")
    direction = agent["direction"]
    ctx = CallContext(call_id=cid, tenant_id=agent["tenant_id"], agent_id=agent["agent_id"], session_id=sid,
                      channel="pstn", direction=direction, environment="development", tier="medium",
                      resolved_stack=stack, compiled_brain_version=version, compiled_brain_text=brain,
                      started_at=_now(), storage_path=relative_storage_path(cid), pipeline="composed_voice",
                      call_end_policy=normalize_call_end_policy(None, language=lang))
    put(ctx)
    await call_store.insert(ctx.to_public_dict() | {"is_test": True, "finalization_status": "pending"})
    peer = {"callee_e164": phone, "caller_id": "+914000000000"} if direction == "outbound" else \
        {"caller_id": phone, "callee_e164": "+914000000000"}
    await call_ledger.init(cid, ctx.to_public_dict() | peer | {"is_test": True, "call_end_policy": ctx.call_end_policy})
    memory_manager.init(cid)
    match = re.search(r"^@opening_line:\s*(.+)$", brain, re.M)
    opening = match.group(1).strip() if match else ""
    conversation_manager.add_turn(sid, "", opening)
    case = {"id": f"{lang}/{scenario['id']}", "scenario": scenario["id"], "language": lang,
            "tenant_id": agent["tenant_id"], "agent_id": agent["agent_id"], "call_id": cid, "phone": phone,
            "opening": opening, "brain_path": agent.get("brain_path"), "turn_index": 0, "turns": [], "speech": [], "tts_events": [], "tool_calls": [],
            "errors": [], "carrier": [], "events": [], "reviews": [], "raw_streams": []}
    case["available_tools"] = [t.get("name") for t in await agent_available_tools(
        agent["agent_id"], brain, tenant_id=agent["tenant_id"])]
    CURRENT["case"] = case
    token = CASE.set(case["id"])
    ACTOR.set("agent")

    async def wire(_frame):
        return None

    playback = playback_cls()
    voice = PstnVoiceLoop(session_id=sid, call_id=cid, on_agent_wire=wire, playback=playback, sample_rate=16000,
                          tts_output_codec="linear16",
                          stack_override=stack.to_safe_dict() | {"pipeline": "composed_voice",
                                                                 "voice_flow": "composed_stages"})
    voice._intro_phase, voice._phase = False, PHASE_LISTENING
    # Mirror the PSTN loop: live switching only when the voice core enables it.
    from server.services.pstn_voice_core import LIVE_LANGUAGE_SWITCH
    if LIVE_LANGUAGE_SWITCH:
        voice._enable_live_language_switch()
    voice._schedule_outage_clip_prewarm = lambda: case["tts_events"].append(
        {"turn": case["turn_index"], "event": "outage_clip_prewarm_requested"})

    async def hangup():
        case["carrier"].append({"turn": case["turn_index"], "at": time.monotonic()})

    voice.set_hangup_handler(hangup)
    history = [{"speaker": "representative", "text": opening}]
    began = time.monotonic()
    await asyncio.sleep(_pace(opening, caller=False))
    max_turns = spec.get("max_turns", 18)
    try:
        for turn in range(1, max_turns + 1):
            if voice._phase == PHASE_ENDED or ctx.status != "active" or case["carrier"]:
                break
            elapsed = time.monotonic() - began
            script = (scenario.get("script") or {}).get(lang)
            if script is not None:
                if turn > len(script):
                    break
                caller = {"utterance": script[turn - 1], "ending": turn == len(script)}
            else:
                caller = await caller_turn(spec, scenario, lang, history, elapsed, False)
            utterance = caller["utterance"].strip()
            await asyncio.sleep(_pace(utterance, caller=True))
            case["turn_index"] = turn
            speech_start, req_start = len(case["speech"]), len(REQUESTS)
            tools_start = len(case["tool_calls"])
            active_before = ctx.active_language if getattr(ctx, "active_language", "") else lang
            turn_start = time.monotonic()
            error = None
            for _attempt in range(2):
                try:
                    await asyncio.wait_for(voice._run_turn(utterance), timeout=120)
                    if voice._background_hangup_task:
                        await asyncio.wait_for(asyncio.shield(voice._background_hangup_task), timeout=65)
                    await asyncio.wait_for(drain(cid), timeout=120)
                    error = None
                except Exception as exc:  # noqa: BLE001 - recorded on the turn
                    error = f"{type(exc).__name__}: {str(exc)[:300]}"
                if not (is_credits_error(error) and rotate_sarvam_key()):
                    break
            done_at = time.monotonic()
            spoken = case["speech"][speech_start:]
            reply = " ".join(s["text"] for s in spoken if not s["farewell"]).strip()
            farewell = " ".join(s["text"] for s in spoken if s["farewell"]).strip()
            times = [s["at"] for s in spoken]
            gaps = [round(b - a, 3) for a, b in zip(times, times[1:])]
            snapshot = memory_manager.get_snapshot(cid) or {}
            row = {"turn": turn, "elapsed_s": round(turn_start - began, 1), "caller": utterance,
                   "caller_ending": caller.get("ending"), "reply": reply, "farewell": farewell,
                   "first_chunk_s": round(times[0] - turn_start, 3) if times else None,
                   "turn_s": round(done_at - turn_start, 3), "chunks": len(spoken),
                   "max_chunk_gap_s": max(gaps) if gaps else 0.0,
                   "tts_languages": sorted({s["tts_language"] for s in spoken}),
                   "active_language_before": active_before,
                   "active_language": getattr(ctx, "active_language", "") or lang,
                   "llm": _prompt_facts(_agent_requests(req_start)),
                   "tools": case["tool_calls"][tools_start:],
                   "memory_facts": copy.deepcopy(snapshot.get("facts") or {}),
                   "memory_preferences": copy.deepcopy(snapshot.get("preferences") or {}),
                   "memory_summary": str(snapshot.get("summary") or "")[:400],
                   "armed": ctx.agent_hangup_armed, "error": error,
                   "events": [e for e in case["events"] if e["turn"] == turn],
                   "reviews": [r for r in case["reviews"] if r["turn"] == turn],
                   "raw_streams": [r for r in case["raw_streams"] if r["turn"] == turn]}
            case["turns"].append(row)
            if error:
                case["errors"].append(error)
            history += [{"speaker": "customer", "text": utterance},
                        {"speaker": "representative", "text": (reply + " " + farewell).strip() or "(silence)"}]
            progress("turn", id=case["id"], turn=turn, t=row["elapsed_s"], first_chunk=row["first_chunk_s"],
                     llm_calls=row["llm"]["count"], lang=row["active_language"], tools=[t["action"] for t in row["tools"]],
                     caller=utterance[:80], reply=(reply or farewell)[:120])
            await asyncio.sleep(_pace(reply + " " + farewell, caller=False))
            if caller.get("ending") and time.monotonic() - began >= spec["min_session_s"]:
                break
        case["duration_s"] = round(time.monotonic() - began, 1)
        case["ended_by_agent"] = bool(case["carrier"]) or ctx.agent_hangup_armed
        case["contact_preference"] = getattr(ctx, "contact_preference", None)
        if ctx.status == "active":
            await call_lifecycle_service.end(cid, reason="user_stop")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            stored = await call_store.get(cid)
            if read_outcome(cid) and stored and stored.get("finalization_status") in {"complete", "failed"}:
                break
            await asyncio.sleep(0.3)
        outcome = read_outcome(cid) or {}
        case["outcome"] = {k: outcome.get(k) for k in ("disposition", "contact_preference", "summary",
                                                       "status_tags", "facts")}
        case["db"] = await db_evidence(case)
        from server.call.order_confirmation import read_order_proof
        case["order_proof"] = read_order_proof(cid, tenant_id=agent["tenant_id"])
        case["meta"] = {k: v for k, v in (call_ledger.read_meta(cid) or {}).items()
                        if k in {"contact_preference", "callback_request", "end_reason", "language_switches"}}
        await cleanup_calendar(case)
    except Exception as exc:  # noqa: BLE001 - the session is reported, the run continues
        case["errors"].append(f"{type(exc).__name__}: {str(exc)[:500]}")
        case.setdefault("duration_s", round(time.monotonic() - began, 1))
    finally:
        await voice.close()
        CASE.reset(token)
        CURRENT.pop("case", None)
    return case


# -- Verdicts ---------------------------------------------------------------------------------------

def server_checks(case: dict, scenario: dict, spec: dict) -> list[dict]:
    """Deterministic checks from what the server recorded and what the LLM actually streamed."""
    from server.call.action_proof import unproven_claim
    from server.eval.conversation_sim.checks import check_reply

    db, lang = case.get("db") or {}, case["language"]
    expect = scenario.get("expect", {})
    checks: list[dict] = []

    def add(cid: str, ok: bool, evidence: str = "") -> None:
        checks.append({"id": cid, "passed": bool(ok), "evidence": evidence, "kind": "server"})

    add("no_runtime_error", not case["errors"], "; ".join(case["errors"])[:300])
    add("min_duration_90s", case.get("duration_s", 0) >= 90, f"{case.get('duration_s')}s")
    silent = [t["turn"] for t in case["turns"] if not t["reply"] and not t["farewell"]]
    add("responsive_every_turn", not silent, f"silent turns {silent}")
    # A turn that ran a tool has a hold clip on a real call; it gets the tool's own time on top.
    slow = [(t["turn"], t["first_chunk_s"]) for t in case["turns"]
            if (t["first_chunk_s"] or 0) > spec["slow_first_chunk_s"] + (
                3 if t["tools"] or any(e["event"] == "order.tool" for e in t.get("events", [])) else 0)]
    add("first_chunk_latency", not slow, f"slow turns {slow}")
    hard = []
    for t in case["turns"]:
        if t["reply"]:
            result = check_reply(t["reply"], language=t["active_language"], tts_provider="sarvam", tts_model="bulbul:v3")
            hard += [f"t{t['turn']}:{h}" for h in result.hard]
    add("speech_clean", not hard, ", ".join(hard)[:300])
    from server.call.spoken_fact_review import correct_stated_total
    brain = (Path(case.get("brain_path") or "").read_text(encoding="utf-8")
             if case.get("brain_path") and Path(case["brain_path"]).is_file() else "")
    wrong = [t["turn"] for t in case["turns"] if brain and correct_stated_total(t["reply"], brain) != t["reply"]]
    add("totals_consistent", not wrong, f"turns {wrong}")
    from server.call.action_proof import proof_for_tool_result
    receipts = {p for t in case["tool_calls"] if (p := proof_for_tool_result(t["action"], t.get("result")))}
    if case.get("order_proof"):
        receipts.add("order_confirmed")  # CONFIRM_ORDER is a platform tool, not an integration call
    if db.get("leads"):
        receipts.add("enquiry_saved")
    claims = [t["turn"] for t in case["turns"] if unproven_claim(t["reply"], receipts)]
    add("no_unproven_action_claim", not claims, f"turns {claims}")
    active_dnd = [d for d in db.get("dnd", []) if d.get("active")]
    if "dnd" in expect:
        add("dnd_saved" if expect["dnd"] else "no_false_dnd", bool(active_dnd) == expect["dnd"], str(len(active_dnd)))
    else:
        add("no_false_dnd", not active_dnd, str(len(active_dnd)))
    if expect.get("callback"):
        add("callback_saved", bool(db.get("callbacks")), str([c.get("scheduled_for") for c in db.get("callbacks", [])]))
    if expect.get("no_callback"):
        add("no_unrequested_callback", not db.get("callbacks"), str(len(db.get("callbacks", []))))
    if expect.get("ended"):
        add("agent_closed_call", case.get("ended_by_agent"), "")
    if expect.get("order"):
        add("order_recorded", bool(case.get("order_proof")), str(case.get("order_proof"))[:200])
    if expect.get("lead"):
        # A lead carries the number the caller gave, which may differ from the dialled one.
        said = {re.sub(r"\D", "", m)[-10:] for t in case["turns"] for m in re.findall(r"[\d\s-]{10,}", t["caller"])}
        mine = [l for l in db.get("leads", []) if re.sub(r"\D", "", str(l.get("phone") or ""))[-10:]
                in said | {case["phone"][-10:]}]
        add("lead_recorded", bool(mine), str([l.get("phone") for l in db.get("leads", [])])[:200])
    lang_cb = expect.get("language_callback")
    if lang_cb:
        target = (scenario.get("other_language", {}).get(lang) or scenario.get("other_language", {}).get("*"))
        items = db.get("language_switch", [])
        add("language_callback_saved", any(i.get("requested_language") == target for i in items),
            str([i.get("requested_language") for i in items]))
    switch = expect.get("switch")
    if switch:
        target = (scenario.get("switch_to", {}).get(lang) or scenario.get("switch_to", {}).get("*"))
        if target and target != lang and target.startswith("en"):
            after = [t for t in case["turns"] if t["elapsed_s"] >= scenario["switch_at_s"]]
            switched = [t for t in after if t["active_language"] == target]
            add("switched_live_to_english", bool(switched), f"active languages {[t['active_language'] for t in after]}")
            if switched:
                first = switched[0]["turn"]
                packs = [r["packs"] for t in case["turns"] if t["turn"] > first for r in t["llm"]["requests"]
                         if r["packs"]]  # reply requests; the classifiers carry no pack
                # The cached brain keeps the original pack; exactly one active-language pack is added.
                add("pack_replaced_not_stacked", all(p.count(target) == 1 for p in packs) if packs else True,
                    str(packs[:4]))
                tts = [t["tts_languages"] for t in case["turns"] if t["turn"] > first and t["reply"]]
                add("tts_followed_switch", all(x == [target] for x in tts), str(tts[:4]))
        elif target:
            items = db.get("language_switch", [])
            add("language_callback_saved", any(i.get("requested_language") == target for i in items),
                str([i.get("requested_language") for i in items]))
    if expect.get("tool"):
        want = expect["tool"]
        calls = [t for t in case["tool_calls"] if t["action"].upper() == want and not t.get("blocked")]
        ok = [t for t in calls if str((t.get("result") or {}).get("status", "")).lower() not in {"error", "unknown", "failed"}]
        # The tenant's connection itself failing (expired OAuth) says nothing about the agent: score the
        # attempt and the honesty of what it told the caller, and mark the session infra-blocked.
        down = [t for t in calls if re.search(r"re-authori|HTTP 400|HTTP 424",
                                              str((t.get("result") or {}).get("message", "")))]
        if calls and not ok and down:
            case["infra"] = f"{want} connection unavailable: {(down[0].get('result') or {}).get('message')}"
            add(f"tool_{want.lower()}_attempted", True, str(down[0]["params"].get("to") or "")[:120])
        else:
            add(f"tool_{want.lower()}_succeeded", bool(ok), str([(t["action"], (t.get("result") or {}).get("status"))
                                                                for t in case["tool_calls"]])[:300])
    disp = expect.get("dispositions")
    if disp:
        got = (case.get("outcome") or {}).get("disposition")
        add("disposition", got in disp, str(got))
    return checks


JUDGE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["checks"], "properties": {
    "checks": {"type": "array", "items": {"type": "object", "additionalProperties": False,
        "required": ["id", "passed", "evidence"], "properties": {
            "id": {"type": "string"}, "passed": {"type": "boolean"}, "evidence": {"type": "string"}}}}}}

JUDGE_SYSTEM = """You audit a transcript of an AI phone agent. Judge each listed check strictly and only from
the transcript and the business brief. Lines may be in an Indian language; read them in that language.
"PLATFORM FAREWELL" is spoken by the platform after the agent decided to end the call. Tool lines show
integration calls the agent made and their real results. Return every check id with passed and a short
evidence quote. A check that does not apply to what happened in this transcript passes."""


def transcript_text(case: dict) -> str:
    lines = [f"AGENT (opening): {case.get('opening')}"]
    for t in case["turns"]:
        lines.append(f"[{t['elapsed_s']}s] CALLER: {t['caller']}")
        for tool in t["tools"]:
            lines.append(f"TOOL {tool['action']} {json.dumps(tool['params'], ensure_ascii=False)[:300]} -> "
                         f"{json.dumps(tool.get('result'), ensure_ascii=False, default=str)[:300]}")
        if any(e["event"] == "order.tool" and e.get("status") == "ok" for e in t.get("events", [])):
            proof = case.get("order_proof") or {}
            # Platform tools are not integration calls; without this line the judge read a real
            # recorded order as an invented confirmation.
            lines.append("TOOL CONFIRM_ORDER -> ok: order recorded "
                         f"({proof.get('product')}, qty {proof.get('quantity')}, {proof.get('customer_name')})")
        lines.append(f"AGENT [{t['active_language']}]: {t['reply'] or '(silent)'}")
        if t["farewell"]:
            lines.append(f"PLATFORM FAREWELL: {t['farewell']}")
    return "\n".join(lines)


async def judge(case: dict, scenario: dict, spec: dict) -> list[dict]:
    from server.providers import get_provider_registry
    from server.providers.base import LLMConfig

    checks = {**spec["universal_checks"], **{k: spec["scenario_checks"][k] for k in scenario.get("judge", [])
                                             if k in spec["scenario_checks"]}}
    payload = json.dumps({"business_brief": spec["agent"]["brief"], "call_language": case["language"],
                          "scenario": scenario["id"], "transcript": transcript_text(case), "checks": checks},
                         ensure_ascii=False)
    result, errors = None, []
    if SARVAM_ONLY:
        judges = (("sarvam", SARVAM_MODEL),)
    else:
        judges = JUDGES
    if _GEMINI_EXHAUSTED and not REJUDGE and not SARVAM_ONLY:
        # The judge stays independent of the model under test: pending until --rejudge.
        return [{"id": c, "passed": None, "evidence": "judge_pending:gemini_quota", "kind": "judge"} for c in checks]
    for attempt in range(4):
        for provider, model in judges:
            try:
                async with asyncio.timeout(150):
                    result = await get_provider_registry().get_llm(provider).structured_completion(
                        [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": payload}],
                        JUDGE_SCHEMA, LLMConfig(provider=provider, model=model, temperature=0),
                        schema_name="qa_judge", max_output_tokens=6000)
                if isinstance(result, dict):
                    case["judge_model"] = model
                    break
            except Exception as exc:  # noqa: BLE001 - a judge outage is unknown, never a pass
                errors.append(f"{model}:{type(exc).__name__}")
                _note_gemini_quota("gemini", exc)
                result = None
        if result is not None:
            break
        await asyncio.sleep(15 * (attempt + 1))
    if result is None:
        return [{"id": c, "passed": None, "evidence": "judge_error:" + ",".join(errors), "kind": "judge"} for c in checks]
    got = {c["id"]: c for c in result.get("checks", [])}
    return [{**(got.get(c) or {"id": c, "passed": None, "evidence": "judge omitted"}), "kind": "judge"} for c in checks]


# -- Reporting --------------------------------------------------------------------------------------

def summarize(out: Path, results: list[dict]) -> None:
    langs = [lang for lang in LANGUAGES if any(r["language"] == lang for r in results)]
    scenarios = list(dict.fromkeys(r["scenario"] for r in results))
    total_checks = sum(len(r["checks"]) for r in results)
    passed_checks = sum(c["passed"] is True for r in results for c in r["checks"])
    lines = [f"# Agent QA {out.name}", "",
             f"Sessions passed {sum(r['passed'] for r in results)}/{len(results)}. "
             f"Checks passed {passed_checks}/{total_checks} ({100 * passed_checks / max(total_checks, 1):.1f}%).", "",
             "| Scenario | " + " | ".join(langs) + " |", "|---|" + "---|" * len(langs)]
    cell = {(r["scenario"], r["language"]): r for r in results}
    for sid in scenarios:
        row = []
        for lang in langs:
            r = cell.get((sid, lang))
            row.append("-" if not r else ("PASS" if r["passed"] else "FAIL: " + ", ".join(r["failures"])))
        lines.append(f"| {sid} | " + " | ".join(row) + " |")
    lines += ["", "## Session metrics", "",
              "| Session | Dur s | Turns | Avg first chunk s | Max first chunk s | LLM calls/turn | Max sys prompt chars | Tools |",
              "|---|---|---|---|---|---|---|---|"]
    for r in results:
        fc = [t["first_chunk_s"] for t in r["turns"] if t["first_chunk_s"] is not None]
        calls = [t["llm"]["count"] for t in r["turns"]]
        chars = [q["system_chars"] for t in r["turns"] for q in t["llm"]["requests"]]
        lines.append(f"| {r['id']} | {r.get('duration_s')} | {len(r['turns'])} | "
                     f"{sum(fc) / len(fc) if fc else 0:.2f} | {max(fc) if fc else 0:.2f} | "
                     f"{sum(calls) / len(calls) if calls else 0:.1f} | {max(chars) if chars else 0} | "
                     f"{','.join(t['action'] for t in r['tool_calls']) or '-'} |")
    lines += ["", "## Transcripts", ""]
    for r in results:
        if r.get("infra"):
            lines.append(f"> infra: {r['infra']}")
        lines.append(f"### {r['id']} {'PASS' if r['passed'] else 'FAIL'} — {r.get('duration_s')}s, "
                     f"disposition {(r.get('outcome') or {}).get('disposition')} {r['failures']}")
        lines.append(f"- opening: {r.get('opening')}")
        for t in r["turns"]:
            lines.append(f"- [{t['elapsed_s']}s] caller: {t['caller']}")
            for tool in t["tools"]:
                lines.append(f"  - tool {tool['action']} -> {json.dumps(tool.get('result'), ensure_ascii=False, default=str)[:200]}")
            lines.append(f"- agent [{t['active_language']}, {t['first_chunk_s']}s]: {t['reply'] or '(silent)'}")
            if t["farewell"]:
                lines.append(f"- farewell: {t['farewell']}")
        for c in r["checks"]:
            if c["passed"] is not True:
                lines.append(f"- FAILED {c['kind']}:{c['id']} — {c['evidence']}")
        lines.append("")
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")


async def rejudge(args) -> int:
    """Re-run pending/unknown judge checks (e.g. after the judge's quota reset)."""
    global REJUDGE
    REJUDGE = True
    if args.sarvam_only:
        use_sarvam_only()
        from server.eval.conversation_sim.environment import use_env_sarvam_key, sarvam_preflight
        use_env_sarvam_key()
        await sarvam_preflight("sarvam-105b-conversations")
    spec = load_spec(args.spec)
    out = Path(args.out)
    from server.services.dev_secrets_store import dev_secrets_store
    from server.config.env import get_settings
    get_settings().gemini_api_key = dev_secrets_store.effective_secret("gemini_api_key") or get_settings().gemini_api_key
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in spec["scenarios"]}
    only = set(args.scenarios.split(",")) if args.scenarios else None
    for case in results:
        forced = only is not None and case["id"] in only
        if not forced and all(c["passed"] is not None for c in case["checks"] if c["kind"] == "judge"):
            continue
        server = [c for c in case["checks"] if c["kind"] == "server"]
        case["checks"] = server + await judge(case, by_id[case["scenario"]], spec)
        case["failures"] = [c["id"] + ("" if c["passed"] is False else ":unknown")
                            for c in case["checks"] if c["passed"] is not True]
        case["passed"] = not case["failures"]
        progress("rejudged", id=case["id"], passed=case["passed"], failures=case["failures"])
        write_json(out / "results.json", results)
    summarize(out, results)
    return 0


def rescore(args) -> int:
    """Recompute server checks on saved sessions; judge verdicts are kept."""
    spec = load_spec(args.spec)
    out = Path(args.out)
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in spec["scenarios"]}
    for case in results:
        if not case.get("brain_path"):
            case["brain_path"] = str(out / "agents" / f"{case['language']}-brain.txt")
        judged = [c for c in case["checks"] if c["kind"] == "judge"]
        case["checks"] = server_checks(case, by_id[case["scenario"]], spec) + judged
        case["failures"] = [c["id"] + ("" if c["passed"] is False else ":unknown")
                            for c in case["checks"] if c["passed"] is not True]
        case["passed"] = not case["failures"]
    write_json(out / "results.json", results)
    summarize(out, results)
    return 0


def use_sarvam_only() -> None:
    """Customer, judge and agent creation all on Sarvam (process-local; stored config untouched)."""
    global SARVAM_ONLY
    SARVAM_ONLY = True
    import server.brain.generation_runtime as generation
    generation.generation_target_metadata = lambda: ("sarvam", SARVAM_MODEL)


async def run(args) -> int:
    if args.sarvam_only:
        use_sarvam_only()
    spec = load_spec(args.spec)
    languages = list(LANGUAGES) if args.langs == "all" else args.langs.split(",")
    only = set(args.scenarios.split(",")) if args.scenarios else None
    out = Path(args.out) if args.out else ARTIFACTS / f"agent-qa-{spec['id']}-{_now():%Y%m%d-%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    integrations = await real_integrations(spec)
    progress("integrations", apps=[i["app_name"] for i in integrations])
    env = await setup(out, schema=args.schema, sarvam_key_source=args.sarvam_key_source)
    from server.providers.resolver import resolve_stack
    stack = resolve_stack(tier="medium", language=languages[0])
    require_sarvam_brain(stack)
    await sarvam_preflight(stack.llm.model)
    playback_cls = install_boundaries()
    install_integration_guard(spec)
    results: list[dict] = []
    if args.resume and (out / "results.json").is_file():
        results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    done = {r["id"] for r in results}
    write_json(out / "run.json", {"schema": env["schema"], "spec": spec["id"], "languages": languages,
                                  "model": stack.llm.model})
    index = len(results)
    plan = {}
    if args.plan:
        for part in args.plan.split(";"):
            lang, _, ids = part.partition("=")
            plan[lang.strip()] = set(ids.split(","))
        languages = list(plan)
    for lang in languages:
        wanted = plan.get(lang) or only
        jobs = [s for s in spec["scenarios"] if (not wanted or s["id"] in wanted) and f"{lang}/{s['id']}" not in done]
        if not jobs:
            continue
        saved = [Path(d) / "agents" / f"{lang}-brain.txt" for d in (args.brains or "").split(",") if d]
        saved = [p for p in saved if p.is_file()]
        record_path = out / "agents" / f"{lang}.json"
        if record_path.is_file():
            agent = json.loads(record_path.read_text(encoding="utf-8"))
        elif saved:
            agent = await publish_saved_brain(spec, lang, out, integrations, saved[0].read_text(encoding="utf-8"),
                                              f"pipeline:{saved[0]}")
        elif args.retarget_from:
            base = (Path(args.retarget_from) / "agents" / f"{args.retarget_from_lang}-brain.txt").read_text(encoding="utf-8")
            agent = await publish_saved_brain(spec, lang, out, integrations, retarget_brain(base, lang, spec["agent"]),
                                              f"retargeted:{args.retarget_from_lang}")
        else:
            agent = await create_agent(spec, lang, out, integrations)
        for scenario in jobs:
            index += 1
            progress("session_start", id=f"{lang}/{scenario['id']}")
            for infra_attempt in range(3):
                case = await run_session(spec, agent, scenario, playback_cls, index)
                if not any(e.startswith("CallerModelError") for e in case["errors"]):
                    break
                progress("session_infra_retry", id=case["id"], attempt=infra_attempt + 1, errors=case["errors"])
                index += 1
                await asyncio.sleep(90)
            case["infra_retries"] = infra_attempt
            case["checks"] = server_checks(case, scenario, spec) + await judge(case, scenario, spec)
            case["failures"] = [c["id"] + ("" if c["passed"] is False else ":unknown")
                                for c in case["checks"] if c["passed"] is not True]
            case["passed"] = not case["failures"]
            results = [r for r in results if r["id"] != case["id"]] + [case]
            progress("session", id=case["id"], passed=case["passed"], failures=case["failures"],
                     duration=case.get("duration_s"), disposition=(case.get("outcome") or {}).get("disposition"))
            write_json(out / "results.json", results)
            summarize(out, results)
    write_json(out / "requests.json", REQUESTS)
    summarize(out, results)
    from server.db.connection import close_db
    await close_db()
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", default="natureveda")
    parser.add_argument("--langs", default="all")
    parser.add_argument("--scenarios")
    parser.add_argument("--schema")
    parser.add_argument("--out")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--rescore", action="store_true", help="recompute server checks in --out")
    parser.add_argument("--rejudge", action="store_true", help="re-run pending/unknown judge checks in --out")
    parser.add_argument("--sarvam-only", action="store_true", help="Sarvam plays customer and judge and builds the agent")
    parser.add_argument("--brains", help="comma list of run dirs whose pipeline-built agents/<lang>-brain.txt to reuse")
    parser.add_argument("--retarget-from", help="run dir whose brain is re-assembled for languages without a saved brain")
    parser.add_argument("--retarget-from-lang", default="en-IN")
    parser.add_argument("--plan", help="per-language scenarios: 'hi-IN=a,b;en-IN=c,d' (overrides --langs/--scenarios)")
    parser.add_argument("--sarvam-key-source", choices=("runtime", "env"), default="env")
    args = parser.parse_args()
    if args.rescore:
        return rescore(args)
    if args.rejudge:
        return asyncio.run(rejudge(args))
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
