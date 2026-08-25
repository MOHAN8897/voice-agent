# 11 — UX, Information Architecture, and Screen Contracts

This document is normative for product behavior and UX on the **Next.js App Router** application in `web/` ([19-frontend-backend-nextjs-railway.md](./19-frontend-backend-nextjs-railway.md)). **No vanilla SPA** in the target product.

The existing `client/` folder is **historical reference** for porting live-voice and barge-in behavior only.

## 1. UX design context

### Users

- Customer business administrator: configures the business brain, voice tier, deployment channel, and reviews call outcomes.
- Voice engineer/developer: configures providers, runs benchmarks, inspects traces, and promotes combinations.
- Prompt/platform administrator: owns the protected platform brain, output rules, optimizer policy, and tenant guardrails.
- Operations/reviewer: reviews calls, dispositions, recordings, quality, and failures.

### Product character

Calm, precise, operational, Telugu-first, and developer-capable. The product should feel like a trustworthy control plane, not a collection of demo controls.

### Design principles

1. Start from the user workflow, not provider settings.
2. Establish hierarchy through spacing, labels, and grouping before color.
3. Show one primary action per task; place advanced controls behind progressive disclosure.
4. Separate customer-editable instructions from protected platform instructions.
5. Always expose state, version, validation, and deployment impact.
6. Keep per-call debugging separate from aggregate analytics.
7. Preserve the current dark-console visual language while improving density, navigation, accessibility, and responsive behavior.

## 2. Current UI evidence

The current client is a single-page vanilla application:

- `client/index.html`: sidebar tabs for Voice Agent, Voice Pipeline, AI Brain, Prompting, CRM & Tools, and Advanced.
- `client/settings.js`: loads a safe server catalog, edits runtime settings, edits one free-form brain prompt, tests TTS/brain, and saves per-session settings.
- `client/console_tabs.js`: query-string tab navigation.
- `client/styles.css`: current dark console, cards, sidebar, pills, fields, and responsive styling.
- `client/app.js`: live microphone, STT WebSocket, brain SSE, TTS WebSocket, transcript, interruption, and client export.

The supplied UI reference shows eight collapsible instruction groups:

1. Identity & Purpose
2. Facts
3. Actions & Limits
4. Flow: qualify buyer
5. Flow: arrange callback
6. Scope & Redirects
7. Guardrails
8. FAQ

This pattern is adopted for customer business logic, with explicit versioning and deterministic compilation.

## 3. Target information architecture

### Primary navigation

1. Overview
2. Agents
3. Test Studio
4. Calls
5. Analytics
6. Benchmarks
7. Providers
8. Integrations
9. Settings

### Agent workspace navigation

1. Summary
2. Business Brain
3. Platform Brain — only platform administrator/developer
4. Voice & Models
5. Memory Schema
6. Tools & Actions
7. Channels
8. Versions & Deployment

### Environment separation

- Development: editable; test calls and draft benchmark sessions.
- Staging: approved configurations only; regression and PSTN tests.
- Production: immutable active version; changes require promotion.

Environment promotion is **in MVP scope** per [`17-product-decisions.md`](./17-product-decisions.md) §2 and §9–10 (dev → staging → production via Dev Portal). Implementation: [../implementation/phase-05-production-ui-telephony-and-launch.md](../implementation/phase-05-production-ui-telephony-and-launch.md) §6.3.1.

## 4. Full sitemap

### Authentication and tenancy

- Sign in
- Tenant selector
- Access denied / request access
- Profile and session security

### Overview

- Fleet health
- Active production agents
- Calls today
- P50/P95 first-audible latency
- Failure rate
- Estimated cost
- Recent incidents and configuration changes

### Agents

- Agent list
- Create agent
- Agent summary
- Business Brain
- Platform Brain
- Voice & Models
- Memory Schema
- Tools & Actions
- Channels
- Versions & Deployment

### Test Studio

- Browser live test
- PSTN/Plivo test
- Conversation event stream
- Live transcript
- Memory projection inspector
- Latency waterfall
- Errors and provider events

### Calls

- Call list
- Call detail
- Transcript timeline
- Audio player
- Trace timeline
- Memory changes
- Outcome and disposition
- Raw metadata

