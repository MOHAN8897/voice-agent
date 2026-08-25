# 16 — MVP Implementation Skills and Tooling Guide

This document is normative for **which skills, tools, and verification steps** implementation agents must use when building the MVP. It does not replace product requirements in other PRDs.

**Architecture ownership:** Before coding, read [15-architecture-ownership-and-singularity.md](./15-architecture-ownership-and-singularity.md) so modules are not duplicated.

---

## 1. Skill selection by workstream

| Workstream | Primary skill | Secondary skills | When NOT to use |
|------------|---------------|------------------|-----------------|
| **Next.js on Railway (marketing + consoles)** | `web-mvp-design` | **`vercel-react-best-practices`**, `vercel-composition-patterns`, `setup`, `frontend-design` | Backend-only tasks |
| **SEO (metadata, sitemap, JSON-LD)** | `web-mvp-design` | `web-design-guidelines`; Next.js Metadata API | Backend |
| **Core Web Vitals / bundle perf** | **`vercel-react-best-practices`** | Vercel Speed Insights, Lighthouse CI | Backend |
| **Full frontend MVP / console redesign** | `web-mvp-design` | `ui-design`, `polish` | Backend-only tasks |
| **New page or section (5 variations)** | `add-ui` | `web-mvp-design`, `frontend-design` | Tiny text/CSS tweak |
| **Vanilla `client/`** | — | — | **Do not extend** — reference only for porting |
| **shadcn/Tailwind component work** | `shadcn` | `tailwind-design-system` | Only if project adopts shadcn |
| **Motion / micro-interactions** | `motion-patterns` | `motion-foundations`, `ui-animation`, `animate` | Non-UI backend work |
| **Design tokens / theming** | `design-system-patterns` | `tailwind-design-system`, `setup` | One-off button color |
| **React performance refactor** | `vercel-react-best-practices` | `vercel-composition-patterns` | Non-React code |
| **Accessibility / UX audit** | `web-design-guidelines` | `ui-design` | After feature complete |
| **Pre-merge code review** | `review-bugbot` (Cursor) | `review-security` | During exploratory spike |
| **Railway deploy (staging/prod)** | `use-railway` | — | Local-only dev |
| **Firebase (if chosen for hosting/auth)** | `firebase-basics`, relevant firebase-* skills | — | Not required by PRD v1 |
| **Cursor rules / persistent agent guidance** | `create-rule` | `create-skill` | One-off tasks |
| **PR hygiene / CI loop** | `autopilot` | `split-to-prs` | Documentation-only |

**Orchestration rule:** Start with **`web-mvp-design`** + **`vercel-react-best-practices`** for Next.js. Deploy with **`use-railway`** (web + api + worker). Read [19-frontend-backend-nextjs-railway.md](./19-frontend-backend-nextjs-railway.md).

---

## 2. Context7 and library documentation

**Context7** was not available during PRD authoring. Treat it as **mandatory before implementing any provider adapter or SDK integration** when available in the agent environment.

| Integration | Verify via Context7 / official docs before coding |
|-------------|---------------------------------------------------|
| OpenAI Responses streaming + Structured Outputs | `openai` Python SDK, Responses API, `json_schema` |
| Sarvam STT/TTS REST + WS | Sarvam SDK / API reference |
| Cartesia Ink 2 / Ink Whisper STT | Cartesia STT WS, `cartesia_version`, encoding |
| Cartesia Sonic 3.5 TTS | TTS bytes/SSE API, `locale`/`language` rules |
| Plivo bidirectional stream | Stream XML, `playAudio`, signature validation |
| FastAPI background tasks | FastAPI lifespan, `BackgroundTasks` |
| Gemini / DeepSeek adapters | Provider-specific streaming + JSON schema support (DeepSeek MVP; Gemini post-MVP per `17` §13) |

---

## 2.1 MCP servers (Cursor environment)

| MCP | Use | MVP phase |
|-----|-----|-----------|
| **`plugin-railway-railway`** | Deploy, env vars, logs, Postgres/Redis plugins | 5 |
| **`plugin-firebase-firebase`** | **Not required** — Railway is normative | — |
| **`cursor`** | Optional `CreateGoal` for session tracking | All |

Full per-phase testing matrix: [../implementation/SKILLS-AND-MCP-GUIDE.md](../implementation/SKILLS-AND-MCP-GUIDE.md) §4–5.

Authenticate Railway MCP before deploy: `mcp_auth` on `plugin-railway-railway`.

**If Context7 is unavailable:** use official doc URLs in [14-research-traceability.md](./14-research-traceability.md) §2 and `WebFetch` on provider docs. Record verified model IDs in registry metadata — never guess.

---

## 3. MVP phase → skill map

**Engineering delivery uses 5 phases** — see [../implementation/README.md](../implementation/README.md) and [SKILLS-AND-MCP-GUIDE.md](../implementation/SKILLS-AND-MCP-GUIDE.md) for the canonical mapping.

