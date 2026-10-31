import React from 'react';
import { PageHeader } from './PageHeader';
import { Footer } from '../components/Footer';
import { Shield } from 'lucide-react';

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
              Updated: 24 October 2026 · India
            </p>
          </div>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              1. Scope &amp; Telephony Voice Data Processing
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              Dialtact ("we", "us") provides AI voice services. We process account details, contact lists, call audio, transcripts and call metadata to provide and support the service. Business customers are responsible for the purpose of their calls, the information they collect and the privacy notices they provide to callers.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              2. Voice Recording, Transcription &amp; Consent Disclosures
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              Identify your business and explain any recording or transcription, its purpose and the applicable privacy notice before collecting caller data. Obtain consent or other permission required for your use case. Commercial calls in India also need review under TRAI's TCCCPR framework for valid consent, recipient preferences and applicable registration.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              3. Indian data protection framework
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              The Information Technology Act, 2000 and SPDI Rules, 2011 apply where relevant. The Digital Personal Data Protection Act, 2023 and Rules, 2025 have phased commencement. Main notice, consent and data-principal duties commence 18 months after Gazette publication in November 2025; preparation for those duties does not mean they are all already in force. Review the{' '}
              <a href="https://www.meity.gov.in/static/uploads/2025/11/c56ceae6c383460ca69577428d36828b.pdf" target="_blank" rel="noopener noreferrer" className="font-semibold underline">official commencement notification</a>{' '}and{' '}
              <a href="https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf" target="_blank" rel="noopener noreferrer" className="font-semibold underline">DPDP Rules</a>.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              4. Tenant Isolation &amp; Zero Model Training on Customer Audio
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              Dialtact does not sell your personal information or use your customer calls, transcripts or business knowledge to train public foundation models. Workspace access is restricted by tenant and authorised roles. Only share information needed for your stated calling purpose and control which members can access it.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              5. Data Retention &amp; Deletion
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              Document a retention period appropriate to the purpose of your recordings, transcripts and contact data. Use the available deletion process or contact support for a request. Applicable recordkeeping requirements, disputes and the service's deletion process may affect when data can be removed; do not assume an unlimited archive or immediate erasure.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              6. Privacy Rights &amp; Contact
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              For privacy questions, correction or deletion requests, consent withdrawal or grievances under applicable Indian law, contact{' '}
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
