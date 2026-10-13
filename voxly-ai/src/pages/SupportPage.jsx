import React, { useState } from 'react';
import { PageHeader } from './PageHeader';
import { ContactUsSection } from '../components/ContactUsSection';
import { Footer } from '../components/Footer';
import {
  Headphones,
  HelpCircle,
  ChevronDown,
  ShieldAlert,
  Clock,
  Sparkles,
  ArrowRight,
  LifeBuoy,
} from 'lucide-react';

const SUPPORT_FAQS = [
  {
    q: 'How are support tickets prioritized by the Dialtact team?',
    a: 'Tickets marked Critical Incident receive immediate automated paging to our on-call voice engineering team with a sub-2 hour SLA. High Priority tickets (telephony routing, trunk degradation) are addressed within 4 hours. General product and billing queries are processed within standard 24-hour business windows.',
  },
  {
    q: 'What should I do during an active voice trunk or telephony outage?',
    a: 'Submit a ticket with Priority set to "Critical Incident" and select "SIP Voice Network Routing". Our direct voice monitoring pipeline will immediately cross-reference carrier trunk logs and trigger automatic carrier failover if needed.',
  },
  {
    q: 'Can I bring my own existing telephone numbers or SIP trunks?',
    a: 'Yes! Dialtact provides Bring-Your-Own-Carrier (BYOC) SIP URI trunking as well as direct number provisioning across 100+ countries directly within your workspace console.',
  },
  {
    q: 'Where do I find my workspace tenant ID for a support ticket?',
    a: 'Your workspace tenant ID is visible in the console URL (`#dashboard/overview`) and under Settings > Workspace Profile. If you are already signed in, your ticket will automatically link to your workspace.',
  },
];

export function SupportPage({ onBackToLanding, onEnterConsole, onNavigatePage }) {
  const [openFaqIndex, setOpenFaqIndex] = useState(null);

  const toggleFaq = (index) => {
    setOpenFaqIndex(openFaqIndex === index ? null : index);
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#FAF9FD] text-[#0F0E17]">
      <PageHeader
        title="Customer Support Desk & Ticket Portal"
        subtitle="Direct technical engineering support, voice trunk operations, and enterprise SLAs."
        onBackToLanding={onBackToLanding}
        onEnterConsole={onEnterConsole}
      />

      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-10 space-y-12">
        {/* Main Support & Ticket Desk Form Section */}
        <section>
          <ContactUsSection />
        </section>

        {/* Support Knowledge Base & Common Questions */}
        <section className="bg-white rounded-3xl p-8 sm:p-10 border border-[#E4E2EB] shadow-xs space-y-6">
          <div className="flex items-center gap-2.5 border-b border-[#E4E2EB] pb-4">
            <div className="w-8 h-8 rounded-xl bg-[#6344E7]/10 text-[#6344E7] flex items-center justify-center">
              <HelpCircle className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base font-bold text-[#0F0E17]">Frequently Answered Inquiries</h2>
              <p className="text-xs text-[#524E5E] mt-0.5">Quick guidance on common account, billing, and telephony questions.</p>
            </div>
          </div>

          <div className="divide-y divide-[#E4E2EB]">
            {SUPPORT_FAQS.map((faq, idx) => (
              <div key={idx} className="py-4 first:pt-0 last:pb-0">
                <button
                  type="button"
                  onClick={() => toggleFaq(idx)}
                  className="w-full flex items-center justify-between text-left group"
                >
                  <span className="text-xs sm:text-sm font-semibold text-[#0F0E17] group-hover:text-[#6344E7] transition-colors">
                    {faq.q}
                  </span>
                  <ChevronDown
                    className={`w-4 h-4 text-[#8C879A] transition-transform duration-200 shrink-0 ml-4 ${
                      openFaqIndex === idx ? 'rotate-180 text-[#6344E7]' : ''
                    }`}
                  />
                </button>
                {openFaqIndex === idx && (
                  <p className="text-xs text-[#524E5E] mt-2.5 leading-relaxed bg-[#FAF9FD] p-3 rounded-xl border border-[#E4E2EB]">
                    {faq.a}
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>
      </main>

      <Footer onNavigatePage={onNavigatePage} />
    </div>
  );
}

export default SupportPage;
