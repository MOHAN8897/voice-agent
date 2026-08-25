# 17 — Locked Product Decisions (from `douts.md`)

Date: 25 August 2026  
Status: **Normative** — resolves open questions in `01`, `14`, and prior conflict CD-001.

Source: [`douts.md`](../../douts.md) product owner answers.

---

## 1. Product positioning

| Decision | Detail |
|----------|--------|
| **Generic platform** | Not real-estate-only. Any business configures their agent; Platform Brain defines how voice agents behave globally. |
| **MVP goal** | Small end-to-end MVP to test, configure, and fine-tune architecture before full fleet features. |
| **Knowledge base / RAG** | **Out of scope** until separately approved. |
| **CRM integrations** | **Future** — no CRM implied in MVP. |
| **Benchmark runs** | **Disabled by default** until product owner enables/configures scenarios. No automated benchmark UI runs without explicit configuration. |

---

## 2. Multi-tenant, agents, and environments

| Decision | Detail |
|----------|--------|
| **Multi-tenant** | **Required** — each business owner gets their own console; industry-standard security (see `13`). |
| **Agent limit** | **No limit** — customers may create unlimited agents. |
| **Environments** | **Development / Staging / Production** — full promotion workflow like major SaaS platforms. |
| **Agent-level brain (MVP)** | Each **call** references an **immutable compiled brain version** at `call/start`. Move to agent-level brain in MVP (not per-session ad-hoc prompts). |
| **Dev single-tenant convenience** | Auto-create **default agent** in development so engineers can test without onboarding flow. Database still supports many agents. |
| **Production onboarding** | Business owner creates agent, connects phone number. **First-time customer:** platform may auto-assign a number once to skip empty state; thereafter customer buys/assigns numbers and creates agents freely. |

---

## 3. Business Brain UI (customer console)

Eight **default** section types (UI authoring only — compiles to **one** optimized versioned prompt):

1. Identity & Purpose  
2. Business Facts  
3. Actions & Limits  
4. Qualification Flow  
5. Callback / Appointment Flow  
6. Scope & Redirects  
7. Guardrails  
8. FAQ  

| Rule | Detail |
|------|--------|
| Custom sections | Customer may **add and delete** custom sections. |
| Compilation | All enabled sections → single raw prompt → one-time optimize → versioned `optimized_business_prompt` → part of compiled brain. |
| Platform Brain | **Developer-only** — master instruction layer; no customer read/write. |

---

## 4. Languages and speech

| Decision | Detail |
|----------|--------|
| **Launch languages** | **Telugu** live now; **English** and **Hindi** planned; architecture must not hard-code Telugu-only. |
| **Live conversation** | **Telugu + English code-mix** — Sarvam STT `codemix` mode default for te+en agents. |
| **Cartesia Ink-2 STT** | **English only** (verified). **Not** production Telugu STT. Benchmark-only until Telugu officially verified. |
| **Production STT default** | **Sarvam** `saaras:v3` / `saaras:v3-realtime` for Telugu/code-mix. |
| **Provider fallback** | Try configured provider/model first; on failure fallback (e.g. Cartesia TTS → Sarvam TTS). Log fallback in trace; never silent swap. |
| **Tier assignments** | **Not pre-defined** by product owner yet. Developer tests combinations in **Dev Console** and assigns LOW/MEDIUM/PREMIUM globally for production via UI. |

---

## 5. Live LLM and memory (CD-016 — supersedes CD-001 async extraction as primary)

**Product owner decision:** The **same LLM** that talks to the user returns **structured output** with both `spoken_response` and `memory_update`.

### Normative live turn flow

```text
STT final → server saves ledger → load memory B → build projection C → build LLM request
  → SAME LLM (OpenAI or DeepSeek Flash per dev config)
  → structured { spoken_response, memory_update }
  → spoken_response → TTS (stream without blocking on full JSON parse when possible)
  → memory_update → validate + merge → B (+ event log)
```

| Rule | Detail |
|------|--------|
| Memory model | **Same model as live conversation** — not a separate cheap extraction call in MVP. |
| Streaming | Stream `spoken_response` to TTS on the hot path; parse/apply `memory_update` when available without delaying first audible byte beyond existing sentence-buffer behavior. |
| Cross-call memory | **No** in MVP — one call = one memory scope. Add later. |
| Rolling summary in live input | **One compact dynamic memory block** — do not duplicate narrative in projection + separate summary message unless projection omits prose (see `15` §8). |

### MVP working memory shape (default schema)

Cleaner compact block for live projection and storage:

```json
{
  "facts": {},
  "preferences": {},
  "important_context": "",
  "summary": ""
}
```

Extended slot/history schema (`12` §18) remains available for agents that need provenance-heavy fields; default new agents use the compact schema above.

---

## 6. Post-call disposition and summaries

### Canonical disposition enum

