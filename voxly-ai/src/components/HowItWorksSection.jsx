import React from 'react';
import { ArrowRight, CreditCard } from 'lucide-react';
import { HOW_IT_WORKS_STEPS, BILLING_USAGE_PREVIEW } from '../data/siteContent';

/**
 * The canonical onboarding path, plus the billing terms.
 *
 * This used to be one of two near-identical steppers on the page. It is now the only
 * one. The billing widget beside it also showed a fabricated account — 20,500 credits,
 * 1,284 minutes, $128.40 — which implied $0.10/min while the pricing table said
 * $0.11–$0.14. It now shows the plan's own terms, which cannot drift from pricing
 * because pricing is where they come from.
 */
export function HowItWorksSection({ onGetStarted }) {
  return (
    <section id="how-it-works" className="py-20 sm:py-28 bg-white relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        <div className="max-w-3xl mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] text-[#6344E7] text-xs font-bold tracking-wider uppercase mb-4 shadow-craft-xs">
            <span>Onboarding</span>
          </div>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#0F0E17] tracking-tight leading-[1.12] mb-4">
            From idea to answering calls in minutes.
          </h2>
          <p className="text-base sm:text-lg text-[#524E5E] leading-relaxed">
            No developer setup and no telephony hardware. Five steps, and the first call is
            the one you place yourself.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-3.5 mb-16">
          {HOW_IT_WORKS_STEPS.map((st) => (
            <div
              key={st.step}
              className="bg-[#FAF9FD] p-5 rounded-xl border border-[#E4E2EB] flex flex-col justify-between"
            >
              <div>
                <div className="w-9 h-9 rounded-lg bg-white border border-[#E4E2EB] text-[#0F0E17] flex items-center justify-center font-mono font-bold text-xs mb-3 shadow-craft-xs">
                  {st.step}
                </div>
                <h4 className="text-sm font-bold text-[#0F0E17] mb-1.5">{st.title}</h4>
                <p className="text-xs text-[#524E5E] leading-relaxed">{st.desc}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="max-w-4xl bg-[#111019] text-white rounded-2xl p-6 sm:p-8 border border-white/10 shadow-craft-lg">
          <div className="flex flex-wrap items-center justify-between gap-4 pb-5 mb-6 border-b border-white/10">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-white/10 border border-white/10 text-white flex items-center justify-center">
                <CreditCard className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">{BILLING_USAGE_PREVIEW.headline}</h3>
                <p className="text-xs text-[#10B981] font-mono">{BILLING_USAGE_PREVIEW.tagline}</p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6 font-mono">
            {BILLING_USAGE_PREVIEW.items.map((item) => (
              <div key={item.label} className="bg-black/30 p-3.5 rounded-xl border border-white/5">
                <span className="text-[10px] font-sans font-bold text-[#A19EAD] uppercase tracking-wider block mb-1">
                  {item.label}
                </span>
                <span className="text-xl font-bold text-white">{item.value}</span>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-4 pt-4 border-t border-white/10 text-xs">
            <span className="text-[#D1CFDB] max-w-xl">{BILLING_USAGE_PREVIEW.footnote}</span>
            <button
              onClick={onGetStarted}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-semibold text-[#0F0E17] bg-white hover:bg-[#FAF9FD] active:scale-[0.98] transition-all"
            >
              <span>Build your agent</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

export default HowItWorksSection;