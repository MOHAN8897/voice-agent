# Voxly frontend ↔ voice agent backend

## Layout

| Piece | Path / URL |
|--------|------------|
| Backend API | `server/` — `http://localhost:8000` |
| Voxly UI (clone) | `voxly-ai/` — `http://localhost:5173` |
| Dev admin (unchanged) | `web/` dev portal — `DEV_PORTAL_USERNAME` / `DEV_PORTAL_PASSWORD` |

## One-time setup

1. Root `.env`: copy fields from `saas-workflow/ENV-SaaS.example` plus your existing provider keys.
   - Set `SAAS_AUTH_ENABLED=true`, `JWT_SECRET`, `DATABASE_URL`.
   - Razorpay: `razorpay_api_key` / `razorpay_api_secret` (or uppercase variants).
   - Google: `GOOGLE_OAUTH_*` and `VOXLY_FRONTEND_URL=http://localhost:5173`.
2. Migrations: `alembic upgrade head` (includes `012_razorpay_invoices`).
3. Voxly: `cd voxly-ai && npm install && npm run dev`.
   - API calls use `/api` proxy to `:8000` unless `VITE_API_URL` is set.

## Auth flows (see `singinflow.md`)

- **Email/password**: signup sends **Resend** verification email; login only after verify (`SAAS_REQUIRE_EMAIL_VERIFICATION_FOR_LOGIN`).
- **Tokens**: short-lived **access** in memory/localStorage; **refresh** in **HttpOnly** cookie (`voxly_refresh`) + optional body for non-browser clients.
- **Forgot/reset**: generic API messages; reset link emailed via Resend.
- **Session restore**: `GET /api/auth/me` with `Authorization: Bearer`.
- **Google**:
  - `GET /api/auth/google/config` — public `{ enabled, clientId, redirectUri }`; Auth modal disables the button when `enabled` is false.
  - Redirect: `GET /api/auth/google/start` → callback → `#auth/callback?accessToken=...` (handled in `AuthContext`).
  - Or GIS: optional `VITE_GOOGLE_CLIENT_ID`; otherwise the UI uses `clientId` from config and falls back to redirect.
- **Console gate**: `#dashboard/*` requires a valid JWT; landing stays public.

## Billing

- **INR wallet**: `POST /api/billing/razorpay/create-order` → Razorpay Checkout → `POST /api/billing/razorpay/verify` → invoice row + `balance_inr_paise`.
- **USD wallet**: `POST /api/billing/topup` → Stripe Checkout URL (if `STRIPE_SECRET_KEY` set).
- **Invoices**: `GET /api/billing/invoices` (shown in Billing module).

Rate limits: billing routes use `RateLimiter` (30 req / 5 min per user for top-up/order).

## Google Cloud (CLI + Cursor MCP)

See **`saas-workflow/GOOGLE-CLOUD-SETUP.md`** and run `scripts/setup-google-cloud.ps1`.  
`.cursor/mcp.json` includes the [Cloud CLI remote MCP](https://cloud.google.com/sdk/use-gcloud-mcp) endpoint; complete OAuth in Cursor (client + `http://localhost:8787/callback` for desktop).

## E2E (Playwright)

TestSprite is **not** used. From `voxly-ai/`:

```powershell
npx playwright install chromium
npm run test:e2e
```

Playwright starts API + Vite when ports are free (`reuseExistingServer`). Set `PLAYWRIGHT_SKIP_WEBSERVER=1` if you already run `npm run dev`.

- Smoke + Google UI/config: always (when API is up).
- Full SaaS API/UI: set `SAAS_AUTH_ENABLED=true` in root `.env`, then optional `E2E_EMAIL` / `E2E_PASSWORD` for a **verified** user.

Checklist: `saas-workflow/E2E-SAAS-AUDIT.md`.

## Dev panel

Not gated by subscriber JWT. Use existing dev portal credentials in `.env` (`DEV_PORTAL_*`).

## Production notes

- Set `CORS_ORIGINS` and `VOXLY_FRONTEND_URL` to your deployed Voxly origin.
- Do not commit `.env`. Rotate keys if they were ever exposed in chat or logs.
