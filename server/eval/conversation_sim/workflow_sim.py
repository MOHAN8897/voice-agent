"""Live workflow simulator: real PSTN turn loop, Sarvam brain, server-side outcome checks.

Five tenant-style business scripts x workflow scenarios (enquiry, callback, DND, end-of-call
without DND, negated block, order, order without the capability, refusal) x languages.
Each call runs through PstnVoiceLoop._run_turn with a text TTS stub, then the real post-call
pipeline. Verdicts come from what the server recorded (callback rows, follow-up jobs, DND
entries, order proof, leads, disposition), not from the model's words.

  python -m server.eval.conversation_sim.workflow_sim --langs all --sarvam-key-source env
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from server.eval.conversation_sim.checks import SCRIPTS, check_reply, script_profile
from server.eval.conversation_sim.environment import (ACTOR, ARTIFACTS, CASE, REQUESTS, is_credits_error,
                                                    require_sarvam_brain, rotate_sarvam_key, sarvam_preflight,
                                                    setup, write_json)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CALLER_LINES = FIXTURES / "workflow_utterances.json"
LANGUAGES = ("te-IN", "hi-IN", "ta-IN", "kn-IN", "en-IN", "gu-IN", "ml-IN")
NAMES = {"te-IN": "Telugu", "hi-IN": "Hindi", "ta-IN": "Tamil", "kn-IN": "Kannada", "en-IN": "Indian English",
         "gu-IN": "Gujarati", "ml-IN": "Malayalam"}

BUSINESSES = {
    "printing": dict(agent="Kavitha", direction="inbound", industry="printing", role="sales", brief="""Agent name Kavitha. Company Sri Krishna Digital Prints, a printing shop in Vijayawada.
Normal visiting cards cost 200 rupees per 100 cards; matte finish cards cost 350 rupees per 100 cards. Minimum order 100 cards.
Flex banners cost 15 rupees per square foot. Delivery in Vijayawada takes 3 working days after artwork approval.
We take orders on the call. Collect quantity, customer name and delivery address, then confirm the order.
Payment is cash on delivery; never take card details on the phone.""",
        ask="What is the price of matte visiting cards?"),
    "appliance": dict(agent="Suresh", direction="inbound", industry="home_services", role="support", brief="""Agent name Suresh. Company SmartCare Appliance Services, home appliance repair in Hyderabad.
Window AC servicing costs 499 rupees. Split AC servicing costs 599 rupees.
Fridge inspection costs 250 rupees; the inspection charge is waived if the customer goes ahead with the repair.
Service areas: Madhapur, Gachibowli, Kondapur and Kukatpally only.
If the caller wants a visit, take their name, appliance, issue, locality and preferred slot so the team can confirm it.""",
        ask="How much is split AC servicing?"),
    "clinic": dict(agent="Anjali", direction="inbound", industry="healthcare", role="appointment", brief="""Agent name Anjali. Company Sunrise Dental Clinic in Hyderabad.
Consultation fee is 300 rupees. Scaling and cleaning costs 1,200 rupees. Root canal starts from 4,500 rupees; the final price is given after an X-ray.
Open Monday to Saturday, 10 AM to 8 PM.
If the caller wants an appointment, take their name, problem and preferred day and time so the front desk can confirm it.
Never give a medical diagnosis; for severe pain or swelling advise visiting the clinic immediately.""",
        ask="How much is the consultation fee and when are you open?"),
    "academy": dict(agent="Madhavi", direction="inbound", industry="education", role="education", brief="""Agent name Madhavi. Company Teja Data Academy.
We offer an 8-week online Python with Data Analytics course. The fee is 8,999 rupees, no instalments.
Weekday batch 8 PM to 9 PM; weekend batch 10 AM to 1 PM. Any graduate or final-year student can join.
Placement assistance is provided, but there is strictly no job guarantee.
If the caller is interested, take their name, qualification and preferred batch for a free demo class.""",
        ask="What is the course fee and is there a weekend batch?"),
    "realestate": dict(agent="Ravi", direction="outbound", industry="real_estate", role="sales", brief="""Agent name Ravi. Company Green Acres Realty.
