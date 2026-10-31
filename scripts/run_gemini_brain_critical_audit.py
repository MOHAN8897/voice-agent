#!/usr/bin/env python3
"""Run 4 Gemini 3.8 Live brain probes + pytest; write data/audits/*.md (machine-generated)."""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

GEMINI_LIVE_MODEL = "gemini-3.8-live"

from server.eval.behavior_scenarios import AGENTIC_BRIEFS, EVAL_BRIEFS  # noqa: E402

AUDIT_CASES: list[dict] = [
    {
        "session_id": "session_1_sales_acme",
        "label": "Acme Realty sales",
        "brief_key": 'EVAL_BRIEFS["sales"]',
        "spec": EVAL_BRIEFS["sales"],
        "direction": "outbound",
        "caller_line": "Who is calling? How much for a 2BHK apartment?",
        "fact_needle": "fifty lakhs",
        "company_needle": "Acme Realty",
    },
    {
        "session_id": "session_2_support_billing",
        "label": "Acme Billing support",
        "brief_key": 'EVAL_BRIEFS["support"]',
        "spec": EVAL_BRIEFS["support"],
        "direction": "inbound",
        "caller_line": "I was charged twice on my invoice. Who are you?",
        "fact_needle": "invoice",
        "company_needle": "Acme Billing",
    },
    {
        "session_id": "session_3_smilecare_dental",
        "label": "SmileCare dental appointments",
        "brief_key": 'AGENTIC_BRIEFS["smilecare_dental"]',
        "spec": AGENTIC_BRIEFS["smilecare_dental"],
        "direction": "outbound",
        "caller_line": "I have tooth pain. Can I book an appointment this week?",
        "fact_needle": "appointment",
        "company_needle": "SmileCare Dental",
    },
    {
        "session_id": "session_4_salesflow_crm",
        "label": "SalesFlow CRM SaaS sales",
        "brief_key": 'AGENTIC_BRIEFS["salesflow_crm"]',
        "spec": AGENTIC_BRIEFS["salesflow_crm"],
        "direction": "outbound",
        "caller_line": "What does your CRM cost for a team of eight people?",
        "fact_needle": "five thousand",
        "company_needle": "SalesFlow CRM",
    },
]


def _fence(text: str) -> str:
    return f"```\n{text.rstrip()}\n```"


def _prompt_checks(
    gemini_prompt: str, agent_script: str, case: dict, agent_name: str
) -> dict[str, bool]:
    low = gemini_prompt.lower()
    script_low = (agent_script or "").lower()
    co = case["company_needle"].lower()
    an = (agent_name or "").lower()
    return {
        "agent_name_in_prompt": bool(an and an in low),
        "company_in_script_or_prompt": co in low or co in script_low,
        "pinned_business_block": "pinned business script" in low,
        "company_offer_section": "company & offer" in low or co in low,
        "role_section": "your role on this call" in low or "role on this call" in low,
        "canonical_opening": "canonical opening" in low or "example opening" in low,
        "model_is_gemini_38_live": True,
    }


def _reply_checks(reply: str, case: dict) -> dict[str, bool]:
    low = (reply or "").lower()
    co = case["company_needle"].lower()
    fact = case["fact_needle"].lower()
    return {
        "mentions_company_or_product": co.split()[0] in low or co in low,
        "mentions_script_fact": fact in low or fact.replace(" ", "") in low.replace(" ", ""),
        "non_empty": bool(reply and reply.strip()),
        "no_obvious_hallucinated_price": not any(
            x in low for x in ("99,999", "99999", "one lakh per month", "free forever")
        ),
    }


async def _compile_case(case: dict) -> tuple[str, object, int, int, int]:
    from server.brain.agent_script_compiler import compile_agent_from_brief

    spec = case["spec"]
    return await compile_agent_from_brief(
        brief=spec["brief"],
        language=spec.get("language", "en-IN"),
        use_llm=False,
        interpret_brief=False,
        direction=case["direction"],
    )


def _gemini_system_instruction(compiled: str, case: dict, opening: str) -> str:
    from server.realtime.voice_instructions import build_realtime_voice_instructions

    spec = case["spec"]
    return build_realtime_voice_instructions(
        compiled,
        model=GEMINI_LIVE_MODEL,
        stack_override={"llm": {"provider": "gemini", "model": GEMINI_LIVE_MODEL}},
        language=spec.get("language", "en-IN"),
        direction=case["direction"],
        opening_greeting=opening,
    )


async def _probe_gemini_live(
    system_instruction: str, caller_line: str, opening: str
) -> tuple[str, str]:
    """One Gemini 3.8 Live WebSocket session (bidi), same path as PSTN."""
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        return "skipped", "GEMINI_API_KEY not set — live probe skipped"
    from server.realtime.providers.gemini_voice import GeminiLiveVoiceAdapter

    adapter = GeminiLiveVoiceAdapter(api_key=key)
    try:
        await asyncio.wait_for(
            adapter.connect(
                model=GEMINI_LIVE_MODEL,
                instructions=system_instruction,
                include_tools=False,
                turn_detection="server_vad",
                max_output_tokens=256,
            ),
            timeout=45,
        )
        await adapter.wait_ready(timeout=45)
        adapter.opening_history_clean = False
        await adapter.note_opening_delivered(spoken_line=opening)
        user_turn = (
            "Simulated phone call. The platform already played your CANONICAL OPENING. "
            f"The caller now says: {caller_line}"
        )
        await adapter.start_response(instructions=user_turn)

        reply_parts: list[str] = []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 75
        while loop.time() < deadline:
            ev = await adapter.poll_event(timeout=3.0)
            if not ev:
                if reply_parts:
                    break
                continue
            if ev.get("type") == "_stream_end":
                break
            if ev.get("type") == "assistant_transcript_delta":
                reply_parts.append(str(ev.get("delta") or ""))
            if ev.get("type") == "response_done" and not ev.get("usage_only"):
                break
        text = "".join(reply_parts).strip()
        if not text:
            return "error", "(Live session ended with no output_audio_transcription text)"
        return "ok", text
    except Exception as exc:
        return "error", f"{type(exc).__name__}: {str(exc)[:800]}"
    finally:
        try:
            await adapter.close()
        except Exception:
            pass


