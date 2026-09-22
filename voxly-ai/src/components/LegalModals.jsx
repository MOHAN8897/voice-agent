import React, { useEffect } from 'react';
import { X, Shield, FileText, CheckCircle2, Lock } from 'lucide-react';

export function LegalModals({ isOpen, onClose, defaultTab = 'privacy' }) {
  const [tab, setTab] = React.useState(defaultTab);

  useEffect(() => {
    setTab(defaultTab);
  }, [defaultTab]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-[#0F0E17]/60 backdrop-blur-sm transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal Dialog */}
      <div className="relative bg-white rounded-2xl border border-[#E4E2EB] shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden z-10 animate-in fade-in zoom-in-95 duration-200">
        
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#E4E2EB] bg-[#FAF9FD]">
          <div className="flex items-center gap-3">
            <div className="flex p-1 rounded-xl bg-[#EFECE6] border border-[#E4E2EB]">
              <button
                onClick={() => setTab('privacy')}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  tab === 'privacy'
                    ? 'bg-white text-[#0F0E17] shadow-xs'
                    : 'text-[#524E5E] hover:text-[#0F0E17]'
                }`}
              >
                <Shield className="w-3.5 h-3.5 text-[#6344E7]" />
                <span>Privacy Policy</span>
              </button>
              <button
                onClick={() => setTab('terms')}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  tab === 'terms'
                    ? 'bg-white text-[#0F0E17] shadow-xs'
                    : 'text-[#524E5E] hover:text-[#0F0E17]'
                }`}
              >
                <FileText className="w-3.5 h-3.5 text-[#6344E7]" />
                <span>Terms of Service</span>
              </button>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#E4E2EB]/50 transition-colors"
            aria-label="Close dialog"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 sm:p-8 overflow-y-auto text-sm text-[#524E5E] leading-relaxed space-y-6 font-normal">
          {tab === 'privacy' ? (
            <div className="space-y-5">
              <div className="pb-4 border-b border-[#E4E2EB]">
                <h3 className="text-xl font-bold text-[#0F0E17] tracking-tight">
                  Voxly AI Privacy Policy
                </h3>
                <p className="text-xs text-[#524E5E] mt-1">
                  Last Updated: September 17, 2026 • Effective Date: January 1, 2026
                </p>
              </div>

              <section className="space-y-2">
                <h4 className="text-sm font-bold text-[#0F0E17] uppercase tracking-wider">
                  1. Scope & Telephony Voice Data Processing
                </h4>
                <p>
                  Voxly AI Inc. ("Voxly", "we", "us") provides enterprise autonomous AI voice employee infrastructure. This Privacy Policy details how we collect, process, transcribe, and secure audio recordings, synthetic voice outputs, caller telemetry, and contact data transmitted through our web services and telephone connections.
                </p>
              </section>

              <section className="space-y-2">
                <h4 className="text-sm font-bold text-[#0F0E17] uppercase tracking-wider">
                  2. Voice Recording, Transcription & Consent
                </h4>
                <p>
                  Inbound and outbound telephone calls processed through Voxly are digitized and transcribed in real-time. Customers deploying Voxly agents are contractually required to configure two-party call recording consent disclosures ("This call may be recorded or monitored by an automated assistant") in compliance with applicable federal, state, and international telecommunication laws.
                </p>
                <div className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-3.5 space-y-1.5 text-xs">
                  <div className="flex items-center gap-2 font-semibold text-[#0F0E17]">
                    <Lock className="w-3.5 h-3.5 text-[#6344E7]" />
                    <span>Audio Encryption & Retention Standards</span>
                  </div>
                  <p>
                    All audio streams are encrypted in transit via TLS 1.3 and SRTP. By default, raw audio recordings are purged after 30 days unless customer enterprise retention rules mandate longer archival under custom storage encryption (AES-256).
                  </p>
                </div>
              </section>

              <section className="space-y-2">
                <h4 className="text-sm font-bold text-[#0F0E17] uppercase tracking-wider">
                  3. Non-Training Commitment on Customer Audio
                </h4>
                <p>
                  We do <strong>not</strong> sell personal information, and we do <strong>not</strong> use your proprietary customer phone calls, transcripts, or uploaded business knowledge documents to train public foundation models without your explicit opt-in enterprise agreement.
                </p>
              </section>

              <section className="space-y-2">
                <h4 className="text-sm font-bold text-[#0F0E17] uppercase tracking-wider">
                  4. GDPR, UK DPA & CCPA/CPRA Rights
                </h4>
                <p>
                  Data subjects maintain rights to request access to call recordings, request transcript corrections, or execute complete data deletion. Data erasure requests can be dispatched directly to <span className="font-mono text-xs text-[#0F0E17]">privacy@voxly.ai</span> and are completed within 30 calendar days.
                </p>
              </section>
            </div>
          ) : (
            <div className="space-y-5">
              <div className="pb-4 border-b border-[#E4E2EB]">
                <h3 className="text-xl font-bold text-[#0F0E17] tracking-tight">
                  Voxly AI Terms of Service
                </h3>
                <p className="text-xs text-[#524E5E] mt-1">
                  Last Updated: September 17, 2026 • Enterprise License Agreement
                </p>
              </div>

              <section className="space-y-2">
                <h4 className="text-sm font-bold text-[#0F0E17] uppercase tracking-wider">
                  1. Acceptance & Service Overview
                </h4>
                <p>
                  By creating an account, connecting a phone number, or deploying an AI voice employee on Voxly, you agree to these Terms of Service. Voxly grants you a commercial license to configure, deploy, and scale autonomous voice employees across telephone and web channels.
                </p>
              </section>

              <section className="space-y-2">
                <h4 className="text-sm font-bold text-[#0F0E17] uppercase tracking-wider">
                  2. Acceptable Telephony Use & TCPA Compliance
                </h4>
                <p>
                  You agree to comply with the Telephone Consumer Protection Act (TCPA), the FTC Telemarketing Sales Rule (TSR), and applicable Do-Not-Call (DNC) registry requirements. You may <strong>not</strong> utilize Voxly for:
                </p>
                <ul className="list-disc pl-5 space-y-1 text-xs">
                  <li>Unsolicited commercial robocalls without prior express written consent</li>
                  <li>Emergency service impersonation or spoofing caller IDs</li>
                  <li>Harassment, debt extortion, or deceptive financial schemes</li>
                  <li>High-frequency spam dialing exceeding published API concurrency quotas</li>
                </ul>
              </section>

              <section className="space-y-2">
                <h4 className="text-sm font-bold text-[#0F0E17] uppercase tracking-wider">
                  3. Billing, Metering & Per-Second Precision
                </h4>
                <p>
                  Platform subscriptions are billed monthly or annually in advance. Voice usage minutes are metered in exact 1-second increments with zero rounding up to the nearest minute. Unused monthly plan minutes do not roll over to subsequent billing cycles.
                </p>
              </section>

              <section className="space-y-2">
                <h4 className="text-sm font-bold text-[#0F0E17] uppercase tracking-wider">
                  4. Service Level Agreement (SLA) & Uptime
                </h4>
                <p>
                  Enterprise plans carry a 99.95% telephony uptime guarantee covering SIP gateway availability and sub-500 millisecond neural acoustic processing. Scheduled maintenance windows are communicated at least 72 hours in advance.
                </p>
              </section>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 border-t border-[#E4E2EB] bg-[#FAF9FD] flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-[#524E5E]">
            <CheckCircle2 className="w-4 h-4 text-[#10B981]" />
            <span>Strict TLS 1.3 & SOC2 Type II Certified Architecture</span>
          </div>
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl text-xs font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] active:scale-[0.98] transition-all"
          >
            Acknowledge & Close
          </button>
        </div>

      </div>
    </div>
  );
}
