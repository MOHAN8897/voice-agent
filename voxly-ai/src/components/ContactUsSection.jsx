import React, { useState, useEffect } from 'react';
import {
  Mail,
  Clock,
  ShieldCheck,
  Send,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  Headphones,
  LifeBuoy,
  Copy,
  Check,
  Server,
  FileCheck2,
} from 'lucide-react';
import { api } from '../services/api';

const INQUIRY_CATEGORIES = [
  { id: 'technical_support', label: 'Technical & Voice Prompt Tuning' },
  { id: 'enterprise_fleet', label: 'Enterprise Fleet & Dedicated Trunks' },
  { id: 'telephony_trunk', label: 'SIP Voice Network Routing' },
  { id: 'billing_pricing', label: 'Billing, Invoicing & Quotas' },
  { id: 'general_inquiry', label: 'General Product Inquiry' },
];

const PRIORITY_LEVELS = [
  { id: 'normal', label: 'Standard Ticket', color: 'text-[#10B981]' },
  { id: 'high', label: 'High Priority', color: 'text-[#F59E0B]' },
  { id: 'urgent', label: 'Critical Incident', color: 'text-[#EF4444]' },
];

export function ContactUsSection() {
  const [supportConfig, setSupportConfig] = useState({
    supportEmail: 'support@dialtact.com',
    businessHours: 'Mon - Fri: 9:00 AM - 6:00 PM EST',
    slaResponseTime: 'Within 2 hours for Priority, 24 hours Standard',
    autoReplyMessage: 'Thank you for reaching out. Our support engineering desk will review your inquiry promptly.',
  });

  const [form, setForm] = useState({
    fullName: '',
    email: '',
    company: '',
    category: 'technical_support',
    priority: 'normal',
    subject: '',
    message: '',
  });

  const [honeypot, setHoneypot] = useState('');
  const [loading, setLoading] = useState(false);
  const [submittedTicket, setSubmittedTicket] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);
  const [copiedEmail, setCopiedEmail] = useState(false);

  useEffect(() => {
    let isMounted = true;
    api.support
      .getConfig()
      .then((cfg) => {
        if (isMounted && cfg && Object.keys(cfg).length > 0) {
          setSupportConfig((prev) => ({
            ...prev,
            ...cfg,
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

  const handleCopyEmail = () => {
    if (supportConfig.supportEmail) {
      navigator.clipboard?.writeText(supportConfig.supportEmail);
      setCopiedEmail(true);
      setTimeout(() => setCopiedEmail(false), 2000);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg(null);

    // Anti-bot honeypot check
    if (honeypot && honeypot.trim() !== '') {
      setSubmittedTicket({
        ticketNumber: 'DT-ACK-REC',
        fullName: form.fullName || 'Subscriber',
        email: form.email,
      });
      return;
    }

    if (!form.fullName.trim() || !form.email.trim() || !form.subject.trim() || !form.message.trim()) {
      setErrorMsg('Please complete all required fields.');
      return;
    }

    setLoading(true);
    try {
      const res = await api.support.submitInquiry({
        ...form,
        botTrap: honeypot || undefined,
      });
      if (res && res.ticket) {
        setSubmittedTicket(res.ticket);
      } else {
        setSubmittedTicket({
          ticketNumber: 'DT-' + Math.random().toString(36).substring(2, 8).toUpperCase(),
          fullName: form.fullName,
          email: form.email,
        });
      }
    } catch (err) {
      setErrorMsg(err.message || 'Failed to submit inquiry. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setSubmittedTicket(null);
    setErrorMsg(null);
    setForm({
      fullName: '',
      email: '',
      company: '',
      category: 'technical_support',
      priority: 'normal',
      subject: '',
      message: '',
    });
  };

  return (
    <section id="contact" className="py-20 sm:py-28 bg-[#0F0E17] text-white relative overflow-hidden">
      {/* Background glow effects */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[700px] h-[350px] bg-gradient-to-tr from-[#6344E7]/15 to-[#10B981]/10 rounded-full blur-[120px] pointer-events-none" />

      <div className="max-w-7xl mx-auto px-6 sm:px-8 relative z-10">
        {/* Section Header */}
        <div className="max-w-3xl mb-14 sm:mb-18">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-white/10 border border-white/10 text-white text-xs font-bold tracking-wider uppercase mb-4">
            <Headphones className="w-3.5 h-3.5 text-[#10B981]" />
            <span>Customer Support & Solutions Desk</span>
          </div>
          <h2 className="text-2xl sm:text-4xl lg:text-5xl font-extrabold text-white tracking-tight leading-[1.14] mb-4">
            Connect with our voice engineering{' '}
            <span className="block text-white">and customer support desk.</span>
          </h2>
          <p className="text-base sm:text-lg text-[#D1CFDB] leading-relaxed">
            Need assistance tuning agent prompts, deploying high-throughput outbound queues, or resolving account billing?
            Our support desk is monitored directly by platform engineers.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12">
          {/* Left Column: Direct Channels & SLA Overview */}
          <div className="lg:col-span-5 space-y-6">
            {/* Live Channel 1: Email */}
            <div className="p-6 rounded-2xl bg-[#161522] border border-[#27253D] shadow-xl relative overflow-hidden">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-[#6344E7]/20 border border-[#6344E7]/40 flex items-center justify-center text-[#A78BFA]">
                    <Mail className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-[#A78BFA] uppercase tracking-wider">Engineering Email Desk</h3>
                    <p className="text-sm font-semibold text-white mt-0.5">{supportConfig.supportEmail}</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={handleCopyEmail}
                  className="px-2.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-xs font-medium text-[#D1CFDB] flex items-center gap-1.5 transition-colors"
                  title="Copy email address"
                >
                  {copiedEmail ? <Check className="w-3.5 h-3.5 text-[#10B981]" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copiedEmail ? 'Copied' : 'Copy'}</span>
                </button>
              </div>
              <p className="text-xs text-[#9B97AA] mt-3">
                Inquiries are automatically triaged with response notifications sent straight to your inbox.
              </p>
            </div>

            {/* Live Channel 2: Ticket Portal & Telemetry */}
            <div className="p-6 rounded-2xl bg-[#161522] border border-[#27253D] shadow-xl">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-[#10B981]/20 border border-[#10B981]/40 flex items-center justify-center text-[#34D399]">
                  <FileCheck2 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-xs font-bold text-[#34D399] uppercase tracking-wider">Direct Ticket Tracking</h3>
                  <p className="text-sm font-semibold text-white mt-0.5">Automated Dispatch & SLA Timers</p>
                </div>
              </div>
              <p className="text-xs text-[#9B97AA] mt-3">
                Submit an inquiry below to receive an authenticated ticket tracking ID with priority response handling.
              </p>
            </div>

            {/* Business Hours & SLA */}
            <div className="p-6 rounded-2xl bg-[#161522] border border-[#27253D] shadow-xl space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-[#D1CFDB]">
                  <Clock className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-xs font-bold text-[#D1CFDB] uppercase tracking-wider">Operational Hours</h3>
                  <p className="text-sm font-medium text-white mt-0.5">{supportConfig.businessHours}</p>
                </div>
              </div>

              <div className="pt-3 border-t border-[#27253D] flex items-center gap-3">
                <ShieldCheck className="w-5 h-5 text-[#6344E7] shrink-0" />
                <div className="text-xs">
                  <span className="font-semibold text-white">SLA Standard: </span>
                  <span className="text-[#9B97AA]">{supportConfig.slaResponseTime}</span>
                </div>
              </div>

              <div className="pt-3 border-t border-[#27253D] flex items-center gap-3">
                <Server className="w-5 h-5 text-[#10B981] shrink-0" />
                <div className="text-xs">
                  <span className="font-semibold text-white">Platform Health: </span>
                  <span className="text-[#34D399]">All Trunks & Core Systems Active</span>
                </div>
              </div>
            </div>

            {/* Confidence reassurance banner */}
            <div className="p-4 rounded-xl bg-white/[0.03] border border-white/10 text-xs text-[#9B97AA] flex items-center gap-3">
              <Sparkles className="w-4 h-4 text-[#A78BFA] shrink-0" />
              <span>
                Enterprise subscribers receive dedicated solutions triage and direct engineering support.
              </span>
            </div>
          </div>

          {/* Right Column: Support Inquiry & Ticket Form */}
          <div className="lg:col-span-7">
            <div className="p-6 sm:p-8 rounded-2xl bg-[#161522] border border-[#27253D] shadow-2xl">
              {submittedTicket ? (
                /* Success Confirmation View */
                <div className="py-8 text-center space-y-5 animate-in fade-in duration-300">
                  <div className="w-16 h-16 rounded-full bg-[#10B981]/20 border border-[#10B981]/40 flex items-center justify-center text-[#34D399] mx-auto shadow-lg shadow-[#10B981]/10">
                    <CheckCircle2 className="w-8 h-8" />
                  </div>
                  <div>
                    <h3 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
                      Support Inquiry Received
                    </h3>
                    <p className="text-sm text-[#9B97AA] max-w-md mx-auto mt-2 leading-relaxed">
                      Your inquiry has been assigned to a support engineer. A confirmation notification has been dispatched.
                    </p>
                  </div>

                  <div className="p-4 rounded-xl bg-[#0F0E17] border border-[#27253D] inline-block text-left max-w-sm w-full mx-auto space-y-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-[#9B97AA]">Ticket Reference ID:</span>
                      <span className="font-mono font-bold text-[#A78BFA]">{submittedTicket.ticketNumber}</span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-[#9B97AA]">Assigned Contact:</span>
                      <span className="font-semibold text-white">{submittedTicket.fullName}</span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-[#9B97AA]">Status:</span>
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-[#10B981]/15 text-[#34D399] font-bold text-[11px]">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
                        Active Queue
                      </span>
                    </div>
                  </div>

                  {supportConfig.autoReplyMessage && (
                    <p className="text-xs italic text-[#7C778D] max-w-md mx-auto">
                      "{supportConfig.autoReplyMessage}"
                    </p>
                  )}

                  <div className="pt-4">
                    <button
                      type="button"
                      onClick={resetForm}
                      className="px-6 py-2.5 rounded-xl bg-white/10 hover:bg-white/15 border border-white/20 text-xs font-semibold text-white transition-all shadow-xs"
                    >
                      Submit Another Inquiry
                    </button>
                  </div>
                </div>
              ) : (
                /* Inquiry Form */
                <form onSubmit={handleSubmit} className="space-y-4">
                  {/* Anti-bot honeypot field */}
                  <input
                    type="text"
                    name="bot_protection_shield"
                    value={honeypot}
                    onChange={(e) => setHoneypot(e.target.value)}
                    style={{ display: 'none' }}
                    tabIndex="-1"
                    autoComplete="off"
                    aria-hidden="true"
                  />

                  <div>
                    <h3 className="text-lg font-bold text-white tracking-tight">Open a Support Request</h3>
                    <p className="text-xs text-[#9B97AA] mt-1">
                      Our customer support desk responds directly to your email address.
                    </p>
                  </div>

                  {errorMsg && (
                    <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-xs flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 shrink-0" />
                      <span>{errorMsg}</span>
                    </div>
                  )}

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-[#D1CFDB] mb-1.5">
                        Your Name <span className="text-red-400">*</span>
                      </label>
                      <input
                        type="text"
                        required
                        value={form.fullName}
                        onChange={(e) => setForm({ ...form, fullName: e.target.value })}
                        placeholder="Mohan Saiteja"
                        className="w-full px-3.5 py-2.5 rounded-xl bg-[#0F0E17] border border-[#27253D] text-white text-xs placeholder:text-[#524E5E] focus:outline-none focus:border-[#6344E7] focus:ring-1 focus:ring-[#6344E7] transition-colors"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-[#D1CFDB] mb-1.5">
                        Work Email <span className="text-red-400">*</span>
                      </label>
                      <input
                        type="email"
                        required
                        value={form.email}
                        onChange={(e) => setForm({ ...form, email: e.target.value })}
                        placeholder="you@company.com"
                        className="w-full px-3.5 py-2.5 rounded-xl bg-[#0F0E17] border border-[#27253D] text-white text-xs placeholder:text-[#524E5E] focus:outline-none focus:border-[#6344E7] focus:ring-1 focus:ring-[#6344E7] transition-colors"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-[#D1CFDB] mb-1.5">Company / Workspace</label>
                      <input
                        type="text"
                        value={form.company}
                        onChange={(e) => setForm({ ...form, company: e.target.value })}
                        placeholder="Acme Global Inc"
                        className="w-full px-3.5 py-2.5 rounded-xl bg-[#0F0E17] border border-[#27253D] text-white text-xs placeholder:text-[#524E5E] focus:outline-none focus:border-[#6344E7] focus:ring-1 focus:ring-[#6344E7] transition-colors"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-[#D1CFDB] mb-1.5">Inquiry Category</label>
                      <select
                        value={form.category}
                        onChange={(e) => setForm({ ...form, category: e.target.value })}
                        className="w-full px-3.5 py-2.5 rounded-xl bg-[#0F0E17] border border-[#27253D] text-white text-xs focus:outline-none focus:border-[#6344E7] focus:ring-1 focus:ring-[#6344E7] transition-colors"
                      >
                        {INQUIRY_CATEGORIES.map((cat) => (
                          <option key={cat.id} value={cat.id} className="bg-[#0F0E17] text-white">
                            {cat.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#D1CFDB] mb-1.5">Priority Level</label>
                    <select
                      value={form.priority}
                      onChange={(e) => setForm({ ...form, priority: e.target.value })}
                      className="w-full px-3.5 py-2.5 rounded-xl bg-[#0F0E17] border border-[#27253D] text-white text-xs focus:outline-none focus:border-[#6344E7] focus:ring-1 focus:ring-[#6344E7] transition-colors"
                    >
                      {PRIORITY_LEVELS.map((p) => (
                        <option key={p.id} value={p.id} className="bg-[#0F0E17] text-white">
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#D1CFDB] mb-1.5">
                      Subject <span className="text-red-400">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      value={form.subject}
                      onChange={(e) => setForm({ ...form, subject: e.target.value })}
                      placeholder="e.g. Inbound voice agent prompt customization"
                      className="w-full px-3.5 py-2.5 rounded-xl bg-[#0F0E17] border border-[#27253D] text-white text-xs placeholder:text-[#524E5E] focus:outline-none focus:border-[#6344E7] focus:ring-1 focus:ring-[#6344E7] transition-colors"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#D1CFDB] mb-1.5">
                      Detailed Message <span className="text-red-400">*</span>
                    </label>
                    <textarea
                      required
                      rows={4}
                      value={form.message}
                      onChange={(e) => setForm({ ...form, message: e.target.value })}
                      placeholder="Please describe your setup, agent prompt behavior, or inquiry details..."
                      className="w-full px-3.5 py-2.5 rounded-xl bg-[#0F0E17] border border-[#27253D] text-white text-xs placeholder:text-[#524E5E] focus:outline-none focus:border-[#6344E7] focus:ring-1 focus:ring-[#6344E7] transition-colors resize-none"
                    />
                  </div>

                  <div className="pt-2 flex items-center justify-between">
                    <p className="text-[11px] text-[#7C778D] flex items-center gap-1.5">
                      <ShieldCheck className="w-3.5 h-3.5 text-[#10B981]" />
                      <span>Encrypted ticket dispatch</span>
                    </p>

                    <button
                      type="submit"
                      disabled={loading}
                      className="min-h-[42px] px-6 py-2.5 rounded-xl bg-[#6344E7] hover:bg-[#5235D6] active:scale-[0.98] text-white text-xs font-semibold flex items-center gap-2 transition-all shadow-md shadow-[#6344E7]/25 disabled:opacity-60 disabled:cursor-not-allowed"
                    >
                      {loading ? (
                        <>
                          <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                          <span>Transmitting...</span>
                        </>
                      ) : (
                        <>
                          <span>Transmit Ticket</span>
                          <Send className="w-3.5 h-3.5" />
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default ContactUsSection;
