# Landing refresh verification — 28 October 2026

The active Dialtact Vite landing page now has seven sections below the original hero: voice preview, workspace/product proof, use cases, setup, wallet pricing, FAQ, and closing CTA. The old overlapping feature sections are no longer mounted. Existing routes, authentication, the hero, and voice-tier selections remain intact.

## Design and content decisions

Reviewed the current [Retell](https://www.retellai.com/), [Vapi](https://vapi.ai/), and [Bolna](https://www.bolna.ai/) homepages. Applied their emphasis on an early demonstration, concrete workflows, product explanation, and a clear starting point. The implementation uses Dialtact's existing typography and accent to remain consistent with the preserved hero; the repository's older dark Vāṇi design context was not applied to this active light-themed surface.

The new layout uses a compact audio card, a real console screenshot with fictional data, selectable workflow explanations, an editorial three-step setup section, a single pricing panel, and native FAQ disclosure controls. It avoids invented customer logos, testimonials, conversion figures, certifications, and generic repeated feature-card walls. The console image is labelled as an example.

Removed the old monthly/annual pricing selection, automatic-follow-up promises, unconditional integration claims, and the footer's non-persisting newsletter form. Pricing now leads to the existing billing entry point without changing a workspace's tier. Social links are rendered only when configured.

## Evidence

- **Hero preservation:** byte comparison passed for the hero component; hero content and rendered props also matched their pre-edit baselines. Results are in local `hero-invariant.json`.
- **41 browser tests passed**, including seven new landing tests: navigation/asset loading, selectable workflows, real audio progress, audio failure/recovery, pricing and integration sign-in destinations, mobile layout, keyboard FAQ operation, and the closing CTA. Existing script, CRM, wallet, layout, and session-routing tests also passed.
- **486 changed-file backend tests passed; 3 skipped.** Coverage includes the pending voice, CRM, billing, tax, session, admin, and readiness changes being published with this update. The three skips are reported rather than counted as passes.
- **7 Node tests passed**, covering handling-rule/script round-trip and a regression for the CSS-percentage false positive in the copy guard.
- **8 Reticle verdicts passed**, on desktop 1440×1000 and mobile 390×844: page readiness, workflow selection, FAQ expansion, and the pricing authentication entry point. Network and console observations were captured. Reticle's SDK is 3.7.0 against driver 3.8.2; its pointer driver initially reported an off-viewport result after acting. The final run used real keyboard focus/Enter, with the same consequence assertions. Initial unknown results are not counted as passes. Browser tests separately exercise pointer interactions.
- **Vite build and six-page prerender passed.** The Next.js production build for the pending admin changes also passed in an isolated output directory, and its generated config edits were reverted. The repository's Next build skips lint/type checking; no separate TypeScript-check claim is made.
- **Semgrep SAST passed** with zero findings and zero blocking findings. Source secret-pattern checks found no matches. `git diff --check` passed with existing line-ending warnings. Graft was refreshed.
- Desktop sections and a complete mobile page were inspected visually. Measured horizontal overflow at 390px was zero.

Local evidence files include `browser-tests.log`, `backend-results.xml`, `node-tests.log`, `reticle-verification.json`, `reticle-observations.json`, `vite-build.log`, `next-build.log`, and `security-sast.log`. Raw execution files and browser screenshots remain local. The public workspace image contains fictional data and is included as a product asset.

The first browser run exposed audio-state/test timing issues and a sign-in test that navigated before authentication finished. The audio player now presents loading separately from confirmed playback and has explicit failure recovery. The routing test waits for the console and uses its sidebar control. The final 41-test run passed after those changes.

## Publication scope

Source, regression tests, safe verification notes, and release notes are included. Raw call recordings/logs, customer screenshots, browser episodes, local environment files, generated builds, and Reticle metadata containing phone-number candidates are excluded. No production deployment, merge to `main`, customer agent publication, or external call/payment is part of this push.

The pending conversation work's live-provider checks were performed earlier and are described in its own verification notes. This landing task did not place customer calls or retest every provider/language/integration. Deploy the code through the normal release process; older generated scripts need review and republication to pick up template changes.

VERDICT: PASS
