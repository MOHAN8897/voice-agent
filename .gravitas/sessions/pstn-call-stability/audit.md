# Primary PSTN call stability audit

Reviewed the two latest local call ledgers, transcripts, response traces, and their exact carrier CDRs on 21 October 2026. No new phone call was placed. No customer phone numbers or carrier credentials are included here.

## Observed calls

- Earlier call: 97 seconds answered talk time; 11 caller transcript segments; transcription status failed just after disconnect with RuntimeError. The carrier reports Normal Hangup, send_bye, Answer XML, and media stream termination **Connection error**.
- Latest call: approximately 110 seconds answered talk time; 13 caller transcript segments; transcription status later failed with stream_cancelled. The carrier again reports media stream termination **Connection error**. Native Gemini input text rendered one Telugu caller utterance as Hindi; the agent then used the platform's canned Telugu language reminder. Caller immediately corrected it.
- Several late model responses have usage records but no completed assistant transcript. This is consistent with interrupted/discarded replies; the available artifacts do not establish the cause of every individual interruption.
- Both local ledger reasons were user_stop. The bridge previously passed unknown prefixed reasons into a normalizer that converted them to user_stop, losing the actual disconnect classification.
- The historical API log had been replaced by a subsequent startup, so there is no preserved Python process crash traceback for these calls. Carrier media connection errors establish stream failure, not the root cause of a whole-process exit.

## Reproduced and fixed

1. Playback accounting discarded fractional frame time on each media read. A deterministic 120-second stream reproduced a false remaining playback backlog. Fractional decay now uses a separate clock and preserves the actual last-send time.
2. Local speech detection and provider VAD could cancel the same output generation twice. Cancellation is now idempotent for that generation; a later response can still be interrupted normally.
3. Carrier-disconnect cleanup closed the conversation adapter but omitted the live transcription stream. This left provider tasks pending until cancellation and could mark saved transcripts failed. Cleanup now performs the same bounded transcription final drain used by agent hangup.
4. Final completed assistant transcript/usage work is drained before the bridge can seal the ledger.
5. Gemini's language-barrier tool now asks a neutral selected-language clarification instead of accusing the caller of speaking another language. The Gemini instruction also warns against treating ASR spelling as reliable language evidence.
6. Bridge exceptions are contained to their call. Media and runtime disconnect reasons are saved without transcripts, credentials or raw provider exception text. Connection failures now retain ws_disconnect/provider_failure classifications; confirmed carrier hangups retain pstn_hangup. Diagnostic storage failure cannot prevent cleanup.

Code evidence:

- server/services/pstn_playback.py:91
- server/services/pstn_realtime_voice_core.py:1292, 2096, 2651, 4204
- server/services/vobiz_pstn_bridge.py:655, 689
- server/realtime/gemini_audio_session.py:306
- server/tests/test_pstn_call_stability.py

## Verification

- Before fixes: four new reproductions failed (playback drift, duplicate cancellation, missing transcription cleanup, pending provider task).
- After final fixes: **219 passed**, three warnings across primary lifecycle, prewarm, farewell, browser startup, carrier safety, transcription, call access, and new stability regressions.
- Includes a deterministic **160-second, 20-turn** primary call simulation that keeps answering without unsolicited hangup. This is a simulation, not a real recognition/voice-quality benchmark.
- Ruff passed for the new test and playback module; undefined-name check passed for modified existing runtime modules. Scoped whitespace check passed.
- Repository SAST passed: **290 rules, 1295 targets, zero findings**. Final changed-file custom SAST also passed with zero findings.
- Reticle skipped: backend-only changes; no frontend component was changed.
- Official Google documentation describes audio-only session limits in minutes, not an 80-second timeout: https://ai.google.dev/gemini-api/docs/live-api/session-management . This app already enables context compression.

## Runtime recovery and limits

During verification, port 8000 was no longer listening. The last available API log entry was a development auto-reload triggered by a test-file edit. Started the API through the existing repository command `scripts/dev_up.ps1 -ApiOnly -ProductionWeb -Wait`, which uses stable mode without file reload. Local health then returned HTTP 200. No existing process was killed and no persisted production setting, schema, pricing, or saved transcription model was changed.

After recovery, both local API health and https://www.dialtact.com/api/health returned HTTP 200 (public response was JSON).

The code is local and uncommitted; the restarted local API loads it. No GitHub push or separate deployment was performed. A fresh real PSTN call through the public carrier connection is still required to verify audio quality and closure end to end. The specific historical whole-process crash cause remains unconfirmed because its traceback is unavailable.
