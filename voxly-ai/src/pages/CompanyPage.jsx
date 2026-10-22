import React from 'react';
import { PageHeader } from './PageHeader';
import { Footer } from './../components/Footer';
import {
  Sparkles,
  ShieldCheck,
  Zap,
  Globe,
  Radio,
  Lock,
  Cpu,
  Users,
  Building2,
  ArrowRight,
  CheckCircle2,
} from 'lucide-react';

export function CompanyPage({ onBackToLanding, onEnterConsole, onNavigatePage }) {
  return (
    <div className="min-h-screen flex flex-col bg-[#FAF9FD] text-[#0F0E17]">
      <PageHeader
        title="About Dialtact"
        subtitle="Empowering modern enterprises with autonomous, emotionally resonant AI voice employees."
        onBackToLanding={onBackToLanding}
        onEnterConsole={onEnterConsole}
      />

      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-12 space-y-16">
        {/* Mission Statement Hero */}
        <section className="bg-white rounded-3xl p-8 sm:p-12 border border-[#E4E2EB] shadow-xs relative overflow-hidden">
          <div className="absolute top-0 right-0 w-96 h-96 bg-[#6344E7]/5 rounded-full blur-3xl pointer-events-none -mr-20 -mt-20" />
          <div className="max-w-3xl space-y-5 relative">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#6344E7]/10 text-[#6344E7] text-xs font-bold uppercase tracking-wider">
              <Sparkles className="w-3.5 h-3.5" />
              Our Mission
            </div>
            <h1 className="text-2xl sm:text-4xl font-extrabold text-[#0F0E17] tracking-tight leading-tight">
              Eliminating phone trees and hold music with intelligent, conversational AI employees.
            </h1>
            <p className="text-sm sm:text-base text-[#524E5E] leading-relaxed">
              Dialtact was founded on a simple conviction: customers should never wait on hold or fight with robotic keypad menus. We build autonomous neural voice employees that listen attentively, understand nuance, handle interruptions gracefully, and take real-world action on the first ring.
            </p>
          </div>
        </section>

        {/* Core Architectural Pillars */}
        <section className="space-y-6">
          <div className="text-center max-w-2xl mx-auto space-y-2">
            <h2 className="text-xs font-bold uppercase tracking-wider text-[#6344E7]">Engineering Principles</h2>
            <h3 className="text-2xl font-extrabold text-[#0F0E17]">Built for Real-World Conversations</h3>
            <p className="text-xs sm:text-sm text-[#524E5E]">
              Every layer of the Dialtact platform is purpose-built to deliver lightning-fast response times and unyielding enterprise reliability.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            <div className="bg-white p-6 rounded-2xl border border-[#E4E2EB] shadow-xs space-y-3">
              <div className="w-10 h-10 rounded-xl bg-purple-50 text-[#6344E7] flex items-center justify-center">
                <Zap className="w-5 h-5" />
              </div>
              <h4 className="text-sm font-bold text-[#0F0E17]">Ultra-Low Latency Voice Core</h4>
              <p className="text-xs text-[#524E5E] leading-relaxed">
                Sub-second audio streaming with bidirectional WebSocket pipelining ensures fluid, human-cadence turn taking without awkward pauses.
              </p>
            </div>

            <div className="bg-white p-6 rounded-2xl border border-[#E4E2EB] shadow-xs space-y-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
                <Radio className="w-5 h-5" />
              </div>
              <h4 className="text-sm font-bold text-[#0F0E17]">Direct Voice Telephony Trunks</h4>
              <p className="text-xs text-[#524E5E] leading-relaxed">
                Direct carrier trunks and Tier-1 voice routing across 100+ countries guarantee crystal-clear acoustics and pristine audio fidelity.
              </p>
            </div>

            <div className="bg-white p-6 rounded-2xl border border-[#E4E2EB] shadow-xs space-y-3">
              <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
                <Lock className="w-5 h-5" />
              </div>
              <h4 className="text-sm font-bold text-[#0F0E17]">Strict Tenant Data Isolation</h4>
              <p className="text-xs text-[#524E5E] leading-relaxed">
                Enterprise security with cryptographic tenant isolation, zero model training on customer data, and fail-closed cryptographic auth.
              </p>
            </div>

            <div className="bg-white p-6 rounded-2xl border border-[#E4E2EB] shadow-xs space-y-3">
              <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center">
                <Cpu className="w-5 h-5" />
              </div>
              <h4 className="text-sm font-bold text-[#0F0E17]">Contextual Business Brain</h4>
              <p className="text-xs text-[#524E5E] leading-relaxed">
                Hybrid vector retrieval (RAG) grounds every agent answer in your company policies, product specs, and dynamic scheduling availability.
              </p>
            </div>

            <div className="bg-white p-6 rounded-2xl border border-[#E4E2EB] shadow-xs space-y-3">
              <div className="w-10 h-10 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <h4 className="text-sm font-bold text-[#0F0E17]">Automated DNC &amp; Compliance</h4>
              <p className="text-xs text-[#524E5E] leading-relaxed">
                Built-in TCPA scrubbing, calling window enforcement, and real-time consent verification safeguard outbound campaigns.
              </p>
            </div>

            <div className="bg-white p-6 rounded-2xl border border-[#E4E2EB] shadow-xs space-y-3">
              <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
                <Globe className="w-5 h-5" />
              </div>
              <h4 className="text-sm font-bold text-[#0F0E17]">Global Multi-Lingual Fluency</h4>
              <p className="text-xs text-[#524E5E] leading-relaxed">
                Native voice models supporting diverse regional accents, vernacular idioms, and rapid bilingual code-switching in real time.
              </p>
            </div>
          </div>
        </section>

        {/* Global Network Overview */}
        <section className="bg-white rounded-3xl p-8 sm:p-10 border border-[#E4E2EB] shadow-xs space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-[#E4E2EB] pb-6">
            <div>
              <h3 className="text-lg font-bold text-[#0F0E17]">Global Voice Trunk Infrastructure</h3>
              <p className="text-xs text-[#524E5E] mt-0.5">
                Carrier-grade edge routing deployed across multiple availability zones.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-xs font-semibold text-emerald-700">Enterprise Carrier Network Online</span>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="p-4 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-center">
              <div className="text-2xl font-extrabold font-mono text-[#0F0E17]">99.99%</div>
              <div className="text-[11px] text-[#524E5E] font-medium mt-1">Uptime SLA</div>
            </div>
            <div className="p-4 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-center">
              <div className="text-2xl font-extrabold font-mono text-[#0F0E17]">100+</div>
              <div className="text-[11px] text-[#524E5E] font-medium mt-1">Countries Supported</div>
            </div>
            <div className="p-4 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-center">
              <div className="text-2xl font-extrabold font-mono text-[#0F0E17]">&lt; 700ms</div>
              <div className="text-[11px] text-[#524E5E] font-medium mt-1">Mean Voice Latency</div>
            </div>
            <div className="p-4 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-center">
              <div className="text-2xl font-extrabold font-mono text-[#0F0E17]">0</div>
              <div className="text-[11px] text-[#524E5E] font-medium mt-1">Data Leaks Permitted</div>
            </div>
          </div>
        </section>

        {/* Call to Action */}
        <section className="bg-gradient-to-br from-[#0F0E17] to-[#1F1D2B] rounded-3xl p-8 sm:p-12 text-white shadow-xl flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
          <div className="space-y-2 max-w-xl">
            <h3 className="text-xl sm:text-2xl font-bold tracking-tight">Deploy your first AI Voice Employee today</h3>
            <p className="text-xs sm:text-sm text-[#8C879A] leading-relaxed">
              Launch in under 10 minutes with zero code. Claim your local number or connect an existing SIP trunk.
            </p>
          </div>
          <button
            type="button"
            onClick={() => onEnterConsole?.('employees')}
            className="inline-flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl font-bold text-xs bg-white text-[#0F0E17] hover:bg-[#FAF9FD] active:scale-95 transition-all shadow-md shrink-0"
          >
            <span>Open Workspace Console</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </section>
      </main>

      <Footer onNavigatePage={onNavigatePage} />
    </div>
  );
}

export default CompanyPage;
