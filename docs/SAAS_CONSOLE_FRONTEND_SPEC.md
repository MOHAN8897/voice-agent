# SaaS Console Frontend — 5-Phase Build Spec

**Status:** Ready to build. No code written yet.
**Scope:** The tenant-facing console at `web/app/app/(console)/`. Internal dev portal (`web/app/dev/`) and the legacy Vite app (`voxly-ai/`) are **out of scope except as UX references**.
**Audience:** The paying SaaS customer (a business owner or ops lead), not an engineer.

---

## 1. The gap, in one paragraph

The backend is essentially complete — 262 endpoints covering agent creation, script compilation, telephony, campaigns, leads, calls and billing. The working agent-creation flow lives **only in Test Studio**, which is an internal tool with internal-tool ergonomics. The tenant console at `web/app/app/(console)/` can **list** agents and edit a brain, but there is **no create button anywhere in it**, and campaigns, leads, numbers, billing and tenant members exist **only** in the legacy `voxly-ai` app, which is no longer routed. This spec wires the existing backend into a console a non-technical customer can operate.

### 1.1 What exists today

| Area | `web/` (Next.js, live) | `voxly-ai/` (legacy Vite) |
|---|---|---|
| Agent creation | Test Studio only (`TestStudioCreateAgent.tsx`) | 4-step `CreateAgentWizard` + `agent-creation/` module |
| Agent management | `agents` list + 8 sub-pages | `AgentStudioModule`, `EmployeesModule` |
| Numbers / inbound-outbound | **none** | `PhoneNumbersModule`, `TelephonySettingsCard` |
| Campaigns | **none** | `CampaignsModule` |
| Leads | **none** | `LeadsModule` |
| Calls | `calls`, `calls/[id]` | `CallsModule` |
| Billing | **none** | `BillingModule`, `AddFundsModal` |
| Tenant members / roles | **none** | `AdminModule`, `SettingsModule` |

### 1.2 The two known blockers (fix in Phase 1)

**BLOCKER-A — `/api/instructions` has no tenant guard.**
`server/routes/instructions.py:45` declares a bare `router = APIRouter()` with no `require_subscriber` dependency and no tenant scoping. Compile state is keyed only by a **client-supplied `sessionId`**. Acceptable for an internal Test Studio; not acceptable in the tenant console. The console must not call this endpoint directly.

**BLOCKER-B — `/api/agents` uses optional auth.**
`require_subscriber_jwt_if_enabled` (`server/routes/agents.py:44,54,73,88,115,124`); with SaaS auth disabled it falls back to `tenant_id_from_request(request)`, and `create_agent` will additionally accept a body-supplied `tenantId` (`agents.py:23,58`). The stronger, hard-guarded equivalents are `require_subscriber_jwt` + `load_agent_for_tenant` in `app_agents.py` / `app_agent_telephony.py`.

**Resolution for both:** the console wizard calls **`POST /api/app/agents/compose-onboarding`** and **`POST /api/app/agents/build-employee`** only. Both use `require_subscriber_jwt` + `require_subscriber_permission("app.agents.write")` + `subscriber_workspace_tenant_id`. The console derives its wizard session key server-side from `agentId`, never from user input.

---

## 2. Design principles

These are constraints, not suggestions. Every screen is reviewed against them.

1. **The brief is the only required field.** A customer who writes two sentences about their business must be able to finish Step 1. Every other field has a working default. No form in this product is allowed to block on a field the customer did not ask for.
2. **Four steps. Never five.** Describe → Review script → Phone & voice → Ready. The shape is already proven in `voxly-ai/src/console/modules/agent-creation/index.js`; keep it. A wizard that grows a fifth step has failed.
3. **Test call is available from Step 1.** Never gate the ability to hear the agent behind completing setup. This is the single biggest trust-builder in the category and it is free — the Test Studio already works.
4. **Reuse the Skeuo kit.** `web/components/ui/skeuo/` has `SkeuoPanel`, `SkeuoButton`, `SkeuoInput`, `SkeuoTextarea`, `SkeuoBadge`, `SkeuoTable`, `SkeuoEmptyState`, `SkeuoMeter`, `SkeuoNavItem`, `SkeuoStatusLight`, `icons`. Do not introduce a second design language. `cn()` from `web/lib/cn.ts` for all conditional classes.
5. **Reuse the data layer.** `useAdminResource` / `adminAction` from `web/lib/useAdminResource.ts` (shared `devFetch`, error + loading states). Do not hand-roll `fetch` + `useEffect` per page.
6. **Status is always a pill, never prose.** Every agent, number, campaign and call shows `SkeuoStatusLight` + `SkeuoBadge`. "Active", "Paused", "Provisioning", "Failed" — never "currently enabled and running fine".
7. **Empty states are instructions.** `SkeuoEmptyState` always contains one sentence of what this screen does and one primary action. Never an empty table.
8. **Destructive actions confirm and name the target.** "Delete agent **Priya · spandana private limited**? This removes 1,204 calls of history." Not "Are you sure?".
9. **No internal vocabulary in the UI.** No "compiled brain", "tier", "stack", "VAD", "E.164", "pnl". The customer sees "Script", "Voice", "Phone number", "Recording", "Lead".
10. **The customer never sees a raw token, a trace, or an internal id** unless they are on `/dev/`.

---

## 3. Competitor benchmark — what to match

Measured against Vapi, Retell AI, Bland AI, ElevenLabs Agents and PolyAI. Where they are better, match them.

