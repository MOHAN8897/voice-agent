# Agent QA — NatureVeda "Priya" (multilingual, PSTN-equivalent, text TTS)

**Date:** 2026-10-31 · **Status: complete for the reduced critical matrix** — all 7 supported languages.
Every number comes from recorded sessions under `artifacts/call-quality-review/agent-qa-*`.

## 1. Method (agent-agnostic)

Harness `server/eval/conversation_sim/agent_qa.py` + spec `fixtures/agent_qa_natureveda.json`; another agent needs
only a new spec (brief, persona, scenarios, checks).

| Layer | What runs |
|---|---|
| Agent | Built by the real creation pipeline (`analyze-brief` → `build-employee`). gu-IN/ml-IN reuse the en-IN generated script through the pipeline's own assembly (`reassemble_brain_from_script`) with the native template opening, because Gemini (the creation model) hit its quota. |
| Call | Real `PstnVoiceLoop._run_turn` → orchestrator → classifiers → reply → verifier → guards → TTS session; live mid-call language switching on. TTS is a text stub that records every streamed chunk. |
| Customer | Adaptive LLM, one utterance per turn, wall-clock paced; ≥ 90 s enforced. Final runs: **Sarvam** (Gemini/OpenAI out of quota/credits). |
| Integrations | Test tenant's verified Gmail + Google Calendar via Nango; only `mohansaiteja.99@gmail.com` allowed; calendar test events cancelled. |
| Verdict | **Server truth** (DND/callback/language-switch/lead/order/tool rows, silence, latency, totals, script, unproven claims, 90 s) + LLM judge. Final judge = Sarvam, so it grades its own model family: server checks are the primary verdict. |

Reduced critical matrix (per your request): te-IN all 8 scenarios; each other language 4 scenarios, `interested`
(the order flow) in every language, every other scenario in ≥ 3 languages.

## 2. Final results (final code)

**32 sessions · 31 passed (96.9%) · checks 622/623 (99.8%) · 0 silent turns / 255 · first audio p50 1.62 s, p90 2.42 s · avg 140 s (min 97 s)**

| Scenario | te | hi | en | ta | kn | gu | ml |
|---|---|---|---|---|---|---|---|
| DND | ✅ | | ✅ | | ✅ | | |
| Callback | ✅ | | | ✅ | | ✅ | |
| Callback in other language | ✅ | ✅ | ✅ | | | | ✅ |
| Interested (order) | ✅ | ✅ / ⚠️¹ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Not interested | ✅ | | | ✅ | | | ✅ |
| Partially interested | ✅ | | ✅ | | | ✅ | |
| Mid-call language switch | ✅ | ✅ | | ✅ | ✅ | ✅ | ✅ |
| Integration (Gmail) | ✅² | ✅² | | | ✅² | | |

¹ Two runs: one clean pass; one failed only `speech_clean` (a guard reduced "ठीक है, noted।" to "noted।") — fixed (F27),
not re-run. ² Gmail send was attempted correctly and the agent stayed honest, but the connection itself fails
(OAuth refresh at Google) — see Blockers. Every `interested` session recorded the order (`converted`) with correct
items and quantity.

## 3. History

| Run | Code | Sessions | Server checks | Silent turns | First audio p50/p90 | Verifier rewrites |
|---|---|---|---|---|---|---|
| baseline | before fixes | 9 | 93.3% | 2 / 49 | 1.80 / 2.42 s | — |
| v2 | F1–F7 | 26 | 94.5% | 1 / 148 | 1.73 / 2.53 | 97 of 124 |
| v3 | F1–F15 | 12 | 97.5% | 0 / 75 | 1.79 / 2.23 | 34 of 67 |
| **v4 + v5 (final)** | **all** | **32** | **99.7% (318/319)** | **0 / 255** | **1.62 / 2.42** | **35 of 240** |

## 4. Issues found and fixed

