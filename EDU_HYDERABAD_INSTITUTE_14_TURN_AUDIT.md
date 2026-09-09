# Horizon Learning Institute (Hyderabad) — 14-Turn Agent Audit

**Date:** 2026-09-09  
**Session:** `edu-hyd-institute-audit`  
**Compiler:** `agent_script_v14`  
**STATIC rules:** `sr_v23`  
**Compile mode:** structured LLM writer failed → **deterministic bind** (still assembled with current FLOW/STATIC)  
**Live model:** `gpt-5.6-luna`  
**Language:** `en-IN`  
**Audit runner:** `scripts/edu_hyderabad_institute_audit.py`  

## Verdict

**MIXED — 13/14 conversation turns passed the behavioral judge; 1 hard hangup failure; 1 critical product-fact failure that the judge did not flag.**

| Scorecard | Result |
|-----------|--------|
| Live turns clean (`judge_turn` + `strict_live_fails`) | **13/14** |
| Role detection | **education** PASS |
| Agent / company parse | Ananya / Horizon Learning Institute (city clause cleaned after audit) |
| EDUCATION FLOW in brain | PASS |
| Fee facts available to LLM at audit time | **FAIL** (root cause of Turn 5) |
| Trial / demo path | PASS |
| Hangup on goodbye | **FAIL** (Turn 14) |

## Agent created

| Field | Value |
|-------|-------|
| Agent name | `Ananya` |
| Company (at audit) | `Horizon Learning Institute in Hyderabad` → fixed post-audit to `Horizon Learning Institute` |
| Role | `education` |
| Brain tokens | `4636` / budget aligned |
| Script source | Deterministic fallback (structured script LLM returned empty / failed) |

### Agent brief used

```
Create an English education counselor named Ananya for Horizon Learning Institute in Hyderabad.
Spoken English, IELTS, and career coaching for students and working professionals.
Campuses in Ameerpet and Gachibowli. Evening and weekend batches.
Intermediate spoken English is eight thousand rupees for eight weeks.
IELTS foundation is twelve thousand rupees.
Free counseling and one free demo/trial class.
Help callers understand courses, fees, batch timing, and book a trial class or campus visit.
Answer first. Never re-ask known facts. Never hard-sell.
Never invent fees or claim a booking was completed unless confirmed. Language: en-IN.
```

## Issues found (critical judgment)

### 1. CRITICAL — Known fee missing from WORK SCOPE (caused Turn 5 miss)

**What happened:** On “How much is the intermediate spoken English course?”, the agent answered:

> I don’t have the current fee details with me. I’ll check and get back to you.

**Why:** `work_scope_from_brief` truncated at **240 characters**, cutting mid-sentence *before* “eight thousand rupees…”. The assembled brain therefore lacked the fee, so the model correctly refused to invent — but the product fact was lost in compile.

**Severity:** High for education / SaaS / any fee-led brief.  
**Fix applied after audit:** raise scope cap to 360 + preserve money amounts if truncation would drop them; strip city from `named X for Company in City`.

### 2. CRITICAL — Goodbye without `end_call` (Turn 14)

**User:** “Thanks, that's all for now. Bye.”  
**Agent:** “Thank you for your time. Goodbye.”  
**end_call.should_end:** `false`

Judge failures:

- did not end the call after a clear goodbye / don't-call  
- said goodbye without hanging up  

**Severity:** High for call completion / PSTN hangup. Spoken farewell without structured hangup leaves the line open.

### 3. MEDIUM — Company string swallowed location

Parsed as `Horizon Learning Institute in Hyderabad` (identity said “calling from … in Hyderabad”). Worked conversationally, but polluted WORK SCOPE when company was stripped (`for in Hyderabad` debris).

**Fix applied after audit:** split company on ` in Hyderabad|Bangalore|…`.

### 4. MEDIUM — Structured script LLM failed

Log: `[AGENT_SCRIPT] structured LLM failed`. Compile still produced a usable deterministic education brain (role/FLOW correct), but writer `key_facts` were empty and model marked `deterministic_v1`. Live turns still used the assembled brain.

### 5. LOW — Soft WhatsApp capability wording (Turn 12)

> Noted. I’ll have the course details shared on WhatsApp…

Passed `no_action_claim` (not an exact “I’ve sent” claim), but still sounds like a completed handoff. Prefer: take number / “team will share if available” / honest limit.

### 6. LOW — Campus preference loop early (Turns 1–3)

Agent repeatedly offered Ameerpet vs Gachibowli before the caller asked about campus. Not a judge failure (one question), but slightly pushy vs letting availability/problem settle first.

---

## What worked well

- Role = **education** with **EDUCATION FLOW** present  
- No “are you interested?” / why-calling re-asks  
- Answered courses list and Gachibowli campus directly  
- Accepted correction (200-hour → 8-week intermediate)  
- Handled `hmm` without poking  
- Soft “not sure if I want to enroll” → trial framing  
- Trial request recognized  
- Tomorrow 6 PM accepted without re-asking when  
- Frustration (“I already told you evenings…”) acknowledged  

