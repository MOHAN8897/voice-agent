# MASTER UI REDESIGN PROMPT

## Modern Premium Skeuomorphic Voice-Agent Control Plane

You are the lead product designer, UX architect, and senior frontend engineer responsible for transforming the existing Voice Agent Platform UI into a **premium modern skeuomorphic interface**.

This is NOT a request to make the interface look like an old 2010-era glossy website.

The target is:

**Modern SaaS usability + premium industrial hardware aesthetics + tactile skeuomorphism + dark developer-console precision.**

The final product should feel like a sophisticated piece of professional audio/AI equipment translated into software.

Think:

* premium studio hardware
* high-end synthesizer
* professional audio console
* aerospace/industrial control interface
* modern Apple-era skeuomorphism
* physical knobs, switches and illuminated indicators
* machined metal
* glass
* rubber
* subtle brushed surfaces
* tactile buttons
* realistic depth
* precise technical typography

But combine those physical metaphors with a modern SaaS application architecture.

---

# 1. READ THE EXISTING PRODUCT DOCUMENTATION FIRST

Before changing UI code, inspect the repository and read the existing product documentation.

Important sources include:

* `01-master-prd.md`
* `02-requirements-reconciliation.md`
* `05-ux-console-and-dashboards.md`
* `08-implementation-roadmap.md`
* `11-ui-information-architecture.md`
* `16-mvp-implementation-skills.md`
* `17-product-decisions.md`
* `19-frontend-backend-nextjs-railway.md`
* `00-current-state-audit.md`
* `fix.md`
* `memory implemenation.md`

Do not invent product behavior that contradicts these documents.

The normative target UI is the Next.js App Router application in `web/`. The old `client/` SPA is historical reference only and must not become the target architecture.

The product workflow is:

Configure Agent
→ Configure Business Brain
→ Choose Voice Tier
→ Test Agent
→ Compare Models
→ Inspect Calls
→ Analyze Performance
→ Promote Configuration.

Preserve this workflow.

---

# 2. DESIGN OBJECTIVE

Transform the UI into:

## "TACTILE AI CONTROL ROOM"

The user should feel like they are operating a sophisticated physical machine.

However:

DO NOT make it feel like:

* a retro game
* a 1990s website
* a skeuomorphic calendar app
* an old Apple dashboard
* a glossy Web 2.0 website
* a toy
* a casino interface
* a cyberpunk neon dashboard

Instead:

**quiet luxury + engineering precision + physical tactility.**

The UI must communicate:

* reliability
* intelligence
* precision
* technical sophistication
* control
* transparency
* professional voice infrastructure

The existing product character is calm, precise, operational, Telugu-first and developer-capable. Preserve that character.

---

# 3. CORE VISUAL DIRECTION

Use a dark industrial material system.

Primary environment:

* deep graphite
* charcoal
* gunmetal
* near-black
* smoked glass
* dark anodized aluminum

Secondary materials:

* brushed aluminum
* black rubber
* dark glass
* subtle metal plates
* machined edges

Accent colors should be restrained.

Use accents primarily for:

* active state
* recording
* live state
* success
* warning
* error
* primary action

Do NOT make the entire application colorful.

The application should remain predominantly dark and neutral.

---

# 4. SKEUOMORPHIC MATERIAL SYSTEM

Create a reusable material system.

Every major surface must have a defined material.

## MATERIAL: CHASSIS

Used for:

* application background
* major navigation areas
* large structural surfaces

Appearance:

* dark graphite
* extremely subtle texture
* very low contrast
* barely visible material grain

It should feel like anodized metal.

---

## MATERIAL: MACHINED PANEL

Used for:

* major cards
* configuration panels
* settings sections
* agent workspace panels

Appearance:

* slightly lighter than chassis
* subtle inset border
* fine highlight along upper edge
* controlled shadow underneath
* subtle inner shadow

Avoid giant shadows.

---

## MATERIAL: GLASS

Used sparingly for:

* floating status panels
* live monitoring overlays
* temporary inspectors
* audio visualization panels

