# Voice setup and tenant console repair

The voice workspace now has one header Test call action and one primary Save changes action. Selecting a tier saves its catalog voice through the same revision-checked path as selecting a voice card. A successful voice save does not create an unpublished script change. Stale selections and failed saves block tests and show the next action.

Flagship profiles use their persisted engine, model, voice aliases and profile revision. They no longer substitute the separate universal voice catalog merely because the tier is named `premium`. The older universal configuration path remains available only when no Flagship profile exists.

OAuth callbacks remove the one-time handoff from the address bar, finish authentication, then navigate to the requested tenant console. Receiving a session policy no longer starts another restore during login. Email login and signup retain onboarding metadata and cache the normalized user.

Persisted profile readiness now validates speech model, voice and language compatibility. Browser startup and phone preparation return fixed tenant-safe configuration errors; stale choices direct the tenant back to Voice. These known pre-dial failures release admission capacity and never trigger a replacement stack.

## Saved development configuration

The user selected these repairs explicitly:

- Economical profile: replace unsupported `sarvam-2b` with `sarvam-105b-conversations` on chat V1; revision 14 to 15.
- Standard profile: keep `bulbul:v4-flash` and replace the six obsolete short speaker IDs with their corresponding v4 personas; revision 23 to 24. Shubh uses `shubh_enhi_ads`. Malayalam and Odia are removed from this v4 profile's offered languages because its catalog has no corresponding voices.
- Advance the one agent selection using the prior current Standard revision while preserving its voice alias. Older incomplete or already stale selections require an explicit current voice selection.

The active retail rates were not modified. The disabled Flagship profile was not activated. A local configuration backup was saved before the repair. Runtime resolution of the current Standard agent confirms the exact recognition, conversation and v4 speech stages with the corrected persona.

Provider references: [Bulbul voice compatibility](https://docs.sarvam.ai/api-reference/text-to-speech/convert), [v4 migration guidance](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/best-practices), [current chat API models](https://docs.sarvam.ai/api/api-guides-tutorials/chat-completion/overview).

## Verification

- 135 targeted Python tests passed; one isolated PostgreSQL migration test skipped.
- 17 Playwright tests passed with one worker. They cover email/OAuth routing, exact tier-save payloads, Flagship aliases, stale selections, failed saves, script publication and browser audio startup/cancellation. A parallel run had a fake-microphone timing failure; the complete serial run passed without weakening its assertions.
- Vite production build and public-page prerender passed.
- Semgrep scanned 1,361 targets with zero findings or blocking results.
- Reticle produced passing local UI verdicts for tier-save feedback, selection state and opening the test dialog using synthetic account/API fixtures. Coverage is partial: request-body capture was disabled and no application store was registered. Exact request payloads were checked by Playwright. No live provider or carrier call was made.
- Reticle's gated local connector now receives the Vite plugin's pairing token. Its localhost/authenticated-user test passes, and the production bundle check confirms that the development runtime is absent.
