# Text-Only Realtime LLM Critical Audit

**Audit date:** 2026-09-06  
**Scope:** OpenAI `gpt-realtime-2.1-mini` and Gemini Live text-only; live Sarvam/Cartesia STT+TTS stack costing  
**Languages:** English (primary), Hindi, Telugu, and mixed Telugu-English  
**Credentials:** Existing `.env` keys were used; secret values were never printed  
**Overall verdict:** **NO-GO for production**

---

## 0. Integration Status and Audit Boundary

The application does **not** currently implement the architecture tested in this audit:

- No `server/realtime/` package
- No `RealtimeTextSession` or `RealtimeTextManager`
- No `OpenAIRealtimeTextAdapter`
- No `GeminiLiveTextAdapter`
- No `VOICE_PIPELINE_MODE` runtime setting
- No `/ws/brain-realtime` route

Production currently uses:

- OpenAI Responses API over per-turn HTTP
- Gemini `streamGenerateContent` over HTTP/SSE
- Existing streaming STT and TTS connectors

Therefore the OpenAI/Gemini tests below are **direct authenticated provider probes**, not end-to-end tests through the application, Web agent, PSTN path, Telnyx bridge, ledger, or lifecycle service.

The direct tests establish provider capability, measured token usage, caching, language behavior, and tool behavior. They do **not** prove that the planned application integration works; that integration cannot be tested until it is implemented.

---

## 1. Executive Verdict

| Area | Result | Severity |
|---|---|---|
| OpenAI Realtime text connection | PASS | — |
| OpenAI text-only enforcement | PASS — zero audio tokens | — |
| OpenAI session memory | PASS | — |
| OpenAI prompt caching | PASS — 85.25% aggregate cache ratio | — |
| English behavior | PASS for tested factual/memory turns | — |
| Hindi behavior | PASS on isolated Unicode test | — |
| Telugu behavior | PARTIAL — Telugu script returned, but awkward code mixing | High |
| Mixed Telugu-English behavior | FAIL — unrelated Tamil and Korean appeared | Critical |
| Gemini Live text output | FAIL — model rejected `TEXT` output modality | Blocking |
| Non-terminal hangup discipline | PASS on “busy, maybe later” | — |
| Explicit hangup tool | PARTIAL — isolated pass, one long-session failure | Critical |
| Realtime summary JSON | FAIL — JSON parsed but violated its schema and language requirement | Blocking |
| Implemented `outcome.json` with Realtime model | FAIL — three HTTP 404 attempts | Blocking |
| Implemented `call_summary.json` | NOT IMPLEMENTED | Blocking |
| Sarvam STT + TTS live probe | PASS for English/Hindi; Telugu STT garbled | High |
| Cartesia Sonic TTS live probe | PASS — faster first audio than Sarvam | — |
| Cartesia Ink Whisper STT live probe | PASS English/Hindi; FAIL Telugu loop | Critical |
| Cartesia Ink-2 STT live probe | FAIL — REST `model_not_found` on this account | High |
| Full STT + Realtime LLM + TTS per-minute cost | Measured — see §13 | — |

The requested stack is not production-ready as currently planned:

1. OpenAI `gpt-realtime-2.1-mini` is available and works for persistent text sessions.
2. Gemini `gemini-3.1-flash-live-preview` does **not** support text output in the tested Live session.
3. Realtime function-call arguments cannot be treated as strict summary JSON.
4. The current post-call code sends the locked Realtime model to the Responses API, where it fails.
5. Telugu/mixed-language quality and long-session hangup reliability do not pass a critical release gate.
6. No application-level Realtime flow exists yet, so Web/PSTN integration remains completely untested.

---

## 2. What Was Actually Tested

### 2.1 Provider discovery

The authenticated OpenAI model-list endpoint returned:

- `gpt-realtime-2`
- `gpt-realtime-2.1`
- `gpt-realtime-2.1-mini`
- other Realtime/transcription/translation models

This proves the configured account currently has Realtime access to `gpt-realtime-2.1-mini`.

