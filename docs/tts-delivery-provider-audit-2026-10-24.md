# TTS delivery API audit — 24 October 2026

The admin control schema, profile validator and outbound synthesis payload must
agree on provider-supported controls. Transport settings such as PCM sample rate,
channel count, encoding and container are handled separately by the call adapter.
These findings cover the currently integrated models; they do not add providers.

## Cartesia Sonic 3 / 3.5

- Official delivery controls are `generation_config.speed` (0.6–1.5),
  `volume` (0.5–2.0) and `emotion` (58 documented values).
- Emotion guidance is documented for English only. The model treats these values
  as guidance rather than exact acoustic multipliers, and the transcript needs to
  support the requested emotion.
- The previous 12-value admin/profile allowlists omitted accepted values such as
  `excited`, `sarcastic` and `determined`; saving a selection could drop it or
  replace it with `calm`. Both validators now share the complete vocabulary.
- The platform's default remains `calm`, matching its existing environment
  default. Explicitly saved values such as `neutral` remain unchanged.
- `generation_config` is scoped to one request. REST synthesis and every
  WebSocket generation include the resolved settings.

Sources: [Delivery controls](https://docs.cartesia.ai/build-with-cartesia/capability-guides/volume-speed-emotion),
[REST request schema](https://docs.cartesia.ai/api-reference/tts/bytes),
[supported Sonic models](https://docs.cartesia.ai/build-with-cartesia/tts-models/older-models).

## Gnani Timbre 2.5 / 3.0

- Both current model request schemas document speaking speed (0.85–1.15).
- Timbre 3.0 additionally supports expressive inline audio tags. Timbre 2.5
  does not have that documented audio-tag capability.
- Neither current REST nor WebSocket documentation lists numeric pitch, volume
  or temperature controls. The former admin controls and payload fields had no
  supporting provider schema. They must not be described as verified native
  controls without evidence that the provider applies them.
- The admin now advertises speaking speed only. Audio format controls remain
  fixed by the transport requirements of the call.

Sources: [REST parameters](https://docs.gnani.ai/api/TTS/tts-inference),
[WebSocket parameters](https://docs.gnani.ai/api/TTS/tts-websocket),
[model-specific voices](https://docs.gnani.ai/api/TTS/available-voices).

## Gemini TTS

- Gemini 3.8 uses a verbatim transcript and `speech_metadata.style` for sustained
  directions such as pace, pitch, prosody and inflection.
- The existing speed and pitch controls are translated into style directions;
  they are not documented native numeric pitch or rate parameters. No numeric
  temperature or volume parameter is advertised by the app's TTS control schema.
- Earlier integrated TTS models use natural language delivery prompting. Gemini
  Live is a separate audio path and should not inherit composed TTS controls.

Source: [Gemini TTS prompting, pacing and prosody](https://ai.google.dev/gemini-api/docs/speech-generation).

## Evidence limits

The API documentation establishes documented control shapes. Mocked regression
tests prove profile validation and call configuration preserve accepted values;
they do not measure the acoustic effect of live provider synthesis. Those effects
need representative provider audio and listening or measurement evidence.
