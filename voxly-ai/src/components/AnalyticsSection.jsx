import React, { useState } from 'react';
import {
  BarChart3,
  TrendingUp,
  Clock,
  CheckCircle2,
  Filter,
  Calendar
} from 'lucide-react';
import { PERFORMANCE_STATS } from '../data/siteContent';

export function AnalyticsSection() {
  const [activeChartTab, setActiveChartTab] = useState('calls');

  return (
    <section id="analytics" className="py-20 sm:py-28 bg-[#FAF9FD] relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        
        {/* Section Header */}
        <div className="max-w-3xl mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-white border border-[#E4E2EB] text-[#6344E7] text-xs font-bold tracking-wider uppercase mb-4 shadow-craft-xs">
            <span>Fleet Telemetry</span>
          </div>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#0F0E17] tracking-tight leading-[1.12] mb-4">
            Your AI gets better when you can see everything.
          </h2>
          <p className="text-base sm:text-lg text-[#524E5E] leading-relaxed">
            {PERFORMANCE_STATS.subtitle}
          </p>
        </div>

        {/* Large Top Dashboard Mockup Card */}
        <div className="max-w-5xl bg-white rounded-2xl border border-[#E4E2EB] shadow-craft-md p-6 sm:p-8 mb-10">
          
          {/* 4 Primary Top Metrics Grid */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 pb-6 border-b border-[#E4E2EB] mb-6 font-mono">
            {PERFORMANCE_STATS.metrics.map((m) => (
              <div key={m.label} className="bg-[#FAF9FD] p-4 rounded-xl border border-[#E4E2EB]">
                <span className="text-[10px] font-sans font-bold text-[#524E5E] uppercase tracking-wider block mb-1">
                  {m.label}
                </span>
                <div className="text-2xl sm:text-3xl font-bold text-[#0F0E17] mb-1 tracking-tight">
                  {m.value}
                </div>
                <span className="text-[11px] font-semibold text-[#10B981] flex items-center gap-1 font-mono">
                  <TrendingUp className="w-3.5 h-3.5" /> {m.change}
                </span>
              </div>
            ))}
          </div>

          {/* Interactive Chart View Segmented Control */}
          <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
            <div className="inline-flex p-1 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB]">
              {[
                { id: 'calls', label: 'Calls over time' },
                { id: 'outcomes', label: 'Outcomes' },
                { id: 'funnel', label: 'Conversion funnel' },
                { id: 'hours', label: 'Business hours' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveChartTab(tab.id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    activeChartTab === tab.id
                      ? 'bg-white text-[#0F0E17] shadow-craft-xs'
                      : 'text-[#524E5E] hover:text-[#0F0E17]'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <span className="text-xs font-mono text-[#524E5E]">
              Telemetry updated 3s ago
            </span>
          </div>

          {/* Chart 1: Calls Over Time */}
          {activeChartTab === 'calls' && (
            <div className="space-y-4">
              <div className="h-56 flex items-end justify-between gap-4 sm:gap-8 pt-4 pb-2 border-b border-[#E4E2EB]">
                {PERFORMANCE_STATS.charts.callsOverTime.map((item) => {
                  const heightCalls = (item.calls / 13000) * 100;
                  const heightResolved = (item.resolved / 13000) * 100;
                  return (
                    <div key={item.month} className="flex-1 flex flex-col items-center gap-2 h-full justify-end">
                      <div className="w-full max-w-[40px] flex items-end justify-center gap-1.5 h-full">
                        <div
                          className="w-1/2 bg-[#0F0E17] rounded-t-sm transition-all"
                          style={{ height: `${heightCalls}%` }}
                          title={`Total Calls: ${item.calls}`}
                        />
                        <div
                          className="w-1/2 bg-[#10B981] rounded-t-sm transition-all"
                          style={{ height: `${heightResolved}%` }}
                          title={`Resolved: ${item.resolved}`}
                        />
                      </div>
                      <span className="text-xs font-mono text-[#524E5E]">{item.month}</span>
                    </div>
                  );
                })}
              </div>
              <div className="flex flex-wrap items-center justify-center gap-6 text-xs font-medium pt-2">
                <span className="flex items-center gap-2 text-[#0F0E17]">
                  <span className="w-2.5 h-2.5 rounded-xs bg-[#0F0E17]" /> Total Calls Placed & Received
                </span>
                <span className="flex items-center gap-2 text-[#10B981]">
                  <span className="w-2.5 h-2.5 rounded-xs bg-[#10B981]" /> Resolved Autonomously (82%)
                </span>
              </div>
            </div>
          )}

          {/* Chart 2: Outcomes */}
          {activeChartTab === 'outcomes' && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 py-4">
              {PERFORMANCE_STATS.charts.outcomes.map((out) => (
                <div key={out.label} className="bg-[#FAF9FD] p-5 rounded-xl border border-[#E4E2EB] text-center">
                  <div
                    className="w-16 h-16 rounded-full mx-auto flex items-center justify-center text-xl font-mono font-bold text-white mb-3"
                    style={{ backgroundColor: out.label.includes('Resolved') ? '#10B981' : out.label.includes('Transfer') ? '#6344E7' : '#524E5E' }}
                  >
                    {out.pct}%
                  </div>
                  <h4 className="text-xs font-bold text-[#0F0E17] mb-1">{out.label}</h4>
                  <p className="text-[11px] text-[#524E5E]">Automatic disposition categorization</p>
                </div>
              ))}
            </div>
          )}

          {/* Chart 3: Conversion Funnel */}
          {activeChartTab === 'funnel' && (
            <div className="space-y-3 py-4 max-w-xl mx-auto font-mono">
              {PERFORMANCE_STATS.charts.funnel.map((fn, idx) => (
                <div key={fn.stage} className="space-y-1">
                  <div className="flex justify-between text-xs font-semibold">
                    <span className="text-[#0F0E17] font-sans">{fn.stage}</span>
                    <span className="text-[#0F0E17]">{fn.count.toLocaleString()} ({fn.pct})</span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-[#F0EEF6] overflow-hidden">
                    <div
                      className="h-full bg-[#0F0E17] rounded-full transition-all"
                      style={{ width: `${100 - idx * 21}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Chart 4: Business Hours */}
          {activeChartTab === 'hours' && (
            <div className="py-4 text-center space-y-4">
              <span className="text-xs font-bold text-[#524E5E] uppercase tracking-wider block font-mono">
                Call Volume Distribution by Hour (24/7 Enterprise Availability)
              </span>
              <div className="grid grid-cols-6 sm:grid-cols-12 gap-1.5 max-w-3xl mx-auto">
                {[
                  { h: '12am', load: 15 }, { h: '2am', load: 10 }, { h: '4am', load: 12 },
                  { h: '6am', load: 25 }, { h: '8am', load: 68 }, { h: '9am', load: 95 },
                  { h: '11am', load: 98 }, { h: '1pm', load: 88 }, { h: '3pm', load: 92 },
                  { h: '5pm', load: 74 }, { h: '7pm', load: 45 }, { h: '10pm', load: 22 },
                ].map((slot) => (
                  <div key={slot.h} className="bg-[#FAF9FD] p-2 rounded-lg border border-[#E4E2EB] text-center">
                    <div
                      className="w-full rounded-sm bg-[#0F0E17] transition-all mb-1 mx-auto"
                      style={{ height: `${Math.max(12, (slot.load / 100) * 44)}px` }}
                    />
                    <span className="text-[10px] font-mono font-medium text-[#524E5E] block">{slot.h}</span>
                  </div>
                ))}
              </div>
              <p className="text-xs text-[#524E5E]">
                Zero hold times guaranteed even during peak traffic windows.
              </p>
            </div>
          )}

        </div>

      </div>
    </section>
  );
}