The authenticated Gemini model-list endpoint returned these `bidiGenerateContent` models:

- `gemini-3.5-transcribe-live`
- `gemini-2.5-flash-native-audio-latest`
- `gemini-2.5-flash-native-audio-preview-09-2025`

It did not advertise `gemini-3.1-flash-live-preview`, although a direct connection reached that model and returned a capability error.

### 2.2 Live protocols

**OpenAI**

- Persistent WebSocket through the installed OpenAI Python SDK
- Model: `gpt-realtime-2.1-mini`
- User turns: `conversation.item.create` with `input_text`
- Generation: `response.create`
- Output: `response.output_text.delta`
- Completion/usage: `response.done`
- No input or output audio events sent

**Gemini**

- Direct `BidiGenerateContent` WebSocket
- Requested model: `gemini-3.1-flash-live-preview`
- Requested output modality: `TEXT`
- No audio payload sent

### 2.3 Critical test set

The principal OpenAI session used:

- A cache-stable instruction prefix close to the current 5,000-token prompt ceiling
- Eight turns, six primarily English
- Name and reference-code retention
- Name correction
- Hindi request
- Telugu request
- English recap after multilingual turns
- Non-terminal “busy/maybe later”
- Explicit stop-calling/end-call request
- A schema-shaped post-call outcome tool

Additional isolated tests covered:

- Hindi Unicode preservation
- Telugu Unicode preservation
- Mixed Telugu-English output
- Strict enum-style `end_call` arguments
- Server-side `validate_end_call()`
- Existing memory, ledger, post-call, and hangup unit suites

---

## 3. Measured OpenAI Cost per Voice Minute

### 3.1 Published text pricing

For `gpt-realtime-2.1-mini`:

| Meter | Price per 1M tokens |
|---|---:|
| Text input | $0.60 |
| Cached text input | $0.06 |
| Text output | $2.40 |

Source: <https://developers.openai.com/api/docs/pricing>

Audio pricing was not used because the measured API responses reported zero audio tokens.

### 3.2 Measured usage

| Metric | Measured value |
|---|---:|
| Total input tokens | 35,961 |
| Cached input tokens | 30,656 |
| Uncached input tokens | 5,305 |
| Output tokens | 600 |
| Input audio tokens | 0 |
| Output audio tokens | 0 |
| Aggregate input cache ratio | 85.25% |
| Estimated spoken words | 229 |
| Estimated voice duration at 150 words/minute | 1.527 minutes |

Calculation:

```text
uncached input = 5,305 × $0.60 / 1,000,000 = $0.003183
cached input   = 30,656 × $0.06 / 1,000,000 = $0.00183936
output         = 600 × $2.40 / 1,000,000 = $0.00144

measured session LLM cost = $0.00646236
measured LLM cost/minute  = $0.00646236 / 1.527
                          = $0.004233/minute
```

At the audit conversion rate of **₹95.70/$**:

```text
OpenAI measured LLM-only cost ≈ ₹0.405/minute
```

This excludes STT, TTS, Telnyx, silence, network, and infrastructure. Full STT + LLM + TTS stack minutes are in **§13**.

### 3.3 Cold and uncached sensitivity

The first cold response cost approximately **$0.00323** because the full instruction prefix was uncached.

If the same measured token volume received no cache discount:

```text
uncached-only session cost ≈ $0.02302
uncached-only cost/minute  ≈ $0.01507
                            ≈ ₹1.44/minute
```

Observed caching reduced this test's estimated LLM cost by approximately **71.9%**.

### 3.4 Interpretation

The measured $0.00423/minute is a workload-specific LLM-only result, not a flat provider rate. Realtime text models are token-billed; voice-minute cost varies with:

- Instruction size
- Turns per minute
- Caller and assistant verbosity
- Reasoning/output tokens
- Cache hit rate
- Tool schemas and tool calls
- Session truncation

Production must calculate cost from each `response.done.usage`, then divide the call's accumulated LLM cost by actual call duration.

---

## 4. Gemini Cost and Capability Audit