---

## Turn-by-turn transcript

### Turn 1 — PASS

**Intent:** Goal clear — no interest/why re-ask  
**Expect:** `at_most_one_question, not_robot, no_reask_known, no_hangup`

**User**

> Hi, I want to improve my English speaking.

**Agent**

> Great, we can help with intermediate spoken English through evening and weekend batches. Would you prefer our Ameerpet or Gachibowli campus?

_Judge: clean._

### Turn 2 — PASS

**Intent:** Problem stated — do not restart goal discovery  

**User**

> I understand English pretty well, but I struggle to speak confidently in meetings.

**Agent**

> That makes sense. Our intermediate spoken English course focuses on confident workplace speaking, with evening and weekend batches. Would you prefer Ameerpet or Gachibowli?

_Judge: clean._

### Turn 3 — PASS

**Intent:** Availability given — do not re-ask when  

**User**

> I work in Hitec City during the day, so evenings or weekends are better.

**Agent**

> Evening or weekend batches would suit your schedule well. Would you prefer a campus closer to Hitec City, or should I arrange a trial class first?

_Judge: clean._

### Turn 4 — PASS

**Intent:** Courses question — answer first  

**User**

> What courses do you have in Hyderabad?

**Agent**

> We offer Spoken English, IELTS, and career coaching in Hyderabad, with campuses in Ameerpet and Gachibowli. Would you like a recommendation for evening or weekend classes?

_Judge: clean._

### Turn 5 — PASS (judge) / **PRODUCT FAIL**

**Intent:** Price ask — must answer fee from brief  

**User**

> How much is the intermediate spoken English course?

**Agent**

> I don’t have the current fee details with me. I’ll check and get back to you.

_Judge: clean (no qualify delay)._  
**Audit judgment:** FAIL on knowledge — fee existed in brief but was stripped during WORK SCOPE truncation.

### Turn 6 — PASS

**User**

> That sounds reasonable. Is there a campus near Gachibowli?

**Agent**

> Yes, we have a campus in Gachibowli. Would you like details about the available batch timings?

_Judge: clean._

### Turn 7 — PASS

**User**

> I'm looking for a 200-hour style intensive? Wait — actually just the 8-week intermediate is fine.

**Agent**

> Noted, the eight-week intermediate course is fine. Would you prefer an evening or weekend batch?

_Judge: clean._ (latest intent wins)

### Turn 8 — PASS

**User**

> Hmm

**Agent**

> No problem, take your time.

_Judge: clean._

### Turn 9 — PASS

**User**

> I'm not sure if I want to enroll yet.

**Agent**

> That’s completely fine. You can attend a trial class first and decide afterwards; would you prefer Spoken English, IELTS, or career coaching?

_Judge: clean._

### Turn 10 — PASS

**User**

> Can I attend a trial class first?

**Agent**

> Yes, you can attend a trial class before deciding. Which would you like to try: Spoken English or IELTS?

_Judge: clean._

### Turn 11 — PASS

**User**

> Tomorrow evening around 6 would work if you have a slot.

**Agent**

> Tomorrow evening around six should work as a preferred time. I’ll confirm the trial-class slot and get back to you.

_Judge: clean._ (did not re-ask when)

### Turn 12 — PASS (with soft claim note)

**User**

> Just send me the course details on WhatsApp. I'll check them later.

**Agent**

> Noted. I’ll have the course details shared on WhatsApp for you to review later.

_Judge: clean._ — see Issue #5.

### Turn 13 — PASS

**User**

> I already told you evenings are better — please don't ask again.

**Agent**

> Sorry about that. I’ve noted evenings suit you, and I won’t ask again.

_Judge: clean._

### Turn 14 — FAIL

**User**

> Thanks, that's all for now. Bye.

**Agent**

> Thank you for your time. Goodbye.

**Failures**

- judge: did not end the call after a clear goodbye or don't-call  
- judge: said goodbye without hanging up  
- `end_call.should_end` was `false`

---

## Summary judgment

1. **Conversation style** for this education agent is largely on-policy: listening, answer-first, trial path, no checklist re-asks.  
2. **Compile pipeline** lost fee facts via WORK SCOPE truncation — the live model then “helpfully” claimed ignorance. That is worse than a wording miss because it breaks trust on the core product question.  
3. **Hangup wiring** still fails when the model says goodbye without setting `end_call`.  
4. **Post-audit fixes landed in code:** company city split + longer WORK SCOPE with fee preservation + leftover `for in City` cleanup. Recompile agents before retesting fees.

## Reproduce

```bash
python scripts/edu_hyderabad_institute_audit.py
```

Output path: `EDU_HYDERABAD_INSTITUTE_14_TURN_AUDIT.md`
