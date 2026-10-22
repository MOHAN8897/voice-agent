# E2E SaaS audit checklist (Voxly + backend)

**E2E:** Playwright in `voxly-ai/e2e/` (TestSprite removed). API must be on `:8000`, Voxly on `:5173`.

## Automated (run locally)

```powershell
alembic upgrade head
python -m pytest server/tests/test_razorpay_wallet.py server/tests/test_saas_auth.py server/tests/test_google_oauth.py -q
cd voxly-ai
npm install
npx playwright install chromium
npm run test:e2e
```

Optional full console flow (verified user):

```powershell
$env:E2E_EMAIL="you@example.com"
$env:E2E_PASSWORD="your-password"
npm run test:e2e
```

Required `.env` for SaaS + Google: `SAAS_AUTH_ENABLED=true`, `DATABASE_URL`, `JWT_SECRET`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/auth/google/callback`, `VOXLY_FRONTEND_URL=http://localhost:5173`.

## Auth (singinflow.md)

| Step | UI | API | Backend validates |
|------|----|-----|-------------------|
| Signup | Voxly Auth modal | `POST /api/auth/signup` | Rate limit, password hash, Resend verify email |
| Verify email | `#verify-email?token=` | `POST /api/auth/verify-email` | Single-use token table `013` |
| Login | Auth modal | `POST /api/auth/login` | Generic errors, unverified blocked |
| Session | Console gate | `GET /api/auth/me` + JWT | Tenant membership + email verified |
| Refresh | Cookie | `POST /api/auth/refresh` | HttpOnly `voxly_refresh` |
| Dev portal | `/dev/login` | `POST /api/dev/login` | Env creds, HttpOnly session, IP rate limit |

## Console modules ↔ API

| Module | API | Notes |
|--------|-----|--------|
| Employees / Create wizard | `GET/POST/PATCH/DELETE /api/agents` | Normalized `agent_id` → UI `id` |
| Phone numbers | `GET /api/telephony/numbers`, `search`, `buy`, `assign` | Buy → Stripe checkout URL when configured |
| Billing | wallet, Razorpay create/verify, invoices | INR credits in `balance_inr_paise` |
| Calls / Leads / Campaigns | `/api/calls`, `/api/leads`, `/api/campaigns` | JWT tenant scoped |

## Razorpay wallet E2E (manual)

1. `SAAS_AUTH_ENABLED=true`, logged into Voxly console.
2. Billing → **+₹500** → Razorpay Checkout (test mode).
3. After pay: `POST /api/billing/razorpay/verify` → wallet INR ↑, row in `GET /api/billing/invoices`.

## SEO (Voxly)

- `public/robots.txt`, `public/sitemap.xml`
- `index.html`: canonical, OG/Twitter, JSON-LD (already present)
- Production: serve over HTTPS, update `sitemap.xml` host to live domain

## PRD alignment

- Phases 1–7 backend: see `PRD-PHASES-1-7-STATUS.md`
- API map: update `PRD-08-api-contract-mapping.md` as endpoints land (auth/billing now implemented)

## Known gaps

- Number **buy** is Stripe subscription flow (PRD-04), not Razorpay.
- Workspace **demo fallback** only when not logged in; logged-in users see API errors (no silent mock).
- Google OAuth requires `GOOGLE_OAUTH_*` in `.env`.
- Full browser E2E: add Playwright against `voxly-ai` (not in CI yet).