### 4.1 Published price

For `gemini-3.1-flash-live-preview` paid-tier text:

| Meter | Price per 1M tokens |
|---|---:|
| Text input | $0.75 |
| Text output, including thinking | $4.50 |

Source: <https://ai.google.dev/gemini-api/docs/pricing>

### 4.2 Live result

Gemini rejected the required setup:

```text
WebSocket close code: 1007
The requested combination of response modalities (TEXT) is not supported
by models/gemini-3.1-flash-live-preview.
```

`gemini-2.5-flash-native-audio-latest` rejected the same text-output setup.

Therefore:

- Text input + text output Gemini Live cost was **not measurable**.
- No successful Gemini response token usage exists for this audit.
- The model cannot currently replace the OpenAI text-only Realtime session under the stated no-LLM-audio requirement.
- Using generated audio plus output transcription would violate the architecture and incur unwanted audio-output cost.

### 4.3 Hypothetical token comparison only

If Gemini processed the same 35,961 input and 600 output tokens with no cache discount:

```text
hypothetical cost = 35,961 × $0.75 / 1M
                  + 600 × $4.50 / 1M
                  = $0.02967

hypothetical cost/minute = $0.01943
                         ≈ ₹1.86/minute
```

This is **not a measured Gemini call**. Gemini tokenization, context accounting, and cache behavior may differ. It is included only to compare published rates against the measured OpenAI workload.

---

## 5. Latency Results

### 5.1 Persistent OpenAI session

| Metric | Result |
|---|---:|
| Initial WebSocket connection | 2,923–2,989 ms |
| Warm successful-turn median first text | 657 ms |
| Warm successful-turn maximum first text | 937 ms |
| Warm successful-turn median completion | 921 ms |

The connection delay is paid once per call if the session is opened during call setup. It should not be placed after the first `transcript.final`.

The measured latency excludes:

- STT endpointing
- Text chunk threshold
- TTS first-audio latency
- Browser/Telnyx playback buffering

Expected end-to-end first audio remains:

```text
STT final latency
+ Realtime first-text latency
+ text chunk gating
+ TTS first-audio latency
+ channel buffering
```

---

## 6. Language Critical Gate

### 6.1 English

**PASS for the tested factual and memory turns.**

Observed behavior:

- Correctly stated fifty-lakh price and included parking.
- Recalled `Arjun Rao` and `ZX forty two`.
- Accepted correction to `Varun Rao`.
- Later recap used `Varun Rao` and did not revert to Arjun.
- Did not request hangup for “I am busy now, maybe later.”

### 6.2 Hindi

**PASS on the isolated Unicode-safe rerun.**

The response used Devanagari and correctly conveyed:

- 2BHK starts at fifty lakh
- Parking is included

The first combined harness passed Hindi through PowerShell with the wrong input encoding, turning it into question marks. That result was discarded and rerun using Unicode escapes.

### 6.3 Telugu

**PARTIAL / NOT RELEASE-READY.**

The isolated response used Telugu script and communicated the known facts, but mixed English terms such as `included` and `2BHK`. This may be acceptable only if the product explicitly allows Tanglish; it does not prove high-quality natural Telugu.

### 6.4 Mixed Telugu-English

**CRITICAL FAIL.**

The model returned a mixture containing:

- Telugu
- Tamil
- Korean
- English

Unrequested Tamil and Korean script is a severe language-control failure for a customer-facing call. This requires a larger multilingual regression corpus and a strict script-contamination gate.

---

## 7. Session Memory and Cache Audit

### 7.1 Native Realtime session memory

**PASS in one persistent session.**

Evidence:

1. Caller supplied name `Arjun Rao` and reference `ZX forty two`.
2. A later turn asked for both without resending them.
3. The model recalled both.
4. Caller corrected the name to `Varun Rao`.
5. A later recap returned Varun and did not return Arjun.

This verifies in-session provider conversation memory. It does not prove persistence across reconnects, server restarts, calls, or customers.

### 7.2 Prompt caching

