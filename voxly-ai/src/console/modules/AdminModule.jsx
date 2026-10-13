import React, { useState, useEffect, useCallback } from 'react';
import {
  Shield,
  Users,
  Phone,
  Building2,
  Wallet,
  Minus,
  Plus,
  Radio,
  Server,
  CheckCircle2,
  AlertCircle,
  Trash2,
  Lock,
  Unlock,
  Search,
  ShoppingCart,
  RefreshCw,
  Globe,
  Sliders,
  Check,
  AlertTriangle,
  ChevronRight,
  Headphones,
  Mail,
  Clock,
  LifeBuoy,
  MessageSquare,
  FileText,
  X,
  Send,
  Share2,
  Tag,
  ExternalLink,
  AtSign,
} from 'lucide-react';
import { api } from '../../services/api';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { AdminMetricsSkeleton } from '../ui/Skeleton';
import { showToast } from '../ui/ToastHost';

function moneyUsd(cents) {
  return `$${(Number(cents || 0) / 100).toFixed(2)}`;
}

function walletUsdCents(t) {
  if (t?.balanceUsdCents != null) return Number(t.balanceUsdCents) || 0;
  return Number(t?.balanceCents) || 0;
}

export function AdminModule({ activeSection = 'tenants', onSelectSection } = {}) {
  const [internalSection, setInternalSection] = useState(activeSection || 'tenants');
  const section = onSelectSection ? (activeSection || 'tenants') : internalSection;
  const setSection = (nextSec) => {
    if (onSelectSection) {
      onSelectSection(nextSec);
    } else {
      setInternalSection(nextSec);
    }
  };

  const [overview, setOverview] = useState(null);
  const [tenants, setTenants] = useState([]);
  const [error, setError] = useState(null);
  const [grantTenant, setGrantTenant] = useState('');
  const [grantUsd, setGrantUsd] = useState('50');
  const [busy, setBusy] = useState(false);
  const [telephonyInfo, setTelephonyInfo] = useState(null);
  const [providerBusy, setProviderBusy] = useState(false);

  // Tenant action states
  const [tenantStatusBusyId, setTenantStatusBusyId] = useState(null);
  const [deleteConfirmTenant, setDeleteConfirmTenant] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  // Platform Phone Number Management states
  const [phoneNumbers, setPhoneNumbers] = useState([]);
  const [phoneNumbersLoading, setPhoneNumbersLoading] = useState(false);
  const [releaseBusyId, setReleaseBusyId] = useState(null);

  // Direct Carrier Phone Buying states
  const [buyProvider, setBuyProvider] = useState('vobiz');
  const [buyCountry, setBuyCountry] = useState('US');
  const [carrierResults, setCarrierResults] = useState([]);
  const [carrierSearchLoading, setCarrierSearchLoading] = useState(false);
  const [adminBuyTargetTenant, setAdminBuyTargetTenant] = useState('');
  const [buyingNumberE164, setBuyingNumberE164] = useState(null);

  // Test Call states
  const [testCallTo, setTestCallTo] = useState('+918897908470');
  const [testCallFrom, setTestCallFrom] = useState('+917965480745');
  const [testCallBusy, setTestCallBusy] = useState(false);
  const [testCallResult, setTestCallResult] = useState(null);

  // Customer Support Flow & Inquiry states
  const [supportConfig, setSupportConfig] = useState({
    supportEmail: 'support@dialtact.com',
    businessHours: 'Mon - Fri: 9:00 AM - 6:00 PM EST',
    slaResponseTime: 'Within 2 hours for Priority, 24 hours Standard',
    autoReplyMessage: 'Thank you for reaching out. A support specialist has received your inquiry.',
    isActive: true,
    twitterUrl: 'https://x.com/dialtact',
    linkedinUrl: 'https://linkedin.com/company/dialtact',
    githubUrl: 'https://github.com/dialtact',
    youtubeUrl: 'https://youtube.com/@dialtact',
    discordUrl: 'https://discord.gg/dialtact',
    smtpHost: '',
    smtpPort: 587,
    smtpUsername: '',
    smtpPassword: '',
    smtpUseTls: true,
    senderEmail: 'support@dialtact.com',
    senderName: 'Dialtact Support Desk',
    notifyCustomerOnTicket: true,
    notifyAdminOnTicket: true,
    adminAlertEmail: 'support@dialtact.com',
  });
  const [supportConfigBusy, setSupportConfigBusy] = useState(false);
  const [supportSubTab, setSupportSubTab] = useState('tickets'); // 'tickets' | 'channels' | 'mail'
  const [supportInquiries, setSupportInquiries] = useState([]);
  const [supportInquiriesLoading, setSupportInquiriesLoading] = useState(false);
  const [inquiryFilter, setInquiryFilter] = useState('all');
  const [inquiryPriorityFilter, setInquiryPriorityFilter] = useState('all');
  const [inquiryCategoryFilter, setInquiryCategoryFilter] = useState('all');
  const [inquirySearch, setInquirySearch] = useState('');
  const [inquiryStatusBusyId, setInquiryStatusBusyId] = useState(null);
  const [activeInquiryDetail, setActiveInquiryDetail] = useState(null);
  const [adminNoteInput, setAdminNoteInput] = useState('');
  const [assigneeInput, setAssigneeInput] = useState('');
  const [customerReplyInput, setCustomerReplyInput] = useState('');
  const [replySending, setReplySending] = useState(false);
  const [smtpTesting, setSmtpTesting] = useState(false);
  const [smtpTestResult, setSmtpTestResult] = useState(null);

  const handleTestCall = async () => {
    if (!testCallTo.trim()) {
      showToast('Enter destination phone number in E.164 format', 'error');
      return;
    }
    setTestCallBusy(true);
    setTestCallResult(null);
    try {
      const res = await api.admin.triggerTestCall({
        toE164: testCallTo.trim(),
        fromE164: testCallFrom.trim() || null,
        provider: telephonyInfo?.activeProvider || 'vobiz',
      });
      setTestCallResult(res);
      showToast(`Test call initiated via ${res.provider?.toUpperCase()}! Call UUID: ${res.call_uuid?.slice(0, 8)}...`, 'success');
    } catch (err) {
      showToast(err.message || 'Test call failed', 'error');
      setTestCallResult({ ok: false, error: err.message });
    } finally {
      setTestCallBusy(false);
    }
  };

  const handleSaveSupportConfig = async (e) => {
    if (e && e.preventDefault) e.preventDefault();
    setSupportConfigBusy(true);
    try {
      const updated = await api.admin.updateSupportConfig(supportConfig);
      if (updated && updated.configKey) {
        setSupportConfig((prev) => ({ ...prev, ...updated }));
      }
      showToast('Support configuration, social links & mail settings saved successfully!', 'success');
    } catch (err) {
      showToast(err.message || 'Failed to update support configuration', 'error');
    } finally {
      setSupportConfigBusy(false);
    }
  };

  const handleTestSmtp = async () => {
    if (!supportConfig.smtpHost) {
      showToast('Please provide an SMTP Host before testing connection', 'error');
      return;
    }
    setSmtpTesting(true);
    setSmtpTestResult(null);
    try {
      const res = await api.admin.testSmtpConnection({
        smtpHost: supportConfig.smtpHost,
        smtpPort: supportConfig.smtpPort,
        smtpUsername: supportConfig.smtpUsername,
        smtpPassword: supportConfig.smtpPassword,
        smtpUseTls: supportConfig.smtpUseTls,
      });
      setSmtpTestResult({ success: true, message: res.message || 'SMTP connected successfully!' });
      showToast('SMTP Mail Gateway verified successfully!', 'success');
    } catch (err) {
      const msg = err.message || 'SMTP connection failed';
      setSmtpTestResult({ success: false, error: msg });
      showToast(msg, 'error');
    } finally {
      setSmtpTesting(false);
    }
  };

  const handleUpdateInquiryStatus = async (inquiryId, status, notes = null, assignedTo = null) => {
    setInquiryStatusBusyId(inquiryId);
    try {
      const updated = await api.admin.updateSupportInquiry(inquiryId, {
        status,
        adminNotes: notes != null ? notes : undefined,
        assignedTo: assignedTo != null ? assignedTo : undefined,
      });
      setSupportInquiries((prev) =>
        prev.map((inq) => (inq.id === inquiryId ? { ...inq, ...updated } : inq))
      );
      if (activeInquiryDetail && activeInquiryDetail.id === inquiryId) {
        setActiveInquiryDetail((prev) => ({ ...prev, ...updated }));
      }
      showToast(`Inquiry updated (${status.toUpperCase()})`, 'success');
    } catch (err) {
      showToast(err.message || 'Failed to update inquiry status', 'error');
    } finally {
      setInquiryStatusBusyId(null);
    }
  };

  const handleSendCustomerReply = async (inquiryId) => {
    if (!customerReplyInput.trim()) {
      showToast('Please enter a response message', 'error');
      return;
    }
    setReplySending(true);
    try {
      const nextStatus = activeInquiryDetail?.status === 'new' ? 'in_progress' : activeInquiryDetail?.status;
      const updated = await api.admin.updateSupportInquiry(inquiryId, {
        replyMessage: customerReplyInput.trim(),
        status: nextStatus,
        adminNotes: adminNoteInput || undefined,
        assignedTo: assigneeInput || undefined,
      });
      setCustomerReplyInput('');
      setSupportInquiries((prev) =>
        prev.map((inq) => (inq.id === inquiryId ? { ...inq, ...updated } : inq))
      );
      if (activeInquiryDetail && activeInquiryDetail.id === inquiryId) {
        setActiveInquiryDetail((prev) => ({ ...prev, ...updated }));
      }
      showToast('Reply dispatched to customer successfully!', 'success');
    } catch (err) {
      showToast(err.message || 'Failed to dispatch reply', 'error');
    } finally {
      setReplySending(false);
    }
  };

  const refreshInquiries = async () => {
    setSupportInquiriesLoading(true);
    try {
      const inq = await api.admin.listSupportInquiries({
        status: inquiryFilter === 'all' ? null : inquiryFilter,
        priority: inquiryPriorityFilter === 'all' ? null : inquiryPriorityFilter,
        category: inquiryCategoryFilter === 'all' ? null : inquiryCategoryFilter,
        search: inquirySearch || null,
      });
      setSupportInquiries(inq);
      showToast('Inquiry tickets refreshed', 'success');
    } catch (err) {
      showToast('Could not refresh inquiries', 'error');
    } finally {
      setSupportInquiriesLoading(false);
    }
  };

  const load = useCallback(async () => {
    setError(null);
    try {
      const [dash, list, tel, phones, supCfg, supInq] = await Promise.all([
        api.admin.overview(),
        api.admin.tenants(),
        api.telephony.getProvider().catch(() => null),
        api.admin.listPhoneNumbers().catch(() => []),
        api.admin.getSupportConfig().catch(() => null),
        api.admin.listSupportInquiries().catch(() => []),
      ]);
      setOverview(dash);
      setTenants(list);
      if (tel) {
        setTelephonyInfo(tel);
        if (tel.activeProvider) {
          setBuyProvider(tel.activeProvider);
        }
      }
      setPhoneNumbers(phones);
      if (supCfg && Object.keys(supCfg).length > 0) {
        setSupportConfig((prev) => ({ ...prev, ...supCfg }));
      }
      if (supInq) {
        setSupportInquiries(supInq);
      }
    } catch (e) {
      setError(e.message || 'Admin API access denied');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!grantTenant && tenants[0]?.tenantId) {
      setGrantTenant(tenants[0].tenantId);
    }
    if (!adminBuyTargetTenant && tenants[0]?.tenantId) {
      setAdminBuyTargetTenant(tenants[0].tenantId);
    }
  }, [tenants, grantTenant, adminBuyTargetTenant]);

  const selected = tenants.find((t) => t.tenantId === grantTenant);
  const fxRateInr = Number(selected?.fxRateInr || tenants.find((t) => t.fxRateInr)?.fxRateInr) || 0;

  const adjust = async (sign) => {
    const usd = Math.abs(Number(grantUsd));
    if (!grantTenant || !Number.isFinite(usd) || usd <= 0) return;
    if (!fxRateInr) {
      showToast('No USD/INR rate available — cannot convert the amount', 'error');
      return;
    }
    const usdCents = Math.round(usd * 100);
    const paise = Math.round(usd * fxRateInr * 100) * (sign < 0 ? -1 : 1);
    setBusy(true);
    try {
      await api.admin.grantCredits({
        tenantId: grantTenant,
        amountInrPaise: paise,
        reason: sign < 0 ? 'admin_debit' : 'admin_grant',
      });
      showToast(
        sign < 0 ? `Debited ${moneyUsd(usdCents)}` : `Credited ${moneyUsd(usdCents)}`,
        'success'
      );
      await load();
    } catch (e) {
      showToast(e.message || 'Wallet adjust failed', 'error');
    } finally {
      setBusy(false);
    }
  };

  const switchProvider = async (providerId) => {
    if (providerBusy || telephonyInfo?.activeProvider === providerId) return;
    setProviderBusy(true);
    try {
      await api.admin.setTelephonyProvider(providerId);
      showToast(`Switched active calling trunk to ${providerId.toUpperCase()}`, 'success');
      const updated = await api.telephony.getProvider();
      setTelephonyInfo(updated);
      setBuyProvider(providerId);
      await load();
    } catch (e) {
      showToast(e.message || 'Failed to switch telephony infrastructure', 'error');
    } finally {
      setProviderBusy(false);
    }
  };

  // Toggle Tenant Block / Unblock status
  const toggleTenantStatus = async (tenant) => {
    const isProtected = String(tenant.name || '').toLowerCase().includes('mohan saiteja');
    if (isProtected && tenant.status === 'active') {
      showToast("Primary workspace [mohan saiteja's Workspace] is protected and cannot be blocked.", 'error');
      return;
    }
    const nextStatus = tenant.status === 'active' ? 'suspended' : 'active';
    setTenantStatusBusyId(tenant.tenantId);
    try {
      await api.admin.updateTenantStatus(tenant.tenantId, nextStatus);
      showToast(
        nextStatus === 'active' ? `Unblocked ${tenant.name}` : `Blocked ${tenant.name}`,
        'success'
      );
      await load();
    } catch (e) {
      showToast(e.message || 'Failed to update tenant status', 'error');
    } finally {
      setTenantStatusBusyId(null);
    }
  };

  // Delete Tenant Permanently
  const confirmDeleteTenant = async () => {
    if (!deleteConfirmTenant) return;
    const isProtected = String(deleteConfirmTenant.name || '').toLowerCase().includes('mohan saiteja');
    if (isProtected) {
      showToast("Primary workspace [mohan saiteja's Workspace] is protected and cannot be deleted.", 'error');
      setDeleteConfirmTenant(null);
      return;
    }
    setDeleteBusy(true);
    try {
      await api.admin.deleteTenant(deleteConfirmTenant.tenantId);
      showToast(`Workspace "${deleteConfirmTenant.name}" has been permanently removed`, 'success');
      setDeleteConfirmTenant(null);
      await load();
    } catch (e) {
      showToast(e.message || 'Failed to delete workspace', 'error');
    } finally {
      setDeleteBusy(false);
    }
  };

  // Search Carrier Numbers (Vobiz or Telnyx)
  const searchCarrier = async () => {
    setCarrierSearchLoading(true);
    setCarrierResults([]);
    try {
      const results = await api.admin.searchCarrierNumbers(buyProvider, buyCountry);
      setCarrierResults(results);
      if (results.length === 0) {
        showToast(`No numbers found for ${buyCountry} on ${buyProvider.toUpperCase()}`, 'info');
      }
    } catch (e) {
      showToast(e.message || 'Failed to search carrier numbers', 'error');
    } finally {
      setCarrierSearchLoading(false);
    }
  };

  // Buy and Provision Number directly in Admin panel
  const handleAdminBuyNumber = async (item) => {
    const e164 = item.e164 || item.phone_number;
    if (!e164) return;
    setBuyingNumberE164(e164);
    try {
      await api.admin.buyPhoneNumber({
        e164,
        provider: buyProvider,
        country: buyCountry,
        tenantId: adminBuyTargetTenant || tenants[0]?.tenantId,
      });
      showToast(`Provisioned ${e164} on ${buyProvider.toUpperCase()} directly to workspace`, 'success');
      setCarrierResults((prev) => prev.filter((n) => (n.e164 || n.phone_number) !== e164));
      await load();
    } catch (e) {
      showToast(e.message || 'Failed to provision carrier number', 'error');
    } finally {
      setBuyingNumberE164(null);
    }
  };

  // Release Phone Number
  const handleReleaseNumber = async (numberId, e164) => {
    if (!window.confirm(`Are you sure you want to release ${e164}?`)) return;
    setReleaseBusyId(numberId);
    try {
      await api.admin.releasePhoneNumber(numberId);
      showToast(`Released line ${e164}`, 'success');
      await load();
    } catch (e) {
      showToast(e.message || 'Failed to release line', 'error');
    } finally {
      setReleaseBusyId(null);
    }
  };

  const ADMIN_SECTIONS = [
    {
      id: 'tenants',
      label: 'Workspaces & Balances',
      icon: Building2,
      badge: `${tenants.length} Workspaces`,
      title: 'Platform Workspaces & Account Balances',
      desc: 'Global management of subscriber workspaces, account blocking / unblocking, and platform credits.',
    },
    {
      id: 'telephony',
      label: 'Carriers & Lines',
      icon: Radio,
      badge: `${phoneNumbers.length} Lines`,
      title: 'Telephony Infrastructure & Carrier Lines',
      desc: 'Direct Voice Networks, Canary live call testing, and DID number purchasing.',
    },
    {
      id: 'support',
      label: 'Support Tickets Desk',
      icon: Headphones,
      badge: `${supportInquiries.filter((i) => i.status !== 'resolved' && i.status !== 'closed').length} Open`,
      title: 'Customer Support Desk & Ticket Operations',
      desc: 'Manage incoming support inquiries and tickets raised by prospective customers and tenant workspaces.',
    },
    {
      id: 'social',
      label: 'Social Media & Channels',
      icon: Share2,
      badge: 'Public Links',
      title: 'Channels & Social Media Management',
      desc: 'Configure official public contact channels, operating hours, and social media hyperlinks rendered in the website footer.',
    },
    {
      id: 'mail',
      label: 'Mail Gateway & SMTP',
      icon: Mail,
      badge: supportConfig.smtpHost ? 'Active Gateway' : 'Local Mock',
      title: 'Mail Gateway & SMTP Configuration',
      desc: 'Configure transactional SMTP mail server credentials, ticket confirmations, and staff alert routing.',
    },
  ];

  const currentMeta = ADMIN_SECTIONS.find((s) => s.id === section) || ADMIN_SECTIONS[0];

  return (
    <div className="space-y-6" data-testid="admin-wallet-panel">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">{currentMeta.title}</h2>
          <p className="text-xs text-[#524E5E] mt-1">
            {currentMeta.desc}
          </p>
        </div>
        <TactileButton
          variant="secondary"
          size="sm"
          onClick={load}
          className="text-xs shrink-0 self-start sm:self-auto"
        >
          <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
          Refresh Console
        </TactileButton>
      </div>

      {/* Category Navigation Bar */}
      <div className="flex items-center gap-1.5 p-1 rounded-2xl bg-[#F0EEF6] border border-[#E4E2EB] overflow-x-auto scrollbar-none" data-testid="admin-section-nav">
        {ADMIN_SECTIONS.map((s) => {
          const Icon = s.icon;
          const isActive = section === s.id;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => setSection(s.id)}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all whitespace-nowrap shrink-0 ${
                isActive
                  ? 'bg-white text-[#0F0E17] shadow-xs border border-[#E4E2EB]'
                  : 'text-[#524E5E] hover:text-[#0F0E17] hover:bg-white/50'
              }`}
            >
              <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-[#6344E7]' : 'text-[#8C879A]'}`} />
              <span>{s.label}</span>
              {s.badge && (
                <span
                  className={`text-[10px] px-2 py-0.5 rounded-full font-mono font-semibold ${
                    isActive
                      ? 'bg-[#6344E7]/10 text-[#6344E7]'
                      : 'bg-[#E4E2EB] text-[#524E5E]'
                  }`}
                >
                  {s.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-800 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-red-600" />
          <span>{error}</span>
        </div>
      )}

      {/* SECTION 1: Workspaces & Balances */}
      {section === 'tenants' && (
        <div className="space-y-6">
          {/* Metrics Row */}
          {overview ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                ['Workspaces', overview.tenants, Building2],
                ['Users', overview.users, Users],
                ['Active Phone Lines', overview.activeNumbers, Phone],
                ['Failed Orders', overview.failedPurchases, Shield],
              ].map(([label, value, Icon]) => (
                <SolidCard key={label} className="p-4">
                  <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-[#8C879A]">
                    <Icon className="w-3.5 h-3.5" />
                    {label}
                  </div>
                  <p className="text-2xl font-mono font-bold text-[#0F0E17] mt-2">{value}</p>
                </SolidCard>
              ))}
            </div>
          ) : (
            <AdminMetricsSkeleton count={4} />
          )}

          {/* Workspaces & Tenants Management Table */}
          <SolidCard padding="p-0" className="overflow-hidden">
            <div className="p-4 border-b border-[#E4E2EB] flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <div>
                <h3 className="text-sm font-bold text-[#0F0E17]">Platform Workspaces</h3>
                <p className="text-[11px] text-[#524E5E] mt-0.5">
                  Manage subscriber workspaces, control account status (Block / Unblock), and remove test workspaces.
                </p>
              </div>
              <span className="text-xs font-mono px-2.5 py-1 rounded-full bg-[#FAF9FD] border border-[#E4E2EB] text-[#524E5E]">
                Total: {tenants.length}
              </span>
            </div>

            <div className="overflow-x-auto scrollbar-none touch-pan-x">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[10px] font-bold text-[#8C879A] uppercase">
                    <th className="py-3 px-4">Workspace Name</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4 font-mono">Wallet (USD)</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E4E2EB]">
                  {tenants.map((t) => {
                    const isProtected = String(t.name || '').toLowerCase().includes('mohan saiteja');
                    const isBusy = tenantStatusBusyId === t.tenantId;
                    const isActive = t.status === 'active';

                    return (
                      <tr key={t.tenantId} data-testid={`admin-tenant-row-${t.tenantId}`} className="hover:bg-[#FAF9FD]/50">
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-[#0F0E17]">{t.name}</span>
                            {isProtected && (
                              <span className="inline-flex items-center gap-1 text-[10px] font-bold bg-[#6344E7]/10 text-[#6344E7] border border-[#6344E7]/20 px-2 py-0.5 rounded-full">
                                <Shield className="w-2.5 h-2.5" /> Primary Workspace
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          {isActive ? (
                            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full">
                              <Check className="w-3 h-3" /> Active
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-700 bg-amber-50 border border-amber-200 px-2.5 py-0.5 rounded-full">
                              <Lock className="w-3 h-3" /> Blocked ({t.status})
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 font-mono font-bold text-[#0F0E17]">
                          {moneyUsd(walletUsdCents(t))}
                        </td>
                        <td className="py-3 px-4 text-right">
                          {isProtected ? (
                            <span className="text-[11px] text-[#8C879A] italic">Protected System Workspace</span>
                          ) : (
                            <div className="flex items-center justify-end gap-2">
                              <button
                                type="button"
                                onClick={() => toggleTenantStatus(t)}
                                disabled={isBusy}
                                className={`inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border font-medium transition-colors ${
                                  isActive
                                    ? 'border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100'
                                    : 'border-emerald-200 bg-emerald-50 text-emerald-800 hover:bg-emerald-100'
                                }`}
                              >
                                {isActive ? (
                                  <>
                                    <Lock className="w-3 h-3" /> Block
                                  </>
                                ) : (
                                  <>
                                    <Unlock className="w-3 h-3" /> Unblock
                                  </>
                                )}
                              </button>
                              <button
                                type="button"
                                onClick={() => setDeleteConfirmTenant(t)}
                                className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border border-red-200 bg-red-50 text-red-700 hover:bg-red-100 font-medium transition-colors"
                              >
                                <Trash2 className="w-3 h-3" /> Delete
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </SolidCard>

          {/* Adjust Wallet Balance Card */}
          <SolidCard className="p-5 space-y-4">
            <div className="flex items-center gap-2">
              <Wallet className="w-4 h-4 text-[#6344E7]" />
              <h3 className="text-sm font-bold text-[#0F0E17]">Adjust Workspace Balance (USD)</h3>
            </div>
            {selected && (
              <p className="text-[11px] text-[#524E5E]" data-testid="admin-selected-wallet">
                Selected: <span className="font-semibold text-[#0F0E17]">{selected.name}</span> · Current Balance:{' '}
                <span className="font-mono font-bold text-[#0F0E17]">{moneyUsd(walletUsdCents(selected))}</span>
              </p>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
              <select
                value={grantTenant}
                onChange={(e) => setGrantTenant(e.target.value)}
                data-testid="admin-tenant-select"
                className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-base sm:text-xs min-h-[42px] sm:min-h-[36px] sm:col-span-2 text-[#0F0E17]"
              >
                {tenants.map((t) => (
                  <option key={t.tenantId} value={t.tenantId}>
                    {t.name} — {moneyUsd(walletUsdCents(t))}
                  </option>
                ))}
              </select>
              <input
                type="number"
                min="1"
                value={grantUsd}
                onChange={(e) => setGrantUsd(e.target.value)}
                data-testid="admin-credit-amount"
                className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-base sm:text-xs min-h-[42px] sm:min-h-[36px] font-mono text-[#0F0E17]"
                placeholder="Amount USD"
              />
              <div className="flex gap-2">
                <TactileButton
                  variant="primary"
                  size="sm"
                  loading={busy}
                  onClick={() => adjust(1)}
                  data-testid="admin-credit-add"
                  className="flex-1 sm:flex-initial min-h-[42px] sm:min-h-[36px]"
                >
                  <Plus className="w-3.5 h-3.5 mr-1" />
                  Add
                </TactileButton>
                <TactileButton
                  variant="secondary"
                  size="sm"
                  loading={busy}
                  onClick={() => adjust(-1)}
                  data-testid="admin-credit-debit"
                  className="flex-1 sm:flex-initial min-h-[42px] sm:min-h-[36px]"
                >
                  <Minus className="w-3.5 h-3.5 mr-1" />
                  Debit
                </TactileButton>
              </div>
            </div>
          </SolidCard>
        </div>
      )}

      {/* SECTION 2: Carriers & Lines */}
      {section === 'telephony' && (
        <div className="space-y-6">
          {/* Telephony Infrastructure Selection Card */}
          <SolidCard className="p-5 space-y-4" data-testid="admin-telephony-card">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-[#6344E7]" />
            <h3 className="text-sm font-bold text-[#0F0E17]">Active Telephony Infrastructure</h3>
            <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-[#6344E7]/10 text-[#6344E7] font-semibold">
              Live Gateway
            </span>
          </div>
          {telephonyInfo && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-[#8C879A]">Current Primary:</span>
              <span className="font-bold text-[#0F0E17] uppercase tracking-wide">
                {telephonyInfo.activeLabel || telephonyInfo.activeProvider}
              </span>
              {telephonyInfo.ready ? (
                <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full font-medium">
                  <CheckCircle2 className="w-3 h-3" /> Ready
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full font-medium">
                  <AlertCircle className="w-3 h-3" /> Incomplete
                </span>
              )}
            </div>
          )}
        </div>

        <p className="text-xs text-[#524E5E]">
          Switching the provider updates all outbound dialing, inbound webhooks, and phone number purchasing workflows in real time.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
          {(telephonyInfo?.providers || [
            { id: 'vobiz', label: 'Primary Voice Network', enabled: true, ready: true },
            { id: 'telnyx', label: 'International Voice Trunk', enabled: true, ready: false },
          ]).map((p) => {
            const isActive = (telephonyInfo?.activeProvider || 'vobiz') === p.id;
            const displayLabel = p.id === 'vobiz' ? 'Primary Voice Network' : (p.id === 'telnyx' ? 'International Voice Trunk' : p.label);
            return (
              <div
                key={p.id}
                className={`relative rounded-xl border p-4 transition-all ${
                  isActive
                    ? 'border-[#6344E7] bg-[#6344E7]/5 ring-1 ring-[#6344E7]'
                    : 'border-[#E4E2EB] bg-[#FAF9FD] hover:border-[#8C879A]'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Server className="w-4 h-4 text-[#524E5E]" />
                    <span className="text-sm font-bold text-[#0F0E17]">{displayLabel}</span>
                  </div>
                  {isActive && (
                    <span className="text-[10px] uppercase font-bold text-[#6344E7] bg-[#6344E7]/10 px-2 py-0.5 rounded font-mono">
                      Active Trunk
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-[#524E5E] space-y-1 mb-3 font-mono">
                  <div>
                    Caller ID:{' '}
                    <span className="text-[#0F0E17] font-semibold">{p.phoneNumber || 'Dynamic Pool'}</span>
                  </div>
                  <div>
                    Endpoints:{' '}
                    <span className="text-[#0F0E17]">
                      Direct Voice Gateway
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    Status:{' '}
                    <span className={p.ready ? 'text-emerald-700 font-medium' : 'text-[#8C879A]'}>
                      {p.ready ? 'Live & Handshake Verified' : p.enabled ? 'Credentials Present' : 'Disabled'}
                    </span>
                  </div>
                </div>
                <TactileButton
                  variant={isActive ? 'primary' : 'secondary'}
                  size="sm"
                  className="w-full text-xs"
                  disabled={isActive || providerBusy}
                  loading={providerBusy && !isActive}
                  onClick={() => switchProvider(p.id)}
                >
                  {isActive ? 'Currently Active Trunk' : `Switch Platform to ${p.label}`}
                </TactileButton>
              </div>
            );
          })}
        </div>
      </SolidCard>

      {/* Telephony Canary & Live Test Call Card */}
      <SolidCard className="p-5 space-y-4" data-testid="admin-test-call-card">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-[#6344E7]" />
            <h3 className="text-sm font-bold text-[#0F0E17]">Live Telephony Test Call (Canary Probe)</h3>
          </div>
          <span className="text-xs font-mono font-medium text-[#6344E7] bg-[#6344E7]/10 px-2 py-0.5 rounded">
            Trunk: Enterprise Voice Line
          </span>
        </div>
        <p className="text-xs text-[#524E5E]">
          Dispatch a live PSTN voice call to test carrier connectivity, audio streaming WebSocket, and VoiceXML instructions.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="text-[11px] font-semibold text-[#524E5E] block mb-1">
              Destination Phone Number (To)
            </label>
            <input
              type="text"
              className="w-full text-xs font-mono border border-[#E4E2EB] rounded-lg px-3 py-2 bg-white text-[#0F0E17]"
              value={testCallTo}
              onChange={(e) => setTestCallTo(e.target.value)}
              placeholder="+918897908470"
              data-testid="admin-test-call-to"
            />
          </div>
          <div>
            <label className="text-[11px] font-semibold text-[#524E5E] block mb-1">
              Outbound Caller ID (From / Available Lines)
            </label>
            {phoneNumbers.length > 0 ? (
              <select
                className="w-full text-xs font-mono border border-[#E4E2EB] rounded-lg px-3 py-2 bg-white text-[#0F0E17]"
                value={testCallFrom}
                onChange={(e) => setTestCallFrom(e.target.value)}
                data-testid="admin-test-call-from"
              >
                {phoneNumbers.map((p) => {
                  const val = p.e164 || p.number;
                  const prov = 'DIRECT LINE';
                  return (
                    <option key={p.id || val} value={val}>
                      {val} • {prov} ({p.tenantName || 'Workspace'})
                    </option>
                  );
                })}
              </select>
            ) : (
              <input
                type="text"
                className="w-full text-xs font-mono border border-[#E4E2EB] rounded-lg px-3 py-2 bg-white text-[#0F0E17]"
                value={testCallFrom}
                onChange={(e) => setTestCallFrom(e.target.value)}
                placeholder="+917965480745"
                data-testid="admin-test-call-from"
              />
            )}
          </div>
        </div>

        <div className="flex items-center justify-between pt-1">
          <div className="text-[11px] text-[#524E5E]">
            {testCallResult?.ok ? (
              <span className="text-emerald-700 font-medium inline-flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> Call Active (UUID: {testCallResult.call_uuid?.slice(0, 12)}...)
              </span>
            ) : testCallResult?.error ? (
              <span className="text-rose-600 font-medium inline-flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5" /> {testCallResult.error}
              </span>
            ) : (
              <span>Ready to dial destination via enterprise voice trunk</span>
            )}
          </div>
          <TactileButton
            variant="primary"
            size="sm"
            loading={testCallBusy}
            disabled={testCallBusy || !testCallTo.trim()}
            onClick={handleTestCall}
            data-testid="admin-test-call-submit"
          >
            Initiate Test Call
          </TactileButton>
        </div>
      </SolidCard>

      {/* Admin Carrier Phone Buying & Provisioning Panel */}
      <SolidCard className="p-5 space-y-4" data-testid="admin-phone-buy-card">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div className="flex items-center gap-2">
            <ShoppingCart className="w-4 h-4 text-[#6344E7]" />
            <h3 className="text-sm font-bold text-[#0F0E17]">Carrier Number Acquisition & Provisioning</h3>
            <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-semibold border border-emerald-200">
              Admin Direct Buy
            </span>
          </div>
        </div>

        <p className="text-xs text-[#524E5E]">
          Search live phone numbers directly across global voice inventories and provision them directly into any workspace.
        </p>

        {/* Carrier Search Filter Controls */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
          <div>
            <label className="block text-[10px] font-bold text-[#8C879A] uppercase mb-1">Voice Network</label>
            <select
              value={buyProvider}
              onChange={(e) => setBuyProvider(e.target.value)}
              className="w-full bg-white border border-[#E4E2EB] rounded-lg p-2 text-xs text-[#0F0E17] font-semibold focus:outline-none focus:border-[#6344E7]"
            >
              <option value="vobiz">Primary Network (India & Regional)</option>
              <option value="telnyx">International Network (Global)</option>
            </select>
          </div>

          <div>
            <label className="block text-[10px] font-bold text-[#8C879A] uppercase mb-1">Country</label>
            <select
              value={buyCountry}
              onChange={(e) => setBuyCountry(e.target.value)}
              className="w-full bg-white border border-[#E4E2EB] rounded-lg p-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
            >
              <option value="US">United States (+1)</option>
              <option value="IN">India (+91)</option>
              <option value="GB">United Kingdom (+44)</option>
              <option value="CA">Canada (+1)</option>
              <option value="AU">Australia (+61)</option>
            </select>
          </div>

          <div>
            <label className="block text-[10px] font-bold text-[#8C879A] uppercase mb-1">Target Workspace</label>
            <select
              value={adminBuyTargetTenant}
              onChange={(e) => setAdminBuyTargetTenant(e.target.value)}
              className="w-full bg-white border border-[#E4E2EB] rounded-lg p-2 text-xs text-[#0F0E17] font-medium focus:outline-none focus:border-[#6344E7]"
            >
              {tenants.map((t) => (
                <option key={t.tenantId} value={t.tenantId}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-end">
            <TactileButton
              variant="primary"
              size="sm"
              loading={carrierSearchLoading}
              onClick={searchCarrier}
              className="w-full text-xs min-h-[34px]"
            >
              <Search className="w-3.5 h-3.5 mr-1" />
              Search Carrier DIDs
            </TactileButton>
          </div>
        </div>

        {/* Carrier Search Results List */}
        {carrierResults.length > 0 && (
          <div className="space-y-2 pt-1 max-h-60 overflow-y-auto">
            <div className="text-xs font-semibold text-[#0F0E17] px-1">
              Available Numbers on {buyProvider.toUpperCase()} ({carrierResults.length}):
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {carrierResults.map((item) => {
                const num = item.e164 || item.phone_number;
                const isBuying = buyingNumberE164 === num;
                return (
                  <div
                    key={num}
                    className="flex items-center justify-between p-3 rounded-xl bg-white border border-[#E4E2EB] shadow-2xs hover:border-[#6344E7] transition-all"
                  >
                    <div>
                      <div className="font-mono font-bold text-xs text-[#0F0E17]">{num}</div>
                      <div className="text-[10px] text-[#524E5E]">
                        {item.country || buyCountry} • {item.type || 'Local DID'} •{' '}
                        <span className="uppercase text-[#6344E7] font-semibold">{buyProvider}</span>
                      </div>
                    </div>
                    <TactileButton
                      variant="primary"
                      size="xs"
                      disabled={isBuying || Boolean(buyingNumberE164)}
                      loading={isBuying}
                      onClick={() => handleAdminBuyNumber(item)}
                      className="text-xs"
                    >
                      {isBuying ? 'Ordering…' : 'Order & Assign'}
                    </TactileButton>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Existing Platform Numbers Table */}
        <div className="pt-2">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wide text-[#8C879A]">
              Currently Provisioned Platform Phone Lines ({phoneNumbers.length})
            </h4>
          </div>
          <div className="overflow-x-auto rounded-xl border border-[#E4E2EB]">
            <table className="w-full text-left text-xs bg-white">
              <thead>
                <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[10px] font-bold text-[#8C879A] uppercase">
                  <th className="py-2.5 px-3">Phone Line (E.164)</th>
                  <th className="py-2.5 px-3">Carrier Trunk</th>
                  <th className="py-2.5 px-3">Workspace</th>
                  <th className="py-2.5 px-3">Assigned Agent</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E4E2EB]">
                {phoneNumbers.length === 0 ? (
                  <tr>
                    <td colSpan="6" className="py-6 text-center text-xs text-[#524E5E]">
                      No active phone numbers found across platform workspaces.
                    </td>
                  </tr>
                ) : (
                  phoneNumbers.map((p) => (
                    <tr key={p.id} className="hover:bg-[#FAF9FD]/50">
                      <td className="py-2.5 px-3 font-mono font-bold text-[#0F0E17]">{p.e164}</td>
                      <td className="py-2.5 px-3">
                        <span className={`text-[10px] uppercase font-mono px-2 py-0.5 rounded font-bold border ${
                          (p.provider || '').toLowerCase().includes('vobiz')
                            ? 'bg-purple-50 text-purple-700 border-purple-200'
                            : 'bg-sky-50 text-sky-700 border-sky-200'
                        }`}>
                          Direct Voice Line
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-semibold text-[#0F0E17]">{p.tenantName}</td>
                      <td className="py-2.5 px-3 text-[#524E5E]">
                        {p.agentName ? (
                          <span className="text-[#6344E7] font-medium">{p.agentName}</span>
                        ) : (
                          <span className="text-[#8C879A]">Unassigned Pool</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3">
                        <span className="inline-flex items-center gap-1 text-[10px] font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                          <Check className="w-2.5 h-2.5" /> Active
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <button
                          type="button"
                          onClick={() => handleReleaseNumber(p.id, p.e164)}
                          disabled={releaseBusyId === p.id}
                          className="text-[11px] font-semibold text-rose-600 hover:text-rose-800 disabled:opacity-50"
                        >
                          {releaseBusyId === p.id ? 'Releasing…' : 'Release'}
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </SolidCard>
        </div>
      )}

      {/* SECTION 3: Support Tickets Desk */}
      {section === 'support' && (
        <SolidCard className="p-5 space-y-6" data-testid="admin-customer-support-card">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-[#E4E2EB] pb-4">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-[#6344E7]/10 border border-[#6344E7]/20 flex items-center justify-center text-[#6344E7]">
                <Headphones className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-[#0F0E17]">Customer Support Desk & Ticket Operations</h3>
                  <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-semibold border border-emerald-200">
                    Live Queue
                  </span>
                </div>
                <p className="text-xs text-[#524E5E] mt-0.5">
                  Manage incoming customer inquiries and support tickets raised across platform workspaces and public visitors.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <TactileButton
                variant="secondary"
                size="sm"
                loading={supportInquiriesLoading}
                onClick={refreshInquiries}
                className="text-xs"
              >
                <RefreshCw className="w-3.5 h-3.5 mr-1" />
                Refresh Tickets
              </TactileButton>
            </div>
          </div>

          <div className="space-y-4">
            {/* Filter & Search Bar */}
            <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
              <div className="relative flex-1 max-w-sm">
                <Search className="w-3.5 h-3.5 text-[#8C879A] absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={inquirySearch}
                  onChange={(e) => setInquirySearch(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && refreshInquiries()}
                  placeholder="Search by ticket ID, email, name, or subject..."
                  className="w-full pl-8 pr-3 py-1.5 text-xs bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl text-[#0F0E17] placeholder:text-[#8C879A] focus:outline-none focus:border-[#6344E7]"
                />
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={inquiryPriorityFilter}
                  onChange={(e) => setInquiryPriorityFilter(e.target.value)}
                  className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2.5 py-1.5 text-xs text-[#0F0E17] font-medium"
                >
                  <option value="all">All Priorities</option>
                  <option value="urgent">Urgent</option>
                  <option value="high">High</option>
                  <option value="normal">Normal</option>
                  <option value="low">Low</option>
                </select>

                <select
                  value={inquiryCategoryFilter}
                  onChange={(e) => setInquiryCategoryFilter(e.target.value)}
                  className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2.5 py-1.5 text-xs text-[#0F0E17] font-medium"
                >
                  <option value="all">All Categories</option>
                  <option value="technical_support">Technical Support</option>
                  <option value="enterprise_fleet">Enterprise Fleet</option>
                  <option value="telephony_trunk">Voice Network</option>
                  <option value="billing_pricing">Billing</option>
                  <option value="general_inquiry">General</option>
                </select>
              </div>
            </div>

            {/* Status Filter Pills */}
            <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-none pb-1">
              {[
                { id: 'all', label: 'All Tickets' },
                { id: 'new', label: 'New' },
                { id: 'triaged', label: 'Triaged' },
                { id: 'in_progress', label: 'In Progress' },
                { id: 'waiting_on_customer', label: 'Waiting on Customer' },
                { id: 'resolved', label: 'Resolved' },
                { id: 'closed', label: 'Closed' },
              ].map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setInquiryFilter(f.id)}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold whitespace-nowrap transition-colors ${
                    inquiryFilter === f.id
                      ? 'bg-[#0F0E17] text-white shadow-xs'
                      : 'bg-[#FAF9FD] text-[#524E5E] hover:bg-[#F0EEF6] border border-[#E4E2EB]'
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>

            {/* Inquiries Table */}
            {supportInquiries.length === 0 ? (
              <div className="p-8 text-center rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
                <Headphones className="w-8 h-8 text-[#8C879A] mx-auto mb-2 opacity-50" />
                <p className="text-xs font-semibold text-[#0F0E17]">No support tickets match the current filter</p>
                <p className="text-[11px] text-[#8C879A] mt-0.5">
                  Inquiries raised by tenants or website visitors will appear here automatically.
                </p>
              </div>
            ) : (
              <div className="rounded-xl border border-[#E4E2EB] overflow-hidden">
                <div className="overflow-x-auto scrollbar-none">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[10px] font-bold text-[#8C879A] uppercase tracking-wider">
                        <th className="py-2.5 px-3">Ticket ID</th>
                        <th className="py-2.5 px-3">Contact & Tenant</th>
                        <th className="py-2.5 px-3">Category</th>
                        <th className="py-2.5 px-3">Priority</th>
                        <th className="py-2.5 px-3">Status</th>
                        <th className="py-2.5 px-3">Subject / Message</th>
                        <th className="py-2.5 px-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E4E2EB]">
                      {supportInquiries
                        .filter((inq) => inquiryFilter === 'all' || inq.status === inquiryFilter)
                        .filter((inq) => inquiryPriorityFilter === 'all' || inq.priority === inquiryPriorityFilter)
                        .filter((inq) => inquiryCategoryFilter === 'all' || inq.category === inquiryCategoryFilter)
                        .filter((inq) => {
                          if (!inquirySearch.trim()) return true;
                          const s = inquirySearch.toLowerCase();
                          return (
                            inq.ticketNumber?.toLowerCase().includes(s) ||
                            inq.email?.toLowerCase().includes(s) ||
                            inq.fullName?.toLowerCase().includes(s) ||
                            inq.subject?.toLowerCase().includes(s)
                          );
                        })
                        .map((inq) => (
                          <tr key={inq.id} className="hover:bg-[#FAF9FD] transition-colors">
                            <td className="py-3 px-3 font-mono font-bold text-[#6344E7] whitespace-nowrap">
                              {inq.ticketNumber}
                            </td>
                            <td className="py-3 px-3">
                              <div className="font-semibold text-[#0F0E17] flex items-center gap-1.5">
                                <span>{inq.fullName}</span>
                                {inq.tenantId && (
                                  <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-purple-50 text-purple-700 border border-purple-200">
                                    Tenant
                                  </span>
                                )}
                              </div>
                              <div className="text-[11px] text-[#524E5E]">{inq.email}</div>
                              {inq.company && <div className="text-[10px] text-[#8C879A]">{inq.company}</div>}
                            </td>
                            <td className="py-3 px-3">
                              <span className="inline-block px-2 py-0.5 rounded-md bg-[#FAF9FD] border border-[#E4E2EB] text-[11px] font-medium text-[#524E5E]">
                                {inq.category.replace('_', ' ')}
                              </span>
                            </td>
                            <td className="py-3 px-3">
                              <span
                                className={`text-[11px] font-bold uppercase ${
                                  inq.priority === 'urgent'
                                    ? 'text-rose-600'
                                    : inq.priority === 'high'
                                    ? 'text-amber-600'
                                    : 'text-emerald-600'
                                }`}
                              >
                                {inq.priority}
                              </span>
                            </td>
                            <td className="py-3 px-3">
                              <span
                                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10.5px] font-semibold capitalize ${
                                  inq.status === 'new'
                                    ? 'bg-blue-50 text-blue-700 border border-blue-200'
                                    : inq.status === 'in_progress'
                                    ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                    : inq.status === 'resolved'
                                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                    : inq.status === 'waiting_on_customer'
                                    ? 'bg-purple-50 text-purple-700 border border-purple-200'
                                    : 'bg-gray-100 text-gray-600 border border-gray-200'
                                }`}
                              >
                                {inq.status.replace('_', ' ')}
                              </span>
                            </td>
                            <td className="py-3 px-3 max-w-xs">
                              <div className="font-medium text-[#0F0E17] truncate">{inq.subject}</div>
                              <div className="text-[11px] text-[#524E5E] line-clamp-1">{inq.message}</div>
                            </td>
                            <td className="py-3 px-3 text-right whitespace-nowrap">
                              <div className="flex items-center justify-end gap-1.5">
                                {inq.status !== 'resolved' && (
                                  <button
                                    type="button"
                                    disabled={inquiryStatusBusyId === inq.id}
                                    onClick={() => handleUpdateInquiryStatus(inq.id, 'resolved')}
                                    className="text-[11px] font-medium px-2 py-1 rounded-md border border-emerald-200 bg-emerald-50 text-emerald-800 hover:bg-emerald-100"
                                  >
                                    Resolve
                                  </button>
                                )}
                                <button
                                  type="button"
                                  onClick={() => {
                                    setActiveInquiryDetail(inq);
                                    setAdminNoteInput(inq.adminNotes || '');
                                    setAssigneeInput(inq.assignedTo || '');
                                    setCustomerReplyInput('');
                                  }}
                                  className="text-[11px] font-medium px-2 py-1 rounded-md border border-[#E4E2EB] bg-white text-[#0F0E17] hover:bg-[#FAF9FD]"
                                >
                                  View & Reply
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </SolidCard>
      )}

      {/* SECTION 4: Social Media & Channels */}
      {section === 'social' && (
        <SolidCard className="p-5 space-y-6" data-testid="admin-social-channels-card">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-[#E4E2EB] pb-4">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-[#6344E7]/10 border border-[#6344E7]/20 flex items-center justify-center text-[#6344E7]">
                <Share2 className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-[#0F0E17]">Channels & Social Media Configuration</h3>
                  <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 font-semibold border border-purple-200">
                    Public Footer Hyperlinks
                  </span>
                </div>
                <p className="text-xs text-[#524E5E] mt-0.5">
                  Configure official contact channels, operating hours, SLA guarantees, and public social media links rendered in the website footer.
                </p>
              </div>
            </div>
          </div>

          <form onSubmit={handleSaveSupportConfig} className="space-y-6">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider flex items-center gap-1.5">
                  <Sliders className="w-3.5 h-3.5 text-[#6344E7]" />
                  Support Channels & Operational Parameters
                </h4>
                <label className="text-xs font-medium text-[#524E5E] cursor-pointer flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={supportConfig.isActive}
                    onChange={(e) => setSupportConfig({ ...supportConfig, isActive: e.target.checked })}
                    className="rounded border-[#E4E2EB] text-[#6344E7] focus:ring-[#6344E7]"
                  />
                  <span className="text-xs font-semibold text-[#0F0E17]">Support Flow Active</span>
                </label>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                <div>
                  <label className="block text-[11px] font-bold text-[#8C879A] uppercase mb-1">Support Email</label>
                  <input
                    type="email"
                    value={supportConfig.supportEmail}
                    onChange={(e) => setSupportConfig({ ...supportConfig, supportEmail: e.target.value })}
                    placeholder="support@dialtact.com"
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-medium text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-[#8C879A] uppercase mb-1">Operational Hours</label>
                  <input
                    type="text"
                    value={supportConfig.businessHours}
                    onChange={(e) => setSupportConfig({ ...supportConfig, businessHours: e.target.value })}
                    placeholder="Mon - Fri: 9:00 AM - 6:00 PM EST"
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-medium text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-[#8C879A] uppercase mb-1">SLA Response Guarantee</label>
                  <input
                    type="text"
                    value={supportConfig.slaResponseTime}
                    onChange={(e) => setSupportConfig({ ...supportConfig, slaResponseTime: e.target.value })}
                    placeholder="Within 2 hours for Priority, 24 hours Standard"
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-medium text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                  />
                </div>

                <div className="sm:col-span-3">
                  <label className="block text-[11px] font-bold text-[#8C879A] uppercase mb-1">Auto-Reply Confirmation Message</label>
                  <textarea
                    rows={2}
                    value={supportConfig.autoReplyMessage || ''}
                    onChange={(e) => setSupportConfig({ ...supportConfig, autoReplyMessage: e.target.value })}
                    placeholder="Automatic acknowledgment message displayed to users upon ticket transmission..."
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-medium text-[#0F0E17] focus:outline-none focus:border-[#6344E7] resize-none"
                  />
                </div>
              </div>
            </div>

            {/* Social Media Links Section */}
            <div className="space-y-3 pt-4 border-t border-[#E4E2EB]">
              <div>
                <h4 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider flex items-center gap-1.5">
                  <Share2 className="w-3.5 h-3.5 text-[#6344E7]" />
                  Social Media Links (Public Footer Hyperlinks)
                </h4>
                <p className="text-[11px] text-[#524E5E] mt-0.5">
                  These URLs control the active icons and hyperlinks rendered in the website footer.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                <div>
                  <label className="block text-[11px] font-bold text-[#8C879A] uppercase mb-1">X / Twitter URL</label>
                  <input
                    type="url"
                    value={supportConfig.twitterUrl || ''}
                    onChange={(e) => setSupportConfig({ ...supportConfig, twitterUrl: e.target.value })}
                    placeholder="https://x.com/dialtact"
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-medium text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-[#8C879A] uppercase mb-1">LinkedIn URL</label>
                  <input
                    type="url"
                    value={supportConfig.linkedinUrl || ''}
                    onChange={(e) => setSupportConfig({ ...supportConfig, linkedinUrl: e.target.value })}
                    placeholder="https://linkedin.com/company/dialtact"
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-medium text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-[#8C879A] uppercase mb-1">GitHub URL</label>
                  <input
                    type="url"
                    value={supportConfig.githubUrl || ''}
                    onChange={(e) => setSupportConfig({ ...supportConfig, githubUrl: e.target.value })}
                    placeholder="https://github.com/dialtact"
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-medium text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-[#8C879A] uppercase mb-1">YouTube URL</label>
                  <input
                    type="url"
                    value={supportConfig.youtubeUrl || ''}
                    onChange={(e) => setSupportConfig({ ...supportConfig, youtubeUrl: e.target.value })}
                    placeholder="https://youtube.com/@dialtact"
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-medium text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-[#8C879A] uppercase mb-1">Discord URL</label>
                  <input
                    type="url"
                    value={supportConfig.discordUrl || ''}
                    onChange={(e) => setSupportConfig({ ...supportConfig, discordUrl: e.target.value })}
                    placeholder="https://discord.gg/dialtact"
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-medium text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                  />
                </div>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <TactileButton
                variant="primary"
                size="sm"
                loading={supportConfigBusy}
                type="submit"
                data-testid="admin-save-support-channels"
              >
                <Check className="w-3.5 h-3.5 mr-1.5" />
                Save Channels & Social Links
              </TactileButton>
            </div>
          </form>
        </SolidCard>
      )}

      {/* SECTION 5: Mail Gateway & SMTP */}
      {section === 'mail' && (
        <SolidCard className="p-5 space-y-6" data-testid="admin-mail-gateway-card">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-[#E4E2EB] pb-4">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-[#6344E7]/10 border border-[#6344E7]/20 flex items-center justify-center text-[#6344E7]">
                <Mail className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-[#0F0E17]">Mail Gateway & SMTP Configuration</h3>
                  <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-semibold border border-emerald-200">
                    {supportConfig.smtpHost ? 'Custom SMTP' : 'Default Gateway'}
                  </span>
                </div>
                <p className="text-xs text-[#524E5E] mt-0.5">
                  Configure outgoing SMTP mail server credentials to send ticket confirmations to users and staff alerts.
                </p>
              </div>
            </div>
          </div>

          <form onSubmit={handleSaveSupportConfig} className="space-y-6">
            {smtpTestResult && (
              <div
                className={`p-3 rounded-xl border text-xs flex items-center gap-2 ${
                  smtpTestResult.success
                    ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                    : 'bg-rose-50 border-rose-200 text-rose-800'
                }`}
              >
                {smtpTestResult.success ? (
                  <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
                ) : (
                  <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" />
                )}
                <span>{smtpTestResult.message || smtpTestResult.error}</span>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <div>
                <label className="block text-[11px] font-bold text-[#8C879A] uppercase mb-1">SMTP Host</label>
                <input
                  type="text"
                  value={supportConfig.smtpHost || ''}
                  onChange={(e) => setSupportConfig({ ...supportConfig, smtpHost: e.target.value })}
                  placeholder="smtp.sendgrid.net or smtp.gmail.com"
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-medium text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold text-[#8C879A] uppercase mb-1">SMTP Port</label>
                <input
                  type="number"
                  value={supportConfig.smtpPort || 587}
                  onChange={(e) => setSupportConfig({ ...supportConfig, smtpPort: Number(e.target.value) })}
                  placeholder="587"
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-medium text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold text-[#8C879A] uppercase mb-1">SMTP Username</label>
                <input
                  type="text"
                  value={supportConfig.smtpUsername || ''}
                  onChange={(e) => setSupportConfig({ ...supportConfig, smtpUsername: e.target.value })}
                  placeholder="apikey or user@company.com"
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-medium text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold text-[#8C879A] uppercase mb-1">SMTP Password / API Key</label>
                <input
                  type="password"
                  value={supportConfig.smtpPassword || ''}
                  onChange={(e) => setSupportConfig({ ...supportConfig, smtpPassword: e.target.value })}
                  placeholder={supportConfig.smtpHasPassword ? '•••••••• (persisted)' : 'Password or Secret Token'}
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-medium text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold text-[#8C879A] uppercase mb-1">Sender Email</label>
                <input
                  type="email"
                  value={supportConfig.senderEmail || ''}
                  onChange={(e) => setSupportConfig({ ...supportConfig, senderEmail: e.target.value })}
                  placeholder="support@dialtact.com"
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-medium text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold text-[#8C879A] uppercase mb-1">Sender Display Name</label>
                <input
                  type="text"
                  value={supportConfig.senderName || ''}
                  onChange={(e) => setSupportConfig({ ...supportConfig, senderName: e.target.value })}
                  placeholder="Dialtact Support Desk"
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-medium text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                />
              </div>

              <div className="sm:col-span-2">
                <label className="block text-[11px] font-bold text-[#8C879A] uppercase mb-1">Admin Notification Recipient Email</label>
                <input
                  type="email"
                  value={supportConfig.adminAlertEmail || ''}
                  onChange={(e) => setSupportConfig({ ...supportConfig, adminAlertEmail: e.target.value })}
                  placeholder="alerts@dialtact.com"
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-medium text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                />
              </div>

              <div className="flex items-center pt-5">
                <label className="text-xs font-medium text-[#524E5E] cursor-pointer flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={supportConfig.smtpUseTls}
                    onChange={(e) => setSupportConfig({ ...supportConfig, smtpUseTls: e.target.checked })}
                    className="rounded border-[#E4E2EB] text-[#6344E7] focus:ring-[#6344E7]"
                  />
                  <span className="text-xs font-semibold text-[#0F0E17]">Enable TLS / STARTTLS</span>
                </label>
              </div>
            </div>

            {/* Notification Checkboxes */}
            <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-2">
              <label className="text-xs font-medium text-[#0F0E17] cursor-pointer flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={supportConfig.notifyCustomerOnTicket}
                  onChange={(e) => setSupportConfig({ ...supportConfig, notifyCustomerOnTicket: e.target.checked })}
                  className="rounded border-[#E4E2EB] text-[#6344E7] focus:ring-[#6344E7]"
                />
                <span>Automatically dispatch confirmation email to customer upon ticket submission</span>
              </label>

              <label className="text-xs font-medium text-[#0F0E17] cursor-pointer flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={supportConfig.notifyAdminOnTicket}
                  onChange={(e) => setSupportConfig({ ...supportConfig, notifyAdminOnTicket: e.target.checked })}
                  className="rounded border-[#E4E2EB] text-[#6344E7] focus:ring-[#6344E7]"
                />
                <span>Automatically dispatch alert email to admin recipient on new support tickets</span>
              </label>
            </div>

            <div className="flex items-center justify-between pt-2">
              <TactileButton
                variant="secondary"
                size="sm"
                type="button"
                loading={smtpTesting}
                onClick={handleTestSmtp}
              >
                <Radio className="w-3.5 h-3.5 mr-1.5" />
                Test SMTP Connection
              </TactileButton>

              <TactileButton
                variant="primary"
                size="sm"
                loading={supportConfigBusy}
                type="submit"
                data-testid="admin-save-mail-config"
              >
                <Check className="w-3.5 h-3.5 mr-1.5" />
                Save Mail Configuration
              </TactileButton>
            </div>
          </form>
        </SolidCard>
      )}

      {/* Inquiry Detail, Reply Composer & Ticket Maintenance Modal */}
      {activeInquiryDetail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs">
          <div className="w-full max-w-2xl bg-white rounded-2xl shadow-2xl border border-[#E4E2EB] p-5 sm:p-6 space-y-4 max-h-[92vh] overflow-y-auto">
            {/* Modal Header */}
            <div className="flex items-center justify-between pb-3 border-b border-[#E4E2EB]">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-[#6344E7]/10 flex items-center justify-center text-[#6344E7]">
                  <FileText className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-bold text-[#0F0E17]">Ticket {activeInquiryDetail.ticketNumber}</h3>
                    {activeInquiryDetail.tenantId && (
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 font-bold border border-purple-200">
                        Workspace Tenant
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-[#524E5E]">
                    Submitted: {new Date(activeInquiryDetail.createdAt).toLocaleString()}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setActiveInquiryDetail(null)}
                className="w-7 h-7 rounded-lg bg-[#FAF9FD] hover:bg-[#E4E2EB] flex items-center justify-center text-[#524E5E]"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-4 text-xs">
              {/* Contact Information Card */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
                <div>
                  <span className="text-[#8C879A] block text-[10px] uppercase font-bold">Contact Name</span>
                  <span className="font-semibold text-[#0F0E17]">{activeInquiryDetail.fullName}</span>
                </div>
                <div>
                  <span className="text-[#8C879A] block text-[10px] uppercase font-bold">Work Email</span>
                  <a href={`mailto:${activeInquiryDetail.email}`} className="font-semibold text-[#6344E7] hover:underline">
                    {activeInquiryDetail.email}
                  </a>
                </div>
                {activeInquiryDetail.company && (
                  <div>
                    <span className="text-[#8C879A] block text-[10px] uppercase font-bold">Organization</span>
                    <span className="font-semibold text-[#0F0E17]">{activeInquiryDetail.company}</span>
                  </div>
                )}
                <div>
                  <span className="text-[#8C879A] block text-[10px] uppercase font-bold">Category</span>
                  <span className="font-medium text-[#0F0E17] capitalize">{activeInquiryDetail.category?.replace('_', ' ')}</span>
                </div>
                <div>
                  <span className="text-[#8C879A] block text-[10px] uppercase font-bold">Priority</span>
                  <span className="font-bold text-amber-700 uppercase">{activeInquiryDetail.priority}</span>
                </div>
                <div>
                  <span className="text-[#8C879A] block text-[10px] uppercase font-bold">Assigned Staff</span>
                  <span className="font-medium text-[#0F0E17]">{activeInquiryDetail.assignedTo || 'Unassigned'}</span>
                </div>
              </div>

              {/* Subject & Original Inquiry Message */}
              <div>
                <span className="text-[#8C879A] block text-[10px] uppercase font-bold mb-1">Subject</span>
                <p className="font-bold text-sm text-[#0F0E17]">{activeInquiryDetail.subject}</p>
              </div>

              <div>
                <span className="text-[#8C879A] block text-[10px] uppercase font-bold mb-1">Customer Inquiry Message</span>
                <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-[#0F0E17] leading-relaxed whitespace-pre-wrap">
                  {activeInquiryDetail.message}
                </div>
              </div>

              {/* Conversation Timeline & Past Replies */}
              {activeInquiryDetail.customerReplies && activeInquiryDetail.customerReplies.length > 0 && (
                <div className="space-y-2 pt-2 border-t border-[#E4E2EB]">
                  <span className="text-[#8C879A] block text-[10px] uppercase font-bold">
                    Conversation Thread & Dispatched Responses ({activeInquiryDetail.customerReplies.length})
                  </span>
                  <div className="space-y-2 max-h-48 overflow-y-auto p-2 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
                    {activeInquiryDetail.customerReplies.map((r, i) => (
                      <div key={i} className="p-2.5 rounded-lg bg-white border border-[#E4E2EB] text-xs space-y-1">
                        <div className="flex items-center justify-between text-[10px] text-[#8C879A]">
                          <span className="font-bold text-[#6344E7]">{r.author || 'Support Staff'}</span>
                          <span>{r.sentAt ? new Date(r.sentAt).toLocaleString() : ''}</span>
                        </div>
                        <p className="text-[#0F0E17] whitespace-pre-wrap">{r.message}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Reply to Customer Composer */}
              <div className="space-y-2 pt-2 border-t border-[#E4E2EB]">
                <div className="flex items-center justify-between">
                  <span className="text-[#8C879A] block text-[10px] uppercase font-bold flex items-center gap-1.5">
                    <Send className="w-3 h-3 text-[#6344E7]" />
                    Compose Response (Dispatched via Outbound Email)
                  </span>
                </div>
                <textarea
                  rows={3}
                  value={customerReplyInput}
                  onChange={(e) => setCustomerReplyInput(e.target.value)}
                  placeholder="Type your response to the customer. When dispatched, an email will be sent directly to their address..."
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-2.5 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] resize-none"
                />
                <div className="flex justify-end">
                  <TactileButton
                    variant="primary"
                    size="sm"
                    loading={replySending}
                    onClick={() => handleSendCustomerReply(activeInquiryDetail.id)}
                  >
                    <Send className="w-3.5 h-3.5 mr-1" />
                    Dispatch Reply to Customer
                  </TactileButton>
                </div>
              </div>

              {/* Staff Internal Notes & Assignee */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-[#E4E2EB]">
                <div>
                  <span className="text-[#8C879A] block text-[10px] uppercase font-bold mb-1">Assign Staff Engineer</span>
                  <input
                    type="text"
                    value={assigneeInput}
                    onChange={(e) => setAssigneeInput(e.target.value)}
                    placeholder="e.g. staff-voice@dialtact.com"
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2.5 py-1.5 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                  />
                </div>

                <div>
                  <span className="text-[#8C879A] block text-[10px] uppercase font-bold mb-1">Set Ticket Status</span>
                  <select
                    value={activeInquiryDetail.status}
                    onChange={(e) =>
                      handleUpdateInquiryStatus(activeInquiryDetail.id, e.target.value, adminNoteInput, assigneeInput)
                    }
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2.5 py-1.5 text-xs font-semibold text-[#0F0E17]"
                  >
                    <option value="new">New</option>
                    <option value="triaged">Triaged</option>
                    <option value="in_progress">In Progress</option>
                    <option value="waiting_on_customer">Waiting on Customer</option>
                    <option value="resolved">Resolved</option>
                    <option value="closed">Closed</option>
                  </select>
                </div>

                <div className="sm:col-span-2">
                  <span className="text-[#8C879A] block text-[10px] uppercase font-bold mb-1">Internal Staff Notes (Private)</span>
                  <textarea
                    rows={2}
                    value={adminNoteInput}
                    onChange={(e) => setAdminNoteInput(e.target.value)}
                    placeholder="Private staff notes, technical triage findings, or internal follow-up steps..."
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-2.5 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] resize-none"
                  />
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-[#E4E2EB]">
              <TactileButton
                variant="secondary"
                size="sm"
                onClick={() => setActiveInquiryDetail(null)}
              >
                Close Dialog
              </TactileButton>
              <TactileButton
                variant="primary"
                size="sm"
                onClick={() => {
                  handleUpdateInquiryStatus(
                    activeInquiryDetail.id,
                    activeInquiryDetail.status,
                    adminNoteInput,
                    assigneeInput
                  );
                  setActiveInquiryDetail(null);
                }}
              >
                <Check className="w-3.5 h-3.5 mr-1" />
                Save Notes & Assignee
              </TactileButton>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirmTenant && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs">
          <div className="w-full max-w-md bg-white rounded-2xl shadow-xl border border-[#E4E2EB] p-5 space-y-4">
            <div className="flex items-center gap-3 text-rose-600">
              <div className="w-10 h-10 rounded-full bg-rose-50 border border-rose-200 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5 text-rose-600" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-[#0F0E17]">Delete Workspace</h3>
                <p className="text-xs text-[#524E5E]">This action cannot be undone.</p>
              </div>
            </div>

            <p className="text-xs text-[#524E5E] leading-relaxed">
              Are you sure you want to permanently delete{' '}
              <strong className="text-[#0F0E17] font-semibold">{deleteConfirmTenant.name}</strong>? All associated agents,
              call histories, and workspace settings will be purged.
            </p>

            <div className="flex items-center justify-end gap-2 pt-2">
              <TactileButton
                variant="secondary"
                size="sm"
                onClick={() => setDeleteConfirmTenant(null)}
                disabled={deleteBusy}
                className="text-xs"
              >
                Cancel
              </TactileButton>
              <button
                type="button"
                onClick={confirmDeleteTenant}
                disabled={deleteBusy}
                className="inline-flex items-center justify-center px-4 py-2 rounded-xl text-xs font-bold text-white bg-rose-600 hover:bg-rose-700 disabled:opacity-50 transition-colors shadow-xs"
              >
                {deleteBusy ? 'Deleting…' : 'Yes, Delete Workspace'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
