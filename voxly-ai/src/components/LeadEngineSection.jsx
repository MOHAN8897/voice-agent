import React, { useState } from 'react';
import {
  Target,
  Filter,
  FolderKanban,
  Send,
  ArrowRight,
  CheckCircle2,
  User,
  Building,
  DollarSign,
  Calendar
} from 'lucide-react';
import { LEAD_PIPELINE } from '../data/siteContent';

const ICONS = {
  Target,
  Filter,
  FolderKanban,
  Send,
};

export function LeadEngineSection({ onGetStarted }) {
  const [activeCard, setActiveCard] = useState(0);

  return (
    <section id="leads" className="py-20 sm:py-28 bg-white relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        
        {/* Section Header */}
        <div className="max-w-3xl mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] text-[#6344E7] text-xs font-bold tracking-wider uppercase mb-4 shadow-craft-xs">
            <span>Pipeline Intelligence</span>
          </div>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#0F0E17] tracking-tight leading-[1.12] mb-4">
            Every conversation can become an opportunity.
          </h2>
          <p className="text-base sm:text-lg text-[#524E5E] leading-relaxed">
            {LEAD_PIPELINE.subtitle}
          </p>
        </div>

        {/* Pipeline Stepper Visual: CALL -> CONVERSATION -> INTENT -> QUALIFIED LEAD -> FOLLOW-UP */}
        <div className="mb-14">
          <div className="bg-[#FAF9FD] rounded-2xl p-6 sm:p-7 border border-[#E4E2EB] max-w-5xl">
            <span className="text-[10px] font-bold text-[#524E5E] uppercase tracking-wider block font-mono mb-5">
              Autonomous Conversion Flow:
            </span>

            <div className="flex flex-col md:flex-row items-center justify-between gap-3">
              {LEAD_PIPELINE.stages.map((stage, idx) => (
                <React.Fragment key={stage}>
                  <div className="flex flex-col items-center text-center">
                    <div className="w-10 h-10 rounded-xl bg-white border border-[#E4E2EB] flex items-center justify-center font-mono font-bold text-xs text-[#0F0E17] shadow-craft-xs mb-2">
                      0{idx + 1}
                    </div>
                    <span className="text-xs font-bold text-[#0F0E17] tracking-tight">
                      {stage}
                    </span>
                  </div>

                  {idx < LEAD_PIPELINE.stages.length - 1 && (
                    <div className="hidden md:flex items-center text-[#8C8899]">
                      <ArrowRight className="w-4 h-4" />
                    </div>
                  )}
                </React.Fragment>
              ))}
            </div>
          </div>
        </div>

        {/* 4 Cards: Capture, Qualify, Organize, Follow Up */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-14">
          {LEAD_PIPELINE.cards.map((card, idx) => {
            const Icon = ICONS[card.icon] || Target;
            const isSelected = activeCard === idx;

            return (
              <div
                key={card.title}
                onClick={() => setActiveCard(idx)}
                className={`p-6 rounded-xl cursor-pointer border text-left transition-all duration-150 flex flex-col justify-between ${
                  isSelected
                    ? 'bg-[#FAF9FD] border-[#0F0E17] shadow-craft-sm ring-1 ring-[#0F0E17]'
                    : 'bg-white hover:bg-[#FAF9FD] border-[#E4E2EB] hover:border-[#D1CFDB]'
                }`}
              >
                <div>
                  <div className="w-9 h-9 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] text-[#0F0E17] flex items-center justify-center mb-4">
                    <Icon className="w-4 h-4" />
                  </div>
                  <h3 className="text-base font-bold text-[#0F0E17] mb-1">
                    {card.title}
                  </h3>
                  <h4 className="text-[11px] font-semibold text-[#6344E7] uppercase tracking-wider mb-2">
                    {card.desc}
                  </h4>
                  <p className="text-xs text-[#524E5E] leading-relaxed mb-4">
                    {card.detail}
                  </p>
                </div>
                <div className="pt-3 border-t border-[#E4E2EB] flex items-center gap-1.5 text-xs font-mono font-medium text-[#10B981]">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>{card.stat}</span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Live Extracted Lead Card Preview Mockup */}
        <div className="bg-[#111019] text-white rounded-2xl p-6 sm:p-7 border border-white/10 shadow-craft-lg max-w-4xl mx-auto">
          <div className="flex items-center justify-between gap-4 pb-4 mb-5 border-b border-white/10">
            <div className="flex items-center gap-2.5">
              <span className="w-6 h-6 rounded-md bg-[#10B981]/20 text-[#10B981] flex items-center justify-center font-bold text-xs">
                ✓
              </span>
              <div>
                <h4 className="text-sm font-bold text-white">Live Extraction Dispatched to CRM</h4>
                <p className="text-[11px] font-mono text-[#D1CFDB]">Auto-created via Call #2841 (03:42 duration)</p>
              </div>
            </div>
            <span className="px-2.5 py-1 rounded-md text-[11px] font-mono font-semibold bg-white/10 text-white border border-white/15">
              {LEAD_PIPELINE.sampleLead.status}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
            <div className="bg-black/30 p-3 rounded-xl border border-white/5">
              <span className="text-[#A19EAD] block text-[10px] uppercase mb-1">Decision Maker:</span>
              <span className="text-white font-medium flex items-center gap-2">
                <User className="w-3.5 h-3.5 text-[#D1CFDB]" />
                {LEAD_PIPELINE.sampleLead.name} ({LEAD_PIPELINE.sampleLead.role})
              </span>
            </div>

            <div className="bg-black/30 p-3 rounded-xl border border-white/5">
              <span className="text-[#A19EAD] block text-[10px] uppercase mb-1">Target Account:</span>
              <span className="text-white font-medium flex items-center gap-2">
                <Building className="w-3.5 h-3.5 text-[#D1CFDB]" />
                {LEAD_PIPELINE.sampleLead.company}
              </span>
            </div>

            <div className="bg-black/30 p-3 rounded-xl border border-white/5">
              <span className="text-[#A19EAD] block text-[10px] uppercase mb-1">Detected Intent:</span>
              <span className="text-[#D1CFDB] font-medium leading-relaxed block">
                "{LEAD_PIPELINE.sampleLead.intent}"
              </span>
            </div>

            <div className="bg-black/30 p-3 rounded-xl border border-white/5">
              <span className="text-[#A19EAD] block text-[10px] uppercase mb-1">Verified Budget & Authority:</span>
              <span className="text-[#10B981] font-bold text-xs flex items-center gap-1.5">
                <DollarSign className="w-3.5 h-3.5" />
                {LEAD_PIPELINE.sampleLead.budget} (BANT Verified)
              </span>
            </div>
          </div>
        </div>

      </div>
    </section>
  );
}