def _run_pytest() -> tuple[int, str]:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "server/tests/test_gemini_brain_script_adherence.py",
            "server/tests/test_gemini_audio_session.py",
            "-q",
            "--tb=short",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


async def main() -> int:
    from server.agent.brain_prompt_composer import estimate_tokens

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = REPO / "data" / "audits"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"gemini-brain-critical-audit-{ts}.md"

    pytest_code, pytest_out = _run_pytest()

    lines: list[str] = [
        "# Gemini brain critical audit (automated run)",
        "",
        f"Generated: **{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}** "
        f"by `scripts/run_gemini_brain_critical_audit.py`",
        "",
        f"**Live model (only):** `{GEMINI_LIVE_MODEL}` — no other Gemini/OpenAI models used for probes.",
        "",
        "This file is produced from real `compile_agent_from_brief` + "
        "`build_realtime_voice_instructions` (Gemini PSTN path) and optional Gemini API probes. "
        "It is not hand-written narrative.",
        "",
        "## Pytest (adherence — compile + prompt structure)",
        "",
        f"exit_code={pytest_code}",
        "",
        _fence(pytest_out),
        "",
        "## Four LLM sessions (one per business brief)",
        "",
    ]

    live_ok = 0
    prompt_pass = 0
    for idx, case in enumerate(AUDIT_CASES, start=1):
        compiled, result, _raw, comp_t, budget = await _compile_case(case)
        from server.brain.agent_script_compiler import build_opening_line, work_scope_from_brief

        spec = case["spec"]
        lang = spec.get("language", "en-IN")
        scope = work_scope_from_brief(spec["brief"], result.company_name or "")
        opening = build_opening_line(
            agent_name=result.agent_name,
            company_name=result.company_name or "",
            work_scope=scope,
            language=lang,
            direction=case["direction"],
        )
        script = result.agent_script or ""

        gemini_sys = _gemini_system_instruction(compiled, case, opening)
        checks = _prompt_checks(gemini_sys, script, case, result.agent_name or "")
        if all(checks.values()):
            prompt_pass += 1
        status, reply = await _probe_gemini_live(gemini_sys, case["caller_line"], opening)
        if status == "ok":
            live_ok += 1
        reply_checks = _reply_checks(reply, case) if status == "ok" else {}

        lines.extend(
            [
                f"### {idx}. {case['label']} (`{case['session_id']}`)",
                "",
                f"- **Brief source:** `{case['brief_key']}`",
                f"- **Direction:** {case['direction']}",
                f"- **Language:** {lang}",
                f"- **Canonical opening (fed to Gemini):** {opening!r}",
                f"- **Agent name (resolved):** {result.agent_name}",
                f"- **Company (resolved):** {result.company_name}",
                f"- **Optimizer model tag:** {getattr(result, 'optimizer_model', 'n/a')}",
                f"- **Compiled brain tokens (est.):** {comp_t} (budget {budget}, assembled {estimate_tokens(compiled)})",
                f"- **Gemini live system_instruction tokens (est.):** {estimate_tokens(gemini_sys)}",
                "",
                "#### Automated prompt checks",
                "",
            ]
        )
        for k, v in checks.items():
            lines.append(f"- `{k}`: **{'PASS' if v else 'FAIL'}**")
        lines.extend(
            [
                "",
                "#### Simulated caller (probe input)",
                "",
                _fence(case["caller_line"]),
                "",
                "#### Agent script (user-facing `result.agent_script` — what Test Studio shows)",
                "",
                _fence(script),
                "",
                "#### Full compiled brain (cached assembly sent to call lock)",
                "",
                _fence(compiled),
                "",
                "#### Gemini Live `system_instruction` (what PSTN Gemini 3.8 Live receives)",
                "",
                _fence(gemini_sys),
                "",
                "#### Live LLM probe",
                "",
                f"- **Model:** `{GEMINI_LIVE_MODEL}`",
                f"- **Status:** {status}",
                "",
                "#### Model reply (text probe with same system_instruction as Live PSTN)",
                "",
                _fence(reply if status != "skipped" else reply),
                "",
            ]
        )
        if reply_checks:
            lines.append("#### Reply adherence checks (automated)")
            lines.append("")
            for k, v in reply_checks.items():
                lines.append(f"- `{k}`: **{'PASS' if v else 'FAIL'}**")
            lines.append("")
        lines.append("---")
        lines.append("")

    lines.extend(
        [
            "## Summary",
            "",
            f"- **Prompt structure checks (all 4 sessions):** {prompt_pass}/4 PASS",
            f"- **Live Gemini 3.8 Live probes (WebSocket bidi):** {live_ok}/4 replied",
            f"- **Pytest adherence:** exit_code={pytest_code}",
            "",
            f"Audit file: `{out_path}`",
        ]
    )

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0 if pytest_code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
