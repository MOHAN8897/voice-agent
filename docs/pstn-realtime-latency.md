# Realtime PSTN latency

Verified against OpenAI documentation on 2026-09-19.

## Supported audio and transcripts

The Realtime GA `RealtimeAudioFormats` schema accepts PCM at **24 kHz**,
or G.711 PCMU/PCMA. Keep the Telnyx 16 kHz PCM to Realtime 24 kHz resamplers.
The 16 kHz PCM example on the shared voice WebSockets page describes GPT-Live
(`session.start`, `/v1/live/sessions`), not this Realtime integration
(`session.update`, `/v1/realtime`). Do not change models or label 16 kHz bytes as 24 kHz.

Realtime emits the assistant's final speech transcript through
`response.output_audio_transcript.done`; the adapter already consumes it without
another transcription request. It does **not** supply the caller's transcript
through this event, nor a complete two-sided transcript automatically at hangup.
Input transcription is a separate asynchronous service. Keep
`gpt-4o-mini-transcribe` enabled here: caller-detail capture, callback consent,
hangup validation, and the call ledger depend on its completed events. The voice
model consumes audio directly and does not need to wait for that transcript.

Sources:

- [Realtime audio configuration and formats](https://developers.openai.com/api/reference/resources/realtime/subresources/calls/methods/accept)
- [Realtime conversations and transcript events](https://developers.openai.com/api/docs/guides/realtime-conversations)
- [Realtime VAD](https://developers.openai.com/api/docs/guides/realtime-vad)
- [Voice WebSockets (check which API the page describes)](https://developers.openai.com/api/docs/guides/voice-websockets)

## Runtime behavior

- Default semantic VAD eagerness is `high`. Selecting server VAD defaults to
  250 ms silence, with 300 ms prefix padding. Explicit saved settings still win;
  an existing Test Studio configuration saved with `medium` must be changed there.
- Keep `interrupt_response: false`; local echo/barge handling remains in charge.
- Keep far-field noise reduction as the quality default. For an A/B test, select
  `off` in Test Studio; it sends explicit `noise_reduction: null`, including on
  subsequent updates, so an old setting cannot remain enabled accidentally.
- Cancellation only sends the WebSocket command. It does not wait for a server
  acknowledgement in the event consumer. Injected responses send ordered
  disable/cancel/create/restore commands, with metadata to distinguish the
  requested response from an in-flight VAD response. Late cancelled events are
  filtered both during normalization and when consuming queued events.
- A previous response having audio does not invalidate a new answer. Known
  greeting leftovers and stale response IDs remain suppressed.
- First response audio never clears the caller's input buffer.
- Actual queue occupancy and a frame being sent determine whether echo gating
  applies. An outstanding model response alone does not keep the caller muted.
- Ordinary answers start with substantive speech. Closing tools remain enabled;
  a short farewell precedes the closing action in the same turn. Do not claim
  a transfer or confirmed callback before a successful tool result.
- The 20 ms Telnyx pacer remains unchanged. No local backchannel or GPT-Live path
  is added.

## Verification on a call

Compare later turns with the same caller, model, network, and prompt. Check
`vad_stop_to_first_audio_ms` in the media-flow snapshot: it measures arrival of
OpenAI's VAD stop event to the first actual Telnyx outbound frame, not just audio
generation or queue insertion. It excludes the VAD detection wait itself.
Measure caller-silence-to-agent-audio from the call recording for the complete
latency. Do not use delayed STT completion as the start timestamp.

Compare far-field and off for both turn latency and false interruptions. Keep
far-field unless the off trial improves latency without unacceptable noise or
echo. No 400–800 ms claim is established by the automated tests; that requires
a real call. Lower VAD waits can also cut off natural pauses, so listen for that.

Automated regressions in `server/tests/test_realtime_voice_latency_regressions.py`
cover delayed cancellation acknowledgements, pending response races, stale
queued audio, final assistant transcripts, idle-queue unmuting, greeting
leftovers, buffer preservation, and latency measurement boundaries.
