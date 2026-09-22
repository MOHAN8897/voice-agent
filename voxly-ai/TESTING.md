# Voxly console testing

## Playwright (primary E2E)

From `voxly-ai/`:

```bash
npm install
npx playwright install chromium
npm run test:e2e
```

Environment:

| Variable | Purpose |
|----------|---------|
| `VOXLY_API_URL` | API base (default `http://127.0.0.1:8000`) |
| `E2E_EMAIL` / `E2E_PASSWORD` | Verified subscriber for login + dashboard tests |

`playwright.config.js` can start API (`:8000`) and Vite (`:5173`) when nothing is listening.

Specs: `e2e/smoke.spec.js`, `e2e/saas-flow.spec.js`, `e2e/google-oauth.spec.js`, `e2e/console-billing.spec.js`.

## Stagehand (optional AI UI checks)

```bash
npm run test:stagehand
```

Requires `OPENAI_API_KEY` (or model env supported by Stagehand) and a running dev site (`VOXLY_WEB_URL`, default `http://127.0.0.1:5173`).

## Chrome DevTools MCP (Cursor)

Repo `.cursor/mcp.json` includes `chrome-devtools` via `npx chrome-devtools-mcp@latest`. Requires **Node 22+**. Reload MCP in Cursor after install.

Use for live network/console inspection while debugging console ↔ API issues.

## Console ↔ backend checklist

| Area | API | Notes |
|------|-----|--------|
| Auth | `/api/auth/*` | JWT in `localStorage`; refresh cookie on same origin (Vite `/api` proxy). |
| Agents | `/api/agents` | Create sends `name`, `languages`. |
| Numbers | `/api/telephony/numbers`, `buy`, `assign` | **Buy** opens Stripe `checkoutUrl`; wallet top-up uses Razorpay in Billing. |
| Calls / Leads | `/api/calls`, `/api/leads` | Tenant-scoped when `SAAS_AUTH_ENABLED`. |
| Campaigns | `/api/campaigns` | Subscriber JWT via `require_api_tenant`. |
| Billing | `/api/billing/wallet`, Razorpay routes | INR wallet separate from Stripe number checkout. |

When signed in, the console does **not** fall back to demo data on API errors; use the yellow **Retry sync** banner on partial failures.

## Wallet & PSTN usage

- Top up via **Razorpay (INR)** or **Stripe (USD)** on the Billing tab.
- PSTN outbound requires minimum balance (`PSTN_MIN_BALANCE_*` in API `.env`) and a **published** agent brain.
- Usage is debited per completed PSTN call (`usage_pstn` ledger rows). View wallet via `GET /api/billing/wallet` and `GET /api/billing/transactions`.
- Run migration **`014_wallet_ledger_reference`** (`alembic upgrade head`).
