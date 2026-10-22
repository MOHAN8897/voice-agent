# 14 — States, accessibility, responsive

Normative: `prd/11` §17–18, `prd/19` §6–7.

## Required UI states (every data screen)

| State | Pattern |
|-------|---------|
| Initial loading | Skeleton or `PageHeader` + muted “Loading…” — not a blank chassis |
| Empty | `SkeuoEmptyState` + one CTA |
| Partial | Show known rows; badge “Refreshing” |
| Validation | Inline `FieldError` next to field |
| Permission | Redirect `/app/access-denied` or hide control |
| Provider down | Banner; disable Start |
| Request failed | Error + Retry |
| Unsaved | Sticky save |
| Archived version | Read-only banner |
| Pending job | Progress; safe to leave |

## Voice-specific states

Idle → Connecting → Listening → Thinking → Speaking → Ended (`prd/05` / session FSM).  
Barge: visual flash, interrupted transcript styling.  
Mic denied: instructions to enable permission.  
Echo / agent talking: do not show STT partials as customer barge until barge logic agrees.

## Accessibility

- WCAG 2.2 AA target
- Keyboard: nav, accordions, tabs, dialogs, audio
- Visible focus rings
- Not color-only (disposition badge + label text)
- `aria-live="polite"` on transcript; throttle
- Telugu line-height; don’t truncate mid-glyph
- `prefers-reduced-motion`: no tilt/parallax
- Icon-only buttons need `aria-label`

## Responsive

| Break | Marketing | Console |
|-------|-----------|---------|
| < md | Stack hero; hamburger nav | `MobileShellHeader` drawer |
| md | | Collapsible sidebar |
| lg+ | Split hero; 3 pricing cols | Persistent sidebar + split inspectors |

Mobile **must** support: sign in, Test Studio start/stop, call list, call summary.  
Benchmark comparison: metric-by-metric, not a squeezed table (`prd/11`).

## Performance

- SSG/ISR marketing
- No live WS on public pages
- `next/image` for Stitch PNGs
- Console: server components for lists; client only for live/audio
- Core Web Vitals on marketing (`prd/19`)

## Dark only

v1 is dark chassis. Do not ship Stitch light-mode frames without a token pass.
