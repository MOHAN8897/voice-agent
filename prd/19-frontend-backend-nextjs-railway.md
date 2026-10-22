# 19 — Frontend vs Backend, Next.js, Railway Deployment, SEO, and Performance

Normative split of responsibilities, deployment topology, SEO, and performance for the MVP.

**Frontend framework (locked):** **Next.js (App Router) only.** No vanilla HTML/CSS/JS SPA in the target product. The existing `client/` folder is **historical reference** for live-voice and barge-in behavior to port into Next.js — it is **not** deployed or extended for MVP.

---

## 1. Deployment topology

### 1.1 Primary — single Railway project (recommended MVP)

Railway supports **multiple services** in one project, including a **Next.js frontend** and a **long-running API** with WebSockets. This is the **default deployment model** for this product.

```text
                    RAILWAY PROJECT
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  ┌─────────────────┐      private network / public URL       │
│  │  WEB service    │  Next.js App Router (Node 20)            │
│  │  (frontend)     │  Marketing, Dev Portal, Business UI    │
│  └────────┬────────┘                                        │
│           │ REST + browser WS/SSE to API service             │
│           ▼                                                  │
│  ┌─────────────────┐                                        │
│  │  API service    │  FastAPI — REST + WebSocket proxy      │
│  │  (backend)      │  STT/TTS/Plivo WS, voice pipeline      │
│  └────────┬────────┘                                        │
│           │                                                  │
│  ┌─────────────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │  WORKER service │  │ Postgres │  │ Redis (queue)    │  │
│  │  campaigns,     │  │ agents,  │  │                  │  │
│  │  post-call,     │  │ calls,   │  └──────────────────┘  │
│  │  summaries      │  │ campaigns│                          │
│  └─────────────────┘  └──────────┘  ┌──────────────────┐  │
│                                     │ Storage bucket   │  │
│                                     │ audio, exports   │  │
│                                     └──────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

| Service | Railway role | Root directory |
|---------|--------------|----------------|
| **web** | Next.js frontend (SSR/SSG, SEO, consoles) | `web/` |
| **api** | FastAPI voice API + WebSockets | `server/` (+ start command) |
| **worker** | Background jobs | `worker/` |
| **PostgreSQL** | Managed plugin | — |
| **Redis** | Managed plugin | — |
| **Bucket** | Object storage plugin | — |

**Why Railway for frontend too**

- One project, one bill, shared env groups, **private networking** between `web` ↔ `api` ↔ `worker`.
- Railway runs Next.js as a **persistent Node service** (not serverless-only) — suitable for SSR and long sessions.
- Same platform as API/worker/Postgres — simpler ops than split Vercel + Railway for MVP.
- Custom domains: e.g. `app.yourdomain.com` → web, `api.yourdomain.com` → api (or path-based proxy — see §4).

Official reference: Railway multi-service SaaS architecture (API + Postgres + Redis + Worker in one project).

### 1.2 Optional alternative — Next.js on Vercel + API on Railway

Use only if you later need Vercel’s global edge CDN for marketing at scale:

| Layer | Host |
|-------|------|
| Next.js | Vercel |
| API, WS, Worker, data | Railway |

Cross-origin CORS + cookies required. **Not the default MVP path.**

### 1.3 Rules (all topologies)

| Rule | Detail |
|------|--------|
| **Next.js only** | All user-facing UI in `web/` — no production vanilla `client/` |
| **Secrets** | Provider keys, Plivo, brain secrets — **API/Worker services only** |
| **WebSockets** | Always terminate on **API service** (`/ws/stt-realtime`, `/ws/tts`, `/ws/plivo-stream`) |
| **Workers** | Campaign dialer, post-call, retention — **Worker service**, not Next.js |
| **SEO** | Next.js Metadata API, `sitemap.ts`, `robots.ts` on **web** service |

---

## 2. Next.js frontend stack (mandatory)

| Layer | Choice |
|-------|--------|
| Framework | **Next.js 14+ App Router** |
| Language | TypeScript |
| Styling | Tailwind + CSS variables. **Normative look:** [20-visual-design-and-ui-style.md](./20-visual-design-and-ui-style.md). Marketing tokens: `DESIGN.md`. Console + Dev Portal: `web/app/globals.css` (already shipping). |
| Data fetching | Server Components where possible; client components for live voice |
| Hosting | **Railway `web` service** (primary) |
| Live voice | Client components porting logic from `client/app.js`, `live-guards.js`, worklets — **same behavior**, Next.js implementation |

### 2.1 What NOT to build

- No new features in `client/*.html`, `client/app.js`, or vanilla SPA tabs
- No “extend existing SPA” path in MVP
- Do not serve `client/` from FastAPI in production (remove static mount after `web` ships)

---

## 3. Frontend responsibilities (Next.js `web/`)

Runs in the **browser** or **Next.js server (RSC/SSR)** on the **web** Railway service. No provider secrets in client bundles.

### 3.1 Public marketing (SEO-critical)

| Responsibility | Implementation |
|----------------|----------------|
| Landing, pricing, docs, legal | App Router pages — SSG or ISR |
| Metadata | `generateMetadata` per route |
| `sitemap.xml`, `robots.txt` | `app/sitemap.ts`, `app/robots.ts` |
| JSON-LD | Layout or page-level structured data |
| Semantic HTML | One `h1`, landmarks, Telugu-first copy |
| Images | `next/image` |

### 3.2 Dev Portal (`/dev/*`) — **implemented**

The Dev Portal is **already built** in `web/app/dev/`. Align new work to these routes; do not create a parallel admin app. Visual look: [20-visual-design-and-ui-style.md](./20-visual-design-and-ui-style.md) Layer B.

| Responsibility | Implementation (code) |
|----------------|------------------------|
| Login → API session cookie | `/dev/login` → `LoginForm` `POST /api/dev/login`; `AuthShell variant="dev"` |
| Shell / nav | `DevShell`, `DevNav`, `DevPortalProvider` |
| Overview workflow | `/dev` — env → stack → platform brain → test → promote |
| Environment & key presence | `/dev/environment` (`EnvironmentPanel`) — booleans, never secrets |
| Stack/tier UI | `/dev/stack` — STT/LLM/TTS per LOW/MEDIUM/PREMIUM |
| Runtime (barge/VAD) | `/dev/runtime` |
| Platform Brain editor | `/dev/platform-brain` — developer only; customers never see body |
| Compiled preview | `/dev/compiled` |
| Providers / agents / test | `/dev/providers`, `/dev/agents`, `/dev/test-studio` |
| Benchmarks | `/dev/benchmarks` — gated until scenarios configured (`17`) |
| Promotion staging → production | `/dev/promotion` — confirmation; `prd/11` §13 state machine |
| Logout | `/api/dev/logout` |
| Isolation | Not linked from marketing; `robots` disallow `/dev` |

### Business Console (`/app/*`)

| Responsibility | Implementation |
|----------------|----------------|
| Agents, Business Brain accordion, campaigns, calls | App Router layouts — **shipped** under `web/app/app/(console)` |
| Tier chips only in production / ENV mode | No provider matrix for customers |
| Customer auth | `/app/login` (P2 in `17`; **now implemented**) |

### 3.4 Live voice (client components)

| Responsibility | Implementation |
|----------------|----------------|
| Mic, PCM worklet | Port from `client/pcm-worklet.js` |
| STT/TTS WebSocket | Connect to API service public or proxied URL |
| Brain SSE | Same contract as today |
| Barge-in | Port `live-guards.js` policy — **no redesign** |
| `call/start`, `call/end` | REST to API service |

### 3.5 Frontend must NOT do

- Store provider API keys
- Compile brain, merge memory, write ledger
- Resolve tiers (display server-resolved stack only)
- Enforce RBAC (server authoritative)

---

## 4. Backend responsibilities (Railway `api` + `worker`)

### 4.1 API service

| Responsibility | Module |
|----------------|--------|
| REST `/api/*` | FastAPI routes |
| WebSocket proxies | `routes/ws.py`, Plivo WS |
| Auth sessions, RBAC | Middleware |
| CORS | Allow web service origin(s) |
| `live_turn_orchestrator`, memory, ledger, brain | `call/*`, `brain/*`, `agent/*` |
| Provider adapters | Server-only |

### 4.2 Worker service

| Responsibility | Module |
|----------------|--------|
| Post-call outcome | `post_call_pipeline` |
| Campaign dialer, retries, DNC | Campaign worker + Redis |
| Rolling summary jobs | Memory package |
| Retention (90 days) | Cron/scheduled worker |

### 4.3 Backend must NOT do

- Ship production HTML marketing (Next.js owns SEO pages)
- Expose secrets in JSON responses
- Trust client tier overrides in production `env` mode

---

## 5. Connecting Next.js (web) to API on Railway

### 5.1 Recommended — split public domains (simplest)

| Service | Domain example |
|---------|----------------|
| web | `https://app.yourdomain.com` |
| api | `https://api.yourdomain.com` |

Next.js env (web service):

```bash
NEXT_PUBLIC_API_BASE_URL=https://api.yourdomain.com
NEXT_PUBLIC_WS_BASE_URL=https://api.yourdomain.com
```

API CORS: allow `https://app.yourdomain.com` (+ staging/preview URLs).

Cookies: `SameSite=None; Secure` if cross-subdomain session, or shared parent domain strategy.

### 5.2 Alternative — Next.js rewrites (same browser origin)

In `web/next.config.ts`, proxy API and WS to internal Railway URL:

```typescript
async rewrites() {
  return [
    { source: '/api/:path*', destination: `${process.env.API_INTERNAL_URL}/api/:path*` },
  ];
}
```

WebSockets may still need explicit `wss://api...` URL from env (browser WS cannot always rewrite cleanly). Prefer **api subdomain** for WS.

### 5.3 Railway private networking

- `API_INTERNAL_URL` for server-side Next.js RSC fetches (server components calling API without public internet).
- Browser always uses public `NEXT_PUBLIC_*` URLs for WS and client-side fetch.

---

## 6. SEO requirements (normative)

Apply to **public** routes on the Next.js **web** service.

### 6.1 Metadata (every public page)

- Unique title (50–60 chars) and description (150–160 chars)
- `alternates.canonical`
- Open Graph + Twitter card
- `<html lang="te">` or appropriate locale

### 6.2 Technical SEO

| Item | Requirement |
|------|-------------|
| `robots.ts` | Allow `/`, `/pricing`, `/docs`; disallow `/dev`, `/app` |
| `sitemap.ts` | All public URLs with `lastmod` |
| JSON-LD | `Organization`, `SoftwareApplication` on landing |
| Status codes | Real 404/500 pages |
| hreflang | Prepare for `te`, `en`, `hi` |

### 6.3 Console routes

- `/dev/*`, `/app/*`: `robots: { index: false, follow: false }` in metadata

---

## 7. Performance requirements (normative)

### 7.1 Core Web Vitals (marketing, mobile)

| Metric | Target |
|--------|--------|
| LCP | ≤ 2.5 s |
| INP | ≤ 200 ms |
| CLS | ≤ 0.1 |

Measure: Lighthouse CI on PRs + production checks (Railway or external monitor).

### 7.2 Next.js performance rules

| Rule | Implementation |
|------|----------------|
| Code splitting | Route-level; `dynamic()` for live voice panel |
| Fonts | `next/font`, `display: swap` |
| Images | `next/image`, explicit dimensions |
| Scripts | Defer analytics; no blocking third-party in head |
| Data | Parallel fetches; Server Components for static console chrome |
| CSS | Tailwind purge |

### 7.3 Snappy console UX

- Route transitions ≤ 100 ms perceived (prefetch, `loading.tsx` skeletons)
- Paginated/virtualized tables for calls and campaigns

---

## 8. Railway project configuration

| Service | Settings |
|---------|----------|
| **web** | Root: `web/`; build: `npm run build`; start: `npm start` or Railway Next.js preset |
| **api** | Start: `uvicorn` on FastAPI app; health: `/api/health` |
| **worker** | Start: worker entrypoint; consumes Redis queue |
| **Env groups** | Shared: `DATABASE_URL`, `REDIS_URL`; API-only: provider secrets; Web-only: `NEXT_PUBLIC_*` |
| **Domains** | Custom domains per service in Railway dashboard |
| **Regions** | Align API region with primary users (e.g. South Asia) |

Local development:

- `web`: `npm run dev` (Next.js)
- `api`: `uvicorn` + local Postgres
- `docker-compose` optional for Postgres + Redis

---

## 9. Optional Vercel deployment (not default)

If you later move **only** the `web/` service to Vercel:

- Keep API/Worker/Postgres/Redis on Railway
- Set `NEXT_PUBLIC_API_BASE_URL` to Railway API URL
- Use `vercel-react-best-practices` + Vercel Analytics
- CORS and cookie rules from §5.1 apply

MVP ships on **Railway web + Railway api** unless explicitly changed.

---

## 10. Skills and tooling

| Task | Skills |
|------|--------|
| Next.js UI (all surfaces) | `web-mvp-design`, `frontend-design`, `ui-design` |
| Performance / bundles | **`vercel-react-best-practices`** (applies to Next.js regardless of host) |
| Composition patterns | `vercel-composition-patterns` |
| SEO / a11y audit | `web-design-guidelines` |
| Railway deploy (web + api + worker) | **`use-railway`** |
| API / voice pipeline | Context7 or official FastAPI/OpenAI docs |

---

## 11. Repository layout (target)

```text
voice-agent/
├── web/                    # Next.js → Railway WEB service (ONLY frontend)
│   ├── app/                # App Router
│   ├── components/
│   ├── lib/api/            # Typed clients to API service
│   └── next.config.ts
├── server/                 # Railway API service (FastAPI)
├── worker/                 # Railway Worker service
├── client/                 # DEPRECATED — reference only; do not extend
└── prd/
```

---

## 12. Acceptance criteria

- [ ] Production UI is **100% Next.js** in `web/` — no vanilla SPA deployed
- [ ] Railway project runs **web + api + worker + Postgres + Redis + bucket**
- [ ] Frontend/backend matrix (§3–4) with no responsibility leaks
- [ ] SEO checklist §6 on public pages
- [ ] Core Web Vitals targets met on production web URL
- [ ] Live voice E2E: Next.js → API WebSockets/SSE
- [ ] Barge-in parity with ported `live-guards` logic
- [ ] FastAPI no longer serves production `client/` static files
