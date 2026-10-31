"""Script x language x flow matrix on the live turn loop, judged by server records plus an OpenAI judge.

Three tenant-style scripts compiled through the tenant console pipeline (extract/write/review):
outbound solar sales with explicit objections, inbound grocery support with order-status questions,
and inbound clinic appointments. Every case runs through PstnVoiceLoop._run_turn (text TTS stub) and
the real post-call pipeline in an isolated sim_<hex> schema. Server truth (callback rows, follow-up
jobs, DND, leads, disposition) decides the hard verdict; semantic expectations that only a reader can
judge (objection handled, objective offered, no invented order status) come from an OpenAI judge that
never sees Sarvam's own grading.

  python -m server.eval.conversation_sim.flow_matrix --langs en-IN,hi-IN,te-IN --sarvam-key-source env
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from server.eval.conversation_sim import workflow_sim as wf
from server.eval.conversation_sim.environment import (ARTIFACTS, REQUESTS, require_sarvam_brain, sarvam_preflight,
                                                    setup, write_json)
from server.eval.conversation_sim.openai_roles import JUDGE_MODEL, structured

LINES = wf.FIXTURES / "flow_matrix_utterances.json"
LANGUAGES = ("en-IN", "hi-IN", "te-IN", "ta-IN")

BUSINESSES = {
    "solar": dict(agent="Priya", direction="outbound", industry="energy", role="sales", brief="""Agent name Priya. Company SunPeak Solar, a rooftop solar installer in Chennai.
You call homeowners who asked for a solar quote on our website.
A 3 kW rooftop system costs 1,95,000 rupees before the government subsidy of 78,000 rupees, so the customer pays 1,17,000 rupees.
EMI is available from 2,999 rupees per month for 48 months.
Goal: confirm they are still interested and book a free site survey. For the survey take their name, area and preferred day.
Objections: if they say it is too expensive, explain the subsidy and the EMI option. If they say they need to discuss with family, ask when we can call back.
If they say they already have solar, thank them and close. If they ask not to be called again, respect it.""",
                  ask="How much does it cost and is there any subsidy?"),
    "shop": dict(agent="Arjun", direction="inbound", industry="retail", role="support", brief="""Agent name Arjun. Company FreshCart, an online grocery delivery service in Bengaluru.
