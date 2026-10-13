import React from 'react';
import { PageHeader } from './PageHeader';
import { Footer } from '../components/Footer';
import { ShieldCheck, Lock, Key, Server, Cpu, CheckCircle2 } from 'lucide-react';

export function SecurityPage({ onBackToLanding, onEnterConsole, onNavigatePage }) {
  const securityPillars = [
    {
      title: 'SRTP & TLS 1.3 Encryption',
      desc: 'All real-time audio media payload is secured with Secure Real-Time Transport Protocol (SRTP). All client, console, and REST API network packets require TLS 1.3 ciphers.',
      icon: Lock,
    },
    {
      title: 'Strict Multi-Tenant Isolation',
      desc: 'Workspace databases enforce kernel and row-level tenant filtering. Customer data, call transcripts, and voice models are cryptographically compartmentalized.',
      icon: Server,
    },
    {
      title: 'Zero Training on Customer Data',
      desc: 'Your voice recordings, private business brain records, and caller transcripts are never used to train generalized foundation language models.',
      icon: Cpu,
    },
    {
      title: 'Automated DAST & SAST Scans',
      desc: 'Continuous Semgrep static security audits, OWASP Top 10 compliance rules, and automated dynamic penetration suites execute on every deployment.',
      icon: ShieldCheck,
    },
    {
      title: 'Hardware Security Modules (HSM)',
      desc: 'SIP trunk keys, API secrets, and OAuth connection tokens are encrypted at rest using industry-grade HSM key management infrastructure.',
      icon: Key,
    },
    {
      title: 'Role-Based Access Control (RBAC)',
      desc: 'Granular permissions for workspace owners, staff administrators, and read-only auditors ensure least-privilege operational access.',
      icon: CheckCircle2,
    },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-[#FAF9FD] text-[#0F0E17]">
      <PageHeader
        title="Security & Compliance"
        onBackToLanding={onBackToLanding}
        onEnterConsole={onEnterConsole}
      />

      <main className="flex-1 max-w-5xl mx-auto px-6 sm:px-8 py-12 sm:py-16 space-y-12">
        <div className="text-center max-w-2xl mx-auto space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-xs font-semibold text-emerald-800">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Enterprise Security Posture</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold text-[#0F0E17] tracking-tight">
            Security Architecture & Voice Trust
          </h1>
          <p className="text-sm text-[#524E5E] leading-relaxed">
            Dialtact is designed from the bare metal up to handle high-concurrency telephony, confidential business workflows, and sensitive customer conversations.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {securityPillars.map((p) => {
            const Icon = p.icon;
            return (
              <div key={p.title} className="bg-white rounded-2xl border border-[#E4E2EB] p-6 shadow-xs space-y-3">
                <div className="w-10 h-10 rounded-xl bg-[#6344E7]/10 border border-[#6344E7]/20 flex items-center justify-center text-[#6344E7]">
                  <Icon className="w-5 h-5" />
                </div>
                <h2 className="text-base font-bold text-[#0F0E17]">{p.title}</h2>
                <p className="text-xs text-[#524E5E] leading-relaxed">{p.desc}</p>
              </div>
            );
          })}
        </div>

        <div className="bg-white rounded-2xl border border-[#E4E2EB] p-8 shadow-xs space-y-4">
          <h2 className="text-lg font-bold text-[#0F0E17]">Security Incident Response & Reporting</h2>
          <p className="text-xs text-[#524E5E] leading-relaxed">
            If you believe you have discovered a security vulnerability or anomalous behavior within Dialtact infrastructure, please submit a responsible disclosure report directly to{' '}
            <a href="mailto:security@dialtact.com" className="font-semibold text-[#6344E7] hover:underline">
              security@dialtact.com
            </a>{' '}
            or open a priority ticket via our{' '}
            <a href="#contact" onClick={(e) => { e.preventDefault(); onNavigatePage?.('contact'); }} className="font-semibold text-[#6344E7] hover:underline">
              Customer Support Desk
            </a>.
          </p>
        </div>
      </main>

      <Footer onNavigatePage={onNavigatePage} />
    </div>
  );
}

export default SecurityPage;
