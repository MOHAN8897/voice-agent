# 08 — Business console (web console for users)

**Shell:** `ConsoleShell` → `InstrumentSidebar` + `ConsoleNav` + `ShellTopBar`.  
**Layout:** `web/app/app/(console)/layout.tsx`.  
**IA:** `prd/11` + `PRIMARY_NAV`.

This is the product customers pay for. Visual language: **Layer B skeuo** ([02](./02-ui-style-system.md)). Stitch “SaaS dashboard” frames restyle this shell; they do not replace the nav model.

## Chrome (every `/app` page)

| Region | Component | Must show |
|--------|-----------|-----------|
| Sidebar | `InstrumentSidebar` | Brand, nav, Profile, Sign out |
| Top bar | `ShellTopBar` | Product “Voice Agent”, **real tenant name**, **real env**, connection status |
| Mobile | `MobileShellHeader` | Same nav |
| Main | max-w-shell | PageHeader + content |

Live indicator: only Test Studio sets nav `status="live"`.

## Overview `/app`

**Code:** `OverviewInstrumentation` + health/metrics `apiGet`.

**Stitch “home dashboard” elements to bind:**

| Widget | Data | Empty |
|--------|------|--------|
| Fleet health | `/api/health` | API down banner |
| Calls today | metrics | “No calls yet — open Test Studio” |
| P50/P95 first-audible | metrics | “—” |
| Failure rate | metrics | “—” |
| Estimated cost | optional | Hide if no billing metadata |
| Active agents | agents list | CTA Create agent |
| Recent calls | last 5 | Link to Calls |
| Setup checklist | local onboarding | Hide when complete |

Do not show provider keys or platform brain.

## Agents `/app/agents`

List: name, language, env version (draft/active), last call, status.  
Primary: **Create agent**.  
Row click → `/app/agents/[id]/summary`.

Create dialog: name, language (`te-IN` default), optional brief.

## Agent workspace `/app/agents/[id]/*`

Tabs from `AGENT_WORKSPACE_TABS`. Shared `AgentWorkspaceNav`.

### Summary

Purpose, language, active version, last test, channel readiness (browser / PSTN). Checklist: brain valid, stack assigned, smoke test, promote.

### Business Brain `/brain`

Eight accordions — `BRAIN_SECTION_LABELS` / `BRAIN_SECTION_ORDER`.  
Editor: `BusinessBrainEditor`.

Per section: title, help, textarea, enabled toggle, token estimate, validation.  
Required: Identity & Purpose, Actions & Limits, Guardrails (`prd/11` §6).  
Actions: Save draft · Preview assembled · Validate · (Publish is Versions, Customer Admin).

Raw text round-trips. Optimizer preview is read-only; never overwrite raw.

### Voice & Models `/voice`

Customer sees **tier** LOW/MEDIUM/PREMIUM (server-resolved). In ENV mode, stack is read-only. FRONTEND mode: enabled STT/LLM/TTS dropdowns from catalog — backend validates (`prd/11` §15).

Cartesia `ink-2` STT must not appear for Telugu.

### Memory Schema `/memory-schema`

Read-mostly schema of memory fields; customers don’t invent arbitrary JSON. Link to call memory inspector.

### Tools & Actions `/tools`

MVP: honest empty — “No tools connected” (`prd/17` CRM future). Don’t fake WhatsApp send.

### Channels `/channels`

Browser always on. PSTN: assigned numbers, Telnyx status, inbound/outbound. First-time auto-assign per `prd/17`.

### Versions `/versions`

Draft / validated / approved / active. Diff. Rollback. Who/when. Promote requires valid brain + stack + smoke test + role.

### Test `/test`

Same Test Studio client, agent locked.

## Test Studio `/app/test-studio`

**The product demo inside the console.** Components under `web/components/test-studio/`.

Required UI:

- Agent + version + language + channel (browser | PSTN)
- Start / Stop
- Call state machine
- Live transcript (user/agent, barge, interrupted)
- Latency waterfall STT → LLM → TTS
- Memory projection panel (`TestStudioMemoryPanel`)
- Fine-tune **only if FRONTEND mode** (`TestStudioFineTuneWorkbench`)
- Cartesia voice select when that TTS is on the stack
- Errors / provider events

Mic denied: explicit permission state. PSTN: show number + “ready” or “not configured”.

## Calls `/app/calls` and `/app/calls/[id]`

**List:** time, channel badge (browser/pstn), duration, tier, disposition color, summary, customer name. Filters: date, disposition, agent, channel (`prd/11` §10).  
`CallsFilterBar`, `CallsListPanel`.

**Detail:** outcome card, audio (`CallAudioPanel`), transcript timeline, memory (`CallMemoryStatePanel`), trace, config snapshot, errors.

Disposition colors: keep a single map (interested = success-tint, not_interested = muted, error = rose).

## Analytics `/app/analytics`

`AnalyticsWorkspace` — aggregate only. Volume, completion, latency P50/P95, quality, errors, cost/usage, disposition trends. Not a trace viewer.

## Benchmarks `/app/benchmarks`

Visible to engineers; **runs disabled until configured** (`prd/17`). UI: explain “no scenarios enabled” empty state rather than a green Start that no-ops.

## Providers `/app/providers`

Safe catalog: provider, model, type, enabled/configured/healthy, languages, pricing **timestamp**. Never secrets.

## Integrations `/app/integrations`

Placeholder: webhooks / CRM “coming later”. Honest.

## Settings `/app/settings`

Retention days, environments legend, members (gap), audit log (gap), link to Billing (gap).

## Profile `/app/profile`

Session, password change (if API), default tenant.

## Campaigns (gap, PRD 18)

When built: `/app/campaigns` list, create (agent, numbers, window, DNC, audience CSV), run status, per-campaign analytics. Honor consent. Outbound > inbound for product value — **add to nav when API exists**.
