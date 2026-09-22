import React, { useState } from 'react';
import { SectionHeading } from './SectionHeading';
import { PRICING_TIERS } from '../data/siteContent';
import { Check, ArrowRight, Sparkles, CheckCircle2 } from 'lucide-react';
import { analytics } from '../services/analytics';
import { useWorkspace } from '../console/context/WorkspaceContext';

export function PricingSection({ onSelectPlan }) {
  const [annual, setAnnual] = useState(true);
  const [selectedTier, setSelectedTier] = useState('Professional');
  const workspace = useWorkspace();

  const handleSelect = (tierName) => {
    setSelectedTier(tierName);
    analytics.trackPlanSelected(tierName);
    if (workspace?.updateWorkspaceTier) {
      workspace.updateWorkspaceTier(tierName);
    }
  };

  const handleConfirm = (tierName) => {
    handleSelect(tierName);
    if (onSelectPlan) {
      onSelectPlan(tierName);
    }
  };

  return (
    <section id="pricing" className="py-20 sm:py-28 bg-[#FAF9FD] relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        <SectionHeading
          badge="Predictable Metering"
          title="Transparent Plans for Every"
          highlight="Fleet Size"
          subtitle="No telephony markup or rounding up to the nearest minute. Select a plan below to configure your voice fleet with dedicated DIDs and minutes."
        />

        {/* Monthly vs Annual Segmented Toggle */}
        <div className="flex items-center justify-center gap-3 mb-12">
          <div className="inline-flex p-1 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB]">
            <button
              type="button"
              onClick={() => setAnnual(false)}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                !annual
                  ? 'bg-white text-[#0F0E17] shadow-craft-xs'
                  : 'text-[#524E5E] hover:text-[#0F0E17]'
              }`}
            >
              Monthly Billing
            </button>
            <button
              type="button"
              onClick={() => setAnnual(true)}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                annual
                  ? 'bg-white text-[#0F0E17] shadow-craft-xs'
                  : 'text-[#524E5E] hover:text-[#0F0E17]'
              }`}
            >
              <span>Annual Billing</span>
              <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-[#0F0E17] text-white">
                -20%
              </span>
            </button>
          </div>
        </div>

        {/* Pricing Cards Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-stretch max-w-6xl mx-auto">
          {PRICING_TIERS.map((tier) => {
            const price = annual ? tier.priceAnnual : tier.priceMonthly;
            const isSelected = selectedTier === tier.name;

            return (
              <div
                key={tier.name}
                onClick={() => handleSelect(tier.name)}
                className={`rounded-2xl p-5 sm:p-7 flex flex-col justify-between transition-all duration-200 relative text-left cursor-pointer group select-none ${
                  isSelected
                    ? 'bg-white border-2 border-[#6344E7] shadow-craft-md -translate-y-1.5 ring-4 ring-[#6344E7]/10'
                    : 'bg-white border border-[#E4E2EB] shadow-craft-xs hover:border-[#6344E7]/50 hover:-translate-y-0.5'
                }`}
              >
                {/* Most Popular Badge */}
                {tier.highlighted && (
                  <div className="absolute -top-3 left-8 bg-[#0F0E17] text-white text-[10px] font-bold tracking-wider uppercase px-3 py-1 rounded-md shadow-xs">
                    Most Popular
                  </div>
                )}

                <div>
                  {/* Card Header: Category Badge & Select Pill */}
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="text-[11px] font-mono font-bold uppercase tracking-wider text-[#6344E7]">
                      {tier.badge}
                    </div>

                    {/* Selection State Indicator */}
                    {isSelected && (
                      <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-[#6344E7] text-white text-[10px] font-bold shadow-xs">
                        <Check className="w-3 h-3 stroke-[3]" />
                        <span>Selected</span>
                      </div>
                    )}
                  </div>

                  <h3 className="text-xl font-bold text-[#0F0E17] mb-2">
                    {tier.name}
                  </h3>
                  <p className="text-xs text-[#524E5E] leading-relaxed mb-6">
                    {tier.description}
                  </p>

                  <div className="flex items-baseline gap-1 mb-6 pb-6 border-b border-[#E4E2EB]">
                    <span className="text-4xl font-extrabold text-[#0F0E17] tracking-tight">
                      ${price}
                    </span>
                    <span className="text-xs font-semibold text-[#524E5E]">/ month</span>
                    {annual && (
                      <span className="text-[11px] font-mono text-[#15803D] ml-2 font-bold">
                        (Billed Annually)
                      </span>
                    )}
                  </div>

                  {/* Feature Checklist */}
                  <div className="space-y-2.5 mb-8">
                    <span className="text-[10px] font-mono font-bold text-[#524E5E] uppercase tracking-wider block">
                      Plan Inclusions:
                    </span>
                    {tier.features.map((feat, i) => (
                      <div key={i} className="flex items-start gap-2.5 text-xs text-[#0F0E17]">
                        <div className={`w-4 h-4 rounded-full flex items-center justify-center shrink-0 mt-0.5 border ${
                          isSelected
                            ? 'bg-[#6344E7]/10 border-[#6344E7]/30 text-[#6344E7]'
                            : 'bg-[#FAF9FD] border-[#E4E2EB] text-[#10B981]'
                        }`}>
                          <Check className="w-2.5 h-2.5 stroke-[3]" />
                        </div>
                        <span>{feat}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Bottom Action Button */}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleConfirm(tier.name);
                  }}
                  className={`w-full py-3.5 rounded-xl text-xs font-semibold transition-all flex items-center justify-center gap-2 active:scale-[0.98] ${
                    isSelected
                      ? 'bg-[#0F0E17] hover:bg-[#232130] text-white shadow-xs font-bold'
                      : 'bg-[#FAF9FD] hover:bg-[#F0EEF6] border border-[#E4E2EB] text-[#0F0E17]'
                  }`}
                >
                  <span>{isSelected ? `Continue with ${tier.name}` : `Select ${tier.name} Plan`}</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