**PASS with direct provider usage evidence.**

Observed progression:

- First response: 4,985 input tokens, 0 cached
- Second response: 5,041 input tokens, 4,992 cached
- Later responses: approximately 5,056–5,248 cached input tokens

Aggregate:

```text
30,656 cached / 35,961 input = 85.25%
```

Cache requirements:

- Keep instructions and tool schemas at the start.
- Keep the prefix byte-stable.
- Append new conversation items instead of rebuilding/reordering the prefix.
- Persist provider usage fields; the local `prompt_cache_tracker` alone is not proof of billing cache hits.

### 7.3 Isolation not proven by this audit

The live test did not validate multi-worker call ownership or cross-call leakage because `RealtimeTextSession` is still only a plan. Required implementation tests remain:

- Call A cannot access Call B items.
- Customer A cannot access Customer B items.
- Browser reconnect attaches to the same call only.
- Closed sessions are destroyed.

---

## 8. Hangup Audit

### 8.1 Non-terminal statement

Input:

```text
I am busy now, maybe later.
```

Result:

- No `end_call` tool emitted.
- PASS.

### 8.2 Explicit hangup

Input:

```text
Please stop calling and end this call now.
```

Isolated result:

```json
{
  "should_end": true,
  "reason": "goodbye",
  "farewell": "Goodbye, and take care!"
}
```

The payload was passed into the implemented `validate_end_call()` with two completed turns.

Gate result:

```json
{
  "accepted": true,
  "should_end": true,
  "reason": "goodbye",
  "reject_code": null
}
```

This proves the model tool payload can pass the existing deterministic server gate.

### 8.3 Reliability failure

In the longer cache/memory session, the explicit hangup turn returned:

- `response.status = failed`
- No output
- No tool
- Zero usage tokens

The following summary response also failed in that session.

The isolated retry succeeded, so this is an intermittent or context/tool-configuration reliability failure—not a permanent capability failure. A production hangup path cannot rely on a single model attempt.

Required behavior:

1. Deterministically detect explicit caller stop/hangup language before waiting for the model.
2. Continue to use `validate_end_call()` as the final gate.
3. If the model response fails on an explicit stop request, end safely using server evidence rather than keeping the caller trapped.
4. Never let the model directly close Telnyx/browser transport.

---

## 9. JSON Output and Post-Call Summary Audit

### 9.1 Realtime function JSON

The Realtime model emitted syntactically valid JSON arguments for `save_call_outcome`.

However, it failed the required semantic/schema gate:

- `next_action` was an object although the schema allows only string or null.
- `summary_te` was Tamil, not Telugu.
- The tool was called on the first turn instead of after the call ended.
- Because it ran early, it omitted the later Thursday-at-four detail.

Verdict: **valid JSON is not equivalent to valid structured output**.

OpenAI Realtime tool calling must not be used as the only producer of authoritative `outcome.json` or `call_summary.json`.

### 9.2 Implemented `outcome.json` path

Relevant code:

- `server/call/post_call_pipeline.py`
- `server/call/outcome_schema.py`
- `server/providers/openai_llm.py`

The implementation selects:

```text
meta.resolved_stack.llm.provider
meta.resolved_stack.llm.model
```

for post-call `structured_completion()`.

With the locked model set to `gpt-realtime-2.1-mini`, the actual post-call test made three attempts and received:

```text
HTTP 404 model_not_found
The model `gpt-realtime-2.1-mini` does not exist or you do not have access to it.
```

The model exists on `/v1/realtime`; it is not available through the Responses endpoint used by `structured_completion()`.

The pipeline then returned the fallback:

- `disposition: no_outcome`
- Empty English/Telugu summaries
- `generation_ok: false`
- Error text in notes

This is a blocking integration defect.

### 9.3 `call_summary.json`

No `call_summary.json` implementation exists under `server/`.

The current implemented post-call artifact is only:

```text
<call directory>/outcome.json
```

The additional summary file described in `VOICE_AGENT_PRESETS.md` is planned, not implemented or tested.

### 9.4 Required architecture

