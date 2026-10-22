# 20 — Visual design, color palette, page look, and UI elements

**Status:** Normative for how the website and consoles **look**. Product behavior stays in [11](./11-ui-information-architecture.md), [17](./17-product-decisions.md), and [19](./19-frontend-backend-nextjs-railway.md).

**Implementation sources (already in repo):**

| Source | Owns |
|--------|------|
| [`DESIGN.md`](../DESIGN.md) | Marketing / brand tokens (teal, serif display) |
| [`web/app/globals.css`](../web/app/globals.css) | **Shipped** console + Dev Portal skeuomorphic tokens |
| [`web/components/ui/skeuo/`](../web/components/ui/skeuo/) | Console controls |
| [`frontend-spec/`](../frontend-spec/README.md) | Screen-by-screen build pack |

If this file and `DESIGN.md` disagree on **marketing**, `DESIGN.md` wins. If they disagree on **`/app` or `/dev`**, **`globals.css` wins** (that is what is shipping).

---

## 0. Dev Portal is already built

The **Developer Portal is implemented** in Next.js. Do not treat `/dev` as a greenfield design. Align Stitch and future UI work to **existing routes and shells**.

| PRD decision | Code |
|--------------|------|
| P0 Dev Portal auth (`17` §9) | `/dev/login` → `POST /api/dev/login`, `LoginForm` + `AuthShell variant="dev"` |
| Separate `/dev` prefix, not mixed with customers | `web/app/dev/(portal)/*` vs `web/app/app/(console)/*` |
| Stack / tiers / Platform Brain / promotion | `/dev/stack`, `/dev/platform-brain`, `/dev/promotion`, … |
| Session cookie + CSRF | `auth-client.ts`, `/api/dev/logout` |
| Not on public marketing nav | `MarketingNav` has no `/dev` link; `robots` disallow `/dev` |

**Shell already used:** `DevShell` → `InstrumentSidebar` + `DevNav` + `ShellTopBar` + `DevPortalProvider`.

**Shipped nav (`DevNav.tsx`):** Overview · Environment · Stack & tiers · Runtime tuning · Platform Brain · Compiled preview · Providers · Agents · Test Studio · Benchmarks · Promotion.

Remaining Dev Portal work is **visual alignment, real env labels, and Stitch restyle on the same routes** — not a second portal.

Business Console (`/app/*`) is also shipped; customer auth was P2 in `17` and now exists as `/app/login`.

---

## 1. Product look (what the website should feel like)

**Personality:** confident, agentic, operational. Telugu-first. A **voice control plane**, not a chatbot landing page and not a neon “AI dashboard.”

Three surfaces, **two visual systems**:

```text
Marketing  /  /pricing /docs     → Layer A  editorial, cinematic, teal
Business   /app/*                → Layer B  skeuo instrument, steel + live rose
Dev Portal /dev/*                → Layer B  same skeuo, denser, more telemetry
```

Never mix teal marketing CTAs with skeuo chassis on the same page. Never use marketing teal as the **live/recording** color in consoles (live is rose `#e11d48`).

**Do**

- Dark only for v1 (no Material light theme from Stitch)
- One primary action per viewport
- Hierarchy from spacing and type before color
- Real Telugu in agent previews / transcripts
- Complete loading, empty, error, forbidden states

**Don't**

- Neon purple / pink AI gradients
- Fake metric walls
- Google Sans / Material defaults copied from Stitch HTML
- Chat-bubble product as the home metaphor
- Linking Dev Portal from the public site

---

## 2. Color palettes

### 2.1 Layer A — Marketing (selling site)

From `DESIGN.md`. Use on `/`, `/pricing`, `/docs`, legal, auth **marketing aside** may borrow grid + glow.

| Token | Hex | Where it appears |
|-------|-----|------------------|
| Background | `#06090d` | Page canvas |
| Background elevated | `#0c1118` | Nav blur, elevated bands |
| Surface | `#10161f` | Secondary blocks |
| Surface raised | `#161e2a` | Hover cards |
| Surface card | `#131920` | Pricing cards, feature cards |
| Border | `#243040` | Strong rules |
| Border subtle | `#1a2430` | Hairlines, nav bottom |
| Text | `#eef2f6` | Headlines, body |
| Text muted | `#8b9aab` | Subcopy |
| Text subtle | `#5c6b7a` | Captions, mono footer lines |
| **Primary / accent** | `#3dd6c6` | Primary buttons, live dots on marketing, links |
| Accent dim | `#0f2e2a` | Highlighted pricing card wash |
| Accent glow | `#3dd6c633` | Hero glow only (one blob) |
| Telemetry | `#4db5ff` | Latency chips in `AgentPreview` |
| Telugu gold | `#e8c468` | Telugu sample text only |
| Success | `#3dd68c` | Optional “online” pill on preview |
| Warning | `#f0b429` | Rare; validation on forms if shown on marketing |

