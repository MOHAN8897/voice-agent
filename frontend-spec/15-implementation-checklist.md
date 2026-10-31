# 15 — Implementation checklist

Build **in this order** so the selling site stays aligned with working voice.

## Phase A — Visual lock

- [ ] Export Stitch screens into `frontend-spec/stitch-exports/`
- [ ] Fill inventory table in [01](./01-stitch-source-and-alignment.md)
- [ ] Map each frame to a route; discard out-of-scope (CRM, RAG)
- [ ] Confirm tokens: marketing teal vs console skeuo ([02](./02-ui-style-system.md))

## Phase B — Marketing (sell)

- [ ] Nav: Sign in + Pricing + Docs
- [ ] Hero CTA → `/app/login?next=/app/test-studio`
- [ ] Keep how-it-works / memory story
- [ ] Footer legal links (pages can be stub)
- [ ] Metadata, sitemap, robots
- [ ] Mobile nav
- [ ] Reduced motion

## Phase C — Auth

- [ ] Restyle `AuthShell` from Stitch without changing login API
- [ ] Real tenant list
- [ ] Canonical `/app/login` (alias `/login`)
- [ ] Onboarding checklist on Overview

## Phase D — Console polish (operate)

- [ ] Real env + tenant on `ShellTopBar`
- [ ] Overview empty + health banner
- [ ] Brain unsaved/validation states
- [ ] Test Studio a11y + PSTN readiness
- [ ] Calls filters + disposition labels
- [ ] Honest Integrations / Benchmarks empty copy

## Phase E — Selling gaps (product)

- [ ] Legal pages
- [ ] Billing API + `/app/billing` ([07](./07-billing-and-payments.md))
- [ ] Campaigns UI when PRD 18 API exists
- [ ] Members + audit in Settings

## Phase F — Dev Portal (already shipped)

Do **not** build a new portal. `/dev/*` exists (`prd/08` MVP item 1, `prd/17` §9, `prd/19` §3.2).

- [x] Login, shell, stack, platform brain, test studio, promotion routes
- [ ] Keep unlinked from marketing
- [ ] Stitch restyle **on** `DevShell` only (Layer B palette)
- [ ] Secrets remain booleans
- [ ] Real environment label on `ShellTopBar`

## Definition of done (frontend)

A stranger can:

1. Understand the product on `/` in 30 seconds  
2. Open pricing  
3. Sign in  
4. Create or open an agent  
5. Run Test Studio  
6. See a call in Calls  

A customer admin can see **draft vs active** and never see platform brain text.

An engineer can open `/dev`, change a stack, test, promote.

No page claims CRM, RAG, or a completed WhatsApp send.

## PRD cross-check

| This pack | PRD |
|-----------|-----|
| Sitemap | 11 |
| Stack / Next | 19 |
| Locked scope | 17 |
| Memory / calls | 04, 12 |
| Campaigns | 18 |
| APIs / RBAC | 13, 15 |
| Voice quality | 01 G-02 |
| Visual / palette / look | **20** |

If a Stitch frame fights PRD 17 (e.g. “connect Salesforce”), **do not build it**.
