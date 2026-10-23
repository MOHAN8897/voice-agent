import React from 'react';
import { PageHeader } from './PageHeader';
import { Footer } from '../components/Footer';
import { Shield, Lock, FileText, CheckCircle2 } from 'lucide-react';

export function PrivacyPage({ onBackToLanding, onEnterConsole, onNavigatePage, onSignIn }) {
  return (
    <div className="min-h-screen flex flex-col bg-[#FAF9FD] text-[#0F0E17]">
      <PageHeader
        title="Privacy Policy"
        onBackToLanding={onBackToLanding}
        onEnterConsole={onEnterConsole}
        onSignIn={onSignIn}
      />

      <main className="flex-1 max-w-4xl mx-auto px-6 sm:px-8 py-12 sm:py-16">
        <div className="bg-white rounded-2xl border border-[#E4E2EB] shadow-xs p-8 sm:p-12 space-y-8">
          <div className="border-b border-[#E4E2EB] pb-6">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#FAF9FD] border border-[#E4E2EB] text-xs font-semibold text-[#6344E7] mb-3">
              <Shield className="w-3.5 h-3.5" />
              <span>Security &amp; Privacy Compliance</span>
            </div>
            <h1 className="text-3xl sm:text-4xl font-extrabold text-[#0F0E17] tracking-tight">
              Dialtact Privacy Policy
            </h1>
            <p className="text-xs text-[#524E5E] mt-2">
              Last Updated: October 2026 • Effective Date: January 1, 2026
            </p>
          </div>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              1. Scope &amp; Telephony Voice Data Processing
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              Dialtact Inc. ("Dialtact", "we", "us") provides autonomous AI voice employee infrastructure. This Privacy Policy details how we collect, process, transcribe, and secure audio streams, synthetic voice models, caller telemetry, and account data transmitted across our web services and telephone networks.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              2. Voice Recording, Transcription &amp; Consent Disclosures
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              Inbound and outbound telephone calls processed through Dialtact are digitized and transcribed in real-time. Customers deploying Dialtact agents are contractually responsible for providing two-party consent disclosures ("This call is monitored or recorded by an automated voice assistant") in compliance with applicable federal, state, and international telecommunication laws.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              3. Voice Encryption &amp; Telephony Protocols
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              Real-time RTP voice media is transmitted over Secure Real-Time Transport Protocol (SRTP) with AES-128 or AES-256 encryption. Web and API communications are strictly mandated under TLS 1.3. Call audio recordings are encrypted at rest using AES-256 keys managed in secure Hardware Security Modules (HSM).
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              4. Tenant Isolation &amp; Zero Model Training on Customer Audio
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              Dialtact does not sell, license, or use your proprietary voice recordings, customer caller transcripts, or business knowledge base materials to train foundational public LLMs. All workspace data is strictly partitioned using multi-tenant database isolations enforced at the application and database kernel layers.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              5. Data Retention &amp; Deletion
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              Subscribers retain full ownership and discretion over recording retention timelines. You may delete call logs, transcripts, and voice cache snapshots at any time via your workspace console or automated REST endpoints. Workspace deletion initiates a 14-day quarantine grace period followed by hard cryptographic purging.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              6. Privacy Rights &amp; Contact
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              For questions regarding our privacy architecture or to exercise GDPR / CCPA data subject rights, contact our Data Privacy Office directly at{' '}
              <a href="mailto:privacy@dialtact.com" className="font-semibold text-[#6344E7] hover:underline">
                privacy@dialtact.com
              </a>{' '}
              or submit a ticket via our{' '}
              <a href="#contact" onClick={(e) => { e.preventDefault(); onNavigatePage?.('contact'); }} className="font-semibold text-[#6344E7] hover:underline">
                Customer Support Desk
              </a>.
            </p>
          </section>
        </div>
      </main>

      <Footer onNavigatePage={onNavigatePage} />
    </div>
  );
}

export default PrivacyPage;