Use separate locked roles:

```text
Live call:
  selected Realtime/Live model over WebSocket

Post-call:
  separately configured structured-output model over Responses/generateContent
  using OUTCOME_JSON_SCHEMA
```

Do not inherit the Realtime model identifier for post-call HTTP structured completion.

Validate all generated JSON locally before writing:

- Required keys
- Exact field types
- Disposition enum
- Telugu-script verification for `summary_te`
- English verification for `summary_en`
- No unexpected properties
- No premature summary before ledger sealing

---

## 10. Existing Regression Tests

Command:

```text
python -m pytest
  server/tests/test_end_call_validate.py
  server/tests/test_post_call_pipeline.py
  server/tests/test_memory_cache_regression.py
  server/tests/test_call_ledger.py -q
```

Result:

```text
28 passed in 3.11s
```

These tests confirm local deterministic behavior, but most provider calls are mocked. They did not catch:

- Realtime model incompatibility with the Responses endpoint
- Gemini text-output rejection
- Function arguments violating the declared schema
- Tamil/Korean contamination
- Long-session Realtime response failure

---

## 11. Critical Findings

### Blocking

1. Gemini Live cannot satisfy the required text-output architecture with the tested model.
2. `post_call_pipeline` incorrectly uses the locked Realtime model for HTTP structured completion.
3. `call_summary.json` is not implemented.
4. Realtime function arguments are not reliably schema-conformant.
5. Mixed Telugu-English generated unrelated scripts.

### High

6. Explicit hangup failed once in the long session.
7. Telugu output quality is not yet natural enough for a critical production gate.
8. Current tests do not exercise a real Realtime provider.
9. The plan's model allowlist/pricing section must restore `gpt-realtime-2.1` and `gpt-realtime-2.1-mini`; both were returned by the authenticated OpenAI catalog and are documented on OpenAI's developer pricing page.

### Confirmed strengths

10. OpenAI mini supports persistent text input/output over Realtime WebSocket.
11. No OpenAI audio tokens were used.
12. Native session memory retained facts and corrections.
13. Prompt caching produced direct, substantial billing evidence.
14. The isolated hangup tool output passed `validate_end_call()`.
15. English and isolated Hindi factual responses passed the tested checks.

---

## 12. Release Gate Before Implementation Approval

The architecture may proceed only after:

- [ ] Choose OpenAI-only for the first text-Realtime release, or obtain a Gemini model that successfully accepts `TEXT` output.
- [ ] Add real-provider Realtime integration tests to CI/manual release gates.
- [ ] Separate live Realtime model selection from post-call structured-output model selection.
- [ ] Implement and validate `call_summary.json`.
- [ ] Make explicit caller hangup deterministic even when model generation fails.
- [ ] Run at least 100 turns each for English, Hindi, Telugu, and mixed Telugu-English.
- [ ] Reject output containing unrelated Indian/non-Indian scripts.
- [ ] Validate every tool argument against JSON Schema before using it.
- [ ] Record input, cached input, output, reasoning, and audio tokens per response.
- [ ] Assert audio token counts remain zero.
- [ ] Measure cost per actual call duration, not a fixed assumed provider rate.
- [ ] Test reconnect, cancellation, concurrent calls, and cross-call isolation.

Until these pass, the safest target is:

```text
Selected streaming STT
→ final transcript text
→ OpenAI gpt-realtime-2.1-mini persistent text session
→ streamed text
→ selected streaming TTS

plus a separate structured-output HTTP model for post-call JSON.
```

Gemini must remain disabled for this text-only LLM path until a live handshake proves text output support.

---

## 13. Full Stack Per-Minute Cost — OpenAI Realtime + Sarvam/Cartesia STT/TTS

This section answers one question: **what does one minute of a live voice call cost if the LLM is OpenAI Realtime text-only and STT/TTS are independently chosen from Sarvam or Cartesia?**

Gemini is excluded here because the Live text-output handshake failed. No Gemini stack cost was measured.