| Capability | Category standard | Our position | Required action |
|---|---|---|---|
| Create agent from a description | One textarea + industry templates; AI drafts the prompt; user edits before deploy | Backend is strongest-in-class (brief compiler extracts entity tags + opening line per language). No console entry point. | **Phase 1** — expose it |
| Script review before deploy | Editable prompt in a single pane, side-by-side with the live prompt preview | `BusinessBrainEditor`, `LivePromptPreviewPanel`, `CompilerSectionsPanel` all exist in Test Studio | **Phase 1** — port |
| Immediate test call | A "Test call" button on the agent card, no navigation | Exists, but only inside Test Studio | **Phase 1 + 2** — put it on the agent card |
| Language selection | A prominent selector, 10+ Indian languages, shown during creation | 12 languages ready in `compile-languages.ts` | **Phase 1** |
| Voice selection | Per-agent voice picker with preview sample | Three pickers already built (Realtime / Cartesia / Sarvam) | **Phase 1** |
| Phone number | Buy **or** import (BYO number), assign to agent, per-number inbound/outbound toggles | Full backend, zero UI | **Phase 3** |
| After-hours / IVR | Business hours, voicemail vs hangup vs transfer, per agent | `AgentTelephonyProfile` complete, zero UI | **Phase 3** |
| Agent lifecycle | List, activate/pause, duplicate, delete, per-agent stats | List exists; no actions | **Phase 2** |
| Call history | Filter by agent, direction, status, date; click through to detail | Exists and is tenant-scoped | **Phase 4** — add filters + recording |
| Recording playback | In-call player with transcript alongside | `/api/call/{id}/audio` exists, no player | **Phase 4** |
| Call outcome / objective | Per-call structured outcome + captured fields | `/outcome`, `/memory`, `/memory/projection` exist, no UI | **Phase 4 + 5** |
| Campaigns | Create → import contacts → start/pause → analytics; DNC list | Full backend, zero UI | **Phase 5** |
| Leads | Pipeline board by stage + table view + per-call capture | Full backend, zero UI | **Phase 5** |

**Where we can beat them, do:** our compiler produces a *ready-to-use script with a natural opening line in the selected language* (e.g. "Meeku oka moment unda?") and entity tags the runtime pins. Most competitors hand you a blank prompt. Make that visible in Step 2 — show the extracted agent name, company, role, scope and opening line as read-only "what we understood", and let the customer correct them. That is the differentiator; do not bury it.

---

## 4. Data model reference

Exact fields. Use these names in TypeScript types — do not invent camelCase/snake_case variants.

### 4.1 `Agent` — `server/db/models/entities.py:47`

```
agent_id                     uuid  (PK)
tenant_id                    uuid
name                         string(255)
status                       string(50)   default "active"
active_compiled_brain_version string(64) | null   ← null means NOT compiled/activated
default_tier                 string(20)   default "medium"
languages                    string[]     default ["te-IN"]
memory_schema                string(64)   default "compact_v1"
environment                  string(50)   default "development"
voice_settings               jsonb        default {}
created_at                   timestamptz
```

> `active_compiled_brain_version === null` is a real production state we already hit — the `Priya · spandana private limited` agent has it. The console **must** surface this as a `SkeuoStatusLight` "Not activated" badge on the agent card and in the agent list, because an agent in that state cannot take calls.

### 4.2 `AgentTelephonyProfile` — `phase5_models.py:52`

```
greeting_phrase    string(500) | null    spoken opening on inbound; null = derive from brain
business_hours     jsonb {"mon":[{"open":"09:00","close":"18:00"}], ...}   {} = always open
timezone           string(64)  default "Asia/Kolkata"   IANA
after_hours_action string(30)  default "voicemail"     voicemail | hangup | transfer | always
transfer_number    string(32)  | null    required when after_hours_action == "transfer"
inbound_enabled    bool        default true    false = live inbound path does not answer
outbound_enabled   bool        default true    false = outbound refused before dialling
```

### 4.3 `PhoneNumber` — `phase5_models.py:31`

```
id                 uuid (PK)          ← note: `id`, not `number_id`
e164               string(20)
status             string(30)  default "pending"
agent_id           uuid | null
purchase_id        uuid | null
plivo_number_id    string(100) | null
telnyx_number_id   string(100) | null
billing_source     string(30)  default "manual"
inbound_enabled    bool default true
outbound_enabled   bool default true
released_at        timestamptz | null
```

### 4.4 `Campaign` / `CampaignContact` / `CampaignRun` — `phase5_models.py:97,111,123`

```
Campaign:  campaign_id, tenant_id, agent_id, name, status(default "draft"),
           schedule jsonb, retry_rules jsonb, concurrency int(default 5), created_at
CampaignContact: id, campaign_id, phone_e164, status(default "pending"),
           metadata jsonb, attempts int, last_attempt_at
CampaignRun: run_id, campaign_id, status(default "scheduled"), started_at, ended_at, stats jsonb
```

### 4.5 `Lead` / `TelephonyContact` / `DncEntry`

```
Lead:              lead_id, tenant_id, name, phone|null, email|null,
                   stage(default "new"), notes, created_at, updated_at
TelephonyContact:  contact_id, tenant_id, name, phone, notes, created_at
DncEntry:          id, tenant_id, phone_e164, reason|null, added_at
```

### 4.6 Request bodies — copy these exactly

