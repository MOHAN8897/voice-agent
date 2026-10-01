# Agent workspace UI redesign (voxly-ai frontend only)

**Status:** Mostly implemented in `voxly-ai` (P0–P3). Doc header previously said “spec only” — that is outdated.  
**Remaining:** P4 shadcn polish optional; keep §8 deferred items out of UI.  
**Date:** 2026-10-01 (revised — frontend-only scope locked; status refreshed 2026-10-01)  
**App:** `voxly-ai/` (Vite React console the customer opens after login)  
**UI kit:** Prefer [shadcn/ui](https://ui.shadcn.com/) inside this Vite app only (P4 not done — still custom craft UI)  

---

## 0. Non-negotiable scope (read first)

### 0.1 In scope — change only these places

All work is **frontend UI/UX recombination** under:

```
voxly-ai/src/console/modules/AgentStudioModule.jsx
voxly-ai/src/console/modules/EmployeesModule.jsx
voxly-ai/src/console/modules/TelephonySettingsCard.jsx
voxly-ai/src/console/modules/CallsModule.jsx          ← reuse / extract agent-scoped UI only
voxly-ai/src/console/modules/LeadsModule.jsx          ← reuse / extract agent-scoped UI only
voxly-ai/src/console/modules/TalkToAiConsole.jsx      ← open as modal/drawer, not a top tab
voxly-ai/src/console/modules/agent-creation/*         ← labels, defaults, chips, copy only
voxly-ai/src/console/employeeFlowHash.js              ← tab ids for Open builder hash
voxly-ai/src/console/Topbar.jsx                       ← step labels for employee flow only
voxly-ai/src/console/AppShell.jsx                     ← only if needed to mount the new shell
voxly-ai/src/lib/callStatus.js                        ← display labels only
voxly-ai/src/lib/voicePresets.js / voiceDisplay.js    ← display grouping only
voxly-ai/src/services/api.js                          ← call existing endpoints only; no new routes
voxly-ai/src/services/agentBrain.js                   ← keep using current brain load/save
voxly-ai/src/console/context/WorkspaceContext.jsx     ← filter/aggregate client-side if needed
(+ optional new files under voxly-ai/src/console/modules/agent-workspace/ for the five tabs)
(+ optional shadcn components under voxly-ai/src/components/ui/)
```

### 0.2 Out of scope — do not touch

| Area | Paths / systems | Why |
|------|-----------------|-----|
| **Backend Python API** | Entire `server/` tree | Call behaviour, PSTN, hangup, brain compile, billing already work |
| **Backend admin API** | `server/routes/app_admin.py`, `/api/admin/*` | Platform admin is separate |
| **Next.js admin / dev portal** | Entire `web/` tree (`web/app/dev/admin`, Test Studio, agent brain pages) | Different product surface |
| **voxly-ai Platform admin UI** | `voxly-ai/src/console/modules/AdminModule.jsx` | Do not redesign or restyle |
| **Agent working flow** | Live inbound/outbound PSTN, hangup state machine, brain compiler, Gemini/OpenAI live session, Telnyx bridge | Must keep working exactly as today |
| **New HTTP endpoints** | Anything not already in `voxly-ai/src/services/api.js` | Frontend must use existing APIs |
| **DB migrations / models** | `server/db/**` | No schema work |
| **Fleet Overview / Billing / Campaigns / Integrations / Settings (workspace)** | Those console tabs stay as they are unless a tiny label fix is required | This redesign is **Open builder → agent workspace** only |

### 0.3 Hard rule for implementers

1. **No backend commits** in this effort.  
2. **No changes** to how a live call is answered, spoken, hung up, billed, or recorded.  
3. **No fake controls** that look saved but do not map to an existing API field.  
4. If a US/EU “best practice” needs a field the API does not store today → put it in **§8 Deferred (needs backend later)** — do **not** build it in this UI pass.  
5. Existing APIs already enforce telephony; the UI only **rearranges** how the subscriber edits the same payload.

### 0.4 What “work properly” means here

- Open builder still opens the selected agent.  
- Save still persists via the **same** existing endpoints listed in §3.  
- Inbound still uses the saved telephony profile (server already does this — UI must keep sending the same field names).  
- Script / voice save still update the published brain the same way `AgentStudioModule` / `api.agents.saveCallingScript` / `api.agents.saveVoice` do today.  
- Outbound dial / callback still use `api.calls.triggerOutbound` and `api.calls.callback`.  
- Lead stage edits still use `api.leads.updateStage` / `updateNotes`.  
- Platform admin (`AdminModule`) and all of `server/` remain unchanged and still work.

---

## 1. Goal (UI only)

Replace the current Open-builder tab strip:

`Script & flow | Voice | Phone lines | Live test | Knowledge`

with five customer-facing tabs:

| New tab | Job | Built from (already in frontend) |
|---------|-----|----------------------------------|
| **Overview** | Per-agent analytics | `api.calls.stats`, `api.calls.list({ agentId })`, workspace `leads` filtered by agent |
| **Script** | Edit calling script | Current script editor + `api.agents.saveCallingScript` / brain load |
| **Calls** | History + leads + phone hours | `CallsModule` + `LeadsModule` + `TelephonySettingsCard` scoped to this agent |
| **Voice** | Voice pick / speed / preview | Current voice panel + `api.telephony.getVoiceOptions` + `api.agents.saveVoice` |
| **Settings** | Agent name, language, status, assign number | `api.agents.update`, `api.telephony.assignNumber`, number list from workspace |

**Test call** is a **header button** that opens `TalkToAiConsole` (modal/drawer). It is **not** a top-level tab.

---

## 2. Current Open-builder audit (verified in repo)

### 2.1 Entry

- List: `EmployeesModule.jsx` → button **Open builder** → `openWorkbench(agent.id, 'script')`  
- Hash steps: `employeeFlowHash.js` → `EMPLOYEE_FLOW_STEPS = ['script','voice','telephony','test']`  
- Shell: `AgentStudioModule.jsx` → `FLOW_TABS` (adds **Knowledge** in UI; knowledge is not in the hash list)

### 2.2 APIs the frontend already calls (reuse these — do not invent)

From `voxly-ai/src/services/api.js` (verified):

| Need | Existing client method | Endpoint |
|------|------------------------|----------|
| List / get agent | `api.agents.list` / `get` / `update` | `GET/PATCH /api/agents…` |
| Load script + voice config | `api.agents.getBusinessBrain` / `agentBrain.loadAgentBrain` | `GET /api/agents/{id}/business-brain` |
| Save script | `api.agents.saveCallingScript` | `PUT …/business-brain/calling-script` |
| Save voice | `api.agents.saveVoice` | `PUT …/business-brain/voice` |
| Telephony profile get/save | `api.agents.getTelephonyProfile` / `saveTelephonyProfile` | `GET/PUT …/telephony-profile` |
| Effective hours decision | `api.agents.getEffectiveTelephony` | `GET …/telephony-profile/effective` |
| Voice catalog | `api.telephony.getVoiceOptions` | `GET /api/telephony/voice-options` |
| Numbers / assign | `api.telephony.getNumbers` / `assignNumber` / `buyNumber` | existing telephony routes |
| Call history | `api.calls.list({ agentId, status, direction })` | `GET /api/calls?agentId=…` |
| Call stats | `api.calls.stats({ agentId, since, until })` | `GET /api/calls/stats` |
| Transcript / outcome / audio | `api.calls.transcript` / `outcome` + existing mix URL in `CallsModule` | existing |
| Outbound | `api.calls.triggerOutbound` | `POST /api/calls/outbound` |
| Callback missed | `api.calls.callback` | `POST /api/calls/{id}/callback` |
| Leads | `api.leads.list` / `updateStage` / `updateNotes` / `create` | existing |

### 2.3 Telephony fields the UI may edit (server already accepts)

`TelephonySettingsCard` already saves exactly:

- `greetingPhrase`  
- `businessHours` (per weekday windows)  
- `timezone` (IANA string; server validates via `ZoneInfo`)  
- `afterHoursAction`: `voicemail` \| `hangup` \| `transfer` \| `always`  
- `transferNumber`  
- `inboundEnabled`  
- `outboundEnabled`  

Frontend default today: `timezone: 'Asia/Kolkata'` in `TelephonySettingsCard.jsx` `DEFAULT_PROFILE`.  
**Allowed UI change:** default new/empty profiles in the **frontend** to `America/New_York` or `Europe/London` based on a **UI-only region picker** — still sending the same field names. Do not change `server/services/saas/telephony_profile.py` `DEFAULT_TIMEZONE`.

### 2.4 Call statuses the UI may filter (already canonical)

From `voxly-ai/src/lib/callStatus.js` / server vocabulary:

`answered | missed | outbound | declined | failed | voicemail | in_progress`

Do **not** invent new server statuses in this pass. Extra “tags” in the UI must either:

- map to these statuses, or  
- map to **lead stages** already used in `LeadsModule` (`New`, `Contacted`, `Qualified`, `Meeting Booked`, `Unqualified`), or  
- stay display-only from `api.calls.outcome` if that payload already returns a disposition.

### 2.5 Lead stages already supported

`LeadsModule` + `api.leads.updateStage` — keep this vocabulary. Adding “Do not call” as a stage is **only** allowed if the existing stage API already accepts that string; otherwise keep DNC as a **notes/convention** or omit until backend exists (§8).

---

## 3. Target UI structure (hash + tabs)

### 3.1 New hash steps

Update **only** in `employeeFlowHash.js` + `AgentStudioModule` + `Topbar` labels:

```
EMPLOYEE_FLOW_STEPS = ['overview', 'script', 'calls', 'voice', 'settings']
```

Legacy mapping (frontend-only redirects):

| Old `step=` | Opens |
|-------------|--------|
| `script` | `script` |
| `voice` | `voice` |
| `telephony` | `calls` with Call settings sub-panel focused |
| `test` | `overview` + open Test call modal |
| missing / Open builder | `overview` (new default) |

### 3.2 Shell layout (all inside `AgentStudioModule` or split under `agent-workspace/`)

```
[ ← Back to fleet ]  Agent switcher  Status  [ Test call ]  [ Save ]
[ Overview | Script | Calls | Voice | Settings ]
<tab body>
```

No change to `AdminModule`, Sidebar admin entry, or fleet modules beyond Open-builder entry labels if needed (“Open builder” → “Edit agent” is optional copy).

---

## 4. Page specs (frontend only, wired to existing APIs)

### 4.1 Overview

**Purpose:** Per-agent dashboard (not fleet `OverviewModule`).

**Data (client-side):**

- `api.calls.stats({ agentId, since, until })` for KPIs when available  
- Fallback: `api.calls.list({ agentId, limit })` + aggregate in the browser (same pattern as fleet `OverviewModule`)  
- Leads: from `useWorkspace().leads` filtered where `lead.agentId === selectedAgentId` (field already normalized in `apiNormalize.js`)

**UI (shadcn):** range toggle Today / 7d / 30d; KPI cards; simple chart from aggregated lists; “Recent calls” table (link into Calls tab); “Recent leads” table.

**Do not:** change fleet `OverviewModule.jsx` behaviour for all agents (optional later; not required).  
**Do not:** invent cost/sentiment metrics the API does not return — only show fields present on call/lead objects or stats response.

---

### 4.2 Script

**Purpose:** Same editor as today; clearer US/EU copy.

**Keep behaviour:**

- Load via existing brain load path in `AgentStudioModule`  
- Save via existing `updateAgent` / `saveCallingScript` / publish path already used  

**UI changes only:**

- Rename tab to **Script**  
- Plain-language helper text (disclosure examples as **editable script text**, not new API fields)  
- Fold Knowledge content into an accordion titled FAQ / objections (current objection rules UI)  
- Variable chips stay  

**Do not:** change brain section schema, compiler, or `server/brain/**`.

---

### 4.3 Calls (three sub-panels — same page)

Sub-tabs (UI only): **History | Leads | Call settings**

#### History

- Reuse `CallsModule` patterns with `agentId` **locked** to the open agent (`api.calls.list({ agentId })`).  
- Keep status tabs from `CALL_STATUS_TABS`.  
- Keep recording player, transcript, outbound dial, **Callback** (`api.calls.callback`) — already implemented.  
- CSV export: client-side from loaded rows only (no new endpoint).

#### Leads

- Reuse `LeadsModule` UI filtered to this agent.  
- Stage changes via `updateLeadStage`.  
- “Call now” via existing `triggerCallToLead` in `WorkspaceContext` (same outbound path).

#### Call settings

- Embed existing `TelephonySettingsCard` (same save payload).  
- UI defaults / labels for US-EU (timezone dropdown favourites: `America/New_York`, `America/Chicago`, `America/Los_Angeles`, `Europe/London`, `Europe/Dublin`, `Europe/Berlin` — all valid IANA; server already accepts any valid zone).  
- Explain inbound flow in help text that matches **what the server already does** with `afterHoursAction` (`voicemail` / `hangup` / `transfer` / `always`).  

**Do not add UI for** (not in current telephony profile API):

- Max attempts / day  
- National DNC / TPS scrub toggles that call external registries  
- Consent database fields  
- SMS after-hours (unless already an `afterHoursAction` value — it is **not**; only the four actions above)  
- Missed-call auto-dialer policies beyond using existing **manual** `callback` from History  

Missed-call **management** in this pass = list Missed filter + Callback button (already exists). Not a new automation engine.

---

### 4.4 Voice

**Purpose:** Friendlier controls mapped to **existing** `saveVoice({ voiceId, speed, language })` + voice catalog from `getVoiceOptions`.

**UI only:**

- Group catalog voices as Female / Male / Neutral by **label heuristics in the frontend** (`voiceDisplay.js`) — do not change catalog API  
- Speed slider → existing `speed`  
- Language select → existing language codes already used (`en-US`, `en-GB` if present in options; prefer putting `en-US` first in **frontend** lists in `agent-creation/index.js` / voice presets)  
- Preview: existing `voiceAgent.playTTS` path  

**Do not:** change live voice pipeline in `server/`.

---

### 4.5 Settings

**Purpose:** Agent identity + number assignment (not dialer physics).

**Allowed fields (existing APIs):**

| UI field | Persist with |
|----------|----------------|
| Agent name | `api.agents.update({ name })` |
| Status Active/Paused | `api.agents.toggleStatus` / `update({ status })` |
| Language | `api.agents.update({ languages })` and/or `saveVoice({ language })` — use the **same path AgentStudio already uses** on save; do not invent a third |
| Assigned number | `api.telephony.assignNumber` / unassign (workspace already has `assignNumberToAgent`) |
| Buy number CTA | Navigate to existing buy-number flow (`onOpenBuyNumber`) — do not rebuild provisioning |

**Role / business name:**

- If currently stored only on the client agent object / script text, keep editing where data already lives (agent `role` in form state + script).  
- Do **not** add `website`, `support email`, `data retention days`, `notification prefs` unless an existing PATCH body already supports them (today `api.agents.update` sends `name`, `status`, `languages` only — verified). Extra identity copy belongs in the **Script** text until a backend field exists (§8).

---

## 5. US / EU standards — how they apply in a frontend-only pass

Use standards as **defaults, labels, and help text**, not as new enforcement engines.

| Standard (research) | Frontend-only action now | Not in this pass |
|---------------------|--------------------------|------------------|
| US calling window 8am–9pm callee local | Help text next to business hours; suggest Mon–Fri 09:00–17:00; timezone default `America/New_York` in UI | Server-side clamp of outbound dial |
| AI voice consent (TCPA) | Script template sentences the user can keep | Consent store / hard dial block |
| UK CLI / identify business | Settings shows assigned number; Script opening line | New CLI force API |
| TPS/CTPS / National DNC | Help link + reminder copy | Live registry scrub |
| Recording disclosure | Script snippet suggestion | New recording-consent flag |
| Missed call follow-up | History → Callback (existing API) | Auto-queue / SMS |

Product peers (Retell/Vapi) inform **layout** (Overview + Calls + Script + Voice + Settings), not new backend features.

---

## 6. File change checklist (allowed)

| File | Change |
|------|--------|
| `AgentStudioModule.jsx` | Replace `FLOW_TABS`; compose five tab bodies; Test call modal |
| `employeeFlowHash.js` | New step ids + legacy redirects |
| `Topbar.jsx` | `EMPLOYEE_STEP_LABELS` only |
| `EmployeesModule.jsx` | Default open step `overview`; optional button label |
| `TelephonySettingsCard.jsx` | Default TZ in **frontend** `DEFAULT_PROFILE`; timezone favourites; clearer copy; remain embeddable |
| `agent-creation/index.js` | `en-US` first in language list; US/UK industry chip copy; placeholders — **no new create APIs** |
| New `agent-workspace/*` | Optional split of Overview/Script/Calls/Voice/Settings components |
| shadcn under `voxly-ai` | Optional UI primitives for these pages |

## 7. Explicit do-not-edit list

```
server/**                         # entire backend
web/**                            # Next admin, Test Studio, app console
voxly-ai/src/console/modules/AdminModule.jsx
server/services/pstn_realtime_voice_core.py
server/services/saas/telephony_profile.py   # do not change DEFAULT_TIMEZONE or evaluate_inbound_policy
server/call/**                    # hangup / validate / ledger
server/brain/**                   # compiler
server/routes/**                  # no new routes
```

(Creating **new** UI files under `voxly-ai/src/console/...` is fine. Editing the forbidden list above is not.)

---

## 8. Deferred (needs backend later — do not fake in UI)

Do **not** ship toggles for these until APIs exist:

- National DNC / TPS-CTPS automated scrub  
- Consent ledger + hard outbound gate  
- Max dial attempts per day/week  
- SMS / email after-hours channels  
- Auto missed-call campaign  
- Recording retention policy storage  
- Business website / support email / GDPR retention as first-class agent fields  
- New lead stage `Do not call` unless API stage enum expands  
- Currency conversion / USD billing display beyond what wallet payload already returns  

### 8.1 Found while building this pass (2026-10-01)

- **Leads have no agent link.** `server/db/models/saas_models.py::Lead` has no
  `agent_id`, and `GET /api/leads` never returns one, so "leads for this agent" cannot be
  answered today. §4.1/§4.3 assumed a normalized `lead.agentId` that `apiNormalize.js`
  reads but the API never populates. The Calls → Leads panel and the Overview leads card
  therefore filter on `agentId` (correct the day the field exists) and fall back to the
  real workspace pipeline with a visible note, rather than showing a permanently empty
  board. Needs a backend field plus `lead_agent_id` on list responses.
- **`api.agents.update` sends only `name`, `status`, `languages`.** Settings therefore has
  no website, support email, role or retention field. Those stay in the Script text until
  the PATCH body grows them (§4.5).
- **The old Knowledge tab was dead UI.** It read `selectedAgent.knowledgeSources`, which
  `apiNormalize.js` never sets, and its "Upload Document" button had no `onClick` — no
  method in `api.js` uploads documents. Deleted rather than re-skinned, per §0.3 rule 3.
  Its one real artefact (objection rules) already lives on the Script tab.  

Document them here only so product does not confuse “UI redesign” with “compliance engine.”

---

## 9. Implementation phases (frontend only)

| Phase | Deliverable | Status (2026-10-01) | Success check |
|-------|-------------|---------------------|---------------|
| **P0** | Five-tab shell + hash migration + Overview KPIs from existing stats/list | ✅ `FLOW_TABS`, `employeeFlowHash.js`, `agent-workspace/AgentOverview.jsx` | Open builder → Overview; old `?step=telephony` lands on Calls settings |
| **P1** | Calls = History (agent-scoped) + Leads (filtered) + embedded TelephonySettingsCard | ✅ `AgentCallsPanel.jsx` | Callback, stage change, save hours still hit same APIs |
| **P2** | Script + Voice polish (labels, grouping, en-US first) | ✅ Script/Voice tabs in `AgentStudioModule`; `en-US` first in `voicePresets.js`; `groupPhoneVoices` | Save script/voice; live call still uses published brain unchanged |
| **P3** | Settings = name/status/language/number assign + Test call modal | ✅ `AgentSettingsPanel.jsx` + Test call header → `TalkToAiConsole` modal | Assign number still works; AdminModule untouched |
| **P4** | shadcn styling pass on these five tabs only | ❌ Not started (`voxly-ai/src/components/ui/` absent) | No `server/` or `web/` diffs |

After each phase: smoke Open builder → edit → save → place/test call using **existing** Talk to AI / outbound UI. Confirm platform admin page still loads unchanged.

---

## 10. Acceptance criteria (no ambiguity)

1. Diff for this project contains **only** files under `voxly-ai/` (plus this doc under `docs/`).  
2. Zero changes under `server/` and `web/`.  
3. `AdminModule.jsx` file hash unchanged.  
4. Telephony save body field names unchanged vs today.  
5. Hangup / PSTN / brain compile behaviour unchanged (no backend to change).  
6. Every visible control either reads/writes an endpoint in §2.2 or is pure display/help text.  
7. Five tabs: Overview, Script, Calls, Voice, Settings — Test call is a button.  
8. Agent working flow (create employee, publish script, inbound answer per profile, outbound dial) continues through the **same** APIs as before the UI reshuffle.

---

## 11. Reference (layout inspiration only)

- Retell / Vapi dashboard IA (Overview + call history + agent config)  
- US TCPA/TSR hours & consent — **copy/defaults only** in this pass  
- UK ICO PECR live-call CLI / identify — **copy/defaults only**  
- Internal API surface of truth: `voxly-ai/src/services/api.js`  
- Related (different scope): `docs/SAAS_CONSOLE_FRONTEND_SPEC.md` targets `web/app/app/(console)/` — **not** this workstream