This table maps **workstreams** to skills (cross-references PRD `08` and implementation phases):

| Workstream | Impl. phase | Deliverable | Skills / tools |
|------------|-------------|-------------|----------------|
| Provider registry + Postgres | **1** | Registry, tiers, DB | `pytest`; official Sarvam/OpenAI docs |
| Compiled brain (L2) | **2** | Platform + business + optimizer | `prd/12` §27; `test_brain_caching.py` |
| Call lifecycle + ledger (A) | **3** | `call_ledger` only writer | Read `15` §4.2; `LIVE_TEST=1` optional |
| Memory B/C + orchestrator | **4** | CD-016 same-LLM structured turn | Read `12` §17–28; golden disposition fixtures |
| Next.js + Dev Portal | **5** | Railway `web`, SEO, Dev auth | **`web-mvp-design`**, `vercel-react-best-practices`, **`use-railway`** |
| Business Brain builder UI | **5** | Accordion sections | `add-ui` or `web-mvp-design`; `11` §6 |
| Test Studio + Calls | **5** | Live test, traces | `ui-design`, `web-design-guidelines` |
| Benchmarks UI shell | **5** | Inert until `ENABLE_BENCHMARKS=true` | `web-mvp-design`, `07` metrics spec |
| Plivo + campaigns | **5** | L4 transport + Worker dialer | `prd/09`, `prd/18`; Plivo official docs |
| Hardening | **5** | RBAC, security | **`review-security`**, `web-design-guidelines` |

### Legacy P0–P10 labels (deprecated)

Older drafts used P0–P10 labels. Use **implementation Phase 1–5** instead to avoid ordering confusion (e.g. old "P4 compiled brain" = implementation **Phase 2**).

---

## 4. Per-file implementation ownership (do not clash)

When an agent implements a feature, it must respect **one owner module** from [15](./15-architecture-ownership-and-singularity.md) §5:

| Task | Implement in | Do NOT implement in |
|------|--------------|-------------------|
| Append transcript line | `call/call_ledger.py` | `conversation_manager`, routes |
| Apply memory op | `call/memory_manager.py` | `instruction_builder`, brain routes |
| Build projection | `call/memory_projection.py` | `memory_manager` render + LLM call |
| Build live LLM `input[]` | `instruction_builder.py` | WS handlers, `app.js` |
| Resolve STT/LLM/TTS stack | `providers/resolver.py` | UI, `call/start` body parsing only |
| Compile brain text | `brain/compiled_brain_service.py` | `instruction_builder`, optimizer |
| Optimize business prompt | `brain/business_prompt_optimizer.py` | Live turn path |
| Sequence live turn | `call/live_turn_orchestrator.py` | Individual routes duplicating flow |
| PSTN audio bridge | `plivo_stream.py`, `audio_transcode.py` | STT/TTS vendor SDKs |

---

## 5. UI implementation defaults (Next.js only)

From [19-frontend-backend-nextjs-railway.md](./19-frontend-backend-nextjs-railway.md):

1. **All UI in `web/`** — Next.js App Router + TypeScript + Tailwind.
2. Use **`web-mvp-design`** before large UI work; persist context via **`setup`** → `.better-react-web-ui.md`.
3. Navigation follows doc **11** v2 IA (not doc **05** legacy tabs).
4. **`client/` is not extended** — port live-voice and barge-in logic into Next.js client components.
5. Roles: hide UI per [15](./15-architecture-ownership-and-singularity.md) §9; server RBAC authoritative.

---

## 6. Verification checklist per PRD area

| Area | Automated | Manual / skill |
|------|-----------|----------------|
| Live latency preserved | pytest + optional `LIVE_TEST=1` | Test Studio browser call |
| Cache stable prefix | `test_brain_caching.py` | Metrics: cache_hit_rate |
| Memory projection bounded | unit fixtures in `12` §16 | Memory inspector UI |
| Ledger never in LLM | unit test on `instruction_builder` | Trace export review |
| Provider language gates | resolver unit tests | Catalog UI for Telugu |
| UX accessibility | — | `web-design-guidelines` audit |
| Security | — | `review-security` before production |

---

## 7. Tools explicitly not required for MVP

| Tool | Note |
|------|------|
| Ponytail | Unavailable; replaced by `web-mvp-design` + `ui-design` |
| Canvas | Optional for analytics dashboards; not required for core MVP |
| `GenerateImage` | Marketing assets only |
| Firebase skills | Only if product chooses Firebase for auth/hosting |

---

## 8. Agent session startup (recommended)

1. Read [15-architecture-ownership-and-singularity.md](./15-architecture-ownership-and-singularity.md).
2. Read the topic PRD for the current phase (`03`, `04`, `12`, `11`, etc.).
3. If touching providers: Context7 or official docs.
4. If touching UI: `web-mvp-design` skill first.
5. Before PR: `review-bugbot`; before production: `review-security`.
