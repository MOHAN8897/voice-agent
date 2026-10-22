# 07 — Billing and payment pages

**Status: product gap.** There is no `/app/billing` route and no payment provider in `server/`. Public `/pricing` is informational only. A selling website still needs these screens specified so Stitch checkout frames have a home.

**Do not** implement fake Stripe success. Wire UI only when a billing API exists.

## Why it belongs

Buyers need: plan, usage (STT/LLM/TTS + PSTN minutes), GST invoice, failed-payment state. Analytics may show **estimated cost** (`prd/11` Overview) from registry `pricing_metadata` — that is **not** billing.

## Recommended routes

| Route | Purpose |
|-------|---------|
| `/pricing` | Public catalog (exists) |
| `/app/billing` | Plan, usage, payment method, invoices |
| `/app/billing/checkout` | Confirm plan → provider hosted page |
| `/app/billing/success` | Return URL |
| `/app/billing/invoices/[id]` | PDF / GST invoice |

Settings may link “Billing” instead of a top-nav item (progressive disclosure). For a selling SaaS, a **Billing** nav item under Settings is enough; don’t put it next to Test Studio.

## Plan catalog (align with `/pricing`)

| Plan | Commercial shape | Entitlements |
|------|------------------|--------------|
| Starter | Usage, card on file | 1 agent, browser only, community |
| Business | Usage + platform fee or commit | Unlimited agents, PSTN, campaigns, analytics |
| Enterprise | Contract | Custom stack, SLA, invoice terms |

Show **included** vs **metered**:

- Metered: STT minutes, TTS characters, LLM tokens, Telnyx/PSTN legs  
- Included: seats (define), retention days, environments  

Never display raw provider USD rates to customers unless product wants passthrough. Prefer **INR** with a dated FX note (`prd/07` `FX_RATE_INR`).

## Billing home (`/app/billing`) — UI elements

Stitch “subscription dashboard” maps here.

1. **Current plan card** — name, status (trialing / active / past_due / canceled), renew date  
2. **Usage meters** — calls this period, PSTN minutes, estimated INR  
3. **Payment method** — last4, brand, expiry (never PAN)  
4. **Invoices table** — date, number, amount, GSTIN, status, download  
5. **Primary actions** — Upgrade · Update card · Cancel (Customer Admin only)

Empty: “No payment method — add a card to enable PSTN and campaigns.”

## Checkout (`/app/billing/checkout`)

- Order summary: plan + estimated usage disclaimer  
- GSTIN field (India B2B)  
- Billing address  
- CTA: **Continue to payment** (redirect to Razorpay/Stripe Checkout — **choose one** at implementation; don’t embed card fields unless PCI scope is accepted)  
- Cancel → `/pricing` or `/app/billing`

## Success / failure return

- Success: “Plan active” + CTA to Channels (connect number) or Test Studio  
- Failure: “Payment not completed” + retry  
- `past_due`: banner on all `/app` pages — PSTN outbound paused, browser test may remain

## Invoices

Columns: Invoice # · Date · Amount (INR) · Tax · Status · PDF.

Must support GST invoice fields when GSTIN present.

## Permissions

| Role | Billing |
|------|---------|
| Customer Admin | Full |
| Operator / Viewer | Read invoices if product allows; no card change |
| Dev Portal | No customer billing (platform cost dashboards are separate and internal) |

## Copy constraints

- “Usage-based” is honest; don’t show ₹0 forever on marketing JSON-LD (`home` currently has `offers.price: "0"` — change when paid plans exist).
- Telephony is billed by the carrier **and** the platform — say so.
- Campaigns consume the same minute pool.

## Implementation gate

Do not add checkout UI until:

1. Billing customer id on `tenant`
2. Webhook endpoint on API (signature verified)
3. Entitlement middleware (PSTN/campaigns require `active` or `trialing`)
4. Audit log of plan changes (`prd/13`)
