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
  ArrowRight,
  Cpu,
  Volume2,
  Play,
  Check,
  ShieldCheck
} from 'lucide-react';
import { AI_EMPLOYEE_CAPABILITIES, BUILD_AI_EMPLOYEE_STEPS } from '../data/siteContent';

const ICONS = {
  PhoneIncoming,
  PhoneOutgoing,
  Sparkles,
  CheckCircle2,
  Calendar,
  RotateCcw,
  HelpCircle,
  UserCheck,
};

export function AiEmployeeSection({ onGetStarted }) {
  const [activeStep, setActiveStep] = useState(0);
  const [selectedCapability, setSelectedCapability] = useState(0);

  const stepPreviews = [
    {
      title: "Senior Inbound Lead Specialist",
      role: "Lead Qualification Specialist",
      instructions: "Greet caller within 300ms, identify company size, qualify budget >$25k, and schedule discovery demo with account executive.",
      voice: "Elena Smooth (Neural 48kHz, 310ms latency)",
      knowledge: ["Acme_Product_Catalog_2026.pdf", "Pricing_Matrix_Enterprise.xlsx", "FAQ_Knowledge_Base.url"],
      tools: ["Salesforce CRM Sync", "Google Calendar Booking", "Slack Alert #leads"],
      status: "Role Configured",
    },
    {
      title: "Instruction & Tone Engineering",
      role: "Empathetic, consultative, decisive",
      instructions: "Never talk over caller. Acknowledge objections with 'I understand that timeline is tight...' before presenting enterprise SLA.",
      voice: "Elena Smooth (Pacing 148 wpm)",
      knowledge: ["Objection_Playbook_v4.pdf", "Competitive_Battlecard.pdf"],
      tools: ["Webhook Telemetry", "Real-Time Sentiment Scoring"],
      status: "Prompts Synthesized",
    },
    {
      title: "Voice & Accent Selection",
      role: "40+ Neural High-Fidelity Voices",
      instructions: "Accent: Neutral North American • Cadence: Natural conversational with breathing & micro-pauses active.",
      voice: "Elena Smooth (Studio Quality • 48kHz)",
      knowledge: ["Pronunciation_Glossary_Tech.json"],
      tools: ["Opus Codec Direct Audio Stream"],
      status: "Acoustics Tuned",
    },
    {
      title: "Enterprise Knowledge Grounding",
      role: "Strict RAG • Zero Hallucination Policy",
      instructions: "Answer strictly based on ingested knowledge documents. If pricing tier is unlisted, trigger warm callback dispatch.",
      voice: "Elena Smooth",
      knowledge: ["Enterprise_SLA_Terms.pdf", "Security_Compliance_SOC2.pdf", "Product_API_v3_Docs.url"],
      tools: ["Hybrid Vector Retrieval (Sub-50ms)"],
      status: "3,420 Pages Ingested",
    },
    {
      title: "Tool Connectors & API Webhooks",
      role: "Real-Time Bidirectional Data Sync",
      instructions: "POST https://api.yourcompany.com/lead-qualified on call disposition with extracted JSON payload.",
      voice: "Elena Smooth",
      knowledge: ["HubSpot 2-Way Sync", "Twilio SIP Trunk", "PostgreSQL Database"],
      tools: ["Sub-50ms Webhook Execution"],
      status: "All Webhooks Active",
    },
    {
      title: "Live Production Deployment",
      role: "Phone Line +1 (800) 529-VOXLY",
      instructions: "Concurrent line scaling ready for up to 100,000 parallel calls with 99.99% carrier availability SLA.",
      voice: "Elena Smooth (Active Live)",
      knowledge: ["Carrier SIP Direct Route"],
      tools: ["Live Telemetry Monitor"],
      status: "Live & Taking Calls",
    },
  ];

  const currentPreview = stepPreviews[activeStep];
  const activeCap = AI_EMPLOYEE_CAPABILITIES[selectedCapability];
  const ActiveCapIcon = ICONS[activeCap.icon] || CheckCircle2;

  return (
    <section id="capabilities" className="py-20 sm:py-28 bg-[#FAF9FD] relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        
        {/* ================================================================= */}
        {/* PART 1: What Can Your AI Employee Do? — Asymmetric Workbench */}
        {/* ================================================================= */}
        <div className="max-w-3xl mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-white border border-[#E4E2EB] text-[#6344E7] text-xs font-bold tracking-wider uppercase mb-4 shadow-craft-xs">
            <span>Capabilities Matrix</span>
          </div>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#0F0E17] tracking-tight leading-[1.12] mb-4">
            More than a voice bot.{' '}
            <span className="block text-[#0F0E17]">Your AI employee.</span>
          </h2>
          <p className="text-base sm:text-lg text-[#524E5E] leading-relaxed">
            Voxly doesn't read static scripts. It evaluates intent, checks live team availability, handles objections, and completes multi-step business transactions directly over the phone.
          </p>
        </div>

        {/* Asymmetric Workbench Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 mb-28 items-stretch">
          
          {/* Left Column: 8 Selectable Capabilities Grid */}
          <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            {AI_EMPLOYEE_CAPABILITIES.map((cap, idx) => {
              const IconComponent = ICONS[cap.icon] || CheckCircle2;
              const isSelected = selectedCapability === idx;

              return (
                <div
                  key={cap.id}
                  onClick={() => setSelectedCapability(idx)}
                  className={`p-5 rounded-xl transition-all duration-150 cursor-pointer border text-left flex flex-col justify-between ${
                    isSelected
                      ? 'bg-white border-[#0F0E17] shadow-craft-sm ring-1 ring-[#0F0E17]'
                      : 'bg-white/80 hover:bg-white border-[#E4E2EB] hover:border-[#D1CFDB] shadow-craft-xs'
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${
                        isSelected ? 'bg-[#0F0E17] text-white' : 'bg-[#FAF9FD] text-[#524E5E] border border-[#E4E2EB]'
                      }`}>
                        <IconComponent className="w-4 h-4" />
                      </div>
                      <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded bg-[#FAF9FD] border border-[#E4E2EB] text-[#524E5E]">
                        {cap.badge}
                      </span>
                    </div>

                    <h3 className="text-sm font-bold text-[#0F0E17] mb-1.5">
                      {cap.title}
                    </h3>
                    <p className="text-xs text-[#524E5E] leading-relaxed">
                      {cap.desc}
                    </p>
                  </div>

                  <div className="pt-3 mt-3 border-t border-[#E4E2EB] flex items-center justify-between text-[11px] font-medium text-[#6344E7]">
                    <span>{cap.highlight}</span>
                    {isSelected && <span className="text-xs text-[#0F0E17]">Active preview →</span>}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Right Column: Live Operational Telemetry Console */}
          <div className="lg:col-span-5 bg-[#111019] text-white rounded-2xl p-6 sm:p-7 border border-white/10 shadow-craft-lg flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-4 mb-5 border-b border-white/10">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#10B981]" />
                  <span className="text-xs font-mono text-[#D1CFDB]">telemetry / live-execution</span>
                </div>
                <span className="text-[11px] font-mono text-[#10B981] bg-[#10B981]/10 px-2 py-0.5 rounded border border-[#10B981]/20">
                  Sub-350ms Latency
                </span>
              </div>

              {/* Active Capability Summary Card */}
              <div className="bg-white/5 rounded-xl p-4 border border-white/10 mb-4">
                <div className="flex items-center gap-3 mb-2">
                  <div className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center text-white">
                    <ActiveCapIcon className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-white">
                      {activeCap.title}
                    </h4>
                    <p className="text-[11px] text-[#D1CFDB]">
                      Standard Operational Protocol • Ready
                    </p>
                  </div>
                </div>
                <p className="text-xs text-[#D1CFDB] leading-relaxed mt-2 pt-2 border-t border-white/10">
                  {activeCap.desc}
                </p>
              </div>

              {/* Real-time Field Extractions */}
              <div className="space-y-2 text-xs font-mono">
                <div className="text-[11px] uppercase tracking-wider text-[#A19EAD] font-sans font-bold">
                  Simulated Output Stream:
                </div>
                <div className="bg-black/40 rounded-lg p-3 border border-white/5 space-y-1.5 text-[11px]">
                  <div className="flex justify-between text-[#D1CFDB]">
                    <span className="text-[#A19EAD]">Status:</span>
                    <span className="text-[#10B981]">200 OK (Instant Response)</span>
                  </div>
                  <div className="flex justify-between text-[#D1CFDB]">
                    <span className="text-[#A19EAD]">Speech Cadence:</span>
                    <span>148 wpm (Human Natural)</span>
                  </div>
                  <div className="flex justify-between text-[#D1CFDB]">
                    <span className="text-[#A19EAD]">Action Triggered:</span>
                    <span className="text-[#8369F5] font-semibold">{activeCap.highlight}</span>
                  </div>
                  <div className="flex justify-between text-[#D1CFDB]">
                    <span className="text-[#A19EAD]">CRM Synchronization:</span>
                    <span>Direct Webhook Emitted</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="pt-6 mt-6 border-t border-white/10 flex items-center justify-between text-xs text-[#D1CFDB]">
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-[#10B981]" />
                Zero Hallucination Guaranteed
              </span>
              <button
                onClick={onGetStarted}
                className="text-white hover:text-[#8369F5] font-semibold text-xs transition-colors"
              >
                Deploy Capability →
              </button>
            </div>
          </div>

        </div>

        {/* ================================================================= */}
        {/* PART 2: Build Your AI Employee in Minutes */}
        {/* ================================================================= */}
        <div id="build" className="pt-12 border-t border-[#E4E2EB]">
          <div className="max-w-3xl mb-12 sm:mb-16">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-white border border-[#E4E2EB] text-[#6344E7] text-xs font-bold tracking-wider uppercase mb-4 shadow-craft-xs">
              <span>Studio Blueprint</span>
            </div>
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#0F0E17] tracking-tight leading-[1.12] mb-4">
              Create an AI employee in minutes.
            </h2>
            <p className="text-base sm:text-lg text-[#524E5E] leading-relaxed">
              Configure persona parameters, upload business documentation, connect telephony trunks, and begin handling calls without writing a single line of backend code.
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            
            {/* LEFT COLUMN: Agent Studio Console Preview */}
            <div className="lg:col-span-6 bg-[#111019] text-white rounded-2xl p-6 sm:p-7 border border-white/10 shadow-craft-lg">
              {/* Header */}
              <div className="flex items-center justify-between pb-4 mb-5 border-b border-white/10">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-white/20" />
                  <span className="w-2.5 h-2.5 rounded-full bg-white/20" />
                  <span className="w-2.5 h-2.5 rounded-full bg-white/20" />
                  <span className="text-xs font-mono text-[#A19EAD] ml-2">voxly-builder / v3.2</span>
                </div>
                <span className="text-[11px] font-mono text-[#10B981] bg-[#10B981]/10 px-2 py-0.5 rounded border border-[#10B981]/20">
                  {currentPreview.status}
                </span>
              </div>

              {/* Agent Overview */}
              <div className="bg-white/5 rounded-xl p-5 border border-white/10 space-y-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <h4 className="text-base font-bold text-white">
                      {currentPreview.title}
                    </h4>
                    <p className="text-xs text-[#D1CFDB]">
                      {currentPreview.role}
                    </p>
                  </div>
                  <span className="px-2.5 py-1 rounded-md text-[10px] font-mono font-bold bg-white/10 text-white border border-white/10">
                    Step {activeStep + 1} of 6
                  </span>
                </div>

                <div className="pt-3 border-t border-white/10 space-y-3 text-xs">
                  <div>
                    <span className="text-[#A19EAD] block text-[10px] uppercase font-bold tracking-wider mb-1">
                      Current Prompt & Directives:
                    </span>
                    <p className="font-mono text-[#FAF9FD] bg-black/40 p-3 rounded-lg border border-white/5 leading-relaxed text-xs">
                      "{currentPreview.instructions}"
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-3 pt-1">
                    <div className="bg-black/30 p-2.5 rounded-lg border border-white/5">
                      <span className="text-[#A19EAD] text-[10px] uppercase font-bold block mb-1">Acoustic Model:</span>
                      <span className="text-white font-semibold text-xs flex items-center gap-1.5">
                        <Volume2 className="w-3.5 h-3.5 text-[#8369F5]" />
                        {currentPreview.voice}
                      </span>
                    </div>
                    <div className="bg-black/30 p-2.5 rounded-lg border border-white/5">
                      <span className="text-[#A19EAD] text-[10px] uppercase font-bold block mb-1">Response Speed:</span>
                      <span className="text-[#10B981] font-semibold text-xs flex items-center gap-1.5">
                        <Cpu className="w-3.5 h-3.5" />
                        Sub-350ms Round-Trip
                      </span>
                    </div>
                  </div>

                  {/* Context chips */}
                  <div className="pt-2">
                    <span className="text-[#A19EAD] text-[10px] uppercase font-bold block mb-1.5">Active Context & Connectors:</span>
                    <div className="flex flex-wrap gap-1.5">
                      {currentPreview.knowledge.map((item, i) => (
                        <span key={i} className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/10 text-white/90 border border-white/5">
                          {item}
                        </span>
                      ))}
                      {currentPreview.tools.map((tool, i) => (
                        <span key={i} className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#6344E7]/30 text-white border border-[#6344E7]/50">
                          {tool}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* Physical audio waveform indicator */}
              <div className="mt-4 flex items-center justify-between px-4 py-3 rounded-xl bg-white/5 border border-white/10">
                <div className="flex items-center gap-2 text-xs font-semibold text-white/80">
                  <span className="w-2 h-2 rounded-full bg-[#10B981] animate-pulse" />
                  <span>Real-Time Synthesizer Output</span>
                </div>
                <div className="flex items-center gap-1">
                  {[12, 22, 10, 28, 16, 24, 11, 20, 30, 14, 20, 10].map((h, i) => (
                    <span
                      key={i}
                      className="w-1 bg-[#6344E7] rounded-full"
                      style={{ height: `${h}px` }}
                    />
                  ))}
                </div>
              </div>
            </div>

            {/* RIGHT COLUMN: 6 Step Roadmap & Single CTA */}
            <div className="lg:col-span-6 space-y-3">
              {BUILD_AI_EMPLOYEE_STEPS.map((stepItem, idx) => {
                const isActive = activeStep === idx;
                return (
                  <div
                    key={stepItem.step}
                    onClick={() => setActiveStep(idx)}
                    className={`p-4 rounded-xl cursor-pointer transition-all duration-150 border flex items-start gap-4 ${
                      isActive
                        ? 'bg-white border-[#0F0E17] shadow-craft-sm ring-1 ring-[#0F0E17]'
                        : 'bg-white/80 hover:bg-white border-[#E4E2EB] hover:border-[#D1CFDB]'
                    }`}
                  >
                    <div
                      className={`w-9 h-9 rounded-lg flex-shrink-0 flex items-center justify-center font-bold text-xs transition-colors ${
                        isActive
                          ? 'bg-[#0F0E17] text-white'
                          : 'bg-[#FAF9FD] text-[#524E5E] border border-[#E4E2EB]'
                      }`}
                    >
                      {stepItem.step}
                    </div>

                    <div className="flex-1">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <h4 className={`text-sm font-bold transition-colors ${isActive ? 'text-[#0F0E17]' : 'text-[#524E5E]'}`}>
                          {stepItem.title}
                        </h4>
                        <span className="text-[10px] font-semibold text-[#524E5E] bg-[#FAF9FD] border border-[#E4E2EB] px-2 py-0.5 rounded">
                          {stepItem.tag}
                        </span>
                      </div>
                      <p className="text-xs text-[#524E5E] leading-relaxed">
                        {stepItem.desc}
                      </p>
                    </div>
                  </div>
                );
              })}

              {/* Standard Primary CTA */}
              <div className="pt-4">
                <button
                  onClick={onGetStarted}
                  className="inline-flex items-center justify-center gap-2 px-7 py-3.5 rounded-xl text-sm font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] active:scale-[0.98] shadow-sm transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6344E7]"
                >
                  <span>Build Your Agent</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>

          </div>
        </div>

      </div>
    </section>
  );
}
