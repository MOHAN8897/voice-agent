# 13 — Copy, content, and SEO

Tone: **calm, precise, Telugu-first, operational**. Three words: confident, agentic, operational.

Do not sound like a chatbot vendor (“nurture leads with AI magic”). Sound like a **phone control plane**.

## Brand names

- Product: **Vāṇi**
- Business UI: **Business Console**
- Staff UI: **Developer Portal**
- Live tool: **Test Studio**
- Prompt: **Business Brain** vs **Platform Brain** (never conflate)

## Landing

| Slot | Current / recommended |
|------|------------------------|
| Eyebrow | Built for Telugu-speaking markets |
| H1 | Voice agents that **remember** every caller |
| Sub | Configure how your agent speaks, test live in the browser, review every call with memory and disposition |
| Primary CTA | Sign in / Start in Test Studio |
| Secondary | See how it works |
| Mono | Browser test in minutes · PSTN ready · Memory on every call |

How-it-works titles stay: Configure · Test · Review.

## Pricing

Headline: Pay for what your agents use.  
Sub: STT, LLM, and TTS billed per tier. Telephony via Telnyx.

## Auth

Business: Configure agents, test voice, deploy with confidence.  
Dev: Platform configuration for authorized staff only.

## Console empty states (write once, reuse)

- Agents: “No agents yet. Create one to compile a Business Brain and run Test Studio.”
- Calls: “No calls yet — start a voice session to create your first call archive.”
- Analytics: “Analytics appear after production or test calls finalize.”
- Benchmarks: “Benchmark runs are off until scenarios are configured.”
- Billing: “Add a payment method to enable PSTN and outbound campaigns.”
- Campaigns: “No campaigns. Outbound uses the same agent you already tested.”

## Voice / sales script (product, not website)

Website must not contradict live-agent rules already in `server/prompts/`:

- Greet **once**: name + company + purpose
- Later “hello” = availability, not a new intro
- Don’t repeat the pitch
- After enough info + next step: professional close + `end_call`

Marketing can say “the agent greets as your business and does not restart the pitch.”

## SEO metadata patterns

Title template: `{Page} · Vāṇi`  
Home title already: “Voice agents for Telugu-speaking businesses”

JSON-LD: SoftwareApplication is fine; update `offers.price` when billing exists.

Sitemap: public only. No `/app`, `/dev`.

## Telugu on the marketing site

Use real Telugu in `AgentPreview` only. Don’t machine-translate the whole marketing site until a native pass exists. English UI + Telugu samples is the current pattern.

## Words to avoid

AI-powered, cutting-edge, disrupt, chatbot, GPT as a product name, “we already sent the email”, Plivo (unless a tenant still uses it — this repo’s PSTN path is Telnyx).