FX rate used below: **₹95.64/$** from the environment (`FX_RATE_INR`). Cartesia USD conversion uses the **Pro-plan** credit rate already coded in `usage_pricing.py`: **$5 / 100,000 credits**.

### 13.1 How the bill is built — three separate meters

```text
1-minute voice-call cost
  = STT cost   (inbound caller audio duration)
  + LLM cost   (OpenAI Realtime text tokens)
  + TTS cost   (characters the agent speaks)
  + telephony  (Telnyx/Exotel/Plivo — NOT included below)
```

| Stage | Who is billed | What they count | When it grows |
|---|---|---|---|
| **STT** | Sarvam or Cartesia | Seconds of inbound audio, including silence | Whole call if realtime STT stays open |
| **LLM** | OpenAI Realtime | Text input + cached input + text output tokens | Longer prompts, more turns, cache misses |
| **TTS** | Sarvam or Cartesia | Characters sent to speech, including spaces | Agent talks more, or replies are longer |

Important:

- OpenAI does **not** bill audio in this architecture. Measured audio tokens were **zero**.
- STT is **not** billed by transcript words. A quiet 60-second stream still costs 60 seconds.
- TTS is **not** billed by audio seconds. A short sentence is cheaper than a long one even if both play for similar time.
- Changing STT does not change TTS price. Changing TTS does not change STT price. The LLM price stays the same in every row below.

### 13.2 Published unit rates used in this audit

| Provider | Product | Official rate | 1-minute equivalent |
|---|---|---|---|
| Sarvam | STT `saaras:v3` / `saaras:v3-realtime` | ₹30 / hour of audio | **₹0.50 / min** = **$0.00523 / min** |
| Cartesia | STT `ink-whisper` realtime WebSocket | 1 credit / second | 60 credits = **$0.00300 / min** = **₹0.29 / min** |
| Cartesia | STT `ink-2` realtime WebSocket | 3 credits / second | 180 credits = **$0.00900 / min** = **₹0.86 / min** |
| OpenAI | `gpt-realtime-2.1-mini` text | $0.60 / $0.06 / $2.40 per 1M in / cached / out | **$0.00423 / min** measured with cache |
| Sarvam | TTS `bulbul:v3` | ₹30 / 10,000 characters = ₹3 / 1,000 characters | depends on how much the agent says |
| Cartesia | TTS `sonic-3.5` | ~1 credit / character ≈ **$50 / 1M characters** | depends on how much the agent says |

Sources:

- Sarvam: <https://www.sarvam.ai/api-pricing>
- Cartesia: <https://docs.cartesia.ai/pricing>
- OpenAI: <https://developers.openai.com/api/docs/pricing>

Cartesia `ink-2` is shown as a **published** realtime rate only. The live REST probe on this account returned `model_not_found`. Do not assume Ink-2 works until a realtime WebSocket test succeeds.

### 13.3 What was actually tested live

Authenticated REST probes used the keys already in `.env`. No secrets are printed here.

**TTS — all four languages/samples succeeded on both providers**

| Sample | Chars | Sarvam `bulbul:v3` | Cartesia `sonic-3.5` |
|---|---:|---|---|
| English parking | 107 | 6.23 s audio, 3,116 ms | 6.88 s audio, 1,680 ms |
| English memory recap | 124 | 7.68 s audio, 2,295 ms | 8.72 s audio, 1,404 ms |
| Hindi price | 60 | 4.01 s audio, 1,441 ms | 4.32 s audio, 1,098 ms |
| Telugu parking | 53 | 4.78 s audio, 1,617 ms | 5.28 s audio, 1,211 ms |
| **Total** | **344** | **22.70 s** | **25.20 s** |

Measured speaking density:

- Sarvam: **15.15 characters per second** of generated audio
- Cartesia: **13.65 characters per second** of generated audio

Cartesia was consistently faster to return audio. Sarvam packed a little more speech into each second.

**STT — English and Hindi worked; Telugu did not**

Cartesia-generated clips were sent to both STT providers.

