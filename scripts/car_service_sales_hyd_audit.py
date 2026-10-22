"""
Hyderabad car-service package sales agent: brief → script → brain → 14-turn critical audit.

Writes: CAR_SERVICE_SALES_HYD_14_TURN_AUDIT.md at repo root.
Run: python scripts/car_service_sales_hyd_audit.py
"""
from __future__ import annotations

import asyncio
import json
import traceback
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BRIEF = (
    "Create an English sales counselor named Karthik for DriveRight Auto Care in Hyderabad. "
    "Sell periodic car service packages and annual maintenance contracts (AMC) for hatchbacks "
    "and sedans. Workshop in Kukatpally with pickup from Hitec City and Gachibowli. "
    "Basic periodic service is three thousand five hundred rupees. "
    "Comprehensive service is six thousand five hundred rupees. "
    "AMC for twelve months is fourteen thousand rupees including three services. "
    "Interior detailing add-on is two thousand rupees. "
    "Help callers choose a package, answer fees first, book a service slot or free inspection, "
    "and capture vehicle model. Answer first. Never re-ask known facts. Never hard-sell. "
    "Never invent fees or claim a booking was completed unless confirmed. Language: en-IN."
)

SESSION = "car-service-sales-hyd-audit"
REPORT_PATH = ROOT / "CAR_SERVICE_SALES_HYD_14_TURN_AUDIT.md"

TURNS: list[dict] = [
    {
        "user": "Hi, I need a service package for my car.",
        "note": "Buying intent clear — no interest/why re-ask",
        "expect": ("at_most_one_question", "not_robot", "no_reask_known", "no_hangup"),
        "critical": ["interest re-ask", "robot opener"],
    },
    {
        "user": "It's a Honda City 2019 sedan. Mostly city driving in Hyderabad.",
        "note": "Dense dump — use model + city; do not checklist",
        "expect": ("at_most_one_question", "no_reask_known", "use_all_facts", "no_hangup"),
        "critical": ["re-ask model", "ignore sedan"],
    },
    {
        "user": "Weekday mornings work better for me — I can drop it before 10.",
        "note": "Availability given — do not re-ask when",
        "expect": ("at_most_one_question", "no_reask_known", "no_hangup"),
        "critical": ["re-ask slot"],
    },
    {
        "user": "What packages do you sell at DriveRight?",
        "note": "Packages question — answer first from known facts",
        "expect": ("no_qualify", "at_most_one_question", "no_reask_known", "no_hangup"),
        "critical": ["budget-first delay", "checklist"],
    },
    {
        "user": "How much is the basic periodic service?",
        "note": "Price ask — answer fee before more qualify",
        "expect": ("no_qualify", "at_most_one_question", "no_reask_known", "no_hangup"),
        "critical": ["delay price", "claim unknown fee"],
    },
    {
        "user": "That sounds okay. Do you pick up from Hitec City?",
        "note": "Soft yes + logistics — answer pickup fact",
        "expect": ("at_most_one_question", "no_reask_known", "no_hangup", "no_qualify"),
        "critical": ["ignore Hitec", "re-ask location"],
    },
    {
        "user": "I was thinking full AMC? Wait — actually just the basic service this time.",
        "note": "Correction / jump — latest intent wins",
        "expect": ("at_most_one_question", "no_reask_known", "no_hangup", "no_old_script"),
        "critical": ["cling to AMC", "restart"],
    },
    {
        "user": "Hmm",
        "note": "Hesitation — no new question / pitch",
        "expect": ("no_question", "no_are_you_there", "no_hangup", "short"),
        "critical": ["poke during hmm"],
    },
    {
        "user": "I'm not sure if I want the detailing add-on yet.",
        "note": "Soft hesitation — react; do not force upsell",
        "expect": ("react_hesitation", "at_most_one_question", "no_hangup"),
        "critical": ["hard upsell", "jump to name"],
    },
    {
        "user": "Can I book a free inspection first?",
        "note": "Natural next step — confirm inspection path",
        "expect": ("at_most_one_question", "no_reask_known", "no_hangup"),
        "critical": ["restart sales", "re-ask need"],
    },
    {
        "user": "Tomorrow morning around 9 works if you have a slot.",
        "note": "Day/time given — do not re-ask when",
        "expect": ("at_most_one_question", "no_reask_known", "no_hangup"),
        "critical": ["re-ask when"],
    },
    {
        "user": "Just send me the package prices on WhatsApp. I'll check them later.",
        "note": "Stop selling — honor send-details; no fake send",
        "expect": ("honor_next_step", "at_most_one_question", "no_hangup", "no_action_claim"),
        "critical": ["keep interrogating", "fake send"],
    },
    {
        "user": "I already told you weekday mornings — please don't ask again.",
        "note": "Frustration / already-told — acknowledge and move",
        "expect": ("ack_frustration", "no_reask_known", "no_hangup"),
        "critical": ["re-ask mornings"],
    },
    {
        "user": "Thanks, that's all for now. Bye.",
        "note": "Clear close — farewell + hangup",
        "expect": ("hangup", "no_question", "short"),
        "critical": ["stay pitching", "goodbye without end"],
    },
]