```ts
// POST /api/app/agents/compose-onboarding          app_agents.py:20
{ name?: string; role?: string; language?: string; businessSummary?: string;
  goals?: string; notes?: string; brief?: string; mode?: string;
  industry?: string; naturalSpokenStyle?: boolean }
// → { ok, /* compose_agent_onboarding result */ }

// POST /api/app/agents/build-employee              app_agents.py:33
{ brief: string /* 8..6000 */; language?: string; mode?: string;
  industry?: string; naturalSpokenStyle?: boolean; employeeName?: string }
// → { ok, agent, agentId, script, variables, source: "agent_script_compiler" }

// PUT /api/agents/{id}/business-brain/calling-script   agents_business_brain.py:134
{ script: string /* 1..60000, non-blank */ }

// PUT /api/agents/{id}/business-brain/voice             agents_business_brain.py:151
{ voiceId?: string; speed?: number /* 0.25..2.0 */; language?: string;
  realtimeVoice?: string|null; turnDetection?: string|null; noiseReduction?: string|null }

// PUT /api/agents/{id}/telephony-profile               app_agent_telephony.py:37
{ greetingPhrase?: string|null; businessHours?: object|null; timezone?: string|null;
  afterHoursAction?: string|null; transferNumber?: string|null;
  inboundEnabled?: boolean|null; outboundEnabled?: boolean|null }

// POST /api/telephony/buy                              app_telephony.py:57
{ e164: string /* min 8 */; country?: string /* "IN" */;
  payMethod?: string /* "wallet" */; assignAgentId?: string|null }

// POST /api/telephony/numbers/{numberId}/assign         app_telephony.py:64
{ agentId: string|null }

// PUT /api/telephony/numbers/{numberId}/routing         app_telephony.py:68
{ agentId?: string|null; inboundEnabled?: boolean|null; outboundEnabled?: boolean|null }

// POST /api/telephony/calls/outbound                   app_telephony.py:41
{ agentId: string; toE164: string; fromE164?: string|null; dialRequestId?: string|null }
// ⚠ rejects stackOverride | tier | pipeline — the console must never send them

// POST /api/calls/{callId}/callback                     app_telephony.py:384
{ toE164?, agentId?, fromE164?, dialRequestId?, mode? /* "manual" */ }

// POST /api/campaigns                                   campaigns.py:21
{ name: string; agentId: string; concurrency?: number /* 5 */ }

// POST /api/leads   /  PATCH /api/leads/{id}   /  PATCH /api/leads/{id}/stage
```

### 4.7 Languages — `web/lib/compile-languages.ts`

Twelve, already defined. **Use `COMPILE_LANGUAGE_OPTIONS`, do not re-declare.**

| Group "India" | Group "English (global)" |
|---|---|
| `te-IN` తెలుగు · `hi-IN` हिन्दी · `ta-IN` தமிழ் · `kn-IN` ಕನ್ನಡ · `ml-IN` മലയാളം · `mr-IN` मराठी · `bn-IN` বাংলা · `gu-IN` ગુજરાતી · `pa-IN` ਪੰਜਾਬੀ · `en-IN` Indian English | `en-US` · `en-GB` |

Every one of these has a spoken pack; `spoken_pack_for()` raises for anything else. Do not add a language the backend does not have.

---

## 5. Shared shell

Every phase below assumes this navigation, built once in **Phase 1** and extended after.

Replace the current console nav (`web/components/console/`) with:

```
Overview        /                 Dashboard: calls today, answer rate, spend, top agents
Agents          /agents           list, create
  └ agent       /agents/[id]      Overview | Script | Voice & language | Phone | Memory | Versions
Numbers         /numbers          buy / import / assign / release
Campaigns       /campaigns        outbound + inbound campaigns
Calls           /calls            history, recordings
Leads           /leads            pipeline
Billing         /billing          wallet, top-up, invoices
Settings        /settings         members, roles
```

Keep `/test-studio/*` and `/dev/*` exactly as they are — they are internal and already work. The console links *into* Test Studio for deep testing; it does not replace it.

---

# PHASE 1 — Agent Creation

**Goal:** A signed-in customer with no agents can create a working, tested, script-correct voice agent without leaving the console, without reading documentation.

**This is the phase that matters most.** Everything else is CRUD on top of it.

## 6.1 Files to create

```
web/app/app/(console)/agents/new/page.tsx            wizard shell + step routing
web/app/app/(console)/agents/new/step-brief.tsx
web/app/app/(console)/agents/new/step-script.tsx
web/app/app/(console)/agents/new/step-phone.tsx
web/app/app/(console)/agents/new/step-ready.tsx
web/components/agents/CreateAgentWizard.tsx          state machine (client)
web/components/agents/BriefComposer.tsx              textarea + industry chips
web/components/agents/ScriptReviewPanel.tsx         editable script + "what we understood"
web/components/agents/PhoneAndVoicePanel.tsx         number + profile + voice
web/components/agents/WizardRail.tsx                4-step progress rail
web/lib/create-agent-flow.ts                        endpoint orchestration, typed
```

## 6.2 Files to modify

```
web/app/app/(console)/agents/page.tsx               add the "New agent" primary button
web/lib/useAdminResource.ts                         confirm exported helpers cover this flow
```

## 6.3 The flow, step by step

### Step 1 — Describe (`step-brief.tsx`)

**One textarea is the product.** Everything else is optional and collapsed behind a "More options" disclosure.

Layout:
- `SkeuoPanel` titled **"What should this agent do on calls?"**
- One `SkeuoTextarea`, min 200px. Placeholder is a real example, copied from the working one in `TestStudioCreateAgent.tsx:175`:
  > "Example: Agent name is Murthi. Business is Raghava Sales Private Limited — automobile spare parts in Hyderabad, Boduppal, with 20% discount…"
- Helper line under it: *"Write it the way you'd brief a new hire. Include the agent's name, your business, and what you want them to say."*
- **Industry chips** row (from `voxly-ai/src/console/modules/agent-creation/index.js:44-87`, reuse verbatim): Real estate, Clinic/doctor, Car dealership, Coaching/education, Property support, Restaurant. Clicking a chip **appends** its snippet to the textarea. It never replaces user text. This is how the category does templates and it measurably improves first-brief quality.
- **More options** disclosure containing: Language (`COMPILE_LANGUAGE_OPTIONS`, default `en-IN`), Call direction (Outbound / Inbound, default Outbound), Role (Sales / Lead qualification / Customer support / Appointments / Recruitment / Education / Information / Follow-up / General — reuse `ROLES` from `TestStudioCreateAgent.tsx:16-26`).
- Primary button: **"Create my agent"** — disabled until `brief.trim().length >= 8`.
- Secondary: **"Test a sample call first"** → runs a dry sample on the current brief text without creating anything, so the customer hears a voice before committing.