### Analytics

- Fleet overview
- Quality and task completion
- Latency
- Reliability
- Cost and usage
- Memory health
- Provider/model usage
- Disposition trends

### Benchmarks

- Benchmark sessions
- Create benchmark
- Scenario library
- Combination selection
- Run progress
- Results comparison
- Combination detail
- Review and promotion

### Providers

- Provider registry
- STT providers/models
- LLM providers/models
- TTS providers/models
- Capability and language matrix
- Provider health
- Safe configuration status

### Integrations

- Plivo telephony
- CRM/webhooks
- Tool connectors
- Knowledge sources

### Settings

- Organization
- Members and roles
- Retention and privacy
- Environments
- Scoring weights
- Audit log
- Developer diagnostics

## 5. Configure Agent journey

### Requirement

Provide a guided workspace matching:

`Configure Agent → Configure Business Brain → Choose Voice Tier → Test Agent → Compare Models → Inspect Calls → Analyze Performance → Promote Configuration`.

### Why

The current UI begins with low-level controls and does not communicate deployment state or task completion.

### User behavior

The user creates or selects an agent, completes a visible setup checklist, tests a draft, and promotes a reviewed version.

### System behavior

The system persists drafts independently of active production versions and displays unsaved, saved-draft, validated, approved, and active states.

### Validation

An agent cannot be promoted without a valid brain, enabled provider stack, supported language, completed smoke test, and authorized approver.

### Edge cases

- A provider is disabled after a draft was saved.
- The active brain is edited while calls are running.
- A model loses Telugu support.
- A user lacks permission to promote.

### Acceptance criteria

- A new user can reach a browser test without opening Advanced settings.
- Every editable page identifies draft and active versions.
- Production-impacting actions identify effective environment and confirmation consequence.

## 6. Business Brain builder

### Requirement

Allow customer users to divide business instructions into structured sections while compiling the enabled sections into one ordered business prompt.

### Default section schema

1. Identity & Purpose
2. Business Facts
3. Actions & Limits
4. Qualification Flow
5. Callback / Appointment Flow
6. Scope & Redirects
7. Guardrails
8. FAQ

Additional customer-defined sections are permitted within tenant limits. Customers may **add and delete** custom sections; default eight types remain available as templates.

### Section fields

- Stable `section_id`
- Title
- Description/help text
- Instruction text
- Enabled state
- Fixed or customer-defined type
- Deterministic order
- Validation status
- Estimated tokens
- Last editor/time
- Version introduced

### User behavior

- Expand one or multiple accordion sections.
- Edit instruction text.
- Enable/disable a section.
- Duplicate or delete only customer-defined sections.
- Preview the assembled business prompt.
- Save as draft, validate, test, and publish through version promotion.

### System behavior

The system stores:

- `raw_business_sections[]` exactly as entered.
- `raw_business_prompt`, deterministically assembled from enabled sections.
- `optimized_business_prompt`, generated from the assembled raw prompt.
- optimizer report showing preserved rules, deduplication, warnings, and token change.
- version and optimization timestamp.

Compilation must use stable delimiters and order:

```text
<business_section id="identity-purpose">
...
</business_section>
<business_section id="facts">
...
</business_section>
```

The entire assembled and optimized business brain is treated as a single component of the compiled brain. Sections are an authoring and audit mechanism, not separate per-turn prompts.

### Validation

- Required sections: Identity & Purpose, Actions & Limits, Guardrails.
- Empty enabled sections are invalid.
- Duplicate or conflicting rules produce warnings and require acknowledgement.
- URLs, phone numbers, dates, prices, and policy claims are preserved exactly through optimization unless the user edits them.
- Token budget is enforced before publish.

### Edge cases

- Section disabled after a version is active: creates a new draft version only.
- Optimizer changes meaning: user may reject optimization and keep previous approved optimized version.
- Customer deletes a referenced custom section: references are flagged before save.
- Simultaneous edits: reject stale version or require explicit merge.

### Acceptance criteria

- Raw section text round-trips byte-for-byte.
- Preview order equals compilation order.
- Disabled sections are retained in draft storage but omitted from assembled prompt.
- Optimizer never overwrites the raw source.
- Published calls record the exact business-brain version used.

