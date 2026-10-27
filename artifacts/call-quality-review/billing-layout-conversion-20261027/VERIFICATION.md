# Script layout, settings navigation, wallet/GST, web pricing and lead conversion

Date: 2026-10-27. Branch: `working-app-22-10-2026`.

Implemented and verified locally. No real payment, refund, call, saved pricing value, or saved GST setting was changed during verification. Existing unrelated work in the working tree was preserved. Nothing was committed or pushed in this task.

## Delivered

1. The Script page has a smaller script editor in the left half. Greeting, farewell and objections form a natural stack on the right. Mobile stacks the sections vertically. The script still expands to its content and the page scrolls. The opening greeting's runtime behavior was preserved.
2. Settings now has four icon cards: All settings, Agent & phone, Call handling, and Recording & compliance. Selecting a card shows its category while preserving unsaved edits. The existing floating save/discard dock remains available for unsaved changes.
3. Wallet checkout uses server GST quotes, separates tax from wallet credit, rejects a changed total before opening checkout, and can retry verification without making another payment. Admin GST rules now have a draft checkout preview, customer-facing terms, and stale-edit protection.
4. Each stack profile has an independent `webRetailRateInr`. Admin can edit it beside the phone rate in Stack & tiers. The selected stack's browser rate is locked at call admission and used for billing. Existing profiles without an override use the saved global web default. Phone and web prices stay separate.
5. Leads support a Converted stage, explicit tenant confirmation, stage counts and filtering. Automatic call disposition cannot certify a sale or overwrite a confirmed conversion.

## Confirmed critical issues and fixes

These findings were traced through source and covered by regression tests. Provider responses in payment tests were mocked; the persistence tests use disposable SQLite.

### 1. Browser calls could inherit the phone rate

The composed call path previously selected `composed_snapshot["retailRate"]` for both channels. The legacy path always selected the global web rate, missing an exact profile override.

The composed snapshot now carries `webRetailRate`. Admission chooses `"webRetailRate" if channel == "browser" else "retailRate"`, validates it and stores an immutable rate snapshot. The legacy path resolves the exact profile's browser rate as well. Older profiles use the explicitly saved web default, never an inferred phone price.

Evidence: `server/call/call_lifecycle_service.py:228`, `server/call/call_lifecycle_service.py:405`, `server/services/saas/voice_stack_profiles.py:425`. Persistence and evidence preservation are covered by `test_web_price_persists_without_changing_phone_price_or_verified_stack`; channel selection and immutable snapshots are covered by `test_browser_composed_lifecycle.py`.

### 2. International cards paying INR could credit GST into the wallet

The previous international-payment branch assigned the complete provider `base_amount` to wallet credit. An INR payment's settlement can include GST.

INR now uses the order's snapshotted taxable value. Foreign-currency settlements allocate their verified INR base amount between taxable credit and tax with Decimal arithmetic. Tax remains outside the spendable balance. Provider payment/order ID, captured status, amount and currency are checked before credit or duplicate success is accepted.

Evidence: `server/services/saas/razorpay_service.py:502` and `server/services/saas/razorpay_service.py:579`. SQLite tests verify one credit and one invoice after checkout/webhook replay, and reject a payment replayed against another order.

### 3. Payment currency incorrectly controlled export GST treatment

The previous rule was `domestic = currency == "INR" and buyer_country == "IN"`. That could classify an Indian buyer paying USD as an export. Disabling the export zero-rating option also did not actually apply the configured tax to foreign recipients.

Recipient location now determines domestic treatment: `domestic = buyer_country == "IN"`. The saved export policy determines zero-rating; with that option off the configured IGST is applied. CGST/SGST/IGST shown at checkout use the charge currency, while invoices retain INR minor units.

Evidence: `server/services/saas/tax_service.py:374` and `server/services/saas/tax_service.py:407`. Tests cover Indian USD checkout, same/different Indian states, tax-inclusive pricing, the export option off, and odd-paise rounding.

