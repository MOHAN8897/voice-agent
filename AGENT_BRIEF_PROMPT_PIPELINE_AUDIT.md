# Agent Brief → Script Compiler — Optimized Implementation Spec

**Purpose:** Make generated calling scripts conversation policies for **lead conversion**, not question trees.  
**Scope:** Brief → script writer → compiler → cached calling script only.  
**Out of scope:** PSTN / STT / TTS / barge / Realtime audio / endpointing.

---

## Verdict on this prompt (vs our codebase)

| Aspect | Assessment |
|--------|------------|
| Goal (policy not Q-tree) | **Correct** — matches `script_writer_system` + `flow_section` intent |
| Answer-first / one question / never re-ask | **Correct** — already in HUMAN_CALL + STATIC |
| Soft vs firm no | **Correct** — keep; already gated by `validate_end_call` |
| Separate facts vs policy | **Good** — we do this via WORK SCOPE vs FLOW/ROLE; do not invent new giant section dumps |
| New section headers (DISCOVERY RULES, etc.) | **Trim** — our compiler strips/rewrites IDENTITY/OPENING/WORK SCOPE/ROLE/LIVE CALL GUIDE/FLOW. Prefer **fewer headers**, stronger FLOW + ROLE, not 11 new sections that duplicate STATIC |
| “Do not over-constrain to one sentence” | **Partial** — STATIC allows 1–2 short beats; hard max **200 chars** still applies at runtime (do not fight that here) |
| Realtime “resend memory” | **Not in this prompt** — correct. Dialogue history is session-owned; do not add history inject here |
| Validation reject/regenerate | **Done** — `validate_agent_script` + one LLM repair + deterministic fallback |
| Length | Original prompt was **too long / repetitive** — this optimized version is the project source of truth |

**Bottom line:** The intent of the original prompt is right for the project. The optimized form below is shorter, maps to **real files/functions**, and avoids asking for duplicate platform policy or new section sprawl.

---

## Status (implemented)

| Item | Status |
|------|--------|
| Help-first openings (no forced name ritual) | **Done** — `OPENING_*`, PSTN default greeting, `LIVE_CALL_GUIDE_BODY` |
| Sales ROLE = convert to qualified lead | **Done** — `ROLE_STRATEGY["sales"]` |
| FLOW sales lead-conversion + no checklist | **Done** — `_FLOW_SALES_EXTRA` |
| Explicit turn priority in STATIC + HUMAN_CALL | **Done** — `sr_v15` |
| Writer: convert-to-lead, reject Step/Q trees | **Done** — `script_writer_system` |
| **Always** replace CONVERSATION FLOW with platform policy | **Done** — `_sanitize_conversation_flow` |
| Expand Step/Question checklist detection | **Done** — `_CHECKLIST_FLOW` |
| Post-save validation reject/regenerate | **Done** — `validate_agent_script` + one repair LLM + `deterministic_validation_fallback_v1` |
| Further shrink spoken-pack duplication of HUMAN_CALL | **Done** — `PHONE_CALL_POLICY_PTR` in spoken packs; full text kept as `HUMAN_CALL_RULES` for judges/tests |
| Structured CRM lead slots on Realtime | **Out of this prompt’s scope** (optional later) |
| Fixtures MOCK scripts policy-shaped | **Done** — seven/eight-turn mocks |
| Brief `name from company` identity parse | **Done** — stop name at `from`; company before `.`; multi-word + Unicode names |
| Strip non-canonical DISCOVERY/RECOMMENDATION headers | **Done** — stripped on bind + rejected by validator |
| 15-turn scored flow audit | **Done** — see `AGENT_BRIEF_15_TURN_FLOW_AUDIT.md` |

Compiler version: `agent_script_v14`.

---

## Exact code map

```text
USER BRIEF
  → sanitize_agent_brief
  → _llm_generate_script / _deterministic_script     agent_script_compiler.py
  → resolve_script_identity + infer_agent_role
  → ensure_script_identity_and_scope
       strip IDENTITY/OPENING/WORK SCOPE/ROLE/LIVE CALL GUIDE
       ALWAYS replace CONVERSATION FLOW → flow_section(role)
       inject identity, opening, scope, role_section, LIVE_CALL_GUIDE
  → validate_agent_script
       reject Step/Q leftovers, placeholders, empty identity, invented amounts
       one LLM regenerate with repair_hint, else deterministic fallback
  → _assemble_brain
       SAFETY + spoken_pack(lang) + CALLING SCRIPT + call_end + STATIC + footer
  → saved as cached brain / Realtime session.instructions
```

**Key files**

| File | Role |
|------|------|
| `server/prompts/agent_voice_rules.py` | `script_writer_system`, openings, spoken packs, `PHONE_CALL_POLICY_PTR` |
| `server/prompts/conversation_policy.py` | ROLE_STRATEGY, FLOW, LIVE_CALL_GUIDE, HUMAN_CALL, checklist regex |
| `server/brain/agent_script_compiler.py` | compile, sanitize FLOW, `validate_agent_script`, assemble brain |
| `server/brain/sections.py` | `STATIC_OUTPUT_RULES` (sr_v15) |

---

## Optimized requirements (what generation must produce)

### 1. Policy, not tree

Forbidden in generated FLOW body (compiler replaces FLOW anyway; writer must not emit these):

