# PSTN realtime (Gemini 3.8 Live + Telnyx) — focused audit

Scope: WebSocket / Redis / Telnyx media, language config, hangup edge cases, stack wiring, Usage per turn (Telnyx + Gemini). Excludes audio buffering, playout, and generic VAD tuning (assumed working).

**Audit date:** 2026-09-28  
**Branch reviewed:** `working-app-27/09/2026` (post `ddce20d`)  
**Verification date:** 2026-09-28 — all issues below confirmed against current codebase.

**Legend:** `✅ VERIFIED` in the tables means the audit **found** the risk or behavior in code at review time. It does **not** mean the issue is fixed. See [§7 Fix pass status](#7-fix-pass-status-2026-09-28) for what changed after the audit.

---

## Reusable audit prompt (optimized for this repo)

Use this in a fresh session so the agent stays in scope:

```
Audit the voice-agent repo for PSTN realtime_voice (Gemini 3.8 Live + Telnyx) only.

In scope:
1) Telnyx media WebSocket path (server/routes/telnyx_ws.py, server/services/telnyx_pstn_bridge.py, server/routes/telnyx.py streaming state), Redis mirrors (telnyx_stream_tokens, TelnyxCallRegistry, server/call/redis_memory_cache.py), and multi-worker failure modes.
2) Language misconfigurations: Test Studio language vs meta.language vs @language entity tags vs compiled_brain contradictions (en-US vs te-IN), and how they reach build_gemini_audio_session_instructions / validate_end_call.
3) Hangup: request_end_call / end_call_validate / pstn_realtime_voice_core backup paths (user_transcript, fast_ack, farewell, side-session), and stack/tool declarations on Gemini Live.
4) Stack: web/lib/test-studio-stack.ts pipeline realtime_voice, stack_override on dial, resolved_stack vs actual runtime (ignore Sarvam STT/TTS for realtime_voice).
5) Usage per turn: server/services/usage_pricing.py + call_ledger stamp_ended_usage vs web/lib/usage-cost.ts + TestStudioTurnMetrics (Telnyx components, Gemini session-cumulative tokens, post-call transcribe line, connected_at duration).

Out of scope: jitter buffers, PCM queue depth, Cartesia/Sarvam non-realtime paths, voxly-ai console, unrelated SaaS billing.

Deliver: markdown issue list with severity (P0–P3), file references, user-visible symptom, and suggested fix direction. Use `graft ask` / `graft grep` before reading whole files. Do not commit unless asked.
```

---

## 1. WebSocket, Redis, Telnyx media

| ID | Sev | Status | Symptom | Cause (code) | Fix direction |
|----|-----|--------|---------|--------------|---------------|
| WS-1 | **P0** | ✅ VERIFIED | Outbound call rings but media never connects; logs `stream.unauthorized` / WS closes 1008 | `telnyx_stream_ws` requires a valid stream token; metadata comes from process memory or Redis (`TelnyxStreamTokens.peek`). Webhook/dial on worker A and WS on worker B **without** working `REDIS_URL` → token not found. **Confirmed:** `server/routes/telnyx_ws.py:L17-L45` — token validated, closes 1008 on miss. `TelnyxStreamTokens` class in `server/services/telnyx_client.py:L554-L641` — `peek()` checks process-local then Redis. | Run single worker **or** set `REDIS_URL` and verify `check_redis_health`. Hint is explicit in `server/routes/telnyx_ws.py`. |
| WS-2 | **P1** | ✅ VERIFIED | Intermittent "no media" after deploy / Redis blip | `redis_memory_cache._redis()` uses **0.25s** timeouts and marks Redis unavailable on any error; Telnyx registry/token writes **fail silently** (`except: pass`). **Confirmed:** `server/call/redis_memory_cache.py:L25-L43` — `socket_connect_timeout=0.25, socket_timeout=0.25`, `_mark_unavailable` on error. `TelnyxCallRegistry.upsert` at `server/services/telnyx_client.py:L350-L370` — `except Exception: pass` on Redis write. | Monitor Redis; lengthen timeouts or retry; surface registry write failures in PSTN_STREAM logs. |
| WS-3 | **P1** | ✅ VERIFIED | Streaming stuck "retrying" then call dropped | `_ensure_telnyx_streaming` terminal path hangs up after `_STREAM_MAX_FAILURE_RETRIES` when `PUBLIC_WSS`/stream start fails (`server/routes/telnyx.py`). **Confirmed:** `server/routes/telnyx.py:L20` — `_STREAM_MAX_FAILURE_RETRIES = 3`. `_ensure_telnyx_streaming` at `L141`. Hangup on exhausted retries at `L189`. | Ensure `PUBLIC_TUNNEL_URL` / public API base matches the URL Telnyx can reach; check `stream_failed` / `stream_error` on registry row. |
| WS-4 | **P2** | ✅ VERIFIED | Duplicate or ghost media WS during outbound ring | Dial-time `stream_url` can open WS before answer; bridge raises `_OutboundPreAnswerStream` (`telnyx_pstn_bridge.py`). Live path expects **answer** + `start_streaming`. Mis-timed WS can confuse `stream_connected` until answer WS wins. **Confirmed:** `server/services/telnyx_pstn_bridge.py:L49` — `class _OutboundPreAnswerStream(RuntimeError)`, raised at `L380`, caught at `L278`. | Prefer answer-time streaming only (already commented in `telnyx_client`); avoid relying on ring-time WS for agent audio. |
| WS-5 | **P2** | ✅ VERIFIED | Stale "active call" blocks new dials | `outbound_dial_guard` uses `telnyx_call_registry.list_recent()` which is **process-local** only (`TelnyxCallRegistry.list_recent`), not Redis-backed. **Confirmed:** `server/services/telnyx_client.py:L524-L527` — `list_recent` reads only from `self._calls` (process-local dict), never queries Redis. `server/services/outbound_dial_guard.py:L127,L147` — calls `list_recent`. | Multi-worker: list recent calls from Redis or DB, not in-memory dict per process. |
| WS-6 | **P2** | ✅ VERIFIED | `stream_connected` true in registry but caller hears silence | Registry sets `stream_connected` on WS `start` (`telnyx_pstn_bridge.py`); Gemini/OpenAI session can still fail later in `_on_start`. States are transport vs model readiness. **Confirmed:** Bridge writes `stream_connected` to registry; model session connect is a separate async step. | Correlate `PSTN_STREAM` events with `realtime_voice` connect errors in trace; don't treat `stream_connected` alone as "agent live". |
| WS-7 | **P3** | ✅ VERIFIED | Dev voice-check calls behave differently from production PSTN | Dev routes set `skip_stream` / `voice_check` (`dev_telephony.py`, `telnyx.py`) — streaming and recording skipped. **Confirmed:** `server/routes/telnyx.py:L161,L536-L539` — `skip_stream` / `voice_check` flags gate streaming and recording. `server/routes/dev_telephony.py:L1017-L1051` — voice-check dial sets these flags. | Expected; don't compare voice-check media to real PSTN. |

---

## 2. Language misconfiguration

| ID | Sev | Status | Symptom | Cause (code) | Fix direction |
|----|-----|--------|---------|--------------|---------------|
| LANG-1 | **P1** | ✅ VERIFIED | Agent speaks English on a te-IN call (or mixed Tanglish rules ignored) | Compiled brain can contain **contradictory** blocks: `meta.language` / session `te-IN`, but `@language: en-US`, `YOUR ROLE` "Speak this way: English (US)", and English `CANONICAL OPENING` while `SPOKEN LANGUAGE (te-IN)` demands Telugu. Compiler does not reconcile `@language` with session language (`script_entities.parse_entity_tags` vs `call_lifecycle` `language` param). **Confirmed:** `server/brain/script_entities.py:L128-L165` — `script_conflicts_with_brief` detects but does not auto-fix language conflicts. `server/prompts/agent_voice_rules.py:L106-L115` — `normalize_compile_language` converts codes. Divergence path: entity tag `@language` parsed separately from the session `language` parameter passed to compile. | Recompile script with matching `@language`; run `script_conflicts_with_brief` / entity backfill; align Test Studio language picker with agent compile language. |
| LANG-2 | **P2** | ✅ VERIFIED | Opening greeting language wrong on outbound | `opening_line` entity tag and prewarm greeting use script/brief language, not always `normalize_compile_language(session)`. **Confirmed:** `server/brain/script_entities.py:L193-L231` — `backfill_entity_tags_in_script` takes `language` param but prewarm greeting may read from script entities before backfill runs. | Ensure `backfill_entity_tags_in_script` and compile use same `language` as PSTN dial `stack_override.language`. |
| LANG-3 | **P2** | ✅ VERIFIED | Language mismatch line never plays; agent keeps guessing | `_maybe_mirror_caller_language` / mismatch handler gated on `ctx.language_mismatch_handled` (`pstn_realtime_voice_core.py`). Wrong language config may skip mismatch path. **Confirmed:** `server/services/pstn_realtime_voice_core.py:L1254` — `_maybe_mirror_caller_language` method. `L2195` — sets `ctx.language_mismatch_handled = True`. `server/call/call_context.py:L35` — flag default `False`. `server/prompts/agent_voice_rules.py:L754` — `language_mismatch_fallback_for` function. | Verify `language_mismatch_fallback_for(lang)` for configured lang; test with English-only caller on te-IN agent. |
| LANG-4 | **P3** | ✅ VERIFIED | Farewell / hangup text in wrong script | `default_farewell_for` uses `normalize_compile_language(language)` (`hangup_judge.py`); if loop `_resolve_language()` diverges from compile language, farewell locale can mismatch. **Confirmed:** `server/call/hangup_judge.py:L148-L152` — `default_farewell_for` normalizes via compile language. `server/services/pstn_realtime_voice_core.py:L1241` — `_resolve_language` method returns session language which can diverge from compile language. `L744` — `_localized_farewell` calls `default_farewell_for(self._resolve_language())`. | Single source: pass call `meta.language` from ledger into realtime loop at start. |

---

## 3. Hangup procedure — edge cases and misconfig

| ID | Sev | Status | Symptom | Cause (code) | Fix direction |
|----|-----|--------|---------|--------------|---------------|
| HUP-1 | **P1** | ✅ VERIFIED | Call drops with no farewell; caller still talking | Backup hangup arms from Gemini **`user_transcript`** events (`pstn_realtime_voice_core._arm_hangup_from_caller_words`) even when Live connect is `response_modalities: ["AUDIO"]` only — Google may still emit `input_transcription` (`gemini_voice.py`). Backup can beat model `request_end_call`. **Confirmed:** `server/services/pstn_realtime_voice_core.py:L2369-L2422` — `_arm_hangup_from_caller_words` sets `_set_hangup_arm_source("backup")`, gates on `caller_wants_to_continue` / `caller_firm_refusal`, then arms `_pending_end_call` independently from tool calls. | Prefer tool-sourced hangup; tighten backup to `tool_sourced` or disable backup when post-call transcript mode; ensure model uses `request_end_call` + farewell in one turn. |
| HUP-2 | **P1** | ✅ VERIFIED | Hangup during callback flow rejected / never ends | `validate_end_call` blocks `should_end` while `callback_close_phase` is `collecting_name` / `collecting_phone` or when `agent_still_collecting_lead` (`end_call_validate.py`). Model may say goodbye while platform refuses hangup. **Confirmed:** `server/call/end_call_validate.py:L496-L636` — rejection with `code=caller_engaged` or `code=lead_details_missing` when callback fields incomplete. | Train/policy: complete callback fields before end_call; or adjust gates for firm_refusal/goodbye overrides. |
| HUP-3 | **P2** | ✅ VERIFIED | "Hello?" during closing hangs up immediately | `hangup.fast_ack` / `_finish_hangup()` on simple hello during `_pending_end_call` (`user_transcript` handler). Side-session farewell mitigates only if `_ensure_hangup_farewell_audio` runs first. **Confirmed:** `server/services/pstn_realtime_voice_core.py:L746` — `_farewell_audio_engaged` property, checked at `L805`, `L1012`, and `L2561` before `_finish_hangup`. | Already partially fixed; verify `farewell_audio_engaged` before `_finish_hangup` on fast_ack. |
| HUP-4 | **P2** | ✅ VERIFIED | Model says goodbye but call stays up | `caller_engaged` / `stay_on_line` rejections in `validate_end_call`; or tool never called and repair path requires `agent_spoke_closing` + `caller_confirmed_goal_complete` (`_maybe_hangup_missed_end_call`). **Confirmed:** `server/services/pstn_realtime_voice_core.py:L2424` — `_maybe_hangup_missed_end_call` method, invoked at `L2856`. `server/call/end_call_validate.py` — rejection logged as `[END_CALL] rejected code=...`. | Trace `[END_CALL] rejected code=...` in logs; tighten hangup judgment in brain vs platform gates. |
| HUP-5 | **P2** | ✅ VERIFIED | `request_end_call` reason mapping dropped | `parse_request_end_call_tool` maps limited reason keys (`hangup_tools.py`); invalid reason → tool ignored. **Confirmed:** `server/realtime/hangup_tools.py:L18-L27` — `_REQUEST_TO_INTERNAL` maps only: `customer_declined`, `caller_goodbye`, `goal_complete`, `abuse`, `out_of_scope`, `firm_refusal`, `goodbye`. At `L83-L108` — `parse_request_end_call_tool` returns `None` if reason not in map. | Use documented reasons: `goodbye`, `firm_refusal`, `goal_complete`, `abuse`, etc. |
| HUP-6 | **P3** | ✅ VERIFIED | Hangup allowed reasons in brain don't match runtime policy | `format_call_end_section` merges agent `call_end_policy` with `HANGUP_JUDGMENT_RULES`. Mismatch between compiled brain and `ctx.call_end_policy` on start. **Confirmed:** `server/call/call_end_policy.py:L50-L65` — `format_call_end_section` merges `normalized["allowedReasons"]` with `HANGUP_JUDGMENT_RULES`. | Align agent JSON policy with Test Studio fine-tune export. |

---

## 4. Stack / realtime PSTN wiring

| ID | Sev | Status | Symptom | Cause (code) | Fix direction |
|----|-----|--------|---------|--------------|---------------|
| STK-1 | **P1** | ✅ VERIFIED | PSTN uses text pipeline (Sarvam STT/TTS) instead of Live | `stack_override.pipeline` must be `realtime_voice` (`test-studio-stack.ts` `buildPstnRealtimeStackOverride`). Tier-only mode can leave `realtime_text` if UI not on PSTN realtime mode. **Confirmed:** `web/lib/test-studio-stack.ts:L169` — `buildPstnRealtimeStackOverride` function. `web/components/test-studio/AgentTestStudio.tsx:L295,L769` — used on dial. `server/services/saas/pstn_saas_stack.py:L34-L43` — `saas_stack_override` forces `pipeline: "realtime_voice"`. | Confirm Test Studio mode + `PstnTestPanel` sends `stackOverride` with `pipeline: "realtime_voice"` and `llm.model` gemini-*-live or gpt-realtime-*. |
| STK-2 | **P2** | ✅ VERIFIED | `resolved_stack` shows Sarvam STT/TTS but call is Live | Combination/tier resolution still fills stt/tts slots (`meta.resolved_stack`) while runtime ignores them for `realtime_voice`. Operators think STT model affects PSTN Live. **Confirmed:** `server/call/post_call_transcription.py:L33-L41` — `call_uses_gemini_post_call_transcript` reads `resolved_stack.llm.model` regardless of stt/tts slots. | UI copy already partial; history/metadata should label "Live only — stack STT/TTS ignored". |
| STK-3 | **P2** | ✅ VERIFIED | Wrong LLM on PSTN after switching stack in UI | `AgentTestStudio` syncs `llmModel` from runtime prefs; dial must pass latest `stackOverride` on each POST. Stale session prefs → old OpenAI model. **Confirmed:** `web/components/test-studio/AgentTestStudio.tsx:L295` — `buildPstnRealtimeStackOverride` called with current `stack` and `language` on dial. If `llmModel` not refreshed from prefs, stale model sent. | Verify dev telephony dial payload includes current `stack_override`. |
| STK-4 | **P3** | ✅ VERIFIED (prewarm only) | Gemini tools missing on connect | `include_tools=False` on some connect paths would drop `request_end_call`. Default connect uses tools (`gemini_voice.py` `_gemini_tools`). **Confirmed:** `server/services/pstn_realtime_greeting_prewarm.py:L258` — `include_tools=False` for prewarm side-session (greeting-only, not main call path). `server/realtime/providers/gemini_voice.py:L184,L235` — `include_tools` param; when `True` (default), `_gemini_tools()` at `L62` is included. Main PSTN connect path uses default `include_tools=True`. **Risk is low:** only prewarm side-sessions omit tools, which is intentional since they are ephemeral greeting-only sessions. | Grep `connect(..., include_tools=False)` for PSTN paths. Low risk — only prewarm side-session affected, which is expected. |

---

## 5. Usage per turn — Telnyx & Gemini (miscalculation / mismatch)

| ID | Sev | Status | Symptom | Cause (code) | Fix direction |
|----|-----|--------|---------|--------------|---------------|
| USD-1 | **P2** | ✅ VERIFIED | Live Telnyx ₹ higher than invoice | UI and ledger assume **component list rates** + **recording** when `TELNYX_ESTIMATE_CALL_RECORDING` default true (`usage_pricing.telnyx_estimate_call_recording`). India outbound uses default **$0.009/min** SIP unless deck overridden. **Confirmed:** `server/services/usage_pricing.py:L656-L658` — `telnyx_estimate_call_recording()` returns `True` unless env `TELNYX_ESTIMATE_CALL_RECORDING` set to false. `.env.example:L164` — commented-out default. `server/call/call_ledger.py:L263,L271` — `call_recording=telnyx_estimate_call_recording()` in `stamp_ended_usage`. | Set env SIP deck vars; set `TELNYX_ESTIMATE_CALL_RECORDING=false` if recording disabled. |
| USD-2 | **P2** | ✅ VERIFIED | Telnyx ₹ wrong during call, correct after hangup | In-call Telnyx estimate uses `wallSec` from UI timer; stamped uses `duration_sec` from ledger (`connected_at` → hangup). Missing `callee_e164` until stream start → **US SIP** estimate instead of IN. **Confirmed:** `server/services/telnyx_pstn_bridge.py:L508-L514` — `callee_e164` and `connected_at` are only written to ledger when stream starts (`call.started` event), not at dial time. Before this, ledger has no destination E.164. `server/call/call_ledger.py:L266` — `telnyx_destination_country_from_e164(meta.get("callee_e164"))` returns US default when empty. | Ensure `telnyx_pstn_bridge` writes `callee_e164` + `connected_at`; pass `telnyxDestinationE164` in Test Studio. |
| USD-3 | **P2** | ✅ VERIFIED | "Prompt and conversation context" seems large | Gemini Live bills **text input** at $0.75/M separately from audio; large compiled brain + per-turn context re-billing (`meta.usage.gemini_billing_note`). Not double-counted with audio if token split is correct (`cost_llm_usd`). **Confirmed:** `server/services/pstn_realtime_voice_core.py:L538` — `meta["usage"]["gemini_billing"] = "session_cumulative_tokens"`. `server/call/call_ledger.py:L324` — `usage["gemini_billing"] = "session_cumulative_tokens"`. | Shrink instructions or rely on `context_window_compression` (already configured in `gemini_voice.py`). |
| USD-4 | **P2** | ✅ VERIFIED (minor naming fix) | Per-turn token table doesn't match session footer | Trace turns use **deltas** for Gemini (`token_scope: delta`, `session_snapshot` block in `record_realtime_voice_usage`). `AgentTestStudio` **sums** row tokens into `sessionTotals`; should approximate ledger if all rows loaded. Partial trace poll → underestimated in-call model cost until stamped usage loads. **Confirmed:** `server/services/pstn_realtime_voice_core.py:L276` — function is `record_realtime_voice_usage` (not `_record_realtime_usage`). `L479` — `"token_scope": "delta"`. `L322` — `session_snapshot = gemini_live and not prewarm`. `web/components/test-studio/AgentTestStudio.tsx:L564` — `sessionTotals` computed via `useMemo`. | Prefer `stampedUsage` from dev detail API when `callEnded`; don't sum rows for Gemini totals in UI. |
| USD-5 | **P2** | ✅ VERIFIED | Post-call line appears twice or inflates live total | Before hangup, UI adds **estimated** post-call from `costGeminiPostCallTranscribeUsd(wallSec)`; after stamp, ledger total includes real post-call. Brief window of overestimate is possible. **Confirmed:** `web/lib/usage-cost.ts:L67` — `costGeminiPostCallTranscribeUsd` function. `web/components/test-studio/TestStudioTurnMetrics.tsx:L249` — estimated cost added to pre-hangup total. `L242-L253` — after stamp, `stampedUsage.postCallTranscriptUsd` replaces estimate. | Show "est." label (partially done); after end use stamped only. |
| USD-6 | **P3** | ✅ VERIFIED | `GET /api/call/{id}` 401 → empty usage in studio | Auth-gated call detail; fallback to `/api/dev/telephony/calls/{id}/detail` only when dev session present (`fetchCallDetailForUsage`). **Confirmed:** `web/components/test-studio/AgentTestStudio.tsx:L46` — `fetchCallDetailForUsage` function. `L495,L703` — called on call end and on poll. | Log in to dev portal or fix cookie auth for `/api/call`. |
| USD-7 | **P3** | ✅ VERIFIED | Footer mentions `gpt-4o-mini-transcribe` on Gemini PSTN | `TestStudioTurnMetrics` copy branch for non-`postCallTranscript` gemini path (`gemini && !postCallTranscript`). **Confirmed:** `web/components/test-studio/TestStudioTurnMetrics.tsx:L357-L361` — three-way branch: `gemini && postCallTranscript` shows Gemini 3.5 Transcribe copy (correct), `gemini && !postCallTranscript` shows "Gemini Live text output" copy (correct), else shows "gpt-4o-mini-transcribe" copy. **Note:** The fallback `else` case (L361) shows the OpenAI transcribe copy for non-gemini models, which is correct. The `gemini && !postCallTranscript` branch (L360) actually shows correct Gemini copy. Issue is **not a bug** for the currently coded logic — the three-way branch is correct. However, if `postCallTranscript` is misconfigured while on Gemini, the wrong copy *could* appear. | When `post_call_transcript_enabled`, badge + copy should always show 3.5 post-call line. |
| USD-8 | **info** | ✅ VERIFIED | Gemini per-turn **cost** in trace is delta; **tokens** in row are delta after fix | Session cumulative billing is intentional (`gemini_billing: session_cumulative_tokens`). Summing `cost_usd` on trace turns should match `model_cost_usd` if all events present. **Confirmed:** `server/services/pstn_realtime_voice_core.py:L538` — `gemini_billing = "session_cumulative_tokens"`. `server/tests/test_gemini_pstn_regressions.py:L124` — test `test_gemini_response_usage_bills_session_cumulative_not_per_id`. | Document in UI "session totals from ledger after hangup". |

---

## 6. Cross-cutting checks (ops)

- **Redis:** `REDIS_URL` set, `GET /api/health` redis ok, same URL for all workers. ✅ `check_redis_health` at `server/db/redis_health.py:L9`.
- **Public URL:** `PUBLIC_TUNNEL_URL` / voice API base matches Telnyx connection webhook and WSS URL. ✅ `server/config/env.py:L131` — `public_tunnel_url` setting. `server/config/urls.py:L15-L17` — priority docs.
- **Post-call:** `POST_CALL_TRANSCRIPT_ENABLED`, recording attach on answer (`telnyx_recordings.py`). ✅ `server/call/post_call_transcription.py:L33-L41` — checks setting. `server/services/telnyx_recordings.py:L19` — gates on `skip_stream` / `voice_check`.
- **Language:** Test Studio language = compile language = `@language` tag = `meta.language` on call. ✅ All paths verified — divergence possible (LANG-1 through LANG-4).
- **After hangup:** `meta.usage.cost_is_estimate: false`, `duration_sec` matches answered→ended, `transcript_source` set when post-call completes. ✅ `server/call/call_ledger.py:L237-L330` — `stamp_ended_usage` sets `cost_is_estimate: False`.

---

## Summary counts

| Area | P0 | P1 | P2 | P3 | Verified |
|------|----|----|----|-----|----------|
| WS / Redis / Telnyx | 1 | 2 | 3 | 1 | 7/7 ✅ |
| Language | 0 | 1 | 2 | 1 | 4/4 ✅ |
| Hangup | 0 | 2 | 3 | 1 | 6/6 ✅ |
| Stack | 0 | 1 | 2 | 1 | 4/4 ✅ |
| Usage / cost | 0 | 0 | 5 | 2 | 8/8 ✅ |

**All 29 issues verified against current codebase** (as risks / behaviors to watch).

**Highest impact:** WS-1 (multi-worker without Redis), LANG-1 (brain language contradictions), HUP-1 (backup hangup vs farewell), STK-1 (wrong pipeline).

---

## 7. Fix pass status (2026-09-28)

Second pass on branch `working-app-27/09/2026`: post-audit code changes exist **locally** (9 files, ~124 lines) and are **not necessarily committed** after `ddce20d`. Prewarm path unchanged (`include_tools=False` on greeting prewarm only).

| ID | Fix | Notes |
|----|-----|-------|
| WS-1 | **Ops** | Startup log when `REDIS_URL` unset (`server/app.py`). Still requires Redis or single worker. |
| WS-2 | **Improved** | Registry/token Redis warnings; memory cache timeouts 1.0s / 0.75s (was 0.25s). |
| WS-3 | **Ops** | No code change — `PUBLIC_TUNNEL_URL` / stream retries. |
| WS-4 | **Open / design** | Answer-time streaming + `_OutboundPreAnswerStream` unchanged. |
| WS-5 | **Fixed** | `TelnyxCallRegistry.list_recent` merges Redis ZSET + per-call keys (`telnyx_client.py`). |
| WS-6 | **Doc / ops** | Transport vs model readiness — correlate logs, not product bug. |
| WS-7 | **N/A** | Dev voice-check by design. |
| LANG-1 | **Fixed** | `realign_compiled_brain_for_session` at call lock + prewarm; tag sync on save/backfill. |
| LANG-2 | **Fixed** | `@opening_line` regenerated when `@language` changes in `sync_entity_language_tag`. |
| LANG-3 | **Fixed** | Auto mismatch reminder on mirror when caller language ≠ agent (no tool race). |
| LANG-4 | **Fixed** | `_resolve_language` prefers ledger `meta.language` then stack. |
| HUP-1 | **Improved** | 220ms deferred backup so `request_end_call` tool can win same turn. |
| HUP-2 | **Improved** | `validate_end_call` allows caller goodbye/firm refusal during lead collect. |
| HUP-3 | **Improved** | Fast-ack waits for farewell when adapter present; stuck-response tries farewell before hangup. |
| HUP-4–6 | **Open / policy** | Platform gates, reason map, brain policy alignment — no broad code change. |
| STK-1 | **OK** | Existing `buildPstnRealtimeStackOverride` + SaaS override; user must pick realtime PSTN mode. |
| STK-2 | **Fixed** | `CallMetadataPanel` + history pipeline label “Realtime PSTN (Live only)”. |
| STK-3 | **OK** | Dial sends current `stackOverride` when UI refreshed. |
| STK-4 | **By design** | Prewarm without tools intentional. |
| USD-1 | **Ops** | Env SIP deck + `TELNYX_ESTIMATE_CALL_RECORDING`. |
| USD-2 | **Improved** | `callee_e164` on registry at dial + bridge fallback; Test Studio E.164 for in-call estimate. |
| USD-3 | **N/A** | Session-cumulative Gemini billing intentional. |
| USD-4 | **Fixed** | `sessionTotals` uses ledger-polled tokens for realtime PSTN when available. |
| USD-5 | **Improved** | “est.” label on post-call line before stamp; after end prefers stamped total when present. |
| USD-6 | **OK** | Dev detail API fallback in `AgentTestStudio` (from `ddce20d`). |
| USD-7 | **Improved** | Gemini PSTN footer copy (`TestStudioTurnMetrics`). |
| USD-8 | **Partial** | Footer note after hangup; no separate history badge. |

**Verdict (post second pass):** Runtime fixes cover language alignment, hangup deferral, usage UI, Redis, and Telnyx dest. **Still ops-only:** WS-1 (`REDIS_URL`), WS-3 (public URL), USD-1 (SIP deck env). **By design / monitor:** WS-4/6, HUP-4–6 policy, USD-3/8 billing model.

**Already on `ddce20d` (prior push):** post-call transcription, `connected_at` / billable duration, dev call detail API, transcript source badge, session timer after answer.

**Corrections applied during verification:**
- **USD-4:** Function name corrected from `_record_realtime_usage` → `record_realtime_voice_usage` (`server/services/pstn_realtime_voice_core.py:L276`).
- **USD-7:** Re-evaluated — the three-way copy branch is actually correct for the coded logic. Issue is conditional on `postCallTranscript` misconfiguration, not a hard bug. Severity kept at P3.
- **STK-4:** Clarified scope — `include_tools=False` only affects prewarm side-sessions (intentional), not the main PSTN call path. Risk downgraded in description.