On click, call `POST /api/app/agents/compose-onboarding` with the brief plus the chosen language/mode/industry. Show the returned brief in an editable `SkeuoTextarea` under a **"Refine"** label — the customer can adjust the machine's expansion before compiling. Default action is to accept it unchanged.

Then call `POST /api/app/agents/build-employee` with the (possibly refined) brief. On success, `router.push(/agents/{agentId})?welcome=1`.

**Error handling:** surface `detail.error.message` verbatim in a red `SkeuoPanel`. Never a generic "Something went wrong". If compile fails, keep the customer on Step 1 with their text intact and offer "Try without industry hints".

### Step 2 — Review script (`step-script.tsx`)

This is where we beat the category. Two panes, side by side on desktop, stacked on mobile.

**Left — "What we understood" (read-only, editable via an Edit toggle):**
Extracted from the `script` + `variables` returned by `build-employee` and from `GET /api/agents/{id}/business-brain`:
- Agent name, Company, Role, Work scope, Opening line, Direction, Language
- Editing any of these writes back through `PUT /api/agents/{id}/business-brain/calling-script` after re-compiling. The extraction is `server/brain/script_entities.py::parse_entity_tags`, mirrored client-side in `web/lib/script-entities.ts`.

**Right — "What your agent will say" (editable):**
A `SkeuoTextarea` holding `script` verbatim, pre-populated from `build-employee`. Save via `PUT /api/agents/{id}/business-brain/calling-script`.

Below it, three read-only disclosure panels ported from Test Studio:
- `LivePromptPreviewPanel` — the exact system instruction the model receives. This is a genuine trust artifact; Retell and Vapi do not show it.
- `CompilerSectionsPanel` — the compiled sections and their token counts.
- `ScriptEntityTagsPanel` — the machine-readable entity tags.

Primary: **"Save & continue"**. Secondary: **"Re-generate from my brief"** (re-calls `build-employee` with the original brief, warning that manual edits will be lost).

### Step 3 — Phone & voice (`step-phone.tsx`)

Two `SkeuoPanel`s, both skippable.

**Panel A — Voice.** Reuse `RealtimeVoiceSelect`, `CartesiaVoiceSelect`, `SarvamVoiceSelect` from `web/components/test-studio/`. Options loaded from `GET /api/telephony/voice-options`. A **Play sample** button per voice — non-negotiable, this is table stakes. Speed slider 0.25–2.0. Save: `PUT /api/agents/{id}/business-brain/voice` with `{voiceId, speed, language, realtimeVoice, turnDetection, noiseReduction}`. The voice language selector is bound to the agent's primary language and defaults to it.

**Panel B — Phone number.** Three mutually exclusive options as radio cards:
1. **I already have a number** → `SkeuoInput` for the number, then `POST /api/telephony/buy` is *not* used; the number must be imported. **There is no import endpoint** — see §11 RISK-3. Until it exists, this option is disabled with the label "Coming soon" rather than faked.
2. **Buy a number** → inline search against `GET /api/telephony/numbers/search?country=IN`, results in a `SkeuoTable` (number, monthly price, setup fee). Selecting one opens a confirm dialog showing the charge against `GET /api/billing/wallet` balance, then `POST /api/telephony/buy` with `{e164, country:"IN", payMethod:"wallet", assignAgentId}`. Handle insufficient balance by linking to `/billing`.
3. **Skip for now** → allowed. The agent is created and usable for test calls; inbound/outbound activation is blocked until a number exists, and the agent card shows "No number attached".

**Panel C — When should it answer?** (`AgentTelephonyProfile`)
- Inbound: `SkeuoInput type=checkbox` bound to `inboundEnabled`
- Outbound: same, bound to `outboundEnabled`
- Business hours: a 7-row `SkeuoTable` (Mon–Sun) each with one or more `open`/`close` time inputs, plus an **"Always open"** master toggle that writes `{}`. Reuse `DEFAULT_BUSINESS_HOURS` and the `WEEKDAYS` / `businessHoursSummary` helpers from `voxly-ai/.../agent-creation/index.js:117-152` — port them to `web/lib/business-hours.ts`.
- Timezone: `SkeuoInput` with IANA default `Asia/Kolkata`.
- After hours: 4 radio cards — Take a voicemail / Do not answer / Transfer to a number / Always answer. Selecting **Transfer** reveals a required `SkeuoInput` for `transferNumber`; the form cannot submit without it.
- Greeting phrase: optional `SkeuoInput` maxLength 500, placeholder "Leave blank to use the agent's own opening line."

Save all of C with a single `PUT /api/agents/{id}/telephony-profile`. Show the resulting summary line using `businessHoursSummary()` under the form ("Open 6 days a week, 09:00–18:00") — this is the pattern that stops users guessing.

### Step 4 — Ready (`step-ready.tsx`)

- `SkeuoStatusLight` confirming each precondition: script saved ✅, voice set ✅, number attached ✅/⚠, profile saved ✅.
- A **"Make a test call"** primary button that opens the existing Test Studio in a new tab at `/test-studio/{agentId}`.
- A short, literal "What happens next" list (3 bullets max).
- Primary: **"Go to my agent"** → `/agents/{agentId}`.

## 6.4 Acceptance criteria — Phase 1

1. A customer with **zero agents** reaches a created, script-bearing agent in **≤ 4 interactions** from `/agents`.
2. The wizard is reachable at `/agents/new`; a `New agent` primary button exists on `/agents`.
3. No tenant-console network request goes to `/api/instructions`. Verified by grep in review: `web/app/app/(console)/**` must not contain the string.
4. Every failing call shows the backend's own `error.message`.
5. Reloading at any step does not lose the brief (persist wizard state in `sessionStorage` keyed by tenant).
6. `tsc --noEmit` clean; no new file imports from `voxly-ai/`.
7. Keyboard: the whole wizard is completable with Tab/Enter; the primary action is a real `<button>`, not a click-handler on a `<div>`.

