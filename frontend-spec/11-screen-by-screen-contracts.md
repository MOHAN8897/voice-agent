# 11 — Screen-by-screen contracts

Each screen: purpose, primary action, regions, states. Bind to routes in [12](./12-codebase-route-map.md).

Legend: **Exists** · **Extend** · **Gap**

---

## M1 Home `/` — Exists

- **Purpose:** Sell memory + live voice control plane.  
- **Primary:** Sign in / start test (extend CTA).  
- **Regions:** nav, hero+preview, how-it-works, features, FAQ, footer.  
- **Empty/error:** n/a (static). Preview is simulated.  
- **A11y:** one `h1`, FAQ buttons `aria-expanded`.

## M2 Pricing `/pricing` — Exists

- **Primary:** Get started (Starter/Business), Contact sales (Enterprise).  
- **States:** none. Later: logged-in “Current plan” badge.

## M3 Docs `/docs` — Exists / thin

- **Primary:** Open console.  
- Don’t look like Dev Portal.

## M4 Legal — Gap

Privacy, Terms, DNC. Static; SEO.

---

## A1 Business login `/app/login` — Exists

- **Primary:** Sign in.  
- **States:** checking session, loading submit, invalid creds, API down.  
- **Redirect:** `next` or `/app`.

## A2 Dev login `/dev/login` — Exists

Same contract, different copy/endpoint.

## A3 Tenant `/app/select-tenant` — Exists (mock data)

- **Primary:** Choose workspace.  
- **States:** loading, empty, error.

## A4 Access denied — Exists

- **Primary:** Go back / sign out.

## A5 Onboarding wizard — Gap

- **Primary:** Create agent.  
- **States:** compiling brain, compile error, skip.

---

## B1 Overview `/app` — Exists / extend

- **Primary:** Create agent or Resume setup.  
- **Regions:** stats, checklist, recent calls.  
- **States:** API fail (`health.ok === false`), empty fleet.

## B2 Agents list — Exists

- **Primary:** Create.  
- **Empty:** “Create your first agent”.  
- **Error:** retry list.

## B3 Agent summary — Exists

- **Primary:** Test agent / Edit brain.  
- Show draft vs active.

## B4 Business Brain — Exists

- **Primary:** Save draft.  
- **States:** unsaved, validating, conflict warning, token over budget, permission denied.  
- **Forbidden:** platform prompt text.

## B5 Voice & Models — Exists

- **Primary:** Save tier / stack (if FRONTEND).  
- Invalid combo disabled with reason.

## B6 Memory schema — Exists

Read-only explanation + link to a call.

## B7 Tools — Exists / honest empty

## B8 Channels — Exists / extend PSTN

- **Primary:** Assign number.  
- States: not configured, pending Telnyx, live.

## B9 Versions — Exists

- **Primary:** Promote (admin). Confirm dialog with env impact.

## B10 Test Studio — Exists

- **Primary:** Start / Stop.  
- **States:** idle, connecting, live, mic denied, PSTN not ready, provider fail mid-call, barge.  
- `aria-live="polite"` on transcript; don’t announce every token.

## B11 Calls list — Exists

- **Primary:** Open call.  
- Empty: copy from PRD 05.  
- Filters persist in query string (recommended).

## B12 Call detail — Exists

- **Primary:** Play audio.  
- States: audio missing, still processing post-call, failed archive.

## B13 Analytics — Exists

- Empty: not enough calls.  
- Don’t show traces.

## B14 Benchmarks — Exists / gated

Empty: scenarios not enabled.

## B15 Providers — Exists

Read-only catalog.

## B16 Integrations — Exists / placeholder

## B17 Settings — Exists / thin

Extend: members, audit, billing link.

## B18 Profile — Exists

## B19 Campaigns — Gap (PRD 18)

List / create / run / contacts. States: draft, running, paused, DNC blocked.

## B20 Billing — Gap

See [07](./07-billing-and-payments.md).

---

## D1–D12 Dev portal — Exists

Contracts follow [09](./09-dev-portal.md). Extra states:

- Missing keys (Environment)  
- Promotion rejected  
- Benchmark cancelled / partial  
- Compiled conflict blocking  

**Primary actions:** Save stack, Save platform brain, Start test, Promote.

---

## Shared chrome contracts

| State | UI |
|-------|-----|
| Unsaved | Sticky bar Save / Discard |
| Stale version | Reload |
| 403 | Access denied page, not a blank main |
| 401 | Login with `next` |
| Provider down | Banner, Test Studio Start disabled |

Confirm destructive actions with `ConfirmDialog` (promote, hang up remote, delete draft, cancel campaign).
