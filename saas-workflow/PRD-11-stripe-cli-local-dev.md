# PRD-11 — Stripe CLI & local payment development

## Install Stripe CLI (Windows)

**Option A — winget (recommended)**

```powershell
winget install Stripe.StripeCli
```

**Option B — Scoop**

```powershell
scoop bucket add stripe https://github.com/stripe/scoop-stripe-cli.git
scoop install stripe
```

**Option C — Manual**

Download from [Stripe CLI docs](https://stripe.com/docs/stripe-cli) and add to PATH.

Verify:

```powershell
stripe version
```

## Login & keys

```powershell
stripe login
```

Dashboard → Developers → API keys:

- **Publishable** → Voxly `.env` if using Elements (optional)
- **Secret** → backend `STRIPE_SECRET_KEY=sk_test_...`

Never commit secrets; use `.env` (already gitignored).

## Local webhook forwarding

With backend running on port 8000:

```powershell
stripe listen --forward-to localhost:8000/api/stripe/webhook
```

Copy the printed **webhook signing secret** (`whsec_...`) to:

```
STRIPE_WEBHOOK_SECRET=whsec_...
```

Restart API after setting env.

### Events to listen for (minimum)

- `checkout.session.completed`
- `invoice.paid`
- `invoice.payment_failed`
- `customer.subscription.deleted`

Trigger test events:

```powershell
stripe trigger checkout.session.completed
```

(Customize fixtures once Checkout Session metadata is implemented.)

## Test cards

| Card | Scenario |
|------|----------|
| `4242 4242 4242 4242` | Success |
| `4000 0000 0000 9995` | Decline |
| `4000 0025 0000 3155` | Requires authentication (3DS) |

Use any future expiry, any CVC, any billing ZIP.

## Recommended local workflow

1. Start Postgres + migrate.
2. Start FastAPI: `uvicorn server.app:app --reload --port 8000`
3. Start `stripe listen --forward-to ...`
4. Start Voxly: `VITE_API_URL=http://localhost:8000/api npm run dev`
5. Complete buy flow → confirm webhook hits → `number_purchases.status=active`

## Stripe Dashboard setup (staging)

1. Create **Product**: "Phone number — India"
2. Add **Price** recurring monthly + optional one-time setup
3. Copy Price IDs into `number_catalog` seed or admin UI
4. Add webhook endpoint for production URL with same events

## Industry practices

- **Verify webhook signatures** on every request (`stripe.Webhook.construct_event`).
- **Idempotency**: store Stripe `event.id`; return 200 if already processed.
- **Don't provision on client success URL alone** — only on webhook (or retrieve Session server-side in success handler as backup).
- **Use metadata** on Checkout Session for `purchase_id` and `tenant_id`.
- **Customer object** per tenant for subscriptions and Portal.
- **Refunds** automated on provision failure with admin alert.

## CI

- Stripe CLI not required in CI; mock webhook payloads in pytest with signed test secret.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| 400 invalid signature | Wrong `STRIPE_WEBHOOK_SECRET` for listen vs dashboard |
| Webhook not received | Firewall, wrong port, path must match router |
| Double provision | Missing idempotency on `event.id` |
