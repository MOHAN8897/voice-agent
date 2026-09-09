# Script alignment audit — local compile vs website create-script

**Date:** 2026-09-09  
**Session:** `align-driveright-web-compare` + Playwright agent `DriveRight Align` (`4d038518-…`)  
**Brief:** DriveRight Auto Care (Hyderabad) car-service sales  
**Tools:** local compile, `POST /api/instructions` (website path), Playwright Test Studio UI (no TestSprite package in repo — used Playwright MCP)

## Verdict

**PASS after fixes** — local, API, and website UI all produce the same full sectional calling script; live LLM answers fees from the saved brain.

| Path | Result |
|------|--------|
| Local `compile_agent_from_brief` | PASS — full script + brain |
| Website API `POST /api/instructions` | PASS — 17/17 probes |
| Playwright Fine-tune → Create agent script | PASS — v1 · **6419 tokens** · cache ON |
| Live LLM using saved brain | PASS — fee answered from WORK SCOPE |

## What was wrong (and fixed)

1. **`.env` still capped brain at 3500/5000** while code allowed 10k — live turns logged `budget: 3500` against a ~6.4k brain.  
   **Fix:** `.env` → `BRAIN_PROMPT_BUDGET_TOKENS=6000`, `MAX=10000`.

2. **Live budget ignored saved instruction budget** — Fine-tune could save a 6k+ brain while `resolve_brain_budget` returned the stale runtime/env value.  
   **Fix:** `resolve_brain_budget` takes `max(runtime, instruction_store.budgetTokens, estimatedTokens, env)`.

3. **Fine-tune sent a low slider budget** (often 2500 from model presets).  
   **Fix:** Create-script requests at least **6000**, then persists effective budget to runtime after save.

4. **Live prep still used budget &lt; brain_est** for overrides.  
   **Fix:** `_prepare_brain_context` / stream metadata clamp budget up to actual `brain_est`.

## Playwright website check

- Logged into Dev Portal → Test Studio → created agent **DriveRight Align** (en-IN).
- Fine-tune: pasted DriveRight brief → **Create agent script**.
- Status: `Agent script v1 created and saved · 6419 tokens · cache ON`.
- Generated calling script showed `AGENT IDENTITY`, `DriveRight Auto Care`, fees, `LIVE CALL GUIDE`, `VOICE STYLE`, `OBJECTION HANDLING`, `GUARDRAILS`, `CLOSING`.

## Live LLM (website-saved brain)

**User:** How much is the basic periodic service?  
**Agent:** The Basic Periodic Service is three thousand five hundred rupees.

Session store: `budget=6419`, script embedded under `--- CALLING SCRIPT ---`, fee present in brain.

## Earlier API compare (script_alignment_compare.py)

**PASS** — 0 issues; 17/17 probes; local↔web Jaccard ≈ 0.71 (same structure; LLM wording varies). Live goodbye hangup OK.

Reproduce:

```bash
python scripts/script_alignment_compare.py
```

## Residual notes

- No TestSprite install in this repo; comparison used Playwright MCP + API/scripts.
- Dev share web build may still show the older Fine-tune hint text until the Next production bundle is rebuilt; create-script behavior is already on the new path.
- Recompile/recreate scripts on existing agents so they pick up the raised budget + quality floor.
