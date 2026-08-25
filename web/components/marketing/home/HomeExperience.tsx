"use client";

import Link from "next/link";
import { useState } from "react";
import { AgentPreview } from "./AgentPreview";
import { Reveal } from "./Reveal";
import { ScrollProgress } from "./ScrollProgress";
import { TiltCard } from "./TiltCard";

const STEPS = [
  {
    n: "01",
    title: "Configure your agent",
    body: "Use structured Business Brain sections — identity, facts, flows, and guardrails — compiled into one versioned prompt.",
    chips: ["Voice script", "Fields set", "Guardrails"],
  },
  {
    n: "02",
    title: "Test before you go live",
    body: "Run browser Test Studio with real speech, barge-in, and latency readouts. PSTN tests use the same call lifecycle.",
    chips: ["Live mic", "Transcript", "Trace"],
  },
  {
    n: "03",
    title: "Review every call",
    body: "Transcript ledger, memory projection, disposition, and audio archive — ready the moment the call ends.",
    chips: ["Memory", "Disposition", "Archive"],
  },
];

const FEATURES = [
  {
    title: "Caller memory",
    body: "Returning customers are recognized without asking them to repeat budget, location, or last next-action.",
    sample: "Welcome back, Rahul — still looking at the 3BHK in Gachibowli?",
  },
  {
    title: "Structured outcomes",
    body: "Summary, sentiment, and extracted fields land on the call record automatically — not in a spreadsheet later.",
    sample: "Budget ₹1.5–2 Cr · Timeline immediate · Sentiment: positive",
  },
  {
    title: "Production reliability",
    body: "Sentence-buffered TTS, barge-in, and stream healing keep conversations natural when networks jitter.",
    sample: "Network jitter detected → stream stabilized in 120ms",
  },
];

const FAQS = [
  {
    q: "Who is Vāṇi built for?",
    a: "Teams in Andhra Pradesh, Telangana, and across India who serve Telugu-speaking customers on the phone — real estate, admissions, healthcare, dealerships, and D2C.",
  },
  {
    q: "Does the agent sound robotic?",
    a: "No. It is tuned for natural conversational speech with Telugu-speaking customers, including mixed-language turns when callers switch mid-sentence.",
  },
  {
    q: "What happens after each call?",
    a: "Every finalized call produces a transcript, working memory history, disposition, and optional audio archive. You inspect calls in the console — not in a demo session log.",
  },
  {
    q: "Can I test before paying for telephony?",
    a: "Yes. Start in the browser with Test Studio, validate your Business Brain, then connect PSTN when you are ready.",
  },
];

