# SAM Default Design Standards

**Purpose:** Baseline UI quality standards for all SAM-built web applications. Applied automatically when the PRD does not include a design section or UX design document. PRD-provided design guidance takes precedence over these defaults.

---

## Typography

- **Font:** Inter (Google Fonts) — load in `index.html`, set in Tailwind config
- **Fallback:** `system-ui, -apple-system, sans-serif`
- **Scale:** Use Tailwind defaults — `text-sm`, `text-base`, `text-lg`, `text-xl`, `text-2xl`, `text-3xl`
- **Weights:** 400 (body), 500 (labels/emphasis), 600 (headings), 700 (hero/display)
- **Line height:** 1.5 for body, 1.2 for headings
- **Heading hierarchy:** Each level visually distinct (size + weight)

## Colors

- **Define as Tailwind theme tokens** — never use raw color classes (`bg-slate-900`)
- **Token names:** `background`, `foreground`, `primary`, `primary-foreground`, `muted`, `muted-foreground`, `accent`, `destructive`, `border`, `input`, `ring`
- **Dark mode:** Mandatory. Use CSS variables toggled by a `.dark` class
- **Default palette:** Neutral base (zinc/slate) + one accent (indigo/blue)
- **Contrast:** WCAG AA minimum — 4.5:1 for normal text, 3:1 for large text

## Spacing

- **Base unit:** 4px (Tailwind's default scale)
- **Consistent padding:** Use `p-2`(8px), `p-3`(12px), `p-4`(16px), `p-6`(24px), `p-8`(32px)
- **Component gaps:** Use `gap-` utilities, not ad-hoc margins
- **Page layout:** Max content width (`max-w-7xl`), centered, with horizontal padding

## Components

- **Buttons:** Primary (filled), Secondary (outline), Ghost (text-only). All must have hover, focus, disabled, and loading states
- **Inputs:** Visible border, focus ring (`ring-2`), error state (red border + message), helper text support
- **Cards:** Consistent `rounded-lg`, subtle border or shadow, uniform padding
- **Forms:** Client-side validation with user-friendly messages (not regex descriptions). Show errors inline below each field
- **Navigation:** Clean top navbar. Responsive — hamburger menu on mobile

## States (Mandatory)

- **Loading:** Skeleton placeholders or spinner for async operations. Never show a blank void
- **Error:** Clear message describing what went wrong + a retry/recovery action
- **Empty:** Helpful placeholder with illustration or next-step guidance, not just "No data"
- **Success:** Brief confirmation (toast or inline), then get out of the way

## Responsive Design

- **Approach:** Mobile-first
- **Breakpoints:** `sm`(640px), `md`(768px), `lg`(1024px), `xl`(1280px)
- **Touch targets:** Minimum 44x44px on mobile
- **Navigation:** Adapts to screen size (sidebar collapses, nav becomes hamburger)
- **Typography:** Scales down gracefully on small screens

## Micro-interactions

- **Transitions:** 150-200ms ease on hover/focus for buttons, links, inputs
- **Page entrance:** Subtle fade-in or slide-up on route change (optional, use Framer Motion if in deps)
- **Button feedback:** Visual press/active state
- **Form submission:** Button shows loading state, disables during submit

## Accessibility (Baseline)

- **Keyboard navigation:** All interactive elements focusable and operable via keyboard
- **Focus indicators:** Visible focus ring on all interactive elements
- **ARIA labels:** On icon-only buttons, form inputs, and dynamic content
- **Semantic HTML:** Use `<nav>`, `<main>`, `<section>`, `<button>`, not generic `<div>` for everything
- **Screen reader:** Page structure navigable via headings hierarchy

## Project Setup Requirements

When scaffolding a new project with UI:

1. **Tailwind config:** Define custom theme with all color tokens, font family, and extended spacing
2. **Global CSS:** Import Inter font, define CSS variables for light/dark themes
3. **Base layout:** App shell with navbar, main content area, consistent padding
4. **Utility components:** Create reusable Button, Input, Card components in the first UI story

---

## Agent Integration

- **Atlas (Step 1):** Check PRD for design guidance. If none found, reference this document in the architecture-ref.md
- **SAM (Step 2):** Include "Follow default-design-standards.md" in Technical Notes of UI stories
- **Titan (RED):** Write tests verifying: custom font loaded, theme tokens defined, no raw color classes, interactive states present
- **Dyna (GREEN):** Implement Tailwind config and base components first, then build features using tokens
- **Iris (UI Review):** Review against these standards — flag raw defaults, missing states, accessibility gaps
- **Cosmo (CSS Review):** Verify token consistency, contrast ratios, spacing system compliance
