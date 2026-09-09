"""
Compare local compile vs website /api/instructions create-script path,
then verify live LLM uses the saved brain (not a stale/default prompt).

Writes: SCRIPT_ALIGNMENT_AUDIT.md
Run: python scripts/script_alignment_compare.py
"""
from __future__ import annotations

import asyncio
import json
import re
import traceback
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "SCRIPT_ALIGNMENT_AUDIT.md"

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

SESSION = "align-driveright-web-compare"
API = "http://127.0.0.1:8000"


def _section_heads(text: str) -> list[str]:
    return re.findall(r"^---\s*(.+?)\s*---\s*$", text or "", flags=re.M)


def _fee_ok(text: str) -> bool:
    low = (text or "").lower()
    return "three thousand five hundred" in low or "3500" in low


async def _compile_local(budget: int = 6000):
    from server.brain.agent_script_compiler import compile_agent_from_brief

    return await compile_agent_from_brief(
        brief=BRIEF,
        language="en-IN",
        use_llm=True,
        budget_tokens=budget,
    )


async def _compile_via_http(budget: int = 6000) -> dict:
    """Same path the website Fine-tune 'Create agent script' button uses."""
    import urllib.error
    import urllib.request

    payload = json.dumps(
        {
            "sessionId": SESSION,
            "agentBrief": BRIEF,
            "language_code": "en-IN",
            "brainPromptBudgetTokens": budget,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/api/instructions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body[:800]}") from e


async def _get_instructions(*, include_compiled: bool = True) -> dict:
    import urllib.request

    q = f"sessionId={SESSION}"
    if include_compiled:
        q += "&includeCompiled=true"
    with urllib.request.urlopen(f"{API}/api/instructions?{q}", timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def _live_probe(brain: str) -> list[dict]:
    from server.agent.conversation_manager import conversation_manager
    from server.services.openai_brain_service import generate_response

    conversation_manager.clear(SESSION + "-live")
    turns = [
        ("Hi, I need a service package for my car.", ["karthik", "driveright", "package", "service"]),
        ("How much is the basic periodic service?", ["three thousand", "3500", "rupees"]),
        ("Thanks, that's all for now. Bye.", ["goodbye", "thank"]),
    ]
    rows = []
    for user, expect_any in turns:
        out = await generate_response(
            transcript=user,
            language_code="en-IN",
            session_id=SESSION + "-live",
            brain_prompt=brain,
            openai_model="gpt-5.6-luna",
            max_output_tokens=180,
        )
        text = (out.get("text") or "").strip()
        end = out.get("end_call") or {}
        low = text.lower()
        hit = any(x in low for x in expect_any)
        rows.append(
            {
                "user": user,
                "agent": text,
                "end_call": bool(end.get("should_end")),
                "expect_any": expect_any,
                "matched_fact": hit,
            }
        )
    return rows


def _similarity(a: str, b: str) -> float:
    """Rough token Jaccard on significant words."""
    wa = {w.lower() for w in re.findall(r"[A-Za-z0-9']{4,}", a or "")}
    wb = {w.lower() for w in re.findall(r"[A-Za-z0-9']{4,}", b or "")}
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


async def main() -> int:
    issues: list[str] = []
    notes: list[str] = []

    print("1) Local compile_agent_from_brief (LLM)...")
    compiled_local, result, raw_t, comp_t, bud = await _compile_local(6000)
    local_script = result.agent_script or ""
    notes.append(
        f"Local: model={result.optimizer_model} script_tok≈{result.optimized_token_estimate} "
        f"brain_tok≈{comp_t} budget={bud}"
    )

    print("2) Website-equivalent POST /api/instructions ...")
    try:
        http_resp = await _compile_via_http(6000)
    except Exception as exc:
        issues.append(f"Website API create-script failed: {exc}")
        http_resp = {}
        print(f"   FAILED: {exc}")

    web_script = str(http_resp.get("agentScript") or "")
    web_brain_full = str(http_resp.get("brainPromptFull") or http_resp.get("compiledBrainPrompt") or "")
    web_brain_preview = str(http_resp.get("brainPrompt") or "")
    opt = http_resp.get("optimizerReport") or {}

    print("3) GET /api/instructions (with/without includeCompiled)...")
    get_full = {}
    get_ui = {}
    try:
        get_full = await _get_instructions(include_compiled=True)
        get_ui = await _get_instructions(include_compiled=False)
    except Exception as exc:
        issues.append(f"GET instructions failed: {exc}")

    ui_script = str(get_ui.get("agentScript") or "")
    ui_brain = get_ui.get("brainPrompt")  # should be absent for Fine-tune default fetch
    stored_brain = str(get_full.get("brainPrompt") or "")
    stored_script = str(get_full.get("agentScript") or "")

    # Alignment checks
    checks: dict[str, bool] = {
        "local_has_identity": "AGENT IDENTITY" in local_script,
        "local_has_live_guide": "LIVE CALL GUIDE" in local_script,
        "local_fee_in_script": _fee_ok(local_script),
        "local_script_in_brain": local_script[:200] in compiled_local if local_script else False,
        "web_ok": bool(http_resp.get("ok")),
        "web_has_identity": "AGENT IDENTITY" in web_script,
        "web_has_live_guide": "LIVE CALL GUIDE" in web_script,
        "web_fee_in_script": _fee_ok(web_script),
        "web_script_embedded_in_brain": (
            bool(web_script) and ("--- CALLING SCRIPT ---" in web_brain_full) and (web_script[:180] in web_brain_full)
        ),
        "web_brain_has_static_rules": "STATIC OUTPUT RULES" in web_brain_full,
        "web_company_driveright": "DriveRight" in web_script,
        "get_ui_keeps_agent_script": bool(ui_script),
        "get_ui_hides_brain_by_default": ui_brain is None,
        "stored_script_matches_post": stored_script.strip() == web_script.strip() if web_script else False,
        "stored_brain_matches_post": stored_brain.strip() == web_brain_full.strip() if web_brain_full else False,
        "local_web_script_similar": _similarity(local_script, web_script) >= 0.35 if web_script else False,
        "preview_not_confused_as_full": "..." in web_brain_preview or len(web_brain_preview) < len(web_brain_full),
    }

    for k, v in checks.items():
        if not v:
            issues.append(f"Alignment check failed: {k}")

    print("4) Live LLM probe against website-saved brain...")
    live_rows: list[dict] = []
    brain_for_live = stored_brain or web_brain_full or compiled_local
    try:
        live_rows = await _live_probe(brain_for_live)
        if not live_rows[0]["matched_fact"]:
            issues.append("Live turn 1 did not use identity/company from script.")
        if not live_rows[1]["matched_fact"]:
            issues.append("Live turn 2 did not answer basic fee from WORK SCOPE / script.")
        if not live_rows[2]["end_call"]:
            issues.append("Live turn 3 goodbye did not set end_call.")
    except Exception as exc:
        issues.append(f"Live probe failed: {exc}")

    # Compare section inventories
    local_heads = _section_heads(local_script)
    web_heads = _section_heads(web_script)

    lines: list[str] = []
    lines.append("# Script alignment audit — local compile vs website create-script")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}  ")
    lines.append(f"**Session:** `{SESSION}`  ")
    lines.append(f"**Brief:** DriveRight Auto Care (Hyderabad) car-service sales  ")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    verdict = "PASS" if not issues else "FAIL / ISSUES"
    lines.append(f"**{verdict}** — {len(issues)} issue(s); {sum(1 for v in checks.values() if v)}/{len(checks)} alignment probes green.")
    lines.append("")
    for n in notes:
        lines.append(f"- {n}")
    if opt:
        lines.append(
            f"- Website optimizer: model=`{opt.get('optimizer_model')}` "
            f"role=`{opt.get('detected_role')}` name=`{opt.get('agent_name')}` "
            f"company=`{opt.get('company_name')}`"
        )
    lines.append("")
    lines.append("## Alignment probes")
    lines.append("")
    lines.append("| Probe | Pass |")
    lines.append("|-------|------|")
    for k, v in checks.items():
        lines.append(f"| `{k}` | {'PASS' if v else 'FAIL'} |")
    lines.append("")
    lines.append("## Issues")
    lines.append("")
    if not issues:
        lines.append("None.")
    else:
        for i, item in enumerate(issues, 1):
            lines.append(f"{i}. {item}")
    lines.append("")
    lines.append("## Section headers")
    lines.append("")
    lines.append(f"- Local script: {local_heads}")
    lines.append(f"- Website script: {web_heads}")
    lines.append(f"- Word Jaccard similarity (local vs web script): `{_similarity(local_script, web_script):.2f}`")
    lines.append("")
    lines.append("## Live LLM (uses website-saved brainPrompt)")
    lines.append("")
    for i, row in enumerate(live_rows, 1):
        status = "PASS" if row["matched_fact"] and (i < 3 or row["end_call"]) else "FAIL"
        if i == 3:
            status = "PASS" if row["end_call"] else "FAIL"
        lines.append(f"### Turn {i} — {status}")
        lines.append("")
        lines.append(f"**User:** {row['user']}  ")
        lines.append(f"**Agent:** {row['agent']}  ")
        lines.append(f"**end_call:** `{row['end_call']}`  ")
        lines.append(f"**Fact match:** `{row['matched_fact']}` (looked for {row['expect_any']})")
        lines.append("")
    lines.append("## Website script excerpt (first 1.5k)")
    lines.append("")
    lines.append("```")
    lines.append((web_script or local_script)[:1500])
    lines.append("```")
    lines.append("")
    lines.append("## Brain embedding check")
    lines.append("")
    lines.append(
        f"Brain contains `--- CALLING SCRIPT ---`: "
        f"`{'--- CALLING SCRIPT ---' in (brain_for_live or '')}`  "
    )
    lines.append(
        f"Brain contains fee fact: `{_fee_ok(brain_for_live)}`  "
    )
    lines.append(
        f"GET without includeCompiled hides brainPrompt: `{ui_brain is None}` "
        f"(UI still shows agentScript — Fine-tune tab uses agentScript field)."
    )
    lines.append("")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT}")
    print(f"Issues: {len(issues)}")
    return 1 if issues else 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception:
        traceback.print_exc()
        raise