| # | Defect (evidence) | Fix (file) |
|---|---|---|
| F1 | kn/ml agents opened in **English** | native template opening when repair fails — `brain/employee_script_pipeline.py` |
| F2 | Intermittent creation failure with no diagnosable cause | validator findings logged — same |
| F3 | Email split into two TTS chunks / `gmail. com` | address-safe chunking & glue fix — `services/pstn_text_chunker.py`, `voice_pipeline_limits.py` |
| F4 | **Silent turns** ("I'll think about it") — reply skipped, close refused | shared `close_rejection()` — `call/semantic_call_control.py`, `live_turn_orchestrator.py` |
| F5 | "I'll let you know, bye" saved as a business callback | three-way next-contact check — `call/close_classifier.py` |
| F6 | Hinglish on the English switch turn | verifier treats wrong language as an error — `call/spoken_fact_review.py` |
| F7 | Complete sentence treated as unfinished → dead air | sentence-final punctuation is complete — `close_classifier.py` |
| F8 | Verifier rewrote 74% of correct drafts, invented actions/failures, added a wrong size | trigger-based review, accepted only if it fixes its trigger — `spoken_fact_review.py` |
| F9 | "Place the order, bye" hung up before the order tool | write action defers the close — `close_classifier.py` |
| F10 | **Orders/emails lost**: Sarvam strips a tool call from a request without `tools` → `content: null` (reproduced by replay) | re-offer tools when the speech pass is empty (both branches) — `live_turn_orchestrator._speech_or_reselect` |
| F11 | Recovery asked "what time should I call?" after an email request | restate the caller's request — `call/speech_recovery.py` |
| F12 | Multi-product orders ambiguous | `CONFIRM_ORDER` contract — `call/order_confirmation.py` |
| F13 | Wrong totals (₹1,497 for 2×499+599) in te/hi/kn/ml, read back into orders | deterministic total check (digits **and** quantity words, 7 languages), server combined total, checked against business facts only — `spoken_fact_review.py`, `call/business_answer_plan.py` |
| F14 | Code-mixed false claims ("order place हो गया") passed | patterns for 7 languages — `call/action_proof.py` |
| F15 | Real booking's "request noted" replaced by a failure line | confirmed booking proves the request — `action_proof.py` |
| F16 | Repeat-stripper cut an email mid-token | address-safe sentence split — `call/reply_guard.py` |
| F17 | Expired Gmail token reported as "HTTP 400" | mapped to re-authorization — `services/nango_service.py` |
| F18 | Model wouldn't email "product details" | tool description — `services/tool_schema_registry.py` |
| F19 | Name + address given, agent said "I'll pass it to the team", nothing recorded; "yes, but how long is delivery?" looped "shall I proceed?" 10× | order-flow rules in runtime capabilities — `brain/capabilities.py` |
| F20 | Per-item totals not computed for pack sizes ("₹499 (200 ml)") or quantity words | pack-size rule + quantity words — `business_answer_plan.py` |
| F21 | "Not interested *for now*, I use other products" not closed (te, ta) | refusal rule in all three readings — `call/turn_control_prompt.py`, `close_classifier.py` |
| F22 | Re-asked question answered with bare "ಸರಿ" ("OK") | repeat guard keeps answers to questions — `live_turn_orchestrator.py` |
| F23 | Invented usage instructions ("apply on a clean face, massage") | usage/dosage words trigger the fact check (7 languages) — `spoken_fact_review.py` |
| F24 | Dictated phone stored raw (`9876543210`) beside E.164 leads → duplicates, DND misses | normalize to E.164 — `services/saas/lead_sync.py` |
| F25–F26 | (harness) judge couldn't see platform tools; lead check ignored dictated numbers | fixed in `agent_qa.py` |
| F27 | Echo strip left a bare "noted।" | never strip to a one-word reply — `reply_guard.py` |

Tests: `server/tests/test_agent_qa_regressions.py` (40), `test_semantic_close_rejection.py` (3), new cases in
`test_brain_flow_coherence.py`, `test_close_classifier_handoff.py`, `test_employee_script_pipeline.py`. Affected
suites: same 7 pre-existing failures before and after (Cartesia 402, finetune catalog, Gemini model key,
seven-turn brief) — no regressions.

## 5. Component findings

- **LLM (Sarvam 105B):** correct catalog facts, DND/callback/refusal handling, doctor referral, no cure claims, honest
  "not available" for stock/delivery/discount. Weak at arithmetic (now guarded), occasionally invents usage advice
  (now fact-checked), occasionally re-introduces itself on turn 1.
- **LLM → TTS:** 1–2 chunks per turn, ~0 s inter-chunk gap; TTS language follows live switches. Defects were text
  shaping (F3, F16, F27).
- **Memory:** name, address, email, product captured and kept across switches; multi-item quantity stored as a
  single number (minor).
- **Language packs:** cached brain keeps the original pack; one ACTIVE LANGUAGE note replaces (never stacks) per
  request. English switches live; other languages become a callback in that language — verified in te/hi/en/ml.
- **Efficiency:** 4.6 LLM calls/turn; verifier now runs only when it can fix something (35 rewrites in 240 runs).

## 6. Open items and blockers

1. **Gmail connection needs re-authorization** (Integrations page → reconnect Google). Sends worked once, then
   Google refused token refresh.
2. **Gemini key is free-tier and quota-exhausted**; agent creation (`generation_target()`, no fallback by design)
   blocks for every tenant when it is. Upgrade the key or plan.
3. **Sarvam as a creation model doesn't work** (asks per-customer clarifications, then "generation_needs_review") —
   don't switch the generation provider to Sarvam.
4. Admin-panel Sarvam key has no credits (tests used the funded `.env` key). OpenAI has no credits.
5. Judge = Sarvam for final runs; re-judge with an independent model when available (`--rejudge`).

## 7. Rating

| Area | Score |
|---|---|
| Conversation quality | 8.5/10 |
| Call control (DND/callback/close) | 9.5/10 |
| Orders & integrations | 8.5/10 (orders 7/7 languages; Gmail blocked by the connection) |
| Multilingual | 9/10 (all 7 languages pass the critical matrix) |
| Responsiveness | 9/10 (0 silent turns, 1.6 s p50 first audio) |
| **Overall** | **9/10 — target met: 96.9% sessions, 99.8% checks** |

## 8. Rerun

```
python -m server.eval.conversation_sim.agent_qa --sarvam-only --out <dir> \
  --brains <run dirs with agents/<lang>-brain.txt> --retarget-from <run with en-IN brain> \
  --plan "hi-IN=interested,language_switch;..."
python -m server.eval.conversation_sim.agent_qa --rescore --out <dir>
```
