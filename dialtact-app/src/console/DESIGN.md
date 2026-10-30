# Dialtact console design foundation

The console sells AI voice employees. It should feel like managing a team, not
reading reports: plain words, calm colour, one clear action per thing. Phase 2
restyles every module with exactly what is written here. If something you need
is missing, add it here and to `ui/` first, then use it.

Primitives live in `src/console/ui/` (barrel: `ui/index.js`). Tokens live in
`tailwind.config.js` and are mirrored as CSS variables in `src/styles/globals.css`.

---

## 1. Colour tokens

Never write a hex value in a class (`text-[#0F0E17]`). Use these Tailwind tokens.
The legacy keys (`text-primary`, `brand`, `border-hairline`, `telemetry`) still
exist only so old code compiles; do not use them in new code.

| Role | Class | Value | Use |
|---|---|---|---|
| Page background | `bg-canvas` | #FAF9FD | `<main>` and page shells |
| Surface | `bg-surface` | #FFFFFF | cards, tables, modals |
| Subtle surface | `bg-surface-subtle` | #F0EEF6 | segmented controls, icon tiles |
| Primary text (ink) | `text-ink` / `text-fg` | #0F0E17 | headings, names, numbers |
| Body text | `text-fg-body` | #524E5E | sentences, table cells |
| Muted text | `text-fg-muted` | #716C7F | timestamps, captions, helper text (AA on white) |
| Subtle | `text-fg-subtle` | #8C879A | icons, placeholders, disabled. **Not for readable text** (fails AA) |
| Border | `border-line` | #E4E2EB | every hairline and divider (`divide-line`) |
| Strong border | `border-line-strong` | #D1CFDB | hover borders |
| Accent | `bg-accent` / `text-accent` | #6344E7 | brand moments, focus rings, the one brand button |
| Accent hover | `bg-accent-hover` | #5234D4 | |
| Accent soft | `bg-accent-soft` + `text-accent-fg` | #F0ECFF / #5034CE | links (`text-accent-fg`), selected rows |

Semantic tones — each has `DEFAULT` (dot/solid), `soft` (background), `fg` (text
on soft) and `line` (border):

| Tone | Soft bg / fg | Meaning |
|---|---|---|
| `success` | #ECFDF5 / #047857 | done, connected, live, money in |
| `warning` | #FFFBEB / #92400E | needs the owner's attention soon |
| `danger` | #FEF2F2 / #B91C1C | something is broken or failed |
| `info` | #EFF6FF / #1E40AF | a neutral fact worth noticing (incoming, scheduled) |
| `neutral` | #F4F3F8 / #524E5E | everything else |

## 2. Status colour rules

1. **Red (`danger`) only for problems**: failed call, technical failure, wallet empty,
   number paused for unpaid rent, disconnected integration, failed renewal.
2. **Amber (`warning`) for attention**: needs review, callback requested, low wallet,
   missed call, payment due (grace).
3. **Green (`success`) for success or live**: answered, booked, qualified, connected,
   on a call now, top-up received.
4. **Neutral or info for facts**: synced, metered, draft, incoming/outgoing, scheduled.
   "Synced" and "Metered" are never red.
5. A metric changing is not a status. `MetricCard` trends are green when positive and
   neutral otherwise — never red.
6. Never use colour alone: pair with a word (`Badge`) or an icon.

Use `statusWord(status)` from `src/lib/internalLabels.js` to get `{ label, tone }`
for any status string, or just `<StatusBadge status={…} />`.

## 3. Type scale

One family: **Inter** (`font-sans`). **JetBrains Mono** (`font-mono tabular-nums`)
only for numbers and IDs that must line up: durations, money, counts in tables,
phone numbers in tables, call references. Never for labels, headings or buttons.

| Token | Size / line | Use |
|---|---|---|
| `text-display` | 24/32 bold | page greeting / page title on desktop |
| `text-heading` | 20/28 bold | page title on phones, big numbers in rails |
| `text-title` | 16/24 semibold | card and section titles |
| `text-copy` | 14/22 | sentences, feed items, form inputs |
| `text-ui` | 13/20 | buttons, table cells, secondary lines, tabs |
| `text-meta` | 12/16 | timestamps, captions, table headers, badges |