Appearance:

* translucent dark surface
* subtle border
* very small blur
* restrained highlight

Do not turn the entire UI into glassmorphism.

---

## MATERIAL: RUBBER

Used for:

* toggle tracks
* knobs
* physical control surfaces
* microphone controls
* transport controls

Appearance:

* matte
* slightly soft
* subtle depth
* no excessive shine

---

## MATERIAL: METAL CONTROL

Used for:

* knobs
* rotary selectors
* hardware-like buttons
* tier selectors
* transport controls

Appearance:

* machined metal
* circular highlights
* subtle edge bevel
* realistic pressed state

---

# 5. LIGHTING SYSTEM

This is extremely important.

Skeuomorphism should come from **consistent lighting**, not random shadows.

Define one global light source:

Top-left / upper-left.

Therefore:

Top-left edges:
slightly brighter.

Bottom-right edges:
slightly darker.

Pressed elements:
inner shadow.

Raised elements:
outer shadow + subtle highlight.

Every component must obey the same lighting direction.

Do not randomly reverse shadows.

---

# 6. DEPTH HIERARCHY

Use only a few depth levels.

LEVEL 0
Flat background.

LEVEL 1
Raised panel.

LEVEL 2
Interactive control.

LEVEL 3
Primary control / active hardware.

LEVEL 4
Floating overlay.

Do not give every element maximum depth.

The user must immediately understand what is:

* background
* panel
* control
* active control
* floating overlay

---

# 7. THE GOLDEN RULE OF SKEUOMORPHISM

Do NOT make everything look physical.

Use physical metaphors where they improve understanding.

Examples:

Voice control:
physical audio console.

Tier selection:
rotary/physical selector.

Live call:
professional recording hardware.

Latency:
instrument-style measurement.

Provider health:
hardware status LEDs.

Brain:
technical control panel.

Memory:
structured data module.

Calls:
professional monitoring/recording archive.

Benchmarks:
test laboratory.

Analytics:
instrumentation panel.

This creates semantic skeuomorphism instead of decorative skeuomorphism.

---

# 8. APPLICATION SHELL

Create a premium application shell.

Desktop:

LEFT:
compact vertical navigation.

CENTER:
main workspace.

RIGHT:
contextual inspector when needed.

TOP:
environment / agent / status / account controls.

The navigation should feel like a physical control panel integrated into the chassis.

Primary navigation:

1. Overview
2. Agents
3. Test Studio
4. Calls
5. Analytics
6. Benchmarks
7. Providers
8. Integrations
9. Settings

This navigation is normative in the product IA.

---

# 9. SIDEBAR DESIGN

Do not use a generic SaaS sidebar.

Create a tactile instrument-panel sidebar.

Each navigation item should have:

* icon
* label
* active indicator
* subtle inset/raised state
* optional status indicator

Active item:

* appears physically engaged
* slightly brighter surface
* subtle inner highlight
* tiny accent indicator
* subtle illumination

Inactive:

* matte
* low contrast
* quiet

Do not use huge glowing pills.

---

# 10. TOP BAR

Create a compact technical header.

Left:

Agent identity.

Example:

VOICE AGENT
Residential Sales Agent

Middle:

Environment selector:

DEV / STAGING / PRODUCTION

Right:

* connection state
* tier
* notifications
* user menu

Environment must be visually obvious because development, staging and production have different mutability rules.

Production should feel locked.

Development should feel editable.

Staging should feel controlled.

---

# 11. OVERVIEW PAGE

Create an instrumentation-style command center.

Top:

"System Overview"

Supporting information:

Agent health
Environment
Active version
Last deployment

Then create physical instrument modules.

## MODULE 1 — ACTIVE AGENTS

Show:

Active agents
Healthy agents
Agents needing attention

Use physical status LEDs.

---

## MODULE 2 — LIVE CALLS

Show:

Calls today
Active calls
Completed
Failed

---

## MODULE 3 — LATENCY

Show:

P50
P95
First audible byte

