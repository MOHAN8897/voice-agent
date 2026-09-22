import React, { useState } from 'react';
import {
  Brain,
  FileText,
  Layers,
  HelpCircle,
  ShieldCheck,
  Sparkles,
  CheckCircle2,
  ArrowRight,
  Database,
  Lock
} from 'lucide-react';

const KNOWLEDGE_PILLARS = [
  {
    id: 'instructions',
    title: 'Instructions',
    desc: 'Core operational directives, conversational boundaries, tone of voice, and custom sales scripts.',
    items: ['B2B Sales Qualification Script', 'Empathetic Customer Greeting', 'Objection Handling Playbook'],
    icon: FileText,
  },
  {
    id: 'knowledge',
    title: 'Knowledge',
    desc: 'Uploaded product manuals, service offerings, tech specs, pricing matrices, and CRM fields.',
    items: ['Enterprise_Pricing_Matrix_2026.pdf', 'Platform_Architecture_SLA.pdf', 'Product_Manual_v3.pdf'],
    icon: Layers,
  },
  {
    id: 'faqs',
    title: 'FAQs',
    desc: 'Hundreds of curated question-and-answer pairs covering common buyer questions and edge cases.',
    items: ['140 Curated Technical Q&As', 'Competitor Comparison Tables', 'Billing & Refund Rules'],
    icon: HelpCircle,
  },
  {
    id: 'policies',
    title: 'Policies',
    desc: 'Compliance guardrails, Do-Not-Call (DNC) registry rules, HIPAA/SOC2 guidelines, and refund limits.',
    items: ['Zero Hallucination Guardrails', 'TCPA & DNC Scrubbing Rules', 'Escalation Protocol for Disputes'],
    icon: ShieldCheck,
  },
  {
    id: 'personality',
    title: 'Personality',
    desc: 'Humanized conversational rhythm, natural breathing pauses, empathy inflection, and polite affirmations.',
    items: ['Consultative Pacing (145 WPM)', 'Empathetic Active Listening', 'Adaptive Humor & Politeness'],
    icon: Sparkles,
  },
];

export function TrainingSection() {
  const [activePillar, setActivePillar] = useState(0);
  const selected = KNOWLEDGE_PILLARS[activePillar];

  return (
    <section id="train" className="py-20 sm:py-28 bg-white relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        
        {/* Section Header */}
        <div className="max-w-3xl mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] text-[#6344E7] text-xs font-bold tracking-wider uppercase mb-4 shadow-craft-xs">
            <span>Knowledge Architecture</span>
          </div>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#0F0E17] tracking-tight leading-[1.12] mb-4">
            Teach it how your business works.
          </h2>
          <p className="text-base sm:text-lg text-[#524E5E] leading-relaxed">
            Give your agent the knowledge, instructions, and behavior it needs to represent your business with absolute precision and zero hallucinations.
          </p>
        </div>

        {/* Central Visual Architecture Diagram */}
        <div className="max-w-5xl mb-12">
          <div className="bg-[#FAF9FD] rounded-2xl p-6 sm:p-8 border border-[#E4E2EB] text-left">
            <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#524E5E] block mb-4">
              Ingestion Channels (Select to inspect):
            </span>

            {/* 5 Ingestion Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-6">
              {KNOWLEDGE_PILLARS.map((p, idx) => {
                const Icon = p.icon;
                const isSelected = activePillar === idx;
                return (
                  <button
                    key={p.id}
                    onClick={() => setActivePillar(idx)}
                    className={`p-4 rounded-xl border text-left transition-all duration-150 flex flex-col justify-between ${
                      isSelected
                        ? 'bg-white border-[#0F0E17] shadow-craft-sm ring-1 ring-[#0F0E17]'
                        : 'bg-white/80 hover:bg-white border-[#E4E2EB] hover:border-[#D1CFDB]'
                    }`}
                  >
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-3 ${
                      isSelected ? 'bg-[#0F0E17] text-white' : 'bg-[#FAF9FD] text-[#524E5E] border border-[#E4E2EB]'
                    }`}>
                      <Icon className="w-4 h-4" />
                    </div>
                    <div>
                      <span className="text-xs font-bold text-[#0F0E17] block mb-0.5">{p.title}</span>
                      <span className="text-[10px] text-[#524E5E] leading-tight block">{p.items.length} rule sets</span>
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Ingestion Pipeline Bar */}
            <div className="flex items-center justify-between p-4 rounded-xl bg-white border border-[#E4E2EB]">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] flex items-center justify-center text-[#0F0E17]">
                  <Database className="w-4 h-4" />
                </div>
                <div>
                  <span className="text-xs font-bold text-[#0F0E17] block">Hybrid Vector Embedding Pipeline (RAG)</span>
                  <span className="text-[11px] text-[#524E5E]">Semantic chunking + strict policy guardrails</span>
                </div>
              </div>
              <span className="text-xs font-mono font-semibold text-[#10B981] bg-[#10B981]/10 px-2.5 py-1 rounded border border-[#10B981]/20">
                100% Grounded
              </span>
            </div>
          </div>
        </div>

        {/* Interactive Ingestion Inspector */}
        <div className="max-w-5xl bg-[#111019] text-white rounded-2xl p-6 sm:p-7 border border-white/10 shadow-craft-lg">
          <div className="flex flex-wrap items-center justify-between gap-4 pb-4 mb-5 border-b border-white/10">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-white/10 border border-white/10 text-white flex items-center justify-center">
                <Brain className="w-4 h-4" />
              </div>
              <div>
                <h4 className="text-sm font-bold text-white">
                  Ingested Context: {selected.title}
                </h4>
                <p className="text-xs text-[#D1CFDB]">{selected.desc}</p>
              </div>
            </div>
            <span className="text-[11px] font-mono font-semibold px-2.5 py-1 rounded bg-white/10 text-[#10B981] border border-white/15 flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5" /> Strict RAG Enabled
            </span>
          </div>

          <div className="space-y-2.5">
            <span className="text-[10px] font-mono font-bold text-[#A19EAD] uppercase tracking-wider block">
              Active Documents & Verification Rules:
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 font-mono">
              {selected.items.map((item, i) => (
                <div key={i} className="bg-black/30 p-3 rounded-xl border border-white/5 flex items-center gap-2.5">
                  <FileText className="w-3.5 h-3.5 text-[#A19EAD] shrink-0" />
                  <span className="text-xs text-[#FAF9FD] truncate">{item}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

      </div>
    </section>
  );
}
