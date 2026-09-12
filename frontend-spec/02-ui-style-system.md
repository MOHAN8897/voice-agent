# 02 — UI style system (palette, look, elements)

Normative PRD twin: [`prd/20-visual-design-and-ui-style.md`](../prd/20-visual-design-and-ui-style.md).  
Marketing tokens: [`DESIGN.md`](../DESIGN.md).  
**Shipped console + Dev Portal CSS:** [`web/app/globals.css`](../web/app/globals.css).

Personality: **confident, agentic, operational**. Dark control plane — not a chatbot site, not Material light, not neon AI.

Two layers. **Never mix on one page.**

---

## Color palette — Layer A (marketing `/` `/pricing` `/docs`)

| Token | Hex | Use on the page |
|-------|-----|-----------------|
| Canvas | `#06090d` | Full background |
| Elevated | `#0c1118` | Sticky nav |
| Card | `#131920` | Pricing / feature cards |
| Border subtle | `#1a2430` | Hairlines |
| Text | `#eef2f6` | Headlines, body |
| Muted | `#8b9aab` | Subcopy |
| Subtle | `#5c6b7a` | Captions |
| **Teal accent** | `#3dd6c6` | **The** primary button, one live dot, highlighted word in H1 |
| Teal dim / glow | `#0f2e2a` / `#3dd6c633` | Highlighted pricing wash; **one** hero glow |
| Telemetry blue | `#4db5ff` | Latency chips in preview only |
| Telugu gold | `#e8c468` | Telugu sample strings only |
| Success | `#3dd68c` | Preview “online” pill |

Primary button = teal fill + **dark** label. One primary CTA per viewport.

## Color palette — Layer B (`/app` **and shipped `/dev`**)

This is how the **existing Dev Portal and Business Console already look**. Keep it.

| Token | Hex | Use on the page |
|-------|-----|-----------------|
| Chassis | `#08090c` | Page; faint steel radial top-left |
| Panel | `#111318` | Sidebar, cards |
| Raised | `#171b22` | Hover, raised buttons |
| Inset | `#0c0e12` | JSON wells, meters, pressed |
| Text | `#f0f2f5` / `#9aa3b2` / `#6b7280` | Title / body / hint |
| **Steel** | `#8fa6c4` | Links, selected nav, focus — **not** live |
| **Live rose** | `#e11d48` | Test Studio live, barge, recording |
| Success / warn / error / info | `#4ade80` / `#fbbf24` / `#f87171` / `#60a5fa` | Status |

Bevel: upper-left highlight. Radius 6 / 10 / 14. **Do not paint Dev Portal teal.**

---

## How pages should look

### Marketing home

Dark canvas + grid + **one** teal glow. Sticky hairline nav. Hero: left copy (status pill, H1 with one teal word, two buttons), right **instrument preview** (window chrome, transcript, waveform) — not a 3D mascot. Sections `py-24`, left-aligned. Cards: hairline, hover teal border 30%. FAQ accordion. Footer muted. **No `/dev` link.**

### Pricing

Same canvas. Three cards, **one** glow highlight. Teal ticks. Filled CTA only on highlight.

### Auth (shipped `AuthShell`)

Split pane: left story + ticks, right form. Dev login = “Restricted access”. Business = back to website.

### Business Console `/app` (shipped)

Skeuo chassis, **instrument sidebar**, top bar (product, tenant, env, connection). `PageHeader` then panels. Live rose only on Test Studio. Tables and empty states from skeuo kit.

### Dev Portal `/dev` (shipped — do not rebuild)

**Same Layer B** as `/app` so it is one product.

Must keep looking like an **ops instrument**, not a marketing site:

- Sidebar subtitle **Developer Portal**
- Overview: 3 stat cards + 01–05 `DevCard` workflow (keys → stack → brain → test → promote) — this **is** PRD `08` MVP item 1
- Environment: configured/missing **booleans**, warning if key missing
- Stack: dense forms / matrix
- Platform Brain: editor, not a customer accordion
- Compiled / traces: inset JSON wells, more mono IDs than `/app`
- Promotion: confirm dialog; production chip `skeuo-env-prod`
- Footer link **to Business Console** `/app`
- Test Studio: same live rose + extra `SessionTracePanel`

Stitch “admin dashboard” frames restyle **these routes**, they do not replace `DevNav`.

---

## Elements (use these, don’t invent)

See [10-component-library.md](./10-component-library.md) and PRD 20 §5.

Marketing: `BrandMark`, `MarketingNav`, `.btn-primary`, `AgentPreview`, `TiltCard`, `Reveal`.  
Auth: `AuthShell`, `LoginForm`, `Input`, `Button`.  
Consoles: `DevShell` / `ConsoleShell`, `SkeuoNavItem`, `SkeuoPanel`, `SkeuoButton`, `SkeuoTable`, `SkeuoBadge`, `PageHeader`, `StatCard`, `ConfirmDialog`.  
Voice: `TestStudioLivePanel` and siblings.

Icons: `skeuo/icons.tsx` only.

---

## Type

Marketing display: Instrument Serif if loaded, else tight sans ~3rem H1. Body DM Sans. Mono JetBrains for captions. Telugu: Noto Sans Telugu, line-height ≥ 1.5.

Consoles: `PageHeader` titles, 14px forms, 11–12px mono IDs (Dev Portal uses **more** mono).

---

## Motion

Transform + opacity. `prefers-reduced-motion` → still. No autoplay voice on public pages.

## Don't

Neon purple, fake KPIs, Google Sans from Stitch, light mode v1, teal live indicators on `/dev`, second icon set, chatbot home.
