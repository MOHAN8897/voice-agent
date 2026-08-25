# Database & Storage

Persistence strategy across implementation phases.

---

## 1. Storage tiers

| Tier | Technology | Contents |
|------|------------|----------|
| **Relational** | PostgreSQL | Entities, indexes, versions, campaigns |
| **Object** | Local `data/` (dev) / Railway bucket (prod) | Audio, transcripts, outcomes |
| **Cache/Queue** | Redis | Job queue, dialer state, rate limits |
| **Ephemeral** | Process RAM | In-flight sessions, WS state, ring buffers |

---

## 2. PostgreSQL — phase rollout

### Phase 1

```sql
tenants (tenant_id, name, created_at)
agents (agent_id, tenant_id, name, status, created_at)
tier_assignments (id, environment, tier, combination_id, updated_at)
config_versions (id, resource_type, resource_id, version, payload, created_at)
```

### Phase 2

```sql
platform_brain_versions (...)
business_brain_sections (...)
business_brain_versions (...)
compiled_brain_snapshots (...)
```

### Phase 3–4

```sql
calls (
  call_id UUID PK,
  tenant_id UUID,
  agent_id UUID,
  session_id TEXT,
  channel TEXT,
  tier TEXT,
  combination_id TEXT,
  compiled_brain_version TEXT,
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  duration_sec INT,
  disposition TEXT,
  finalization_status TEXT,
  storage_path TEXT,
  created_at TIMESTAMPTZ
)
CREATE INDEX idx_calls_tenant_started ON calls(tenant_id, started_at DESC);
CREATE INDEX idx_calls_agent ON calls(agent_id, started_at DESC);
```

### Phase 5

```sql
users (user_id, tenant_id, email, role, ...)
campaigns (campaign_id, tenant_id, agent_id, status, schedule, ...)
campaign_contacts (id, campaign_id, phone, status, attempts, ...)
dial_attempts (id, campaign_id, contact_id, call_id, status, ...)
audit_log (id, tenant_id, actor, action, resource, ts, ...)
phone_numbers (id, tenant_id, number, plivo_id, status, ...)
```

---

## 3. File store layout

### Development (`DATA_DIR=./data`)

```text
data/
├── voice_agent.db          # Deprecated after Postgres migration
└── calls/
    └── {call_id}/
        ├── meta.json
        ├── transcript.jsonl
        ├── memory_events.jsonl
        ├── memory_snapshot.json
        ├── user.pcm
        ├── agent.mp3
        ├── mix.wav
        └── outcome.json
```

### Production (bucket)

```text
s3://bucket/{tenant_id}/calls/{call_id}/...
```

`calls.storage_path` stores bucket URI. Signed URLs for audio access.

---

## 4. Retention policy

| Data | Default retention | Mechanism |
|------|-------------------|-----------|
| Call metadata (DB) | 90 days | Worker cleanup job |
| Call files (bucket) | 90 days | Bucket lifecycle rule |
| Brain versions | Permanent | — |
| Audit log | 1 year | Configurable |
| Benchmark runs | 90 days | Phase 6+ |

Env: `CALL_RETENTION_DAYS=90`

---

## 5. Migrations

- **Tool:** Alembic
- **Location:** `server/db/migrations/`
- **Run:** On api service deploy and local `alembic upgrade head`

### Local setup

```bash
# Install PostgreSQL locally
createdb voice_agent
export DATABASE_URL=postgresql://localhost/voice_agent
alembic upgrade head
```

Document in repo README (Phase 1 deliverable).

---

## 6. Connection pooling

| Environment | Pool |
|-------------|------|
| api (FastAPI) | asyncpg via SQLAlchemy async, pool_size=10 |
| worker | sync or async pool, smaller |

Railway Postgres connection limits — use PgBouncer if needed at scale.

---

## 7. Backup & recovery

| Component | Strategy |
|-----------|----------|
| PostgreSQL | Railway automated daily backups |
| Bucket | Versioning optional; lifecycle for cost |
| Redis | Ephemeral — jobs re-queue on failure |

RPO: 24h (Railway default). RTO: redeploy from git + restore DB.

---

## 8. Data residency

Recording/retention jurisdictions — identify before production PSTN launch ([`prd/README`](../../prd/README.md) approval checklist).

Telugu/India deployment: prefer Railway region closest to users and Plivo POP.
