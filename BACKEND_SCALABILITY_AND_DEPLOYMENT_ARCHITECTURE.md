# Backend Scalability & Railway Deployment Architecture

**Status:** Testing on local machine → Deploying on Railway  
**Target:** Zero-surprise Railway deploy now, measured auto-scaling driven by operational metrics, durable background execution, and minimal maintenance cost.

---

## Architecture Roadmap at a Glance

The architecture is divided into three distinct operational stages to prevent mixing immediate fixes with future scale:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. CURRENT (Today's Codebase)                                               │
│    FastAPI Monolith + In-Memory Queue + Ephemeral Disk + Hardcoded DB Pool  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. PHASE 1: SHIP-READY TO RAILWAY (Immediate - Low Friction)                 │
│    • Env-configurable DB pool (small baseline)                             │
│    • REDIS_URL wired for tokens & working memory                           │
│    • Durable post-call job state in DB + restart recovery                   │
│    • Durable R2 upload workflow (staged → verified → finalized)             │
│    • Always-on Worker & API in railway.json (no sleep-to-zero queue stalls) │
│    • Dockerfile migration automation (idempotent alembic upgrade)           │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼ [Triggered by Telemetry & Load Benchmarks]
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. LATER: MEASURED SCALE (High Volume Growth)                                │
│    • Distributed Redis/ARQ Worker with formal Job Schema & Composio retries  │
│    • VOICE_GATEWAY_SAFE_CONCURRENCY load-tested threshold                   │
│    • Dedicated Voice WebSocket Service (isolate telephony event loop)       │
│    • Metric-driven DB scaling: PgBouncer (conn saturation) & Read Replicas  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. CURRENT: What Exists in the Codebase Today

A factual audit of the current repository:

### 1.1 Single-Process FastAPI Monolith
The backend runs as a single FastAPI instance defined in [server/app.py](file:///d:/voice%20agent/server/app.py). On startup, the lifespan handler:
- Connects to PostgreSQL via SQLAlchemy async engine ([server/db/connection.py:43](file:///d:/voice%20agent/server/db/connection.py#L43)).
- Spawns an in-process provisioning worker task `_provision_worker_loop()` ([server/app.py:186-207](file:///d:/voice%20agent/server/app.py#L186-L207)).
- Serves all REST APIs, authentication, billing, WebSockets (Telnyx, Exotel, Web Agent), and post-call analysis in the same Python process.

### 1.2 Existing Strengths (Do Not Break)
- **Redis-Optional Token Store:** [server/services/telnyx_client.py:582-641](file:///d:/voice%20agent/server/services/telnyx_client.py#L582-L641) automatically switches from in-memory dictionary to Redis when `REDIS_URL` is set.
- **Redis Working Memory Cache:** [server/call/redis_memory_cache.py](file:///d:/voice%20agent/server/call/redis_memory_cache.py) transparently falls back to Postgres if Redis is absent.
- **Async Database Stack:** Uses `asyncpg>=0.30` and `sqlalchemy[asyncio]>=2.0` ([pyproject.toml:17-18](file:///d:/voice%20agent/pyproject.toml#L17-L18)).
- **Alembic Migrations:** 29 curated migration versions in [server/db/migrations/versions/](file:///d:/voice%20agent/server/db/migrations/versions/).
- **Worker Process:** [worker/main.py](file:///d:/voice%20agent/worker/main.py) and [Dockerfile.worker](file:///d:/voice%20agent/Dockerfile.worker) exist as a separate runnable container running `worker.dialer.run_loop()`.

### 1.3 Identified Limitations in Current Code

| Issue | Current Code | Failure Mode |
|---|---|---|
| **Hardcoded Small Pool** | [server/db/connection.py:43](file:///d:/voice%20agent/server/db/connection.py#L43) (`pool_size=5, max_overflow=10`) | Cannot be tuned per environment without code edits. Exhausts under burst. |
| **In-Memory Queue** | [server/call/post_call_pipeline.py:28](file:///d:/voice%20agent/server/call/post_call_pipeline.py#L28) (`asyncio.Queue`) | Container restart or redeploy causes all queued post-call jobs to be dropped. |
| **Ephemeral Local Storage** | [server/call/paths.py](file:///d:/voice%20agent/server/call/paths.py) (`data/calls/{call_id}/`) | Railway container restarts wipe local disks, losing audio recordings and artifacts. |
| **Fire-and-Forget Uploads** | No persistent upload ledger | Any async task spawned at call tear-down terminates if the container recycles. |

---

## 2. PHASE 1: Immediate Ship-Ready Fixes

These changes prepare the codebase for a bulletproof, reliable deployment on Railway without requiring complex infrastructure rewrites.

---

### 2.1 Configurable Database Connection Pool

#### The Problem with Hardcoding
Hardcoding connection parameters like `pool_size=15, max_overflow=15` is dangerous. When scaling horizontally across replicas:
$$\text{Max DB Connections} = N_{\text{replicas}} \times (\text{pool\_size} + \text{max\_overflow})$$
3 API replicas with $15 + 15$ would demand up to 90 simultaneous connections, immediately exhausting managed database connection limits (e.g. Supabase free/micro or Railway Postgres limits).

#### The Fix: Configuration via Environment Variables
Make pool parameters configurable through `server/config/env.py` with conservative, safe defaults:

```python
# In server/config/env.py Settings:
db_pool_size: int = Field(5, alias="DB_POOL_SIZE")
db_max_overflow: int = Field(5, alias="DB_MAX_OVERFLOW")
db_pool_timeout: float = Field(20.0, alias="DB_POOL_TIMEOUT")
db_pool_recycle: int = Field(1800, alias="DB_POOL_RECYCLE")
```

Update [server/db/connection.py](file:///d:/voice%20agent/server/db/connection.py):
```python
# server/db/connection.py
async def init_db() -> bool:
    global _engine, _session_factory
    settings = get_settings()
    if not settings.database_url:
        return False
    url = _to_async_url(settings.database_url)
    _engine = create_async_engine(
        url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return True
```

#### Sizing Guidelines
- **Development / Local:** `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=5`
- **Small Production (Single Replica):** `DB_POOL_SIZE=5` to `10`, `DB_MAX_OVERFLOW=5` to `10`
- **Multi-Replica (2–3 Replicas):** Keep `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=5`. Increase **only after measuring** real connection pool saturation through database telemetry.

---

### 2.2 Wire Redis for Multi-Replica Safety

The code already supports Redis:
- Telnyx stream tokens: [server/services/telnyx_client.py:596-641](file:///d:/voice%20agent/server/services/telnyx_client.py#L596-L641)
- Working memory cache: [server/call/redis_memory_cache.py:60](file:///d:/voice%20agent/server/call/redis_memory_cache.py#L60)

When deploying to Railway:
1. Add a managed **Redis** service to your Railway project.
2. Link `REDIS_URL=${{Redis.REDIS_URL}}` in the `api` service environment variables.
3. This eliminates session fragmentation where Replica A receives a webhook and stores the token in memory, while Replica B receives the incoming media WebSocket and rejects it.

---

### 2.3 Durable Post-Call Job State & Recovery

#### Why Naive In-Memory Queues Fail
An `asyncio.Queue` only exists in memory. If code is redeployed while 5 calls are being summarized or dispatched to webhooks, those 5 tasks vanish.

#### Phase 1 Solution: Durable DB Intent + Startup Reconciliation
Before handing a post-call job to the pipeline, record its pending status durably:

```python
# server/call/post_call_pipeline.py
async def enqueue(call_id: str, *, force: bool = False) -> None:
    """Durably record pending status before enqueuing."""
    try:
        from server.db.session import get_session
        from sqlalchemy import text
        async with get_session() as db:
            await db.execute(
                text("UPDATE calls SET post_call_status = 'pending', updated_at = NOW() WHERE id = :id"),
                {"id": call_id}
            )
            await db.commit()
    except Exception as exc:
        logger.warning("[POST_CALL] Failed to record pending status for %s: %s", call_id, exc)
    
    await _QUEUE.put((call_id, force))
    _ensure_worker()
```

During application startup in `server/app.py` lifespan:
```python
# In server/app.py lifespan startup:
async def _reconcile_pending_post_calls():
    """Find any calls stuck in 'pending' from a previous crash/deploy and re-queue."""
    from server.db.session import get_session
    from server.call.post_call_pipeline import enqueue
    from sqlalchemy import text
    try:
        async with get_session() as db:
            rows = await db.execute(
                text("SELECT id FROM calls WHERE post_call_status = 'pending' ORDER BY created_at ASC LIMIT 100")
            )
            for row in rows:
                logger.info("[STARTUP] Resuming pending post-call analysis for %s", row[0])
                await enqueue(str(row[0]), force=True)
    except Exception as exc:
        logger.warning("[STARTUP] Post-call reconciliation failed: %s", exc)
```

---

### 2.4 Durable Cloudflare R2 Upload Workflow (No Fire-and-Forget)

#### The Risk of Fire-and-Forget
Spawning `asyncio.create_task(r2_storage.upload_audio(...))` at the end of a call creates an orphan task. If the container shuts down or restarts for a deploy, the task dies mid-upload, leaving recordings permanently missing.

#### The Durable R2 Workflow
```
Call Ends
   ↓
Finalize local audio file to disk (staged locally)
   ↓
Record durable upload intent in DB (recording_status='pending_upload')
   ↓
Worker/Task executes upload with exponential retry
   ↓
Verify upload success (check HTTP ETag / object size via S3 HeadObject)
   ↓
Update DB (recording_url=r2_key, recording_status='uploaded')
   ↓
Safely delete temporary local file
```

#### R2 Storage Service Implementation ([server/services/r2_storage.py](file:///d:/voice%20agent/server/services/r2_storage.py))

```python
"""Cloudflare R2 object storage — zero egress fees, S3-compatible."""
from __future__ import annotations

import json
from typing import Any
from server.config.env import get_settings
from server.utils.logger import logger


class R2StorageService:
    def __init__(self) -> None:
        pass

    def is_configured(self) -> bool:
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

    async def upload_audio_file(self, call_id: str, file_path: str, fmt: str = "wav") -> str | None:
        """Upload audio from disk, verify receipt, and return storage key."""
        if not self.is_configured():
            return None
        import aioboto3
        from pathlib import Path
        
        path = Path(file_path)
        if not path.exists() or path.stat().st_size == 0:
            logger.warning("[R2] File %s empty or missing for call %s", file_path, call_id)
            return None

        key = f"calls/{call_id}/recording.{fmt}"
        session = aioboto3.Session()
        bucket = get_settings().r2_bucket_name
        file_bytes = path.read_bytes()

        try:
            async with session.client(**self._client_kwargs()) as s3:
                # 1. Put object
                await s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=file_bytes,
                    ContentType=f"audio/{fmt}",
                )
                # 2. Verify existence and byte size
                head = await s3.head_object(Bucket=bucket, Key=key)
                if head.get("ContentLength") != len(file_bytes):
                    raise IOError("Uploaded R2 size does not match local file size")

            logger.info("[R2] Verified upload for %s (%d bytes) -> %s", call_id, len(file_bytes), key)
            return key
        except Exception as exc:
            logger.error("[R2] Upload failed for call %s: %s", call_id, exc)
            raise

    async def presigned_url(self, key: str, expires_in: int = 3600) -> str | None:
        """Generate a pre-signed download URL for audio playback in the dashboard."""
        if not self.is_configured():
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
        except Exception as exc:
            logger.warning("[R2] Presigned URL failed for %s: %s", key, exc)
            return None


r2_storage = R2StorageService()
```

---

### 2.5 High-Throughput Event Loop (`uvloop`)
Python’s standard `asyncio` event loop has measurable scheduling latency under concurrent audio streaming. `uvloop` is a drop-in replacement built on `libuv` (the engine powering Node.js) providing 20–30% lower event-loop scheduling latency on Linux:

In [pyproject.toml](file:///d:/voice%20agent/pyproject.toml):
```toml
dependencies = [
    ...
    "uvloop>=0.21; sys_platform != 'win32'",
    "aioboto3>=12.0",
]
```

In `Dockerfile.api`:
```dockerfile
CMD ["sh", "-c", "python -m alembic -c alembic.ini upgrade head && uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8000} --loop uvloop --no-access-log"]
```

---

### 2.6 Hardened Dockerfile with Automated Idempotent Migrations

Update [Dockerfile.api](file:///d:/voice%20agent/Dockerfile.api):
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies needed for asyncpg and audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Cache dependencies
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e ".[dev]"

# Copy source trees
COPY server ./server
COPY scripts ./scripts
COPY alembic.ini ./
COPY worker ./worker

ENV PORT=8000
EXPOSE 8000

# Run Alembic migrations idempotently prior to launching Uvicorn
CMD ["sh", "-c", "python -m alembic -c alembic.ini upgrade head && uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8000} --loop uvloop --no-access-log"]
```

> [!IMPORTANT]
> Running `python -m alembic -c alembic.ini upgrade head` on container boot guarantees that schema upgrades apply safely before incoming traffic is routed. Because Alembic tracks executed versions in `alembic_version`, subsequent boots perform a zero-downtime no-op.

---

## 3. Railway Deployment Specification

---

### 3.1 Production [railway.json](file:///d:/voice%20agent/railway.json)

> [!WARNING]
> **Do not make the worker scale-to-zero initially.**  
> If the worker handles queued jobs (campaign dialing, post-call retries, R2 uploads) and Railway puts the worker container to sleep, background jobs will stall indefinitely because internal queue additions do not trigger HTTP wake-up webhooks. Both services should run continuously at launch.

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
      "dockerfilePath": "Dockerfile.worker",
      "sleepApplication": false
    }
  }
}
```

---

### 3.2 Environment Variables Reference

Configure these in Railway Dashboard → `api` and `worker` service settings:

```bash
# Environment Mode
APP_ENVIRONMENT=production
PORT=8000

# Database & Cache (Railway Managed Service References)
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}

# Connection Pool Defaults (Start Conservative)
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=5
DB_POOL_TIMEOUT=20.0
DB_POOL_RECYCLE=1800

# Secrets (Generate via `openssl rand -hex 32`)
SESSION_SECRET=<RANDOM_64_CHAR_HEX>
JWT_SECRET=<RANDOM_64_CHAR_HEX>

# Cloudflare R2 Object Storage
R2_ACCOUNT_ID=<YOUR_CLOUDFLARE_ACCOUNT_ID>
R2_ACCESS_KEY_ID=<YOUR_R2_ACCESS_KEY_ID>
R2_SECRET_ACCESS_KEY=<YOUR_R2_SECRET_ACCESS_KEY>
R2_BUCKET_NAME=voxly-call-archives

# Telephony Webhook Host & CORS
PUBLIC_APP_URL=https://<your-railway-domain>.up.railway.app
CORS_ORIGINS=https://<your-railway-domain>.up.railway.app,https://<your-vite-app>.up.railway.app

# Voice & LLM Provider Keys
OPENAI_API_KEY=<YOUR_KEY>
SARVAM_API_KEY=<YOUR_KEY>
TELNYX_API_KEY=<YOUR_KEY>
COMPOSIO_API_KEY=<YOUR_KEY>
```

---

### 3.3 Step-by-Step Deployment Guide

```bash
# 1. Install & Login
npm install -g @railway/cli
railway login

# 2. Link Local Workspace to Railway Project
railway link

# 3. Provision Managed Postgres and Redis in the Railway UI:
#    - Add New Service -> Database -> PostgreSQL
#    - Add New Service -> Database -> Redis

# 4. Deploy code
railway up

# 5. Verify Health & Database Connectivity
curl -s https://<your-domain>.up.railway.app/api/health | jq .
```

---

## 4. LATER: Architecture at Scale (Driven by Measured Growth)

Scale your architecture **in response to observed telemetry**, never based on arbitrary tenant counts or premature assumptions.

---

### 4.1 Telemetry-Driven Scaling Framework

Do not rely on arbitrary rules like *"at 10 calls, do X"* or *"at 100 tenants, do Y"*. Real capacity depends on which STT/TTS models you use (Sarvam, Deepgram, ElevenLabs), chunk sizes, audio filters, and LLM turnaround latency.

#### Baseline: `VOICE_GATEWAY_SAFE_CONCURRENCY`
Establish this number by running an empirical load test against your deployment (simulating concurrent audio WebSockets). For instance, benchmarking might prove that a 1 vCPU / 2GB RAM container comfortably handles **28 concurrent calls** before audio jitter occurs. Define that as your baseline.

#### When to Trigger Horizontal Auto-Scaling
Add API replicas when **any** of the following telemetry conditions persist for >3 minutes:

| Metric | Warning / Scale Trigger | Action |
|---|---|---|
| **CPU Utilization** | Sustained > 70–75% | Add API container replica |
| **Container Memory** | Sustained > 80% limit | Add replica / inspect memory leaks |
| **Event-Loop Lag** | Scheduling jitter > 50ms | Scale out voice container immediately |
| **Audio Turnaround / TTFT** | Roundtrip latency > 1,200ms | Inspect network egress and scale gateway |
| **Active Calls** | $\ge 85\%$ of `VOICE_GATEWAY_SAFE_CONCURRENCY` | Spin up additional replica ahead of saturation |
| **WebSocket Abnormals** | 1006 / 1008 error disconnect rate > 1% | Investigate proxy buffer limits & auto-scale |

---

### 4.2 Distributed Durable Job Queue (Redis / ARQ Engine)

When call volume grows and post-call analytics, audio encoding, and Composio tool calls become heavy, migrate from in-process background tasks to a dedicated **ARQ (Async Redis Queue)** architecture:

```
Call Finishes in Voice Gateway
          │
          ▼
   Enqueue Durable Job
   (Redis Streams / ARQ)
          │
          ▼
┌───────────────────────────────────────────────┐
│ Worker Pool (Dockerfile.worker)               │
│                                               │
│ • Post-call LLM summarization                 │
│ • WAV → MP3 encoding                          │
│ • Cloudflare R2 archive & verification        │
│ • Composio post-call actions & CRM sync       │
│ • Automatic exponential retry on network drop │
└───────────────────────────────────────────────┘
```

#### Standard Durable Job Schema
Every background job dispatched through the queue must adhere to this structured contract:

```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"

@dataclass
class DurableJob:
    job_id: str             # UUID4
    call_id: str            # Associated call UUID
    tenant_id: str          # Multi-tenant isolation boundary
    job_type: str           # "post_call_summary" | "recording_upload" | "composio_action"
    status: JobStatus       # Execution state
    attempt_count: int      # Incremented on retry (max 3-5)
    created_at: str         # ISO8601 UTC
    next_retry_at: str      # ISO8601 UTC with exponential backoff
    idempotency_key: str    # e.g. f"{job_type}:{call_id}:{action_name}"
    payload: dict[str, Any] # Job arguments
```

---

### 4.3 Composio Post-Call Tool Durability

Composio actions (e.g. creating a lead in Salesforce, updating a HubSpot contact, sending a confirmation email via Gmail, posting to Slack) are external HTTP API calls subject to network outages and rate limits.

**Durability Rule:**
- **Never** execute Composio post-call actions inside the live voice loop or as an un-tracked fire-and-forget background task.
- Enqueue them as distinct jobs with an `idempotency_key` (`composio:{action_name}:{call_id}`).
- The worker executes them with exponential backoff:
  - Attempt 1: Immediate
  - Attempt 2: After 30 seconds
  - Attempt 3: After 2 minutes
  - Final Failure: Log to dead-letter queue and flag in tenant dashboard.

---

### 4.4 Dedicated Voice WebSocket Service

At higher concurrency, audio streaming packets (arriving every 20ms over WebSockets) should not compete on the same Python event loop with slow dashboard queries or analytics CSV downloads.

Split into two focused services:
1. **REST API Service (`Dockerfile.api`):** Serves `/api/v1/*`, authentication, analytics, billing, CRUD.
2. **Voice Gateway Service (`Dockerfile.voice`):** Serves only telephony WebSockets (`/ws/telnyx`, `/ws/exotel`, `/ws/web-agent`).

```python
# server/voice_app.py
from fastapi import FastAPI
from server.routes.telnyx_ws import router as telnyx_ws_router
from server.routes.exotel_ws import router as exotel_ws_router
from server.routes.web_agent_ws import router as web_agent_ws_router

app = FastAPI(title="Voxly Voice Gateway")
app.include_router(telnyx_ws_router)
app.include_router(exotel_ws_router)
app.include_router(web_agent_ws_router)
```

---

### 4.5 Metric-Driven Database Scaling (PgBouncer & Read Replicas)

Do not scale the database based on tenant counts. Scale based strictly on database telemetry:

#### Trigger for PgBouncer (Connection Pooling)
- **Signal:** Total application pool size across all running replicas ($N_{\text{replicas}} \times (\text{DB\_POOL\_SIZE} + \text{DB\_MAX\_OVERFLOW})$) approaches $\ge 75\%$ of PostgreSQL's `max_connections`.
- **Signal:** Health check reports `QueuePool limit reached` or connection acquisition time $>100\text{ms}$.
- **Solution:** Deploy PgBouncer in **transaction pooling mode** (`pool_mode = transaction`). 200 application connections funnel efficiently through 25 real PostgreSQL server connections.

#### Trigger for Read Replicas (Query Splitting)
- **Signal:** Tenant analytics queries (call logs, billing charts, campaign aggregations) cause database CPU to exceed 70% or induce write lock contention on the `calls` table.
- **Signal:** p95 latency on `INSERT INTO calls` or `UPDATE wallet_ledger` spikes above $150\text{ms}$.
- **Solution:** Add a read replica. Direct all read-only dashboard traffic (`SELECT ... FROM calls`) to the replica connection pool; keep all transactional voice mutations on the primary database.

---

## 5. Cost Optimization & Operational Discipline

| Component | Architecture Strategy | Impact / Savings |
|---|---|---|
| **Call Audio Storage** | Cloudflare R2 ($0.015/GB storage, **$0 egress fees**) | Zero data loss; free audio downloads for tenants |
| **Worker Sizing** | Always-on single small instance initially; autoscale later based on queue depth | Predictable base cost (~$5/mo); reliable job completion |
| **Database Network** | Private Railway DNS (`${{Postgres.DATABASE_URL}}`) | Zero cross-network egress fees; sub-millisecond query latency |
| **Working Memory** | Multi-tier: Local LRU $\to$ Redis $\to$ PostgreSQL | Reduces database read queries by up to 70% during active calls |

---

## 6. Implementation Checklist for Agents & Engineers

### Phase 1: Deploy to Railway (Do Now)
- [ ] **DB Pool Config:** Add `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE` to [server/config/env.py](file:///d:/voice%20agent/server/config/env.py) and consume in [server/db/connection.py](file:///d:/voice%20agent/server/db/connection.py).
- [ ] **Redis Connection:** Add managed Redis in Railway and verify `REDIS_URL` is passed to the container.
- [ ] **Startup Reconciliation:** Add DB reconciliation for `post_call_status = 'pending'` in [server/app.py](file:///d:/voice%20agent/server/app.py) lifespan.
- [ ] **R2 Storage Service:** Implement [server/services/r2_storage.py](file:///d:/voice%20agent/server/services/r2_storage.py) with upload verification and durable status tracking.
- [ ] **Event Loop & Dockerfile:** Add `uvloop` to [pyproject.toml](file:///d:/voice%20agent/pyproject.toml) and prefix [Dockerfile.api](file:///d:/voice%20agent/Dockerfile.api) CMD with `python -m alembic upgrade head &&`.
- [ ] **Railway Configuration:** Update [railway.json](file:///d:/voice%20agent/railway.json) with `sleepApplication: false` for both `api` and `worker`.

### Scale Phase: When Telemetry Thresholds Fire
- [ ] Benchmark and record `VOICE_GATEWAY_SAFE_CONCURRENCY`.
- [ ] Migrate post-call pipeline to standalone ARQ / Redis Streams worker process.
- [ ] Wrap Composio tool dispatches in durable retries with exponential backoff.
- [ ] Isolate voice WebSockets to `server/voice_app.py` service.
- [ ] Introduce PgBouncer when active DB connection usage crosses 75% of server limits.
- [ ] Split analytical dashboard queries to a PostgreSQL read replica when primary write latency degrades.

---

## 7. Quick Reference: Key File Map

| System Area | Source File |
|---|---|
| Database Connection & Pool | [server/db/connection.py](file:///d:/voice%20agent/server/db/connection.py) |
| Environment Settings | [server/config/env.py](file:///d:/voice%20agent/server/config/env.py) |
| Post-Call Processing Pipeline | [server/call/post_call_pipeline.py](file:///d:/voice%20agent/server/call/post_call_pipeline.py) |
| Audio File Archiving | [server/call/audio_archive.py](file:///d:/voice%20agent/server/call/audio_archive.py) |
| Call Storage Paths | [server/call/paths.py](file:///d:/voice%20agent/server/call/paths.py) |
| Stream Token Management | [server/services/telnyx_client.py](file:///d:/voice%20agent/server/services/telnyx_client.py) |
| Redis Working Memory | [server/call/redis_memory_cache.py](file:///d:/voice%20agent/server/call/redis_memory_cache.py) |
| Application Lifecycle & Startup | [server/app.py](file:///d:/voice%20agent/server/app.py) |
| Background Worker Entrypoint | [worker/main.py](file:///d:/voice%20agent/worker/main.py) |
| Railway Service Config | [railway.json](file:///d:/voice%20agent/railway.json) |
| API Container Dockerfile | [Dockerfile.api](file:///d:/voice%20agent/Dockerfile.api) |
| Worker Container Dockerfile | [Dockerfile.worker](file:///d:/voice%20agent/Dockerfile.worker) |
| Database Schema Migrations | [server/db/migrations/versions/](file:///d:/voice%20agent/server/db/migrations/versions/) |
