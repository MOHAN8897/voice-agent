# Agent Brief Prompt Pipeline — Deep Audit

**Date:** 2026-09-08  
**Spec:** `AGENT_BRIEF_PROMPT_PIPELINE_AUDIT.md`  
**Compiler:** `agent_script_v14` · **STATIC:** `sr_v14`  
**Overall verdict: PASS (fully aligned for in-scope work)**

---

## Method

1. Re-read the optimized implementation spec line-by-line.  
2. Probe live code (not status tables) for each requirement.  
3. Reproduce two real gaps found on first pass; fix them; re-run **61** related tests (all green).  
4. Confirm out-of-scope items were correctly left alone.

---

## Scorecard (after fixes)

| # | Requirement | Verdict | Evidence |
|---|-------------|---------|----------|
| 1 | Help-first openings | **PASS** | `OPENING_*`, `LIVE_CALL_GUIDE_BODY`, PSTN `_default_greeting` |
| 2 | Sales = convert to qualified lead | **PASS** | `ROLE_STRATEGY["sales"]` + `role_section` |
| 3 | FLOW lead-conversion / no checklist | **PASS** | `_FLOW_SALES_EXTRA` + always-replace FLOW |
| 4 | Turn priority in STATIC + HUMAN_CALL | **PASS** | `sr_v14` + `CONVERSATION_INTELLIGENCE` |
| 5 | Writer: convert-to-lead, ban Step/Q trees | **PASS** | `script_writer_system` |
| 6 | Always replace CONVERSATION FLOW | **PASS** | `_sanitize_conversation_flow` |
| 7 | Checklist / Step detection | **PASS** | `_CHECKLIST_FLOW` + `_LEFTOVER_TREE` |
| 8 | Validate + one repair + deterministic fallback | **PASS** | `validate_agent_script` in `compile_agent_from_brief` |
| 9 | Spoken-pack HUMAN_CALL dedupe | **PASS** | `PHONE_CALL_POLICY_PTR` in TE/EN/HI packs |
| 10 | Section shape / no DISCOVERY sprawl | **PASS** | Strip + validator reject `DISCOVERY`/`RECOMMENDATION` |
| 11 | Facts vs policy / invent amounts | **PASS** | WORK SCOPE from brief; digit amounts validated |
| 12 | Soft vs firm no | **PASS** | HUMAN_CALL + `validate_end_call` |
| 13 | No third brevity system | **PASS** | Writer 80–150 matches runtime |
| 14 | No duplicate platform policy in writer | **PASS** | Writer bans locks/barge/numbers dumps |
| 15 | Identity `name from company` + multi-word/Unicode | **PASS** | `Priya`/`Acme`, `John Smith`, `దీప్తి` |
| 16 | Out of scope left alone | **PASS** | No CRM Realtime slots; no STT/TTS/barge changes for this prompt |
| 17 | 15-turn scored flow | **PASS** | `AGENT_BRIEF_15_TURN_FLOW_AUDIT.md` · 15/15 judges |

---

## Gaps found on first deep pass (now fixed)

| Gap | Impact | Fix |
|-----|--------|-----|
| Multi-word / Unicode names failed (`John Smith`, `దీప్తి`) | Identity wrong or empty | Broadened `extract_agent_name_from_brief` |
| `DISCOVERY RULES` / `RECOMMENDATION RULES` survived bind | Spec §2 section sprawl | Strip on bind + validator reject |
| PSTN docstring still said “name ask” | Doc drift only | Updated to “offer help” |
| Seven-turn mock taught 60–80 chars | Fixture smell | Aligned to 80–150 |

---

## What is intentionally NOT claimed

- **Live OpenAI per-turn replies** in the 15-turn audit are policy-aligned mocks scored by production judges (deterministic). Script *creation* uses the real compile path.  
- **Structured CRM lead slots on Realtime** remain out of scope per the spec.  
- Runtime TTS hard max **150 chars** still applies — the spec marks “do not over-constrain to one sentence” as intentionally partial vs that hard limit.

---

## Test gate

```text
61 passed — test_conversation_policy, test_human_call_rules, test_agent_brief,
            test_seven_turn_agent_brief, test_fifteen_turn_agent_brief_audit,
            test_spoken_numbers
```

---

## Bottom line

**Yes — for the in-scope brief → script compiler work, everything in the optimized spec is implemented and aligned.**  
First deep pass was **PARTIAL**; after closing the four gaps above, treat the pipeline as **PASS / ship-ready** for this prompt scope.

Related artifacts:
- Spec: `AGENT_BRIEF_PROMPT_PIPELINE_AUDIT.md`
- 15-turn flow: `AGENT_BRIEF_15_TURN_FLOW_AUDIT.md`
