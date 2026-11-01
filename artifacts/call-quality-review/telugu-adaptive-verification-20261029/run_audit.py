"""Live Sarvam customer talks to the real call orchestrator, with isolated storage."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from environment import OUT, CASE, ACTOR, REQUESTS, NETWORK, setup, write, source_manifest, business_inputs
from scenarios import matrix, CUSTOMERS, CALLER_SYSTEM, CALLER_SCHEMA

CURRENT = None
RESULTS = []
MEMORY_LOAD = ContextVar("audit_memory_load", default=None)


def now():
    return datetime.now(timezone.utc)


def progress(event, **kwargs):
    print(json.dumps({"event": event, **kwargs}, ensure_ascii=False, default=str), flush=True)


async def create_agents():
    from fastapi import FastAPI
    import httpx
    from server.routes import app_agents
    from server.db.connection import get_session_factory
    from server.db.models.entities import Tenant
    from server.db.models.saas_models import User, TenantMembership
    from server.services.saas.tenant_guard import SubscriberPrincipal
    from server.brain.compiled_brain_service import compiled_brain_service
    records = {}
    for business in business_inputs():
        prior = OUT / f"agents/{business['id']}-published.json"
        if os.getenv("AUDIT_RESUME") == "1" and prior.is_file():
            record = json.loads(prior.read_text(encoding="utf-8"))
            record["principal"] = SubscriberPrincipal(uuid.UUID(record["user_id"]), uuid.UUID(record["tenant_id"]),
                "customer_admin", f"audit-{uuid.UUID(record['user_id']).hex}@example.invalid")
            await compiled_brain_service.get_active_for_agent(record["agent_id"])
            records[business["id"]] = record
            progress("creation_reused_from_this_run", business=business["id"])
            continue
        tid, uid = uuid.uuid4(), uuid.uuid4()
        async with get_session_factory()() as db:
            db.add(Tenant(tenant_id=tid, name="Isolated adaptive audit " + business["name"], status="active"))
            db.add(User(user_id=uid, email=f"audit-{uid.hex}@example.invalid", password_hash="isolated-unusable-password",
                        status="active", email_verified_at=now()))
            await db.flush()
            db.add(TenantMembership(user_id=uid, tenant_id=tid, role="customer_admin"))
            await db.commit()
        principal = SubscriberPrincipal(uid, tid, "customer_admin", f"audit-{uid.hex}@example.invalid")
        app = FastAPI()
        app.include_router(app_agents.router)
        app.dependency_overrides[app_agents.require_subscriber_jwt] = lambda: principal
        body = {"brief": business["brief"], "language": "te-IN", "employeeName": business["agent_name"],
                "agentRole": business["role"], "industry": business["industry"], "callDirection": "outbound",
                "mode": "instant_lead", "naturalSpokenStyle": True, "requestId": str(uuid.uuid4())}
        progress("creation_start", business=business["id"])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://audit.local", timeout=240) as client:
            response = await client.post("/api/app/agents/analyze-brief", json=body)
            analysis = response.json()
            write(f"agents/{business['id']}-analysis.json", {"status": response.status_code, "body": analysis})
            if response.status_code != 200:
                raise RuntimeError(f"Brief analysis failed: {business['id']} HTTP {response.status_code}")
            # Clarification truth is the supplied fictional fact sheet, not a guessed answer.
            facts = json.dumps(business["facts"], ensure_ascii=False)
            body["clarificationAnswers"] = [{"field": q["field"], "question": q.get("question", q["field"]),
                "answer": "Use the following supplied facts for this field; any unlisted detail is unavailable. " + facts}
                for q in analysis.get("questions", []) if q.get("field")]
            response = await client.post("/api/app/agents/build-employee", json=body)
            result = response.json()
            write(f"agents/{business['id']}-build.json", {"request": body, "status": response.status_code, "body": result})
            if response.status_code != 200:
                raise RuntimeError(f"Agent creation failed: {business['id']} HTTP {response.status_code}: {str(result)[:700]}")
        aid = result["agentId"]
        snapshot = await compiled_brain_service.get_active_for_agent(aid)
        record = {**business, "tenant_id": str(tid), "user_id": str(uid), "agent_id": str(aid),
                  "snapshot": snapshot, "principal": principal}
        records[business["id"]] = record
        write(f"agents/{business['id']}-published.json", {k: v for k, v in record.items() if k != "principal"})
        progress("creation_complete", business=business["id"], version=snapshot.get("compiled_version"))
    return records


def install_boundaries():
    """Leave orchestration, authorization, journal, memory and lifecycle methods real."""
    from server.services.tool_router import tool_router
    async def external_action(*, tenant_id, action_name, params, **kwargs):
        case = CURRENT
        if not case or str(tenant_id) != case["agent"]["tenant_id"]:
            raise RuntimeError("External mock rejected foreign audit tenant")
        row = {"name": action_name, "params": copy.deepcopy(params), "turn": case["turn_index"], "at": time.monotonic()}
        case["external_actions"].append(row)
        if case["scenario"]["integration"] == "failure":
            result = {"status": "unknown", "message": "The external action timed out; its result is unconfirmed."}
        elif action_name.endswith("FIND_FREE_SLOTS"):
            date = params["date"]
            duration = int(params.get("duration") or 30)
            starts = [datetime.fromisoformat(f"{date}T{hour}:00:00+05:30") for hour in ("10", "14")]
            result = {"status": "success", "date": date, "slots": [
                {"start": start.isoformat(), "end": (start + timedelta(minutes=duration)).isoformat()}
                for start in starts]}
        elif action_name.endswith("CREATE_EVENT"):
            result = {"status": "confirmed", "event_id": "audit-event-" + uuid.uuid4().hex[:10],
                      "start": params["start"], "end": params["end"], "confirmed": True}
        elif action_name == "HUBSPOT_CREATE_CONTACT":
            result = {"status": "created", "contact_id": "audit-contact-" + uuid.uuid4().hex[:10], "saved": True}
        else:
            result = {"status": "error", "message": "This fixture has no implementation for that action."}
        row["result"] = result
        return result
    tool_router.nango.execute_in_call_tool = external_action

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
            if CURRENT:
                CURRENT["speech"].append({"turn": CURRENT["turn_index"], "text": text, "at": time.monotonic()})
                from server.call.call_context import get
                ctx = get(self.voice.call_id)
                if ctx and ctx.agent_hangup_armed:
                    CURRENT["farewell_events"].append({"text": text, "turn": CURRENT["turn_index"], "at": time.monotonic()})
                    if CURRENT["scenario"]["kind"] == "farewell_resume" and not CURRENT.get("resume_injected"):
                        CURRENT["resume_injected"] = True
                        self.voice._queue_user_transcript("ఆగండి, ఇంకో ప్రశ్న ఉంది. ఇన్‌స్పెక్షన్ ఫీజు ఎంత?")
                        CURRENT["events"].append({"kind": "caller_resumed_during_farewell"})
            self.voice.playback.until = time.monotonic() + 0.015
            # Transport-only silence lets the production loop observe delivery, without a TTS request.
            await self.voice._emit_agent_wire(b"\0" * 320)
        async def finish(self):
            return None
        async def end_turn(self):
            return None
        async def close(self):
            self._closed = True

    import server.services.pstn_turn_tts as tts
    tts.PstnTurnTtsSession = TextTts
    from server.call.live_turn_orchestrator import live_turn_orchestrator
    original = live_turn_orchestrator.handle_user_turn_stream
    async def observed_turn(**kwargs):
        async for item in original(**kwargs):
            if CURRENT and item.get("done"):
                CURRENT["done_events"].append(copy.deepcopy(item))
            yield item
    live_turn_orchestrator.handle_user_turn_stream = observed_turn
    original_gate = live_turn_orchestrator._gate_end_call
    def observed_gate(raw, **kwargs):
        result = original_gate(raw, **kwargs)
        if CURRENT:
            CURRENT["gates"].append({"turn": CURRENT["turn_index"], "proposal": raw, "result": result,
                                    "transcript": kwargs.get("transcript"), "at": time.monotonic()})
        return result
    live_turn_orchestrator._gate_end_call = observed_gate
    original_after = live_turn_orchestrator._after_assistant
    async def observed_after(*args, **kwargs):
        active_case = CURRENT
        await original_after(*args, **kwargs)
        if active_case:
            active_case["memory_commits"].append({"turn_seq": kwargs.get("turn_seq"), "at": time.monotonic()})
    live_turn_orchestrator._after_assistant = observed_after
    # Observe the existing 75ms memory budget without changing it or injecting facts.
    from server.call.memory_manager import memory_manager
    original_snapshot = memory_manager.get_snapshot
    def observed_snapshot(call_id):
        timing = MEMORY_LOAD.get()
        started = time.monotonic()
        if timing is not None:
            timing["worker_start_s"] = started
        result = original_snapshot(call_id)
        if timing is not None:
            timing["worker_elapsed_s"] = time.monotonic() - started
        return result
    memory_manager.get_snapshot = observed_snapshot
    original_blocks = live_turn_orchestrator._memory_blocks
    async def observed_blocks(call_id, caller_text=""):
        started = time.monotonic()
        local = memory_manager.peek_snapshot(call_id) or {}
        timing = {"turn": CURRENT["turn_index"] if CURRENT else None, "start_s": started,
                  "local_facts_present": bool(local.get("facts"))}
        token = MEMORY_LOAD.set(timing)
        try:
            projection, rolling = await original_blocks(call_id, caller_text)
            timing.update(elapsed_s=time.monotonic() - started,
                          projection_chars=len(projection or ""), rolling_chars=len(rolling or ""))
            if CURRENT:
                CURRENT.setdefault("memory_loads", []).append(timing)
            return projection, rolling
        finally:
            MEMORY_LOAD.reset(token)
    live_turn_orchestrator._memory_blocks = observed_blocks
    return TextPlayback


async def configure_case(agent, scenario):
    from sqlalchemy import delete
    from server.db.connection import get_session_factory
    from server.db.models.integration_models import TenantIntegration, AgentIntegration
    from server.services.saas.followup_policy import FollowUpConfig
    from server.services.saas.followup_service import read_policy, save_policy
    from server.services.tenant_tool_cache import invalidate
    tid, aid = uuid.UUID(agent["tenant_id"]), uuid.UUID(agent["agent_id"])
    async with get_session_factory()() as db:
        await db.execute(delete(AgentIntegration).where(AgentIntegration.tenant_id == tid, AgentIntegration.agent_id == aid))
        await db.execute(delete(TenantIntegration).where(TenantIntegration.tenant_id == tid))
        if scenario["integration"] != "none":
            apps = {"HUBSPOT": ["HUBSPOT_CREATE_CONTACT"], "GOOGLECALENDAR": ["GOOGLECALENDAR_FIND_FREE_SLOTS", "GOOGLECALENDAR_CREATE_EVENT"]}
            for name, tools in apps.items():
                db.add(TenantIntegration(tenant_id=tid, app_name=name, connection_id="audit-" + uuid.uuid4().hex,
                                        status="ACTIVE", metadata_={"gateway_verified": True}))
                db.add(AgentIntegration(tenant_id=tid, agent_id=aid, app_name=name,
                                       action_whitelist=tools, timing_mode="in_call", enabled=True))
        await db.commit()
    invalidate(str(tid))
    before = await read_policy(tid, aid)
    config = FollowUpConfig(enabled=scenario["policy"] != "disabled",
        callbackMode="automatic" if scenario["policy"] == "automatic" else "review", missedMode="off",
        timezone="Asia/Kolkata", weekdays=list(range(7)), startTime="00:00", endTime="23:59",
        maxAttempts=2, cooldownMinutes=30)
    await save_policy(agent["principal"], aid, config, before["revision"], True)


async def caller_turn(scenario, history, index, stack):
    if scenario.get("fixed_turns"):
        return {"utterance": scenario["fixed_turns"][index - 1],
                "intends_end": index == len(scenario["fixed_turns"]),
                "intent": "Focused reproducible stimulus; actual business response remains live", "elapsed_s": 0}
    from server.providers import get_provider_registry
    from server.providers.base import LLMConfig
    adapter = get_provider_registry().get_llm(stack.llm.provider)
    token = ACTOR.set("caller")
    try:
        messages = [{"role": "system", "content": CALLER_SYSTEM}, {"role": "user", "content": json.dumps({
            "customer_profile": CUSTOMERS[scenario["business"]], "private_goal": scenario["goal"],
            "turn_number": index, "maximum_turns": scenario["max_turns"],
            "current_time_India": now().astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kolkata")).isoformat(),
            "actual_conversation": history,
            "instruction": "Generate your next customer utterance based on the last actual answer. On the final permitted turn, explicitly end the call unless your opt-out/refusal already does so."}, ensure_ascii=False)}]
        started, result = time.monotonic(), None
        async with asyncio.timeout(40):
            result = await adapter.structured_completion(messages, CALLER_SCHEMA,
                LLMConfig(provider=stack.llm.provider, model=stack.llm.model, temperature=0.5),
                api_mode=stack.llm.config.get("api_mode"), schema_name="audit_customer", max_output_tokens=400)
            if not isinstance(result, dict) or not result.get("utterance"):
                raise RuntimeError("Caller LLM did not return a valid utterance")
        if result is None:
            raise RuntimeError("Caller LLM ended without a complete response")
        result["elapsed_s"] = round(time.monotonic() - started, 3)
        return result
    finally:
        ACTOR.reset(token)


async def db_evidence(case):
    from sqlalchemy import select, inspect
    from server.db.connection import get_session_factory
    from server.db.models.entities import Call, CallCallback
    from server.db.models.phase5_models import DncEntry
    from server.db.models.followup_models import FollowUpJob, LeadAssessment
    from server.db.models.saas_models import Lead
    from server.db.models.integration_models import ToolExecution
    tid, aid = uuid.UUID(case["agent"]["tenant_id"]), uuid.UUID(case["agent"]["agent_id"])
    cid = uuid.UUID(case["call_id"])
    result = {}
    async with get_session_factory()() as db:
        for name, cls, filters in [
            ("call", Call, [Call.tenant_id == tid, Call.call_id == cid]),
            ("callbacks", CallCallback, [CallCallback.tenant_id == tid, CallCallback.original_call_id == cid]),
            ("jobs", FollowUpJob, [FollowUpJob.tenant_id == tid, FollowUpJob.agent_id == aid, FollowUpJob.phone == case["phone"]]),
            ("dnd", DncEntry, [DncEntry.tenant_id == tid, DncEntry.phone_e164 == case["phone"]]),
            ("leads", Lead, [Lead.tenant_id == tid, Lead.agent_id == str(aid), Lead.phone == case["phone"]]),
            ("tools", ToolExecution, [ToolExecution.tenant_id == tid, ToolExecution.call_id == str(cid)]),
            ("assessments", LeadAssessment, [LeadAssessment.tenant_id == tid, LeadAssessment.source_call_id == str(cid)]),
        ]:
            rows = (await db.scalars(select(cls).where(*filters))).all()
            result[name] = [{attr.key: getattr(row, attr.key) for attr in inspect(row).mapper.column_attrs} for row in rows]
    return result


async def run_case(agent, scenario, stack, index):
    global CURRENT
    from server.call.call_brain_lock import resolve_locked_compiled_brain
    from server.call.call_context import CallContext, put
    from server.call.call_ledger import call_ledger
    from server.call.memory_manager import memory_manager
    from server.call.call_store import call_store
    from server.call.call_end_policy import normalize_call_end_policy
    from server.call.call_lifecycle_service import call_lifecycle_service
    from server.call.paths import relative_storage_path
    from server.services.composed_voice_session import composed_system_prompt
    from server.services.pstn_voice_core import PstnVoiceLoop, PHASE_LISTENING, PHASE_ENDED
    from server.agent.conversation_manager import conversation_manager
    from server.brain.capabilities import agent_available_tools

    await configure_case(agent, scenario)
    cid, sid = str(uuid.uuid4()), "adaptive-" + uuid.uuid4().hex
    phone = f"+120255501{index:02d}"
    version, brain, source = await resolve_locked_compiled_brain(agent["agent_id"], session_id=sid)
    if not brain:
        raise RuntimeError("Published brain unavailable at admission")
    context = CallContext(call_id=cid, tenant_id=agent["tenant_id"], agent_id=agent["agent_id"],
        session_id=sid, channel="pstn", direction="outbound", environment="development", tier="medium",
        resolved_stack=stack, compiled_brain_version=version, compiled_brain_text=brain, started_at=now(),
        storage_path=relative_storage_path(cid), pipeline="composed_voice",
        call_end_policy=normalize_call_end_policy(None, language="te-IN"))
    put(context)
    await call_store.insert(context.to_public_dict() | {"is_test": True, "finalization_status": "pending"})
    await call_ledger.init(cid, context.to_public_dict() | {"caller_id": "+12025550100", "callee_e164": phone,
        "audit": True, "is_test": True, "call_end_policy": context.call_end_policy})
    memory_manager.init(cid)
    opening = "నమస్తే, " + agent["agent_name"] + " మాట్లాడుతున్నాను. మీకు ఏ వివరాలు కావాలి?"
    # Voice preparation is outside this text-only test. Seed an already-delivered opening explicitly.
    conversation_manager.add_turn(sid, "", opening)
    case = {"scenario": scenario, "agent": {k: v for k, v in agent.items() if k not in {"principal", "snapshot"}},
        "call_id": cid, "session_id": sid, "phone": phone, "brain_source": source, "brain_version": version,
        "turn_index": 0, "turns": [], "speech": [], "done_events": [], "gates": [], "external_actions": [],
        "farewell_events": [], "carrier": [], "events": [], "memory_commits": [], "started_at": now().isoformat(), "errors": []}
    CURRENT = case
    token = CASE.set(scenario["id"])
    ACTOR.set("agent")
    prompt = composed_system_prompt(context)
    case["brain_checksum"] = hashlib.sha256(brain.encode()).hexdigest()
    case["runtime_checksum"] = hashlib.sha256(prompt.encode()).hexdigest()
    case["available_tools"] = [t["name"] for t in await agent_available_tools(agent["agent_id"], brain, tenant_id=agent["tenant_id"])]
    (OUT / "sessions").mkdir(exist_ok=True)
    (OUT / "sessions" / (scenario["id"] + "-prompt.txt")).write_text(prompt, encoding="utf-8")
    async def wire(_frame):
        return None
    playback = PLAYBACK()
    voice = PstnVoiceLoop(session_id=sid, call_id=cid, on_agent_wire=wire, playback=playback,
                          sample_rate=16000, tts_output_codec="linear16", stack_override=stack.to_safe_dict())
    voice._intro_phase, voice._phase = False, PHASE_LISTENING
    async def hangup():
        event = {"turn": case["turn_index"], "at": time.monotonic(), "playback_active": playback.is_active(),
                 "pending": bool(voice._pending_transcript)}
        case["carrier"].append(event)
        if scenario["kind"] == "carrier_failure" and len(case["carrier"]) == 1:
            event["acknowledged"] = False
            raise TimeoutError("Isolated carrier acknowledgement failure")
        event["acknowledged"] = True
    voice.set_hangup_handler(hangup)
    history = [{"role": "representative", "text": opening}]
    began, request_start = time.monotonic(), len(REQUESTS)
    progress("case_start", case=scenario["id"], tools=case["available_tools"])
    try:
        for turn in range(1, scenario["max_turns"] + 1):
            if voice._phase == PHASE_ENDED or context.status != "active":
                break
            case["turn_index"] = turn
            if scenario["kind"] == "revoked" and turn == 2:
                from sqlalchemy import update
                from server.db.connection import get_session_factory
                from server.db.models.integration_models import AgentIntegration
                from server.services.tenant_tool_cache import invalidate
                async with get_session_factory()() as db:
                    await db.execute(update(AgentIntegration).where(AgentIntegration.tenant_id == uuid.UUID(agent["tenant_id"]))
                                     .values(enabled=False))
                    await db.commit()
                invalidate(agent["tenant_id"])
                case["events"].append({"kind": "permissions_revoked", "turn": turn})
            caller = await caller_turn(scenario, history, turn, stack)
            before = memory_manager.get_snapshot(cid)
            commits_before = len(case["memory_commits"])
            speech_start, done_start, req_start = len(case["speech"]), len(case["done_events"]), len(REQUESTS)
            turn_start = time.monotonic()
            if scenario["kind"] == "thinking_interrupt" and turn == 1:
                from server.call.turn_coordinator import track, drain
                active = track(cid, voice._run_turn(caller["utterance"]))
                deadline = time.monotonic() + 10
                while len(REQUESTS) == req_start and time.monotonic() < deadline:
                    await asyncio.sleep(0.002)
                continuation = "ముందు చెప్పింది మార్చుతున్నాను. నాకు split AC కాదు, window AC service కావాలి. దాని ధర ఎంత?"
                case["events"].append({"kind": "caller_interrupt_while_thinking", "text": continuation,
                    "phase": voice._phase, "queued_speech_before": len(case["speech"]) - speech_start})
                await voice._think_cancel(continuation, immediate=True)
                await asyncio.wait_for(active, timeout=100)
                await asyncio.wait_for(drain(cid), timeout=100)
            else:
                await asyncio.wait_for(voice._run_turn(caller["utterance"]), timeout=100)
            if voice._background_hangup_task:
                await asyncio.wait_for(asyncio.shield(voice._background_hangup_task), timeout=65)
            # A resumption may schedule the follow-up through the production queue.
            from server.call.turn_coordinator import drain
            await asyncio.wait_for(drain(cid), timeout=100)
            memory_deadline = time.monotonic() + 3
            while len(case["memory_commits"]) == commits_before and time.monotonic() < memory_deadline:
                await asyncio.sleep(0.025)
            after = memory_manager.get_snapshot(cid)
            speech = case["speech"][speech_start:]
            reply = " ".join(s["text"] for s in speech).strip()
            row = {"turn": turn, "caller": caller, "spoken": reply, "elapsed_s": round(time.monotonic() - turn_start, 3),
                "memory_before": before, "memory_after": after, "projection_log": memory_manager.projection_at_turn(cid, len(call_ledger.read_lines(cid))),
                "request_indexes": list(range(req_start, len(REQUESTS))), "done": case["done_events"][done_start:],
                "context_status": context.status, "voice_phase": voice._phase, "armed": context.agent_hangup_armed}
            case["turns"].append(row)
            history.extend([{"role": "customer", "text": caller["utterance"]}, {"role": "representative", "text": reply}])
            write(f"sessions/{scenario['id']}.json", case)
            progress("turn", case=scenario["id"], turn=turn, seconds=row["elapsed_s"], reply_chars=len(reply),
                     memory_facts=len(after.get("facts") or {}), carrier_acks=sum(x.get("acknowledged", False) for x in case["carrier"]))
            if scenario["kind"] == "carrier_failure" and case["carrier"] and not any(x.get("acknowledged") for x in case["carrier"]):
                case["events"].append({"kind": "state_after_failed_ack", "status": context.status, "phase": voice._phase})
                await voice._finish_agent_hangup(reason="goodbye")
                if voice._background_hangup_task:
                    await voice._background_hangup_task
        # Do not manufacture a successful agent hangup if it never proposed one.
        case["ended_by_agent"] = bool(any(e.get("acknowledged") for e in case["carrier"]))
        if context.status == "active":
            case["events"].append({"kind": "audit_caller_transport_closed", "reason": "max_turns_or_error"})
            await call_lifecycle_service.end(cid, reason="user_stop")
        deadline = time.monotonic() + 70
        while time.monotonic() < deadline:
            from server.call.post_call_pipeline import read_outcome
            outcome = read_outcome(cid)
            stored = await call_store.get(cid)
            if outcome and stored and stored.get("finalization_status") in {"complete", "failed"}:
                break
            await asyncio.sleep(0.2)
        case["outcome"] = read_outcome(cid)
        case["db"] = await db_evidence(case)
        case["metadata"] = call_ledger.read_meta(cid)
        case["ledger"] = call_ledger.read_lines(cid)
    except Exception as exc:
        case["errors"].append({"kind": type(exc).__name__, "message": str(exc)[:900]})
        progress("case_error", case=scenario["id"], kind=type(exc).__name__, message=str(exc)[:250])
        if context.status == "active":
            await call_lifecycle_service.end(cid, reason="user_stop")
        await asyncio.sleep(0.5)
        case["db"] = await db_evidence(case)
        case["metadata"] = call_ledger.read_meta(cid)
    finally:
        case["wall_elapsed_s"] = round(time.monotonic() - began, 3)
        case["simulated_exchange_timeline_s"] = 20 * len(case["turns"])
        case["request_count"] = len(REQUESTS) - request_start
        write(f"sessions/{scenario['id']}.json", case)
        write("requests.json", REQUESTS)
        write("network.json", NETWORK)
        await voice.close()
        CASE.reset(token)
        CURRENT = None
    return case


async def main():
    global PLAYBACK
    settings, stack, manifest = await setup()
    progress("isolated_ready", schema=manifest["schema"], model=stack.llm.model, memory=settings.working_memory_enabled)
    PLAYBACK = install_boundaries()
    agents = await create_agents()
    cases = matrix()
    selected = os.getenv("AUDIT_CASES")
    if selected:
        cases = [c for c in cases if c["id"] in selected.split(",")]
    write("case-plan.json", cases)
    for index, scenario in enumerate(cases, 1):
        prior = OUT / f"sessions/{scenario['id']}.json"
        if prior.is_file():
            write("attempts/" + scenario["id"] + "-" + uuid.uuid4().hex[:8] + ".json", json.loads(prior.read_text(encoding="utf-8")))
        case_index = next(i + 1 for i, item in enumerate(matrix()) if item["id"] == scenario["id"])
        result = await run_case(agents[scenario["business"]], scenario, stack, case_index)
        RESULTS.append({"id": scenario["id"], "turns": len(result["turns"]), "errors": result["errors"],
                        "agent_closed": result.get("ended_by_agent"), "elapsed_s": result["wall_elapsed_s"]})
        write("results-index.json", RESULTS)
        progress("case_complete", **RESULTS[-1])
    after_source = source_manifest()
    write("source-drift.json", {p: [old, after_source.get(p)] for p, old in manifest["source_hashes"].items()
                               if after_source.get(p) != old})
    write("requests.json", REQUESTS)
    write("network.json", NETWORK)
    from server.db.connection import close_db
    await close_db()
    progress("finished", scenarios=len(RESULTS), caller_requests=sum(r["actor"] == "caller" for r in REQUESTS),
             agent_requests=sum(r["actor"] == "agent" for r in REQUESTS))


if __name__ == "__main__":
    asyncio.run(main())
