# Telecaller audit implementation (28 Sep 2026)

## Done

- Brain/language: B1–B8, rendered prompt validation, cache-floor pad, closing policy alignment.
- Dial: C1 bounded prewarm adopt (1.5s), C2 brain checksum parity, C3 durable dial attempts (dev + SaaS), C4 E.164 guard, C5 leg/media split in Telnyx webhooks.
- Audio/runtime: A1 Gemini effective VAD logging, A2 echo-tail barge tightening, A3/A4 playout pacing/underruns, A5 pickup hangup, A6 TTS partial timeout.
- Tests: 177 pytest cases in the audit module set; new coverage for dial attempts, event state, B1 realign, 11-locale packs.

## PSTN forensics (manual test support)

- `server/services/pstn_forensics.py` + `GET /api/dev/telephony/forensics`
- Milestones: `answered`, `voice_loop_started`, `first_outbound_sent` (ms from dial)
- Test Studio **PSTN forensics** panel above live media flow; snapshot saved on call cleanup in `meta.pstn_forensics`
- `AUDIOOP_MIGRATION.md` for Phase 4 deprecation plan

## Section 5 (partial, 28 Sep 2026 evening)

- `server/brain/compiled_brain_artifact.py`: `assemble_unified_brain`, `CompiledBrainArtifact`, `is_unified_compiled_brain`.
- All compile paths use one assembler: brief (`_assemble_brain`), session brain, factory `compose_brain_prompt`, SaaS `compiled_brain_service`.
- Live voice: unified brains skip duplicate `live_realtime_*` language locks and `FINAL LANGUAGE CONSTRAINT`; Gemini keeps spoken pack in prompt via `_extract_spoken_language_section`.
- `call_end_policy` uses `pack_get` for indic locales missing explicit call-end copy.

## Still not in scope

- Persisting structured artifact JSON on every save/publish (only `final_instructions` string today).
- Full migration republish of historical brains.
- Section 7 live-call verification and prompt snapshot archive on disk.
- Automated republish of every saved agent brain from brief.
