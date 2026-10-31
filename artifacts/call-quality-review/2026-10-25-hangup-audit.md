# Last-two-call hangup audit — 25 October 2026

The immediate cause in both calls was a failed LLM turn followed by a server-forced farewell and disconnect. Neither call contains a caller request to end at the failing turn. Separate, reproducible validation and prompt defects also make premature hangup possible.

Audit scope: the two latest locally archived calls, their transcripts, failure records, metadata, trace and API logs; the selected composed voice route; prompt assembly and the frozen script; hangup validation, playback and disconnect. No production settings, scripts, call records or application source were changed. No calls were placed.

Policy: deep read-only investigation; dependency-level tracing; runtime archive plus offline reproductions and focused tests; no delegation. Writes are limited to audit deliverables. Confidence labels: **Confirmed** = observed in call evidence or reproduced against current code; **Likely** = supported reconstruction without the historical request body; **Suspected** = requires provider/runtime evidence.

## The two calls

All times below are IST (UTC+05:30). Both calls used agent `4259d53c-3994-5f05-9489-537ef06d0406`, composed voice, Sarvam STT → `sarvam-105b-conversations` → Sarvam TTS, Telugu `te-IN`, and compiled brain `cb_v20261024_e048fe0b6cb3`. They did not use the Gemini Live audio loop.

### Latest: 0ed6f194-9ad0-4bc3-963b-76e3da07f329

- Connected 18:38:40; disconnected 18:39:07; carrier duration 27 seconds.
- Archived caller: `అవును.` — “Yes.” Then `అవును. ఆ ఉందండి నాకు ఉంది.` — approximately “Yes … yes, I have [it/time],” an elliptical affirmative, not a refusal. The missing referent should be understood from the opening or clarified.
- API log: STT final at 18:38:58; first turn starts 18:39:01. Another caller final causes `THINK_CANCEL` and a replacement turn at 18:39:02.
- 18:39:03: `IncompleteTurnError`, `finish_reason='length'`, `partial_chars=0`, `retry_used=False`, `delivered=False`.
- Archived agent at 18:39:04.299: `సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.` — “Okay, thank you for your time. Goodbye.”
- Another STT final appears at 18:39:03 during recovery, but is not a later archived user turn; its Telugu words are lost to ASCII replacement in this log. Its content cannot be established from that log.
- Disconnect: `reason='agent_hangup'`, playback wait 3,218 ms, post-playback trail 0 ms. Metadata also records `end_reason='ws_disconnect'`; that transport label does not explain the initiating cause.

Evidence: [transcript](<D:/voice agent/data/calls/0ed6f194-9ad0-4bc3-963b-76e3da07f329/transcript.jsonl:1>), [failure record](<D:/voice agent/data/calls/0ed6f194-9ad0-4bc3-963b-76e3da07f329/failed_turns.jsonl:1>), [API failure](<D:/voice agent/data/dev-logs/api.log:785>), [disconnect](<D:/voice agent/data/dev-logs/api.log:819>).

### Previous: 3031d32c-f012-4fab-ae73-4091303dd68a

- Connected 18:36:22; disconnected 18:37:02; carrier duration 40 seconds.
- Caller: `సరే నాకు విజిటింగ్ కార్డ్స్ అయితే వద్దు కానీ వెడ్డింగ్ కార్డ్స్ కావాలి మీరు వెడ్డింగ్ కార్డ్స్ చేస్తారా` — “I do not want visiting cards, but I want wedding cards. Do you make wedding cards?” This declines one product while requesting another.
- Agent: `తప్పకుండా, చెప్పండి.` — “Certainly, tell me.” This does not answer availability or establish that wedding cards are offered.
- Caller: `అదే వెడ్డింగ్ కార్డ్స్ చేస్తారా మీ దగ్గర ఎంత ప్రైసింగ్ ఉన్నాయి చెప్పగలరా?` — “Do you make wedding cards? Can you tell me the pricing?”
- 18:36:57: the same incomplete LLM error, `length`, no usable spoken partial, no retry.
- 18:36:58.586: the same platform farewell. At 18:37:02 the server disconnects after 3,531 ms of playback wait and 0 ms trail.
- Pricing and product availability were never answered; no next step was agreed.

