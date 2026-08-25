# 05 — UX Console and Dashboards

> **SUPERSEDED for navigation and sitemap.** Use [11-ui-information-architecture.md](./11-ui-information-architecture.md) for normative IA. This file retains component-level ideas only. Role ownership: [15-architecture-ownership-and-singularity.md](./15-architecture-ownership-and-singularity.md) §9–11.

Console information architecture, env vs frontend modes, call review, and configuration workflows.

**Note:** Ponytail skill unavailable; patterns from existing `client/` SPA, 2026 voice observability research (Pipecat, Retell disposition UX, AWS LCA), and SaaS configuration UX principles.

**Target-state concept:** the current product still has six always-visible console panels and no Calls/Test/Metrics pages or configuration-mode gating. Document 11 is the normative v2 UX specification.

---

## 1. UX principles

1. **Mode-aware complexity** — production operators see tiers; engineers see the full matrix.
2. **Measure the pipeline, not just the model** — every dashboard shows STT → LLM → TTS waterfall.
3. **Calls are the unit of review** — not browser sessions.
4. **Raw vs optimized prompt separation** — customers edit raw; system shows effective in dev only.
5. **Progressive disclosure** — advanced tuning behind tabs, not the default start flow.
6. **Empty / loading / error states** — every list and panel (research: production voice-agent UX 2026).

---

## 2. Application shell

### 2.1 Layout (extend current SPA)

```
┌─────────────────────────────────────────────────────────────┐
│  Voice Agent Platform    [Tier: MEDIUM ▼]  [● Live]  ⚙    │
├──────────┬──────────────────────────────────────────────────┤
│ Nav      │  Main content area                               │
│          │                                                  │
│ ● Voice  │                                                  │
│ ○ Calls  │                                                  │
│ ○ Test   │  (hidden in env mode)                            │
│ ○ Brain  │                                                  │
│ ○ Metrics│                                                  │
│ ○ Config │                                                  │
└──────────┴──────────────────────────────────────────────────┘
```

Preserve existing `styles.css` design tokens, dark theme, Telugu font stack.

### 2.2 Navigation modes

| Tab | env mode | frontend mode |
|-----|----------|---------------|
| **Voice** | Tier chip + Start + live transcript | Full live UI + preset selector |
| **Calls** | List + detail | Same |
| **Test** | Hidden | Combination matrix + benchmark runs |
| **Brain** | Read-only effective summary | Full prompt editor + optimizer preview |
| **Metrics** | Session aggregates | Per-call traces + combination comparison |
| **Config** | Hidden | Provider enables read-only from catalog |

Implementation: `console_tabs.js` + server-driven `config_mode` from catalog API.

---

## 3. Voice tab (live call)

### 3.1 env mode

**Visible:**

- Tier selector: LOW | MEDIUM | PREMIUM (maps to server tier, not client override)
- Estimated cost hint per minute (from benchmark defaults)
- Start / Stop buttons
- Live transcript (user + agent)
- Connection status (STT / Brain / TTS indicators)
- Minimal latency badge (E2E last turn)

**Hidden:** provider dropdowns, VAD sliders, brain editor, preset matrix.

### 3.2 frontend mode

**Visible:** everything today plus:

- STT / LLM / TTS provider + model dropdowns (from catalog)
- Voice preset selector (existing)
- Fine-tune panels (pipeline, barge, TTS tuning)
- Per-turn latency breakdown expandable row
- "Save as benchmark run" after session

### 3.3 Live transcript UX

| Element | Behavior |
|---------|----------|
| User bubble | Telugu-primary, timestamp, STT latency on hover |
| Agent bubble | Streaming partial text, TTS playing indicator |
| Interrupted turn | Strikethrough partial + "Interrupted" badge |
| Barge-in | Visual flash on user speech during agent play (existing `live-guards.js`) |

### 3.4 Call state indicator

```
Idle → Connecting → Listening → Thinking → Speaking → Ended
```

Maps to `session_state.py` enum; show in header.

---

## 4. Calls tab (new primary review surface)

### 4.1 Call list

| Column | Source |
|--------|--------|
| Time | `meta.json.started_at` |
| Channel | `meta.json.channel` — `browser` or `pstn` badge |
| Duration | computed |
| Tier | `resolved_stack.tier` |
| Disposition | `outcome.disposition` badge (color-coded) |
| Summary | `outcome.summary_en` truncated |
| Customer | `outcome.extracted.name` |

**Filters:** date range, disposition, tier, search on summary text.

**Empty state:** "No calls yet — start a voice session to create your first call archive."

### 4.2 Call detail view

**Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│ Call abc-123   MEDIUM tier   4m 32s   [can_convert]       │
├──────────────────────┬──────────────────────────────────────┤
│ Outcome card         │  Audio player (mix.wav)              │
│ Summary TE / EN      │  [====●========]  scrub              │
│ Next action          │                                      │
│ Extracted fields     │                                      │
├──────────────────────┴──────────────────────────────────────┤
│ Transcript timeline                                         │
│  0:12 USER  నమస్కారం          STT 98ms                      │
│  0:14 AGENT నమస్కారం! ...     LLM 120ms TTFT  TTS 45ms     │
│  ...                                                        │
├─────────────────────────────────────────────────────────────┤
│ Latency waterfall (last turn / avg / p95)                   │
│  [STT bar][LLM bar][TTS bar][E2E]                           │
├─────────────────────────────────────────────────────────────┤
│ Working memory final (collapsible JSON)                     │
│ Stack config snapshot (read-only)                           │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Disposition badge colors

