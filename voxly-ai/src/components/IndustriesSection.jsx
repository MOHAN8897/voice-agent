import React, { useState } from 'react';
import {
  TrendingUp,
  Headphones,
  Building2,
  Stethoscope,
  ShieldCheck,
  ShoppingBag,
  ArrowRight,
  CheckCircle2,
  Briefcase
} from 'lucide-react';
import { INDUSTRIES_DATA } from '../data/siteContent';

const INDUSTRY_ICONS = {
  TrendingUp,
  Headphones,
  Building2,
  Stethoscope,
  ShieldCheck,
  ShoppingBag,
};

export function IndustriesSection({ onGetStarted }) {
  const [selectedIndustry, setSelectedIndustry] = useState(0);

  return (
    <section id="industries" className="py-20 sm:py-28 bg-[#FAF9FD] relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        
        {/* Section Header */}
        <div className="max-w-3xl mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-white border border-[#E4E2EB] text-[#6344E7] text-xs font-bold tracking-wider uppercase mb-4 shadow-craft-xs">
            <span>Vertical Solutions</span>
          </div>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#0F0E17] tracking-tight leading-[1.12] mb-4">
            One AI platform. Every conversation.
          </h2>
          <p className="text-base sm:text-lg text-[#524E5E] leading-relaxed">
            Tailored acoustic models, domain vocabularies, and regulatory compliance built for high-performing organizations across every vertical.
          </p>
        </div>

        {/* 6 Industry Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-10">
          {INDUSTRIES_DATA.map((ind, idx) => {
            const Icon = INDUSTRY_ICONS[ind.icon] || Briefcase;
            const isSelected = selectedIndustry === idx;

            return (
              <div
                key={ind.id}
                onClick={() => setSelectedIndustry(idx)}
                className={`p-6 rounded-2xl border transition-all duration-150 cursor-pointer flex flex-col justify-between text-left ${
                  isSelected
                    ? 'bg-white border-[#0F0E17] shadow-craft-sm ring-1 ring-[#0F0E17]'
                    : 'bg-white/80 hover:bg-white border-[#E4E2EB] hover:border-[#D1CFDB]'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <div className="w-9 h-9 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-[#0F0E17] flex items-center justify-center">
                      <Icon className="w-4 h-4" />
                    </div>
                    <span className="text-[11px] font-mono font-semibold text-[#10B981] bg-[#10B981]/10 px-2.5 py-0.5 rounded border border-[#10B981]/20">
                      {ind.stat}
                    </span>
                  </div>

                  <h3 className="text-base font-bold text-[#0F0E17] mb-0.5">
                    {ind.title}
                  </h3>
                  <h4 className="text-xs font-semibold text-[#6344E7] mb-2.5">
                    {ind.subtitle}
                  </h4>
                  <p className="text-xs text-[#524E5E] leading-relaxed mb-4">
                    {ind.desc}
                  </p>

                  <div className="space-y-2 pt-3 border-t border-[#E4E2EB]">
                    {ind.examples.map((ex, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs text-[#0F0E17]">
                        <CheckCircle2 className="w-3.5 h-3.5 text-[#10B981] flex-shrink-0" />
                        <span>{ex}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="pt-4 mt-4 border-t border-[#E4E2EB]">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onGetStarted();
                    }}
                    className="w-full flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-xs font-semibold text-[#0F0E17] bg-[#FAF9FD] hover:bg-[#F0EEF6] border border-[#E4E2EB] transition-all"
                  >
                    <span>Deploy {ind.title} Agent</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>

      </div>
    </section>
  );
}