Use a beautiful instrumentation graph.

Do not use generic dashboard cards.

Make it feel like a precision measurement instrument.

---

## MODULE 4 — COST

Show:

Today
This month
Estimated cost per minute

---

## MODULE 5 — SYSTEM HEALTH

STT
LLM
TTS
Database
Worker

Each should have a physical status lamp.

The Overview information is derived from the normative sitemap.

---

# 12. AGENTS PAGE

This should feel like a physical equipment rack.

Each agent is represented as a premium hardware module.

Agent card:

Agent name
Status
Language
Tier
Environment
Version
Last call
Health

Primary action:

OPEN AGENT

Secondary:

TEST

The agent workspace must expose:

Summary
Business Brain
Platform Brain where permitted
Voice & Models
Memory Schema
Tools & Actions
Channels
Versions & Deployment.

---

# 13. AGENT WORKSPACE

This is one of the most important screens.

Create a professional "console within the console."

Header:

Agent name

Status:

DRAFT
READY
ACTIVE
DEPLOYING
FAILED

Show:

Environment
Version
Tier
Language
Channel readiness

Then create a setup progress strip:

Brain
Voice
Memory
Tools
Channels
Test
Deploy

Each stage should have a physical status indicator.

The user should always understand:

"What is configured?"

"What is missing?"

"What will happen if I deploy?"

---

# 14. BUSINESS BRAIN

This must feel like a sophisticated programmable instrument.

Do NOT create a generic textarea page.

Use structured physical modules.

Sections:

1. Identity & Purpose
2. Business Facts
3. Actions & Limits
4. Qualification Flow
5. Callback / Appointment Flow
6. Scope & Redirects
7. Guardrails
8. FAQ

These eight sections are explicitly defined by the product requirements.

Each section should be collapsible.

Each section:

Header
Status
Completion indicator
Edit control
Preview control

When opened:

structured fields
rich text
rules
examples
validation

---

# 15. RAW VS OPTIMIZED BRAIN

This distinction must be visually obvious.

Create:

USER SOURCE

and

OPTIMIZED BRAIN

Do not allow the customer to accidentally confuse them.

The raw business prompt remains the source of truth, while optimized output is internal, reviewable and versioned.

Use different material treatments.

Raw:

paper-like / editable technical panel.

Optimized:

machined dark panel / read-only compiled module.

Compiled:

"LOCKED VERSION"

with version number.

---

# 16. VOICE & MODELS

Make this feel like an audio hardware rack.

Three major modules:

STT
LLM
TTS

Each should have a physical selector.

Example:

┌ STT ┐
Sarvam
saaras:v3
TELUGU
● HEALTHY

┌ LLM ┐
OpenAI
configured model
STREAMING
● HEALTHY

┌ TTS ┐
Sarvam
bulbul:v3
TELUGU
● HEALTHY

Do not hard-code models into UI.

Use the backend registry.

---

# 17. LOW / MEDIUM / PREMIUM

This should be one of the signature UI elements.

Do NOT use ordinary radio buttons.

Create a physical tier selector.

Three positions:

LOW
MEDIUM
PREMIUM

Possible visual metaphor:

machined rotary dial / industrial selector.

When selecting:

LOW:

Cost:
lowest

Latency:
fast

Quality:
acceptable

MEDIUM:

balanced

PREMIUM:

highest quality

The product requires exactly three customer-facing tiers.

---

# 18. TEST STUDIO

This should look like a professional voice laboratory.

Main layout:

LEFT:
configuration rack

CENTER:
live conversation

RIGHT:
diagnostics

Bottom:
latency waterfall

The Test Studio must support:

Browser live test
PSTN/Plivo test
conversation event stream
live transcript
memory projection inspector
latency waterfall
errors/provider events.

---

# 19. LIVE VOICE CONTROL

Create a large physical microphone/voice control.

Possible structure:

Large circular control.

Idle:

READY

Connecting:

CONNECTING

Listening:

LISTENING

Thinking:

THINKING

Speaking:

