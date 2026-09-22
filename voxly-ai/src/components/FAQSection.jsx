import React, { useState } from 'react';
import { SectionHeading } from './SectionHeading';
import { FAQS } from '../data/siteContent';
import { ChevronDown } from 'lucide-react';

export function FAQSection() {
  const [openIndex, setOpenIndex] = useState(0);

  const toggle = (i) => {
    setOpenIndex(openIndex === i ? -1 : i);
  };

  return (
    <section id="faq" className="py-20 sm:py-28 bg-white relative overflow-hidden">
      <div className="max-w-4xl mx-auto px-6 sm:px-8">
        <SectionHeading
          badge="Documentation & FAQ"
          title="Everything You Need to"
          highlight="Know About Voxly"
          subtitle="Answers to common technical, telephony, compliance, and deployment questions."
        />

        <div className="space-y-3">
          {FAQS.map((faq, idx) => {
            const isOpen = openIndex === idx;
            return (
              <div
                key={idx}
                className={`rounded-xl border transition-all duration-150 overflow-hidden ${
                  isOpen
                    ? 'bg-[#FAF9FD] border-[#0F0E17] shadow-craft-xs'
                    : 'bg-white border-[#E4E2EB] hover:border-[#D1CFDB]'
                }`}
              >
                <button
                  onClick={() => toggle(idx)}
                  className="w-full p-4 sm:p-5 text-left flex items-center justify-between gap-4"
                  aria-expanded={isOpen}
                >
                  <span className="text-sm sm:text-base font-bold text-[#0F0E17]">
                    {faq.q}
                  </span>
                  <div className={`w-7 h-7 rounded-lg border border-[#E4E2EB] flex items-center justify-center text-[#524E5E] shrink-0 transition-transform duration-200 ${
                    isOpen ? 'rotate-180 bg-[#0F0E17] text-white border-[#0F0E17]' : 'bg-[#FAF9FD]'
                  }`}>
                    <ChevronDown className="w-3.5 h-3.5" />
                  </div>
                </button>

                {isOpen && (
                  <div className="px-4 sm:px-5 pb-5 text-xs sm:text-sm text-[#524E5E] leading-relaxed">
                    <p className="pt-2.5 border-t border-[#E4E2EB]">
                      {faq.a}
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
