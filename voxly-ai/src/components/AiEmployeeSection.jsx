import React, { useState } from 'react';
import {
  PhoneIncoming,
  PhoneOutgoing,
  Sparkles,
  CheckCircle2,
  Calendar,
  RotateCcw,
  HelpCircle,
  UserCheck,
  Target,
  Send,
  ArrowRight,
} from 'lucide-react';
import { AI_EMPLOYEE_CAPABILITIES } from '../data/siteContent';

const ICONS = {
  PhoneIncoming,
  PhoneOutgoing,
  Sparkles,
  CheckCircle2,
  Calendar,
  RotateCcw,
  HelpCircle,
  UserCheck,
  Target,
  Send,
};

/**
 * What the employee does on a call.
 *
 * This section used to carry two more things that have moved or gone:
 *  - a second onboarding stepper, six sections after the canonical one in
 *    HowItWorksSection, saying the same five things in slightly different words;
 *  - a "live telemetry" panel and a fake studio console full of invented readings
 *    ("Sub-350ms", "148 wpm", "3,420 pages ingested", "100,000 parallel calls").
 *    A mock dashboard that invents its own numbers is evidence against the product.
 *
 * What is here now is the capability list and one honest panel: what the selected
 * capability does, and where the call record ends up.
 */
const SIDE_PANEL = {
  header: 'Where this ends up',
  rows: [
    { label: 'Transcript', value: 'Stored against the call, searchable' },
    { label: 'Extracted fields', value: 'Written to your CRM on disposition' },
    { label: 'Outcome', value: 'Qualified, booked, or escalated — with a reason' },
    { label: 'Recording', value: 'Kept for as long as you set retention' },
  ],
};

export function AiEmployeeSection({ onGetStarted }) {
  const [selectedCapability, setSelectedCapability] = useState(0);

  const activeCap = AI_EMPLOYEE_CAPABILITIES[selectedCapability];
  const ActiveCapIcon = ICONS[activeCap.icon] || CheckCircle2;

  return (
    <section id="capabilities" className="py-20 sm:py-28 bg-[#FAF9FD] relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        <div className="max-w-3xl mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-white border border-[#E4E2EB] text-[#6344E7] text-xs font-bold tracking-wider uppercase mb-4 shadow-craft-xs">
            <span>Capabilities</span>
          </div>
          <h2 className="text-2xl sm:text-4xl lg:text-5xl font-extrabold text-[#0F0E17] tracking-tight leading-[1.12] mb-4">
            More than a voice bot.{' '}
            <span className="block text-[#0F0E17]">Your AI employee.</span>
          </h2>
          <p className="text-base sm:text-lg text-[#524E5E] leading-relaxed">
            It doesn't read a fixed script. It works out what the caller wants, answers from
            your material, applies your qualification rules, and writes the whole thing up before
            it hangs up.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch">
          {/* Capability grid */}
          <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            {AI_EMPLOYEE_CAPABILITIES.map((cap, idx) => {
              const IconComponent = ICONS[cap.icon] || CheckCircle2;
              const isSelected = selectedCapability === idx;

              return (
                <button
                  key={cap.id}
                  type="button"
                  onClick={() => setSelectedCapability(idx)}
                  aria-pressed={isSelected}
                  className={`p-5 rounded-xl transition-all duration-150 cursor-pointer border text-left flex flex-col justify-between ${
                    isSelected
                      ? 'bg-white border-[#0F0E17] shadow-craft-sm ring-1 ring-[#0F0E17]'
                      : 'bg-white/80 hover:bg-white border-[#E4E2EB] hover:border-[#D1CFDB] shadow-craft-xs'
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <div
                        className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${
                          isSelected
                            ? 'bg-[#0F0E17] text-white'
                            : 'bg-[#FAF9FD] text-[#524E5E] border border-[#E4E2EB]'
                        }`}
                      >
                        <IconComponent className="w-4 h-4" />
                      </div>
                      <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded bg-[#FAF9FD] border border-[#E4E2EB] text-[#524E5E]">
                        {cap.badge}
                      </span>
                    </div>

                    <h3 className="text-sm font-bold text-[#0F0E17] mb-1.5">{cap.title}</h3>
                    <p className="text-xs text-[#524E5E] leading-relaxed">{cap.desc}</p>
                  </div>

                  <div className="pt-3 mt-3 border-t border-[#E4E2EB] flex items-center justify-between text-[11px] font-medium text-[#6344E7]">
                    <span>{cap.highlight}</span>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Selected capability + where the result lands */}
          <div className="lg:col-span-5 bg-[#111019] text-white rounded-2xl p-6 sm:p-7 border border-white/10 shadow-craft-lg flex flex-col justify-between">
            <div>
              <div className="flex items-center gap-3 mb-4 pb-5 border-b border-white/10">
                <div className="w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center text-white">
                  <ActiveCapIcon className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-white">{activeCap.title}</h4>
                  <p className="text-[11px] text-[#D1CFDB]">{activeCap.badge}</p>
                </div>
              </div>

              <p className="text-xs text-[#D1CFDB] leading-relaxed mb-6">{activeCap.desc}</p>

              <p className="text-[11px] uppercase tracking-wider text-[#A19EAD] font-bold mb-3">
                {SIDE_PANEL.header}
              </p>
              <div className="space-y-2.5">
                {SIDE_PANEL.rows.map((row) => (
                  <div
                    key={row.label}
                    className="flex items-start justify-between gap-3 text-[11px] border-b border-white/5 pb-2 last:border-0"
                  >
                    <span className="text-[#A19EAD] shrink-0">{row.label}</span>
                    <span className="text-[#D1CFDB] text-right">{row.value}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="pt-6 mt-6 border-t border-white/10">
              <button
                onClick={onGetStarted}
                className="w-full inline-flex items-center justify-center gap-2 px-6 py-3 min-h-[44px] rounded-xl text-xs font-semibold text-[#0F0E17] bg-white hover:bg-[#FAF9FD] active:scale-[0.98] transition-all"
              >
                <span>Build this employee</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default AiEmployeeSection;