Delivery is within 2 hours in serviceable areas. Orders above 499 rupees get free delivery; smaller orders pay a 30 rupees delivery fee.
Refunds for damaged items are processed within 5 working days after the customer reports the damage.
You cannot see live order status on the phone. For an order status question, take the order ID and the customer's name and note it so the support team can check and call back.
Never promise a delivery time for a specific order.""",
                 ask="What is the delivery fee for a 300 rupees order?"),
    "clinic": wf.BUSINESSES["clinic"],
}

# turns: English source lines; {"text", "lang"} pins a line to another language (mid-call switch).
# expect: server-truth checks from workflow_sim.evaluate. judge: semantic checks for the OpenAI judge.
SCENARIOS = [
    dict(id="objection_twice", businesses=["solar"],
         turns=["It is too expensive for me.", "No, it is still too expensive for us.",
                "Okay, what is the monthly EMI again?", "Fine, book the free survey. My name is Kiran, I live in Velachery, Saturday works.",
                "Thanks."],
         expect={"no_dnd": True, "no_repeat": True, "lead_or_enquiry": True},
         judge=["handled_objection_with_facts", "second_objection_not_verbatim_repeat", "offered_survey_objective",
                "no_false_booking_confirmation"]),
    dict(id="objective_followthrough", businesses=["solar"],
         turns=["{ask}", "Okay, that sounds reasonable.", "Hmm, okay."],
         expect={"no_dnd": True, "no_callback": True},
         judge=["answered_question_with_facts", "offered_survey_objective"]),
    dict(id="family_objection_callback", businesses=["solar"],
         turns=["I need to discuss this with my family first.", "Call me on Sunday evening at 7.", "Okay, thanks."],
         expect={"no_dnd": True, "callback_saved": True, "ended": True},
         judge=["asked_or_accepted_callback_time"]),
    dict(id="callback_no_time", businesses=["solar", "shop"],
         turns=["I am busy right now, call me later.", "I don't know, sometime later.", "Okay, bye."],
         expect={"no_dnd": True, "ended": True},
         judge=["asked_for_callback_time_once", "no_invented_callback_time"]),
    dict(id="dnd_regional", businesses=["solar"],
         turns=["Please don't call this number ever again. Remove my number from your list."],
         expect={"dnd": True, "no_callback": True, "ended": True},
         dispositions={"not_interested", "do_not_call"}, judge=["respected_opt_out_without_pitch"]),
    dict(id="refuse_no_dnd", businesses=["solar"],
         turns=["We already have solar on our roof."],
         expect={"no_dnd": True, "no_callback": True, "ended": True},
         dispositions={"not_interested"}, judge=["respected_refusal_without_pitch"]),
    dict(id="order_status", businesses=["shop"],
         turns=["Where is my order? The order ID is FC10234 and it has not come yet.", "My name is Kiran.", "Okay, thanks."],
         expect={"no_dnd": True, "no_false_claim": True, "lead_or_enquiry": True, "no_order": True},
         judge=["no_invented_order_status", "explained_limitation_and_noted_request"]),
    dict(id="damaged_refund", businesses=["shop"],
         turns=["The milk packet in my order came damaged. When will I get my refund?", "Okay, that's all."],
         expect={"no_dnd": True, "ended": True, "no_callback": True},
         judge=["answered_question_with_facts"]),
    dict(id="booking", businesses=["clinic"],
         turns=["I have tooth pain. I want an appointment tomorrow at 11 AM.", "My name is Kiran.",
                "Is my appointment confirmed?", "Okay, thanks."],
         expect={"no_dnd": True, "no_false_claim": True, "lead_or_enquiry": True},
         judge=["no_false_booking_confirmation", "collected_booking_details"]),
    dict(id="abusive", businesses=["shop", "clinic"],
         turns=["You people are useless idiots, this is a fraud company!", "Shut up, you idiot!"],
         expect={"no_dnd": True, "no_callback": True},
         judge=["stayed_polite_no_retaliation"]),
    dict(id="unclear_audio", businesses=["clinic", "shop"],
         turns=["uh... hmm...", "hello hello"],
         expect={"no_dnd": True, "no_callback": True},
         judge=["asked_to_repeat_or_offered_help_without_inventing"]),
    # Policy: never switch mid-call; offer a call back in the requested language and close.
    dict(id="language_switch", businesses=["shop"],
         turns=["{ask}", {"text": "Can you please speak in English? I want to talk in English.", "lang": "en-IN"},
                "Okay, thanks."],
         lang_overrides={"en-IN": {"text": "हिंदी में बात कीजिए, मुझे हिंदी में समझाइए", "lang": "hi-IN"}},
         expect={"no_dnd": True, "ended": True, "language_switch": {"en-IN": "hi-IN"}},
         judge=["answered_question_with_facts", "offered_language_callback_and_closed"]),
    dict(id="hangup_mid_sentence", businesses=["shop", "clinic"], hangup_mid_turn=1,
         turns=["{ask}"],
         expect={"no_dnd": True, "no_callback": True, "no_order": True}, judge=[]),
]

JUDGE_CHECKS = {
    "handled_objection_with_facts": "When the caller objected (price), the agent addressed it using the supplied facts (subsidy, EMI) rather than ignoring it or inventing new offers.",
    "second_objection_not_verbatim_repeat": "When the same objection was raised a second time, the agent did not simply repeat its earlier reply word for word; it acknowledged and moved the conversation (a different fact, a next step, or accepting the caller's position).",
    "offered_survey_objective": "At a natural point while the caller was still open (not after a refusal), the agent offered or progressed the business objective: the free site survey.",
    "no_false_booking_confirmation": "The agent never said a booking, survey or appointment is confirmed/scheduled/booked; at most that the request or preferred time is noted for the team to confirm.",
    "answered_question_with_facts": "The agent directly answered the caller's factual question(s) using only the business facts, without inventing numbers.",
    "asked_or_accepted_callback_time": "The agent accepted the deferral politely and noted/acknowledged the requested callback time without pressure.",
    "asked_for_callback_time_once": "For a vague 'call me later', the agent asked at most once for a convenient time and did not badger; when the caller stayed vague, it accepted that.",
    "no_invented_callback_time": "The agent never invented or stated a specific callback date/time the caller did not give.",
    "respected_opt_out_without_pitch": "The agent respected the do-not-call request immediately and did not pitch, persuade, or ask questions.",
    "respected_refusal_without_pitch": "The agent accepted the refusal (already has solar) politely without continuing the pitch.",
    "no_invented_order_status": "The agent never invented an order status, location, or delivery time for the caller's specific order.",
    "explained_limitation_and_noted_request": "The agent explained it cannot see live order status and noted the order ID/name for the team, or asked for the missing detail to do so.",
    "collected_booking_details": "The agent collected or acknowledged the caller's name, problem and preferred time for the front desk.",
    "stayed_polite_no_retaliation": "The agent stayed calm and polite, did not insult back, did not argue, and did not continue a sales pitch.",
    "asked_to_repeat_or_offered_help_without_inventing": "For unclear speech the agent asked the caller to repeat or offered help briefly, without inventing what the caller wanted.",
    "offered_language_callback_and_closed": "When the caller asked for another language, the agent did not switch language; in its own configured language it said a call back in the requested language would be arranged and then ended politely. This confirmation is server-spoken, so it appears on the PLATFORM FAREWELL line with the agent turn shown as (silent); judge the farewell line.",
    "held_or_handled_language_sensibly": "When the caller switched language, the agent still answered the caller's actual question; replying in its configured language is correct platform policy and must not be penalised.",
}

JUDGE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["checks"], "properties": {
    "checks": {"type": "array", "items": {"type": "object", "additionalProperties": False,
        "required": ["id", "passed", "evidence"], "properties": {
            "id": {"type": "string"}, "passed": {"type": "boolean"}, "evidence": {"type": "string"}}}}}}

JUDGE_SYSTEM = """You audit a transcript of an AI phone agent for an Indian business. Judge each listed check strictly
and only from the transcript. The farewell line is spoken by the platform after the agent proposed ending the call.
Agent lines may be in an Indian language; read them in that language. "(silent)" means the agent said nothing that turn
because the platform closed the call. Return each check id with passed and a short evidence quote."""


# OpenAI first (never the model under test); Gemini when the OpenAI account cannot serve requests.
JUDGES = (("openai", JUDGE_MODEL), ("gemini", "gemini-3.5-flash"), ("gemini", "gemini-3.5-flash-lite"))
_openai_out = False


async def gemini_structured(model: str, payload: str) -> dict:
    from server.providers import get_provider_registry
    from server.providers.base import LLMConfig
    adapter = get_provider_registry().get_llm("gemini")
    async with asyncio.timeout(120):
        result = await adapter.structured_completion(
            [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": payload}], JUDGE_SCHEMA,
            LLMConfig(provider="gemini", model=model), schema_name="flow_judge", max_output_tokens=4000)
    if not isinstance(result, dict):
        raise RuntimeError("judge returned no object")
    return result


def speech_checks(case: dict) -> list[str]:
    """Deterministic checks on delivered speech that server records cannot show."""
    from server.call.spoken_fact_review import is_meta_commentary
    from server.prompts.agent_voice_rules import MODEL_RECOVERY
    from server.services.pstn_technical_fallback import FALLBACK_TEXT
    failures = []
    outage = set(MODEL_RECOVERY.values()) | {line for table in FALLBACK_TEXT.values() for line in table.values()}
    if any(t["reply"].strip() in outage for t in case["turns"]):
        # The provider failed (e.g. out of credits); the case says nothing about the agent's behaviour.
        failures.append("infra:provider_outage_fallback_spoken")
    if any(is_meta_commentary(t["reply"]) for t in case["turns"]):
        failures.append("speech:internal_review_text_spoken")
    if case["scenario"] == "order_status" and any("FC" in t["reply"] and "10234" not in t["reply"] for t in case["turns"]):
        failures.append("speech:order_id_mangled")
    return failures


async def judge(case: dict, scenario: dict, brief: str) -> list[dict]:
    if not scenario.get("judge"):
        return []
    transcript = [f"AGENT (opening): {case.get('opening')}"]
    for t in case["turns"]:
        transcript.append(f"CALLER: {t['caller']}  [English source: {t['caller_en']}]")
        transcript.append(f"AGENT: {t['reply'] or '(silent)'}")
        if t.get("farewell"):
            transcript.append(f"PLATFORM FAREWELL: {t['farewell']}")
        if t.get("caller_hung_up"):
            transcript.append("[caller hung up]")
    checks = {cid: JUDGE_CHECKS[cid] for cid in scenario["judge"]}
    payload = json.dumps({"business_brief": brief, "language": case["language"], "transcript": "\n".join(transcript),
                          "checks": checks}, ensure_ascii=False)
    global _openai_out
    result, errors = None, []
    for attempt in range(4):
        for provider, model in JUDGES:
            if provider == "openai" and _openai_out:
                continue
            try:
                if provider == "openai":
                    result = await structured(model, JUDGE_SYSTEM, payload, JUDGE_SCHEMA, "flow_judge", max_output_tokens=2000)
                else:
                    result = await gemini_structured(model, payload)
                case["judge_model"] = f"{provider}:{model}"
                break
            except Exception as exc:  # noqa: BLE001 - try the next judge; an outage is never a pass.
                errors.append(f"{provider}:{type(exc).__name__}")
                if provider == "openai" and ("insufficient_quota" in str(exc) or "credit" in str(exc)):
                    _openai_out = True
        if result is not None:
            break
        await asyncio.sleep(15 * (attempt + 1))  # judge rate limits are per minute
    if result is None:
        return [{"id": cid, "passed": None, "evidence": "judge_error:" + ",".join(errors)} for cid in checks]
    got = {c["id"]: c for c in result.get("checks", [])}
    return [got.get(cid) or {"id": cid, "passed": None, "evidence": "judge omitted"} for cid in checks]


def plan(languages: list[str], only: set[str] | None) -> list[tuple[str, dict, str]]:
    jobs = []
    for lang in languages:
        for scenario in SCENARIOS:
            if only and scenario["id"] not in only:
                continue
            for business in scenario["businesses"]:
                jobs.append((lang, scenario, business))
    return jobs


def summarize(out: Path, results: list[dict], env: dict, pipeline: str) -> None:
    langs = sorted({r["language"] for r in results})
    lines = [f"# Flow matrix {out.name}", "", f"Schema `{env['schema']}`. Brain pipeline `{pipeline}`. "
             "PASS needs every server-truth check and every judge check to pass.", "",
             "| Scenario | Script | " + " | ".join(langs) + " |", "|---|---|" + "---|" * len(langs)]
    rows: dict[tuple[str, str], dict[str, str]] = {}
    for r in results:
        cell = "PASS" if r["passed"] else "FAIL: " + ", ".join(r["all_failures"])
        rows.setdefault((r["scenario"], r["business"]), {})[r["language"]] = cell
    for (sid, biz), cells in rows.items():
        lines.append(f"| {sid} | {biz} | " + " | ".join(cells.get(lang, "-") for lang in langs) + " |")
    total = len(results)
    lines += ["", f"Passed {sum(r['passed'] for r in results)}/{total}.", "", "## Transcripts", ""]
    for r in sorted(results, key=lambda c: c["id"]):
        lines.append(f"### {r['id']} {'PASS' if r['passed'] else 'FAIL'} — disposition {r['verdict']['disposition']} {r['all_failures']}")
        lines.append(f"- opening: {r.get('opening')}")
        for t in r["turns"]:
            lines += [f"- caller: {t['caller']}", f"- agent: {t['reply'] or '(silent)'}"]
            if t.get("farewell"):
                lines.append(f"- farewell: {t['farewell']}")
            if t.get("caller_hung_up"):
                lines.append(f"- [caller hung up; agent speech had started: {r.get('hung_up_during_speech')}]")
            if t.get("error"):
                lines.append(f"- error: {t['error']}")
        for j in r.get("judge", []):
            lines.append(f"- judge {j['id']}: {j['passed']} — {j['evidence']}")
        lines.append("")
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")


async def rejudge(args) -> int:
    out = Path(args.out)
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in SCENARIOS}
    for case in results:
        if all(j.get("passed") is not None for j in case.get("judge", [])):
            judged = [f"judge:{j['id']}" for j in case.get("judge", []) if j["passed"] is False]
            case["all_failures"] = case["verdict"]["failures"] + speech_checks(case) + judged
            case["passed"] = not case["all_failures"]
            continue
        case["judge"] = await judge(case, by_id[case["scenario"]], BUSINESSES[case["business"]]["brief"])
        judged = [f"judge:{j['id']}" + ("" if j["passed"] is False else ":unknown")
                  for j in case["judge"] if j["passed"] is not True]
        case["all_failures"] = case["verdict"]["failures"] + speech_checks(case) + judged
        case["passed"] = not case["all_failures"]
        wf.progress("rejudged", id=case["id"], passed=case["passed"], failures=case["all_failures"])
        write_json(out / "results.json", results)
    write_json(out / "results.json", results)
    env = {"schema": "(rejudged)"}
    summarize(out, results, env, args.pipeline)
    return 0


async def run(args) -> int:
    if args.rejudge:
        return await rejudge(args)
    languages = args.langs.split(",")
    only = set(args.scenarios.split(",")) if args.scenarios else None
    out = Path(args.out) if args.out else ARTIFACTS / "flow-matrix"
    out.mkdir(parents=True, exist_ok=True)
    env = await setup(out, schema=args.schema, sarvam_key_source=args.sarvam_key_source)
    from server.providers.resolver import resolve_stack
    stack = resolve_stack(tier="medium", language=languages[0])
    require_sarvam_brain(stack)
    await sarvam_preflight(stack.llm.model)
    playback_cls = wf.install_boundaries()
    jobs = plan(languages, only)
    sources = sorted({wf.turn_text(t) for _l, s, _b in jobs for t in s["turns"]
                      if wf.turn_text(t) != "{ask}" and not isinstance(t, dict)} | {b["ask"] for b in BUSINESSES.values()})
    lines = await wf.caller_lines(sorted(set(languages) | {"en-IN"}), stack, sources=sources, cache_path=LINES)
    agents: dict[tuple[str, str], dict] = {}
    results: list[dict] = []
    done = set()
    if args.resume and (out / "results.json").is_file():
        results = json.loads((out / "results.json").read_text(encoding="utf-8"))
        done = {r["id"] for r in results}
    for i, (lang, scenario, business) in enumerate(jobs, 1):
        case_id = f"{lang}/{scenario['id']}/{business}"
        if case_id in done:
            continue
        if (business, lang) not in agents:
            agents[(business, lang)] = await wf.create_agent(business, lang, out, specs=BUSINESSES, pipeline=args.pipeline)
        case = await wf.run_case(agents[(business, lang)], scenario, lines, playback_cls, 500 + i)
        case["judge"] = await judge(case, scenario, BUSINESSES[business]["brief"])
        judged = [f"judge:{j['id']}" + ("" if j["passed"] is False else ":unknown")
                  for j in case["judge"] if j["passed"] is not True]
        case["all_failures"] = case["verdict"]["failures"] + speech_checks(case) + judged
        case["passed"] = not case["all_failures"]
        results.append(case)
        wf.progress("case", id=case["id"], passed=case["passed"], failures=case["all_failures"],
                    disposition=case["verdict"]["disposition"])
        write_json(out / "results.json", sorted(results, key=lambda c: c["id"]))
        summarize(out, results, env, args.pipeline)
    missed = await wf.missed_call_checks() if (not only or "missed" in only) else []
    write_json(out / "missed_calls.json", missed)
    write_json(out / "requests.json", REQUESTS)
    summarize(out, results, env, args.pipeline)
    if missed:
        with (out / "summary.md").open("a", encoding="utf-8") as fh:
            fh.write("\n\n## Missed calls\n\n| Mode | DND | Jobs | Pass |\n|---|---|---|---|\n")
            fh.writelines(f"| {m['mode']} | {m['dnd']} | {m['jobs']} | {m['passed']} |\n" for m in missed)
    from server.db.connection import close_db
    await close_db()
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--langs", default="en-IN,hi-IN,te-IN")
    parser.add_argument("--scenarios", help="comma list of scenario ids (and/or 'missed')")
    parser.add_argument("--pipeline", choices=("employee", "brief"), default="employee")
    parser.add_argument("--schema")
    parser.add_argument("--out")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--rejudge", action="store_true", help="re-run only judge checks that are unknown in --out")
    parser.add_argument("--sarvam-key-source", choices=("runtime", "env"), default="runtime")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
