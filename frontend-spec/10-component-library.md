# 10 — UI element and component library

Prefer **existing** `web/components` over new primitives. Stitch elements map into this table.

## Marketing

| Stitch / visual element | Implement with |
|-------------------------|----------------|
| Top nav | `MarketingNav` |
| Footer | `MarketingFooter` |
| Wordmark | `BrandMark` |
| Hero preview | `AgentPreview` + `TiltCard` |
| Scroll chapter | `Reveal`, `ScrollProgress` |
| Primary / secondary buttons | `.btn-primary` `.btn-secondary` in `globals.css` |
| FAQ accordion | local state in `HomeExperience` (extract if reused) |
| Pricing card | article + border; highlight via `shadow-glow` |

## Auth

| Element | Component |
|---------|-----------|
| Split layout | `AuthShell` |
| Fields | `Input`, `Label`, `FieldError` |
| Submit | `Button` |
| Session | `auth-client.ts` |

## Console chrome

| Element | Component |
|---------|-----------|
| App shell | `ConsoleShell` / `DevShell` |
| Sidebar | `InstrumentSidebar` |
| Nav item | `SkeuoNavItem` |
| Top bar | `ShellTopBar` |
| Page title | `PageHeader` |
| Page wrap | `ConsolePage` |
| Card | `Panel` / `SkeuoPanel` |
| Stat | `StatCard` |
| Empty | `SkeuoEmptyState` |
| Dialog | `ConfirmDialog` |

## Skeuo controls (`web/components/ui/skeuo`)

| Element | File | Use |
|---------|------|-----|
| Button | `SkeuoButton` | Console primary/secondary/ghost |
| Input | `SkeuoInput` | Settings, filters |
| Textarea | `SkeuoTextarea` | Brain sections |
| Badge | `SkeuoBadge` | Disposition, env, channel |
| Table | `SkeuoTable` | Calls, invoices, providers |
| Meter | `SkeuoMeter` | Usage, latency bars |
| Status light | `SkeuoStatusLight` | Health / live |
| Icons | `icons.tsx` | Nav only |

## Voice / Test Studio

| Element | Component |
|---------|-----------|
| Live panel | `TestStudioLivePanel` |
| Memory | `TestStudioMemoryPanel` |
| Turn metrics | `TestStudioTurnMetrics` |
| Fine-tune | `TestStudioFineTuneWorkbench` |
| Voice picker | `CartesiaVoiceSelect` |
| Language | `CompileLanguagePicker` |
| Rack module | `VoiceRackModule` |

## Calls

| Element | Component |
|---------|-----------|
| List | `CallsListPanel` |
| Filters | `CallsFilterBar` |
| Audio | `CallAudioPanel` |
| Transcript | `CallTranscriptTimeline` |
| Memory | `CallMemoryStatePanel` |

## Agents / brain

| Element | Component |
|---------|-----------|
| Workspace tabs | `AgentWorkspaceNav` |
| Brain editor | `BusinessBrainEditor` |

## Dev-only

| Element | Component |
|---------|-----------|
| Workflow card | `DevCard` |
| Env panel | `EnvironmentPanel` |
| Agents grid | `DevAgentsGrid` |
| Trace | `SessionTracePanel` |
| Brain client | `DevAgentBrainClient` |
| Test studio | `DevAgentTestStudio` |

## Elements to add (selling site / typical Stitch kit)

Only add when a screen needs them; match skeuo tokens:

- **Toast** — save draft / promote success
- **Banner** — `past_due`, provider outage
- **Stepper** — onboarding
- **Diff viewer** — versions
- **Audio waveform** — if Stitch shows one; keep accessible play/pause
- **GSTIN field** — billing
- **File upload** — campaign CSV

Do **not** add: full shadcn kit, Material, a second button language, chatbot widget.

## CSS utility classes (already in `globals.css`)

`.btn-primary` `.btn-secondary` `.label-caps` `.skeuo-inset` `.skeuo-btn-primary` `.skeuo-env-prod` `.grid-bg` `.animate-pulse-dot`

## Icon + status mapping

| Meaning | Color token | Icon |
|---------|-------------|------|
| Live call | `--status-live` | `IconMic` + pulse |
| Healthy | `--status-success` | `SkeuoStatusLight` |
| Warning | `--status-warning` | badge |
| Error | `--status-error` | banner |
| Info / telemetry | `--status-info` | mono chips |
