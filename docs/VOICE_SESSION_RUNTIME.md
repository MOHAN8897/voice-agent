# Voice session runtime

The selected agent language, tier, model and voice are admitted together before
opening a provider. Browser practice and PSTN use the same locked stack and
voice-loop factory. A browser practice call can supply a test language; the UI
loads the saved agent language before older script-editor voice metadata.

## Economical and Standard

Both tiers use the admitted Sarvam recognizer and conversational text model.
Economical uses the saved Gemini speech model; Standard uses the saved Sarvam
speech model. Provider/model choices come from versioned profiles. An unavailable
stage fails explicitly; the runtime does not substitute Premium or another model.

`ComposedPromptSnapshot` belongs to the active call. Admission prepares its
system text once, preserving business content and refreshing platform language
rules. The key includes compiled script/version, language, provider, model and
API mode. A changed key invalidates the snapshot. Transcript, history, memory
projection and turn hints remain outside the stable prefix. No shared prompt
cache stores customer text across calls.

Sarvam V1 rejects the `developer` role: the adapter maps it to `system` while
preserving assistant and tool history. V1 requests resend the stable prefix;
local snapshot reuse does not remove input tokens. Provider caching is measured
only from returned `cached_tokens`. V2 documents session affinity, but that is
not claimed or silently enabled for the V1 conversational model.

A mismatched opening is translated once with the admitted text model and an
explicit named-language rule before TTS. Native-script validation rejects a
wrong-language result. PSTN performs this during preparation before dialing;
the answered call consumes the prepared audio and translated text. Browser
startup opens STT and TTS while it prepares the opening. Greeting delivery is
remembered so subsequent turns continue the conversation. Localization usage is
included in internal LLM costing.

## Turn taking and media

Composed recognition uses VAD endpointing, 300 ms of onset padding and 250 ms
minimum speech. Saved session silence/threshold settings apply; absent values
use 500 ms and 0.3. The shared voice runtime normally supplies its 400 ms silence
setting. Final transcripts coalesce for 150 ms to preserve natural pauses.

Barge-in confirms substantive or explicit short interruptions for 120 ms,
checks overlap with audio actually heard, applies a 450 ms debounce and rejects
stale generation output. Optional VAD confirmation accepts provider speech-start
events as well as local energy evidence. Quiet microphone frames still reach
recognition. On interruption the generation is invalidated, local/remote audio
is cleared, TTS is stopped and LLM generation is cancelled; the final transcript
or bounded partial fallback starts the next turn.

Browser media is mono PCM16 at 16 kHz, 640 bytes per 20 ms frame. PSTN uses the
carrier's admitted format: 16 kHz PCM16 or 8 kHz mu-law (160 bytes per 20 ms).
Resampling and encoding occur at the transport boundary.

Optional Redis/disk hydration runs off the event loop with a 75 ms live-turn
budget. Callback/hangup hints read already hydrated call memory without network
I/O. Provider failures produce a service error and end the failed session;
they are not reported as a failure to hear the caller.

## Premium

Premium uses the existing hot Gemini Live session. Voice selection saves
`realtimeVoice` with the tier, language and expected revision. The server removes
old composed aliases when entering Premium; the client confirms the returned
voice and blocks tests while a save is pending, conflicted or unconfirmed.
The existing prepared-opening, owner routing and single-consumption rules stay
in the realtime voice path.

## Verification

Regression coverage: `test_composed_session_repair.py`, voice revision,
browser admission, PSTN preparation/framing, interruption, callback and hangup
tests; `voice-language-studio.spec.js` covers saved language, atomic Premium
selection, reload and save failures.

Synthetic live-provider evidence from 22 October 2026 is under
`.gravitas/sessions/voice-session-repair-20261022/`. All three providers produced
Telugu audio. Economical and Standard produced valid browser/PSTN frame formats;
Premium reused one Live connection through its opening and two replies. No real
PSTN call was placed. Provider probes do not prove an acoustic microphone or
carrier round trip.

Protocol references: [Sarvam V1 chat](https://docs.sarvam.ai/api-reference/chat/chat-completions-v1),
[Sarvam V2 caching](https://docs.sarvam.ai/api-reference/chat/chat-completions-v2),
[Sarvam realtime VAD](https://docs.sarvam.ai/api-reference/speech-to-text/transcribe/realtime/ws),
[Gemini Live](https://ai.google.dev/api/live).