---

# PHASE 2 — Agent Management

**Goal:** An existing customer can see every agent, understand its state at a glance, and change anything about it without contacting support.

## 7.1 Files to create

```
web/components/agents/AgentListTable.tsx
web/components/agents/AgentCard.tsx
web/components/agents/AgentActions.tsx          duplicate / pause / activate / delete
web/components/agents/AgentStateBadge.tsx        active | paused | not-activated
web/components/agents/AgentWorkspace.tsx         the [id] tab shell
web/components/agents/tabs/OverviewTab.tsx
web/components/agents/tabs/ScriptTab.tsx        ← Step 2 of Phase 1, extracted
web/components/agents/tabs/VoiceLanguageTab.tsx ← Step 3 voice+language, extracted
web/components/agents/tabs/PhoneTab.tsx         ← Step 3 profile, extracted
web/components/agents/tabs/MemoryTab.tsx
web/components/agents/tabs/VersionsTab.tsx
web/lib/agent-lifecycle.ts                      typed wrapper over PATCH /api/agents/{id}
```

## 7.2 The list — `/agents`

`SkeuoTable` with columns:

| Column | Source | Notes |
|---|---|---|
| Agent | `name` | bold; subtitle = `languages.join(", ")` |
| Status | `status` + `active_compiled_brain_version` | three states, see below |
| Numbers | derived | count of assigned numbers, from `GET /api/telephony/numbers` filtered by `agent_id` |
| Last call | `GET /api/calls?agentId={id}&limit=1` | relative time, `—` if none |
| Calls (7d) | `GET /api/calls/stats?agentId={id}` | number |

**`AgentStateBadge` — three states, non-negotiable:**
- `status === "active"` **and** `active_compiled_brain_version !== null` → green **Live**
- `status === "active"` **and** `active_compiled_brain_version === null` → amber **Not activated** — with the explanation "This agent has never been compiled. Open it and save the script to make it live." This state exists in production today and silently produces dead agents.
- `status !== "active"` → grey **Paused**

Row actions (`AgentActions`, kebab menu): **Test call**, **Edit script**, **Duplicate**, **Pause / Activate**, **Delete**.

- `Duplicate` → `POST /api/agents` with `{name: "{name} (copy)", languages}` then `PUT` the same calling script. The duplicate starts in **Not activated** so the customer must confirm it before it can bill.
- `Pause` → `PATCH /api/agents/{id}` `{status:"paused"}`
- `Delete` → `PATCH`-then-`DELETE /api/agents/{id}`, with a confirm naming the agent and its call count. No silent deletes.
- Filter bar above the table: status, language, search by name. All client-side until the list exceeds 100 agents, at which point add `?search=` to `GET /api/agents`.

## 7.3 The agent workspace — `/agents/[id]`

A tabbed `SkeuoPanel` shell. **Reuse the sub-pages that already work** — `app/(console)/agents/[id]/brain`, `/voice`, `/versions`, `/summary`, `/memory-schema`, `/tools`, `/test`, `/channels` — and re-skin them as tabs. Do not rewrite them.

| Tab | Content | Endpoints |
|---|---|---|
| **Overview** | Name, status, language, created, script preview (first 20 lines), numbers, 7-day stats, "Test call" | `GET /api/agents/{id}`, `GET /api/calls/stats?agentId=` |
| **Script** | Phase 1 Step 2, extracted verbatim | `GET/PUT .../calling-script`, `POST .../optimize`, `GET .../versions`, `GET .../brain/compiled-preview` |
| **Voice & language** | Phase 1 Step 3 voice, plus primary language with a warning that changing language **regenerates the opening line** | `GET /api/telephony/voice-options`, `PUT .../voice` |
| **Phone** | Phase 1 Step 3 profile + assigned numbers table | `GET/PUT .../telephony-profile`, `GET .../telephony-profile/effective` |
| **Memory** | `memory_schema` selector; what the agent is allowed to remember | `PATCH /api/agents/{id}` |
| **Versions** | Compiled brain history with token counts and rollback | `GET .../versions` |

## 7.4 The duplication problem — fix it in this phase

`web/app/app/(console)/agents/[id]/*` and `web/app/dev/(portal)/agents/[id]/*` are **the same eight pages written twice**. Extract every page body into `web/components/agents/tabs/*.tsx` (above), then have both route trees be thin wrappers that render the shared tab with a `portal: "app" | "dev"` prop. This must happen in Phase 2 or every later phase is written twice.

## 7.5 Acceptance criteria — Phase 2

1. `New agent` and every row action work without leaving the console.
2. A `Not activated` agent is visually distinct and the customer can reach the fix in one click.
3. Duplicating an agent does **not** produce a live-billing agent by accident.
4. The eight agent sub-pages exist in exactly one implementation.
5. Deleting requires a typed confirm that names the agent.
6. All lifecycle actions respect the caller's permission; a read-only member sees disabled controls with a tooltip, not a raw 403.

---

# PHASE 3 — Numbers, Inbound and Outbound

**Goal:** A customer can buy or attach a number and decide exactly when and how their agent answers — with no telephony vocabulary exposed.

## 8.1 Files to create

```
web/app/app/(console)/numbers/page.tsx
web/components/numbers/NumberTable.tsx
web/components/numbers/NumberSearchDialog.tsx
web/components/numbers/BuyNumberDialog.tsx
web/components/numbers/AssignNumberDialog.tsx
web/components/numbers/NumberRoutingToggles.tsx
web/components/numbers/NumberStatusBadge.tsx   pending | active | provisioning | failed | released
web/lib/numbers.ts                              typed wrapper, e164 formatting helpers
```

