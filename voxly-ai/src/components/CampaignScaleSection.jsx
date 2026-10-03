import React from 'react';
import { UploadCloud, Users, Rocket, PhoneCall, BarChart3, ArrowRight } from 'lucide-react';
import { CAMPAIGN_WORKFLOW } from '../data/siteContent';

const STEP_ICONS = [UploadCloud, Users, Rocket, PhoneCall, BarChart3];

/**
 * Bulk calling.
 *
 * This section used to end with a "Live Campaign Command Center" — 2,450 contacts,
 * 486 qualified, a 26.4% conversion rate, a progress bar frozen at 88% — pointing at a
 * fictional employee called Harish Patel who no longer exists on the page. Five mock
 * dashboards across the page, each showing a different invented business, was the single
 * biggest credibility problem here.
 *
 * The analytics section keeps one clearly-labelled example dashboard, because a page
 * that describes reporting with no picture of it is harder to evaluate. This one keeps
 * the process, which is the part a buyer actually needs to picture.
 */
export function CampaignScaleSection({ onGetStarted }) {
  return (
    <section id="campaigns" className="py-20 sm:py-28 bg-[#FAF9FD] relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        <div className="max-w-3xl mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-white border border-[#E4E2EB] text-[#6344E7] text-xs font-bold tracking-wider uppercase mb-4 shadow-craft-xs">
            <span>High-Volume Outbound</span>
          </div>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#0F0E17] tracking-tight leading-[1.12] mb-4">
            {CAMPAIGN_WORKFLOW.headline}
          </h2>
          <p className="text-base sm:text-lg text-[#524E5E] leading-relaxed">
            {CAMPAIGN_WORKFLOW.subtitle}
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5 mb-12 max-w-6xl">
          {CAMPAIGN_WORKFLOW.steps.map((step, idx) => {
            const Icon = STEP_ICONS[idx] || Rocket;
            return (
              <div
                key={step.num}
                className="bg-white p-5 rounded-xl border border-[#E4E2EB] shadow-craft-xs flex flex-col justify-between"
              >
                <div>
                  <div className="w-8 h-8 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] text-[#0F0E17] flex items-center justify-center font-bold text-xs mb-3">
                    <Icon className="w-4 h-4" />
                  </div>
                  <span className="text-[10px] font-mono font-semibold text-[#6344E7] uppercase tracking-wider block mb-1">
                    Step {step.num}
                  </span>
                  <h4 className="text-sm font-bold text-[#0F0E17] mb-1">{step.title}</h4>
                  <p className="text-xs text-[#524E5E] leading-relaxed">{step.desc}</p>
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-4 max-w-6xl">
          <p className="text-xs text-[#524E5E] max-w-xl leading-relaxed">
            Pacing, retry limits and Do-Not-Call scrubbing are set per campaign, so a list is
            never dialled faster than the rules you configured allow.
          </p>
          <button
            onClick={onGetStarted}
            className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-xs font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] active:scale-[0.98] transition-all duration-150 shadow-xs"
          >
            <span>Run your first campaign</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </section>
  );
}

export default CampaignScaleSection;