You call people who enquired online about plots in Shadnagar.
Plots start from 18 lakh rupees for 150 square yards; the layout is DTCP approved.
Site visits are on Saturdays and Sundays, 10 AM to 5 PM.
Goal: check if they are still interested and offer a site visit. If they are busy, offer to call back at a time they choose.
If they ask not to be called again, respect it.""",
        ask="What is the plot price and is it approved?"),
}

# expect: server-side outcome that must hold. "any" business list rotates by language for coverage.
SCENARIOS = [
    dict(id="enquiry", businesses=["appliance", "clinic", "academy", "printing"],
         turns=["{ask}", "Okay, please note my enquiry. My name is Kiran and I am interested.", "That's all for now, thank you."],
         expect={"no_dnd": True, "lead_or_enquiry": True}),
    dict(id="callback", businesses=["clinic", "realestate", "academy", "appliance"],
         turns=["I'm busy right now. Can you call me back tomorrow at 6 in the evening?",
                "Yes, on this same number. My name is Kiran.", "Okay, thank you."],
         expect={"no_dnd": True, "callback_saved": True, "ended": True}),
    dict(id="dnd", businesses=["realestate", "printing", "appliance"],
         turns=["Please don't call this number ever again. Remove my number from your list.",
                "I already said it. Do not call me again."],
         expect={"dnd": True, "no_callback": True, "ended": True}),
    dict(id="end_no_dnd", businesses=["academy", "appliance", "clinic", "printing"],
         turns=["{ask}", "Okay, that's all I needed. Thanks, bye."],
         expect={"no_dnd": True, "ended": True, "no_callback": True}),
    dict(id="negated_block", businesses=["realestate"],
         turns=["I'm driving now. Don't block my number, I am interested. Call me next Monday morning.",
                "Yes, same number. My name is Kiran.", "Thanks."],
         expect={"no_dnd": True}),
    dict(id="order", businesses=["printing"],
         turns=["I want 200 matte visiting cards.", "My name is Ravi Kumar. Deliver to 12 MG Road, Vijayawada.",
                "Yes, please confirm the order.", "Thanks, that's all."],
         expect={"order": True, "no_dnd": True}),
    dict(id="order_unavailable", businesses=["appliance", "clinic"],
         turns=["Book it for tomorrow 11 AM and confirm the booking right now.",
                "Is it confirmed? Give me the booking number.", "Okay, thanks."],
         expect={"no_order": True, "no_false_claim": True, "no_dnd": True}),
    dict(id="refusal", businesses=["realestate", "academy"],
         turns=["No, I'm not interested. Thanks."],
         expect={"no_dnd": True, "ended": True, "no_callback": True}),
]

TRANSLATE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["lines"],
                    "properties": {"lines": {"type": "array", "items": {"type": "string"}}}}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def progress(event: str, **kw) -> None:
    print(json.dumps({"event": event, **kw}, ensure_ascii=False, default=str), flush=True)


def _in_script(line: str, lang: str) -> bool:
    base = lang.split("-")[0]
    profile = {k: v for k, v in script_profile(line).items() if k != "latin" and v}
    if base not in SCRIPTS:
        return not profile
    return profile.get(base, 0) > 0 and not (set(profile) - {base})


async def caller_lines(languages: list[str], stack) -> dict:
    """English source lines, rendered once per language by Sarvam and cached as fixtures."""
    cache = json.loads(CALLER_LINES.read_text(encoding="utf-8")) if CALLER_LINES.is_file() else {}
    sources = sorted({t for s in SCENARIOS for t in s["turns"] if t != "{ask}"} | {b["ask"] for b in BUSINESSES.values()})
    from server.providers import get_provider_registry
    from server.providers.base import LLMConfig
    adapter = get_provider_registry().get_llm("sarvam")
    for lang in languages:
        have = cache.get(lang, {})
        missing = [s for s in sources if s not in have]
        if lang.startswith("en"):
            have.update({s: s for s in missing})
        elif missing:
            token = ACTOR.set("translator")
            try:
                async def translate(batch: list[str]) -> list[str]:
                    result = await adapter.structured_completion(
                        [{"role": "system", "content": (
                            f"Translate each phone-caller line into natural spoken {NAMES[lang]} as an urban caller would say it: "
                            f"{NAMES[lang]} script with common English words (AC, booking, number, order) left in English. "
                            "Keep names, numbers and addresses unchanged. Return the lines in the same order.")},
                         {"role": "user", "content": json.dumps({"lines": batch}, ensure_ascii=False)}],
                        TRANSLATE_SCHEMA, LLMConfig(provider="sarvam", model=stack.llm.model, temperature=0.2),
                        api_mode=stack.llm.config.get("api_mode"), schema_name="caller_lines", max_output_tokens=3000)
                    return (result or {}).get("lines") or []

                def acceptable(source: str, line: str) -> bool:
                    # Callers really do say "Thanks." in English; longer lines must be in the call script.
                    return _in_script(line, lang) or (len(source.split()) <= 3 and not script_profile(line).keys() - {"latin"})

                lines = await translate(missing)
                if len(lines) != len(missing):
                    lines = [""] * len(missing)
                for i, source in enumerate(missing):
                    for _attempt in range(3):
                        if lines[i] and acceptable(source, lines[i]):
                            have[source] = lines[i]
                            break
                        single = await translate([source])
                        lines[i] = single[0] if single else ""
                    else:
                        if len(source.split()) > 3:
                            raise RuntimeError(f"Could not get a valid {lang} caller line for {source!r}")
                        have[source] = source  # a short "Thanks." in English is how callers talk
                        progress("caller_line_fallback", language=lang, source=source)
            finally:
                ACTOR.reset(token)
        cache[lang] = have
        FIXTURES.mkdir(exist_ok=True)
        CALLER_LINES.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return cache


async def create_agent(business: str, lang: str, out: Path) -> dict:
    """Tenant + agent + published brain + follow-up policy, written directly (no LLM build)."""
    from server.brain.agent_script_compiler import compile_agent_from_brief
    from server.brain.compiled_brain_artifact import checksum_instructions
    from server.brain.sections import STATIC_OUTPUT_RULES_VERSION
    from server.db.connection import get_session_factory
    from server.db.models.entities import Agent, Tenant
    from server.db.models.brain_models import CompiledBrainSnapshot
    from server.db.models.followup_models import AgentFollowUpPolicy
    from server.db.models.saas_models import TenantMembership, User
    from server.services.saas.followup_policy import FollowUpConfig

    spec = BUSINESSES[business]
    cache = out / "brains" / f"{business}-{lang}.txt"
    if cache.is_file():
        brain = cache.read_text(encoding="utf-8")
    else:
        brain, *_ = await compile_agent_from_brief(
            brief=spec["brief"], language=lang, direction=spec["direction"],
            generation_config={"employeeName": spec["agent"], "agentRole": spec["role"], "callDirection": spec["direction"],
                               "industry": spec["industry"], "mode": "instant_lead", "naturalSpokenStyle": True})
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(brain, encoding="utf-8")
    tid, uid, aid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    version = "cb_sim_" + uuid.uuid4().hex[:16]
    async with get_session_factory()() as db:
        db.add(Tenant(tenant_id=tid, name=f"sim {business} {lang}", status="active"))
        db.add(User(user_id=uid, email=f"sim-{uid.hex}@example.invalid", password_hash="sim-unusable",
                    status="active", email_verified_at=_now()))
        await db.flush()
        db.add(TenantMembership(user_id=uid, tenant_id=tid, role="customer_admin"))
        db.add(Agent(agent_id=aid, tenant_id=tid, name=spec["agent"], status="active", languages=[lang],
                     active_compiled_brain_version=version))
        db.add(CompiledBrainSnapshot(compiled_version=version, platform_version="sim", business_version="sim",
                                     static_rules_version=STATIC_OUTPUT_RULES_VERSION, compiled_text=brain,
                                     checksum=checksum_instructions(brain)))
        await db.flush()
        cfg = FollowUpConfig(enabled=True, callbackMode="automatic", missedMode="review", timezone="Asia/Kolkata",
                             weekdays=list(range(7)), startTime="00:00", endTime="23:59", maxAttempts=2, cooldownMinutes=30)
        db.add(AgentFollowUpPolicy(tenant_id=tid, agent_id=aid, config=cfg.model_dump(), authorized_by=uid,
                                   billing_tenant_id=tid, authorized_at=_now() - timedelta(days=1)))
        await db.commit()
    return {"business": business, "language": lang, "tenant_id": str(tid), "agent_id": str(aid), "user_id": str(uid),
            "brain_version": version, **spec}


def install_boundaries():
    """Text TTS and a closed external-integration boundary; orchestration stays real."""
    from server.services.tool_router import tool_router

    async def no_external(**_kw):
        return {"status": "error", "message": "No external integration is connected in this simulation."}

    tool_router.nango.execute_in_call_tool = no_external

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

        async def open(self, **_kwargs):
            return None

        async def send_text(self, text):
            self.has_sent_text = self.audio_emitted = True
            self._chars_sent += len(text)
            case = CURRENT.get("case")
            if case is not None:
                from server.call.call_context import get
                ctx = get(self.voice.call_id)
                case["speech"].append({"turn": case["turn_index"], "text": text,
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
    return TextPlayback


CURRENT: dict = {}


async def db_evidence(case: dict) -> dict:
    from sqlalchemy import inspect, select
    from server.db.connection import get_session_factory
    from server.db.models.entities import Call, CallCallback
    from server.db.models.followup_models import FollowUpJob
    from server.db.models.phase5_models import DncEntry
    from server.db.models.saas_models import Lead

    tid, aid, cid = uuid.UUID(case["tenant_id"]), uuid.UUID(case["agent_id"]), uuid.UUID(case["call_id"])
    out = {}
    async with get_session_factory()() as db:
        for name, cls, filters in [
            ("call", Call, [Call.tenant_id == tid, Call.call_id == cid]),
            ("callbacks", CallCallback, [CallCallback.tenant_id == tid, CallCallback.original_call_id == cid]),
            ("jobs", FollowUpJob, [FollowUpJob.tenant_id == tid, FollowUpJob.agent_id == aid]),
            ("dnd", DncEntry, [DncEntry.tenant_id == tid, DncEntry.phone_e164 == case["phone"]]),
            ("leads", Lead, [Lead.tenant_id == tid]),
        ]:
            rows = (await db.scalars(select(cls).where(*filters))).all()
            out[name] = [{a.key: getattr(r, a.key) for a in inspect(r).mapper.column_attrs} for r in rows]
    return out


async def run_case(agent: dict, scenario: dict, lines: dict, playback_cls, index: int) -> dict:
    from server.agent.conversation_manager import conversation_manager
    from server.call.call_brain_lock import resolve_locked_compiled_brain
    from server.call.call_context import CallContext, put
    from server.call.call_end_policy import normalize_call_end_policy
    from server.call.call_ledger import call_ledger
    from server.call.call_lifecycle_service import call_lifecycle_service
    from server.call.call_store import call_store
    from server.call.memory_manager import memory_manager
    from server.call.order_confirmation import read_order_proof
    from server.call.paths import relative_storage_path
    from server.call.post_call_pipeline import read_outcome
    from server.call.turn_coordinator import drain
    from server.providers.resolver import resolve_stack
    from server.services.pstn_voice_core import PHASE_ENDED, PHASE_LISTENING, PstnVoiceLoop

    lang = agent["language"]
    stack = resolve_stack(tier="medium", language=lang)
    require_sarvam_brain(stack)
    cid, sid = str(uuid.uuid4()), "wf-" + uuid.uuid4().hex
    phone = f"+9198765{index:05d}"
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
    import re
    match = re.search(r"^@opening_line:\s*(.+)$", brain, re.M)
    opening = match.group(1).strip() if match else ""
    conversation_manager.add_turn(sid, "", opening or f"{agent['agent']}, {agent['business']}.")
    case = {"id": f"{lang}/{scenario['id']}/{agent['business']}", "scenario": scenario["id"], "language": lang,
            "business": agent["business"], "tenant_id": agent["tenant_id"], "agent_id": agent["agent_id"],
            "call_id": cid, "phone": phone, "opening": opening, "turn_index": 0, "turns": [], "speech": [],
            "carrier": [], "errors": []}
    CURRENT["case"] = case
    token = CASE.set(case["id"])
    ACTOR.set("agent")

    async def wire(_frame):
        return None

    playback = playback_cls()
    voice = PstnVoiceLoop(session_id=sid, call_id=cid, on_agent_wire=wire, playback=playback, sample_rate=16000,
                          tts_output_codec="linear16",
                          stack_override=stack.to_safe_dict() | {"pipeline": "composed_voice", "voice_flow": "composed_stages"})
    voice._intro_phase, voice._phase = False, PHASE_LISTENING

    async def hangup():
        case["carrier"].append({"turn": case["turn_index"]})

    voice.set_hangup_handler(hangup)
    try:
        for turn, english in enumerate(scenario["turns"], 1):
            if voice._phase == PHASE_ENDED or ctx.status != "active":
                break
            source = english.format(ask=agent["ask"])
            caller = lines[lang].get(source, source)
            case["turn_index"] = turn
            start = len(case["speech"])
            for _attempt in range(2):
                try:
                    await asyncio.wait_for(voice._run_turn(caller), timeout=120)
                    if voice._background_hangup_task:
                        await asyncio.wait_for(asyncio.shield(voice._background_hangup_task), timeout=65)
                    await asyncio.wait_for(drain(cid), timeout=120)
                    error = None
                except Exception as exc:
                    error = f"{type(exc).__name__}: {str(exc)[:300]}"
                if not (is_credits_error(error) and rotate_sarvam_key()):
                    break
            spoken = [s for s in case["speech"][start:]]
            case["turns"].append({"turn": turn, "caller": caller, "caller_en": source,
                                  "reply": " ".join(s["text"] for s in spoken if not s["farewell"]).strip(),
                                  "farewell": " ".join(s["text"] for s in spoken if s["farewell"]).strip(),
                                  "armed": ctx.agent_hangup_armed, "error": error})
            if error:
                case["errors"].append(error)
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
        case["outcome"] = {k: outcome.get(k) for k in ("disposition", "contact_preference", "summary", "status_tags", "facts")}
        case["order_proof"] = read_order_proof(cid, tenant_id=agent["tenant_id"])
        case["db"] = await db_evidence(case)
        case["meta"] = {k: v for k, v in (call_ledger.read_meta(cid) or {}).items()
                        if k in {"contact_preference", "callback_request", "end_reason"}}
    except Exception as exc:
        case["errors"].append(f"{type(exc).__name__}: {str(exc)[:500]}")
    finally:
        await voice.close()
        CASE.reset(token)
        CURRENT.pop("case", None)
    case["verdict"] = evaluate(case, scenario)
    return case


def evaluate(case: dict, scenario: dict) -> dict:
    from server.call.action_proof import unproven_claim

    db = case.get("db") or {}
    expect = scenario["expect"]
    failures: list[str] = []
    active_dnd = [d for d in db.get("dnd", []) if d.get("active")]
    disposition = (case.get("outcome") or {}).get("disposition")
    if case["errors"]:
        failures.append("runtime_error")
    if expect.get("dnd") and not active_dnd:
        failures.append("dnd_not_saved")
    if expect.get("no_dnd") and active_dnd:
        failures.append("false_dnd_saved")
    if expect.get("callback_saved") and not db.get("callbacks"):
        failures.append("callback_not_saved")
    if expect.get("callback_saved") and db.get("callbacks") and not any(j.get("kind") == "callback" for j in db.get("jobs", [])):
        failures.append("callback_job_missing")
    if expect.get("no_callback") and db.get("callbacks"):
        failures.append("unrequested_callback_saved")
    if expect.get("ended") and not case.get("ended_by_agent"):
        failures.append("agent_did_not_close")
    if expect.get("order") and not case.get("order_proof"):
        failures.append("order_not_recorded")
    if expect.get("no_order") and case.get("order_proof"):
        failures.append("order_recorded_without_capability")
    if expect.get("lead_or_enquiry") and not db.get("leads"):
        failures.append("enquiry_not_recorded")
    if expect.get("no_false_claim"):
        receipts: list = []
        for t in case["turns"]:
            if unproven_claim(t["reply"], receipts):
                failures.append("unproven_action_claim")
                break
    expected_disposition = {"dnd": {"not_interested"}, "refusal": {"not_interested"},
                            "callback": {"callback_required", "interested", "new_lead"},
                            "order": {"converted"}}.get(scenario["id"])
    if expected_disposition and disposition not in expected_disposition:
        failures.append(f"disposition:{disposition}")
    speech = [dict(check_reply(t["reply"], language=case["language"], tts_provider="sarvam", tts_model="bulbul:v3").__dict__)
              for t in case["turns"] if t["reply"]]
    for result in speech:
        failures += [f"speech:{h}" for h in result["hard"]]
    return {"passed": not failures, "failures": failures, "disposition": disposition}


def plan(languages: list[str], only: set[str] | None) -> list[tuple[str, dict, str]]:
    jobs = []
    for li, lang in enumerate(languages):
        for si, scenario in enumerate(SCENARIOS):
            if only and scenario["id"] not in only:
                continue
            business = scenario["businesses"][(li + si) % len(scenario["businesses"])]
            jobs.append((lang, scenario, business))
    return jobs


async def missed_call_checks() -> list[dict]:
    """Deterministic missed-call follow-up behaviour on the isolated schema."""
    from types import SimpleNamespace
    from sqlalchemy import select
    from server.db.connection import get_session_factory
    from server.db.models.followup_models import FollowUpJob
    from server.db.models.phase5_models import DncEntry
    from server.db.models.entities import CallAttempt
    from server.services.saas.followup_policy import FollowUpConfig
    from server.services.saas.followup_service import _capture_missed

    results = []
    agent = await create_agent("appliance", "te-IN", ARTIFACTS / "_tmp_missed")
    tid, aid = uuid.UUID(agent["tenant_id"]), uuid.UUID(agent["agent_id"])
    policy = SimpleNamespace(tenant_id=tid, agent_id=aid, authorized_at=_now() - timedelta(days=1),
                             authorized_by=uuid.UUID(agent["user_id"]), billing_tenant_id=tid)
    for mode, phone, dnd in (("off", "+919000000001", False), ("review", "+919000000002", False),
                             ("automatic", "+919000000003", False), ("automatic", "+919000000004", True)):
        async with get_session_factory()() as s:
            if dnd:
                s.add(DncEntry(tenant_id=tid, phone_e164=phone, active=True, source="sim", reason="sim"))
            attempt = CallAttempt(tenant_id=tid, agent_id=aid, provider_call_control_id=uuid.uuid4().hex,
                                  direction="inbound", from_number=phone, status="missed", ended_at=_now() - timedelta(minutes=5))
            s.add(attempt)
            await s.flush()
            await _capture_missed(s, policy, FollowUpConfig(enabled=True, missedMode=mode, weekdays=list(range(7)),
                                                            startTime="00:00", endTime="23:59"), _now())
            await s.commit()
            jobs = (await s.scalars(select(FollowUpJob).where(FollowUpJob.tenant_id == tid, FollowUpJob.phone == phone))).all()
        got = [(j.kind, j.status, j.reason) for j in jobs]
        ok = (not jobs) if mode == "off" else (bool(jobs) and all(j.kind == "missed" for j in jobs))
        if dnd and jobs:
            ok = all(j.status == "suppressed" for j in jobs) or not jobs
        results.append({"mode": mode, "dnd": dnd, "jobs": got, "passed": ok})
        progress("missed_call", mode=mode, dnd=dnd, jobs=got, passed=ok)
    return results


async def run(args) -> int:
    languages = list(LANGUAGES) if args.langs == "all" else args.langs.split(",")
    only = set(args.scenarios.split(",")) if args.scenarios else None
    out = Path(args.out) if args.out else ARTIFACTS / f"workflow-sim-{_now():%Y%m%d-%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    env = await setup(out, schema=args.schema, sarvam_key_source=args.sarvam_key_source)
    from server.providers.resolver import resolve_stack
    stack = resolve_stack(tier="medium", language=languages[0])
    require_sarvam_brain(stack)
    await sarvam_preflight(stack.llm.model)
    playback_cls = install_boundaries()
    lines = await caller_lines(languages, stack)
    jobs = plan(languages, only)
    agents: dict[tuple[str, str], dict] = {}
    for lang, _scenario, business in jobs:
        if (business, lang) not in agents:
            agents[(business, lang)] = await create_agent(business, lang, out)
    semaphore = asyncio.Semaphore(args.concurrency)
    results: list[dict] = []

    async def one(i, lang, scenario, business):
        async with semaphore:
            case = await run_case(agents[(business, lang)], scenario, lines, playback_cls, i)
            results.append(case)
            progress("case", id=case["id"], passed=case["verdict"]["passed"], failures=case["verdict"]["failures"],
                     disposition=case["verdict"]["disposition"])
            write_json(out / "results.json", sorted(results, key=lambda c: c["id"]))

    # CURRENT is a single slot for the TTS stub, so cases run one at a time within this process.
    for i, (lang, scenario, business) in enumerate(jobs, 1):
        await one(i, lang, scenario, business)
    missed = await missed_call_checks() if not only or "missed" in (only or set()) else []
    write_json(out / "missed_calls.json", missed)
    write_json(out / "requests.json", REQUESTS)
    summarize(out, results, missed, env)
    from server.db.connection import close_db
    await close_db()
    return 0


def summarize(out: Path, results: list[dict], missed: list[dict], env: dict) -> None:
    lines = [f"# Workflow simulation {out.name}", "", f"Schema `{env['schema']}`.", "",
             "| Scenario | Pass | Failures |", "|---|---|---|"]
    by: dict[str, list] = {}
    for r in results:
        by.setdefault(r["scenario"], []).append(r)
    for sid, rows in by.items():
        fails = sorted({f for r in rows for f in r["verdict"]["failures"]})
        lines.append(f"| {sid} | {sum(r['verdict']['passed'] for r in rows)}/{len(rows)} | {', '.join(fails) or '-'} |")
    lines += ["", "| Missed-call mode | DND | Jobs | Pass |", "|---|---|---|---|"]
    lines += [f"| {m['mode']} | {m['dnd']} | {m['jobs']} | {m['passed']} |" for m in missed]
    lines += ["", "## Transcripts", ""]
    for r in sorted(results, key=lambda c: c["id"]):
        v = r["verdict"]
        lines.append(f"### {r['id']} {'PASS' if v['passed'] else 'FAIL'} — disposition {v['disposition']} {v['failures']}")
        lines.append(f"- opening: {r.get('opening')}")
        for t in r["turns"]:
            lines += [f"- caller: {t['caller']}", f"- agent: {t['reply'] or '(silent)'}"]
            if t["farewell"]:
                lines.append(f"- farewell: {t['farewell']}")
            if t["error"]:
                lines.append(f"- error: {t['error']}")
        lines.append("")
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--langs", default="all")
    parser.add_argument("--scenarios", help="comma list of scenario ids (and/or 'missed')")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--schema")
    parser.add_argument("--out")
    parser.add_argument("--sarvam-key-source", choices=("runtime", "env"), default="runtime")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