Evidence: [transcript](<D:/voice agent/data/calls/3031d32c-f012-4fab-ae73-4091303dd68a/transcript.jsonl:1>), [failure record](<D:/voice agent/data/calls/3031d32c-f012-4fab-ae73-4091303dd68a/failed_turns.jsonl:1>), [LLM failure](<D:/voice agent/data/dev-logs/api.log:598>), [disconnect](<D:/voice agent/data/dev-logs/api.log:623>).

Saved prompt evidence: [identical archived brain](<D:/voice agent/artifacts/call-quality-review/2026-10-25-saved-call-brain.txt:35>) and [current runtime reconstruction](<D:/voice agent/artifacts/call-quality-review/2026-10-25-reconstructed-live-prompt.txt:124>). The first is copied verbatim from both call snapshots; the second uses current assembly code and is explicitly a reconstruction.

## Critical and high-priority findings

### 1. P1 — LLM failure is treated as permission to end the call

**Confirmed; the immediate cause in both calls.**

Trace: model streaming → `IncompleteTurnError` → `_run_turn` exception handler → `_close_after_non_tts_failure` → `_finish_agent_hangup` → provider disconnect.

In `server/services/pstn_voice_core.py:2716–2774`, the composed exception path records failure, then executes:

```python
reason = caller_close_reason(text) or "agent_hangup"
...
await self._close_after_non_tts_failure(reason=reason, session=tts_session)
```

In the same file, `557–598`, that method selects `default_farewell_for(...)`, speaks it, appends it to the transcript, and calls `_finish_agent_hangup`. It does not ask `validate_end_call` whether the caller is interested, has an unanswered question, or still needs help.

This makes a provider failure sound like a deliberate conversational dismissal. Correcting the system prompt alone cannot fix this path: there was no completed model reply to obey the prompt.

**Recommended:** recover a retryable, unspoken failure once with the same selected model and corrected budget. If recovery cannot succeed, explain the technical inability honestly and close with a failure reason. Keep failure handling distinct from caller refusal and normal goal completion.

### 2. P1 — Every active composed agent gets a tool, which bypasses token-floor and retry protections

**Confirmed by source and offline reproduction. Historical token cap: likely, not directly logged.**

`server/call/live_turn_orchestrator.py:1313–1334` appends `CONFIRM_ORDER_TOOL` even when there are no connected integrations:

```python
return [*tools[:31], CONFIRM_ORDER_TOOL]
```

The truthy tool list sends calls through `1028–1071`, whose initial request directly calls `adapter.stream_structured_turn(...)`. It does not pass through `_stream_composed_turn`.

The wrapper at `1158–1286` implements the configured first-attempt floor and one larger retry. The initial tool request receives neither. This matters even when the caller only says “yes” and no tool is executed.

Offline reproduction against `_stream_llm`, with the first provider attempt returning `length`:

- Tools offered: one request, `max_output_tokens=None`, raises immediately, `retry_used=False`.
- No tools offered: requests use 1,280 then 2,560 tokens; second attempt completes.

The adapter fallback in `server/providers/sarvam_llm.py:232–245` uses `settings.max_response_length`. Current local settings give **320**, while the intended composed floor is **1,280**. Reconstructing the default initial-tool request yields `max_tokens=320`. Archived per-call runtime entries have no token override. The exact historical HTTP bodies and in-memory overrides were not archived, so 320 is a strong reconstruction, not a measured historical value.

**Recommended:** apply budget normalization and bounded retry to the initial tool-selection request before any side effect occurs; preserve tool idempotency after execution. Offer order tools only when applicable. Record actual effective request parameters on this branch.

### 3. P1 — Quoting an affirmative can validate it as a refusal

**Confirmed by executable reproduction; a separate risk, not the observed trigger in these two calls.**

`server/call/end_call_validate.py:845–854` labels evidence a semantic close when it matches the caller's text and is not caught by continuation, negation or short-thanks checks:

```python
semantic_close = bool(
    reason in {"firm_refusal", "not_interested", "goodbye"}
    and parsed.get("evidence")
    and evidence_matches(parsed.get("evidence") or "", user)
    and not caller_wants_to_continue(user)
    ...
)
```

There is no independent positive check that the quoted text means refusal. Against current code, a deliberately wrong proposal with `reason='not_interested'`, `evidence='అవును.'`, and no remaining request is **accepted**. The same happens for the full affirmative from the latest call. No-proposal validation correctly keeps both utterances open.

