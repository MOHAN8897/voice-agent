import React, { useState } from 'react';
import {
  MessageSquare,
  CheckCircle2,
  Clock,
  Filter,
  User,
  Bot
} from 'lucide-react';
import { CONVERSATIONS_DATA } from '../data/siteContent';

export function ConversationHistorySection() {
  const [selectedFilter, setSelectedFilter] = useState('All');
  const [activeCallId, setActiveCallId] = useState('#2841');

  const filteredCalls = CONVERSATIONS_DATA.recentCalls.filter((c) => {
    if (selectedFilter === 'All') return true;
    return c.sentiment === selectedFilter;
  });

  return (
    <section id="conversations" className="py-20 sm:py-28 bg-white relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        
        {/* Section Header */}
        <div className="max-w-3xl mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] text-[#6344E7] text-xs font-bold tracking-wider uppercase mb-4 shadow-craft-xs">
            <span>Audit & Transcripts</span>
          </div>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#0F0E17] tracking-tight leading-[1.12] mb-4">
            Every conversation, in one place.
          </h2>
          <p className="text-base sm:text-lg text-[#524E5E] leading-relaxed">
            {CONVERSATIONS_DATA.subheadline} Full audio recordings, synchronized transcripts, detected intent, and verified business outcomes.
          </p>
        </div>

        {/* Filters Bar: All, Positive, Neutral, Negative */}
        <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono font-bold text-[#524E5E] uppercase tracking-wider mr-1 flex items-center gap-1.5">
              <Filter className="w-3.5 h-3.5" /> Sentiment:
            </span>
            <div className="inline-flex p-1 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB]">
              {CONVERSATIONS_DATA.filters.map((flt) => {
                const isSelected = selectedFilter === flt;
                return (
                  <button
                    key={flt}
                    onClick={() => setSelectedFilter(flt)}
                    className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                      isSelected
                        ? 'bg-white text-[#0F0E17] shadow-craft-xs'
                        : 'text-[#524E5E] hover:text-[#0F0E17]'
                    }`}
                  >
                    {flt}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="text-xs font-mono text-[#524E5E]">
            Showing {filteredCalls.length} of {CONVERSATIONS_DATA.recentCalls.length} Telephony Records
          </div>
        </div>

        {/* 2-Column Dashboard View */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          
          {/* LEFT COLUMN: Call History List */}
          <div className="lg:col-span-5 space-y-2.5">
            <div className="bg-[#FAF9FD] p-4 rounded-2xl border border-[#E4E2EB] space-y-2">
              <span className="text-[10px] font-mono font-bold text-[#524E5E] uppercase tracking-wider block mb-2">
                Recent Call Logs (Auto-Logged)
              </span>

              {filteredCalls.map((call) => {
                const isActive = activeCallId === call.id;
                return (
                  <div
                    key={call.id}
                    onClick={() => setActiveCallId(call.id)}
                    className={`p-3.5 rounded-xl cursor-pointer border transition-all ${
                      isActive
                        ? 'bg-white border-[#0F0E17] shadow-craft-sm ring-1 ring-[#0F0E17]'
                        : 'bg-white/70 hover:bg-white border-[#E4E2EB]'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-mono font-bold text-[#0F0E17]">{call.id}</span>
                      <span className={`text-[10px] font-mono font-semibold px-2 py-0.5 rounded ${
                        call.sentiment === 'Positive'
                          ? 'bg-[#10B981]/10 text-[#10B981] border border-[#10B981]/20'
                          : call.sentiment === 'Neutral'
                          ? 'bg-[#FAF9FD] text-[#524E5E] border border-[#E4E2EB]'
                          : 'bg-red-50 text-red-600 border border-red-200'
                      }`}>
                        {call.sentiment}
                      </span>
                    </div>

                    <h4 className="text-xs font-bold text-[#0F0E17]">{call.caller}</h4>
                    <p className="text-[11px] text-[#524E5E]">{call.company}</p>

                    <div className="flex items-center justify-between mt-2.5 pt-2 border-t border-[#E4E2EB] text-[11px] font-mono text-[#524E5E]">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" /> {call.duration}
                      </span>
                      <span className="font-semibold text-[#0F0E17]">{call.outcome}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* RIGHT COLUMN: Full Call Detail & Transcript with Verified Checklist */}
          <div className="lg:col-span-7">
            <div className="bg-[#111019] text-white rounded-2xl p-6 sm:p-7 border border-white/10 shadow-craft-lg space-y-5">
              
              {/* Call Header */}
              <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-white/10 font-mono">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-bold px-2 py-0.5 rounded bg-white text-[#0F0E17]">
                      {CONVERSATIONS_DATA.callNumber}
                    </span>
                    <span className="text-xs text-[#D1CFDB]">Duration: {CONVERSATIONS_DATA.duration}</span>
                  </div>
                  <h4 className="text-sm font-sans font-bold text-white">{CONVERSATIONS_DATA.caller}</h4>
                  <p className="text-xs text-[#D1CFDB] font-sans">Handling Agent: {CONVERSATIONS_DATA.agent}</p>
                </div>

                <span className="px-2.5 py-1 rounded text-xs font-semibold bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30">
                  ● Sentiment: {CONVERSATIONS_DATA.sentiment}
                </span>
              </div>

              {/* Transcript Chat Bubbles */}
              <div className="space-y-3 max-h-[320px] overflow-y-auto pr-1">
                {CONVERSATIONS_DATA.transcript.map((msg, i) => {
                  const isCustomer = msg.speaker === 'Customer';
                  return (
                    <div
                      key={i}
                      className={`flex gap-3 text-xs leading-relaxed ${
                        isCustomer ? 'justify-start' : 'justify-end'
                      }`}
                    >
                      <div
                        className={`max-w-[85%] p-3.5 rounded-xl ${
                          isCustomer
                            ? 'bg-white/10 text-white/90 rounded-tl-xs'
                            : 'bg-[#6344E7] text-white rounded-tr-xs shadow-xs'
                        }`}
                      >
                        <span className="text-[10px] font-mono uppercase font-bold text-[#D1CFDB] block mb-1">
                          {msg.speaker}
                        </span>
                        <p>{msg.text}</p>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Verified Outcome Checklist */}
              <div className="pt-4 border-t border-white/10 space-y-2">
                <span className="text-[10px] font-mono font-bold text-[#A19EAD] uppercase tracking-wider block mb-1">
                  Automated Dispositions:
                </span>
                {CONVERSATIONS_DATA.outcomes.map((out, i) => (
                  <div key={i} className="flex items-center gap-2.5 text-xs">
                    <CheckCircle2 className="w-3.5 h-3.5 text-[#10B981] flex-shrink-0" />
                    <span className="font-semibold text-white">{out.label}:</span>
                    <span className="text-[#D1CFDB] font-mono text-[11px]">{out.status}</span>
                  </div>
                ))}
              </div>

            </div>
          </div>

        </div>

      </div>
    </section>
  );
}
