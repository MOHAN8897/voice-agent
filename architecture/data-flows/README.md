# Data Flows

Sequence diagrams and flow descriptions for runtime behavior.

| Flow | File | Phase |
|------|------|-------|
| Live voice turn (hot path) | [live-voice-turn.md](./live-voice-turn.md) | 4 |
| Call start / end | [call-lifecycle.md](./call-lifecycle.md) | 3 |
| Post-call analysis | [post-call-pipeline.md](./post-call-pipeline.md) | 4 |

## Path temperature

| Temperature | Latency | Examples |
|-------------|---------|----------|
| Hot | <100ms blocking | LLM stream to TTS, barge-in abort |
| Warm | Async <500ms | Ledger append, memory merge, PCM buffer |
| Cold | Seconds+ | Post-call outcome, mix.wav, campaign stats |

**Invariant:** Hot path never awaits warm or cold work.
