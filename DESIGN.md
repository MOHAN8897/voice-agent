---
version: alpha
name: Vāṇi Voice Platform
description: Telugu-first production voice control plane — calm, precise, operational, with a modern agentic surface for marketing and console.
colors:
  primary: "#3dd6c6"
  background: "#06090d"
  background-elevated: "#0c1118"
  surface: "#10161f"
  surface-raised: "#161e2a"
  surface-card: "#131920"
  border: "#243040"
  border-subtle: "#1a2430"
  text: "#eef2f6"
  text-muted: "#8b9aab"
  text-subtle: "#5c6b7a"
  accent: "#3dd6c6"
  accent-secondary: "#4db5ff"
  accent-dim: "#0f2e2a"
  accent-glow: "#3dd6c633"
  telugu: "#e8c468"
  success: "#3dd68c"
  warning: "#f0b429"
  agent-online: "#3dd68c"
  agent-processing: "#4db5ff"
typography:
  display-xl:
    fontFamily: Instrument Serif
    fontSize: 72px
    fontWeight: 400
    lineHeight: 1.05
    letterSpacing: -0.02em
  display-lg:
    fontFamily: Instrument Serif
    fontSize: 48px
    fontWeight: 400
    lineHeight: 1.1
    letterSpacing: -0.02em
  body-lg:
    fontFamily: DM Sans
    fontSize: 18px
    fontWeight: 400
    lineHeight: 1.6
  body:
    fontFamily: DM Sans
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: DM Sans
    fontSize: 12px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: 0.08em
  mono-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.4
rounded:
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px
  2xl: 64px
  3xl: 96px
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.background}"
    rounded: "{rounded.md}"
    padding: 14px
  button-primary-hover:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.background}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: 14px
  button-secondary-hover:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.text}"
  card:
    backgroundColor: "{colors.surface-card}"
    textColor: "{colors.text}"
    rounded: "{rounded.lg}"
  panel:
    backgroundColor: "{colors.background-elevated}"
    textColor: "{colors.text}"
    rounded: "{rounded.lg}"
  badge-online:
    backgroundColor: "{colors.accent-dim}"
    textColor: "{colors.agent-online}"
    rounded: "{rounded.full}"
    padding: 8px
  badge-processing:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.agent-processing}"
    rounded: "{rounded.full}"
    padding: 8px
  badge-warning:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.warning}"
    rounded: "{rounded.full}"
    padding: 8px
  label-muted:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-muted}"
    rounded: "{rounded.sm}"
    padding: 8px
  caption-subtle:
    backgroundColor: "{colors.surface-card}"
    textColor: "{colors.text-subtle}"
  telugu-sample:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.telugu}"
    rounded: "{rounded.md}"
    padding: 12px
  telemetry:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.accent-secondary}"
    rounded: "{rounded.sm}"
    padding: 8px
  glow-chip:
    backgroundColor: "{colors.accent-glow}"
    textColor: "{colors.accent}"
    rounded: "{rounded.full}"
  border-rule:
    backgroundColor: "{colors.border}"
    textColor: "{colors.text}"
  hairline:
    backgroundColor: "{colors.border-subtle}"
    textColor: "{colors.text-subtle}"
  success-chip:
    backgroundColor: "{colors.accent-dim}"
    textColor: "{colors.success}"
    rounded: "{rounded.full}"
    padding: 8px
---

# Vāṇi Design System

## Overview

Vāṇi is a **production voice control plane** for Telugu-first business calls. The brand feels calm, precise, and operational — not like a generic AI demo. Marketing surfaces use a restrained **agentic** layer: live status, telemetry readouts, and workflow clarity inspired by Outpero (India-first voice employee energy) and Opero (editorial, production-grade control plane), without neon gradients or decorative metric walls.

**Audience:** Business administrators, voice engineers, platform operators, and developers promoting stacks to production.

**Personality:** Confident, Telugu-first, task-oriented. Hierarchy through spacing and weight before color.

## Colors

| Role | Token | Usage |
|------|-------|--------|
| Canvas | `background`, `surface` | Page and panel backgrounds |
| Primary / Accent | `primary` / `accent` (#3dd6c6) | Primary CTAs, live agent indicators |
| Secondary | `accent-secondary` | Links, STT/TTS telemetry |
| Telugu | `telugu` | Telugu script in previews and samples |
| Semantic | `success`, `warning` | Online state, validation |

## Console / Dev Portal tokens (Layer B — shipped)

Marketing uses the YAML tokens above. **`/app` and `/dev` already use** `web/app/globals.css`:

| Role | Hex | Use |
|------|-----|-----|
| Chassis | `#08090c` | Page |
| Panel | `#111318` | Sidebar, cards |
| Raised | `#171b22` | Hover |
| Inset | `#0c0e12` | Wells |
| Text | `#f0f2f5` | Primary |
| Steel | `#8fa6c4` | Chrome, links |
| Live | `#e11d48` | Recording / Test Studio |
| Success / warn / error | `#4ade80` / `#fbbf24` / `#f87171` | Status |

Do not recolor Dev Portal to marketing teal. Full page-look spec: [`prd/20-visual-design-and-ui-style.md`](prd/20-visual-design-and-ui-style.md).

## Typography

- **Display:** Instrument Serif — hero headlines, section titles
- **Body:** DM Sans — paragraphs, nav, forms
- **Mono:** JetBrains Mono — agent telemetry, latency, IDs
- **Telugu:** Noto Sans Telugu — live transcript samples and language chips

Uppercase labels use `label` scale with wide tracking.

## Layout

- Max content width: `72rem` (1152px)
- Section vertical rhythm: `py-24` / `3xl` spacing
- Marketing: generous whitespace, left-aligned editorial blocks alternating with full-width agent previews; cinematic scroll chapters with transform/opacity only
- Console: higher density, sidebar + main, operational dashboards

## Elevation & Depth

- Cards: `surface-card` + `border-subtle`, hover `border-accent/30`
- Hero: subtle grid mask + single soft accent glow (no multi-stop gradients)
- Agent preview: elevated panel with window chrome and inner raised transcript blocks
- Scroll: parallax planes at 0.16 / 0.34 / 0.62 depth; reduce to static under `prefers-reduced-motion`

## Shapes

- Buttons and inputs: `rounded-xl` (12–16px)
- Cards: `rounded-2xl`
- Pills and badges: `rounded-full`

## Components

### Primary button
Teal accent background, dark text, `rounded-xl`, semibold. Hover: slight scale or opacity only.

### Secondary button
Transparent with `border-subtle`, text default. Hover: accent border tint.

### Agent status pill
`rounded-full`, mono uppercase label, green dot pulse for online.

### Feature card
Tag chip (mono), title, body. Hover border accent/30 — no shadow stacks.

### Live preview panel
Window dots, mono path label, split transcript + waveform + latency grid.

## Do's and Don'ts

**Do**
- Lead with workflow: configure → test → inspect → promote
- Show real Telugu copy in product previews
- Use live-agent telemetry aesthetic for hero demo
- Build complete responsive, keyboard-accessible states
- Degrade cinematic motion to a composed still under reduced motion

**Don't**
- Neon AI purple/pink gradients
- Generic card walls with lorem metrics
- Multiple competing primary CTAs per viewport
- Provider-first complexity on marketing pages