def _history_blob(rows: list[dict]) -> str:
    return " ".join(r["user"] for r in rows)


def _fee_present(text: str) -> bool:
    low = (text or "").lower()
    return (
        "three thousand five hundred" in low
        or "3500" in low
        or "3,500" in low
        or "rupees three thousand" in low
    )


async def main() -> int:
    from server.agent.brain_prompt_composer import BUDGET_MAX_TOKENS, estimate_tokens
    from server.agent.conversation_manager import conversation_manager
    from server.agent.instruction_builder import LIVE_TURN_DISCIPLINE
    from server.agent.instruction_store import instruction_store
    from server.brain.agent_script_compiler import (
        COMPILER_VERSION,
        compile_agent_from_brief,
        extract_company_from_brief,
        infer_agent_name,
        validate_agent_script,
    )
    from server.brain.sections import STATIC_OUTPUT_RULES_VERSION
    from server.prompts.conversation_policy import (
        infer_agent_role,
        judge_turn,
        strict_live_fails,
    )
    from server.services.openai_brain_service import generate_response

    issues: list[str] = []
    compile_mode = "llm"
    compile_error = ""

    print("Compiling car-service sales agent from brief (LLM script generation)...")
    try:
        compiled, result, raw_t, comp_t, budget = await compile_agent_from_brief(
            brief=BRIEF,
            language="en-IN",
            use_llm=True,
            budget_tokens=3500,
        )
    except Exception as exc:
        compile_error = f"{type(exc).__name__}: {exc}"
        print(f"LLM compile failed ({compile_error}); falling back to deterministic.")
        compile_mode = "deterministic_fallback"
        compiled, result, raw_t, comp_t, budget = await compile_agent_from_brief(
            brief=BRIEF,
            language="en-IN",
            use_llm=False,
            budget_tokens=3500,
        )

    role = infer_agent_role(BRIEF, llm_role=getattr(result, "detected_role", "") or "")
    company = extract_company_from_brief(BRIEF) or result.company_name
    name = result.agent_name or infer_agent_name(BRIEF)
    script = result.agent_script or ""

    quality = {
        "has_identity": "AGENT IDENTITY" in compiled,
        "has_live_guide": "LIVE CALL GUIDE" in compiled,
        "has_flow": "CONVERSATION FLOW" in compiled,
        "has_sales_flow": "SALES FLOW" in compiled or role == "sales",
        "role_is_sales": role == "sales",
        "company_parsed": bool(company) and "DriveRight" in (company or ""),
        "company_no_city_glue": "in Hyderabad" not in (company or ""),
        "name_parsed": "Karthik" in (name or ""),
        "budget_ok": 1024 <= comp_t <= BUDGET_MAX_TOKENS,
        "no_live_discipline_leak": LIVE_TURN_DISCIPLINE.strip() not in compiled,
        "fee_in_brain": _fee_present(compiled),
        "amc_in_brain": "fourteen thousand" in compiled.lower() or "amc" in compiled.lower(),
        "pickup_in_brain": "hitec" in compiled.lower() or "pickup" in compiled.lower(),
        "static_v24": STATIC_OUTPUT_RULES_VERSION == "sr_v24",
    }
    if not quality["role_is_sales"]:
        issues.append(f"Role inferred as `{role}` expected `sales`.")
    if not quality["company_parsed"]:
        issues.append(f"Company parse weak: got `{company!r}`.")
    if not quality["company_no_city_glue"]:
        issues.append(f"Company still includes city clause: `{company!r}`.")
    if not quality["fee_in_brain"]:
        issues.append("Basic service fee from brief not clearly present in compiled brain.")
    if not quality["budget_ok"]:
        issues.append(f"Brain tokens {comp_t} outside healthy budget (max {BUDGET_MAX_TOKENS}).")

    validator_fails = validate_agent_script(script, brief=BRIEF, agent_name=name)
    if validator_fails:
        issues.append(f"Script validator: {validator_fails}")

    instruction_store.save_brain_prompt(SESSION, compiled, budget_tokens=max(comp_t, 2500))
    conversation_manager.clear(SESSION)

    print(f"Compiled: role={role} name={name} company={company} tokens={comp_t} mode={compile_mode}")
    print("Running 14 live turns against compiled brain...")

    transcript_log: list[dict] = []
    for i, turn in enumerate(TURNS, start=1):
        user = turn["user"]
        hist = _history_blob(transcript_log)
        print(f"  turn {i}/{len(TURNS)}: {user[:60]}...")
        agent_text = ""
        end_call: dict = {"should_end": False}
        err = ""
        try:
            out = await generate_response(
                transcript=user,
                language_code="en-IN",
                session_id=SESSION,
                brain_prompt=compiled,
                openai_model="gpt-5.6-luna",
                max_output_tokens=180,
            )
            agent_text = (out.get("text") or "").strip()
            end_call = out.get("end_call") or {"should_end": False}
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            agent_text = f"[ERROR] {err}"
            issues.append(f"Turn {i} LLM error: {err}")

        expect = turn["expect"]
        fails = judge_turn(
            user=user,
            assistant=agent_text if not err else "",
            end_call=end_call,
            expect=expect,
            history=hist,
        )
        strict = strict_live_fails(
            user=user,
            assistant=agent_text if not err else "",
            end_call=end_call,
            expect=expect,
            history=hist,
        )
        if err:
            fails = list(dict.fromkeys([*fails, f"llm_error:{err[:120]}"]))
            strict = list(dict.fromkeys([*strict, f"llm_error:{err[:120]}"]))

        low = agent_text.lower()
        extra: list[str] = []
        if i == 5 and not _fee_present(agent_text) and (
            "don't have" in low or "do not have" in low or "check and get back" in low
        ):
            extra.append("heuristic: claimed fee unknown despite brief")
        if i == 12 and ("i'll have" in low and "shared" in low):
            extra.append("heuristic: soft WhatsApp send claim")
        if "sure!" in low or "absolutely!" in low:
            extra.append("heuristic: robot opener")
        if extra:
            fails = list(dict.fromkeys([*fails, *extra]))

        if fails or strict:
            issues.append(
                f"Turn {i} FAIL ({turn['note']}): judge={fails or 'ok'}; strict={strict or 'ok'}; "
                f"agent={agent_text[:160]!r}"
            )

        # generate_response already adds the turn — do not double-add.
        transcript_log.append(
            {
                "turn": i,
                "user": user,
                "agent": agent_text,
                "note": turn["note"],
                "expect": list(expect),
                "critical_focus": turn["critical"],
                "judge_fails": fails,
                "strict_fails": strict,
                "end_call": bool((end_call or {}).get("should_end")),
                "error": err,
            }
        )

    _write_audit(
        brief=BRIEF,
        script=script,
        compiled=compiled,
        role=role,
        name=name,
        company=company or "",
        compile_mode=compile_mode,
        compile_error=compile_error,
        raw_t=raw_t,
        comp_t=comp_t,
        budget=budget,
        quality=quality,
        validator_fails=validator_fails,
        transcript_log=transcript_log,
        issues=issues,
        result_meta={
            "optimizer_model": getattr(result, "optimizer_model", "") or "",
            "key_facts": list(getattr(result, "key_facts", None) or []),
            "role_summary": getattr(result, "role_summary", "") or "",
            "detected_role": getattr(result, "detected_role", "") or "",
            "compiler": COMPILER_VERSION,
            "static": STATIC_OUTPUT_RULES_VERSION,
        },
    )
    print(f"Wrote {REPORT_PATH}")
    print(f"Issues: {len(issues)}")
    return 1 if any(r["judge_fails"] or r["strict_fails"] or r["error"] for r in transcript_log) else 0


