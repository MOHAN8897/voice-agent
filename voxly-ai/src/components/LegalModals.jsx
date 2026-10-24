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
        <div className="flex items-center justify-between px-4 sm:px-6 py-3 sm:py-4 border-b border-[#E4E2EB] bg-[#FAF9FD] shrink-0 gap-2">
          <div className="flex items-center gap-2 overflow-x-auto scrollbar-none touch-pan-x">
            <div className="flex p-1 rounded-xl bg-[#EFECE6] border border-[#E4E2EB] whitespace-nowrap">
              <button
                onClick={() => setTab('privacy')}
                className={`flex items-center gap-2 px-3 py-1.5 min-h-[38px] rounded-lg text-xs font-semibold transition-all ${
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
                className={`flex items-center gap-2 px-3 py-1.5 min-h-[38px] rounded-lg text-xs font-semibold transition-all ${
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
            className="p-2 min-w-[40px] min-h-[40px] flex items-center justify-center rounded-xl text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#E4E2EB]/50 transition-colors shrink-0"
            aria-label="Close dialog"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-4 sm:p-8 overflow-y-auto text-sm text-[#524E5E] leading-relaxed space-y-6 font-normal">
          {tab === 'privacy' ? (
            <div className="space-y-5">
              <div className="pb-4 border-b border-[#E4E2EB]">
                <h3 className="text-xl font-bold text-[#0F0E17] tracking-tight">
                  Dialtact Privacy Policy
                </h3>
                <p className="text-xs text-[#524E5E] mt-1">
                  Updated: 24 October 2026 · India
                </p>
              </div>

              <section className="space-y-2">
                <h4 className="text-sm font-bold text-[#0F0E17] uppercase tracking-wider">
                  1. Scope & Telephony Voice Data Processing
                </h4>
                <p>
                  Dialtact ("we", "us") provides AI voice services. Account details, contact lists, call audio, transcripts and call metadata are processed to provide and support the service. Business customers remain responsible for the purpose of their calls, the information they collect and the privacy notices given to callers.
                </p>
              </section>

              <section className="space-y-2">
                <h4 className="text-sm font-bold text-[#0F0E17] uppercase tracking-wider">
                  2. Voice Recording, Transcription & Consent
                </h4>
                <p>
                  Before collecting call data, identify your business, explain any recording or transcription and its purpose, and provide an accessible privacy notice. Obtain the consent or other permission required for your use case. Commercial calls in India must also meet TRAI's TCCCPR requirements for consent, recipient preferences and applicable registration.
                </p>
                <div className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-3.5 space-y-1.5 text-xs">
                  <div className="flex items-center gap-2 font-semibold text-[#0F0E17]">
                    <Lock className="w-3.5 h-3.5 text-[#6344E7]" />
                    <span>Data access &amp; retention</span>
                  </div>
                  <p>
                    Restrict access to recordings and transcripts, collect only what your stated purpose needs and document an appropriate retention period. Deletion may be subject to applicable recordkeeping requirements and the service's deletion process.
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
                  4. Indian privacy law &amp; grievances
                </h4>
                <p>
                  The Information Technology Act and SPDI Rules apply where relevant. The DPDP Act, 2023 and Rules, 2025 have phased commencement; main notice, consent and data-principal duties commence 18 months after Gazette publication in November 2025. Send privacy, correction, deletion or grievance requests to <a href="mailto:privacy@dialtact.com" className="underline">privacy@dialtact.com</a>. Requests are assessed under the applicable law, role and retention requirements.
                </p>
                <p className="text-xs"><a href="https://www.meity.gov.in/static/uploads/2025/11/c56ceae6c383460ca69577428d36828b.pdf" target="_blank" rel="noopener noreferrer" className="underline">Official DPDP commencement notification</a></p>
              </section>
            </div>
          ) : (
            <div className="space-y-5">
              <div className="pb-4 border-b border-[#E4E2EB]">
                <h3 className="text-xl font-bold text-[#0F0E17] tracking-tight">
                  Dialtact Terms of Service
                </h3>
                <p className="text-xs text-[#524E5E] mt-1">
                  Updated: 24 October 2026 · India
                </p>
              </div>

              <section className="space-y-2">
                <h4 className="text-sm font-bold text-[#0F0E17] uppercase tracking-wider">
                  1. Acceptance & Service Overview
                </h4>
                <p>
                  By creating an account, connecting a phone number, or deploying an AI voice employee on Dialtact, you agree to these Terms of Service. Dialtact grants you a commercial license to configure, deploy, and scale autonomous voice employees across telephone and web channels.
                </p>
              </section>

              <section className="space-y-2">
                <h4 className="text-sm font-bold text-[#0F0E17] uppercase tracking-wider">
                  2. TRAI commercial calling &amp; acceptable use
                </h4>
                <p>
                  For Indian commercial calls, comply with TRAI's TCCCPR framework, applicable registration and calling route requirements, valid consent and recipient preferences. Maintain evidence of permission and honour opt-outs. Your workspace suppression list is not proof of a national DND or consent check. You may <strong>not</strong> use Dialtact for:
                </p>
                <ul className="list-disc pl-5 space-y-1 text-xs">
                  <li>Unsolicited commercial calls without the required permission</li>
                  <li>Emergency service impersonation or spoofing caller IDs</li>
                  <li>Harassment, debt extortion, or deceptive financial schemes</li>
                  <li>High-frequency spam dialing exceeding published API concurrency quotas</li>
                </ul>
              </section>

              <p className="text-xs">Indian law governs these terms, subject to any signed agreement. Destination-country rules also apply to international calls. <a href="https://trai.gov.in/release-publication/regulations/amendments-page/7617" target="_blank" rel="noopener noreferrer" className="underline">Read TRAI's regulations and phased amendments.</a></p>

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
                  Service levels, uptime commitments and maintenance notice periods for
                  Enterprise plans are set out in the signed order form rather than on this
                  page. If you need a specific commitment before you buy, ask for the order form
                  and we will put the numbers in writing.
                </p>
              </section>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 border-t border-[#E4E2EB] bg-[#FAF9FD] flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-[#524E5E]">
            <CheckCircle2 className="w-4 h-4 text-[#10B981]" />
            <span>Indian calling &amp; privacy requirements</span>
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
