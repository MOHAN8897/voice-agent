# PRD-07 — Voxly AI frontend integration

## Repository

- **Frontend:** [github.com/saiskm115/voxly-ai](https://github.com/saiskm115/voxly-ai)
- **Stack:** React 18, Vite, Tailwind, Three.js (marketing); user console in `src/`
- **API client:** `src/services/api.js` — expects `VITE_API_URL` (e.g. `http://localhost:8000/api`)

## Deployment model

| Environment | Voxly | Backend |
|-------------|-------|---------|
| Local | `npm run dev` :5173 | FastAPI :8000 |
| Production | Vercel/static (see repo `vercel.json`) | API subdomain `api.example.com` |

### CORS

- `CORS_ORIGINS=https://voxly.example.com,http://localhost:5173`
- Allow headers: `Authorization`, `Content-Type`
- **Subscriber API uses Bearer JWT** — not cookies (PRD-03). Dev portal unchanged.

### Voxly `api.js` changes (Phase E only)

1. Store `accessToken` in memory; `refreshToken` in HttpOnly cookie **if** same-site, else secure storage + refresh body.
2. Attach `Authorization: Bearer` on all authenticated calls.
3. On 401 → call `/api/auth/refresh` once, retry.
4. Implement signup/login/logout per PRD-03 before agents/telephony pages.

**Do not start Phase E until [PRD-12](./PRD-12-backend-saas-readiness.md) Phase A–D pass.**

### Local dev proxy (optional)

`vite.config.js` proxy `/api` → `localhost:8000` avoids CORS during development.

## Pages to wire

| Voxly area | Backend dependency |
|------------|-------------------|
| Landing / pricing | Static; pricing amounts from `GET /api/billing/catalog` (new) optional |
| Signup / login | PRD-03 auth |
| Agents list/detail | `/api/agents` + brain publish |
| Telephony / numbers | PRD-04 |
| Live call / simulator | PSTN outbound + WebSocket status (poll or SSE) |
| Calls history | `/api/calls` |
| Campaigns | `/api/campaigns` (exists, tenant-scoped) |
| Leads / CRM | New or stub until phase 3 |
| Billing wallet | Stripe Customer Portal + top-up (PRD-04/10) |

## Simulator vs real PSTN

Voxly **Live Call Simulator** may use mock when `VITE_API_URL` empty. For production:

- Replace simulator with real `POST /api/telephony/calls/outbound` when user has number + agent.
- Show provisioning states on number buy UI.

## Monorepo option (optional)

Keep Voxly as separate repo; document in root `README`:

```bash
# voice agent backend
cd "D:\voice agent" && uvicorn server.app:app --reload

# voxly frontend
git clone https://github.com/saiskm115/voxly-ai.git ../voxly-ai
cd ../voxly-ai && cp .env.example .env
# VITE_API_URL=http://localhost:8000/api
npm install && npm run dev
```

Submodule or `docs/voxly-integration.md` link — avoid duplicating Voxly inside voice agent unless requested.

## Next.js `/app` console

Decision:

- **A)** Deprecate public `/app` for subscribers; Voxly is sole console.
- **B)** Keep `/app` for internal QA; Voxly for customers.

PRD recommends **B** short-term, converge APIs so both use same `/api/*` subscriber routes.

## Branding

Voxly owns marketing UX; backend returns neutral JSON (no "Telnyx" in subscriber errors).