Port the UX of `voxly-ai/src/console/modules/PhoneNumbersModule.jsx` and `TelephonySettingsCard.jsx`; neither needs redesign.

## 8.2 `/numbers`

Header: `Numbers` + primary **"Buy a number"**. Below, a secondary link **"Add an existing number"** (see RISK-3).

`SkeuoTable` columns: Number (formatted, copy-to-clipboard), Assigned agent, Status, Inbound, Outbound, Monthly, Actions.

- **Inbound / Outbound** columns are two inline toggles per row calling `PUT /api/telephony/numbers/{id}/routing` with `{inboundEnabled}` / `{outboundEnabled}`. This is the single most-used control in the category after "assign" — it must be one click, not a dialog.
- **Actions:** Assign to agent (dialog listing agents + search), Release number, View purchase.
- `GET /api/telephony/numbers` — cache the list in `useAdminResource`; both toggles and assign mutate optimistically and roll back on error.
- Numbers with `released_at !== null` are excluded from the default list and available under a "Released" filter.

`BuyNumberDialog`:
1. `GET /api/telephony/numbers/search?country=IN&areaCode=&pattern=` (debounced 400ms)
2. Results table: number, monthly, setup, total first month
3. Select → confirm panel showing current `GET /api/billing/wallet` balance, the charge, and the balance after. If insufficient → disable and render a `SkeuoEmptyState` linking to `/billing`.
4. `POST /api/telephony/buy` `{e164, country:"IN", payMethod:"wallet", assignAgentId?}`
5. Success → row appears with **Provisioning** badge. Poll `GET /api/telephony/numbers` every 10s until `status` leaves `pending`, max 2 minutes, then tell the customer to refresh. Never leave a spinner running forever.

`NumberStatusBadge` states and their copy — the customer must always know whether the number works:
- `pending` → amber **Provisioning** — "Setting up. This usually takes under a minute."
- `active` → green **Active**
- any failure → red **Action needed** — with the provider message.

## 8.3 Inbound routing model

Inbound calls arrive on a number and must reach exactly one agent. That is `PhoneNumber.agent_id`.

- An unassigned number with `inbound_enabled: true` has nowhere to route. **Warn on the numbers page**: "Inbound is on for 2 numbers with no agent. Callers will hear nothing."
- Validation: an agent cannot have `inbound_enabled: true` with zero assigned numbers. The Phone tab shows this as a blocking `SkeuoEmptyState` with a direct link to `/numbers`.
- `GET /api/agents/{id}/telephony-profile/effective` gives the merged view (agent profile + number overrides) and should be what the Phone tab renders, not the raw profile, so the customer sees what is actually in force.

## 8.4 Inbound vs outbound — the mental model

State this in the UI copy, once, on the Phone tab:

> **Inbound** — someone calls your number and your agent answers.
> **Outbound** — your agent calls out to a list or a single number.

Everything else in this phase hangs off those two toggles. Do not introduce a third concept.

## 8.5 Outbound guardrails (must be visible, not just enforced)

Before a customer can start an outbound campaign or place an outbound call, surface a readiness check on the agent's Phone tab and in the Campaign form:

- Agent has `outbound_enabled: true`
- At least one number with `outbound_enabled: true` is assigned
- A calling number is selected (`fromE164`)
- DNC list is loaded

Show these as four `SkeuoStatusLight` rows. Block the action, and link to the fix for each failing row. Hiding this until the dial fails is how customers lose trust in an outbound product.

## 8.6 Acceptance criteria — Phase 3

1. Buy → provision → assign → toggle inbound/outbound works end to end without a page reload.
2. A number with inbound on and no agent shows a visible warning.
3. An agent with inbound on and no number cannot be saved into that state silently.
4. The outbound readiness check appears before any dial attempt and blocks with a fix link.
5. Provisioning never leaves an infinite spinner.

---

# PHASE 4 — Calls: History, Detail, Recordings, Objectives

**Goal:** After a call, the customer can answer "what happened, what was said, what did we get, what did it cost" without support.

## 9.1 Files to create

```
web/components/calls/CallFilters.tsx
web/components/calls/CallTable.tsx
web/components/calls/CallStatusBadge.tsx
web/components/calls/CallSummaryHeader.tsx
web/components/calls/TranscriptPanel.tsx
web/components/calls/RecordingPlayer.tsx
web/components/calls/CallOutcomePanel.tsx
web/components/calls/CallObjectivePanel.tsx
web/components/calls/CallCapturedFields.tsx
web/components/calls/CallCostPanel.tsx
web/components/calls/CallbackButton.tsx
web/lib/recording.ts                             audio-status polling
```

`app/(console)/calls` and `calls/[id]` already exist — **extend them, do not rewrite.** Reuse `web/lib/call-list-utils.ts`, `call-detail-types.ts`, `call-timeline-utils.ts`, `transcript-source.ts`, `usage-cost.ts`.

## 9.2 `/calls` — history

`GET /api/calls` is already tenant-scoped (`resolve_calls_tenant_id`) and already supports: `agentId`, `status` (comma-separated, canonical vocabulary from `server/call/call_status.py`), `direction` (`inbound|outbound`), `since`, `until`, `limit`, `offset`, `include_attempts`, `disposition`.

Filter bar (`SkeuoPanel`, single row, all optional):
Agent · Direction (All / Inbound / Outbound) · Status (multi-select from the `statuses` array the endpoint returns — do not hardcode) · Date range · **Include unanswered attempts** toggle (default on).

`SkeuoTable`: Started · Direction (icon) · Agent · Peer (masked by default, reveal on click) · Status · Duration · Disposition · Cost · Recording icon.

