import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Pricing",
  description: "Usage-based voice AI pricing for Telugu-speaking business teams.",
};

const TIERS = [
  {
    name: "Starter",
    price: "Usage-based",
    desc: "Single agent, browser Test Studio, call archive.",
    features: ["1 agent", "Browser channel", "Call transcript & memory", "Community support"],
  },
  {
    name: "Business",
    price: "Custom",
    desc: "Production PSTN, campaigns, multi-agent fleet.",
    features: ["Unlimited agents", "Inbound + outbound PSTN", "Disposition analytics", "Priority support"],
    highlighted: true,
  },
  {
    name: "Enterprise",
    price: "Contact",
    desc: "Dedicated stack, custom tiers, SLA, on-prem options.",
    features: ["Custom provider stack", "RBAC & audit log", "Environment promotion", "Dedicated engineer"],
  },
];

export default function PricingPage() {
  return (
    <main className="py-20">
      <div className="mx-auto max-w-content px-6">
        <div className="max-w-2xl">
          <p className="label-caps text-accent">Pricing</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight text-text md:text-5xl">
            Pay for what your agents use
          </h1>
          <p className="mt-4 text-lg text-text-muted">
            STT, LLM, and TTS billed per tier. Telephony via Exotel. Contact us for fleet pricing.
          </p>
        </div>

        <div className="mt-16 grid gap-6 lg:grid-cols-3">
          {TIERS.map((tier) => (
            <article
              key={tier.name}
              className={`rounded-2xl border p-8 transition-all ${
                tier.highlighted
                  ? "border-accent/40 bg-accent-dim/30 shadow-glow"
                  : "border-surface-border-subtle bg-surface-card shadow-card"
              }`}
            >
              <h2 className="text-lg font-semibold text-text">{tier.name}</h2>
              <p className="mt-2 text-3xl font-semibold tracking-tight text-text">{tier.price}</p>
              <p className="mt-2 text-sm text-text-muted">{tier.desc}</p>
              <ul className="mt-6 space-y-2.5">
                {tier.features.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-text-muted">
                    <span className="text-accent">✓</span> {f}
                  </li>
                ))}
              </ul>
              <Link
                href="/app"
                className={`mt-8 block rounded-xl py-3 text-center text-sm font-semibold ${
                  tier.highlighted
                    ? "bg-accent text-white shadow-glow hover:bg-accent-hover"
                    : "border border-surface-border text-text hover:border-accent/40"
                }`}
              >
                {tier.name === "Enterprise" ? "Contact sales" : "Get started"}
              </Link>
            </article>
          ))}
        </div>
      </div>
    </main>
  );
}
