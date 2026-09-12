# 01 — Stitch source and alignment

## Source

- **Project:** [Stitch — Design with AI](https://stitch.withgoogle.com/projects/17901155908568771114)
- **ID:** `17901155908568771114`
- **Role in this pack:** visual and UI-element source for marketing, auth, billing, console, and dev surfaces.
- **Role it does not have:** product scope, RBAC, APIs, or call lifecycle. Those stay in `prd/`.

Stitch is a screen generator. Treat each Stitch frame as a **composition** (layout, hierarchy, control types). Bind every control to a **real route and API** from this repo.

## Access note (important)

The public Stitch URL is a **Google-authenticated app**. Unauthenticated fetches return the Stitch shell, not the screen list or HTML. This pack therefore:

1. Records the project URL as the design source of truth.
2. Aligns **layout jobs** to the existing `web/` IA (which already matches PRD 11).
3. Instructs implementers to **export Stitch screens** (HTML + PNG) into [`stitch-exports/`](./stitch-exports/README.md) and fill the inventory table below.

Until exports land, **do not invent a third palette**. Use [02-ui-style-system.md](./02-ui-style-system.md). When HTML arrives, restyle Stitch markup onto our tokens — do not copy Google Sans / Material defaults into production.

## How to export (when you have access)

From the Stitch project UI:

1. Open each screen.
2. Export **PNG** (full frame) and **HTML** (or copy).
3. Save as `stitch-exports/<nn>-<slug>.png` and `.html`.
4. Fill the inventory table: Stitch title, device (desktop/mobile), mapped route.

Optional later: [Stitch SDK](https://github.com/google-labs-code/stitch-sdk) `project("17901155908568771114").screens()` with `STITCH_API_KEY`.

## Alignment rules

| Stitch shows… | This codebase does… |
|---------------|---------------------|
| Generic “AI dashboard” metrics wall | Map to **Overview** stats from `/api/health` + `/api/metrics` — no fake numbers |
| Chat-bot bubble UI | Map to **Test Studio** live transcript (`web/components/test-studio/*`), not a chatbot |
| “Integrations / CRM” marketplace | **Future** per `prd/17` — show Integrations **placeholder** only, never claim HubSpot/Salesforce live |
| Phone / calling | **PSTN Test Studio + Channels + Campaigns** (campaigns are PRD-in-scope; UI is still a gap) |
| Pricing cards | `/pricing` tiers → later **Billing** in `/app/settings` or `/app/billing` |
| Login split panel | Already exists: `AuthShell` |
| Dark operational console | `ConsoleShell` / `DevShell` + skeuo primitives |
| Landing cinematic hero | `HomeExperience` + cinematic-scroll skill |

**Copy rule:** Stitch English marketing copy may be used if it matches product truth (Telugu-first, memory, Test Studio, PSTN). Discard copy that claims RAG, CRM, or speech-to-speech — those are non-goals in `prd/01` §4.

## Expected Stitch screen → product map

Use this table even before exports. Rename rows to actual Stitch titles when you have them.

| Likely Stitch frame | Product surface | Next.js route | Status in repo |
|---------------------|-----------------|---------------|----------------|
| Marketing home / hero | Landing | `/` | Exists — `web/app/(marketing)/page.tsx` |
| Product / how it works | Landing chapters | `/#how-it-works` | Exists — `HomeExperience` |
| Pricing | Public pricing | `/pricing` | Exists — placeholder tiers, no checkout |
| Docs | Docs | `/docs` | Exists — thin |
| Sign in | Business auth | `/app/login` | Exists |
| Dev sign in | Dev auth | `/dev/login` | Exists |
| Workspace picker | Tenant select | `/app/select-tenant` | Exists — mock tenants |
| Access denied | RBAC wall | `/app/access-denied` | Exists |
| Overview / home | Business overview | `/app` | Exists |
| Agents list / create | Agents | `/app/agents` | Exists |
| Agent builder | Agent workspace | `/app/agents/[id]/*` | Exists |
| Live test / playground | Test Studio | `/app/test-studio` | Exists |
| Calls / history | Calls | `/app/calls`, `/app/calls/[id]` | Exists |
| Analytics | Analytics | `/app/analytics` | Exists |
| Billing / checkout | Payments | **gap** — specify in [07](./07-billing-and-payments.md) |
| Settings / org | Settings | `/app/settings` | Exists — thin |
| Dev home | Dev portal | `/dev` | Exists |
| Stack / providers | Dev stack | `/dev/stack`, `/dev/providers` | Exists |
| Platform brain | Dev brain | `/dev/platform-brain` | Exists |
| Promotion | Env promotion | `/dev/promotion` | Exists |

## Visual translation (Stitch HTML → our components)

When implementing a Stitch frame:

1. Identify regions: nav, hero, primary CTA, supporting panel, footer.
2. Replace Stitch colors with CSS variables (`--surface-chassis`, `--status-live`, `--accent-primary`, etc.).
3. Replace Stitch buttons with `Button` / `SkeuoButton` / `.btn-primary`.
4. Replace Stitch cards with `Panel` / `SkeuoPanel` / marketing `TiltCard`.
5. Replace Stitch tables with `SkeuoTable`.
6. Keep Stitch **spacing and grouping** if it is clearer than the current page; keep our **tokens and type**.

## What “aligned with the codebase” means

- One primary CTA per viewport (already a DESIGN.md rule).
- Business users never see Platform Brain text (`prd/11` §7, `prd/17` §3).
- Test Studio is the live-voice surface, not a second “chat” product.
- Disposition, memory, latency waterfall come from call archives — not invented dashboard widgets.
- Dev Portal stays unlinked from marketing nav.