SPEAKING

Ended:

ENDED

The state sequence already exists in the UX specification.

The control should visually behave like professional recording hardware.

---

# 20. TRANSCRIPT

Transcript should feel like a live monitoring console.

USER:

Telugu transcript

timestamp

STT latency

AGENT:

streaming response

TTS playing indicator

Interrupted turns:

subtle strikethrough

"INTERRUPTED"

Barge-in:

small visual response indicator.

Do not make transcript bubbles look like a generic ChatGPT clone.

---

# 21. LATENCY WATERFALL

Create a beautiful technical visualization.

Each turn:

STT
───────
LLM
────────────
TTS
──────

Show:

STT final latency
LLM TTFT
TTS first audio
E2E latency

The product explicitly requires measuring the pipeline rather than just the model.

Use a professional oscilloscope/instrument feel.

---

# 22. CALLS PAGE

Calls are the primary unit of review.

Do NOT design Calls as a generic CRUD table.

Create:

FILTER BAR

CALL LIST

DETAIL INSPECTOR

Call row:

time
customer
channel
duration
tier
disposition
summary

Clicking a call opens the full investigation workspace.

The product requirements explicitly define Calls as the unit of review and require durable call records.

---

# 23. CALL DETAIL

Create a professional call investigation console.

Header:

CALL ID
MEDIUM
4m 32s
QUALIFIED

Main sections:

Outcome
Audio
Transcript
Timeline
Memory
Trace
Metadata

Timeline should correlate:

USER AUDIO
STT
LLM
TTS
MEMORY
ERRORS

The product requires unified per-call debugging across these systems.

---

# 24. MEMORY UI

Memory should look like structured machine state.

Do NOT make it a chat bubble.

Show:

FACTS

PREFERENCES

IMPORTANT CONTEXT

SUMMARY

Use a live state visualization.

Example:

CUSTOMER
├── name
├── location
├── budget
└── requirements

Make changes visibly animate into the state.

But keep animation subtle.

---

# 25. ANALYTICS

Analytics should look like professional instrumentation.

Pages:

Volume
Quality
Latency
Reliability
Cost
Memory
Provider performance
Combination performance

Separate aggregate analytics from raw call inspection.

This separation is explicitly required.

Charts should be:

clean
technical
high information density
minimal decoration

Do not use generic colorful SaaS charts.

---

# 26. BENCHMARKS

Create a "voice laboratory" experience.

Workflow:

Create Benchmark

↓

Select Environment

↓

Select Language

↓

Select Scenarios

↓

Select compatible combinations

↓

Estimate Runs / Cost

↓

Run

↓

Compare

↓

Review

↓

Promote

This workflow is specified in the benchmark UX requirements.

Results should compare:

Latency
STT accuracy
LLM quality
TTS quality
Reliability
Cost

Show winners **per metric**.

Never show one mysterious "best model" without explaining why.

---

# 27. PROVIDERS

Provider registry should look like a server rack.

Sections:

STT
LLM
TTS

Each provider:

Provider name
Model
Stage
Enabled
Configured
Health
Streaming
Realtime
Languages
Capabilities
Pricing
Last health check

The provider registry requirements explicitly call for these safe metadata fields and forbid displaying secrets.

---

# 28. PROVIDER STATUS LIGHTS

Use small physical indicators.

GREEN:
healthy

AMBER:
degraded

RED:
failed

GREY:
not configured

Do not communicate status using color alone.

Add:

Healthy
Degraded
Unavailable
Not configured

for accessibility.

---

# 29. INTEGRATIONS

Create hardware-module style integration cards.

Plivo
Telephony
CRM/Webhooks
Tool connectors
Knowledge sources

Show:

CONNECTED

NOT CONFIGURED

ERROR

TEST

Never expose credentials.

---

# 30. SETTINGS

Settings should feel like an engineering control cabinet.

Groups:

Organization
Members & roles
Retention & privacy
Environments
Scoring weights
Audit log
Developer diagnostics

Do not overwhelm the user.