Two behaviours that matter:
- **Never-answered ringing attempts** are included by default and must render in the same row shape, greyed, or the customer will think calls vanished.
- **Masking:** show `+91 •••••• 1234` by default with a reveal toggle. Peers are not the customer's employee.

Pagination via `limit`/`offset` with a page-size selector (25/50/100).

## 9.3 `/calls/[id]` — detail

Header `SkeuoPanel`: direction, agent, peer, start, duration, status badge, disposition, cost breakdown (`web/lib/usage-cost.ts` → `costLlmUsd`-equivalent, already implemented client-side).

Tabs:

**Transcript** — `GET /api/call/{id}/transcript`. Speaker-labelled turns, timestamps, search. Toggle to show/hide internal notes. Reuse `transcript-source.ts` for the websocket-vs-rest fallback.

**Recording** — the player. There is **no recording-list or signed-URL endpoint**; only `GET /api/call/{id}/audio` and `GET /api/call/{id}/audio-status`. Therefore:
1. On mount, poll `audio-status` every 5s, max 2 minutes.
2. States: `processing` (spinner + "Recording is still processing"), `ready` (render `<audio controls src={/api/call/{id}/audio}>`), `unavailable` (`SkeuoEmptyState`: "No recording for this call."), `failed`.
3. Playback speed control (0.75/1/1.25/1.5/2) — a small thing that customers ask for constantly.
4. Click-to-seek in the transcript highlights the audio position.

**Outcome** — `GET /api/call/{id}/outcome`. Shows the structured result. `POST /api/call/{id}/outcome/retry` is available to admins only; hide it for members.

**What we captured** — `GET /api/call/{id}/memory` and `/memory/projection`. This is the customer-visible answer to "what did the agent learn": name, interest, callback preference, and anything else the memory schema allows. `POST /api/call/{id}/memory/correction` lets a human correct a misheard field — this is important and often missing in competitors.

**Cost** — `GET /api/metrics/calls/{id}`. Duration, audio tokens, LLM cost, TTS, STT, total, cost per minute.

**Trace** — `GET /api/call/{id}/trace` and `/audio-status`. **Dev portal only.** Do not render this in the console.

**Actions in the header:**
- **Call back** → `POST /api/calls/{id}/callback` `{toE164?, agentId, fromE164?, mode:"manual"}`. Only enabled when the call has a reachable peer. `GET /api/calls/{id}/callbacks` lists prior callbacks.
- **Create lead** → Phase 5, `POST /api/leads`, pre-filled from the captured fields.
- **Download transcript** — client-side text export.

## 9.4 Call objective

The product already computes a per-call objective/outcome. Surface it as a first-class card, not a row in a table:

> **Outcome:** Callback requested · **Captured:** Name, Preferred time · **Next step:** Callback by 6 PM

This is what a business owner actually opens the console to see. Put it at the top of the call detail and in the calls list as a one-line summary.

## 9.5 Acceptance criteria — Phase 4

1. Filters map 1:1 to `GET /api/calls` query params; the URL carries the filter state so a filtered view is shareable and survives reload.
2. A call with no recording shows an explanation, never a broken player.
3. Recording polling terminates in all four terminal states.
4. Peer numbers are masked by default.
5. A human can correct a misheard field from the call detail, and the correction persists.
6. No internal ids, traces or token counts appear in the tenant console.

---

# PHASE 5 — Campaigns and Leads

**Goal:** A customer can run an outbound campaign end to end and work the resulting leads — without the product ever making a call the customer did not intend.

## 10.1 Files to create

```
web/app/app/(console)/campaigns/page.tsx
web/app/app/(console)/campaigns/[id]/page.tsx
web/app/app/(console)/leads/page.tsx
web/components/campaigns/CampaignTable.tsx
web/components/campaigns/CampaignCreateDialog.tsx
web/components/campaigns/ContactImport.tsx
web/components/campaigns/CampaignControls.tsx     start | pause | cancel
web/components/campaigns/CampaignAnalytics.tsx
web/components/campaigns/DncManager.tsx
web/components/campaigns/CampaignReadiness.tsx   ← the guardrail
web/components/leads/LeadPipeline.tsx            kanban
web/components/leads/LeadTable.tsx
web/components/leads/LeadDetailDrawer.tsx
web/components/leads/StageSelect.tsx
web/app/app/(console)/contacts/page.tsx
web/lib/campaigns.ts
web/lib/leads.ts
```

Port `voxly-ai/src/console/modules/CampaignsModule.jsx` and `LeadsModule.jsx`; the backend is complete.

## 10.2 Campaigns — `/campaigns`

`GET /api/campaigns`. Table: Name · Agent · Status · Contacts · Concurrency · Progress · Created.

Status vocabulary from `Campaign.status` default `"draft"`, plus the transitions exposed by `PATCH /api/campaigns/{id}/status`, `POST .../start`, `.../pause`, `.../cancel`. Render with `SkeuoStatusLight`: draft grey, scheduled/running green, paused amber, completed blue, cancelled/failed red.

**Create dialog** — `POST /api/campaigns` `{name, agentId, concurrency}`. `concurrency` = simultaneous dials, default 5, slider 1–20 with the label **"How many calls can run at the same time"** (no "concurrency").

**Contact import** — `POST /api/campaigns/{id}/contacts/import`. Accept CSV upload and paste. Per-row validation with a downloadable error report. This is the step where every customer loses trust if it is a single opaque error, so the response must be per-row: accepted, duplicate, invalid format, already on DNC.

**DNC** — `GET /api/dnc`, `POST /api/dnc {phone_e164, reason?}`. A `SkeuoTable` with manual add, bulk paste, and delete. Every import screen must check against it and say so.

**`CampaignReadiness`** — reuse the Phase 3 outbound check, extended: agent `outbound_enabled`, a number with `outbound_enabled`, `fromE164` selected, DNC list loaded, at least one contact. Render as five `SkeuoStatusLight` rows with a fix link each. **The Start button is disabled until all five pass.** Do not let a customer discover a broken campaign by watching calls fail.