| Sample | Sarvam `saaras:v3` | Cartesia `ink-whisper` | Cartesia `ink-2` REST |
|---|---|---|---|
| English parking | Correct | Correct | `model_not_found` |
| English memory | Correct | Correct | `model_not_found` |
| Hindi price | Correct Devanagari | Correct Devanagari | not tested |
| Telugu parking | Garbled Telugu | Failed — repetitive garbage | not tested |

Cost tables below still include Telugu-capable combinations because billing does not wait for quality. Quality is a separate release gate.

### 13.4 Two 1-minute workloads

Both use the **same measured OpenAI Realtime LLM cost** of **$0.00423 / minute** (85.25% cache hit, zero audio tokens).

**Workload A — balanced call (recommended comparison)**

- 60 seconds of inbound STT audio
- Agent talks for 30 seconds
- TTS characters come from the live speaking-density measurement

```text
Sarvam TTS chars  = 15.15 × 30s = 455 characters
Cartesia TTS chars = 13.65 × 30s = 410 characters
```

**Workload B — this audit's actual Realtime verbosity**

The measured Realtime session produced about **889 assistant characters** over **1.527 minutes** ≈ **582 TTS characters per call minute**. That is a talkative agent (about 38 seconds of Sarvam speech per minute).

Use Workload A to compare stacks fairly. Use Workload B to estimate this specific test conversation.

### 13.5 Component cost per minute

| Component | USD / min | INR / min | Notes |
|---|---:|---:|---|
| Sarvam STT | $0.00523 | ₹0.50 | Full 60 s inbound stream |
| Cartesia Ink Whisper STT (realtime) | $0.00300 | ₹0.29 | Full 60 s inbound stream |
| Cartesia Ink-2 STT (published realtime) | $0.00900 | ₹0.86 | Not live-verified on this account |
| OpenAI Realtime mini LLM (cached, measured) | $0.00423 | ₹0.40 | Text only |
| OpenAI Realtime mini LLM (if cache missed) | $0.01507 | ₹1.44 | Same tokens, no cache discount |
| Sarvam TTS — Workload A (455 chars) | $0.01426 | ₹1.36 | ₹3 / 1,000 chars |
| Cartesia TTS — Workload A (410 chars) | $0.02048 | ₹1.96 | $50 / 1M chars |
| Sarvam TTS — Workload B (582 chars) | $0.01826 | ₹1.75 | Talkative agent |
| Cartesia TTS — Workload B (582 chars) | $0.02911 | ₹2.78 | Talkative agent |

### 13.6 Comparison table — Workload A (balanced 1-minute call)

Every row uses **OpenAI `gpt-realtime-2.1-mini` text-only Realtime**. Only STT and TTS change.

| Stack | STT | LLM | TTS | **Total USD / min** | **Total INR / min** | Share |
|---|---:|---:|---:|---:|---:|---|
| **Cheapest:** Cartesia Whisper + Sarvam TTS | $0.00300 | $0.00423 | $0.01426 | **$0.02149** | **₹2.06** | STT 14% · LLM 20% · TTS 66% |
| Sarvam STT + Sarvam TTS | $0.00523 | $0.00423 | $0.01426 | **$0.02372** | **₹2.27** | STT 22% · LLM 18% · TTS 60% |
| Cartesia Whisper + Cartesia TTS | $0.00300 | $0.00423 | $0.02048 | **$0.02771** | **₹2.65** | STT 11% · LLM 15% · TTS 74% |
| Cartesia Ink-2 + Sarvam TTS | $0.00900 | $0.00423 | $0.01426 | **$0.02749** | **₹2.63** | Published STT rate only |
| Sarvam STT + Cartesia TTS | $0.00523 | $0.00423 | $0.02048 | **$0.02994** | **₹2.86** | STT 17% · LLM 14% · TTS 68% |
| **Most expensive live-safe row:** Sarvam + Cartesia TTS | $0.00523 | $0.00423 | $0.02048 | **$0.02994** | **₹2.86** | If Ink-2 is excluded |
| Cartesia Ink-2 + Cartesia TTS | $0.00900 | $0.00423 | $0.02048 | **$0.03371** | **₹3.22** | Published STT rate only |