The continuation patterns in `server/call/hangup_judge.py:43–62,207–214` omit this Telugu affirmative. The safety of a semantic model proposal therefore depends on incomplete phrase lists despite the prompt promising meaning-based judgment.

**Recommended:** explicitly protect affirmatives, corrections, alternate-product requests and uncertain intent; do not equate a literal matching quotation with proof of refusal. Add the exact call utterances as negative-close regressions.

### 4. P1 — A Telugu service question loses protection when punctuation is missing

**Confirmed by reproduction with the previous call's exact first user turn.**

`server/call/end_call_validate.py:36–40,396–404` detects questions using a question mark or a limited list of question phrases. It omits the Telugu service-question ending in `చేస్తారా` (“do you make/do?”). The exact wedding-card question without `?` returns `looks_like_question=False` and `caller_wants_to_continue=False`.

A wrong refusal proposal quoting that whole turn is accepted. The later pricing question, which has `?`, is rejected as a close with `reject_code='user_asked_question'`. This shows protection changing with ASR punctuation even though the caller's intent remains a service inquiry.

**Recommended:** recognize questions and new needs independently of punctuation, and preserve the unfulfilled request through the close gate. Cover Telugu and mixed-language questions with and without punctuation.

### 5. P1 — The composed close path cannot reconsider caller speech before disconnect

**Confirmed structural defect; an additional STT event is observed in the latest call, but its content is unavailable.**

`server/services/pstn_voice_core.py:443–473` sets `_hangup_started=True` and clears `_pending_transcript` before playback drain. It invokes `execute_agent_close` without its `can_disconnect` callback. The executor explicitly supports that callback at `server/call/close_call_executor.py:116–122` to recheck whether the caller resumed.

Thus this composed path lacks that final veto. Input queued during the farewell can be discarded. Both calls had zero post-playback trail; playback completion is not a check that the user's need was answered.

**Recommended:** keep non-emergency closing reversible until disconnect is committed. Recheck substantive speech, pending requests and current close authorization immediately before provider hangup. Honor an explicit stop-contact request promptly; do not turn every close into another sales pitch.

### 6. P2 — The saved script still tells the model to speak a farewell that another layer forbids

**Confirmed in both identical archived brains and the current reconstructed runtime prompt. Causal contribution to these calls is unproven.**

Frozen brain `compiled_brain_text` lines 109–110 says:

> Confirm in one line, thank them, short farewell, end_call.

Its call-end policy, lines 132–136, instead says never put a farewell in reply text, never say goodbye before approval, and generate no words on a close turn. The script also has a standalone English goodbye at lines 78–79.

`refresh_platform_sections` refreshes recognized top-level platform sections, but leaves embedded saved script guidance intact (`server/brain/compiled_brain_artifact.py:85–124`). The current compiler's corrected professional-close wording at `server/brain/agent_script_compiler.py:1883–1887` does not replace that older embedded instruction in this saved publication. A source fix is not evidence that an already-published script is corrected.

**Recommended:** establish one farewell owner and remove conflicting generated or persisted close instructions during validated publication/assembly. Revalidate this agent's saved artifact; do not overwrite unrelated persisted configuration at startup.

### 7. P2 — Language and opening instructions contradict the admitted Telugu call

**Confirmed in the saved artifact and reconstructed runtime prompt; current runtime adds mitigating instructions.**

The entity language and session are `te-IN`, but saved script line 76 says `Use the selected en-IN language pack`. Its canonical opening says `After the callee speaks, say once`, while the outbound rules say the platform plays it at media readiness and the runtime footer says it has already been delivered.

The runtime footer asks the model to render English examples in Telugu and forbids restarting the opening. This mitigation does not remove the contradictory source instructions. The archived replies are Telugu, so wrong-language output is not established in these two turns.

**Recommended:** validate language and opening ownership across the complete published artifact and reject contradictory instructions, rather than relying on a later footer to override them.

### 8. P2 — Product refusal and alternate-product interest are not clearly separated in this script

**Confirmed ambiguity in the saved script; not the immediate cause of the pricing-turn disconnect.**

Saved script lines 58–61 only establish icards/visiting cards and a visiting-card price of 25 rupees. Line 70 broadly says to quote visiting-card pricing when asked about price; lines 70 and 91 say to thank/close on “not interested.” Neither branch explicitly distinguishes declining visiting cards from requesting wedding cards. Platform policy does say product/service questions must continue, leaving competing broad instructions.

