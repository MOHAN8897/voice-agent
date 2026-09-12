# 12 — Codebase route map

App Router root: `web/app/`. API BFF routes live under `web/app/api/` and proxy to FastAPI.

## Marketing

| URL | File |
|-----|------|
| `/` | `web/app/(marketing)/page.tsx` |
| `/pricing` | `web/app/(marketing)/pricing/page.tsx` |
| `/docs` | `web/app/(marketing)/docs/page.tsx` |
| layout | `web/app/(marketing)/layout.tsx` |
| sitemap / robots | `web/app/sitemap.ts`, `robots.ts` |

## Business auth + console

| URL | File |
|-----|------|
| `/app/login` | `app/app/(auth)/login/page.tsx` |
| `/app/select-tenant` | `app/app/(auth)/select-tenant/page.tsx` |
| `/app/access-denied` | `app/app/(auth)/access-denied/page.tsx` |
| `/app` | `app/app/(console)/page.tsx` |
| `/app/agents` | `.../agents/page.tsx` |
| `/app/agents/[id]/summary` | `.../summary/page.tsx` |
| `/app/agents/[id]/brain` | `.../brain/page.tsx` |
| `/app/agents/[id]/voice` | `.../voice/page.tsx` |
| `/app/agents/[id]/memory-schema` | `.../memory-schema/page.tsx` |
| `/app/agents/[id]/tools` | `.../tools/page.tsx` |
| `/app/agents/[id]/channels` | `.../channels/page.tsx` |
| `/app/agents/[id]/versions` | `.../versions/page.tsx` |
| `/app/agents/[id]/test` | `.../test/page.tsx` |
| `/app/test-studio` | `.../test-studio/page.tsx` |
| `/app/test-studio/[agentId]` | `.../test-studio/[agentId]/page.tsx` |
| `/app/calls` | `.../calls/page.tsx` |
| `/app/calls/[id]` | `.../calls/[id]/page.tsx` |
| `/app/analytics` | `.../analytics/page.tsx` |
| `/app/benchmarks` | `.../benchmarks/page.tsx` |
| `/app/providers` | `.../providers/page.tsx` |
| `/app/integrations` | `.../integrations/page.tsx` |
| `/app/settings` | `.../settings/page.tsx` |
| `/app/profile` | `.../profile/page.tsx` |
| `/login` | `web/app/login/page.tsx` (keep as alias only) |

## Dev

| URL | File |
|-----|------|
| `/dev/login` | `app/dev/(auth)/login/page.tsx` |
| `/dev` | `app/dev/(portal)/page.tsx` |
| `/dev/environment` | `.../environment/page.tsx` |
| `/dev/stack` | `.../stack/page.tsx` |
| `/dev/runtime` | `.../runtime/page.tsx` |
| `/dev/platform-brain` | `.../platform-brain/page.tsx` |
| `/dev/compiled` | `.../compiled/page.tsx` |
| `/dev/providers` | `.../providers/page.tsx` |
| `/dev/agents` | `.../agents/page.tsx` |
| `/dev/agents/[id]/*` | summary, brain, voice, memory-schema, channels, tools, versions, test |
| `/dev/test-studio` | `.../test-studio/page.tsx` |
| `/dev/benchmarks` | `.../benchmarks/page.tsx` |
| `/dev/promotion` | `.../promotion/page.tsx` |

## Web API routes (Next)

| URL | File |
|-----|------|
| `/api/app/login` | via LoginForm (check `web/app/api`) |
| `/api/app/logout` | `web/app/api/app/logout/route.ts` |
| `/api/dev/logout` | `web/app/api/dev/logout/route.ts` |
| `/api/brain/stream` | `web/app/api/brain/stream/route.ts` |
| `/api/instructions` | `web/app/api/instructions/route.ts` |

Live STT/TTS WebSockets terminate on **FastAPI**, not Next (`prd/19`). Client connects to API origin.

## FastAPI surfaces the UI already consumes

Use `web/lib/api.ts` `apiGet` / portal fetch. Typical:

- `GET /api/health`, `GET /api/metrics`
- Auth session, login
- Agents CRUD, brain compile
- `GET /api/calls`, call detail, audio signed URL
- Catalog / providers (safe)
- Test Studio: `POST /api/call/start`, `/ws/stt-realtime`, brain stream, `/ws/tts`, `POST /api/call/end`

Exact contracts: [`prd/13-api-data-security-contracts.md`](../prd/13-api-data-security-contracts.md), [`architecture/integrations/nextjs-frontend-split.md`](../architecture/integrations/nextjs-frontend-split.md).

## Historical (do not extend)

`client/index.html`, `client/app.js`, `client/styles.css` — barge/live-voice reference only.

## Gaps to add as files later

- `web/app/(marketing)/legal/*/page.tsx`
- `web/app/app/(console)/billing/page.tsx`
- `web/app/app/(console)/campaigns/page.tsx`
- Onboarding route e.g. `web/app/app/(console)/setup/page.tsx`