Read it this way:

```text
₹2.06 to ₹2.86 per minute for stacks that actually worked in the live probe
TTS is the largest slice
OpenAI Realtime text is the smallest slice once cache is warm
```

### 13.7 Comparison table — Workload B (this audit's talkative agent)

Same LLM. More TTS characters.

| Stack | STT | LLM | TTS | **Total USD / min** | **Total INR / min** |
|---|---:|---:|---:|---:|---:|
| Cartesia Whisper + Sarvam TTS | $0.00300 | $0.00423 | $0.01826 | **$0.02550** | **₹2.44** |
| Sarvam STT + Sarvam TTS | $0.00523 | $0.00423 | $0.01826 | **$0.02772** | **₹2.65** |
| Cartesia Whisper + Cartesia TTS | $0.00300 | $0.00423 | $0.02911 | **$0.03634** | **₹3.48** |
| Sarvam STT + Cartesia TTS | $0.00523 | $0.00423 | $0.02911 | **$0.03857** | **₹3.69** |
| Cartesia Ink-2 + Sarvam TTS | $0.00900 | $0.00423 | $0.01826 | **$0.03150** | **₹3.01** |
| Cartesia Ink-2 + Cartesia TTS | $0.00900 | $0.00423 | $0.02911 | **$0.04234** | **₹4.05** |

A more talkative agent adds about **₹0.38–₹0.83 / minute**, almost entirely in TTS.

### 13.8 If OpenAI prompt cache misses

Add **$0.01084 / minute (₹1.04 / minute)** to every row above.

Example, Workload A:

| Stack | Cached total | Uncached total |
|---|---:|---:|
| Cartesia Whisper + Sarvam TTS | $0.02149 / ₹2.06 | $0.03233 / ₹3.09 |
| Sarvam + Sarvam | $0.02372 / ₹2.27 | $0.03456 / ₹3.31 |
| Sarvam + Cartesia TTS | $0.02994 / ₹2.86 | $0.04077 / ₹3.90 |

Keep the compiled instruction prefix byte-stable. Cache is the main LLM cost control.

### 13.9 Easy takeaway

| Decision | Result from this audit |
|---|---|
| Cheapest working 1-minute stack | **Cartesia Ink Whisper STT + OpenAI Realtime mini + Sarvam Bulbul TTS ≈ ₹2.06 / min** |
| Default all-Sarvam stack | **₹2.27 / min** — only ₹0.21 more, and Telugu STT was better than Cartesia |
| Lowest latency TTS | **Cartesia Sonic** — about 0.5–1.4 s faster in the live probe, but **₹0.59 more per minute** on Workload A |
| Most expensive published combo | Cartesia Ink-2 + Cartesia Sonic ≈ **₹3.22 / min** (Ink-2 not live-verified) |
| What dominates cost | **TTS characters**, not the Realtime LLM |
| What OpenAI Realtime saved vs audio Realtime | Audio input/output tokens stayed **$0** |
| What is still missing from the rupee figure | Telnyx/PSTN minutes, retries, barge-in waste, failed turns, post-call HTTP summary model |

Recommended default for this product, based on cost **and** the Telugu STT failure:

```text
Sarvam saaras:v3-realtime   STT   ₹0.50 / min
OpenAI gpt-realtime-2.1-mini LLM   ₹0.40 / min  (warm cache)
Sarvam bulbul:v3             TTS   ₹1.36 / min  (balanced talk)
────────────────────────────────────────────
Typical all-Sarvam minute           ₹2.27
```

Use Cartesia Sonic only when a latency test on the same script beats Sarvam by enough to justify the extra **₹0.59–₹1.04 / minute**.

Do not pick Cartesia Ink Whisper as the Telugu STT default from this probe. It looped on the Telugu sample. Cartesia Ink-2 was not available on the REST endpoint used here.

These are **LLM + STT + TTS** minutes only. Add telephony separately.