**12px is the floor.** No `text-[9px]`, `text-[10px]`, `text-[11px]`.
Inputs use `text-base sm:text-ui` so iOS does not zoom.

## 4. Radii, spacing, shadow

Three radii only:

| Token | Value | Use |
|---|---|---|
| `rounded-control` | 10px | buttons, inputs, selects, small tiles, list rows |
| `rounded-card` | 16px | cards, sections, modals, banners |
| `rounded-pill` | 9999px | badges, filter pills, avatars (`rounded-full`) |

Card padding `p-4` (rails, compact) or `p-5 sm:p-6`. Page gutter is set by the shell
(`p-4 sm:p-6 lg:p-8`). Gaps: 8 / 12 / 16 / 20 / 24 px (`gap-2 … gap-6`).
Shadow: `shadow-craft-xs` on cards; `shadow-craft-lg` only on floating menus.

## 5. Copy rules

- **Plain language.** Say what happened to a person: "Meera booked a site visit with
  Ravi", not "Disposition: site_visit_planned".
- **Never show internal tokens.** Tags, dispositions, end reasons, statuses, policy
  reasons, stack names and API phrasing go through `src/lib/internalLabels.js`:
  `tagLabel`, `dispositionLabel`, `endReasonLabel`, `statusWord`, `policyReasonLabel`,
  `humanizeToken`. `custom:solar_panels` → "Solar panels".
- **No developer phrases**: not "from API archive", "tenant-scoped", "stack overrides
  apply", "fleet", "telemetry", "autonomous".
- **No hype.** No "AI-powered", "magic", exclamation marks.
- **Sentence case everywhere**: headings, buttons, tabs, labels, nav groups. No
  all-caps tracked "eyebrow" labels.
- **Buttons are verbs**: "Call back", "Add funds", "Approve", "Open call".
- **Money is India-first**: rupees first, via `src/lib/money.js`
  (`formatInr`, `formatPaise`, `walletAmounts(wallet).primary`). Show dollars only as
  the secondary figure where a screen already had them (`walletAmounts().secondary`).
- **Time** via `relativeTime()` ("4 min ago", "Yesterday 6:10 pm") with the full date
  in a `title`; live timers via `formatClock()` ("2:14").
- Contact phone numbers in summaries are masked (`+91 98••• ••123`); full numbers
  stay on the detail screens that already show them.

## 6. Primitives

All accept `className` for layout only (margins, grid placement) — not for colour.

### `Button` / `TactileButton` (`ui/TactileButton.jsx`)
`variant`: `primary` (ink — the main action on a surface) · `brand` (accent — at most
one per screen) · `secondary` (bordered, default for most) · `ghost` (quiet, inline)
· `danger` (destructive only) · `success` · `white`/`outline` (legacy aliases of
secondary). `size`: `xs | sm | md | lg | icon`. `icon={LucideIcon}`, `loading`.
Touch targets are 44px tall on phones automatically.

### `Card` / `SolidCard`, `Section` (`ui/SolidCard.jsx`)
`Card` is the surface (`variant`: default | subtle | dark, `hover`, `padding`, `as`).
`Section` is a card with `title`, `description`, `actions`, `headingLevel`.

### `Badge`, `StatusBadge` / `StatusPill` (`ui/StatusBadge.jsx`)
`<Badge tone="warning" dot>Needs review</Badge>`. `<StatusBadge status="needs_review" />`
maps through the humanizer; override with `tone` / `label`. Tones: success, warning,
danger, info, neutral, accent, live (pulsing green dot).

### `MetricCard` (`ui/MetricCard.jsx`)
`title` (sentence case), `value`, optional `trend` ("+12%"), `trendLabel` (plain
sentence, never a source/system name), `icon`, `compact`, `onClick` (makes it a button).

### `PageHeader` (`ui/PageHeader.jsx`)
`title`, `description` (one sentence), optional `eyebrow` (sentence case), `actions`.
Every module page starts with one in phase 2. The Topbar already shows the page name,
so PageHeader titles may be more specific ("Calls this week").

