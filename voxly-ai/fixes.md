# Voxly AI — Production Master Blueprint & User Console Architecture

> **Target Codebase**: `d:\Antigravity` (`voxly-ai`)  
> **Evaluation Framework**: Emil Kowalski Design Philosophy (Craft, Restraint, Tactile Feedback, Visual Hierarchy) + **Enterprise User Console Architecture** + **Strict Technical SEO & Core Web Vitals Optimization**  
> **System Status**: Authoritative User Console, Agent Management & SEO Master Blueprint  

---

## Table of Contents
1. [Executive Summary & Design North Star](#1-executive-summary--design-north-star)
2. [Part 1: Emil Kowalski Design Critique & 19 Anti-Pattern Audit](#part-1-emil-kowalski-design-critique--19-anti-pattern-audit)
3. [Part 2: Technical SEO, Discoverability & Core Web Vitals Specification](#part-2-technical-seo-discoverability--core-web-vitals-specification)
   - [2.1 Metadata, Social Cards & Canonical URLs](#21-metadata-social-cards--canonical-urls)
   - [2.2 Heading Hierarchy & Semantic HTML Standards](#22-heading-hierarchy--semantic-html-standards)
   - [2.3 Schema.org Structured Data (JSON-LD) Master Templates](#23-schemaorg-structured-data-json-ld-master-templates)
   - [2.4 Crawling & Indexing Policy: Public vs. Authenticated Console](#24-crawling--indexing-policy-public-vs-authenticated-console)
   - [2.5 Core Web Vitals (CWV) Performance Budget](#25-core-web-vitals-cwv-performance-budget)
   - [2.6 Unique ID Naming Convention for Testing & Deep Linking](#26-unique-id-naming-convention-for-testing--deep-linking)
4. [Part 3: Platform Architecture — Public Marketing Surface vs. Authenticated Console](#part-3-platform-architecture--public-marketing-surface-vs-authenticated-console)
5. [Part 4: Unified User Console Architecture — Module by Module](#part-4-unified-user-console-architecture--module-by-module)
   - [4.1 Global AppShell, Topbar & Command Palette (⌘K)](#41-global-appshell-topbar--command-palette-k)
   - [4.2 Module 1: Unified Overview Dashboard (Single-Pane-of-Glass Management)](#42-module-1-unified-overview-dashboard-single-pane-of-glass-management)
   - [4.3 Module 2: AI Employees Fleet Management (Create N Agents)](#43-module-2-ai-employees-fleet-management-create-n-agents)
   - [4.4 Module 3: Agent Creation Wizard & Script Flow Studio](#44-module-3-agent-creation-wizard--script-flow-studio)
   - [4.5 Module 4: Virtual Number Buying & Direct Agent Assignment](#45-module-4-virtual-number-buying--direct-agent-assignment)
   - [4.6 Module 5: Inbound & Outbound Call Operations](#46-module-5-inbound--outbound-call-operations)
   - [4.7 Module 6: Call Logs & Diarized Audio Waveform Drawer](#47-module-6-call-logs--diarized-audio-waveform-drawer)
   - [4.8 Module 7: Autonomous AI Lead Engine (Call Extraction & Pipeline)](#48-module-7-autonomous-ai-lead-engine-call-extraction--pipeline)
   - [4.9 Module 8: Bulk Campaigns Dialing Engine](#49-module-8-bulk-campaigns-dialing-engine)
   - [4.10 Module 9: Wallet, Per-Second Billing & Usage](#410-module-9-wallet-per-second-billing--usage)
   - [4.11 Module 10: Integrations & Webhook Hub](#411-module-10-integrations--webhook-hub)
   - [4.12 Module 11: Settings, Team Roles & Security](#412-module-11-settings-team-roles--security)
   - [4.13 Module 12: Realtime "Talk to AI" Interactive Testing Console](#413-module-12-realtime-talk-to-ai-interactive-testing-console)
6. [Part 5: Emil Kowalski UI Design System Tokens & Tactile Primitives](#part-5-emil-kowalski-ui-design-system-tokens--tactile-primitives)
7. [Part 6: Frontend Component Hierarchy & Implementation Roadmap](#part-6-frontend-component-hierarchy--implementation-roadmap)
8. [Part 7: Pre-Launch Verification & Quality Assurance Checklist](#part-7-pre-launch-verification--quality-assurance-checklist)

---

## 1. Executive Summary & Design North Star

This blueprint serves as the definitive specification for the **Voxly AI User Console (`/dashboard/*`)** and surrounding platform interfaces.

> **Backend Context**: The underlying LLM orchestration, WebRTC/SIP media servers, speech synthesis pipelines, and carrier PSTN switches are **already configured and operational in the backend**.  
> **Frontend Mission**: Deliver a world-class, high-craft **User Console** where business operators and developers can create $N$ autonomous agents, edit scripts and conversational flows, search and purchase virtual phone numbers, bind numbers to agents, manage inbound/outbound calls, review call recordings, extract and qualify leads, execute bulk outbound campaigns, and monitor everything in one unified dashboard.

### Core Architectural Directives
1. **Hero UI as the Design North Star**: The completed public landing page hero section (`Hero.jsx`) is the visual anchor. Every screen, workbench, dialog, and telemetry card in the authenticated console inherits the Hero's visual polish, high-contrast typography, disciplined spacing, tactile button interactions, and reactive character intelligence.
2. **Elimination of Generic SaaS Tropes**: Strict adherence to the Emil Kowalski design philosophy: solid obsidian surfaces (`#0B0A10`, `#111019`), hairline borders (`#262438`), tactile button depressions (`active:scale-[0.98]`), and zero generic purple gradients or blurry glassmorphism.
3. **Rigorous Technical SEO**: Complete compliance with single `<h1>` hierarchy, Schema.org JSON-LD structured data, metadata standards, Core Web Vitals budgets, and strict indexing isolation (`noindex, nofollow` on `/dashboard/*`).
4. **Intuitive Multi-Agent Management**: Frictionless workflows to create, name, configure, duplicate, test, and deploy multiple AI agents across departments (Sales, Reception, Support, Debt Collection).

---

## Part 1: Emil Kowalski Design Critique & 19 Anti-Pattern Audit

The UI design system across the entire application enforces the elimination of generic AI/SaaS design tropes:

| # | Anti-Pattern | Violation Pattern | Required Remediation |
|---|---|---|---|
| **1** | **Purple-to-blue gradients** | `bg-gradient-to-r from-[#7657E8] to-[#9B7BF7]` on buttons, cards, and backgrounds. | Replace with solid brand neutrals: rich obsidian `#0B0A10`, surface `#111019`, crisp white `#FFFFFF`, subtle stone borders `#262438`, and restrained violet `#6344E7` as an accent. |
| **2** | **Gradient-colored hero text** | `.gradient-text-lavender` clipping masks applied to headlines. | Remove all text clipping gradients. Use solid, high-contrast typography (`#0F0E17` in light mode, `#F7F7FB` on dark panels) for superior optical legibility. |
| **3** | **Emojis in headings** | Emojis in badges, tables, and headers (`🤖`, `📞`, `⚡`, `👩‍💼`). | Remove all emojis from headings, navigation, and badges. Use curated monochrome SVG icons or pure typographic weight. |
| **4** | **Defaulting to Inter everywhere** | Generic uncalibrated font stack without typographic contrast. | Establish a clear typographic scale: Plus Jakarta Sans for crisp display headings, balanced with clean body geometry and monospace accents (`JetBrains Mono`) for telemetry data. |
| **5** | **Excessive colored-border cards** | Cards using `border-[#7657E8]/15` or `border-[#7657E8]/40`. | Replace tinted borders with neutral hairline borders (`border-black/5` in light; `border-white/10` or `#262438` in dark). Rely on whitespace and subtle elevation rather than colored outlines. |
| **6** | **Generic glassmorphism cards** | `backdrop-blur-xl`, `bg-white/10` with semi-transparent frosted borders. | Replace glass cards with solid, opaque surfaces (`#FFFFFF` on `#FAF9FD`, or clean dark `#181724` on `#0B0A10`). Reserve blur strictly for sticky navigation bars. |
| **7** | **Low-contrast dark mode** | Secondary text using `text-white/40` or `text-white/50` on dark grey. | Ensure all body text meets WCAG AA 4.5:1 minimum contrast. Lighten secondary text to `#A19EAD` or `#D1CFDB`. |
| **8** | **Repetitive 3-card & 4-card grids** | Sections relying on identical card boxes with centered top icons. | Break monotony: use varied asymmetric editorial layouts—split feature columns, data tables, interactive workbench split-views, and narrative horizontal bands. |
| **9** | **Unnecessary badges above headlines** | Every section starting with an eyebrow pill badge (`Sparkles`, `Bot`, `Zap`). | Eliminate decorative eyebrow badges where they add no information. Let bold, direct section titles drive the hierarchy. |
| **10** | **Lucide icons everywhere** | Decorative icons placed in small colored rounded rectangles above text. | Remove decorative icon containers. Icons should only exist where they directly aid navigation or clarify functionality (e.g. Play, Mic, Check, Phone). |
| **11** | **Default/shallow styling** | Reliance on standard Tailwind rounded pills (`rounded-full`) and basic shadow utilities. | Use tailored border radiuses (`rounded-xl` / `rounded-2xl` max), bespoke micro-shadows (`box-shadow: 0 1px 2px rgba(0,0,0,0.04)`), and crisp 1px borders. |
| **12** | **Generic fade-in animations** | Multiple `animate-in fade-in zoom-in-95` classes scattered throughout components. | Remove non-functional entrance animations. Keep animations functional: smooth state transitions, audio waveforms, and 3D character interactions. |
| **13** | **Unnecessary cursor-following effects** | Floating blur orbs following mouse or static ambient blur blobs. | Remove blurred decorative background blobs (`blur-3xl`, `blur-[140px]`). Ground the page in clean negative space. |
| **14** | **Fade/opacity-only button hovers** | Buttons relying on `hover:opacity-90` or simple background shifts. | Implement tactile, purposeful button states: subtle active depression (`active:scale-[0.98]`), micro-border illumination, and distinct keyboard focus rings. |
| **15** | **Inconsistent spacing system** | Varying section padding (`py-24`, `py-32`, varying gaps `gap-6`, `gap-8`, `gap-10`). | Enforce an 8pt spatial rhythm: consistent section padding (`py-20` sm: `py-28`), standard container max-width (`max-w-6xl`), and consistent component margins. |
| **16** | **Excessive em dashes in copy** | Copy frequently uses "—" as an empty conversational pause. | Replace em dashes with crisp, professional sentence structures and bulleted specifications. |
| **17** | **Generic AI/SaaS buzzwords** | Phrases like "Supercharge workflows", "Autonomous magic", "Deliver 10x results". | Replace with concrete operational terminology: "Sub-500ms call latency", "BANT qualification", "Direct SIP trunking", "Zero hold times". |
| **18** | **Forced serif-italic accents** | Occasional italicized typography without brand purpose. | Keep typographic styling clean, upright, and legible throughout. |
| **19** | **Arbitrary font combinations** | Caveat handwriting font loaded in `index.html` without cohesive product utility. | Unload unused fonts (`Caveat`) to save bandwidth and maintain typographic discipline. |

---

## Part 2: Technical SEO, Discoverability & Core Web Vitals Specification

Every public page and documentation asset within Voxly must adhere to enterprise SEO standards to ensure rapid indexing, maximum organic discoverability, and high-CTR social previews.

### 2.1 Metadata, Social Cards & Canonical URLs

All public HTML documents must declare complete, valid meta tags within `<head>`:

```html
<!-- Primary Meta Tags -->
<title>Voxly — The AI Employee for Every Conversation</title>
<meta name="title" content="Voxly — The AI Employee for Every Conversation" />
<meta name="description" content="Deploy autonomous AI voice agents that answer inbound calls, execute outbound phone campaigns, qualify leads, and connect to your CRM with sub-500ms latency." />
<meta name="keywords" content="AI voice agent, voice AI, autonomous phone agent, AI receptionist, outbound sales AI, telephony AI, SIP trunking AI" />
<link rel="canonical" href="https://voxly.ai" />

<!-- Open Graph / Facebook -->
<meta property="og:type" content="website" />
<meta property="og:url" content="https://voxly.ai" />
<meta property="og:title" content="Voxly — The AI Employee for Every Conversation" />
<meta property="og:description" content="Deploy autonomous AI voice agents that talk naturally on the phone with sub-500ms latency. Inbound, outbound, and live CRM sync." />
<meta property="og:image" content="https://voxly.ai/images/og-voxly-preview.png" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
<meta property="og:locale" content="en_US" />

<!-- Twitter / X -->
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:url" content="https://voxly.ai" />
<meta name="twitter:title" content="Voxly — The AI Employee for Every Conversation" />
<meta name="twitter:description" content="Deploy autonomous AI voice agents that talk naturally on the phone with sub-500ms latency. Inbound, outbound, and live CRM sync." />
<meta name="twitter:image" content="https://voxly.ai/images/og-voxly-preview.png" />
<meta name="twitter:creator" content="@VoxlyAI" />
```

### 2.2 Heading Hierarchy & Semantic HTML Standards

- **Single `<h1>` Policy**: Each rendered page must contain exactly **one** `<h1>` tag located within the primary hero section.
- **Strict Hierarchy**: Heading levels must not skip ranks (e.g., `<h1>` followed by `<h2>`, never directly by `<h3>` or `<h4>`).
- **Semantic Structure**:
  - Main container: `<main id="main-content" role="main">`
  - Navigation bar: `<header role="banner"><nav role="navigation">`
  - Distinct sections: `<section aria-labelledby="section-id-heading">`
  - Footer: `<footer role="contentinfo">`
- **Descriptive Heading Text**: Headings must clearly state function and topic (e.g., `"Turn Calls into Opportunities with Autonomous Lead Qualification"` rather than vague marketing labels like `"Capabilities"`).

### 2.3 Schema.org Structured Data (JSON-LD) Master Templates

The landing page must inject valid, parseable JSON-LD in `index.html`:

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "SoftwareApplication",
      "@id": "https://voxly.ai/#software",
      "name": "Voxly AI",
      "url": "https://voxly.ai",
      "applicationCategory": "BusinessApplication",
      "operatingSystem": "Web",
      "description": "Enterprise autonomous AI voice agent platform operating over PSTN, SIP trunks, and WebRTC with sub-500ms latency.",
      "offers": {
        "@type": "AggregateOffer",
        "priceCurrency": "USD",
        "lowPrice": "49",
        "highPrice": "299",
        "offerCount": "3"
      }
    },
    {
      "@type": "Organization",
      "@id": "https://voxly.ai/#organization",
      "name": "Voxly AI Inc.",
      "url": "https://voxly.ai",
      "logo": "https://voxly.ai/favicon.svg",
      "contactPoint": {
        "@type": "ContactPoint",
        "telephone": "+1-415-555-0199",
        "contactType": "Customer Support",
        "availableLanguage": ["English", "Telugu", "Hindi", "Spanish"]
      }
    },
    {
      "@type": "FAQPage",
      "@id": "https://voxly.ai/#faq",
      "mainEntity": [
        {
          "@type": "Question",
          "name": "What is the average response latency of Voxly voice agents?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Voxly achieves an end-to-end round-trip latency of 380ms to 490ms by utilizing streaming STT, cached LLM inference, and streaming neural voice synthesis."
          }
        },
        {
          "@type": "Question",
          "name": "Can Voxly AI agents place and receive calls over regular phone lines?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Yes. Voxly provisions virtual local DIDs and toll-free numbers over Tier-1 PSTN carrier networks, supporting both inbound reception and outbound dialing campaigns."
          }
        }
      ]
    }
  ]
}
```

### 2.4 Crawling & Indexing Policy: Public vs. Authenticated Console

```
# public/robots.txt
User-agent: *
Allow: /
Allow: /privacy
Allow: /terms
Allow: /sitemap.xml

# Disallow authenticated application console & API endpoints
Disallow: /dashboard/
Disallow: /api/
Disallow: /auth/

Sitemap: https://voxly.ai/sitemap.xml
```

- **Authenticated Console Exclusion**: Every route under `/dashboard/*` must inject a `<meta name="robots" content="noindex, nofollow" />` directive to prevent private customer data, transcripts, and telemetry from ever being indexed by search crawlers.

### 2.5 Core Web Vitals (CWV) Performance Budget

| Core Web Vital | Industry Threshold | Voxly Target Budget | Optimization Mechanism |
|---|---|---|---|
| **LCP (Largest Contentful Paint)** | < 2.5s | **< 1.1s** | Async Three.js loading, pre-rendered Hero text, font-display swap |
| **INP (Interaction to Next Paint)** | < 200ms | **< 60ms** | Debounced handlers, micro-task scheduling, non-blocking audio |
| **CLS (Cumulative Layout Shift)** | < 0.1 | **0.00** | Explicit width/height on 3D canvas and avatars; fixed dimension hero card |

### 2.6 Unique ID Naming Convention for Testing & Deep Linking

Every interactive element and section across Voxly must adhere to a standardized ID pattern:
- Sections: `section-[name]` (e.g., `section-hero`, `section-pricing`, `section-faq`)
- Action Buttons: `btn-[action]-[target]` (e.g., `btn-cta-build-agent`, `btn-test-voice`, `btn-buy-number`)
- Inputs: `input-[module]-[field]` (e.g., `input-agent-name`, `input-carrier-search`, `input-newsletter-email`)
- Modals & Drawers: `modal-[name]` / `drawer-[name]` (e.g., `modal-auth`, `drawer-call-detail`)

---

## Part 3: Platform Architecture — Public Marketing Surface vs. Authenticated Console

Voxly maintains a clean separation of concerns between the **Public Marketing Surface** and the **Authenticated Voice Console**:

```
                              VOXLY AI ARCHITECTURE
                                        │
           ┌────────────────────────────┴────────────────────────────┐
           ▼                                                         ▼
    PUBLIC SURFACE                                         AUTHENTICATED CONSOLE
    Route: `/`                                             Route: `/dashboard/*`
    ──────────────────────────                             ──────────────────────────
    • Static & dynamic marketing landing page              • High-density enterprise workspace
    • 3D Mascot Interactive Hero (`Hero.jsx`)              • Persistent AppShell & Collapsible Sidebar
    • 15 Curated Product Showcase Sections                • Global Command Palette (`⌘K`)
    • Instant In-Browser Audio Demo (`TalkToAi`)           • Real-time Agent Studio Workbench
    • Transparent Tier Pricing & ROI Calculator            • Multi-Agent Fleet Management
    • Unauthenticated visitors / SEO indexing              • Number Buying & Carrier Assignment
                                                           • Inbound/Outbound Call Flows & Leads
```

- **Unauthenticated Route (`/`)**: Renders public marketing content. Clicking "Sign In" or "Build Your Agent" opens the unified authentication modal (`AuthModal.jsx`).
- **Authenticated Route (`/dashboard/*`)**: Protected by session token (`AuthContext.jsx`). If unauthenticated, immediately triggers the auth modal or redirects to `/login`.

---

## Part 4: Unified User Console Architecture — Module by Module

### 4.1 Global AppShell, Topbar & Command Palette (⌘K)

The authenticated workspace layout features a high-density, focus-first structure:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ [V] Voxly AI   [Acme Corp Workspace ▼]        Search anything... (⌘K)        [1,248m]  [User]│
├──────────────┬──────────────────────────────────────────────────────────────────────────────┤
│ OVERVIEW     │                                                                              │
│ • Overview   │                                                                              │
│              │                                                                              │
│ AI WORKFORCE │                                                                              │
│ • Employees  │                                                                              │
│ • Training   │                         PRIMARY VIEWPORT CONTENT                             │
│ • Knowledge  │                                                                              │
│              │                                                                              │
│ TELEPHONY    │                                                                              │
│ • Calls      │                                                                              │
│ • Campaigns  │                                                                              │
│ • Phone Nums │                                                                              │
│              │                                                                              │
│ INSIGHTS     │                                                                              │
│ • Leads      │                                                                              │
│ • Analytics  │                                                                              │
│              │                                                                              │
│ WORKSPACE    │                                                                              │
│ • Integrat.  │                                                                              │
│ • Billing    │                                                                              │
│ • Settings   │                                                                              │
├──────────────┤                                                                              │
│ 1,248 min    │                                                                              │
│ [+ Add Funds]│                                                                              │
│ Sarah Connor │                                                                              │
└──────────────┴──────────────────────────────────────────────────────────────────────────────┘
```

- **Sidebar (`w-64 bg-[#111019] border-r border-[#262438]`)**:
  - **Organization Switcher**: Dropdown supporting multi-tenant workspaces.
  - **Navigation Groups**:
    - `OVERVIEW`: Overview.
    - `AI WORKFORCE`: AI Employees, Training, Knowledge Base.
    - `COMMUNICATIONS`: Calls, Campaigns, Phone Numbers.
    - `INSIGHTS`: Leads, Analytics.
    - `WORKSPACE`: Integrations, Billing & Usage.
    - `ACCOUNT`: Settings, Profile.
  - **Footer Strip**: Live credit meter (`1,248 min remaining`), `[+ Add Funds]` action, and user profile badge.
- **Global Topbar (`h-14 bg-[#111019]/90 backdrop-blur-md border-b border-[#262438] px-6`)**:
  - Breadcrumbs: Active location (e.g., `AI Employees > Maya > Script Editor`).
  - Active Call Pulse: Visual pulsing green indicator when an outbound campaign or live call is in progress.
  - Command Palette Trigger (`⌘K` / `Ctrl+K`).
  - Quick action: `[+ Create AI Employee]`.
- **Command Palette (`⌘K`)**:
  - Instant fuzzy search across agents, phone numbers, lead records, call IDs, and settings.
  - Quick commands: `"Create AI Employee"`, `"Buy Phone Number"`, `"Launch Campaign"`, `"Top-up Balance"`.

---

### 4.2 Module 1: Unified Overview Dashboard (Single-Pane-of-Glass Management)

The central operational hub giving the user full visibility over their entire AI workforce:

- **Welcome Bar**: `"Good morning, [Name]"` + `"Here's what your AI workforce accomplished today."`
- **KPI Metrics Ribbon (4 Cards)**:
  1. `Total Calls`: `3,842` (`+14.2%` vs last week)
  2. `Call Minutes`: `14,290 min` (`+8.6%` vs last week)
  3. `Qualified Leads`: `849` (`+21.4%` conversion lift)
  4. `Active AI Fleet`: `6 Agents` (4 Active, 2 In Training)
- **Call Activity Canvas**: Hourly interactive bar chart showing Inbound vs. Outbound distribution with hover tooltips for answer rate, duration, and cost.
- **Active AI Fleet Ribbon**: Horizontal cards displaying each agent's current status (`● Active`, `● In Call`, `● Idle`), today's minutes, and quick button `[ Talk to Agent ]`.
- **Recent Calls Feed**: Live updating table showing Caller, Direction, Assigned Agent, Duration, AI Sentiment tag (`Positive`, `Neutral`, `Negative`), and one-click `[ Inspect Transcript ]`.
- **Lead Stream Ticker**: Ticker of newly extracted qualified leads with BANT scores and one-click `[ View Lead ]`.

---

### 4.3 Module 2: AI Employees Fleet Management (Create N Agents)

Allows users to create, manage, and monitor an unlimited fleet of specialized voice agents:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ AI EMPLOYEES (6)                                             [Search agents...]  [+ New Agent]│
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────┐ ┌─────────────────────────┐ ┌─────────────────────────┐        │
│ │ [Avatar] Maya           │ │ [Avatar] David          │ │ [Avatar] Elena          │        │
│ │ Role: Dental Reception  │ │ Role: Outbound SDR      │ │ Role: Tier-1 Support    │        │
│ │ Status: ● Active        │ │ Status: ● Active        │ │ Status: ● Paused        │        │
│ │ Number: +1 415-555-0199 │ │ Number: +1 212-555-0144 │ │ Number: Unassigned      │        │
│ │ Calls: 1,420 (94% Succ) │ │ Calls: 890 (88% Succ)   │ │ Calls: 310 (91% Succ)   │        │
│ ├─────────────────────────┤ ├─────────────────────────┤ ├─────────────────────────┤        │
│ │ [Talk] [Script] [Edit]  │ │ [Talk] [Script] [Edit]  │ │ [Talk] [Script] [Edit]  │        │
│ └─────────────────────────┘ └─────────────────────────┘ └─────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Filter Controls**: `All (6)`, `Active (4)`, `Draft (1)`, `Paused (1)`.
- **Agent Card Details**:
  - Mascot 3D Avatar, Agent Name, Role / Department badge.
  - Assigned Phone Number (with quick link to reassign or buy number).
  - Voice Provider tag (e.g. `Cartesia — British Warm`).
  - Total Calls handled, talk time minutes, and task success rate.
- **Tactile Quick Actions**:
  - `[ Talk ]`: Instant WebRTC browser test session with living mascot.
  - `[ Script ]`: Jump directly into the script and prompt editor.
  - `[ Duplicate ]`: Clones prompt, voice calibration, and tools into a new draft agent.
  - `[ Pause / Resume ]`: Toggles SIP call handling availability on/off.
  - `[ Delete ]`: Soft-deletes agent with confirmation dialog.

---

### 4.4 Module 3: Agent Creation Wizard & Script Flow Studio

#### Guided 6-Step Creation Wizard:
1. **Step 1: Identity & Naming**:
   - Agent Name (e.g. `Maya`, `Alex`, `Jordan`).
   - Role / Department (Inbound Receptionist, Outbound SDR, Customer Support, Debt Collection).
   - Brief Description & Primary Objective.
2. **Step 2: Script & Conversation Flow**:
   - Inbound Greeting phrase (*"Thank you for calling Summit Dental. This is Maya, how may I assist you today?"*).
   - Core Conversation Script / Persona Instructions.
   - Dynamic Script Variables (`{{caller_name}}`, `{{account_id}}`, `{{service_type}}`).
   - Objection Handling Rules (e.g., *"If customer asks about pricing, state that consultations are free..."*).
   - Boundary & Negative Constraints (e.g., *"Never promise a refund without supervisor approval"*).
3. **Step 3: Voice Calibration**:
   - Voice Engine Selection (Cartesia Sonic, ElevenLabs Turbo, Deepgram Aura, PlayHT).
   - Language & Accent (US English, Indian English, Telugu, Hindi, Hinglish, Spanish).
   - Speaking Speed (`0.8x – 1.3x`), Pitch Modulation, and Voice Stability.
   - Live Audio Sample Preview player with real-time waveform.
4. **Step 4: Knowledge Ingestion**:
   - Upload business FAQs, price sheets, service catalogs (PDF, TXT, DOCX, or Website URL crawler).
   - Real-time question testing sandbox (*"What are your hours?"* $\to$ preview retrieved knowledge).
5. **Step 5: Phone Number Connection**:
   - Select from existing owned numbers or trigger the instant Number Purchase modal.
6. **Step 6: Review & Deploy**:
   - Full summary checklist and one-click `[ Activate Agent ]`.

#### Dedicated Script Flow Studio (Workbench):
- **Dual-Pane Script Editor**:
  - Left Pane: Monaco-style prompt editor with markdown syntax highlighting, token count meter, and variable chips.
  - Right Pane: Conversational preview simulator with test chat and audio synthesis.
- **Version History & Rollback**: Save named revisions (`v1.2 - Added insurance objection handling`) with one-click restore.

---

### 4.5 Module 4: Virtual Number Buying & Direct Agent Assignment

Empowers users to search, purchase, and route phone numbers in seconds:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ BUY VIRTUAL PHONE NUMBER                                                                 [X]│
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Country: [United States (US) ▼]   Type: [Local DID (Area Code) ▼]   Area Code: [415]        │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ AVAILABLE NUMBERS IN SAN FRANCISCO, CA (415)                                                │
│ • +1 (415) 555-0199   • Voice + SMS   • $2.50/month   [Buy & Assign to Maya]                │
│ • +1 (415) 555-0142   • Voice + SMS   • $2.50/month   [Buy & Assign to David]               │
│ • +1 (415) 555-0188   • Voice + SMS   • $2.50/month   [Buy to Pool]                         │
│ • +1 (800) 555-0120   • Toll-Free     • $4.50/month   [Buy to Pool]                         │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Global Inventory Search**:
  - Filter by Country (US, Canada, UK, Australia, India, etc.).
  - Filter by Type (`Local DID`, `Toll-Free 800`, `Mobile`).
  - Search by Area Code, City, or Vanity digits.
- **One-Click Agent Binding**:
  - During purchase or from the Number Inventory list, select: `Assign to: [Maya - Receptionist]`.
  - The backend routing table updates immediately (<200ms).
- **Inbound Call Configuration per Number**:
  - `Assigned Agent`: Which AI answers.
  - `Business Hours Schedule`: Active hours (e.g., 08:00–18:00 Mon–Fri).
  - `After-Hours Action`: Route to after-hours agent, take voicemail, or forward to human phone.
  - `Call Recording`: Enabled / Disabled.
- **Outbound Caller ID Configuration**:
  - Select default outbound number for each agent.
  - Option to enable **Dynamic Local Presence** (automatically dials from a number matching the recipient's area code to boost pickup rates from 12% to 42%+).

---

### 4.6 Module 5: Inbound & Outbound Call Operations

Provides complete operational control over all telephone interactions:

#### Inbound Call Flow:
- When a customer dials the virtual number:
  1. Instant answer with assigned agent greeting.
  2. Agent follows the configured conversation script and knowledge base.
  3. Real-time audio recording and transcription.
  4. **Warm Transfer Rule**: If customer requests a human or sentiment drops below threshold, agent places customer on comfort hold, dials human specialist, delivers a private 10-second whisper briefing, and bridges both into a conference call.

#### Outbound Call Flow:
- **Single Test Dial**: Enter any phone number in the console to test the agent over real PSTN lines.
- **Answering Machine Detection (AMD)**:
  - Detects in <1200ms whether a human or voicemail machine answered.
  - If human: Agent begins conversation immediately.
  - If voicemail: Automatically drops a personalized voicemail after the beep or hangs up immediately to conserve credits.

---

### 4.7 Module 6: Call Logs & Diarized Audio Waveform Drawer

Every phone call handled by any AI employee is recorded, transcribed, and analyzed:

- **Calls Table**:
  - Columns: Caller Phone, Direction (`Inbound` / `Outbound`), Assigned AI Employee, Duration (`font-mono`), Outcome (`Qualified`, `Transferred`, `Voicemail`, `Unanswered`), Sentiment (`Positive`, `Neutral`, `Negative`), Timestamp.
  - Filters: Date Range, Agent, Direction, Duration, Outcome, Sentiment score.
  - Search: Full-text transcript keyword search.
- **Call Detail Drawer (Opens on Row Click)**:
  - **Dual-Track Audio Waveform Player**: Interactive waveform with separate color channels for Caller and AI. Clicking any point on the waveform jumps to that exact audio timestamp.
  - **Diarized Transcript**: Clean chat-bubble transcript with speaker tags, timestamps, and confidence scores.
  - **AI Structured Insights**:
    - `Executive Summary`: 2-sentence bulleted summary.
    - `Detected Intent`: (e.g., `Appointment Reschedule`, `Pricing Inquiry`).
    - `Sentiment Score`: `-1.0` to `+1.0` with inflection points.
    - `Extracted Lead Data`: Contact details, dates, and budget noted during the call.
    - `CRM Sync Status`: Confirmed sync to Salesforce/HubSpot.

---

### 4.8 Module 7: Autonomous AI Lead Engine (Call Extraction & Pipeline)

The AI automatically transforms conversations into structured, actionable business leads:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ LEADS PIPELINE (849 Leads Captured)                              [Filter] [Export CSV] [+ New]│
├───────────────┬───────────────┬───────────────┬───────────────┬─────────────────────────────┤
│ NEW (142)     │ CONTACTED(280)│ QUALIFIED(215)│ BOOKED (164)  │ UNQUALIFIED (48)            │
├───────────────┼───────────────┼───────────────┼───────────────┼─────────────────────────────┤
│ Mark Henderson│ Sarah Jenkins │ Apex Logistics│ David Miller  │ Generic Inquiry             │
│ Dental Implant│ Auto Loan     │ 50-Seat Fleet │ Consultation  │ Out of Service Area         │
│ BANT: 92/100  │ BANT: 78/100  │ BANT: 96/100  │ BANT: 88/100  │ BANT: 24/100                │
│ Maya (4m ago) │ Alex (1h ago) │ David (2h ago)│ Maya (4h ago) │ Jordan (Yesterday)          │
│ [Trigger Call]│ [Trigger Call]│ [Trigger Call]│ [View Details]│ [Archive]                   │
└───────────────┴───────────────┴───────────────┴───────────────┴─────────────────────────────┘
```

- **Automated AI Extraction Engine**:
  - During every call, the AI automatically extracts:
    - Contact Name, Phone Number, Email.
    - Specific Needs & Product Interest.
    - **BANT Score (0–100)**: Budget confirmed, Authority verified, Need identified, Timeline established.
    - Next Follow-up Action.
- **Kanban Pipeline & Data Table**:
  - Drag-and-drop leads between stages (`New`, `Contacted`, `Qualified`, `Meeting Booked`, `Lost`).
  - Switch to full Data Table view with sortable columns and batch CSV export.
- **Lead Detail Modal**:
  - Full history of all AI calls with this contact.
  - Transcript preview and audio recording player.
  - One-click `[ Trigger AI Call ]` to have an agent follow up immediately.
  - Bi-directional CRM sync (HubSpot, Salesforce, GoHighLevel).

---

### 4.9 Module 8: Bulk Campaigns Dialing Engine

Execute high-scale outbound calling campaigns powered by any AI agent:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ CAMPAIGN: Q4 Dental Implant Outreach   ● RUNNING               [Pause Fleet] [Campaign Settings]│
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌─────────────────┐ │
│ │ Total Contacts│ │ Answer Rate   │ │ Connected Calls│ │ Leads Created │ │ Cost Incurred   │ │
│ │ 2,500         │ │ 44.8%         │ │ 1,120 calls   │ │ 284 Qualified │ │ $142.80         │ │
│ └───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘ └─────────────────┘ │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ DIALING CADENCE & PROGRESS                                                                  │
│ Progress: [████████████████████░░░░░░░░░░] 52% Completed (1,300/2,500)                      │
│ Active Concurrent Lines: 25 calls in progress   • Calling Hours: 09:00 - 18:00 Recipient Time│
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

#### 5-Step Campaign Creation Wizard:
1. **Campaign Name & Objective**: Define campaign name and select the assigned AI Employee.
2. **Upload Contact List**: Upload CSV with phone numbers and custom data columns.
3. **Column Variable Mapping**: Map CSV headers (`first_name`, `last_visit_date`) to dynamic script variables (`{{first_name}}`, `{{last_visit_date}}`).
4. **Phone Pool & Compliance Settings**:
   - Select Dedicated Virtual DID or enable Dynamic Local Presence.
   - Set Calling Hours (e.g. 09:00–18:00 recipient local time, ensuring TCPA compliance).
   - Set Concurrency Limit (e.g., 5 to 50 simultaneous active lines).
   - Set Retry Rules: Retries on busy/voicemail (e.g., max 3 attempts spaced 3 hours apart).
5. **Review, Cost Projection & Launch**:
   - Preview projected minute consumption and estimated total cost.
   - Click `[ Launch Campaign ]` with real-time progress monitor.

---

### 4.10 Module 9: Wallet, Per-Second Billing & Usage

Full transparency into credit consumption, per-second metering, and payment automation:

- **Credit Balance Banner**:
  - Live remaining balance: `1,248 minutes` (`$118.56 USD value`).
  - Quick Top-Up buttons: `[+$50]`, `[+$100]`, `[+$250]`, `[Custom]`.
- **Auto-Recharge Controller**:
  - Enable / Disable Auto-Recharge toggle.
  - Rule: *"When balance falls below \$20.00, automatically charge \$100.00 to Visa ending in 4242."*
  - Emergency overdraft buffer ($15.00) ensures calls are never cut off mid-sentence.
- **Per-Second Itemized Usage Ledger**:
  - Filterable table showing Call ID, Timestamp, AI Employee, Duration (exact seconds), Destination Phone, and Itemized Cost (Carrier + STT + LLM + TTS = Total).
  - Download monthly tax invoices and CSV usage data.

---

### 4.11 Module 10: Integrations & Webhook Hub

- **Native CRM Connectors**: Salesforce, HubSpot, GoHighLevel, Pipedrive, Zoho.
- **Calendar Booking**: Google Calendar, Microsoft Outlook, Cal.com, Calendly.
- **Communication & Alerts**: Slack, Discord, Microsoft Teams.
- **Custom Webhook Dispatcher**: Configure endpoint URLs to receive live events (`call.completed`, `lead.qualified`, `voicemail.left`).

---

### 4.12 Module 11: Settings, Team Roles & Security

- **Organization & RBAC**: Invite team members with specific roles (`Owner`, `Admin`, `Prompt Engineer`, `Call Center Supervisor`, `Auditor`).
- **Developer API Keys**: Generate scoped keys (`vox_live_...`, `vox_test_...`) to trigger calls via API.
- **Security & PII Protection**:
  - Automatic PII Masking: Redact credit card numbers, SSNs, and sensitive numbers from transcripts.
  - Recording retention policy: Auto-delete audio recordings after 30, 60, or 90 days.

---

### 4.13 Module 12: Realtime "Talk to AI" Interactive Testing Console

The crown jewel interactive testing surface in the application:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ TALK TO AI — REALTIME INTERACTION CONSOLE                                      [End Call (Esc)]│
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                             │
│                                       [ 3D MASCOT ]                                         │
│                                (Living Character Reaction)                                  │
│                                                                                             │
│                            ● SPEAKING (Latency: 382 ms)                                     │
│                     ▂▃▅▇█▓▒░░▒▓█▇▅▃▂ ▂▃▅▇█▓▒░░▒▓█▇▅▃▂                                      │
│                                (Active Audio Waveform)                                      │
│                                                                                             │
│   "I can certainly help you reschedule your appointment for this Thursday at 2:00 PM."     │
│                                                                                             │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ STREAMING CONVERSATION TRANSCRIPT                       │ DIAGNOSTICS & TELEMETRY           │
│ [10:14:02] User: Can I change my appointment time?      │ • STT Latency:     92 ms          │
│ [10:14:03] Maya: Absolutely! What day works best?       │ • LLM TTFT:        174 ms         │
│ [10:14:05] User: Thursday afternoon please.             │ • TTS Latency:     76 ms          │
│ [10:14:06] Maya: Thursday at 2:00 PM is open.           │ • Total RTT:       342 ms         │
│                                                         │ • Codec:           Opus 24kHz     │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ [ 🎙️ Mute Mic ]                       [ ✋ Force Interrupt ]               [ 🔄 Restart Session ]│
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Mascot Reaction States**:
  - `Connecting`: Subtle pulsing base glow.
  - `Listening`: Eyes track cursor; microphone meter responds to user amplitude.
  - `Thinking`: Subtle posture shift and processing pulse.
  - `Speaking`: Articulated speech synchronized to synthesized audio frequencies.
  - `Interrupted`: Instantly stops speech pose and resets when user interrupts.
- **Controls**: Mute Microphone, Force Interrupt, Restart Session, End Call.

---

## Part 5: Emil Kowalski UI Design System Tokens & Tactile Primitives

The authenticated console implements an obsidian, high-contrast dark theme engineered for focus and enterprise utility:

```
/* ─── COLOR PALETTE TOKENS ─── */
--bg-root:       #0B0A10;  /* Deepest obsidian background */
--bg-surface:    #111019;  /* Secondary container / sidebar / topbar */
--bg-card:       #181724;  /* Interactive card / panel surface */
--bg-card-hover: #201F30;  /* Subtle card hover state */
--border-subtle: #262438;  /* 1px structural hairline border */
--border-active: #3D3A55;  /* Active / focused input border */

/* ─── TYPOGRAPHY TOKENS ─── */
--text-primary:   #F7F7FB; /* Crisp high-contrast display & body text */
--text-secondary: #A19EAD; /* Readable secondary metadata (WCAG AA 4.8:1) */
--text-muted:     #6E6B7B; /* Tertiary timestamps & inactive labels */

/* ─── SEMANTIC ACCENT TOKENS ─── */
--accent-brand:   #6344E7; /* Restrained brand violet (primary actions) */
--accent-hover:   #7557F8; /* Interactive hover */
--accent-active:  #5334D6; /* Active depression */
--status-success: #22C55E; /* Call connected / active / verified */
--status-warning: #F59E0B; /* Balance threshold / degraded state */
--status-danger:  #EF4444; /* Call failed / error / cancelled */
--status-info:    #3B82F6; /* Info / inbound call */
```

- **Craft Principles**:
  - **Zero Decorative Glassmorphism**: Cards have solid `#181724` surfaces with clean 1px hairline `#262438` borders.
  - **Tactile Feedback**: Every button, tab, and card click has an intentional active depression: `active:scale-[0.98] transition-transform duration-100`.
  - **Monospace Telemetry**: Call durations, phone numbers, latencies, and dollar amounts use a clean monospace font (`font-mono tracking-tight`).

---

## Part 6: Frontend Component Hierarchy & Implementation Roadmap

```
d:\Antigravity\src\
├── App.jsx                        # Master router (Public Landing Page vs. Authenticated Console)
├── components\                    # Public Landing Page Components (15 Sections, Hero UI benchmark)
│   ├── Hero.jsx                   # 3D Mascot & Conversational North Star
│   ├── AiEmployeeSection.jsx      # Workbench Showcase
│   ├── TalkToAiSection.jsx        # Live In-Browser WebRTC Demo
│   ├── PhoneChannelsSection.jsx   # Inbound, Outbound, Campaigns Overview
│   ├── LeadEngineSection.jsx      # Pipeline & CRM Sync
│   ├── CampaignScaleSection.jsx   # Outbound Dialing Scale
│   ├── TrainingSection.jsx        # Vector Ingestion & RAG
│   ├── AiTeamSection.jsx          # Multi-Agent Profiles
│   ├── ConversationHistorySection.jsx # Call Transcripts
│   ├── AnalyticsSection.jsx       # Performance Charts
│   ├── IndustriesSection.jsx      # Vertical Use-Cases
│   ├── HowItWorksSection.jsx      # Step-by-Step Architecture & Billing
│   ├── PricingSection.jsx         # Tier Pricing
│   ├── FAQSection.jsx             # Technical FAQ
│   ├── FinalCTA.jsx               # Primary Conversion Anchor
│   ├── Navbar.jsx                 # Dynamic Navigation (Sign In / Open Dashboard)
│   ├── Footer.jsx                 # Legal & Links
│   ├── AuthModal.jsx              # Multi-Method Auth Modal (Google, GitHub, Email, Passkey)
│   └── LegalModals.jsx            # Privacy Policy & Terms of Service
│
├── console\                       # Authenticated Enterprise Console (`/dashboard/*`)
│   ├── AppShell.jsx               # Layout Container (Sidebar + Topbar + Command Palette)
│   ├── Sidebar.jsx                # Persistent Obsidian Navigation + Live Credit Meter
│   ├── Topbar.jsx                 # Breadcrumbs, Active Dial Pulse, Workspace Switcher
│   ├── CommandPalette.jsx         # Global ⌘K Fuzzy Action Search
│   ├── modules\                   # Dedicated Console Modules
│   │   ├── OverviewModule.jsx     # KPIs, Volume Canvas, Fleet Grid, Live Feed
│   │   ├── EmployeesModule.jsx    # Fleet Directory (Create N agents, name, role, status)
│   │   ├── AgentStudio.jsx        # Script Flow Studio, Prompt Editor, Voice Tuning
│   │   ├── CreateAgentWizard.jsx  # 6-Step Guided Agent Creation Stepper
│   │   ├── PhoneNumbersModule.jsx # Number Buying Modal, Carrier Search, Agent Binding
│   │   ├── CallsModule.jsx        # Inbound/Outbound Calls Table & Audio Player Drawer
│   │   ├── LeadsModule.jsx        # Autonomous Lead Extraction Kanban & Detail Modal
│   │   ├── CampaignsModule.jsx    # 5-Step Bulk Outbound Wizard & Concurrency Monitor
│   │   ├── BillingModule.jsx      # Credit Meter, Auto-Recharge Slider, Cost Ledger
│   │   ├── IntegrationsModule.jsx # CRM, Calendar & Webhook Connectors
│   │   ├── SettingsModule.jsx     # Team RBAC, API Keys, PII Masking, Security
│   │   └── TalkToAiConsole.jsx    # Real-Time WebRTC Testing Console with 3D Reactions
│   └── ui\                        # High-Craft Tactile Atomic Primitives
│       ├── TactileButton.jsx      # Emil Kowalski active-depression buttons
│       ├── SolidCard.jsx          # Non-glassmorphism solid card surfaces
│       ├── MetricCard.jsx         # Monospace KPI containers
│       ├── WaveformVisualizer.jsx # Multi-band canvas frequency visualizer
│       └── StatusPill.jsx         # Restrained monochrome & semantic indicators
│
├── services\                      # Client & API Services Layer
│   ├── authService.js             # Authentication & session token management
│   ├── voiceAgent.js              # Real-time WebRTC & Speech Synthesis client
│   ├── telephonyApi.js            # Carrier DID provisioning & SIP trunking API client
│   ├── billingService.js          # Stripe Checkout & auto-recharge API client
│   └── analytics.js               # Privacy-friendly event dispatcher
│
└── styles\
    └── globals.css                # Emil Kowalski design tokens & animation utilities
```

---

## Part 7: Pre-Launch Verification & Quality Assurance Checklist

- [x] **Hero UI Anchor Preserved**: `Hero.jsx` remains the design benchmark and conversation soul of the platform.
- [x] **Unnecessary Backend Plumbing Removed**: Low-level FreeSWITCH/SBC internals excised in favor of a clean User Console management architecture.
- [x] **Multi-Agent Fleet Creation**: Create $N$ agents, naming, role tagging, prompt/script editing, and duplicate workflows specified.
- [x] **Virtual Number Buying & Binding**: Real-time carrier inventory search, instant purchase, and direct agent connection documented.
- [x] **Inbound & Outbound Call Operations**: Automatic answering, script following, warm transfers, and AMD voicemail drops detailed.
- [x] **AI Lead Extraction Engine**: Automated parsing of caller info, BANT qualification scores, Kanban pipeline, and CRM sync specified.
- [x] **Bulk Outbound Campaigns**: CSV upload, variable mapping, concurrency controls, retry rules, and live telemetry monitor defined.
- [x] **Unified Overview Dashboard**: Single-pane-of-glass workspace layout providing total operational control.
- [x] **Technical SEO Enforced**: Single `<h1>` hierarchy, meta tags, Open Graph, Core Web Vitals targets, `robots.txt` exclusion of `/dashboard/*`, and valid Schema.org JSON-LD templates defined.
- [x] **Emil Kowalski Craft Enforced**: 19 anti-patterns eliminated, obsidian dark tokens codified, and tactile micro-interactions specified.