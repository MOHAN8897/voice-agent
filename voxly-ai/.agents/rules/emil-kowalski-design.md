# Emil Kowalski Design & Craft Guidelines for Voxly AI

This workspace rule enforces the high-craft design standards, visual hierarchy, and anti-pattern elimination inspired by Emil Kowalski and anchored in the **Hero UI** of Voxly AI.

## 1. Core Architectural Benchmark: Hero UI as Design North Star
The **Hero UI** (`src/components/Hero.jsx`) is the design anchor and aesthetic benchmark for the entire application. Every component must look, feel, and behave as though created by the exact same designer:
- **Solid High-Contrast Typography**: Primary headlines in deep neutral navy (`#0F0E17`). No text clipping gradients (`-webkit-background-clip: text`).
- **Tactile Button Interactions**: Purposeful active depression (`active:scale-[0.98]`), distinct keyboard focus rings (`focus-visible:ring-2`), and solid high-contrast fills (`#0F0E17` or `#6344E7`).
- **Surface Hierarchy**: Clean solid surfaces (`#FFFFFF` on `#FAF9FD`, or `#111019` for dark modules) with 1px neutral hairline borders (`border-[#E4E2EB]` or `border-black/5`). No generic blurry glassmorphism.
- **Living Intelligence**: Retain the 3D mascot, real-time voice synthesis, audio reactivity, and contextual interaction without degrading into static brochure boxes.

---

## 2. The 19 Anti-Patterns of Generic AI SaaS (Strictly Prohibited)

1. **No Purple-to-Blue Gradients**: Never use `bg-gradient-to-r from-[#7657E8] to-[#9B7BF7]` on buttons, text, or card borders. Use solid neutrals with restrained `#6344E7` accents.
2. **No Gradient-Colored Hero Text**: Never apply `.gradient-text-lavender` or text-clip gradients on `<h1>` or `<h2>`. Use solid `#0F0E17` (light) or `#F7F7FB` (dark).
3. **No Emojis in Headings/Badges**: Never use decorative emojis (`🤖`, `📞`, `⚡`, `👩‍💼`) in headers, navigation, or status badges. Use monochrome SVG icons or pure typographic weight.
4. **No Default Font Stacks Without Hierarchy**: Use Plus Jakarta Sans for crisp display typography, balanced with clean body geometry and monospace accents for numeric telemetry. Never load unused handwriting fonts like `Caveat`.
5. **No Colored-Border Cards**: Never use `border-[#7657E8]/20` or colored card outlines. Use neutral hairline borders (`#E4E2EB`) and whitespace for elevation.
6. **No Generic Glassmorphism**: Never use `backdrop-blur-xl bg-white/10` for content cards. Content cards must be solid, opaque surfaces (`#FFFFFF` or `#111019`). Reserve blur strictly for sticky navigation headers.
7. **No Low-Contrast Text**: Secondary text must strictly meet WCAG AA 4.5:1 minimum contrast. Light backgrounds must use `#524E5E` or darker; dark backgrounds must use `#D1CFDB` or `#A19EAD`.
8. **No Repetitive Identical Card Grids**: Avoid monotonous 3-card or 4-card icon boxes. Employ asymmetric editorial layouts: split feature columns, data tables, and interactive workbench views.
9. **No Unnecessary Eyebrow Badges**: Never place decorative pill badges (`Sparkles`, `Bot`) above headlines unless they convey vital status information. Let bold typography lead the hierarchy.
10. **No Gratuitous Icon Boxes**: Icons should only exist where they directly aid navigation or clarify functionality (e.g. Play, Mic, Check). Do not place decorative Lucide icons in colored rounded rectangles above text.
11. **No Shallow/Default Pill Styling**: Avoid generic `rounded-full` pills for standard cards. Use disciplined border radiuses (`rounded-xl` / `rounded-2xl`) and bespoke micro-shadows.
12. **No Generic Fade-In Animations**: Strip out `animate-in fade-in zoom-in-95` on static blocks. Retain animations only for functional interactions (state changes, audio waveforms, 3D character movements).
13. **No Blurred Background Blobs**: Remove ambient decorative blur circles (`blur-3xl`, `blur-[140px]`). Ground pages in clean negative space.
14. **No Fade/Opacity-Only Button Hovers**: Buttons must provide tactile feedback with subtle active scaling (`active:scale-[0.98]`) and micro-border illumination.
15. **Strict 8pt Spatial Rhythm**: Enforce consistent section padding (`py-20` to `py-28`), standard container max-width (`max-w-6xl` / `max-w-7xl`), and structured spacing multiples of 8px.
16. **No Excessive Em Dashes in Copy**: Never use "—" as an empty conversational pause. Use crisp, professional sentences and bulleted technical specifications.
17. **No Generic AI Buzzwords**: Replace marketing fluff ("Supercharge workflows", "Autonomous magic") with concrete operational terminology ("Sub-500ms call latency", "BANT qualification", "Direct SIP trunking").
18. **No Forced Serif-Italic Accents**: Maintain clean, upright, legible typography throughout.
19. **No Arbitrary Font Combinations**: Maintain a unified typographic system without loading extraneous fonts.

---

## 3. Approved Design Tokens

| Token | Hex Value | Usage |
|---|---|---|
| Background Primary | `#FAF9FD` | Main page background |
| Surface Light | `#FFFFFF` | Solid white cards and panels |
| Surface Dark | `#111019` | High-contrast dark modules (Studio, Terminal) |
| Text Primary | `#0F0E17` | Headlines, primary text, high-contrast buttons |
| Text Secondary | `#524E5E` | Subtitles, body copy (WCAG AA 4.5:1 compliant) |
| Text Dark Panel | `#D1CFDB` | Secondary text on dark modules |
| Hairline Border | `#E4E2EB` | 1px clean card and divider borders |
| Hairline Dark | `rgba(255,255,255,0.08)` | 1px border on dark panels |
| Brand Accent | `#6344E7` | Restrained violet accent for key actions and active tabs |
| Success Green | `#10B981` | Operational telemetry indicators |

---

## 4. Conversion Hierarchy
- **Primary CTA**: `[ Build Your Agent ]` (Direct route to workspace onboarding and pricing).
- **Secondary CTA**: `[ Talk to AI ]` (Instant launch of live voice conversation & speech synthesis).
- Single, consistent terminology across all sections.