## 7. Platform Brain editor

### Requirement

Provide a separate protected UI for the developer-owned main/platform brain prompt.

### Why

Platform identity, safety, language behavior, memory contract, and output behavior must not be editable by ordinary customers.

### User behavior

Authorized platform administrators can:

- Edit platform identity and global behavior.
- Edit Telugu/Indian-language conversation rules.
- Edit memory/output contract instructions.
- Edit static safety and compliance rules.
- Preview compiled brain.
- compare versions, validate, test, approve, and activate.

### System behavior

- Enforce `platform_brain:write` permission.
- Store immutable versions.
- Require change reason and approver for production.
- Run regression scenarios before activation.
- Keep in-flight calls on their start version.
- Never expose hidden platform content to customer roles.

### Validation

- Required stable output contract remains present.
- Prompt budget and cache eligibility are calculated.
- Conflicting customer instructions are resolved according to explicit precedence.
- Activation fails if required regression scenarios fail.

### Edge cases

- Emergency rollback.
- Customer business instruction conflicts with platform guardrail.
- Optimizer version changes without platform prompt changes.

### Acceptance criteria

- Customer roles cannot read or modify protected platform content.
- A platform version can be rolled back without changing customer raw content.
- Every call records platform, business, optimizer, and compiled versions.

## 8. Brain preview and precedence UX

The Compiled Preview uses four read-only layers:

1. Platform Brain
2. Optimized Business Brain
3. Static Output/Behavior Rules
4. Cache metadata and token budget

Precedence:

`platform safety/compliance > tenant restrictions > business instructions > stylistic preferences > current-call dynamic context`.

Conflicts are shown as:

- Blocking conflict: cannot publish.
- Warning: publish requires acknowledgement.
- Information: optimization or formatting only.

## 9. Test Studio

### Requirement

Offer a live developer workbench with browser and PSTN channels.

### User behavior

- Select draft/active agent version.
- Select language, tier, scenario, and channel.
- In FRONTEND mode, optionally select enabled STT/LLM/TTS models.
- Start/stop a test.
- Inspect transcript, state transitions, memory projection, memory proposals, latency, tokens, and errors.

### System behavior

- Lock the selected configuration at test start.
- Mark test data separately from production analytics.
- Capture one correlated trace and call ledger.
- Provide replay from transcript, audio, and event timeline.

### Validation

Unsupported language/provider combinations cannot start.

### Edge cases

- Mic denied.
- Plivo not configured.
- provider starts failing mid-test.
- memory update arrives after test stop.

### Acceptance criteria

- Browser test preserves current barge-in and streaming behavior.
- PSTN test clearly shows Plivo readiness and phone number.
- Developer can identify the slowest component for each turn.

## 10. Call history and detail

Call list supports date, agent, channel, environment, tier, combination, disposition, status, and error filters.

Call detail separates:

- Outcome summary
- Audio and transcript timeline
- Pipeline trace
- Memory changes
- Configuration snapshot
- Errors and retries

Transcript rows show speaker, timestamp, interruption, model metadata, component latencies, and what was actually audible.

Memory panel shows:

- full internal current value
- live projection sent to the LLM
- proposed operations
- accepted/rejected operations
- provenance and turn

## 11. Analytics and observability UX

### Per-call debugging

Unified timeline of audio, transcript, STT, LLM, TTS, tools, memory, and errors.

### Aggregate analytics

Separate pages for:

- volume and completion
- latency P50/P95
- quality/task success
- error and fallback rate
- cost and usage
- memory extraction/projection health
- model/combination performance

The aggregate dashboard must not become a raw event inspector.

## 12. Benchmark UX

Benchmark creation:

1. Name session and choose environment.
2. Select language(s), scenario(s), and channels.
3. Select combinations or choose “all compatible enabled combinations.”
4. Review estimated run count and cost.
5. Start run.

Progress states: queued, preparing, running, partially complete, completed, cancelled, failed.

Results show winners per metric, not one unexplained winner. Composite scores display exact weights and component scores.

Export: JSON and CSV result manifests, configuration versions, and scenario versions.

## 13. Combination promotion

State machine:

`draft → benchmarked → reviewed → approved → scheduled → active → superseded → rolled_back`.

