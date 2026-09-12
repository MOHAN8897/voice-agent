# 03 — What a voice-agentic selling website must have

This product is a **control plane that sells itself**: a business buys the ability to run a phone/browser voice agent that qualifies, answers, and hands off leads. The website must sell **that workflow**, not a generic chatbot.

Product truth: [`prd/01-master-prd.md`](../prd/01-master-prd.md) §1–3, [`prd/17-product-decisions.md`](../prd/17-product-decisions.md).

## The story the site must tell

```text
Configure how the agent sells
        → Test it live (browser, then PSTN)
        → Every call leaves memory + disposition
        → Promote a version to production
        → Run outbound campaigns (PRD 18)
```

If a page cannot point to one of those beats, it does not belong on the marketing site.

## Surfaces required to sell and deliver

| Layer | Must exist | Why a buyer cares |
|-------------------|-------------------|
| Landing | Hero, how-it-works, proof of live voice, FAQ, CTA to try/console | First 10 seconds |
| Pricing | Usage / business / enterprise | Objection: cost |
| Auth | Sign-in, session, tenant | Trust |
| Onboarding | Create agent → brain sections → test | Time-to-value |
| Test Studio | Mic, transcript, barge-in, latency | “Does it sound real?” |
| Calls | List + detail + audio + memory | “Will I know what happened?” |
| Analytics | Volume, disposition, latency | “Is it converting?” |
| Channels | Browser + PSTN number | “Can it call India?” |
| Campaigns | Outbound lists, windows, DNC | Sales motion (PRD 18; UI **gap**) |
| Billing | Plan, GST invoice, usage | SaaS close (UI **gap**) |
| Settings | Members, retention, env | Admin |
| Dev portal | Stack, platform brain, promote | We operate the platform |

## Voice-agentic UI patterns (not chatbot patterns)

| Do | Don't |
|----|--------|
| Live **call state**: Idle → Connecting → Listening → Thinking → Speaking → Ended | Typing-indicator chat |
| User / agent **transcript bubbles** with STT/TTS latency | Endless chat thread with avatars |
| **Interrupted** turns + barge flash | Pretend the agent never talks over the user |
| **Memory projection** inspector | “Chat history” as source of truth |
| **Disposition** badges (`interested`, `callback_required`, …) | Star ratings as the only outcome |
| Tier chips LOW / MEDIUM / PREMIUM | Model-name soup on marketing |
| “Opening already spoken” / no re-greet | Script replay of the greeting every turn |

These match Test Studio and PSTN behavior already in `server/services/pstn_voice_core.py` and `web/components/test-studio/`.

## Selling (GTM) pages vs product pages

**GTM (public, SEO):** `/`, `/pricing`, `/docs`, `/legal/*` (gap), use-case pages (optional gap).

**Product (auth):** `/app/*`.

**Platform (staff):** `/dev/*` — never a marketing CTA.

## Industry use cases (copy, not separate products)

From current home FAQ: real estate, admissions, healthcare, dealerships, D2C — **generic platform**, not real-estate-only (`prd/17` §1). Landing may show one Telugu sales example; Business Brain stays eight sections for any brief.

## Claims that are allowed vs forbidden

**Allowed (implemented or PRD-committed):**

- Telugu + English code-mix live path
- Structured Business Brain (8 sections)
- Browser Test Studio
- Call archive, transcript, memory, disposition
- PSTN (Telnyx in code)
- Dev → staging → production promotion
- Outbound campaigns (PRD 18 — product, even if UI unfinished)

**Forbidden until built and approved:**

- RAG / knowledge base (`prd/17` non-goal)
- CRM sync (`prd/17` future)
- Speech-to-speech replacing the cascade (`prd/01` §4)
- “We sent the WhatsApp / email” unless a tool actually ran
- Reading phone numbers aloud (platform voice rules)

## Conversion funnel (website)

1. **Awareness** — landing hero + live preview panel  
2. **Understanding** — how-it-works (configure / test / review)  
3. **Trust** — call archive + memory copy, not logos-of-OpenAI  
4. **Offer** — pricing  
5. **Action** — Sign in / Get started → `/app/login`  
6. **Activation** — first agent + first Test Studio call  
7. **Revenue** — billing (gap) + PSTN number + campaign  

Every marketing CTA maps to step 5 or an in-page anchor. Do not send strangers to `/dev`.