Wedding-card availability and pricing are unknown in the supplied facts. The safe answer is to say that those details are unavailable and follow only a permitted next step, not imply availability or substitute the visiting-card price. The actual `తప్పకుండా, చెప్పండి.` was an acknowledgment, not a useful answer to the concrete service question.

**Recommended:** bind refusal and price handling to the product being discussed; answer the current request first. A changed product need remains an open request. Do not invent wedding-card facts or callback permissions.

### 9. P2 — Failure diagnostics cannot establish the claimed “thinking” cause

**Confirmed observability gap. Hidden model reasoning as the cause remains unverified.**

The initial tool branch lacks the wrapper's request-budget log. Its failures report `output_tokens=0`, but `server/providers/sarvam_llm.py:428–445` raises at a non-success finish reason before reading any later usage-only SSE chunk. Zero recorded tokens therefore does not prove zero provider work or identify the provider's internal reason for `length`.

Current V1 request construction explicitly includes `reasoning_effort=None` (`server/providers/sarvam_llm.py:292–300`), with the intent of avoiding default thinking. The exact provider response body and reasoning usage are not stored for these failed turns. The visible “thinking” phase also includes STT/coalescing and cancellation: the latest call logs an approximately three-second interval from the first final to turn launch, then a restart, then an approximately one-second failed request. This does not establish that the model spent that entire time reasoning about hangup.

**Recommended:** log actual effective token cap, reasoning setting, request ID, finish reason and final usage safely for every attempt. Preserve the initiating failure category separately from the subsequent transport disconnect reason.

## Additional reporting discrepancy

The previous call's generated outcome says the agent confirmed wedding cards are offered. The transcript only says “Certainly, tell me.” That is insufficient evidence of product availability. The summary correctly notes unanswered pricing and an agent failure, but that added availability claim should not be treated as ground truth. Outcome generation also labels a lead as qualified while this conversation never captured the wedding-card requirements; it may reflect an existing lead, so this audit does not claim the call itself changed its qualification.

## Verification performed

1. Traced both archived failures through the current exception, farewell and carrier-disconnect code. Both failure records say `length`, `retry_used=false`, `delivered=false`; both logs show a subsequent server hangup.
2. Offline mocked `_stream_llm` reproduction: tool-enabled first attempt bypasses budget floor/retry; no-tool equivalent retries at 1,280/2,560 and completes. No network, tool writes or real calls.
3. Replayed exact archived caller text through `validate_end_call`: affirmatives and the unpunctuated service question can be accepted under an incorrect quoted-refusal proposal; the punctuated pricing question is protected. These prove validator defects, not that the model emitted those proposals in the two calls.
4. Reconstructed `composed_system_prompt` from the archived brain and resolved stack: 17,667 characters; verified the stale close instruction, `en-IN` conflict and opening conflict remain. This is a current-code reconstruction, not an archived verbatim HTTP request.
5. Focused existing checks:

```text
.venv/Scripts/python.exe -m pytest server/tests/test_llm_finish_reason_recovery.py server/tests/test_sarvam_composed_transport.py server/tests/test_close_decision_contract.py server/tests/test_end_call_validate.py -q --tb=short
65 passed, 1 warning in 2.99s
```

The passing suite covers the recovery helper and existing close cases; it does not prove that the initial tool branch uses that helper or that the exact positive/alternate-product utterances are protected. No tests were weakened.

**Reproduction verdict: PASS — defects reproduced. Product behavior: FAIL — both audited calls ended with unresolved caller needs.** No fixes have been applied. Reticle was skipped because this is a read-only backend/call-flow audit with no application UI change.

## Repair order

1. Unify initial tool-request token budgeting and safe pre-side-effect retry.
2. Separate recoverable model failure from conversational hangup; use honest failure messaging if recovery is exhausted.
3. Harden close authorization for affirmatives, alternate needs, corrections and unpunctuated questions; use these exact call utterances as regressions.
4. Wire a final caller-resumption veto into the composed close path.
5. Revalidate the saved agent script for farewell, locale, opening and product-scoping contradictions.
6. Verify exact-call offline replays, then an authorized end-to-end test; record effective request settings and the correct hangup cause.

Limits: no independent listening/transcription of the recordings was performed; this audit uses saved ASR, runtime logs and source. The complete historical HTTP request/response and hidden reasoning usage are unavailable. These limits do not prevent tracing the observed LLM-error-to-hangup path.
