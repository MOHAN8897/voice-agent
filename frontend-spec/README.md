# Frontend specification — Vāṇi voice-agent selling website

This folder is the **build pack for the Next.js frontend** in `web/`. It translates:

- Google Stitch project [17901155908568771114](https://stitch.withgoogle.com/projects/17901155908568771114)
- Canonical product PRDs in [`prd/`](../prd/README.md)
- Locked decisions in [`prd/17-product-decisions.md`](../prd/17-product-decisions.md)
- Existing App Router routes, shells, and components in `web/`

into **screen-level instructions** for a voice-agentic **selling** website: marketing, sign-in, billing, business console, and the **already-built Developer Portal**.

**Dev Portal is not a future page.** It ships today at `/dev/*` (`web/app/dev`, `DevShell`, `DevNav`) and matches [`prd/17`](../prd/17-product-decisions.md) §9 (P0). This pack **aligns look and Stitch** to those routes. It does not propose a second admin app.

**Visual system (palette + how pages look):** [`prd/20-visual-design-and-ui-style.md`](../prd/20-visual-design-and-ui-style.md) and [02-ui-style-system.md](./02-ui-style-system.md).

## How to use this pack

| If you are… | Start here |
|-------------|------------|
| Implementing UI | [15-implementation-checklist.md](./15-implementation-checklist.md) + the screen file for that surface |
| Matching Stitch | [01-stitch-source-and-alignment.md](./01-stitch-source-and-alignment.md) then drop exports in `stitch-exports/` |
| Tokens / components | [02-ui-style-system.md](./02-ui-style-system.md) and [10-component-library.md](./10-component-library.md) |
| Sitemap / nav | [04-information-architecture.md](./04-information-architecture.md) |
| Finding code | [12-codebase-route-map.md](./12-codebase-route-map.md) |

Normative product behavior still lives in PRD. If this pack and PRD conflict: **PRD wins** (`01` → `15` → `17` → `20` visual → topic docs). This pack wins only for **Next.js file placement** where PRD 20 already locked tokens.

## File index

| File | Contents |
|------|----------|
| [01-stitch-source-and-alignment.md](./01-stitch-source-and-alignment.md) | Stitch URL, access gap, how screens map onto `web/` |
| [02-ui-style-system.md](./02-ui-style-system.md) | Color palettes, page look, elements (mirrors PRD 20) |
| [03-voice-agentic-selling-product.md](./03-voice-agentic-selling-product.md) | What a selling voice-agent website must contain |
| [04-information-architecture.md](./04-information-architecture.md) | Audiences, sitemap, journeys |
| [05-landing-and-marketing.md](./05-landing-and-marketing.md) | Home, pricing, docs, legal, SEO |
| [06-auth-signin-onboarding.md](./06-auth-signin-onboarding.md) | Sign-in, tenant, access denied, first-run |
| [07-billing-and-payments.md](./07-billing-and-payments.md) | Plans, checkout, usage, invoices (mostly **gap**) |
| [08-business-console.md](./08-business-console.md) | `/app/*` operator console |
| [09-dev-portal.md](./09-dev-portal.md) | **Shipped** `/dev/*` — align to PRD 17/19/20, do not rebuild |
| [10-component-library.md](./10-component-library.md) | UI elements to reuse vs build |
| [11-screen-by-screen-contracts.md](./11-screen-by-screen-contracts.md) | Fields, actions, empty/error states per screen |
| [12-codebase-route-map.md](./12-codebase-route-map.md) | Route → file → API |
| [13-copy-content-seo.md](./13-copy-content-seo.md) | Headlines, CTAs, JSON-LD |
| [14-states-a11y-responsive.md](./14-states-a11y-responsive.md) | Loading, empty, a11y, breakpoints |
| [15-implementation-checklist.md](./15-implementation-checklist.md) | Build order and definition of done |
| [stitch-exports/README.md](./stitch-exports/README.md) | Drop Stitch HTML/PNG here |

## Locked stack (do not change)

From [`prd/19-frontend-backend-nextjs-railway.md`](../prd/19-frontend-backend-nextjs-railway.md) and [`.better-react-web-ui.md`](../.better-react-web-ui.md):

- **Framework:** Next.js App Router, TypeScript, `web/`
- **Styling:** Tailwind + CSS variables in `web/app/globals.css`
- **No vanilla SPA** as the product UI (`client/` is historical reference only)
- **No provider secrets** in the browser
- Live voice stays in **client components**; REST lists in **server components**
- Backend: FastAPI in `server/` (REST + WebSocket). PSTN in this repo is **Telnyx L16** (PRD still names Plivo in older docs — UI copy should say **PSTN / Telnyx**, not invent a second carrier brand)

## Two consoles, one product

```text
Public site          Business Console           Developer Portal
/  /pricing /docs    /app/*                     /dev/*
anyone               tenant members             platform staff
sell + educate       operate agents             stack, brain, promote
```

The marketing site **sells** the product. `/app` **runs** it. `/dev` **already tunes** it (shipped) and must not appear in public nav ([`prd/19`](../prd/19-frontend-backend-nextjs-railway.md), [`prd/20`](../prd/20-visual-design-and-ui-style.md)).