This is a configurable tax policy, not automatic proof that every foreign customer meets every statutory export condition. Currency alone is insufficient. The technical change follows the distinction described in [CBIC Circular 88/07/2019](https://cbic-gst.gov.in/pdf/circular-cgst-88.pdf); actual export eligibility remains part of the business's tax policy.

### 4. Quotes could go stale or change before checkout

A delayed quote for a previous amount could replace the current amount's quote. The server also recalculated the order total without comparing it with the amount the customer had reviewed.

Quote generations are invalidated on amount, currency and modal lifecycle changes. Pay is enabled only for a quote matching the displayed amount and currency. Order creation receives optional `expectedTotalMinor` and rejects `quote_changed` before contacting the provider if the latest total differs. The frontend reloads the quote for review.

Evidence: `voxly-ai/src/console/ui/AddFundsModal.jsx`, `server/routes/app_billing.py:42`, `server/services/saas/razorpay_service.py:289`. Browser tests control delayed responses and assert that a changed quote does not open the provider checkout.

### 5. A failed checkout attempt could swallow a later successful retry

The checkout wrapper previously settled its callback state on `payment.failed`, even though a customer can retry inside the same checkout window. A later successful attempt could then be ignored.

Failure is surfaced without settling the checkout. A later success or dismissal completes the same checkout lifecycle. Verification failure retains the original payment response and quote across modal close/reopen, blocks another Pay action, and offers Check payment status. Wallet refresh failure after verified payment does not relabel the payment as failed.

Evidence: `voxly-ai/src/utils/razorpayCheckout.js`, `voxly-ai/src/console/ui/AddFundsModal.jsx`, and `voxly-ai/e2e/wallet-checkout-recovery.spec.js`. Capture validation remains server-owned, consistent with [Razorpay's capture documentation](https://github.com/razorpay/markdown-docs/blob/master/payments/payments/capture-settings/api.md).

The pending browser recovery state survives closing this modal within the same loaded app. A full page reload relies on the existing webhook/reconciliation path; no cross-reload browser payment-state persistence was added.

### 6. Repeated small partial refunds could over-reverse wallet credit or tax

Each refund previously rounded its share independently. Several partial refunds could reverse more paise than the original invoice contained.

Refunds now allocate the cumulative refunded share, subtract what has already been reversed, and bound the remaining reversal. Amount and currency are validated. Prior refunds and credit notes are tenant-scoped, and the invoice/wallet locking path is retained.

Evidence: `server/services/saas/razorpay_service.py:985`. A disposable database test refunds a three-paise invoice in three steps and confirms that exactly two paise of credit and one paise of tax are reversed.

### 7. Unavailable tax settings could silently fall back during checkout

Checkout now uses `load_config(strict=True)` and fails clearly if the configuration store is unavailable. Enabled GST with incomplete supplier identity also blocks checkout. Other readers retain their existing environment fallback.

Evidence: `server/services/saas/tax_service.py:204` and `server/services/saas/razorpay_service.py:240`. The missing-store regression asserts `tax_configuration_unavailable`.

### 8. Admin loading could replace saved values or a fresh edit

The stack editor cached its empty startup draft before saved profiles arrived. This could show an empty/default web price despite a saved value. The GST form also had a small window where loaded data enabled inputs before its form state had been applied, allowing that state application to overwrite a quick edit.

Stack drafts are no longer cached ahead of the initial profile response. GST controls remain disabled until the loaded settings have been applied. Saving carries `expectedUpdatedAt`; the server rejects stale edits under the settings row lock.

Evidence: `web/components/dev/PstnVoiceProfileWorkbench.tsx:597`, `web/components/dev/GstBillingSettings.tsx:162`, `web/components/dev/GstBillingSettings.tsx:282`, `server/services/saas/tax_service.py:283`. Browser tests prove saved low/medium web prices stay separate and a draft 20% rate previews a 1200 total on a 1000 subtotal without saving. A database test proves a stale editor cannot overwrite a newer saved tax rate.

## Admin configuration and customer behavior

- Stack & tiers: each selected profile exposes Phone price, Web agent price and supplier cost separately. Web price uses the existing profile autosave. Leaving it blank uses the saved Default Web Calling Rate. This change did not assign new prices to real stacks.
- GST below the stack editor: configure enabled status, supplier identity, rate, inclusive/exclusive pricing, export policy, numbering and Invoice and checkout terms. Preview the draft for same-state, different-state or eligible export customers in INR or USD before saving.
- Checkout terms are returned with the server quote and shown before payment. Saved supplier identity and tax splits remain snapshotted per order/invoice; later edits do not rewrite historical invoices.
- With an 18% exclusive GST policy, a 1000 INR recharge costs 1180 INR and credits 1000 INR. Tax is not spendable wallet credit.
- Test-call UI and the tenant billing page show the selected stack's web rate. Unknown browser pricing is displayed as unavailable rather than a fabricated free rate.
- New lead conversions require “I confirm this lead became a customer.” The server enforces confirmation on create/stage/notes routes after tenant resolution. Converted leads remain terminal for automatic lead updates; manual tenant edits remain possible.

## Verification results

- Backend: **160 passed, 1 skipped**, across 18 focused payment, GST, wallet, call-billing, tier-pricing, profile and lead test files. Evidence: `backend-regression.xml`.
- After the final admin-route annotation cleanup, the 10 checkout/tier/preview regressions passed again, including authenticated access and tenant-role rejection.
- The skipped test is `test_tier_pricing_and_supplier_cost_persistence_and_sync`, gated by `LIVE_DB=1`. It was not enabled because it requires a live database. Disposable database tests separately exercised persisted payment credit, replay, partial refunds, stale tax editing and saved web pricing. SQLite does not establish PostgreSQL concurrency behavior.
- Tenant browser: **21 passed**, no skipped, unexpected or flaky cases. Suites: wallet checkout recovery, GST invoices/profile, workspace experience and console layout. Evidence: `tenant-browser.log`.
- Admin browser: **2 passed**, covering per-stack web price separation and draft GST preview/save payloads. Run: `cd web; npx playwright test -c e2e/billing-stack.config.ts`.
- Reticle: **25 tenant + 3 admin verdicts `verified: yes`**. Evidence: `reticle-verification.json` and `reticle-admin.json`. These are local leased-browser checks with intercepted APIs; they do not establish live gateway behavior. Reticle reports partial channel coverage and a desktop host stub; the installed app SDK is 3.7.0 and the leased driver is 3.8.2, with no `version_skew` result.
- The admin preview initially returned `unknown` due to Reticle's off-viewport click detection. It was not counted as a pass. Explicit keyboard activation produced a verified result. A tool defect report was sent using the [Reticle verification skill](<D:/voice agent/.agents/skills/install-and-verify/SKILL.md>); no application source, credentials or customer data were included.
- Both production builds passed: Vite tenant console, including six public-page prerenders; Next admin, including 50 generated routes. Logs: `tenant-build.log`, `admin-build.log`.
- Separate TypeScript check passed: `cd web; npx tsc --noEmit --incremental false`. Build-only changes to `web/next-env.d.ts` and `web/tsconfig.json` were restored.
- New payment regression files pass Ruff. Comparing changed backend source diagnostics with HEAD found **zero new Ruff findings**; existing repository lint debt remains. Evidence: `ruff-delta.json`.
- `git diff --check` passed. Its log includes existing Windows line-ending notices, without whitespace errors.
- Security scan **could not execute**: `python scripts/security_audit.py --mode sast` exited 127 because Windows Application Control blocked `pysemgrep`. This is not a clean security scan. Evidence: `security-scan.log`.

## Remaining verification boundaries

No real customer payment, test-mode gateway transaction, refund, webhook delivery or PostgreSQL concurrency exercise was run. Existing provider signatures, captured-payment checks, tenant boundaries and wallet debit paths were exercised through tests. Merchant capture configuration and delivery through the deployed provider account were not independently verified by these local fixtures.

The live-database pricing test and SAST scan remain unverified. No deployment or GitHub push was performed. Screenshots inspected locally: `artifacts/console-script-desktop.png`, `artifacts/console-settings-desktop.png`, and `artifacts/console-settings-mobile.png`.
