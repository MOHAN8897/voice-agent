# PSTN fixes and verification

No live calls were placed. Automated tests use fake carrier/provider transports.

## Issues fixed

- **Critical — answered call without media.** `streaming_start` HTTP success had no WSS-connect deadline, and late HTTP/dial responses could overwrite a connected state. Added bounded connect recovery, preserved newer lifecycle state, and separated carrier `streaming.started` from receipt of WSS `start`. A received WSS start is recorded before slow lifecycle setup. Duplicate socket cleanup cannot complete the owning call.
- **High — choppy audio / queue gaps.** The sender could catch up in bursts after scheduling delays, pad arbitrary callbacks, and treat a dequeued frame as finished. It now preserves source samples across callbacks, uses the source rate for L16 conversion, adds 40 ms startup headroom, checks monotonic pacing deadlines, and tracks in-flight frames through drain. L16 remains mono 16 kHz, 640 bytes per 20 ms frame. Send failures close the failed media transport rather than silently abandoning the sender.
- **High — delayed or lost caller turn.** Removed 400 ms of redundant post-STT-final waiting (550 → 150 ms); reduced prewarm adoption wait from 3 s to 150 ms; cancelled orphan prewarm work. Added release of pending caller speech after the RTP queue drains. Metrics now include `stt_final_to_llm_ms` and `stt_final_to_first_audio_ms`, alongside STT, first-token, TTS, and Telnyx stage timings.
- **High — unreliable interruption.** Windows timers could wake before the hold expired and permanently miss a lone partial. Confirmation now checks a monotonic deadline and tracks playback generations after TTS finishes. Barge clears conversion buffers and invalidates queued/in-flight audio. The partial fallback uses the latest text after an 800 ms quiet window. Old carrier-clear/LLM-cancel operations finish before a new response starts. Turn ownership remains held through TTS cleanup.
- **High — settings ignored.** Config previously persisted UI preferences only. Explicit **Save Config** commits an agent-scoped call configuration and aligns its STT/TTS runtime fields. Inbound and inherited outbound paths resolve `test-studio:{agentId}`; saved configuration merges with explicit call overrides and reaches browser lifecycle resolution too. Individual agent-scoped VAD/TTS edits are no longer dropped or replaced by preset values. Fine-tune now has visible Save controls, saving/error feedback, and runtime refreshes for the browser panel. Saved tiers survive hydration; failed autosaves are not marked successful.
- **High — cold greeting failure.** Optional prewarm failure falls back to cold setup; a greeting that fails before emitting audio gets one retry. Persistent startup failures reach carrier hangup/cleanup rather than leaving an answered silent call.

The existing token metadata merge and Redis call-registry merge were retained. Outbound client state now also carries stack metadata for recovery. No carrier live-call quality claim is made from unit tests.

## Verification without dialing

1. Run `python -m pytest server/tests/test_pstn_quality_regressions.py server/tests/test_pstn_acceptance.py server/tests/test_telnyx_pstn_bridge.py server/tests/test_pstn_critical_loop.py server/tests/test_pstn_production_fixes.py server/tests/test_session_stack.py server/tests/test_realtime_text.py server/tests/test_tts_instructions.py server/tests/test_pstn_prewarm.py server/tests/test_voice_stt_runtime.py server/tests/test_barge_history_and_pstn.py server/tests/test_pstn_stack.py server/tests/test_stack_resolver.py -q`.
2. Run `node web/node_modules/typescript/bin/tsc --noEmit --project web/tsconfig.json`.
3. In Test Studio, change Config and click **Save Config**. Change Fine-tune voice/VAD and click **Save voice / VAD**. Reload, then restart the API without `--reload`; verify those values remain for the same agent. Check another agent remains unchanged. The committed configuration is `prefs.callConfig` from `/api/test-studio/prefs?sessionId=test-studio:AGENT_ID`; runtime is `/api/settings/runtime?sessionId=test-studio:AGENT_ID`.
4. Simulated regressions cover missing-WSS retries, late responses, continuous sample framing, in-flight drain, saved settings after store recreation, partial fallback, prewarm cancellation, and duplicate socket cleanup. Existing tests cover Redis token roundtrips and generation rejection at the actual send lock.
5. Start the API with `python -m uvicorn server.app:app --host 127.0.0.1 --port 8000` (no `--reload`; use Redis when using multiple workers). `/api/health` should return `ok: true`.

## Optional live verification — only when authorized

Test one cold outbound and one inbound call. Confirm the first answered leg greets, sustained speech has no gaps, and a short interruption stops old audio. Check saved language/voice/prompts and VAD values. In media diagnostics, confirm 640-byte L16 frames, zero unexpected drops, and healthy `stt_final_to_first_audio_ms` clearly below approximately 1–1.5 s. Compare under the same provider/network conditions. Real Redis deployment and handset audio remain integration checks; no live dial is required for the regression suite.

Carrier contract reference: [Telnyx media streaming](https://developers.telnyx.com/docs/voice/programmable-voice/media-streaming) documents L16 at 16 kHz and carrier queue clearing.