| Disposition | Color |
|-------------|-------|
| `can_convert`, `highly_interested` | Green |
| `interested`, `callback` | Blue |
| `completed` | Gray |
| `not_interested`, `wrong_number` | Red |
| `no_outcome` | Yellow |

Pattern: CRM disposition UX (Retell/AWS LCA) — scannable at list level.

---

## 5. Test tab (frontend mode only)

### 5.1 Combination matrix

Grid or form:

| Stage | Provider ▼ | Model ▼ |
|-------|------------|---------|
| STT | | |
| LLM | | |
| TTS | | |

**Actions:**

- Run live test (opens Voice tab with locked selection)
- Run scripted benchmark (batch REST turns from fixture audio/text)
- Compare with last run

### 5.2 Benchmark run card

Shows after test:

- Combination id
- Score (weighted from env weights)
- P50/P95: STT, LLM TTFT, TTS first audio, E2E
- Token cost estimate (INR + USD)
- Quality rubric scores (if scripted scenario)

### 5.3 Comparison view

Side-by-side two runs:

- Latency waterfall chart (bar or stacked)
- Cost per minute
- Disposition on scripted calls
- Highlight winner per metric with configurable weights

Research alignment: evaluate **component + E2E latency** and **task quality**, not raw model benchmarks alone.

---

## 6. Brain tab

### 6.1 SaaS customer view

- Large textarea: **raw business prompt** (editable)
- Save → triggers optimizer (show progress spinner)
- Success: "Brain updated to version X"
- Token estimate badge (compiled size)

### 6.2 Developer view (frontend mode)

- Tabs: Raw | Optimized | Compiled (read-only) | Effective (API mirror)
- Platform brain version label
- "Test brain" → `/api/brain/test` without live audio
- Cache status indicator (from metrics)

### 6.3 Version history (v1.1)

List prior `business_brain_version` with diff view — out of v1 scope but reserve UI slot.

---

## 7. Metrics tab

### 7.1 Session view (existing extended)

- Rolling p50/p95 from `/api/metrics`
- Brain token layers (input, cached, output)
- Cache hit rate

### 7.2 Per-call trace (new)

Select call → span timeline:

```
conversation.start
  stt.final          120ms
  llm.stream.start   80ms TTFT
  llm.stream.end     450ms
  tts.first_audio    45ms
  e2e.turn           695ms
```

OpenInference-style names for future export.

### 7.3 Cost analytics

- Per-minute breakdown: STT / TTS / Brain (INR default for this product)
- Amortized phone number line item (env `PHONE_NUMBER_MONTHLY_COST`)
- Tier comparison table from benchmark history

---

## 8. Config tab (frontend mode)

Read-only display of:

- `VOICE_AGENT_CONFIG_MODE`
- Enabled plugins (STT/LLM/TTS)
- **Plivo status** — enabled, number masked, `GET /api/plivo/status` link
- Active tier env mapping (even in frontend mode, for reference)
- Scoring weights (`VOICE_SCORE_*`)

Link to `.env` documentation — no secret values shown.

---

## 9. Responsive & accessibility

| Requirement | Implementation |
|-------------|----------------|
| Mobile | Voice tab usable on tablet; Calls list scroll; detail stacks vertically |
| Keyboard | Start/Stop focusable; transcript landmarks |
| Screen reader | `aria-live="polite"` on agent streaming text |
| Reduced motion | Respect `prefers-reduced-motion` for barge-in flash |
| Telugu | `Noto Sans Telugu` / existing font stack |

---

## 10. Error and empty states

| Context | Message + action |
|---------|------------------|
| Provider disabled | "Cartesia STT is not enabled on this server." |
| call/start failed | Retry button; don't open WS |
| Post-call pending | Skeleton on disposition; poll `GET /api/call/{id}` |
| Audio missing | "Audio archive not available for this call." |
| Benchmark no runs | CTA to Test tab |

---

## 11. Component map (frontend)

| New / modified | File |
|----------------|------|
| Mode gating | `settings.js`, `console_tabs.js` |
| Call list/detail | `calls_view.js` (new) |
| Benchmark UI | `benchmark_view.js` (new) |
| Tier chips | `tier_selector.js` (new) |
| Existing live | `app.js`, `live-guards.js` |
| Styling | `styles.css` — extend, don't replace |

---

## 12. Acceptance criteria

- [ ] `env` mode hides Test and Config tabs; shows tier chips only
- [ ] `frontend` mode shows full matrix; unchanged from today + new tabs
- [ ] Call detail loads transcript + disposition + audio within 2s
- [ ] Disposition badges visible in list without opening detail
- [ ] Benchmark comparison shows at least 2 runs side-by-side
- [ ] Raw business prompt save does not expose compiled text to customer role
- [ ] All new views have empty and error states
