import React from 'react';
import { ArrowRight, Mic } from 'lucide-react';

export function FinalCTA({ onGetStarted, onTalkToMe }) {
  return (
    <section className="py-20 sm:py-28 bg-[#FAF9FD] relative overflow-hidden">
      <div className="max-w-5xl mx-auto px-6 sm:px-8">
        <div className="relative rounded-2xl bg-[#0F0E17] p-8 sm:p-14 text-center text-white border border-[#E4E2EB]/10 shadow-craft-lg">
          
          <div className="relative z-10 max-w-2xl mx-auto">
            {/* Mascot Avatar Icon */}
            <div className="w-12 h-12 rounded-xl bg-white/10 border border-white/15 mx-auto flex items-center justify-center text-white mb-6">
              <svg
                className="w-6 h-6 text-white"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="18" y1="20" x2="18" y2="10" />
                <line x1="12" y1="20" x2="12" y2="4" />
                <line x1="6" y1="20" x2="6" y2="14" />
              </svg>
            </div>

            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight leading-[1.12] mb-4 text-white">
              Build your AI employee today.
            </h2>

            <p className="text-sm sm:text-base text-[#D1CFDB] leading-relaxed mb-8 max-w-lg mx-auto">
              Give your business an AI that can talk, listen, learn and work around the clock with sub-500ms voice intelligence.
            </p>

            <div className="flex flex-wrap items-center justify-center gap-3">
              <button
                onClick={onGetStarted}
                className="inline-flex items-center justify-center gap-2 px-7 py-3.5 rounded-xl text-sm font-semibold text-[#0F0E17] bg-white hover:bg-[#FAF9FD] active:scale-[0.98] transition-all duration-150 shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6344E7]"
              >
                <span>Build Your Agent</span>
                <ArrowRight className="w-4 h-4" />
              </button>

              <button
                onClick={onTalkToMe}
                className="inline-flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl text-sm font-semibold text-white bg-white/10 hover:bg-white/15 border border-white/20 active:scale-[0.98] transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6344E7]"
              >
                <Mic className="w-4 h-4" />
                <span>Talk to AI</span>
              </button>
            </div>
          </div>

        </div>
      </div>
    </section>
  );
}