### `EmptyState` (`ui/EmptyState.jsx`)
`icon`, `title` (what is missing), `description` (what will appear and when),
`action` (the one button that fixes it), `compact`.

### `Tabs` (`ui/Tabs.jsx`)
`items=[{id,label,count?}]`, `value`, `onChange`, `label` (aria). `variant="segmented"`
for view switches (Today / 7 days / 30 days); `variant="pills"` for filter rows (scrolls
sideways on phones instead of wrapping). Arrow keys move between tabs.

### `DataTable` (`ui/DataTable.jsx`)
`columns=[{key, header, numeric?, className?, cellClassName?}]`, `rows`, `rowKey`,
`renderCell(row, column)`, `onRowClick`, `empty={title, description, action}`,
`loading`, `caption`. Scrolls horizontally inside its card on phones, never the page.

### `Avatar` (`ui/Avatar.jsx`)
`<Avatar name="Meera" live />` — stable colour per name, green pulsing ring while on a
call (reduced-motion safe). `<Avatar icon={Wallet} tone="warning" />` for system items.
Sizes `xs | sm | md | lg`.

### `Toolbar`, `SearchInput`, `SelectFilter` (`ui/Toolbar.jsx`)
Filter rows above lists: `<Toolbar><Tabs variant="pills"…/><Toolbar.Spacer/><SearchInput…/>
<SelectFilter label="Agent" options=[{value,label}] …/></Toolbar>`.

### `NotFound` (`ui/NotFound.jsx`)
Rendered by `AppShell` for any `#dashboard/<unknown>` route, with "Go to home".
New pages must be added to `CONSOLE_TABS` in `AppShell.jsx`.

### `Modal` (`ui/Modal.jsx`)
Unchanged API. Titles sentence case; destructive confirms use `variant="danger"`.

## 7. Motion

Short and purposeful: 150–220ms, ease-out. New feed items fade/rise 4px
(`.feed-item-enter`); live avatars pulse (`.avatar-live-ring`). Both are disabled under
`prefers-reduced-motion`. No motion on numbers that update every second.

## 8. Layout and responsiveness

- Must work at **375px** with no horizontal page scroll (`min-w-0` on flex/grid
  children, tables scroll inside their card) and look intentional at **1440px**.
- Two-column pages use `grid lg:grid-cols-[minmax(0,1fr)_320px] xl:…_340px]`; the rail
  stacks under the main column on phones, with a compact summary strip on top.

## 9. Live data

Poll with `useVisiblePoll(fn, delayFn, deps)` from `modules/home/useActivity.js`
(pauses while the tab is hidden, refreshes on return, never overlaps). ~5s while
something is live, 20–30s otherwise. Never one request per row.

## 10. Home (route `overview`)

The home page is a live activity feed (`modules/OverviewModule.jsx` + `modules/home/`),
backed by `GET /api/activity/feed` and `GET /api/activity/live`. Where the old Overview
content lives now:

| Old element | Now |
|---|---|
| Greeting + "Autonomous fleet active" + counts line | Greeting header with a one-line summary (on calls / needs you / wallet ₹) |
| Buy Number / Create Agent buttons | Header buttons (same `data-tour` and `data-testid`) + "Your team" rail card |
| Total calls, Talk time, Wallet minutes, Leads in pipeline, Active agents | Insights → five metric tiles; also rail "Today" and "Wallet" |
| Call activity chart (Today / 7 days / 30 days, incoming vs outgoing) | Insights → Call activity |
| Active fleet with Test / Build | Rail → Your team (live ring when on a call) |
| Recent live calls table with Inspect | Insights → Recent calls; live calls in rail and feed |
| AI lead stream | Insights → Recent leads; lead items in the feed |

## 11. Known copy still to fix in phase 2

`BillingModule` "Default web price · stack overrides apply"; `FollowUpQueue` raw
`label()` of statuses/reasons (use `statusWord`); `AgentOverview` lead stages and
`LeadPriority` dispositions via `replace(/_/g,' ')` (use `statusWord` /
`dispositionLabel`); `CallIntegrationPicker` app names (use one app-label map);
remaining 9–11px text and hard-coded hex across modules.