Promotion record contains:

- combination ID and version
- benchmark session IDs
- assigned tier
- environment
- optional customer scope
- reviewer/approver
- effective date
- rollback target

Promotion does not mutate historical calls or benchmark results.

## 14. Provider registry UX

Provider/model rows display safe metadata:

- provider and model
- STT/LLM/TTS type
- enabled/configured/healthy status
- streaming/realtime support
- language support
- structured-output/tool/caching capabilities where relevant
- pricing metadata timestamp
- last health check

Never display secret values. “Configured” is a boolean.

Important verified constraint: Cartesia **`ink-2` STT** documents **English only** — must not appear in Telugu STT selectors. Cartesia **`sonic-3.5` TTS** documents Telugu (`te`) among 42 languages and may be used for premium Telugu TTS after benchmark. Default production path: Sarvam **`saaras:v3-realtime`** STT + **`bulbul:v3`** TTS with `te-IN`.

## 15. Modes

### ENV mode

- Shows LOW/MEDIUM/PREMIUM and read-only resolved stack.
- Hides provider/model editing and combination promotion.
- Does not trust client-supplied provider overrides.

### FRONTEND mode

- Shows enabled compatible providers and models.
- Backend validates every selection.
- Disables start until a complete compatible stack is selected.

## 16. Roles and permissions

Normative RBAC matrix (server-enforced; UI mirrors but is not authoritative): [15-architecture-ownership-and-singularity.md](./15-architecture-ownership-and-singularity.md) §9.

Summary:

- **Customer Viewer** — read calls/analytics; no brain edit.
- **Customer Operator** — test agents, annotate calls; no publish.
- **Customer Admin** — edit/publish **business brain** and tenant settings; cannot read platform brain body.
- **Voice Engineer** — providers, benchmarks, combinations, traces; cannot publish business brain in production without Customer Admin role.
- **Platform Admin** — platform brain, global guardrails, stack promotion; sole activator of platform brain.
- **Auditor** — read versions, audit log, export; no edit.

**No double assignment:** only Platform Admin activates platform brain; only Customer Admin publishes business brain for tenant; customer roles never see platform brain text.

## 17. UI states

Every data surface must define:

- initial loading
- background refresh/stale data
- empty
- partial data
- validation error
- permission denied
- provider unavailable
- request failed with retry
- read-only archived version
- unsaved changes
- pending activation

Long-running jobs expose progress and may be safely closed/resumed.

## 18. Accessibility, responsive, SEO, and performance

Normative detail: [19-frontend-backend-nextjs-railway.md](./19-frontend-backend-nextjs-railway.md) §6–7.

### Responsive (all devices)

- WCAG 2.2 AA target.
- Keyboard-operable accordions, tabs, tables, filters, dialogs, and audio controls.
- Visible focus; no color-only status.
- `aria-live="polite"` for transcript deltas; prevent excessive announcements.
- Telugu text uses a tested Telugu-capable font stack and appropriate line height.
- Reduced motion preference respected.
- Desktop: persistent navigation and split-pane debugging.
- Tablet: collapsible navigation and stacked inspector.
- Mobile: voice test, call list, call summary, and critical actions; complex benchmark comparison becomes metric-by-metric rather than a squeezed table.

## 19. Recommended enhancements from major-platform patterns

These are not source requirements and must remain labeled until product approval:

1. **RECOMMENDED ENHANCEMENT — Knowledge base:** versioned documents with retrieval evaluated separately from live call memory.
2. **RECOMMENDED ENHANCEMENT — Tools/actions:** schema-defined tools, permission scopes, test mode, and per-call tool traces.
3. **RECOMMENDED ENHANCEMENT — Human transfer:** configured transfer targets, escalation policy, and transfer outcome.
4. **RECOMMENDED ENHANCEMENT — Campaigns/numbers:** outbound batches, calling windows, consent, DNC controls, and per-campaign analytics.
5. **RECOMMENDED ENHANCEMENT — Quality review queue:** automatic sampling, reviewer scorecards, annotations, and regression dataset promotion.
6. **RECOMMENDED ENHANCEMENT — Configuration diff/rollback:** required for safe environment promotion.

None of these may be represented as implemented in the current repository.