- `Step 1` / `Question 1` sequences  
- “First ask X, then Y”  
- “Collect all of the following”  
- Mandatory checklists before helping  

Required behavior language:

> Ask at most one useful missing fact. Never re-ask known facts. Answer their last question first. When enough is known, recommend once and offer one next step.

### 2. Section shape (keep our real headers)

Do **not** invent DISCOVERY RULES / RECOMMENDATION RULES as separate mandatory headers (duplicates STATIC/FLOW). Use:

```
AGENT IDENTITY
OPENING
WORK SCOPE          ← business facts / duties only
ROLE & OBJECTIVE    ← injected role_section
LIVE CALL GUIDE     ← injected
CONVERSATION FLOW   ← always platform flow_section(role)
VOICE STYLE
OBJECTION HANDLING
GUARDRAILS
CLOSING
```

### 3. Opening

- Introduce + offer help.  
- Name ask **optional**, never blocks answering a stated need.  

### 4. Sales conversion objective

Sales / lead_qualification scripts must encode:

> understand need → fit known offerings → convert interest into a qualified lead → one real next step  

Not: finish a qualification form.

### 5. Turn priority (one place)

Already in STATIC + HUMAN_CALL. Writer must **not** paste another full copy. Reference only:

1. Latest utterance  
2. Answer / concern  
3. Known facts  
4. One missing fact if needed  
5. Recommend + next step  
6. End only on clear end  

### 6. Facts vs policy

- WORK SCOPE / facts = products, prices, locations from brief only  
- FLOW / ROLE / STATIC = behavior  
- Never invent facts to “complete” the script  

### 7. Soft vs firm no

Keep existing HUMAN_CALL / call_end behavior. Objections ≠ hangup.

### 8. Voice length

Script may say 1–2 short beats. Runtime hard max remains 200 chars — do not invent a third brevity system in the writer.

### 9. No duplicate platform policy

Writer must **not** dump HUMAN_CALL, SAFETY, language locks, barge, number rules — server already adds them in `_assemble_brain`. Spoken packs use `PHONE_CALL_POLICY_PTR` instead of embedding full HUMAN_CALL.

### 10. Validation

Before save: `validate_agent_script` rejects Step/Question leftovers outside platform FLOW, placeholders, empty identity, or digit amounts not in the brief. One LLM regenerate with `repair_hint`; still failing → `_deterministic_script`.

---

## What NOT to do

- Do not lengthen prompts with repeated “never checklist” paragraphs  
- Do not add HTTP-style history into Realtime  
- Do not touch PSTN/STT/TTS/barge  
- Do not replace business facts with a generic sales template  
- Do not force every vertical to collect budget+location+timeline  

---

## Brief pattern (tell users this)

```text
Agent name {{name}} from {{company}}.
We offer: {{real facts only}}.
Goal: convert interested callers into qualified leads and book {{visit/callback/demo}}.
Talk naturally. Answer first. Ask at most one missing useful fact. Never a question list.
When enough is known, recommend one option and one next step.
Never invent prices or claim actions you cannot do.
Language: {{te-IN|en-IN|hi-IN}}.
```

Avoid: “Qualify them on budget then location then size then timeline.”

---

## Example OLD vs NEW (conceptual)

**OLD (bad)**  
Step 1 greet → Step 2 ask name → Step 3 ask budget → Step 4 ask location → Step 5 pitch → Step 6 close  

**NEW (good)**  
You are Priya from Acme Realty. Plots from fifty lakhs; villas from eighty.  
Answer price/location questions from known facts first.  
Use what they already said. Ask one missing field only if it changes the recommendation.  
When enough is known, recommend one fit and offer a site visit or callback.  
Soft hesitation: stay helpful. Firm no / don’t-call: farewell and end.

---

## Remaining work (out of this prompt)

1. Structured CRM lead slots on Realtime (optional later).  
2. Nothing else required for this brief→script pipeline.

---

## Deliverable checklist

1. **Files changed:** `conversation_policy.py`, `agent_voice_rules.py`, `agent_script_compiler.py`, `sections.py`, `pstn_text_chunker.py`, tests, this spec  
2. **Functions:** `script_writer_system`, `opening_*`, `LIVE_CALL_GUIDE_BODY`, `flow_section` / `_FLOW_*`, `_sanitize_conversation_flow`, `validate_agent_script`, `STATIC_OUTPUT_RULES`, `_default_greeting`, `PHONE_CALL_POLICY_PTR`  
3. **Old behavior:** checklist/Step flows could survive; name-first openings; weak conversion objective  
4. **New behavior:** help-first open; always platform FLOW; sales = lead conversion; explicit turn priority; validate + regenerate  
5. **Checklist prevention:** always replace FLOW + stronger regex + writer bans + validator  
6. **Conditional discovery:** encoded in FLOW sales extra + STATIC priority  
7. **Facts preserved:** WORK SCOPE still from brief; no generic fact overwrite; invented amounts rejected  
8. **Duplicate platform policy:** writer told not to dump locks; spoken packs use policy pointer  
9. **Tests:** openings/FLOW/Step-tree/validator/spoken-pack pointer  
10. **Examples:** see OLD vs NEW above  

---

*Optimized for this repo. Prefer this file over the longer duplicate-heavy implementation prompt.*
