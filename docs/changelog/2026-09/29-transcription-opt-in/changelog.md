# Opt-in PSTN transcription (SaaS phone stack)

## Goal

Admin toggles for live (`gpt-4o-mini-transcribe`) and post-call (`gemini-3.5-transcribe`) on the universal SaaS phone stack; usage panel and ledger totals include add-on lines only when enabled.

## Stack shape

`stack_override.transcription` on call meta (snapshotted at `call/start`): `live_enabled`, `post_call_enabled` — **mutually exclusive** (live wins if both set). SaaS UI uses radio: Off | Live | Post-call.

Env `POST_CALL_TRANSCRIPT_ENABLED` is the default when `post_call_enabled` is omitted and mode not set.

## Server

- `server/services/transcription_policy.py` — policy from stack/meta
- Gemini PSTN + live: `OpenaiCallerTranscribeSidecar` writes ledger only; Gemini native `input_transcription` still drives hangup/turns
- OpenAI Realtime: `input_transcription_enabled` on session when live off
- `call_ledger` — `live_transcript_usd` + post-call gated by policy

## UI

- `/dev/saas-phone-stack` — two checkboxes
- `TestStudioTurnMetrics` — separate live vs post-call cost rows and badges via `transcript-source.ts`
