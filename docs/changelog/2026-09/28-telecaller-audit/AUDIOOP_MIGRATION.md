# Python `audioop` deprecation plan (Phase 4)

## Situation

Python 3.12+ warns that `audioop` will be removed (3.13+). This repo still imports it in `server/services/audio_transcode.py` for PCM level/RMS and some resample helpers used on the PSTN path.

This is **not** the root cause of telecaller language or hangup bugs; it is a **future portability** item.

## Recommended path

1. **Short term (current release):** Stay on Python 3.12 for production; treat the warning as tracked debt. Use PSTN forensics (underruns, timelines) to debug audio issues separately from the deprecation.
2. **Replace usage:** Audit `audio_transcode.py` call sites (`pcm16_rms`, mulaw/linear16 helpers). Prefer:
   - `numpy` / `audioop-lts` only if already justified by deps, or
   - Small pure-Python RMS for 16-bit PCM (already trivial), and existing `StreamingPcmResampler` for rate conversion.
3. **Verification:** Re-run `server/tests/test_pstn_tts_resample.py`, `test_pstn_l16_frames.py`, and one manual PSTN call with forensics panel comparing underruns before/after.
4. **Cutover:** Remove `import audioop` only when all tests pass on target Python version without the module.

## Owner checklist

- [ ] Inventory `grep audioop` under `server/`
- [ ] Implement RMS without `audioop`
- [ ] Confirm Telnyx L16 20 ms framing unchanged
- [ ] CI matrix includes chosen Python version