Use progressive disclosure.

---

# 31. BUTTON DESIGN

Buttons must feel tactile.

PRIMARY:

Raised physical button.

Hover:

slightly brighter.

Pressed:

moves down slightly.

Focus:

visible technical focus ring.

Disabled:

physically recessed / unavailable.

Do not make buttons huge glossy pills.

Avoid excessive border radius.

Use moderate radii.

---

# 32. INPUT DESIGN

Inputs should look inset into the hardware.

Use:

inner shadow
subtle bevel
dark surface
clear text

Focus:

thin accent illumination.

Error:

clear label + subtle red indicator.

---

# 33. TOGGLE DESIGN

Create physical switches.

OFF:

recessed.

ON:

raised with tiny indicator.

The toggle must visually communicate its state without relying solely on color.

---

# 34. SLIDERS

For audio controls:

Use physical fader metaphors.

Examples:

Temperature
Voice speed
Barge sensitivity
Volume

Use vertical faders where appropriate.

Do not turn every setting into a slider.

---

# 35. KNOBS

Use knobs only where rotary controls make semantic sense.

Good examples:

Voice temperature
Voice speed
Sensitivity
Threshold

Do NOT use knobs for:

text
model selection
navigation
ordinary settings

Each knob must have:

label
current value
keyboard equivalent
accessible input

---

# 36. ICONS

Use simple technical icons.

Avoid:

emoji
overly decorative 3D icons
random icon styles

Icons should look like industrial instrumentation symbols.

Maintain consistent stroke weight.

---

# 37. TYPOGRAPHY

Typography should be modern.

Primary:

clean sans-serif.

Technical numbers:

monospace or technical numeral font.

Use Telugu-capable typography.

Telugu text needs appropriate line height and a tested Telugu-capable font stack.

Do not use overly futuristic fonts.

Do not sacrifice readability.

---

# 38. SPACING

Use a disciplined spacing system.

Do not fill every pixel.

Create:

small
medium
large
section

spacing tokens.

Skeuomorphism needs breathing room.

---

# 39. BORDER RADIUS

Avoid excessive rounded cards.

Use:

small radius for hardware panels.

medium radius for major surfaces.

larger radius only for:

dialogs
floating surfaces
special controls

The UI should feel machined rather than inflated.

---

# 40. MICRO-INTERACTIONS

Use motion only to communicate physical behavior.

Examples:

Button press:
1–2px physical depression.

Switch:
mechanical movement.

Knob:
rotation.

Panel:
subtle elevation.

Live call:
soft status pulse.

Audio:
subtle waveform movement.

Memory:
state update transition.

Deployment:
progressive mechanical indicator.

Do NOT use:

constant floating animations
large spring animations
excessive page transitions
neon glows
attention-grabbing motion

Respect reduced-motion preferences.

---

# 41. EMPTY STATES

Every empty state should feel intentional.

Example:

NO CALLS YET

small explanation

START VOICE TEST

Do not show blank cards.

The UX requirements explicitly require loading, empty, partial, validation, permission, provider-unavailable, retry, archived and unsaved states.

---

# 42. ERROR STATES

Errors must look like diagnostic instruments.

Example:

TTS CONNECTION FAILED

Status:
UNAVAILABLE

Cause:
Provider connection timeout

Action:

RETRY

VIEW TRACE

Do not simply show:

"Something went wrong."

---

# 43. PRODUCTION STATE

Production must feel materially different.

Use:

LOCKED

ACTIVE VERSION

v1.4.2

DEPLOYED

The UI must communicate that production is immutable and changes require promotion.

---

# 44. DEVELOPMENT STATE

Development:

EDITABLE

DRAFT

TEST

BENCHMARK

STAGING:

APPROVED CONFIGURATIONS

REGRESSION TEST

PRODUCTION:

ACTIVE

LOCKED

PROMOTE NEW VERSION

---

# 45. ENV MODE VS FRONTEND MODE

Respect the product configuration modes.

ENV mode:

show only:

LOW
MEDIUM
PREMIUM

and resolved stack.

Hide provider/model editing.

FRONTEND mode:

show enabled compatible provider/model selectors.

Backend remains authoritative.

The UI must not expose controls that are unavailable in the active mode.

---

# 46. RESPONSIVE DESIGN

This is mandatory.

Desktop:

persistent navigation
multi-panel debugging

Tablet:

collapsible navigation
stacked inspector

Mobile:

voice testing
call list
call summary
critical actions

Do NOT squeeze complex benchmark tables onto mobile.

Use metric-by-metric comparison.

These responsive rules are explicitly required.

---

# 47. ACCESSIBILITY

Target WCAG 2.2 AA.

Requirements:

keyboard navigation
visible focus
aria labels
aria-live for transcript updates
no color-only status
accessible audio controls
accessible accordions
accessible dialogs
accessible tables
accessible sliders
accessible knobs

Do not sacrifice accessibility for skeuomorphism.

---

# 48. PERFORMANCE

Do not create a visually impressive but slow application.

Avoid:

huge background images
unnecessary WebGL
heavy animation libraries
massive SVG assets
continuous expensive shadows
unbounded animation

Use CSS where possible.

Keep the interface performant on ordinary laptops and mobile devices.

The project is Next.js App Router + TypeScript + Tailwind and should remain within that architecture.

---

# 49. COMPONENT ARCHITECTURE

Create reusable components rather than page-specific CSS.

Suggested system:

/components/ui/

skeuo-panel
skeuo-button
skeuo-switch
skeuo-slider
skeuo-knob
skeuo-meter
skeuo-status-light
skeuo-badge
skeuo-card
skeuo-input
skeuo-select
skeuo-tabs
skeuo-dialog
skeuo-progress
skeuo-fader
skeuo-display

/components/voice/

voice-console
voice-state
live-transcript
audio-meter
latency-waterfall

/components/agent/

agent-header
agent-health
brain-section
version-status
deployment-panel

/components/providers/

provider-rack
provider-module
model-selector
health-indicator

/components/calls/

call-list
call-detail
call-timeline
call-outcome
call-audio

/components/analytics/

metric-panel
latency-chart
quality-chart
cost-chart

---

# 50. DESIGN TOKENS

Create a centralized design-token system.

Example conceptual tokens:

--surface-chassis
--surface-panel
--surface-panel-raised
--surface-panel-inset
--surface-glass

--border-subtle
--border-highlight
--border-inset

--shadow-raised
--shadow-inset
--shadow-floating

--text-primary
--text-secondary
--text-muted

--accent-primary
--status-success
--status-warning
--status-error
--status-info

--radius-sm
--radius-md
--radius-lg

--depth-1
--depth-2
--depth-3
--depth-4

Do NOT scatter arbitrary shadow/color values throughout the application.

---

# 51. DO NOT USE THESE VISUAL PATTERNS

Absolutely avoid:

❌ giant shadows
❌ excessive gradients
❌ neon cyberpunk
❌ excessive glassmorphism
❌ huge rounded pills
❌ cartoon icons
❌ emoji as UI
❌ excessive glow
❌ rainbow dashboards
❌ fake 3D everywhere
❌ bevel on every element
❌ every element looking clickable
❌ retro 90s styling
❌ excessive skeuomorphic decoration
❌ poor contrast
❌ cramped layouts

---

# 52. WHAT "GOOD" LOOKS LIKE

The final interface should make someone think:

"This looks like professional voice infrastructure."

Not:

"This looks like a website with some shadows."

The tactile effects should be subtle enough that the application still feels modern.

The physical metaphors should help users understand the function of each control.

---

# 53. IMPLEMENTATION PROCESS

Do NOT immediately rewrite everything.

First:

1. Inspect existing `web/`.
2. Inspect current components.
3. Inspect current styles.
4. Inspect current routes.
5. Identify reusable components.
6. Identify existing functionality that must remain unchanged.
7. Map existing screens to the new IA.
8. Build the design token system.
9. Build the base skeuomorphic components.
10. Migrate screens progressively.

