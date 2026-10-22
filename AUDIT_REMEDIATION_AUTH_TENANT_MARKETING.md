# Audit remediation — what changed, what is proved, what is left

Companion to `AUDIT_REPORT_AUTH_TENANT_MARKETING.md`. Every line below was either
verified by a test or is called out as not done.

Verification used:
- `server/tests/test_session_policy_and_password_reset.py` (13 new tests, pass)
- `voxly-ai/e2e/auth-session-voice.spec.js` (11 tests, all pass, real account)
- Reticle verdicts against the running app on `http://127.0.0.1:5173`

---

## 1. Forgot-password emails fail silently — **partly fixed, blocked on DNS**

**Was:** `send_email()` returned a bare `bool` nobody checked. Resend rejects
`support@hustlelabs.in` with `403 ... domain is not verified`, so the link was never
delivered and `POST /api/auth/forgot-password` still answered `200 OK`.

**Now:**
- `server/services/saas/email_service.py` returns a structured `EmailResult`
  (`ok`, `code`, `provider_status`, `provider_message`) and never raises.
  `send_email` returns `False` on the domain rejection instead of pretending.
- `email_provider_status()` probes `GET /domains` and only counts a domain as
  deliverable when Resend reports `verified`/`pending`. A domain that was merely
  *added* stays `not_started`, and counting that as usable is exactly the silent
  failure this removes. Result is cached for 5 minutes.
- `auth_forgot_password` refuses with **HTTP 503 `email_delivery_unavailable` when the
  platform cannot deliver at all**. It returns the same answer for every address, so it
  cannot be used to probe whether an account exists.
- When the provider is healthy but one send fails (bad mailbox, throttling), the caller
  still gets the same generic `200` and the real reason goes to the log with a masked
  address (`m***@hustlelabs.in`).
- `GET /api/health` now reports `email: { deliverable, domainVerified, reason }` so a
  broken sender shows up on a monitor instead of a support ticket. Current value:
  `deliverable: false, reason: "domain_not_verified"`.

