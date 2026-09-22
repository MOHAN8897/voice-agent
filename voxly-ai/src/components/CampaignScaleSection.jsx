import React, { useState } from 'react';
import {
  UploadCloud,
  Users,
  Rocket,
  PhoneCall,
  BarChart3,
  ArrowRight,
  CheckCircle2,
  FileSpreadsheet
} from 'lucide-react';
import { CAMPAIGN_WORKFLOW } from '../data/siteContent';

const STEP_ICONS = [
  UploadCloud,
  Users,
  Rocket,
  PhoneCall,
  BarChart3,
];

export function CampaignScaleSection({ onGetStarted }) {
  const [campaignProgress] = useState(88);

  return (
    <section id="campaigns" className="py-20 sm:py-28 bg-[#FAF9FD] relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        
        {/* Section Header */}
        <div className="max-w-3xl mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-white border border-[#E4E2EB] text-[#6344E7] text-xs font-bold tracking-wider uppercase mb-4 shadow-craft-xs">
            <span>High-Volume Outbound</span>
          </div>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#0F0E17] tracking-tight leading-[1.12] mb-4">
            One list. Thousands of conversations.
          </h2>
          <p className="text-base sm:text-lg text-[#524E5E] leading-relaxed">
            {CAMPAIGN_WORKFLOW.subtitle}
          </p>
        </div>

        {/* 5-Step Visual Workflow: Upload Contacts -> Select Employee -> Launch -> AI Calls -> Results */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5 mb-14 max-w-6xl">
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
                  <h4 className="text-sm font-bold text-[#0F0E17] mb-1">
                    {step.title}
                  </h4>
                  <p className="text-xs text-[#524E5E] leading-relaxed">
                    {step.desc}
                  </p>
                </div>
              </div>
            );
          })}
        </div>

        {/* Live Campaign Command Center Dashboard */}
        <div className="max-w-4xl bg-white rounded-2xl border border-[#E4E2EB] shadow-craft-md p-6 sm:p-8">
          <div className="flex flex-wrap items-center justify-between gap-4 pb-5 mb-6 border-b border-[#E4E2EB]">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-[#0F0E17] flex items-center justify-center">
                <FileSpreadsheet className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-base font-bold text-[#0F0E17]">
                  {CAMPAIGN_WORKFLOW.mockCampaign.name}
                </h4>
                <p className="text-xs text-[#524E5E]">
                  Assigned Employee: Harish Patel (Senior Sales AI) • Automated DNC Check Active
                </p>
              </div>
            </div>

            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono font-semibold bg-[#FAF9FD] text-[#10B981] border border-[#E4E2EB]">
              <span className="w-2 h-2 rounded-full bg-[#10B981]" />
              Campaign In Progress
            </span>
          </div>

          {/* Progress bar */}
          <div className="mb-6">
            <div className="flex justify-between text-xs font-semibold mb-2">
              <span className="text-[#0F0E17]">Live Execution Progress ({campaignProgress}%)</span>
              <span className="font-mono text-[#524E5E]">{CAMPAIGN_WORKFLOW.mockCampaign.callsPlaced} / {CAMPAIGN_WORKFLOW.mockCampaign.totalContacts} Contacts Reached</span>
            </div>
            <div className="w-full h-2.5 rounded-full bg-[#F0EEF6] overflow-hidden">
              <div
                className="h-full bg-[#0F0E17] rounded-full transition-all duration-500"
                style={{ width: `${campaignProgress}%` }}
              />
            </div>
          </div>

          {/* Metrics Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6 font-mono">
            <div className="bg-[#FAF9FD] p-3.5 rounded-xl border border-[#E4E2EB]">
              <span className="text-[10px] uppercase tracking-wider block text-[#524E5E] font-sans font-bold mb-1">Connected Calls</span>
              <span className="text-lg font-bold text-[#0F0E17]">{CAMPAIGN_WORKFLOW.mockCampaign.connectedCalls}</span>
            </div>
            <div className="bg-[#FAF9FD] p-3.5 rounded-xl border border-[#E4E2EB]">
              <span className="text-[10px] uppercase tracking-wider block text-[#524E5E] font-sans font-bold mb-1">Qualified Leads</span>
              <span className="text-lg font-bold text-[#6344E7]">{CAMPAIGN_WORKFLOW.mockCampaign.qualifiedLeads}</span>
            </div>
            <div className="bg-[#FAF9FD] p-3.5 rounded-xl border border-[#E4E2EB]">
              <span className="text-[10px] uppercase tracking-wider block text-[#524E5E] font-sans font-bold mb-1">Booked Demos</span>
              <span className="text-lg font-bold text-[#10B981]">{CAMPAIGN_WORKFLOW.mockCampaign.meetingsBooked}</span>
            </div>
            <div className="bg-[#FAF9FD] p-3.5 rounded-xl border border-[#E4E2EB]">
              <span className="text-[10px] uppercase tracking-wider block text-[#524E5E] font-sans font-bold mb-1">Conversion Rate</span>
              <span className="text-lg font-bold text-[#0F0E17]">{CAMPAIGN_WORKFLOW.mockCampaign.conversionRate}</span>
            </div>
          </div>

          {/* Bottom CTA */}
          <div className="pt-2">
            <button
              onClick={onGetStarted}
              className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-xs font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] active:scale-[0.98] transition-all duration-150 shadow-xs"
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
