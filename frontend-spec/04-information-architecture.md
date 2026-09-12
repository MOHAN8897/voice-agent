# 04 — Information architecture

Normative sitemap: [`prd/11-ui-information-architecture.md`](../prd/11-ui-information-architecture.md).  
This file is the **frontend** view of that sitemap plus selling pages.

## Audiences

| Audience | Enters via | Sees |
|----------|------------|------|
| Prospect | `/` | Marketing only |
| Customer Admin | `/app/login` | Full business console, no platform brain body |
| Customer Operator | `/app` | Test Studio, calls; limited publish |
| Customer Viewer | `/app` | Calls + analytics read-only |
| Voice Engineer | `/dev/login` and/or `/app` | Providers, benchmarks, traces |
| Platform Admin | `/dev` | Platform brain, promotion, environment keys |
| Auditor | `/app` or `/dev` read | Versions, audit log (thin today) |

RBAC is **server-enforced**. UI hides; it does not authorize (`prd/11` §16, `prd/15`).

## Public sitemap

```text
/                      HomeExperience
/pricing               Tiers
/docs                  Thin API/docs
/legal/privacy         GAP
/legal/terms           GAP
/legal/dnc             GAP (campaigns / TRAI)
```

Marketing nav today: brand + “How it works” + CTA. **Target nav:** Product · How it works · Pricing · Docs · Sign in.

## Auth sitemap

```text
/app/login             Business LoginForm  POST /api/app/login
/app/select-tenant     Workspace picker
/app/access-denied     Forbidden
/dev/login             Dev LoginForm       POST /api/dev/login
```

Also `/login` exists as a redirect/alias — keep one canonical (`/app/login`) in copy.

## Business console (`/app`)

Primary nav — already in `web/lib/constants.ts` `PRIMARY_NAV`:

1. Overview `/app`
2. Agents `/app/agents`
3. Test Studio `/app/test-studio`
4. Calls `/app/calls`
5. Analytics `/app/analytics`
6. Benchmarks `/app/benchmarks` (disabled-by-default per `prd/17` — UI may exist, runs need config)
7. Providers `/app/providers` (safe catalog, not secrets)
8. Integrations `/app/integrations` (placeholder)
9. Settings `/app/settings`

**Add for selling SaaS (gaps):**

- Billing `/app/billing` (or Settings → Billing)
- Campaigns `/app/campaigns` (PRD 18)
- Profile `/app/profile` (exists)

### Agent workspace tabs

`AGENT_WORKSPACE_TABS` in `constants.ts`:

Summary · Business Brain · Voice & Models · Memory Schema · Tools & Actions · Channels · Versions & Deployment

Plus **Test** at `/app/agents/[id]/test` (mirrors Test Studio scoped to one agent).

**Never** put Platform Brain in this tab list for customers.

## Developer portal (`/dev`) — **already implemented**

Matches [`prd/17`](../prd/17-product-decisions.md) §9, [`prd/19`](../prd/19-frontend-backend-nextjs-railway.md) §3.2, and [`prd/20`](../prd/20-visual-design-and-ui-style.md).

From `DevNav.tsx` (do not invent a second nav):

Overview · Environment · Stack & tiers · Runtime tuning · Platform Brain · Compiled preview · Providers · Agents · Test Studio · Benchmarks · Promotion

Look: Layer B skeuo — [02](./02-ui-style-system.md) and [09](./09-dev-portal.md). Workflow on `/dev` overview: keys → stacks → platform brain → live test → promote.

## Core user journeys

### J1 — Prospect → first test

Landing → Pricing (optional) → Sign in → (Tenant) → Overview empty state → Create agent → Business Brain Identity section → Test Studio browser call.

### J2 — Configure sales agent

Agents → Brain (8 sections) → Voice tier → Channels (PSTN) → Test → Versions → Promote (admin) → Campaigns (gap).

### J3 — Inspect a live lead call

Calls list (filter disposition) → Call detail (audio, transcript, memory, outcome) → optional Analytics.

### J4 — Engineer promotes a stack

`/dev/environment` → `/dev/stack` → `/dev/test-studio` → `/dev/benchmarks` (if enabled) → `/dev/promotion`.

## Environment chrome

Every console top bar shows **environment** (`ShellTopBar` already has `environment="development"`). Production UI must pass the real env, not a hardcoded string.

Draft vs active version must appear on every agent edit page (`prd/11` §5).

## Navigation don'ts

- Do not revive `client/` six-tab SPA as IA.
- Do not put Advanced / VAD sliders on Overview.
- Do not link Dev Portal from `MarketingNav`.
- Do not use “Chat” as a top-level item.