**Still required — one manual step.** `hustlelabs.in` has been **added to Resend**
(region `ap-northeast-1`). It is `not_started` until these records are published in
Cloudflare (the zone's NS are `kanye`/`elma.ns.cloudflare.net`):

| Type | Name | Value | TTL |
|---|---|---|---|
| TXT | `resend._domainkey` | `p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDKIywEG+Mg9K+JKu8nR8+iiQmQkHQr1Vop2npRaGgswG3LR+7cLkX0jS4NGoJo59CjL29dpU/PbjpNFGfa3z4Z8U2jU2ce6rGA1Kd8IPYyjDIBKGmn69efhMfXIc5ahm1SmzIxZA8GIXroApB3j9pnwlUCGLvbCGwow1q9C4rmhwIDAQAB` | Auto |
| MX | `send` | `feedback-smtp.ap-northeast-1.amazonses.com` (priority 10) | Auto |
| TXT | `send` | `v=spf1 include:amazonses.com ~all` | Auto |
| CNAME | `rsend` | `send.forge.rmta.net` | Auto |

I do not have Cloudflare credentials, so these cannot be published from here. Once they
are, `GET /api/health` flips `email.deliverable` to `true` within 5 minutes and no code
change is needed.

**Until then, so local/E2E flows are finishable:** `AUTH_DEBUG_EXPOSE_RESET_TOKEN=true`
(default `false`, never set in production) makes `/api/auth/forgot-password` return
`debugResetUrl` so the rest of the flow can be driven. The UI shows the link with a
"Development mode: email delivery is not configured" label so it cannot be mistaken for
a working mailer.

---

## 2. Password reset did not sign the user in — **fixed**

`reset-password` now returns a session (`accessToken` + refresh cookie) instead of
`{"ok": true}`. A valid single-use reset token *is* proof of mailbox ownership, so the
person is dropped straight into their console.

Frontend (`voxly-ai/src/components/AuthModal.jsx`):
- No redundant "Work Email" field on the reset form — the API never accepted one.
- "Confirm new password" added; mismatch is caught before the request.
- **Bug found while testing:** the token was read from `window.location.hash` once, in a
  `useMemo(..., [])`, on mount. The modal is mounted for the life of the app, so opening
  a reset link in an already-open tab produced "Reset link is invalid or expired" for a
  perfectly good link. It is now read at submit time.

Verified by Reticle: redeeming the link leaves the signed-in console shell present.

---

## 3. No change-password UI — **fixed**

Backend: `POST /api/auth/change-password` now returns a session. Every *other* session
for the account is revoked (a password change must lock out a stolen cookie) and the
browser that made the change stays signed in.

Frontend:
- `voxly-ai/src/console/modules/SettingsModule.jsx` — "Password" card with current /
  new / confirm, plus a "Session security" card showing the idle and absolute bounds.
- `voxly-ai/src/services/api.js` — `auth.changePassword()`, which adopts the new token.
- `web/components/auth/ChangePasswordCard.tsx` + wired into
  `web/app/app/(console)/settings/page.tsx`.

**Bug found while testing:** `SettingsModule.jsx` imported
`../../context/WorkspaceContext`, which does not exist (it is
`../context/WorkspaceContext`). The module failed to resolve, so the Settings tab could
never load. Present before this work.

---

## 4. Sessions never timed out — **fixed, server and client**

Server:
- Migration `027_session_sliding_window` adds `refresh_tokens.last_active_at` and
  `refresh_tokens.absolute_expires_at` (backfilled from `created_at` / `expires_at`, so
  re-running is safe).
- `auth_service.refresh()` refuses a token older than `SESSION_IDLE_TIMEOUT_MINUTES`
  (default 30) with `session_idle`, and a sign-in older than
  `SESSION_ABSOLUTE_MAX_HOURS` (default 24) with `session_absolute_max`. Both revoke the
  whole family and write an `AuthEvent`.
- The absolute deadline belongs to the sign-in, so a rotation carries the family's
  original deadline forward — otherwise every refresh would restart the clock.
- `GET /api/auth/session-policy` publishes the bounds; every auth response carries them
  in `sessionPolicy`, so the client never holds a copy that can drift.
- `refresh` distinguishes those two states from an invalid token, so the sign-in screen
  can say *why* rather than "invalid refresh token".

Client (`voxly-ai/src/services/sessionIdle.js`, `IdleWarningModal.jsx`, `AuthContext`):
- Activity on pointerdown / keydown / wheel / touchstart / focus / visibility.
- Countdown modal with a focus trap, "Stay signed in", and "Sign out now".
- Signed-out reason is shown on the sign-in form instead of silently emptying.
- Cross-tab: activity and the warning are broadcast so a background tab cannot sign the
  person out of the tab they are using.
- `voxly_idle_timeout_ms` in `localStorage` can only *lower* the bound (E2E + support).

---

## 5. Tenant information leakage — **fixed at the API, not just the UI**

`server/services/saas/call_redaction.py` projects a call record into the customer view.
`GET /api/call/{id}` applies it unless the caller's role is `platform_admin`,
`administrator` or `developer`. Verified live as `customer_admin`:

```
returned: call_id, agent_id, channel, pipeline, direction, tier, environment,
          started_at, ended_at, duration_sec, end_reason, cost_usd, status,
          finalization_status, usage{turns,duration_sec,...}, finalization{status},
          internal_fields_hidden
absent:   telnyx*, gemini_list_audio*, fx_rate, resolved_stack, pstn_forensics,
          combination_id, dial_request_id, ledger, audio archive, outcome job
```

Hiding a field in React still ships it to the browser; this does not.

UI: `CallMetadataPanel.tsx` and `lib/transcript-source.ts` render the customer view when
`internal_fields_hidden` is set — including "Transcript: recorded and transcribed"
instead of "Telnyx + Gemini 3.5".

Voice picker: `AgentStudioModule.jsx` groups voices by **character tier** ("Ultra-Realistic
Conversational (Tier 1)", "Expressive Customer Care", "Professional & Formal", "Bright &
Energetic") instead of by supplier. `IntegrationsModule` says "Voxly platform API";
`AgentDialBulkPanel`'s ceiling comment no longer names the carrier.

---

## 6. Marketing voice was the browser's — **fixed**

`window.speechSynthesis` is gone from the marketing flows. Every clip is rendered by
`gemini-3.8-live`, the same live speech model that answers a real call.

`scripts/record_marketing_voice_samples.py` renders ten lines, one per vertical, through
`GeminiLiveVoiceAdapter`:

| Industry | Scene |
|---|---|
| Healthcare & Clinics | Clinic receptionist |
| Real Estate | Property enquiry |
| Car Dealership | Test drive booking |
| Restaurants & QSR | Table reservation |
| IT & Software | Tier-one support |
| Education & Institutes | Admissions enquiry |
| Logistics & Courier | Shipment tracking |
| Home Services | Service booking |
| Banking & Fintech | Card and account help |
| Travel & Hospitality | Itinerary change |

24 kHz mono 16-bit WAV (~8.7–10.5 s each), written to
`voxly-ai/public/audio/voxly/samples/`, with a generated manifest
(`voxly-ai/src/data/voiceSamples.js`) that the UI imports. Re-record with
`.venv\Scripts\python.exe scripts\record_marketing_voice_samples.py [--force] [--only <id>]`.

Where they are wired in:
- `TalkToAiSection` — industry picker, waveform driven by the Web Audio analyser of the
  real clip, the transcript that was spoken, and an A/B against "your browser's voice"
  for the same sentence (the honest "before").
- `TalkToMeModal` — real samples instead of a hard-coded reply array. The microphone is
  no longer requested on the marketing page to fake a conversation; the real live path
  (which needs an agent) is one button away and requests the mic once, inside the real
  session.
- `WatchDemoModal` — **bug fixed:** it called `playTTS(text, { onEnd })` when the
  signature is `playTTS(text, onEnd, onStart, options)`, so it threw on `onEnd()` and the
  walkthrough never advanced past line one. It also played a fictional discovery call
  with invented numbers (a "4.2x speedup", "30% savings"); it now plays real samples and
  makes no claims it cannot show.

---

## 7. 3D scene on the critical path — **fixed**

`three` + `three/fiber` were ~1 MB uncompressed in the entry graph. `Hero` now renders
`LazyVoxlyScene`, a `React.lazy` boundary that falls back to the real preview image
(container keeps its height, so no layout shift).

Getting three.js actually *out* of the initial graph needed three fixes in
`voxly-ai/vite.config.js`:
- `manualChunks` object form put `react-dom` (pulled in by `@react-three/*` via
  `its-fine`) inside the 3D chunk, so the entry statically imported it. Now a function
  that sends `react`/`react-dom`/`scheduler`/`react-reconciler` to their own chunk.
- Vite's dynamic-import preload helper was emitted into the 3D chunk, so the entry
  imported *that* chunk for the helper. It now has its own `vite-helpers` chunk.
- `modulePreload.polyfill: false` (target is `esnext`, so browsers have it natively).

Result — `dist/index.html` preloads only `react-vendor`, `ui-vendor`, `vite-helpers`:

```
react-vendor   239 kB │ gzip  75 kB
ui-vendor       38 kB │ gzip   8 kB
index          497 kB │ gzip 130 kB
three          785 kB │ gzip 208 kB   <- lazy, fetched when the mascot mounts
VoxlyScene      16 kB │ gzip   6 kB   <- lazy
```

The mascot itself is untouched: same scene, same gestures, same lip-sync.

---

## 7b. The landing page said the same thing 15 times — **fixed**

Follow-up pass on repetition and unsourced claims. `voxly-ai/scripts/check-landing-copy.mjs`
(`npm run check:copy`) now fails the build on any of these regressions, because every one
of them was invisible: the build passed, the page looked fine, and the copy still
contradicted itself.

**Deleted outright**
| Removed | Why |
|---|---|
| `TALK_TO_AI_CONTENT` | Dead — 0 references, still holding the old latency and mock prompts. |
| `AiTeamSection` | Four invented employees (91%, 340/mo, 4.9/5, $140k recovered) saying the same "who it's for" as the Industries grid. |
| `LeadEngineSection` | A fake lead card for a qualification story the Capabilities grid already covers. |
| `ConversationHistorySection` | A fabricated transcript, now redundant with the real recorded calls. |
| `BUILD_AI_EMPLOYEE_STEPS` + `AiEmployeeSection` part 2 | A second onboarding stepper six sections after the canonical one, plus a fake studio console ("Sub-350ms", "148 wpm", "3,420 pages ingested", "100,000 parallel calls"). |
| `CampaignScaleSection` dashboard | 2,450 contacts / 486 qualified / 26.4% / a progress bar frozen at 88%, pointing at an employee who no longer exists on the page. |
| "Campaigns" third tab in `PHONE_CHANNELS` | Duplicated the campaigns section. |

**One number, said once**
- Latency appeared **seven times in five versions** (sub-500 / sub-400 / sub-350 / 320 / 300 ms) — including the AI *saying* 320ms while pricing promised 300ms. All removed; the page no longer quotes a latency figure at all.
- "40+ voices" appeared twice. **The platform actually serves 10** (`/api/telephony/voice-options`), so the claim was both repeated and wrong.
- "4.2x faster" appeared twice; "24/7" seven times; "82%"/"84%"/"100%" each two to five times with no source.

**Guarantees and unsourced figures removed** — "+34% pipeline uplift", "100,000 concurrent
lines", "-42% no-shows", "+28% cart recovery", "94% inquiry capture", "$140k recovered",
"140 curated Q&As", "zero hallucinations", "100% grounded", "Zero hold times guaranteed",
and the "No telephony markup" claim (the rate does contain a telephony component).

Also removed from `LegalModals.jsx`: a **"99.95% telephony uptime guarantee … sub-500
millisecond neural acoustic processing"** SLA. That was invented, and an SLA is a
contractual promise rather than marketing copy — it now points to the signed order form.
**Worth a look:** if a real SLA exists, put the actual numbers back there.

**Numbers that contradicted each other, reconciled** — the billing widget implied
$0.10/min (20,500 credits / 1,284 min / $128.40) while pricing said $0.11–$0.14. It now
shows the plan's own terms, so it cannot drift from pricing.

**Kept, labelled** — one sample dashboard in Analytics, now explicitly marked "Example
workspace — sample data". A page that describes reporting with no picture of it is harder
to evaluate; five mock dashboards, each a different invented business, was worse.

**Result:** 15 sections → 12, ~3,290 → 2,137 lines of landing JSX, 16 content exports → 11
(all used), entry chunk 490 kB → 450 kB. Nav now links the five sections that survive.



| Where | What |
|---|---|
| `OverviewModule.jsx` | `useMemo` calls sat **after** an early `return`, so the console's default tab crashed with "Rendered more hooks than during the previous render" whenever the workspace was still loading on first render. |
| `SettingsModule.jsx` | Import path to `WorkspaceContext` did not resolve; the Settings tab could not load. |
| `AuthModal.jsx` | Reset token captured once at mount; a reset link opened in an already-open tab was rejected as expired. |
| `WatchDemoModal.jsx` | Wrong `playTTS` argument order threw on `onEnd()`; the walkthrough stalled on step one. |

Later, on the landing-copy pass:
| Where | What |
|---|---|
| `SettingsModule.jsx` | Already listed above. |
| — | The voice samples shipped as 24 kHz mono **WAV** (no encoder is available in this environment: no ffmpeg, no lameenc). ~4.4 MB for 10 clips, fetched only when a visitor presses play. An MP3/AAC encode would cut that by ~10× if a codec is added to the build. |

---

## 9. Deliberately not done

- **DNS for the Resend domain** — needs Cloudflare access this session does not have.
  Records are listed above; nothing else is blocked.
- **Replacing the marketing demo with an unauthenticated live voice stream.** A public
  endpoint that opens a paid `gemini-3.8-live` session for anonymous visitors is a cost
  and abuse surface. The live path is real, but it is behind an agent + workspace, which
  is what it needs.
- **`web` production build.** `npx tsc --noEmit` passes over the whole app including the
  new `ChangePasswordCard`, but `next build` did not finish in ~13 minutes here: it
  writes into the same `.next` directory as the running `next dev` on port 3000 and the
  two contend. I stopped it rather than report a green build I had not seen. Run it with
  the dev server stopped.
- **Rebranding Voxly / Vāṇi.** The report offers three options and a decision; that is a
  product call, not a bug.
- **`web/app/app/*` still redirects to the Voxly app** (`web/middleware.ts`), so
  `/app/calls/[id]` is dev-only. The redaction is in the API, so it holds on both
  surfaces.

## 10. Pre-existing failures, unchanged by this work

Verified identical on a clean `HEAD` worktree, so nothing here was introduced by this work:

- 19 `pytest server/tests` failures (brief compilation, LLM catalogue, stack resolver,
  trace API, dev environment, TTS guardrails).
- `voxly-ai` Playwright: `console-billing` and `smoke` expect Razorpay `currency: INR`
  and get `USD` (drifted with the international-Razorpay commit);
  `injected-session-create` needs a dev-tester injected session.
- `npx playwright test` with no file list aborts: `e2e/backend-contract.spec.js` is a
  plain node script that calls `process.exit(0)` on a `/health` probe (the API serves
  `/api/health`), which kills the Playwright worker.