Primary button: teal fill, **dark text** (`#06090d`), `rounded-xl`. Secondary: transparent, subtle border, light text.

### 2.2 Layer B — Business Console and Dev Portal (shipped)

From `web/app/globals.css`. **This is how `/app` and `/dev` already look.** Restyles must keep these values.

| Token | Hex / value | Where it appears |
|-------|-------------|------------------|
| Chassis (page) | `#08090c` | Full-page background; faint steel radial at top-left |
| Panel | `#111318` | Sidebar, cards, `SkeuoPanel` |
| Panel raised | `#171b22` | Hover rows, raised buttons |
| Panel inset | `#0c0e12` | Meters, JSON wells, pressed wells |
| Glass | `rgba(12,14,18,0.78)` | Sticky bars |
| Border highlight | `rgba(255,255,255,0.055)` | Top-left bevel |
| Border inset | `rgba(0,0,0,0.5)` | Inner shadow edge |
| Text primary | `#f0f2f5` | Titles, nav active |
| Text secondary | `#9aa3b2` | Body, inactive nav |
| Text muted | `#6b7280` | Hints, timestamps |
| **Steel accent** | `#8fa6c4` | Links, selected chrome, focus (not “live”) |
| Steel dim | `rgba(143,166,196,0.12)` | Selected nav wash |
| **Live / recording** | `#e11d48` | Test Studio live, barge, recording, `--accent` alias |
| Live glow | `rgba(225,29,72,0.18)` | Live halo |
| Success | `#4ade80` | Healthy, configured |
| Warning | `#fbbf24` | Validation, missing key |
| Error | `#f87171` | Failed call, API error |
| Info | `#60a5fa` | Trace / telemetry |

**Light model:** upper-left. Raised controls use `--shadow-raised`. Inset wells use `--shadow-inset`. Active = `skeuo-pressed`.

**Radius:** 6 / 10 / 14 px (`--radius-sm/md/lg`).

**Production env chip:** `skeuo-env-prod` (distinct border, not a loud color).

### 2.3 Semantic chips (both consoles)

| Meaning | Fill / text |
|---------|-------------|
| Disposition interested / converted | success on inset |
| callback_required | warning |
| not_interested / wrong_number | muted text |
| error / failed | error |
| Channel browser | steel |
| Channel PSTN | info or steel + label “PSTN” |
| Env development | muted |
| Env staging | warning tint |
| Env production | `skeuo-env-prod` |

---

## 3. Typography

### Marketing

| Role | Face | Size / weight |
|------|------|----------------|
| Display H1 | Instrument Serif (if loaded) or tight sans | ~2.65rem → 3.25rem, tracking tight |
| Section H2 | Same family, 3xl–4xl | |
| Body | DM Sans | 16–18px, line-height ~1.55–1.6 |
| Label caps | DM Sans or mono | 11–12px, tracking wide, accent color |
| Mono | JetBrains Mono | 11px uppercase captions |
| Telugu | Noto Sans Telugu | line-height ≥ 1.5 |

### Consoles (`/app`, `/dev`)

| Role | Face | Notes |
|------|------|--------|
| Page title | `PageHeader` | Eyebrow + title + description |
| Nav | sans, 14px | `SkeuoNavItem` |
| Forms | 14px | `SkeuoInput` |
| IDs, latency, env | mono 11–12px | Dev Portal uses **more** mono than Business Console |
| Telugu transcript | Noto Sans Telugu | Test Studio + call detail |

---

## 4. How each page type should look

### 4.1 Marketing home `/`

- Full-bleed dark canvas, **grid mask** + **one** teal glow behind hero (no rainbow).
- Sticky nav: hairline bottom, blur, BrandMark left, links muted, **one** teal CTA.
- Hero: left editorial (pill + H1 with one teal word + subcopy + two buttons). Right: **instrument preview** (`AgentPreview` in `TiltCard`) — window chrome, dots, transcript, waveform, latency — not a stock 3D robot.
- Sections: generous `py-24`, left-aligned titles, not centered generic SaaS.
- Feature cards: hairline, hover `border-accent/30`, no drop-shadow stacks.
- FAQ: one-open accordion.
- Footer: muted links, no Dev Portal.

Motion: transform/opacity only; still frame if `prefers-reduced-motion`.

### 4.2 Pricing `/`

- Same marketing canvas.
- Three cards; **one** highlighted (`border-accent/40`, `accent-dim` wash, `shadow-glow`).
- Price is large; features are check rows with teal ticks.
- CTA on highlight = filled teal; others = outlined.

### 4.3 Auth `/app/login` and `/dev/login`

**Already built:** split `AuthShell`.