**Analytics** — `GET /api/campaigns/{id}/analytics`. Show: contacts, dialled, answered, connect rate, qualified, booked, cost, cost per qualified lead. Cost per qualified lead is the number a business owner decides on; put it largest.

## 10.3 Leads — `/leads`

`GET /api/leads`. Two views, one data source, toggled by a `SkeuoNavItem` group — **not** two pages:

**Pipeline (default).** Kanban with columns from the stage vocabulary, default `new`. Drag a card to change stage → `PATCH /api/leads/{id}/stage`. Show name, phone (masked), source campaign, created-ago. Card click opens `LeadDetailDrawer`.

**Table.** All leads, sortable by created/name/stage, with inline stage `StageSelect`, search and a stage filter.

`LeadDetailDrawer`: name, phone, email, stage, notes (`PATCH /api/leads/{id}`), source call (link to `/calls/{id}`), and the captured fields the agent learned. The captured-fields block is the payoff of Phase 4 — link it.

**Per-call lead capture (required by the brief).** From `/calls/[id]`, **Create lead** opens the drawer pre-filled from `GET /api/call/{id}/memory`. `POST /api/leads {name, phone?, email?, stage?, notes?}`. The notes field is pre-seeded with a one-line summary and a link back to the call. This is the loop that makes leads worth having: call → capture → lead → follow up.

## 10.4 Contacts

`GET/POST /api/telephony/contacts` `{name, phone, notes?}`, `PATCH /api/telephony/contacts/{id}`, `DELETE /api/telephony/contacts/{id}`. A simple `SkeuoTable` with an add dialog and CSV import. Contacts are the source list campaigns draw from.

## 10.5 Acceptance criteria — Phase 5

1. A campaign cannot be started unless all five readiness checks pass, and each failure links to its fix.
2. Contact import reports per-row outcomes and never fails opaquely.
3. DNC entries are blocked at import and at dial.
4. A lead created from a call carries the agent's captured fields.
5. Kanban and table stay in sync without a page reload.
6. Campaign analytics shows cost per qualified lead.

---

## 11. Risks and open decisions

| # | Risk | Impact | Resolution |
|---|---|---|---|
| **RISK-1** | `/api/instructions` has no tenant guard (BLOCKER-A) | Cross-tenant compile/session access from the console | Console uses only `compose-onboarding` + `build-employee`. Add a CI grep check. |
| **RISK-2** | `build-employee` hardcodes voice `marin`, and accepts **no** `direction`, `role` or company name (`app_agents.py:74-81`) | The wizard cannot express inbound, role, or a chosen voice | **Backend change required before Phase 1 ships.** Extend `BuildEmployeeBody` with `callDirection`, `agentRole`, `companyName`, `voiceConfig`. Without it, Steps 1 and 3 cannot be wired. |
| **RISK-3** | No endpoint exists to import an existing/BYO number. `POST /api/telephony/buy` only *buys* | "I already have a number" is impossible; this is a real purchase blocker for anyone with an existing number | Either add `POST /api/telephony/numbers/import`, or ship the option disabled and labelled "Coming soon". Do not fake it. |
| **RISK-4** | No tenant-scoped recording endpoint; only `GET /api/call/{id}/audio` | A user who learns a call id could pull another tenant's audio | Wrap in a tenant-scoped `GET /api/app/calls/{id}/recording`. **Do before Phase 4 ships.** |
| **RISK-5** | `app/(console)/agents/[id]/*` and `dev/(portal)/agents/[id]/*` are duplicated | Every later phase is written twice | Resolved in Phase 2 §7.4. |
| **RISK-6** | `/api/campaigns`, `/api/calls` and `/api/leads` use `require_api_tenant`, a different auth mechanism from `require_subscriber_jwt` | Two auth paths; permission granularity may diverge | Confirm both resolve the same tenant for an app session before Phase 5. |
| **RISK-7** | Lead `stage` is a free string with default `"new"`; no vocabulary endpoint | Kanban columns are undefined | Define the stage list in the frontend and ship it; add a vocabulary endpoint later. |

**Open product decisions for the customer:**
1. Do we sell numbers only, or support BYO? (gates RISK-3)
2. Is the console for business owners only, or do we expose agent-builder controls to non-admin members? (determines whether RBAC-gated buttons or separate roles)
3. Do inbound campaigns exist as a first-class object, or is inbound simply "a number + a profile"? Current backend models inbound as the latter; building a separate inbound campaign object is a much larger scope.

---

## 12. Explicitly out of scope

- Any change to `web/app/dev/**` beyond the Phase 2 dedup.
- Any change to `voxly-ai/`. It is a reference and a source of ported UX only.
- Changing the agent-creation **backend** flow. Phase 1 wires up what exists; RISK-2 is the one exception and is scoped to extending an existing body, not redesigning the compiler.
- Billing top-up flows, member invitations and RBAC screens — the backend exists (`app_billing.py`, `app_auth.py`); port them after Phase 5 as a Phase 6.
- Prompt/brain optimisation. The brain is now 2,877 tokens and under budget; nothing in this spec changes it.

---

## 13. Build order and dependencies

```
Phase 1  Creation wizard        → needs RISK-2 resolved
Phase 2  Agent management       → needs Phase 1 (reuses its panels)
Phase 3  Numbers + routing      → independent of 1 and 2
Phase 4  Calls + recordings     → needs Phase 2 (agent filter), needs RISK-4
Phase 5  Campaigns + leads      → needs Phase 3 (outbound readiness) and 4 (lead capture)
```

Phases 1, 2 and 3 can run in parallel by different engineers once RISK-2 lands. Phases 4 and 5 are strictly sequential after them.