| Value | Meaning |
|-------|---------|
| `new_lead` | First contact / lead captured |
| `interested` | Positive engagement |
| `qualified` | Meets qualification criteria |
| `site_visit_planned` | Site visit or appointment scheduled |
| `callback_required` | Must call back |
| `not_interested` | Declined |
| `wrong_number` | Wrong party / misdial |
| `converted` | Deal closed / goal achieved |
| `no_outcome` | Too short or ambiguous |

Replaces generic enum in `02` §4 where noted.

### Summaries

- Store **`summary_te`** and **`summary_en`** when generated.
- **English summary optional** in customer UI (ops may still see both).

---

## 7. Telephony (Plivo) — outbound priority

| Decision | Detail |
|----------|--------|
| **Scope** | **Inbound + outbound** — **outbound prioritized** (campaigns and proactive calls). |
| **Number provisioning** | Customer adds phone number in website → **automatic connection** flow. |
| **Consent** | Internal/dev testing: simplified. **Production PSTN:** consent flow required before launch. |
| **Barge-in** | **Preserve existing** `live-guards.js` / server barge policy — do not redesign; reuse for PSTN via Plivo `clearAudio`. |

---

## 8. Outbound campaigns (MVP scope — product approved)

Campaign system is **in MVP scope** per product owner:

- Campaign management (create, schedule, pause)
- Outbound dialing via Plivo
- Retry rules, max attempts, engagement timeouts
- DNC (do-not-call) list
- Consent and calling-window enforcement
- Campaign analytics (attempts, connects, dispositions, failures)

Normative detail: [18-campaign-outbound.md](./18-campaign-outbound.md).

---

## 9. Dev Console vs Business Console

| Surface | Auth priority | Purpose |
|---------|---------------|---------|
| **Dev Portal** | **P0** — login required | Configure global stack, tiers, Platform Brain, provider keys validation, fallback rules, promotion to staging/production. |
| **Business Console** | **P2** — login second priority | Business owners manage agents, business brain, numbers, campaigns, calls. |

### Dev Portal authentication (MVP)

- Username/password from **environment variables** (e.g. `DEV_PORTAL_USERNAME`, `DEV_PORTAL_PASSWORD`).
- Separate **Dev Portal route prefix** (e.g. `/dev` or dedicated host) — not mixed with customer routes without auth.
- Industry-standard session security (httpOnly cookies, CSRF for mutating routes, rate limits, bcrypt if storing hashes later).

### Stack configuration authority

- **Only Developer/Administrator** configures STT/LLM/TTS stacks and tier assignments.
- UI-based configuration in Dev Console — not `.env` edits required for routine tier tuning after initial deploy.
- Dedicated APIs under `/api/dev/*` or `/api/platform/*` (see `13`).

---

## 10. Roles and promotion governance

| Decision | Detail |
|----------|--------|
| **Base roles** | **Administrator** and **Developer** — both have full Dev Portal access in MVP. |
| **Custom roles** | System must allow **creating new roles** and permission sets (extensible RBAC). |
| **Production promotion** | **One** Administrator or Developer approval sufficient to promote to production (no two-person rule in MVP). |

Customer-facing roles (Viewer, Operator, Customer Admin) apply to Business Console when auth ships.

---

## 11. Infrastructure (Railway)

| Layer | Technology |
|-------|------------|
| **Frontend (`web` service)** | **Railway** — **Next.js App Router only** (no vanilla `client/`); Vercel optional later |
| **API / WS / workers** | **Railway** — FastAPI `api`, Worker, Postgres, Redis, bucket |
| **Retention** | **90 days** default |

Normative split, SEO, performance: [19-frontend-backend-nextjs-railway.md](./19-frontend-backend-nextjs-railway.md).

Normative detail: `06-technical-architecture.md` §16.

---

## 12. UI and responsive design

| Decision | Detail |
|----------|--------|
| **Devices** | Full responsive — mobile, tablet, desktop; best practices in `11` §18. |
| **Navigation** | Next.js App Router per doc **11** v2 IA in `web/` |
| **Benchmark UI** | Present but **inactive** until owner configures/enables benchmarks. |

---

## 13. LLM providers in MVP

| Provider | MVP status |
|----------|------------|
| **OpenAI** | Current default (`gpt-5.6-luna` path) |
| **DeepSeek Flash** | **In MVP** — dev configurable via API key for brain processing |
| **Gemini** | Post-MVP unless needed for benchmark |

---

## 14. Traceability — conflict updates

| ID | Previous | New (this document) |
|----|----------|---------------------|
| **CD-001** | Async second LLM for memory | **Superseded by CD-016** — same LLM structured output |
| **CD-016** | — | Single live LLM returns `spoken_response` + `memory_update` |
| **CD-017** | Real-estate default schema | Generic platform; compact default memory schema |
| **CD-018** | Campaigns post-MVP | Campaigns **in MVP** (outbound priority) |
| **CD-019** | CRM webhook v1 | CRM **deferred** |
| **CD-020** | Benchmarks active in MVP | Benchmarks **disabled until configured** |

Record in `14-research-traceability.md` §7.