def _write_audit(
    *,
    brief: str,
    script: str,
    compiled: str,
    role: str,
    name: str,
    company: str,
    compile_mode: str,
    compile_error: str,
    raw_t: int,
    comp_t: int,
    budget: int,
    quality: dict[str, bool],
    validator_fails: list,
    transcript_log: list[dict],
    issues: list[str],
    result_meta: dict,
) -> None:
    from server.agent.brain_prompt_composer import estimate_tokens
    from server.brain.agent_script_compiler import COMPILER_VERSION
    from server.brain.sections import STATIC_OUTPUT_RULES_VERSION

    j_pass = sum(1 for r in transcript_log if not r["judge_fails"] and not r["strict_fails"] and not r["error"])
    q_pass = sum(1 for v in quality.values() if v)
    verdict = "PASS" if j_pass == len(transcript_log) and not issues else "FAIL / MIXED"
    if j_pass == len(transcript_log) and issues:
        verdict = "PASS with compile notes"

    lines: list[str] = []
    lines.append("# DriveRight Auto Care (Hyderabad) — Car Service Sales 14-Turn Audit")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}  ")
    lines.append(f"**Session:** `{SESSION}`  ")
    lines.append(f"**Compiler:** `{COMPILER_VERSION}`  ")
    lines.append(f"**STATIC rules:** `{STATIC_OUTPUT_RULES_VERSION}`  ")
    lines.append(f"**Compile mode:** `{compile_mode}`  ")
    lines.append(f"**Language:** `en-IN`  ")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(
        f"**{verdict}** — Conversation score **{j_pass}/{len(transcript_log)}** turns clean; "
        f"compile quality probes **{q_pass}/{len(quality)}**; "
        f"**{len(issues)}** issue note(s) logged below."
    )
    lines.append("")
    if compile_error:
        lines.append(f"> LLM compile error (fallback used): `{compile_error}`")
        lines.append("")
    lines.append("## Agent created")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Agent name | `{name}` |")
    lines.append(f"| Company | `{company}` |")
    lines.append(f"| Inferred role | `{role}` |")
    lines.append(f"| Brain tokens | `{comp_t}` / max `{budget}` (raw brief `{raw_t}`) |")
    lines.append(f"| Script tokens (est.) | `{estimate_tokens(script)}` |")
    lines.append(f"| Optimizer / model | `{result_meta.get('optimizer_model')}` |")
    lines.append(f"| Key facts (writer) | `{json.dumps(result_meta.get('key_facts') or [], ensure_ascii=False)}` |")
    lines.append("")
    lines.append("### Agent brief")
    lines.append("")
    lines.append("```")
    lines.append(brief.strip())
    lines.append("```")
    lines.append("")
    lines.append("## Compile / script quality")
    lines.append("")
    lines.append("| Probe | Pass |")
    lines.append("|-------|------|")
    for k, v in quality.items():
        lines.append(f"| `{k}` | {'PASS' if v else 'FAIL'} |")
    lines.append("")
    lines.append(f"Script validator findings: `{validator_fails or 'none'}`")
    lines.append("")
    lines.append("### Generated / bound script (excerpt)")
    lines.append("")
    lines.append("```")
    lines.append(script[:3500] + ("…" if len(script) > 3500 else ""))
    lines.append("```")
    lines.append("")
    lines.append("## Issues found (judge + audit notes)")
    lines.append("")
    if not issues:
        lines.append("No issues recorded.")
    else:
        for n, item in enumerate(issues, start=1):
            lines.append(f"{n}. {item}")
    lines.append("")
    lines.append("## Turn-by-turn transcript")
    lines.append("")
    for row in transcript_log:
        status = "PASS" if not row["judge_fails"] and not row["strict_fails"] and not row["error"] else "FAIL"
        lines.append(f"### Turn {row['turn']} — {status}")
        lines.append("")
        lines.append(f"**Intent / note:** {row['note']}  ")
        lines.append(f"**Critical focus:** {', '.join(row['critical_focus'])}  ")
        lines.append(f"**Expect tags:** `{', '.join(row['expect'])}`  ")
        lines.append(f"**end_call:** `{row['end_call']}`  ")
        lines.append("")
        lines.append("**User**")
        lines.append("")
        lines.append(f"> {row['user']}")
        lines.append("")
        lines.append("**Agent**")
        lines.append("")
        lines.append(f"> {row['agent']}")
        lines.append("")
        if row["judge_fails"] or row["strict_fails"] or row["error"]:
            lines.append("**Failures**")
            lines.append("")
            if row["error"]:
                lines.append(f"- LLM error: `{row['error']}`")
            for f in row["judge_fails"]:
                lines.append(f"- judge: {f}")
            for f in row["strict_fails"]:
                lines.append(f"- strict: {f}")
            lines.append("")
        else:
            lines.append("_Judge: clean._")
            lines.append("")
    lines.append("## Summary judgment")
    lines.append("")
    lines.append(
        "This audit exercises brief → script → brain compile, then a critical 14-turn "
        "car-service *sales* conversation (package intent, dense vehicle dump, fees, pickup, "
        "AMC→basic correction, hesitation, free inspection, WhatsApp send-details, frustration, goodbye)."
    )
    lines.append("")
    if j_pass == len(transcript_log):
        lines.append(
            "Live replies cleared the behavioral judge on all turns. Remaining notes (if any) "
            "are compile/identity probes rather than live conversation failures."
        )
    else:
        failed_turns = [r["turn"] for r in transcript_log if r["judge_fails"] or r["strict_fails"] or r["error"]]
        lines.append(f"Failed turns: {failed_turns}.")
    lines.append("")
    lines.append("### Brain excerpt (first 2k chars)")
    lines.append("")
    lines.append("```")
    idx = compiled.find("--- AGENT IDENTITY ---")
    excerpt = compiled[idx : idx + 2000] if idx >= 0 else compiled[:2000]
    lines.append(excerpt + ("…" if len(compiled) > 2000 else ""))
    lines.append("```")
    lines.append("")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception:
        traceback.print_exc()
        raise
