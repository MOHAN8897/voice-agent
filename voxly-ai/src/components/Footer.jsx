import React, { useState, useEffect } from 'react';
import { ArrowRight, CheckCircle2, ShieldCheck, Globe } from 'lucide-react';
import { analytics } from '../services/analytics';
import { api } from '../services/api';

export function Footer({ onNavigatePage }) {
  const [email, setEmail] = useState('');
  const [honeypot, setHoneypot] = useState('');
  const [status, setStatus] = useState('idle'); // 'idle' | 'success' | 'error'
  const [errorMsg, setErrorMsg] = useState('');
  const [socialLinks, setSocialLinks] = useState({
    twitter: 'https://x.com/dialtact',
    linkedin: 'https://linkedin.com/company/dialtact',
    github: 'https://github.com/dialtact',
    youtube: 'https://youtube.com/@dialtact',
    discord: 'https://discord.gg/dialtact',
  });

  useEffect(() => {
    let isMounted = true;
    api.support
      .getConfig()
      .then((cfg) => {
        if (isMounted && cfg && cfg.socialLinks) {
          setSocialLinks((prev) => ({
            ...prev,
            ...cfg.socialLinks,
          }));
        }
      })
      .catch(() => {
        // Fallback to built-in defaults
      });
    return () => {
      isMounted = false;
    };
  }, []);

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

  const handleLinkClick = (pageHash) => (e) => {
    e.preventDefault();
    if (onNavigatePage) {
      onNavigatePage(pageHash);
    } else {
      window.location.hash = pageHash;
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  return (
    <footer className="bg-white border-t border-[#E4E2EB] pt-16 pb-12 text-[#524E5E]">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        <div className="grid grid-cols-2 md:grid-cols-12 gap-8 lg:gap-12 pb-14 border-b border-[#E4E2EB]">
          
          {/* Brand Info & Social Media Links */}
          <div className="col-span-2 md:col-span-4 space-y-4">
            <a
              href="#"
              onClick={handleLinkClick('')}
              className="flex items-center gap-2.5 group"
            >
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
                Dialtact
              </span>
            </a>
            <p className="text-xs sm:text-sm text-[#524E5E] leading-relaxed max-w-sm">
              The autonomous AI voice employee platform for high-growth revenue, support, and dispatch teams.
            </p>


            {/* Social Media Icons (Configured via Backend Admin Panel) */}
            <div className="pt-3">
              <p className="text-[11px] font-bold text-[#8C879A] uppercase tracking-wider mb-2.5">
                Connect With Us
              </p>
              <div className="flex items-center gap-2.5" data-testid="footer-social-links">
                {/* Twitter / X */}
                {socialLinks.twitter && (
                  <a
                    href={socialLinks.twitter}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label="Dialtact on X (Twitter)"
                    className="w-8 h-8 rounded-lg bg-[#FAF9FD] hover:bg-[#0F0E17] text-[#524E5E] hover:text-white border border-[#E4E2EB] flex items-center justify-center transition-all duration-200 hover:scale-105 shadow-2xs"
                  >
                    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
                    </svg>
                  </a>
                )}

                {/* LinkedIn */}
                {socialLinks.linkedin && (
                  <a
                    href={socialLinks.linkedin}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label="Dialtact on LinkedIn"
                    className="w-8 h-8 rounded-lg bg-[#FAF9FD] hover:bg-[#0077B5] text-[#524E5E] hover:text-white border border-[#E4E2EB] flex items-center justify-center transition-all duration-200 hover:scale-105 shadow-2xs"
                  >
                    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z" />
                    </svg>
                  </a>
                )}

                {/* GitHub */}
                {socialLinks.github && (
                  <a
                    href={socialLinks.github}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label="Dialtact on GitHub"
                    className="w-8 h-8 rounded-lg bg-[#FAF9FD] hover:bg-[#24292e] text-[#524E5E] hover:text-white border border-[#E4E2EB] flex items-center justify-center transition-all duration-200 hover:scale-105 shadow-2xs"
                  >
                    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
                      <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
                    </svg>
                  </a>
                )}

                {/* YouTube */}
                {socialLinks.youtube && (
                  <a
                    href={socialLinks.youtube}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label="Dialtact on YouTube"
                    className="w-8 h-8 rounded-lg bg-[#FAF9FD] hover:bg-[#FF0000] text-[#524E5E] hover:text-white border border-[#E4E2EB] flex items-center justify-center transition-all duration-200 hover:scale-105 shadow-2xs"
                  >
                    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
                    </svg>
                  </a>
                )}

                {/* Discord */}
                {socialLinks.discord && (
                  <a
                    href={socialLinks.discord}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label="Dialtact Discord Community"
                    className="w-8 h-8 rounded-lg bg-[#FAF9FD] hover:bg-[#5865F2] text-[#524E5E] hover:text-white border border-[#E4E2EB] flex items-center justify-center transition-all duration-200 hover:scale-105 shadow-2xs"
                  >
                    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994.021-.041.001-.09-.041-.106a13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.894.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
                    </svg>
                  </a>
                )}
              </div>
            </div>
          </div>

          {/* Column 2: Platform & Product Pages */}
          <div className="col-span-1 md:col-span-2 space-y-3">
            <h4 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
              Platform
            </h4>
            <ul className="space-y-2 text-xs">
              <li>
                <a href="#how-it-works" onClick={handleLinkClick('how-it-works')} className="hover:text-[#0F0E17] transition-colors">
                  How It Works
                </a>
              </li>
              <li>
                <a href="#capabilities" onClick={handleLinkClick('capabilities')} className="hover:text-[#0F0E17] transition-colors">
                  Voice Capabilities
                </a>
              </li>
              <li>
                <a href="#industries" onClick={handleLinkClick('industries')} className="hover:text-[#0F0E17] transition-colors">
                  Industry Models
                </a>
              </li>
              <li>
                <a href="#pricing" onClick={handleLinkClick('pricing')} className="hover:text-[#0F0E17] transition-colors">
                  Pricing & Metering
                </a>
              </li>
              <li>
                <a href="#dashboard/overview" onClick={handleLinkClick('dashboard/overview')} className="hover:text-[#0F0E17] transition-colors">
                  Workspace Console
                </a>
              </li>
            </ul>
          </div>

          {/* Column 3: Customer Support Desk Pages */}
          <div className="col-span-1 md:col-span-2 space-y-3">
            <h4 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
              Customer Support
            </h4>
            <ul className="space-y-2 text-xs">
              <li>
                <a
                  href="#support"
                  onClick={handleLinkClick('support')}
                  className="hover:text-[#0F0E17] font-semibold text-[#6344E7] transition-colors"
                >
                  Customer Support Desk
                </a>
              </li>
              <li>
                <a
                  href="#contact"
                  onClick={handleLinkClick('contact')}
                  className="hover:text-[#0F0E17] transition-colors"
                >
                  Submit Ticket Inquiry
                </a>
              </li>
              <li>
                <a
                  href="#support"
                  onClick={handleLinkClick('support')}
                  className="hover:text-[#0F0E17] transition-colors"
                >
                  Support FAQs & SLAs
                </a>
              </li>
            </ul>
          </div>

          {/* Column 4: Company, Security & Legal */}
          <div className="col-span-1 md:col-span-2 space-y-3">
            <h4 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
              Company & Trust
            </h4>
            <ul className="space-y-2 text-xs">
              <li>
                <a
                  href="#company"
                  onClick={handleLinkClick('company')}
                  className="hover:text-[#0F0E17] font-semibold text-[#0F0E17] transition-colors block text-left"
                >
                  About Dialtact
                </a>
              </li>
              <li>
                <a
                  href="#security"
                  onClick={handleLinkClick('security')}
                  className="hover:text-[#0F0E17] transition-colors block text-left"
                >
                  Security & Architecture
                </a>
              </li>
              <li>
                <a
                  href="#privacy"
                  onClick={handleLinkClick('privacy')}
                  className="hover:text-[#0F0E17] transition-colors block text-left"
                >
                  Privacy Policy
                </a>
              </li>
              <li>
                <a
                  href="#terms"
                  onClick={handleLinkClick('terms')}
                  className="hover:text-[#0F0E17] transition-colors block text-left"
                >
                  Terms of Service
                </a>
              </li>
            </ul>
          </div>

          {/* Column 5: Stay Informed / Research Updates */}
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
                    className="w-full text-base sm:text-xs px-3 py-2 min-h-[44px] sm:min-h-[36px] rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] focus:outline-none focus:border-[#0F0E17] text-[#0F0E17] placeholder:text-[#635F70]"
                  />
                  <button
                    type="submit"
                    className="p-2 min-w-[44px] min-h-[44px] sm:min-w-[36px] sm:min-h-[36px] flex items-center justify-center rounded-xl bg-[#0F0E17] text-white hover:bg-[#232130] active:scale-[0.98] transition-all shrink-0"
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

        {/* Bottom Bar with Separate Pages and Certifications */}
        <div className="pt-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-[#524E5E] text-center sm:text-left">
          <div>
            © {new Date().getFullYear()} Dialtact Inc. All rights reserved.
          </div>
          <div className="flex flex-wrap items-center justify-center sm:justify-end gap-x-6 gap-y-2">
            <a
              href="#terms"
              onClick={handleLinkClick('terms')}
              className="hover:text-[#0F0E17] transition-colors py-1 min-h-[36px] flex items-center"
            >
              Terms of Service
            </a>
            <a
              href="#privacy"
              onClick={handleLinkClick('privacy')}
              className="hover:text-[#0F0E17] transition-colors py-1 min-h-[36px] flex items-center"
            >
              Privacy Policy
            </a>
            <a
              href="#security"
              onClick={handleLinkClick('security')}
              className="hover:text-[#0F0E17] transition-colors py-1 min-h-[36px] flex items-center"
            >
              Security Policy
            </a>
            <span className="flex items-center gap-1 text-[#524E5E] py-1">
              <ShieldCheck className="w-3.5 h-3.5 text-[#10B981]" />
              <span>TLS 1.3 / SRTP Encrypted</span>
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}

export default Footer;
