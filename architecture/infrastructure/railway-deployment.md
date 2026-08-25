# Railway Deployment Architecture

Production deployment topology on Railway.

**Locked decision:** Next.js on Railway `web` service + FastAPI `api` + `worker` in one project ([`prd/17`](../../prd/17-product-decisions.md) §11).

---

## 1. Service topology

```text
                    RAILWAY PROJECT
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  ┌─────────────────┐         public URL                      │
│  │  WEB service    │  app.example.com                       │
│  │  Next.js 20     │  Marketing + Dev Portal + Business UI  │
│  └────────┬────────┘                                        │
│           │  private network                                  │
│           │  NEXT_PUBLIC_API_URL → api.railway.internal      │
│           ▼                                                  │
│  ┌─────────────────┐         public URL (WS)                │
│  │  API service    │  api.example.com                       │
│  │  FastAPI        │  REST + /ws/stt /ws/tts /ws/plivo      │
│  └────────┬────────┘                                        │
│           │                                                  │
│  ┌────────┴────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │  WORKER service │  │ Postgres │  │ Redis            │   │
│  │  Python jobs    │  │          │  │ dialer + jobs    │   │
│  └─────────────────┘  └──────────┘  └──────────────────┘   │
│                                                              │
│                       ┌──────────────────┐                   │
│                       │ Storage bucket   │                   │
│                       │ audio, exports   │                   │
│                       └──────────────────┘                   │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Service configuration

| Service | Root | Start command | Port |
|---------|------|---------------|------|
| **web** | `web/` | `npm run start` | 3000 |
| **api** | `server/` | `uvicorn app:app --host 0.0.0.0 --port 8000` | 8000 |
| **worker** | `worker/` | `python -m worker.main` | — |

### Resource hints

| Service | CPU/RAM | Notes |
|---------|---------|-------|
| api | 2 vCPU, 2GB+ | WebSocket long-lived connections |
| web | 1 vCPU, 1GB | SSR + static |
| worker | 1 vCPU, 1GB | Burst during campaigns |

---

## 3. Environment groups

| Group | `ENVIRONMENT` | `VOICE_AGENT_CONFIG_MODE` | Database |
|-------|---------------|---------------------------|----------|
| development | development | frontend | Local / dev plugin |
| staging | staging | env | Staging Postgres |
| production | production | env | Production Postgres |

Shared secrets (provider keys) via Railway shared variables; environment-specific overrides for tiers and URLs.

---

## 4. Networking

### Public routes

| Domain | Service | Paths |
|--------|---------|-------|
| `app.example.com` | web | `/`, `/dev/*`, `/app/*` |
| `api.example.com` | api | `/api/*`, `/ws/*` |

### Private routes

- `web` → `api`: `http://api.railway.internal:8000`
- `worker` → `api`: internal for status callbacks
- All services → Postgres, Redis via Railway private network

### Next.js rewrites (`web/next.config.js`)

```javascript
async rewrites() {
  return [
    { source: '/api/:path*', destination: `${process.env.API_INTERNAL_URL}/api/:path*` },
    // WebSocket: client connects directly to api.example.com/ws (public)
  ];
}
```

**WebSockets:** Browser connects to `api` public URL directly (not through Next.js proxy) for lower latency.

---

## 5. Secrets distribution

| Secret | web | api | worker |
|--------|-----|-----|--------|
| `OPENAI_API_KEY` | — | ✓ | ✓ |
| `SARVAM_API_KEY` | — | ✓ | — |
| `PLIVO_*` | — | ✓ | ✓ |
| `DATABASE_URL` | — | ✓ | ✓ |
| `REDIS_URL` | — | ✓ | ✓ |
| `DEV_PORTAL_PASSWORD` | ✓ (SSR auth) | ✓ | — |
| `NEXT_PUBLIC_API_URL` | ✓ | — | — |

**Rule:** No provider keys in `NEXT_PUBLIC_*` variables.

---

## 6. CI/CD

```text
git push → Railway deploy hooks
  ├── web: npm ci && npm run build
  ├── api: pip install && pytest (pre-deploy check)
  └── worker: pip install
```

Migrations: run Alembic on api deploy (`alembic upgrade head`).

---

## 7. Local development

```text
docker compose up postgres redis   # optional
cd server && uvicorn app:app --reload
cd web && npm run dev
# Or from repo root (Windows):
# powershell -ExecutionPolicy Bypass -File scripts/dev_up.ps1 -KillStale
cd worker && python -m worker.main  # optional
```

`.env` at repo root; `web/.env.local` for `NEXT_PUBLIC_API_URL=http://localhost:8000`.

---

## 8. Optional: Vercel for marketing

Not default MVP. If adopted later:

- Vercel: marketing pages only
- Railway: api + worker + app console
- Requires CORS + cookie domain configuration

---

## 9. Health checks

| Service | Endpoint |
|---------|----------|
| api | `GET /api/health` (DB + Redis ping) |
| web | `GET /api/health` (rewrite) or `/` |
| worker | Redis heartbeat key |

---

## 10. Phase rollout

| Phase | Deploy target |
|-------|---------------|
| 1–4 | api only + local PostgreSQL |
| 5 | Full Railway project (web + api + worker + data)
