import React, { useState } from 'react';
import {
  PhoneIncoming,
  PhoneOutgoing,
  ListPlus,
  PhoneCall,
  CheckCircle2,
  ArrowRight,
  ShieldCheck,
  Zap,
  Phone
} from 'lucide-react';
import { PHONE_CHANNELS } from '../data/siteContent';

const TAB_ICONS = {
  inbound: PhoneIncoming,
  outbound: PhoneOutgoing,
  campaigns: ListPlus,
};

export function PhoneChannelsSection({ onGetStarted }) {
  const [activeTab, setActiveTab] = useState('inbound');

  const selectedChannel = PHONE_CHANNELS.find((c) => c.id === activeTab) || PHONE_CHANNELS[0];
  const TabIcon = TAB_ICONS[selectedChannel.id] || PhoneCall;

  return (
    <section id="phone" className="py-20 sm:py-28 bg-[#FAF9FD] relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        
        {/* Section Header */}
        <div className="max-w-3xl mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-white border border-[#E4E2EB] text-[#6344E7] text-xs font-bold tracking-wider uppercase mb-4 shadow-craft-xs">
            <span>Telephony Routing</span>
          </div>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#0F0E17] tracking-tight leading-[1.12] mb-4">
            Put your AI on the phone.
          </h2>
          <p className="text-base sm:text-lg text-[#524E5E] leading-relaxed">
            From single toll-free inbound lines to high-velocity outbound follow-ups and automated bulk lists, deploy dedicated voice numbers across 100+ countries with sub-500ms carrier latency.
          </p>
        </div>

        {/* 3 Interactive Channel Segmented Control Tabs */}
        <div className="flex justify-start mb-8">
          <div className="inline-flex p-1 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB]">
            {PHONE_CHANNELS.map((ch) => {
              const Icon = TAB_ICONS[ch.id] || PhoneCall;
              const isSelected = activeTab === ch.id;
              return (
                <button
                  key={ch.id}
                  onClick={() => setActiveTab(ch.id)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all duration-150 ${
                    isSelected
                      ? 'bg-white text-[#0F0E17] shadow-craft-xs'
                      : 'text-[#524E5E] hover:text-[#0F0E17]'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{ch.title}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Active Channel Display Showcase */}
        <div className="bg-white rounded-2xl border border-[#E4E2EB] shadow-craft-md overflow-hidden">
          <div className="grid grid-cols-1 lg:grid-cols-12">
            
            {/* Left Column: Specifications & Feature Checklist */}
            <div className="lg:col-span-7 p-7 sm:p-10 flex flex-col justify-between">
              <div>
                <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-[#FAF9FD] border border-[#E4E2EB] text-[#0F0E17] text-xs font-semibold mb-4">
                  <TabIcon className="w-3.5 h-3.5 text-[#6344E7]" />
                  <span>{selectedChannel.badge}</span>
                </div>

                <h3 className="text-2xl font-bold text-[#0F0E17] mb-3">
                  {selectedChannel.headline}
                </h3>

                <p className="text-xs sm:text-sm text-[#524E5E] leading-relaxed mb-6">
                  {selectedChannel.desc}
                </p>

                {/* Bullet checklist */}
                <div className="space-y-2.5 mb-8">
                  {selectedChannel.features.map((feat, i) => (
                    <div key={i} className="flex items-center gap-2.5 text-xs font-medium text-[#0F0E17]">
                      <div className="w-4 h-4 rounded-full bg-[#EFECE6] flex items-center justify-center text-[#0F0E17] flex-shrink-0">
                        <CheckCircle2 className="w-3 h-3" />
                      </div>
                      <span>{feat}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="pt-6 border-t border-[#E4E2EB] flex flex-wrap items-center justify-between gap-4">
                <button
                  onClick={onGetStarted}
                  className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-xs font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] active:scale-[0.98] transition-all duration-150 shadow-xs"
                >
                  <span>Deploy {selectedChannel.title} Line</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
                <span className="text-xs font-mono font-semibold text-[#10B981] bg-[#10B981]/10 px-2.5 py-1 rounded border border-[#10B981]/20">
                  {selectedChannel.stat}
                </span>
              </div>
            </div>

            {/* Right Column: High-Craft Phone Simulator Enclosure */}
            <div className="lg:col-span-5 bg-[#111019] p-8 text-white flex flex-col justify-center border-t lg:border-t-0 lg:border-l border-white/10">
              <div className="max-w-xs mx-auto w-full bg-[#181724] rounded-2xl p-6 border border-white/10 shadow-craft-lg">
                
                {/* Caller Screen */}
                <div className="text-center mb-5">
                  <div className="w-12 h-12 rounded-xl bg-white/10 mx-auto flex items-center justify-center text-white text-base font-mono font-bold mb-3 border border-white/10">
                    VX
                  </div>
                  <h4 className="text-sm font-bold text-white">Voxly Voice Employee</h4>
                  <p className="text-xs text-[#10B981] font-medium flex items-center justify-center gap-1.5 mt-0.5 font-mono">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#10B981] animate-pulse" />
                    Call in Progress • 01:24
                  </p>
                </div>

                {/* Call metadata cards */}
                <div className="space-y-2 mb-5 text-xs font-mono">
                  <div className="bg-black/40 p-2.5 rounded-lg border border-white/5">
                    <span className="text-[#A19EAD] block text-[10px] uppercase">Active Caller:</span>
                    <span className="text-white font-medium">{selectedChannel.mockCaller}</span>
                  </div>
                  <div className="bg-black/40 p-2.5 rounded-lg border border-white/5">
                    <span className="text-[#A19EAD] block text-[10px] uppercase">Target Intent:</span>
                    <span className="text-[#D1CFDB] font-medium">{selectedChannel.mockGoal}</span>
                  </div>
                </div>

                {/* Audio meter */}
                <div className="flex items-center justify-center gap-1 h-6 px-3 rounded-lg bg-black/40 border border-white/5">
                  {[10, 18, 14, 22, 12, 19, 8, 20, 15, 10].map((h, i) => (
                    <span
                      key={i}
                      className="w-1 bg-[#8369F5] rounded-full"
                      style={{ height: `${h}px` }}
                    />
                  ))}
                </div>

              </div>
            </div>

          </div>
        </div>

      </div>
    </section>
  );
}