export function HomeExperience() {
  const [openFaq, setOpenFaq] = useState(0);

  return (
    <>
      <ScrollProgress />

      <section className="relative overflow-hidden border-b border-surface-border-subtle">
        <div className="pointer-events-none absolute inset-0 grid-bg opacity-50" aria-hidden />
        <div
          className="pointer-events-none absolute left-1/2 top-[-100px] h-[480px] w-[720px] -translate-x-1/2 rounded-full bg-accent/8 blur-3xl"
          aria-hidden
        />

        <div className="relative mx-auto max-w-content px-6 pb-20 pt-16 md:pb-28 md:pt-24">
          <div className="grid items-center gap-14 lg:grid-cols-[1.05fr_0.95fr]">
            <div>
              <p className="inline-flex items-center gap-2 rounded-full border border-surface-border bg-surface-card/90 px-3.5 py-1.5 text-xs font-medium text-text-muted backdrop-blur-sm">
                <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-dot" />
                Built for Telugu-speaking markets
              </p>
              <h1 className="mt-7 text-[2.65rem] font-semibold leading-[1.08] tracking-tight text-text sm:text-5xl lg:text-[3.25rem]">
                Voice agents that <span className="text-accent">remember</span> every caller.
              </h1>
              <p className="mt-6 max-w-xl text-lg leading-relaxed text-text-muted">
                Configure how your agent speaks, test live in the browser, and review every call with memory and
                disposition — one operational console for your team.
              </p>
              <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
                <Link href="/app" className="btn-primary">Open Console</Link>
                <Link href="/pricing" className="btn-secondary">View pricing</Link>
              </div>
              <p className="mt-5 font-mono text-[11px] uppercase tracking-wider text-text-subtle">
                Browser test in minutes · PSTN ready · Memory on every call
              </p>
            </div>
            <TiltCard>
              <AgentPreview />
            </TiltCard>
          </div>
        </div>
      </section>

      <section id="how-it-works" className="border-b border-surface-border-subtle py-24" aria-labelledby="how-title">
        <div className="mx-auto max-w-content px-6">
          <Reveal>
            <p className="label-caps text-accent">How it works</p>
            <h2 id="how-title" className="mt-3 max-w-2xl text-3xl font-semibold tracking-tight text-text md:text-4xl">
              Configure, test, and review — without an agency setup fee.
            </h2>
            <p className="mt-4 max-w-2xl text-lg text-text-muted">
              Your team owns the script, the voice tier, and the call archive. No black-box demo mic.
            </p>
          </Reveal>
          <ol className="mt-14 grid gap-6 md:grid-cols-3">
            {STEPS.map((step, i) => (
              <Reveal key={step.n} as="li" delayMs={i * 80}>
                <article className="card-surface h-full p-6">
                  <span className="font-mono text-2xl font-medium text-accent/50">{step.n}</span>
                  <h3 className="mt-4 text-lg font-semibold text-text">{step.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-text-muted">{step.body}</p>
                  <div className="mt-5 flex flex-wrap gap-2">
                    {step.chips.map((chip) => (
                      <span
                        key={chip}
                        className="rounded-full border border-surface-border bg-surface-raised px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-text-muted"
                      >
                        {chip}
                      </span>
                    ))}
                  </div>
                </article>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      <section className="border-b border-surface-border-subtle bg-surface-elevated py-24" aria-labelledby="features-title">
        <div className="mx-auto max-w-content px-6">
          <Reveal>
            <p className="label-caps text-accent">Why teams switch</p>
            <h2 id="features-title" className="mt-3 text-3xl font-semibold tracking-tight text-text md:text-4xl">
              Memory and outcomes — not a script reader.
            </h2>
          </Reveal>
          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {FEATURES.map((item, i) => (
              <Reveal key={item.title} as="article" delayMs={i * 60} className="card-surface p-6">
                <h3 className="text-lg font-semibold text-text">{item.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-text-muted">{item.body}</p>
                <div className="mt-5 rounded-xl border border-surface-border-subtle bg-surface-raised px-3 py-3">
                  <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Example</p>
                  <p className="mt-1 text-sm text-text">{item.sample}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b border-surface-border-subtle py-24" aria-labelledby="console-title">
        <div className="mx-auto max-w-content px-6">
          <Reveal>
            <p className="label-caps text-accent">Your console</p>
            <h2 id="console-title" className="mt-3 text-3xl font-semibold tracking-tight text-text md:text-4xl">
              One place to run your voice operation.
            </h2>
            <p className="mt-4 max-w-xl text-lg text-text-muted">
              Agents, Test Studio, call review, and analytics — without exposing provider knobs to every user.
            </p>
          </Reveal>
          <Reveal className="mt-10 overflow-hidden rounded-2xl border border-surface-border-subtle bg-surface-card shadow-card">
            <div className="flex items-center justify-between border-b border-surface-border-subtle px-5 py-3">
              <p className="font-mono text-[11px] uppercase tracking-wider text-text-subtle">Business console · overview</p>
              <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-accent">
                <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                live
              </span>
            </div>
            <div className="grid gap-px bg-surface-border-subtle sm:grid-cols-4">
              {[
                ["Active agents", "3"],
                ["Calls today", "128"],
                ["Qualified leads", "41"],
                ["P95 latency", "1.1s"],
              ].map(([label, value]) => (
                <div key={label} className="bg-surface-card px-5 py-5">
                  <p className="font-mono text-2xl font-medium text-text">{value}</p>
                  <p className="mt-1 text-xs text-text-muted">{label}</p>
                </div>
              ))}
            </div>
          </Reveal>
          <div className="mt-8">
            <Link href="/app" className="text-sm font-semibold text-accent hover:underline">
              Open Business Console →
            </Link>
          </div>
        </div>
      </section>

      <section className="border-b border-surface-border-subtle py-24" aria-labelledby="faq-title">
        <div className="mx-auto max-w-content px-6">
          <Reveal>
            <p className="label-caps text-accent">FAQ</p>
            <h2 id="faq-title" className="mt-3 text-3xl font-semibold tracking-tight text-text md:text-4xl">
              Questions before you hand over the phone line.
            </h2>
          </Reveal>
          <ul className="mt-10 divide-y divide-surface-border-subtle border-y border-surface-border-subtle">
            {FAQS.map((item, i) => (
              <li key={item.q}>
                <button
                  type="button"
                  className="flex w-full items-start justify-between gap-6 py-5 text-left"
                  aria-expanded={openFaq === i}
                  onClick={() => setOpenFaq(openFaq === i ? -1 : i)}
                >
                  <span className="text-base font-medium text-text">{item.q}</span>
                  <span className="font-mono text-accent">{openFaq === i ? "−" : "+"}</span>
                </button>
                {openFaq === i && <p className="pb-5 text-sm leading-relaxed text-text-muted">{item.a}</p>}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="py-24">
        <div className="mx-auto max-w-content px-6">
          <div className="relative overflow-hidden rounded-3xl border border-accent/20 bg-accent-dim/40 px-8 py-16 text-center md:px-16">
            <div className="absolute inset-0 grid-bg opacity-20" aria-hidden />
            <div className="relative">
              <p className="label-caps text-accent">Get started</p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight text-text md:text-4xl">
                Ready to configure your first agent?
              </h2>
              <p className="mx-auto mt-4 max-w-lg text-text-muted">
                Sign in, edit your Business Brain, and run a live Test Studio session.
              </p>
              <div className="mt-8 flex flex-col items-center justify-center gap-4 sm:flex-row">
                <Link href="/app/agents" className="btn-primary">Go to Agents</Link>
                <Link href="/app/login" className="btn-secondary">Sign in</Link>
              </div>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