- Left (desktop): elevated surface, grid, soft glow, BrandMark, eyebrow, large headline, three check rows, quiet footer.
- Right: centered form, inputs, primary submit.
- **Dev login** eyebrow = “Restricted access”; no “Back to website” required.
- **Business login** = “Business Console” + link back to `/`.

Do not restyle into a centered-only Material card unless Stitch is remapped onto this split.

### 4.4 Business Console `/app/*`

**Already built:** chassis `#08090c`, left **instrument sidebar**, top bar (product + entity + env + connection), main `max-w-shell`.

Look:

- Dense but not cramped (`p-5 md:p-8`)
- Cards = raised skeuo panels, not flat Tailwind gray cards
- Live Test Studio = rose status on nav item
- Tables = `SkeuoTable`; empty = `SkeuoEmptyState`
- Page starts with `PageHeader` (eyebrow, title, description)

### 4.5 Dev Portal `/dev/*` — **already built, keep this look**

Same chassis as Business Console so engineers feel one product.

**Differences that must stay visible:**

| Business `/app` | Dev `/dev` |
|-----------------|------------|
| Subtitle “Business Console” | Subtitle “Developer Portal” |
| Customer workflow (agents, calls) | Platform workflow (keys → stack → brain → test → promote) |
| Hide Platform Brain body | Platform Brain editor is a first-class page |
| Softer empty states | More JSON wells, traces, IDs |
| Footer: Profile + Sign out | Footer: link **to** `/app` + Sign out |

**Overview `/dev`:** three `StatCard`s (envs, tiers, protected brain) + numbered `DevCard` workflow (01–05). This matches `prd/08` MVP item 1 and `17` §9. **Do not replace with a marketing landing.**

**Environment:** boolean configured/missing keys — never show secret strings. Warning color for missing.

**Stack:** matrix / forms, steel focus, save as primary skeuo button.

**Test Studio (dev):** same live rose as business; extra trace panel allowed.

**Promotion:** confirmation dialog; production chip uses `skeuo-env-prod`.

---

## 5. UI elements (normative inventory)

Use existing components. Mapping:

| Element | Component / class | Surfaces |
|---------|-------------------|----------|
| Wordmark | `BrandMark` | All |
| Marketing nav / footer | `MarketingNav`, `MarketingFooter` | Public |
| Primary / secondary CTA | `.btn-primary` `.btn-secondary` | Marketing |
| Split auth | `AuthShell` | Login |
| Form field | `Input` / `SkeuoInput` + `Label` + `FieldError` | Auth, settings |
| App / Dev shell | `ConsoleShell` / `DevShell` | Consoles |
| Sidebar + nav item | `InstrumentSidebar`, `SkeuoNavItem` | Consoles |
| Top bar | `ShellTopBar` | Consoles |
| Page header | `PageHeader` | Consoles |
| Stat | `StatCard` | Overviews |
| Panel / card | `Panel`, `SkeuoPanel` | Consoles |
| Button | `SkeuoButton` | Consoles |
| Badge | `SkeuoBadge` | Disposition, env |
| Table | `SkeuoTable` | Calls, providers |
| Meter | `SkeuoMeter` | Usage, latency |
| Status light | `SkeuoStatusLight` | Health |
| Empty | `SkeuoEmptyState` | Lists |
| Confirm | `ConfirmDialog` | Promote, destructive |
| Live test | `TestStudioLivePanel` + memory + metrics | Test Studio |
| Call audio / transcript | `CallAudioPanel`, `CallTranscriptTimeline` | Calls |
| Brain editor | `BusinessBrainEditor` | `/app` brain |
| Dev workflow card | `DevCard` | `/dev` overview |
| Icons | `skeuo/icons.tsx` only | Nav |

Stitch Material widgets (FAB, drawer, tonal card) map to the row above — see [`frontend-spec/02-ui-style-system.md`](../frontend-spec/02-ui-style-system.md).

---

## 6. Layout geometry

| Surface | Max width | Nav |
|---------|-----------|-----|
| Marketing | `72rem` (`max-w-content`) | Horizontal sticky |
| Auth | Split ~42% aside / form | None |
| `/app` and `/dev` | `max-w-shell` in main | Persistent sidebar desktop; drawer mobile |

---

## 7. Alignment with other PRDs

| Topic | Document |
|-------|----------|
| Sitemap, screen contracts, a11y | [11](./11-ui-information-architecture.md) |
| Dev Portal P0 vs Business P2 | [17](./17-product-decisions.md) §9 |
| Next.js `/dev` vs `/app`, robots | [19](./19-frontend-backend-nextjs-railway.md) §3 |
| Dev APIs | [13](./13-api-data-security-contracts.md) |
| MVP sequence (Dev Portal first) | [08](./08-implementation-roadmap.md) — **UI for this item is already in `web/app/dev`** |
| Screen build pack | [`frontend-spec/`](../frontend-spec/README.md) |
