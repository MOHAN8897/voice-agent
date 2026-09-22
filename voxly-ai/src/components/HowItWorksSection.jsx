import React from 'react';
import {
  ArrowRight,
  CreditCard,
  CheckCircle2,
  Clock,
  ShieldCheck,
  PhoneCall
} from 'lucide-react';
import { HOW_IT_WORKS_STEPS, BILLING_USAGE_PREVIEW } from '../data/siteContent';

export function HowItWorksSection({ onGetStarted }) {
  return (
    <section id="how-it-works" className="py-20 sm:py-28 bg-white relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        
        {/* Section Header */}
        <div className="max-w-3xl mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] text-[#6344E7] text-xs font-bold tracking-wider uppercase mb-4 shadow-craft-xs">
            <span>Onboarding Roadmap</span>
          </div>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#0F0E17] tracking-tight leading-[1.12] mb-4">
            From idea to AI employee in minutes.
          </h2>
          <p className="text-base sm:text-lg text-[#524E5E] leading-relaxed">
            No complex developer setups or telephony hardware required. Get your first AI employee live and talking to customers in five simple steps.
          </p>
        </div>

        {/* 5-Step Numbered Cards */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3.5 mb-16">
          {HOW_IT_WORKS_STEPS.map((st, idx) => (
            <div
              key={st.step}
              className="bg-[#FAF9FD] p-5 rounded-xl border border-[#E4E2EB] flex flex-col justify-between"
            >
              <div>
                <div className="w-9 h-9 rounded-lg bg-white border border-[#E4E2EB] text-[#0F0E17] flex items-center justify-center font-mono font-bold text-xs mb-3 shadow-craft-xs">
                  {st.step}
                </div>
                <h4 className="text-sm font-bold text-[#0F0E17] mb-1.5">
                  {st.title}
                </h4>
                <p className="text-xs text-[#524E5E] leading-relaxed">
                  {st.desc}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* ================================================================= */}
        {/* Simple Usage & Billing Widget */}
        {/* ================================================================= */}
        <div className="max-w-4xl bg-[#111019] text-white rounded-2xl p-6 sm:p-8 border border-white/10 shadow-craft-lg">
          <div className="flex flex-wrap items-center justify-between gap-4 pb-5 mb-6 border-b border-white/10">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-white/10 border border-white/10 text-white flex items-center justify-center">
                <CreditCard className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">
                  {BILLING_USAGE_PREVIEW.headline}
                </h3>
                <p className="text-xs text-[#10B981] font-mono">
                  {BILLING_USAGE_PREVIEW.tagline}
                </p>
              </div>
            </div>

            <span className="text-[11px] font-mono px-2.5 py-1 rounded bg-white/10 text-white border border-white/10">
              {BILLING_USAGE_PREVIEW.billingPerSec}
            </span>
          </div>

          {/* 4 Usage Counters */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6 font-mono">
            <div className="bg-black/30 p-3.5 rounded-xl border border-white/5">
              <span className="text-[10px] font-sans font-bold text-[#A19EAD] uppercase tracking-wider block mb-1">
                Allocated Credits
              </span>
              <span className="text-xl font-bold text-white">
                {BILLING_USAGE_PREVIEW.credits}
              </span>
            </div>

            <div className="bg-black/30 p-3.5 rounded-xl border border-white/5">
              <span className="text-[10px] font-sans font-bold text-[#A19EAD] uppercase tracking-wider block mb-1">
                Minutes Used
              </span>
              <span className="text-xl font-bold text-[#D1CFDB]">
                {BILLING_USAGE_PREVIEW.minutesUsed}
              </span>
            </div>

            <div className="bg-black/30 p-3.5 rounded-xl border border-white/5">
              <span className="text-[10px] font-sans font-bold text-[#A19EAD] uppercase tracking-wider block mb-1">
                Current Spend
              </span>
              <span className="text-xl font-bold text-[#10B981]">
                {BILLING_USAGE_PREVIEW.currentUsage}
              </span>
            </div>

            <div className="bg-black/30 p-3.5 rounded-xl border border-white/5">
              <span className="text-[10px] font-sans font-bold text-[#A19EAD] uppercase tracking-wider block mb-1">
                Remaining
              </span>
              <span className="text-xl font-bold text-white">
                {BILLING_USAGE_PREVIEW.remainingMinutes}
              </span>
            </div>
          </div>

          {/* Bottom Call to Action */}
          <div className="flex flex-wrap items-center justify-between gap-4 pt-4 border-t border-white/10 text-xs">
            <span className="text-[#D1CFDB]">
              Zero charges for unanswered rings, busy tones, or voicemail. You are billed strictly per connected second.
            </span>
            <button
              onClick={onGetStarted}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-semibold text-[#0F0E17] bg-white hover:bg-[#FAF9FD] active:scale-[0.98] transition-all"
            >
              <span>Build Your Agent</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

      </div>
    </section>
  );
}
