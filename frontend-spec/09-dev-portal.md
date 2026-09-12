# 09 — Developer portal (already shipped)

**Status: implemented.** This is not a backlog surface. Align Stitch and polish to **current code** and PRD `17` §9 / `19` §3.2 / `20` Layer B.

| PRD | What we already have |
|-----|----------------------|
| `17` §9 P0 Dev Portal auth | `/dev/login`, env credentials, session cookie, CSRF |
| Separate `/dev` prefix | `web/app/dev/(auth)` + `web/app/dev/(portal)` |
| Stack, Platform Brain, promotion | `/dev/stack`, `/dev/platform-brain`, `/dev/promotion` |
| Not on marketing site | `MarketingNav` has no link; robots disallow `/dev` |
| Look | Same skeuo chassis as `/app` — steel + live rose, denser telemetry |

**Shell (do not replace):** `DevShell` + `DevNav` + `DevPortalProvider` + `ShellTopBar`.

**Auth:** `/dev/login` → `POST /api/dev/login`. Logout `/api/dev/logout`.

Customers never edit these pages. Platform Brain body is **only** here.

## Why it exists (PRD)

Platform staff configure what **all tenants** run: keys, LOW/MEDIUM/PREMIUM stacks, platform brain, runtime barge/VAD, promotion to staging/prod (`prd/08` MVP item 1 — **UI done**).

## Nav and pages (current code)

| Route | Page | Job |
|-------|------|-----|
| `/dev` | Overview | 5-step workflow cards |
| `/dev/environment` | Environment | API keys, config mode ENV vs FRONTEND, feature flags |
| `/dev/stack` | Stack & tiers | STT/LLM/TTS per LOW/MED/PREM |
| `/dev/runtime` | Runtime tuning | Barge, VAD, PSTN constants that are allowed in UI |
| `/dev/platform-brain` | Platform Brain | Protected master instructions |
| `/dev/compiled` | Compiled preview | Four layers: platform + optimized business + static rules + cache |
| `/dev/providers` | Providers | Full registry + health |
| `/dev/agents` | Agents | Dev grid / default agent convenience (`prd/17`) |
| `/dev/test-studio` | Test Studio | Same live stack, FRONTEND overrides allowed |
| `/dev/test-studio/[agentId]` | Agent-scoped test | |
| `/dev/benchmarks` | Benchmarks | Combination runs — gated |
| `/dev/promotion` | Promotion | draft → … → active / rollback |
| `/dev/agents/[id]/*` | Agent internals | brain, voice, memory, channels, versions, test |

## How it should look (palette)

Use **Layer B** from [02](./02-ui-style-system.md) / PRD 20:

- Page `#08090c`, panels `#111318`, steel `#8fa6c4`, live `#e11d48`
- Overview: three `StatCard`s + numbered `DevCard` 01–05
- More inset JSON / mono IDs than Business Console
- Production promotion uses `skeuo-env-prod`, never a casual teal button
- Missing keys = warning amber, never dump the secret

## Overview cards (keep)

1. Environment & keys
2. Configure stacks
3. Tune platform brain
4. Test live agent
5. Promote

Stat row: 3 envs, LOW/MED/PREM, platform brain protected.

## Environment

- Presence of keys as **booleans** (configured / missing), never the secret
- Config mode: ENV (operators see tiers only) vs FRONTEND (engineers pick models)
- Restart/reload warnings if required

`EnvironmentPanel.tsx` is the pattern.

## Stack & tiers

Matrix: tier × STT × LLM × TTS. Save is server-validated. Incompatible language (e.g. ink-2 + te-IN) blocked with a reason.

## Runtime

Barge hold, think-cancel, coalesce — only settings that already exist in runtime_settings. Label units (ms).

## Platform Brain

Permission `platform_brain:write`. Change reason + approver for production. This is **not** the eight business sections.

## Compiled preview

Four read-only layers (`prd/11` §8). Precedence: platform safety > tenant > business > style > call context.

## Promotion

State machine from `prd/11` §13. Never mutate historical calls. Top bar `environment` must reflect the **target** being edited.

## Test Studio (dev)

Same panels as business plus model overrides in FRONTEND mode, `SessionTracePanel`, compiled brain version at `call/start`.

## Visual differences from `/app`

- Subtitle “Developer Portal”
- Footer link **to** Business Console (`href="/app"`)
- More mono IDs, traces, JSON wells (`skeuo-inset`)

## Remaining work (polish, not greenfield)

- Pass real env into `ShellTopBar`
- Restyle from Stitch **onto** `DevShell`, same routes
- Keep unlinked from `/`, `/pricing`, `/docs`

Engineers bookmark `/dev/login`.
