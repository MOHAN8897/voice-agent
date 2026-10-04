# Backend Scalability & Railway Deployment Architecture

**Status:** Testing on local machine → Deploy on Railway when ready  
**Goal:** Zero-surprise Railway deploy now, auto-scale gracefully as user base grows, minimal maintenance cost.

---

## TL;DR: Where You Are & What to Do

| Phase | Trigger | Action |
|---|---|---|
| **Now (local testing)** | — | Add `REDIS_URL`, bump DB pool, fix ephemeral disk |
| **First Railway deploy** | Any time | Follow §4 step-by-step |
| **~10+ concurrent calls** | Calls drop or queue times up | Split voice WebSocket to its own Railway service |
| **~100+ tenants** | DB query times creep up | Add PgBouncer + read replica |
| **Sustained high load** | CPU/RAM alerts firing | Horizontal scaling + autoscale config |

You do not need to over-engineer today. The changes in **Phase 1** below take under an hour and make the Railway deploy solid from day one.

---

## 1. Current Codebase Architecture (What You Have)

### 1.1 Single-Process Monolith

The backend is a single FastAPI process defined in [server/app.py](file:///d:/voice%20agent/server/app.py). On startup it:
- Connects to PostgreSQL ([server/db/connection.py:43](file:///d:/voice%20agent/server/db/connection.py#L43))
- Starts an in-process `_provision_worker_loop()` asyncio task ([server/app.py:186-207](file:///d:/voice%20agent/server/app.py#L186-L207))
- Registers all 30+ HTTP & WebSocket routes from `server/routes/`

On Railway this single process handles everything: REST API, authentication, billing, Telnyx/Exotel WebSockets, realtime audio loops, and post-call analytics. That's fine for launch. The problems only appear when you add replicas.

### 1.2 What Already Works Well (Don't Change)

| Component | File | Status |
|---|---|---|
| Redis-optional token store | [server/services/telnyx_client.py:582](file:///d:/voice%20agent/server/services/telnyx_client.py#L582) | ✅ Falls back to in-memory; uses Redis when `REDIS_URL` set |
| Redis-optional memory cache | [server/call/redis_memory_cache.py](file:///d:/voice%20agent/server/call/redis_memory_cache.py) | ✅ Falls back to Postgres; uses Redis when available |
| Async SQLAlchemy + asyncpg | [pyproject.toml:17-18](file:///d:/voice%20agent/pyproject.toml#L17-L18) | ✅ Correct async drivers already in place |
| Alembic migrations (29 versions) | [server/db/migrations/versions/](file:///d:/voice%20agent/server/db/migrations/versions/) | ✅ Schema managed properly |
| Worker process | [worker/main.py](file:///d:/voice%20agent/worker/main.py) + [Dockerfile.worker](file:///d:/voice%20agent/Dockerfile.worker) | ✅ Separate process, deployable separately |
| Multi-service railway.json | [railway.json](file:///d:/voice%20agent/railway.json) | ✅ Already defines `web`, `api`, `worker` |
| Docker files | [Dockerfile.api](file:///d:/voice%20agent/Dockerfile.api), [Dockerfile.worker](file:///d:/voice%20agent/Dockerfile.worker) | ✅ Exist, need minor hardening |

### 1.3 The 4 Real Bottlenecks (Ranked by Impact)

#### Bottleneck A: Database Pool Too Small  
**File:** [server/db/connection.py:43](file:///d:/voice%20agent/server/db/connection.py#L43)  
```python
# Current — will fail under ~15 concurrent requests
_engine = create_async_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)
```
Each active call uses 2–4 DB connections (wallet check, ledger write, state update). At 10 concurrent calls + 5 dashboard users = easily 35+ concurrent connections. Pool exhausts → `TimeoutError: QueuePool limit reached`.  
**Fix:** Single line change, shown in §2.1.

#### Bottleneck B: Stream Tokens Fragmented Across Replicas  
**File:** [server/services/telnyx_client.py:594](file:///d:/voice%20agent/server/services/telnyx_client.py#L594)  
```python
self._tokens: dict[str, dict[str, Any]] = {}  # In-memory dict
```
The code already supports Redis (lines 596–641), but **only if `REDIS_URL` is set**. On a single Railway instance with one replica, this is fine. The moment you add a second replica (to handle more load), Telnyx webhook hits Replica A, stores the token there, then the media WebSocket hits Replica B — which has no token and closes with `1008`.  
**Fix:** Set `REDIS_URL` in Railway environment variables before going to 2 replicas.

#### Bottleneck C: Call Data on Ephemeral Disk  
**File:** [server/call/paths.py](file:///d:/voice%20agent/server/call/paths.py)  
```python
def calls_root() -> Path:
    root = get_settings().data_path / "calls"   # writes to container disk
```
All call recordings (WAV), outcome JSONs, and ledger files are written to `data/calls/{call_id}/` inside the container. On Railway, every deployment wipes this disk. You lose every call recording and outcome.  
**Fix:** Add Cloudflare R2 upload after archive finalization (shown in §3).

#### Bottleneck D: Post-Call Queue is In-Memory  
**File:** [server/call/post_call_pipeline.py:28](file:///d:/voice%20agent/server/call/post_call_pipeline.py#L28)  
```python
_QUEUE: asyncio.Queue[tuple[str, bool]] = asyncio.Queue()
_WORKER: asyncio.Task | None = None
```
If the server restarts mid-queue (e.g. during a Railway deployment), all pending post-call analysis, transcript generation, and outcome extraction jobs are silently lost.  
**Fix:** Persist queue jobs to Redis or DB before processing (shown in §2.3).

---

## 2. Phase 1 Fixes — Do These Before First Railway Deploy

These are small, safe changes you can make now on your local machine and push. They make your single-instance Railway deploy bulletproof.

### 2.1 Increase DB Pool Size

**File:** [server/db/connection.py](file:///d:/voice%20agent/server/db/connection.py) — change line 43:

```python
# Before:
_engine = create_async_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)

# After (handles 40+ concurrent connections per replica, Railway Hobby plan):
_engine = create_async_engine(
    url,
    pool_pre_ping=True,
    pool_size=15,       # Keep 15 warm connections alive
    max_overflow=15,    # Allow burst to 30 total
    pool_timeout=20.0,  # Fail fast instead of hanging
    pool_recycle=1800,  # Recycle connections every 30 min (avoids firewall drops)
)
```

> [!NOTE]
> On Railway Hobby with a single replica, 30 connections is well within Supabase free tier (100 limit) and Railway Postgres (100 limit). If you later add a second replica without PgBouncer, set `pool_size=10` so 2 replicas × 20 = 40 total, still safe.

### 2.2 Add Redis URL Startup Enforcement

In [server/app.py:94-98](file:///d:/voice%20agent/server/app.py#L94-L98) the server already warns about missing `REDIS_URL`. To make it actionable in your Railway env variable list, ensure the following are always set when `APP_ENVIRONMENT=production`:

**Required Railway Environment Variables:**
```bash
APP_ENVIRONMENT=production
SESSION_SECRET=<random-64-char-hex>
JWT_SECRET=<random-64-char-hex>
REDIS_URL=${{Redis.REDIS_URL}}          # Railway private networking — auto-filled
DATABASE_URL=${{Postgres.DATABASE_URL}} # Railway private networking — auto-filled
```

The application already reads `REDIS_URL` and uses Redis for:
- Stream token storage ([server/services/telnyx_client.py:610](file:///d:/voice%20agent/server/services/telnyx_client.py#L610))
- Working memory cache ([server/call/redis_memory_cache.py:60](file:///d:/voice%20agent/server/call/redis_memory_cache.py#L60))

You get multi-replica safety for free just by setting this env var.

### 2.3 Persist Post-Call Jobs Before In-Memory Queue

Add job persistence to [server/call/post_call_pipeline.py:60](file:///d:/voice%20agent/server/call/post_call_pipeline.py#L60). When a call ends, write the pending job to the `calls` table before enqueuing in memory:

```python
# In enqueue() function, before putting into _QUEUE:
async def enqueue(call_id: str, *, force: bool = False) -> None:
    # ADDED: Persist job intent to DB so we can recover after restart
    try:
        from server.db.session import get_session
        async with get_session() as db:
            await db.execute(
                text("UPDATE calls SET post_call_status='pending' WHERE id=:id"),
                {"id": call_id}
            )
            await db.commit()
    except Exception:
        pass  # Best-effort; in-memory queue still catches it this session
    
    await _QUEUE.put((call_id, force))
```

Add a recovery call in the lifespan startup (already exists in [server/app.py:145-151](file:///d:/voice%20agent/server/app.py#L145-L151) for stale calls) to re-enqueue any `post_call_status='pending'` rows after restart.

### 2.4 Add `uvloop` for 20-30% Async Throughput Gain

Add to [pyproject.toml](file:///d:/voice%20agent/pyproject.toml):
```toml
dependencies = [
    ...
    "uvloop>=0.21; sys_platform != 'win32'",  # Faster event loop on Linux (Railway)
]
```

Update [Dockerfile.api](file:///d:/voice%20agent/Dockerfile.api) start command:
```dockerfile
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8000} --loop uvloop --no-access-log"]
```
`uvloop` replaces Python's default asyncio event loop with a C-extension based loop. 20-30% faster I/O on Railway's Linux containers with no code changes.

### 2.5 Harden the Existing Dockerfiles

**[Dockerfile.api](file:///d:/voice%20agent/Dockerfile.api)** — replace entirely:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system deps (needed for audioop, asyncpg C extension)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies first (Docker layer cache)
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e ".[dev]" && pip install uvloop

# Copy application source
COPY server ./server
COPY scripts ./scripts

ENV PORT=8000
EXPOSE 8000

# Run DB migration then start server (idempotent, safe on every deploy)
CMD ["sh", "-c", "python -m alembic -c alembic.ini upgrade head && uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8000} --loop uvloop --no-access-log"]
```

> [!IMPORTANT]
> The `alembic upgrade head` in the CMD ensures every Railway deploy automatically applies new database migrations before traffic arrives. It's idempotent — safe to run on every boot.

---

## 3. Cloudflare R2 Storage (Zero Egress Fees)

Your `.env` already has Cloudflare credentials. R2 gives you S3-compatible object storage with **$0 egress** — you never pay for tenants downloading call recordings.

### 3.1 Add R2 Env Variables

Add to Railway environment variables:
```bash
R2_ACCESS_KEY_ID=<from Cloudflare R2 API Tokens>
R2_SECRET_ACCESS_KEY=<from Cloudflare R2 API Tokens>
R2_BUCKET_NAME=voxly-call-archives
R2_ACCOUNT_ID=<your cloudflare account id from .env>
```

Add to [server/config/env.py](file:///d:/voice%20agent/server/config/env.py) `Settings` class:
```python
# --- Cloudflare R2 object storage ---
r2_account_id: str | None = Field(None, alias="R2_ACCOUNT_ID")
r2_access_key_id: str | None = Field(None, alias="R2_ACCESS_KEY_ID")
r2_secret_access_key: str | None = Field(None, alias="R2_SECRET_ACCESS_KEY")
r2_bucket_name: str = Field("voxly-call-archives", alias="R2_BUCKET_NAME")
```

Add `aioboto3>=12.0` to [pyproject.toml](file:///d:/voice%20agent/pyproject.toml) dependencies.

### 3.2 R2 Storage Service ([server/services/r2_storage.py](file:///d:/voice%20agent/server/services/r2_storage.py))

```python
"""Cloudflare R2 object storage — zero egress fees, S3-compatible."""
from __future__ import annotations

import json
from typing import Any

from server.config.env import get_settings
from server.utils.logger import logger


class R2StorageService:
    def __init__(self) -> None:
        self._session = None

    def _is_configured(self) -> bool:
        s = get_settings()
        return bool(s.r2_access_key_id and s.r2_secret_access_key and s.r2_account_id)

    def _client_kwargs(self) -> dict[str, Any]:
        s = get_settings()
        return {
            "service_name": "s3",
            "endpoint_url": f"https://{s.r2_account_id}.r2.cloudflarestorage.com",
            "aws_access_key_id": s.r2_access_key_id,
            "aws_secret_access_key": s.r2_secret_access_key,
            "region_name": "auto",
        }

    async def upload_audio(self, call_id: str, audio_bytes: bytes, fmt: str = "wav") -> str | None:
        """Upload call recording. Returns R2 key or None if R2 not configured."""
        if not self._is_configured() or not audio_bytes:
            return None
        try:
            import aioboto3
            key = f"calls/{call_id}/recording.{fmt}"
            session = aioboto3.Session()
            async with session.client(**self._client_kwargs()) as s3:
                await s3.put_object(
                    Bucket=get_settings().r2_bucket_name,
                    Key=key,
                    Body=audio_bytes,
                    ContentType=f"audio/{fmt}",
                )
            logger.info("[R2] Uploaded audio for call %s (%d bytes)", call_id, len(audio_bytes))
            return key
        except Exception as exc:
            logger.warning("[R2] Audio upload failed for %s: %s", call_id, exc)
            return None

    async def upload_outcome(self, call_id: str, outcome: dict[str, Any]) -> str | None:
        """Upload outcome JSON to R2."""
        if not self._is_configured():
            return None
        try:
            import aioboto3
            key = f"calls/{call_id}/outcome.json"
            body = json.dumps(outcome, ensure_ascii=False, indent=2).encode()
            session = aioboto3.Session()
            async with session.client(**self._client_kwargs()) as s3:
                await s3.put_object(
                    Bucket=get_settings().r2_bucket_name,
                    Key=key,
                    Body=body,
                    ContentType="application/json",
                )
            return key
        except Exception as exc:
            logger.warning("[R2] Outcome upload failed for %s: %s", call_id, exc)
            return None

    async def presigned_url(self, key: str, expires_in: int = 3600) -> str | None:
        """Generate a pre-signed download URL for dashboard audio playback."""
        if not self._is_configured():
            return None
        try:
            import aioboto3
            session = aioboto3.Session()
            async with session.client(**self._client_kwargs()) as s3:
                return await s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": get_settings().r2_bucket_name, "Key": key},
                    ExpiresIn=expires_in,
                )
        except Exception:
            return None


r2_storage = R2StorageService()
```

### 3.3 Hook R2 Into Audio Archive

In [server/call/audio_archive.py](file:///d:/voice%20agent/server/call/audio_archive.py), at the end of the function that writes the final WAV to disk, add an async R2 upload:

```python
# After the existing local disk write:
from server.services.r2_storage import r2_storage
asyncio.create_task(r2_storage.upload_audio(call_id, wav_bytes, "wav"))
```

This is fire-and-forget — it doesn't block the voice call teardown and gracefully does nothing if R2 isn't configured.

---

## 4. Railway Deployment — Step-by-Step

### 4.1 Update [railway.json](file:///d:/voice%20agent/railway.json)

Replace with this production-ready config:

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "services": {
    "api": {
      "rootDirectory": ".",
      "dockerfilePath": "Dockerfile.api",
      "healthcheckPath": "/api/health",
      "healthcheckTimeout": 60,
      "sleepApplication": false
    },
    "worker": {
      "rootDirectory": ".",
      "dockerfilePath": "Dockerfile.worker"
    }
  }
}
```

> [!NOTE]
> `sleepApplication: false` for the `api` service prevents Railway from putting the voice backend to sleep during low traffic periods. Sleep-to-zero causes unacceptable cold start delays for telephony webhooks. The `worker` service CAN sleep — it will auto-restart when new jobs arrive.

### 4.2 Add Required Services in Railway Dashboard

In your Railway project, add these managed services:
1. **PostgreSQL** — Railway managed Postgres. Automatically sets `DATABASE_URL`.
2. **Redis** — Railway managed Redis. Automatically sets `REDIS_URL`.

Link them to your `api` service using Railway's **Reference Variables**: `${{Postgres.DATABASE_URL}}` and `${{Redis.REDIS_URL}}`.

### 4.3 Environment Variables Checklist

Set these in Railway Dashboard → api service → Variables:

```bash
# Core
APP_ENVIRONMENT=production
PORT=8000  # Railway injects this automatically but explicit is safer

# Database (Railway auto-provides if you add Postgres service)
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Redis (Railway auto-provides if you add Redis service)
REDIS_URL=${{Redis.REDIS_URL}}

# Security (generate unique values — never reuse dev secrets)
SESSION_SECRET=<64-char random hex>
JWT_SECRET=<64-char random hex>

# Cloudflare R2 (optional but strongly recommended)
R2_ACCOUNT_ID=<your account id>
R2_ACCESS_KEY_ID=<r2 api key id>
R2_SECRET_ACCESS_KEY=<r2 api secret>
R2_BUCKET_NAME=voxly-call-archives

# App config
SAAS_AUTH_ENABLED=true
PUBLIC_APP_URL=https://<your-railway-domain>.up.railway.app
CORS_ORIGINS=https://<your-railway-domain>.up.railway.app,https://<your-vite-frontend>.up.railway.app

# All your AI API keys
OPENAI_API_KEY=<key>
SARVAM_API_KEY=<key>
# ... etc, same as .env but through Railway Variables (never committed to git)
```

### 4.4 Deploy Commands

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link to your project
railway link

# Deploy (triggers Docker build + deploy from current git branch)
railway up
```

### 4.5 Verify Deployment

```bash
# Check health
curl https://<your-domain>.up.railway.app/api/health

# Watch logs in real time
railway logs --follow

# Check DB connection
curl https://<your-domain>.up.railway.app/api/health | jq .database
```

---

## 5. When to Scale: Decision Thresholds

### 5.1 Stay on Single Replica Until

| Metric | Threshold to Act |
|---|---|
| Concurrent active calls | < 15 |
| Railway CPU usage | < 70% sustained |
| Railway memory | < 80% of plan limit |
| DB connection wait time | < 100ms (from health endpoint) |
| API p95 response time | < 500ms |

Monitor these in the Railway dashboard. At this scale the monolith is perfectly adequate and cheapest.

### 5.2 Add Second Replica When Any Threshold Is Hit

When you go to 2+ replicas, the only change required is:
1. `REDIS_URL` is already set (done in §2.2) — so stream tokens work across replicas ✅
2. Set `pool_size=10` (so 2 replicas × 20 connections = 40 total, within limits) ✅

Railway makes horizontal scaling a slider in the dashboard. No code changes needed because the Redis integration is already implemented.

### 5.3 Separate Voice WebSocket Service at ~30+ Concurrent Calls

When you consistently run 30+ simultaneous phone calls, the voice WebSocket connections compete with REST API traffic on the event loop. At this point:

1. Create a second Railway service pointing to a `Dockerfile.voice` with only the voice routes:
```dockerfile
CMD ["sh", "-c", "uvicorn server.voice_app:app --host 0.0.0.0 --port ${PORT:-8000} --loop uvloop --ws-ping-interval 15 --ws-ping-timeout 30"]
```

2. Create `server/voice_app.py` that only registers the WebSocket routes:
```python
from fastapi import FastAPI
from server.routes.telnyx_ws import router as telnyx_ws_router
from server.routes.exotel_ws import router as exotel_ws_router  
from server.routes.web_agent_ws import router as web_agent_ws_router

app = FastAPI()
app.include_router(telnyx_ws_router)
app.include_router(exotel_ws_router)
app.include_router(web_agent_ws_router)
```

This lets voice WebSocket workers scale independently from the REST API, and prevents a large analytics query from causing audio jitter.

---

## 6. Database Scaling Path

### 6.1 Current — Single Postgres Instance

Adequate for: < 1,000 tenants, < 50 concurrent calls.

Railway Postgres starts at $5/month and scales on demand. The async SQLAlchemy pool in [server/db/connection.py](file:///d:/voice%20agent/server/db/connection.py) is already correct for this tier.

### 6.2 When Traffic Grows — Add PgBouncer

PgBouncer acts as a connection proxy that allows hundreds of application connections while maintaining only a small pool of actual Postgres connections:

```
100 Uvicorn workers → PgBouncer (transaction mode) → 25 real Postgres connections
```

**Railway setup:**
- Deploy PgBouncer as a separate Railway service using the `edoburu/pgbouncer` image.
- Set `DATABASE_URL` in your api service to point to PgBouncer's internal Railway URL.
- Postgres connection string goes into PgBouncer's config.
- `pool_mode = transaction` (best for FastAPI async workloads).

### 6.3 Heavy Analytics — Add Read Replica

When tenant dashboard analytics (call history, billing, campaign results) start competing with live voice write operations:
1. Add a Postgres read replica (available on Railway Pro).
2. Route read-only queries (analytics, reporting) to the replica.
3. Route all writes (call state, billing ledger) to primary.

---

## 7. Cost Optimization Summary

### 7.1 Monthly Cost Comparison

| Component | Without Optimization | With This Architecture | Savings |
|---|---|---|---|
| **Server** | 1× large instance, always on | Railway: pay-per-second, right-sized | ~60% |
| **Call recordings** | Disk storage lost on restart | Cloudflare R2: $0.015/GB, $0 egress | No data loss |
| **Redis** | Not used (fragile) | Railway Redis: ~$5/mo | Bug prevention |
| **Database** | Small pool, crashes | Railway Postgres + tuned pool: ~$15/mo | Stability |
| **Total (launch)** | Broken at 2 replicas | ~$25/mo, scales to 100s of calls | Correct |

### 7.2 Cost-Control Tips for Railway

1. **Scale to zero for staging/dev:** Set minimum replicas = 0 on your staging environment. Railway bills per-second, so idle staging = $0.
2. **Worker service can sleep:** The `worker` service (campaign dialer, post-call retries) can scale-to-zero since jobs aren't time-critical to the millisecond.
3. **Use private networking:** Ensure `DATABASE_URL` and `REDIS_URL` use Railway's internal hostnames (not public URLs) to avoid external egress fees and reduce latency.
4. **Cache aggressively:** The Redis working memory cache ([server/call/redis_memory_cache.py](file:///d:/voice%20agent/server/call/redis_memory_cache.py)) is already implemented — it reduces Postgres reads significantly during active calls.

---

## 8. Production Readiness Checklist

### Before First Railway Deploy
- [ ] Bump DB pool size in [server/db/connection.py:43](file:///d:/voice%20agent/server/db/connection.py#L43): `pool_size=15, max_overflow=15`
- [ ] Add `REDIS_URL` to Railway Variables (link to Railway Redis service)
- [ ] Generate fresh `SESSION_SECRET` and `JWT_SECRET` (64-char random hex each)
- [ ] Set `APP_ENVIRONMENT=production` in Railway Variables
- [ ] Add `uvloop` to [pyproject.toml](file:///d:/voice%20agent/pyproject.toml) dependencies
- [ ] Update [Dockerfile.api](file:///d:/voice%20agent/Dockerfile.api) CMD to include `alembic upgrade head &&` prefix
- [ ] Set `PUBLIC_APP_URL` and `CORS_ORIGINS` to production domain

### Before Going Multi-Replica
- [ ] Verify `REDIS_URL` is set and Redis health check passes (`/api/health`)
- [ ] Confirm Telnyx stream tokens are stored in Redis (check logs for `[TELNYX] stream token redis mirror`)
- [ ] Set `pool_size=10` (single replica: 15, two replicas: 10 each)
- [ ] Configure Cloudflare R2 so call data persists across deploys

### Before Handling High Volume (100+ tenants)
- [ ] Deploy `Dockerfile.worker` as its own Railway service
- [ ] Set up call recording uploads to Cloudflare R2 ([server/services/r2_storage.py](file:///d:/voice%20agent/server/services/r2_storage.py))
- [ ] Add PgBouncer if p95 DB query time > 100ms
- [ ] Consider splitting voice WebSocket routes to dedicated service

---

## 9. Quick Reference: Key Files

| What | File |
|---|---|
| DB pool config | [server/db/connection.py:43](file:///d:/voice%20agent/server/db/connection.py#L43) |
| Redis memory cache | [server/call/redis_memory_cache.py](file:///d:/voice%20agent/server/call/redis_memory_cache.py) |
| Stream token storage | [server/services/telnyx_client.py:582](file:///d:/voice%20agent/server/services/telnyx_client.py#L582) |
| Post-call queue | [server/call/post_call_pipeline.py:28](file:///d:/voice%20agent/server/call/post_call_pipeline.py#L28) |
| Audio archive (disk) | [server/call/audio_archive.py](file:///d:/voice%20agent/server/call/audio_archive.py) |
| Call file paths | [server/call/paths.py](file:///d:/voice%20agent/server/call/paths.py) |
| App startup/lifespan | [server/app.py:71](file:///d:/voice%20agent/server/app.py#L71) |
| Env settings | [server/config/env.py](file:///d:/voice%20agent/server/config/env.py) |
| Railway config | [railway.json](file:///d:/voice%20agent/railway.json) |
| Docker (api) | [Dockerfile.api](file:///d:/voice%20agent/Dockerfile.api) |
| Docker (worker) | [Dockerfile.worker](file:///d:/voice%20agent/Dockerfile.worker) |
| DB migrations | [server/db/migrations/versions/](file:///d:/voice%20agent/server/db/migrations/versions/) |
