import React, { useState } from 'react';
import { ArrowRight, CheckCircle2, ShieldCheck } from 'lucide-react';
import { analytics } from '../services/analytics';

export function Footer({ onOpenLegal }) {
  const [email, setEmail] = useState('');
  const [honeypot, setHoneypot] = useState('');
  const [status, setStatus] = useState('idle'); // 'idle' | 'success' | 'error'
  const [errorMsg, setErrorMsg] = useState('');

  const handleSubscribe = (e) => {
    e.preventDefault();

    // Anti-bot honeypot check
    if (honeypot.trim() !== '') {
      return;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!email || !emailRegex.test(email.trim())) {
      setStatus('error');
      setErrorMsg('Please enter a valid work email address.');
      return;
    }

    setStatus('success');
    analytics.trackNewsletterSubscribed();
    setEmail('');
    setErrorMsg('');
  };

  return (
    <footer className="bg-white border-t border-[#E4E2EB] pt-16 pb-12 text-[#524E5E]">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        <div className="grid grid-cols-2 md:grid-cols-12 gap-8 lg:gap-12 pb-14 border-b border-[#E4E2EB]">
          
          {/* Brand Info */}
          <div className="col-span-2 md:col-span-4 space-y-4">
            <a href="#" className="flex items-center gap-2.5 group">
              <div className="w-8 h-8 rounded-lg bg-[#0F0E17] flex items-center justify-center shadow-xs">
                <svg
                  className="w-4 h-4 text-white"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <line x1="18" y1="20" x2="18" y2="10" />
                  <line x1="12" y1="20" x2="12" y2="4" />
                  <line x1="6" y1="20" x2="6" y2="14" />
                </svg>
              </div>
              <span className="text-xl font-bold tracking-tight text-[#0F0E17]">
                Voxly
              </span>
            </a>
            <p className="text-xs sm:text-sm text-[#524E5E] leading-relaxed max-w-sm">
              The autonomous AI voice employee platform for high-growth revenue, support, and dispatch teams.
            </p>

            {/* Live Telephony Status Indicator */}
            <div className="pt-2">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#FAF9FD] border border-[#E4E2EB] text-[#0F0E17] text-xs font-semibold">
                <span className="w-2 h-2 rounded-full bg-[#10B981]" />
                <span>All Telephony Systems Operational</span>
              </div>
            </div>
          </div>

          {/* Product Links */}
          <div className="col-span-1 md:col-span-2 space-y-3">
            <h4 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
              Product
            </h4>
            <ul className="space-y-2 text-xs">
              <li><a href="#capabilities" className="hover:text-[#0F0E17] transition-colors">Capabilities</a></li>
              <li><a href="#dashboard/employees" className="hover:text-[#0F0E17] transition-colors">Agent console</a></li>
              <li><a href="#talk-to-ai" className="hover:text-[#0F0E17] transition-colors">Talk to AI</a></li>
              <li><a href="#phone" className="hover:text-[#0F0E17] transition-colors">Phone Channels</a></li>
              <li><a href="#pricing" className="hover:text-[#0F0E17] transition-colors">Pricing & Metering</a></li>
            </ul>
          </div>

          {/* Solutions Links */}
          <div className="col-span-1 md:col-span-2 space-y-3">
            <h4 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
              Workflows
            </h4>
            <ul className="space-y-2 text-xs">
              <li><a href="#leads" className="hover:text-[#0F0E17] transition-colors">Lead Engine</a></li>
              <li><a href="#campaigns" className="hover:text-[#0F0E17] transition-colors">Bulk Campaigns</a></li>
              <li><a href="#train" className="hover:text-[#0F0E17] transition-colors">Knowledge Base</a></li>
              <li><a href="#team" className="hover:text-[#0F0E17] transition-colors">AI Team Roster</a></li>
              <li><a href="#industries" className="hover:text-[#0F0E17] transition-colors">Industries</a></li>
            </ul>
          </div>

          {/* Resources & Legal */}
          <div className="col-span-1 md:col-span-2 space-y-3">
            <h4 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
              Resources & Trust
            </h4>
            <ul className="space-y-2 text-xs">
              <li><a href="#faq" className="hover:text-[#0F0E17] transition-colors">Documentation & FAQ</a></li>
              <li><a href="#analytics" className="hover:text-[#0F0E17] transition-colors">Platform Telemetry</a></li>
              <li>
                <button
                  type="button"
                  onClick={() => onOpenLegal && onOpenLegal('privacy')}
                  className="hover:text-[#0F0E17] transition-colors text-left"
                >
                  Privacy Policy
                </button>
              </li>
              <li>
                <button
                  type="button"
                  onClick={() => onOpenLegal && onOpenLegal('terms')}
                  className="hover:text-[#0F0E17] transition-colors text-left"
                >
                  Terms of Service
                </button>
              </li>
            </ul>
          </div>

          {/* Newsletter / Updates */}
          <div className="col-span-2 md:col-span-2 space-y-3">
            <h4 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
              Stay Informed
            </h4>
            <p className="text-xs text-[#524E5E]">
              Quarterly acoustic research & voice telephony release notes.
            </p>
            
            {status === 'success' ? (
              <div className="flex items-center gap-2 p-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-[#10B981] text-xs font-semibold">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>Subscribed! Check your inbox soon.</span>
              </div>
            ) : (
              <form onSubmit={handleSubscribe} className="space-y-1.5 pt-1">
                {/* Honeypot field */}
                <input
                  type="text"
                  name="bot_protection_field"
                  value={honeypot}
                  onChange={(e) => setHoneypot(e.target.value)}
                  style={{ display: 'none' }}
                  tabIndex="-1"
                  autoComplete="off"
                  aria-hidden="true"
                />

                <div className="flex items-center gap-1.5">
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => {
                      setEmail(e.target.value);
                      if (status === 'error') setStatus('idle');
                    }}
                    placeholder="work@company.com"
                    aria-label="Work email address"
                    className="w-full text-xs px-3 py-2 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] focus:outline-none focus:border-[#0F0E17] text-[#0F0E17] placeholder:text-[#635F70]"
                  />
                  <button
                    type="submit"
                    className="p-2 rounded-xl bg-[#0F0E17] text-white hover:bg-[#232130] active:scale-[0.98] transition-all"
                    aria-label="Subscribe to newsletter"
                  >
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
                {status === 'error' && (
                  <p className="text-[11px] text-[#EF4444] mt-1">{errorMsg}</p>
                )}
              </form>
            )}
          </div>

        </div>

        {/* Bottom Bar */}
        <div className="pt-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-[#524E5E]">
          <div>
            © {new Date().getFullYear()} Voxly AI Inc. All rights reserved.
          </div>
          <div className="flex items-center gap-6">
            <button
              type="button"
              onClick={() => onOpenLegal && onOpenLegal('terms')}
              className="hover:text-[#0F0E17] transition-colors"
            >
              Terms of Service
            </button>
            <button
              type="button"
              onClick={() => onOpenLegal && onOpenLegal('privacy')}
              className="hover:text-[#0F0E17] transition-colors"
            >
              Privacy Policy
            </button>
            <span className="flex items-center gap-1 text-[#524E5E]">
              <ShieldCheck className="w-3.5 h-3.5 text-[#10B981]" />
              <span>TLS 1.3 / SRTP Encrypted</span>
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}
