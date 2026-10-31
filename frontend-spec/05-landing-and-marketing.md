# 05 — Landing and marketing pages

**Code today**

| Route | File |
|-------|------|
| `/` | `web/app/(marketing)/page.tsx` → `HomeExperience` |
| `/pricing` | `web/app/(marketing)/pricing/page.tsx` |
| `/docs` | `web/app/(marketing)/docs/page.tsx` |
| Layout | `web/app/(marketing)/layout.tsx` + `MarketingNav` + `MarketingFooter` |

**PRD:** `prd/19` §3.1 (SEO), `prd/11` §1, `DESIGN.md`.

Stitch landing frames should **replace composition**, not invent new product claims. Keep the three-step story already in `HomeExperience`.

## Home (`/`) — required blocks

Implement as scroll chapters (cinematic-scroll). Existing order is correct; flesh out, don’t reshuffle without a Stitch export.

### 1. Nav (`MarketingNav`)

- BrandMark
- Links: How it works · Product · Pricing · Docs
- Primary: **Sign in** → `/app/login` (today the CTA is “Learn more” — selling site should add Sign in)
- Optional secondary: **See pricing**

### 2. Hero

**Current H1:** “Voice agents that remember every caller.”  
Keep this; it is the product differentiator (server-owned memory).

Supporting line: configure speech, test in browser, review calls with memory and disposition.

**UI elements**

- Status pill: live dot + “Built for Telugu-speaking markets”
- Primary CTA: **Start in Test Studio** → `/app/login?next=/app/test-studio`
- Secondary CTA: **See how it works** → `#how-it-works`
- Mono caption: Browser test · PSTN ready · Memory on every call
- Right column: `AgentPreview` inside `TiltCard` (window chrome, Telugu transcript, waveform, latency grid)

Stitch hero: if it shows a phone mock, keep it as **preview only** — do not start a real mic from the public page.

### 3. How it works (`#how-it-works`)

Three numbered steps already in code:

1. Configure your agent (Business Brain sections)
2. Test before you go live (Test Studio / PSTN)
3. Review every call (ledger, memory, disposition)

UI: step number in mono, title, body, chip row. Stitch “process” timeline maps here.

### 4. Feature trio

Caller memory · Structured outcomes · Production reliability — existing `FEATURES` array. Samples must stay **illustrative** and labeled as examples, not live customer data.

### 5. Live-agent / sales proof (add if Stitch has it)

A restrained “on a sales call” panel:

- Call state chip: Listening / Speaking
- One Telugu user line + one agent line
- Disposition chip: `interested` / `callback_required`
- **Not** a wall of KPIs

### 6. Use cases (optional, selling)

Grid of 4–6 industries (real estate, admissions, clinic, auto, D2C, collections). Each card: industry, one sentence, “same 8-section brain”. No fake logos.

### 7. FAQ

Existing four questions in `HomeExperience` — keep. Add:

- Is this only for real estate? → No, generic platform.
- Can I hang up professionally after qualifying? → Yes, after next step + farewell (`end_call`).
- Where is my data? → Tenant isolation, retention days (Settings).

Accordion: one open at a time (already `openFaq` state).

### 8. Final CTA band

Headline: start with a browser test. Buttons: Sign in · Pricing. No Dev Portal.

### 9. Footer (`MarketingFooter`)

Product, Pricing, Docs, Privacy, Terms, DNC. Copyright Vāṇi.

## Pricing (`/pricing`)

**Current tiers:** Starter (usage-based) · Business (custom, highlighted) · Enterprise (contact).

Elements per card: name, price, one-line desc, feature bullets, CTA.

**Selling upgrades (align with billing spec):**

| Tier | Who | Entitlements to list |
|------|-----|----------------------|
| Starter | Trial / single agent | 1 agent, browser Test Studio, call archive, community |
| Business | Paying team | Unlimited agents, inbound+outbound PSTN, campaigns, analytics, GST invoice |
| Enterprise | Fleet | Custom stack, RBAC, promotion, SLA, dedicated engineer |

Highlighted card: `border-accent/40 bg-accent-dim/30 shadow-glow`. Others: hairline card.

CTA:

- Starter / Business → `/app/login` or `/app/billing` after auth
- Enterprise → `mailto:` or `/contact` (gap)

Copy: STT/LLM/TTS billed per tier; telephony via **Telnyx** (code). Do not promise a fixed INR/min until finance locks rates (`prd/07` FX notes).

## Docs (`/docs`)

Keep three columns: Quick start (console links), Call lifecycle API, Realtime WS. Mark `#` API links as “server routes” until a real docs site exists. Do not duplicate Dev Portal.

## Legal (gap)

Create `web/app/(marketing)/legal/privacy/page.tsx`, `terms/page.tsx`, `dnc/page.tsx`.

Must mention: call recording, retention, TRAI/DNC for outbound, subprocessors (OpenAI, Cartesia/Sarvam, Telnyx).

## SEO (prd/19)

- `generateMetadata` on every public page (home already has title/description + JSON-LD SoftwareApplication)
- `web/app/sitemap.ts` include `/`, `/pricing`, `/docs`, legal
- `robots.ts` allow those; **disallow** `/app`, `/dev`
- One `h1` per page
- `next/image` for any Stitch raster exports

## Responsive

- Hero: stacked on mobile, preview below copy
- Pricing: 1 col → 3 col at `lg`
- FAQ: full width
- Nav: collapse to menu under `md` (not implemented — add)

## Motion budget

Scroll progress bar, reveal on how-it-works, tilt on preview. No auto-playing voice on landing.