Preserve working functionality.

The current live voice path is valuable and must not be unnecessarily replaced. The project specifically requires preserving existing realtime behavior and architecture where possible.

---

# 54. IMPLEMENTATION ORDER

Implement in this order:

PHASE 1

Design tokens
+
application shell
+
navigation
+
responsive framework

PHASE 2

Skeuomorphic component library.

PHASE 3

Overview.

PHASE 4

Agents.

PHASE 5

Agent workspace.

PHASE 6

Business Brain.

PHASE 7

Voice & Models.

PHASE 8

Test Studio.

PHASE 9

Calls.

PHASE 10

Analytics.

PHASE 11

Benchmarks.

PHASE 12

Providers.

PHASE 13

Integrations.

PHASE 14

Settings.

PHASE 15

Responsive/mobile polish.

PHASE 16

Accessibility audit.

PHASE 17

Visual QA.

---

# 55. VISUAL QA LOOP

After implementation, do NOT assume the UI is finished.

For every major page:

1. Run the application.
2. Inspect at desktop width.
3. Inspect at tablet width.
4. Inspect at mobile width.
5. Check visual hierarchy.
6. Check contrast.
7. Check shadows.
8. Check material consistency.
9. Check button press states.
10. Check keyboard navigation.
11. Check loading state.
12. Check empty state.
13. Check error state.
14. Check production state.
15. Check reduced motion.
16. Fix inconsistencies.

Then perform a final "skeuomorphism restraint pass":

Remove any decorative effect that does not communicate hierarchy, state or function.

---

# 56. CRITICAL PRODUCT RULE

The UI is NOT the source of truth.

Backend permissions, provider compatibility, environment rules, versioning and security remain authoritative.

Never expose:

API keys
provider secrets
protected Platform Brain content
unauthorized tenant information

The UI must mirror backend permissions, never replace them.

---

# 57. FINAL QUALITY BAR

Do not stop when the interface technically works.

Continue polishing until:

* every screen belongs to the same visual system
* every control has consistent depth
* every material has consistent lighting
* every state is understandable
* every page has clear hierarchy
* mobile is genuinely usable
* Telugu text looks natural
* live voice feels like a professional instrument
* Calls feel like a professional recording archive
* Benchmarks feel like a laboratory
* Providers feel like a hardware rack
* Business Brain feels like a programmable control system
* Analytics feel like instrumentation
* Production feels locked and trustworthy

The final product should look like a **premium professional voice-agent operating system**, not a generic SaaS dashboard.

---

# 58. IMPORTANT — DO NOT FAKE FUNCTIONALITY

If backend functionality does not yet exist:

DO NOT invent fake APIs.

DO NOT silently fabricate data.

DO NOT make buttons appear functional when they are not.

Use clearly labeled mock/demo states only where necessary for visual development, and keep them easy to replace with real data.

Preserve existing APIs and behavior until the corresponding migration is implemented.

---

# 59. FINAL COMMAND

Now inspect the repository and implement this redesign.

First create the design foundation.

Then implement the application shell.

Then migrate the pages progressively.

Do not rewrite working backend functionality merely to achieve the visual redesign.

Do not modify product requirements.

Do not remove required screens.

Do not simplify away important technical controls.

Do not turn this into a generic dashboard.

Build the **Modern Premium Skeuomorphic Voice Agent Control Plane**.

The final result must be production-quality, responsive, accessible, tactile, restrained, technically credible, and visually distinctive.


agent instructions : ODE
 ↓
RUN WEBSITE
 ↓
BROWSER
 ↓
SCREENSHOT
 ↓
VISUAL ANALYSIS
 ↓
UX ANALYSIS
 ↓
ANIMATION ANALYSIS
 ↓
DESIGN SYSTEM ANALYSIS
 ↓
IMPLEMENT IMPROVEMENTS
 ↓
SCREENSHOT AGAIN
 ↓
COMPARE
 ↓
REPEAT