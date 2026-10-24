import React from 'react';
import { PageHeader } from './PageHeader';
import { Footer } from '../components/Footer';
import { Scale } from 'lucide-react';

export function TermsPage({ onBackToLanding, onEnterConsole, onNavigatePage, onSignIn }) {
  return (
    <div className="min-h-screen flex flex-col bg-[#FAF9FD] text-[#0F0E17]">
      <PageHeader
        title="Terms of Service"
        onBackToLanding={onBackToLanding}
        onEnterConsole={onEnterConsole}
        onSignIn={onSignIn}
      />

      <main className="flex-1 max-w-4xl mx-auto px-6 sm:px-8 py-12 sm:py-16">
        <div className="bg-white rounded-2xl border border-[#E4E2EB] shadow-xs p-8 sm:p-12 space-y-8">
          <div className="border-b border-[#E4E2EB] pb-6">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#FAF9FD] border border-[#E4E2EB] text-xs font-semibold text-[#6344E7] mb-3">
              <Scale className="w-3.5 h-3.5" />
              <span>Subscriber Agreement &amp; Master Terms</span>
            </div>
            <h1 className="text-3xl sm:text-4xl font-extrabold text-[#0F0E17] tracking-tight">
              Dialtact Terms of Service
            </h1>
            <p className="text-xs text-[#524E5E] mt-2">
              Updated: 24 October 2026 · India
            </p>
          </div>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              1. Acceptance of Terms
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              By registering an account, provisioning telephone numbers, deploying voice bots, or accessing Dialtact APIs, you agree to be bound by these Master Terms of Service between Dialtact Inc. and your registered organization.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              2. Acceptable Use &amp; Telecommunication Regulations
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              Indian commercial calls must meet TRAI's Telecom Commercial Communications Customer Preference Regulations (TCCCPR), including valid consent, recipient preferences and applicable sender registration and calling route requirements. Maintain evidence of permission and honour opt-outs. Your workspace Do Not Call list records your own suppression requests; it does not verify national preference or consent records. Unsolicited spam, caller ID spoofing and harassment are prohibited. International calls also require review under the destination's rules. See{' '}
              <a href="https://trai.gov.in/release-publication/regulations/amendments-page/7617" target="_blank" rel="noopener noreferrer" className="font-semibold underline">TRAI's regulations and phased amendments</a>.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              3. Telephony Wallet, Credits &amp; Billing Metering
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              Telephony usage (including per-minute audio transport, LLM cognitive tokens, and telephone number leases) is billed against your prepaid workspace balance in integer minor units. Subscriptions renew monthly unless cancelled prior to the billing cycle expiration date.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              4. Service Level Availability (SLA)
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              Dialtact maintains an annual system availability target of 99.9% for core telephone ingress and egress endpoints, excluding scheduled maintenance windows announced with advance notice via our status desk.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              5. Intellectual Property &amp; Voice Customizations
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              You retain all ownership rights in your proprietary prompts, business knowledge documents, and synthetic voice profile customizations. Dialtact retains all intellectual property rights in the underlying agentic execution runtime, speech synthesizer orchestration, and platform software.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-[#0F0E17]">
              6. Dispute Resolution &amp; Contact
            </h2>
            <p className="text-sm text-[#524E5E] leading-relaxed">
              These terms are governed by the laws of India, subject to any signed agreement. For legal inquiries or contractual enterprise amendments, contact{' '}
              <a href="mailto:legal@dialtact.com" className="font-semibold text-[#6344E7] hover:underline">
                legal@dialtact.com
              </a>{' '}
              or our{' '}
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

export default TermsPage;
