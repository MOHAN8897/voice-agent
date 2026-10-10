import React, { useState, useEffect } from 'react';
import {
  Phone,
  Plus,
  CheckCircle2,
  X,
  Radio,
  Sliders,
  Server,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { StatusBadge } from '../ui/StatusBadge';
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';
import { useWorkspace } from '../context/WorkspaceContext';
import { showToast } from '../ui/ToastHost';
import { api } from '../../services/api';
import { VerifyIdentityCard } from '../ui/VerifyIdentityCard';
import { CatalogSkeleton, PhoneNumberRowSkeleton } from '../ui/Skeleton';

const FALLBACK_COUNTRIES = [
  { code: 'US', name: 'United States', dial: '+1' },
  { code: 'GB', name: 'United Kingdom', dial: '+44' },
  { code: 'CA', name: 'Canada', dial: '+1' },
  { code: 'AU', name: 'Australia', dial: '+61' },
  { code: 'IE', name: 'Ireland', dial: '+353' },
  { code: 'NZ', name: 'New Zealand', dial: '+64' },
  { code: 'SG', name: 'Singapore', dial: '+65' },
  { code: 'ZA', name: 'South Africa', dial: '+27' },
  { code: 'PH', name: 'Philippines', dial: '+63' },
  { code: 'IN', name: 'India', dial: '+91' },
];

export function TelephonyPlatformBadge({ provider, size = 'sm' }) {
  const norm = String(provider || '').toLowerCase();
  const isVobiz = norm.includes('vobiz') || norm.includes('plivo');
  const isTelnyx = norm.includes('telnyx');
  const isExotel = norm.includes('exotel');

  const padding = size === 'xs' ? 'px-1.5 py-0.5 text-[9px]' : 'px-2 py-0.5 text-[10px]';

  if (isVobiz) {
    return (
      <span
        className={`inline-flex items-center gap-1.5 font-mono uppercase font-bold rounded-md bg-purple-50 text-purple-700 border border-purple-200 tracking-wide ${padding}`}
        title="Vobiz Cloud Telephony Platform"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-purple-600 shrink-0" />
        Vobiz Cloud
      </span>
    );
  }
  if (isTelnyx) {
    return (
      <span
        className={`inline-flex items-center gap-1.5 font-mono uppercase font-bold rounded-md bg-sky-50 text-sky-700 border border-sky-200 tracking-wide ${padding}`}
        title="Telnyx Telephony Trunk"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-sky-600 shrink-0" />
        Telnyx Trunk
      </span>
    );
  }
  if (isExotel) {
    return (
      <span
        className={`inline-flex items-center gap-1.5 font-mono uppercase font-bold rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 tracking-wide ${padding}`}
        title="Exotel Telephony Platform"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 shrink-0" />
        Exotel
      </span>
    );
  }
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono uppercase font-bold rounded-md bg-slate-100 text-slate-700 border border-slate-200 tracking-wide ${padding}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-slate-400 shrink-0" />
      {norm || 'Carrier'}
    </span>
  );
}

export function PhoneNumbersModule({ isBuyModalOpen, onCloseBuyModal, onOpenBuyModal, onNavigate }) {
  const {
    phoneNumbers,
    agents,
    availableCatalog,
    buyPhoneNumber,
    assignNumberToAgent,
    releasePhoneNumber,
    buyNumberPreselectedAgent,
    reloadCatalog,
    updateNumberRouting,
    wallet,
    refreshWallet,
    isLoading,
    openAddFunds,
    loadWorkspaceData,
  } = useWorkspace();

  // Buy Modal Form State — default based on active carrier
  const [selectedCountry, setSelectedCountry] = useState('IN');
  const [countries, setCountries] = useState(FALLBACK_COUNTRIES);
  const [selectedType, setSelectedType] = useState('Local DID');
  const [searchAreaCode, setSearchAreaCode] = useState('');
  const [targetAgentId, setTargetAgentId] = useState(buyNumberPreselectedAgent || '');
  const [purchasedSuccess, setPurchasedSuccess] = useState(null);
  const [buyError, setBuyError] = useState(null);
  const [buying, setBuying] = useState(false);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState(null);
  const [kycApproved, setKycApproved] = useState(false);
  const [providerInfo, setProviderInfo] = useState(null);
  const [showTelephonySettings, setShowTelephonySettings] = useState(false);
  const [providerBusy, setProviderBusy] = useState(false);

  const refreshProviderInfo = async () => {
    try {
      const data = await api.telephony?.getProvider?.();
      if (data) {
        setProviderInfo(data);
        if (data.activeProvider === 'vobiz') {
          setSelectedCountry('IN');
        } else if (data.activeProvider === 'telnyx') {
          setSelectedCountry('US');
        }
      }
    } catch {}
  };

  const handleSwitchProvider = async (providerId) => {
    if (providerBusy || providerInfo?.activeProvider === providerId) return;
    setProviderBusy(true);
    try {
      await api.telephony.setProvider(providerId);
      showToast(`Active telephony trunk switched to ${providerId.toUpperCase()}`, 'success');
      const nextCountry = providerId === 'vobiz' ? 'IN' : 'US';
      setSelectedCountry(nextCountry);
      await Promise.all([
        refreshProviderInfo(),
        loadWorkspaceData?.(),
        reloadCatalog?.(nextCountry),
      ]);
    } catch (e) {
      showToast(e.message || 'Failed to switch telephony provider', 'error');
    } finally {
      setProviderBusy(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    api.telephony
      ?.getProvider?.()
      .then((data) => {
        if (!cancelled && data) {
          setProviderInfo(data);
          if (data.activeProvider === 'vobiz') {
            setSelectedCountry('IN');
          } else if (data.activeProvider === 'telnyx') {
            setSelectedCountry('US');
          }
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!isBuyModalOpen) return;
    setBuyError(null);
    setCatalogLoading(true);
    setCatalogError(null);
    reloadCatalog?.(selectedCountry)
      .catch((e) => setCatalogError(e.message || 'Could not load numbers for this country'))
      .finally(() => setCatalogLoading(false));
  }, [isBuyModalOpen, selectedCountry, reloadCatalog]);

  // Refresh KYC every time the buy modal opens — status can change outside this tab.
  useEffect(() => {
    if (!isBuyModalOpen) return undefined;
    let cancelled = false;
    api.kyc
      .getStatus()
      .then((st) => {
        if (cancelled) return;
        setKycApproved(Boolean(st?.approved));
      })
      .catch(() => {
        if (!cancelled) setKycApproved(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isBuyModalOpen]);

  useEffect(() => {
    let cancelled = false;
    api.telephony
      .getCountries()
      .then((data) => {
        if (cancelled) return;
        if (data.countries?.length) setCountries(data.countries);
        if (data.default) setSelectedCountry(data.default);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // Inline alerts should not sit forever — toast pattern: 5s, dismissible.
  useEffect(() => {
    if (!buyError) return undefined;
    const id = window.setTimeout(() => setBuyError(null), 5000);
    return () => window.clearTimeout(id);
  }, [buyError]);

  useEffect(() => {
    if (!catalogError) return undefined;
    const id = window.setTimeout(() => setCatalogError(null), 5000);
    return () => window.clearTimeout(id);
  }, [catalogError]);

  useEffect(() => {
    if (buyNumberPreselectedAgent) setTargetAgentId(buyNumberPreselectedAgent);
  }, [buyNumberPreselectedAgent]);

  const unassignedCount = phoneNumbers.filter((n) => !n.assignedAgentId).length;
  const assignedCount = phoneNumbers.length - unassignedCount;
  const monthlyRentalUsd = phoneNumbers.reduce(
    (sum, n) => sum + (Number(n.monthlyCost) || 0),
    0
  );
  const balanceUsd = Number(wallet?.balanceUsd) || 0;

  // Price and wallet top-up floor come from the server so the console can never
  // quote something `/api/telephony/buy` or `/api/billing/topup` would reject.
  const [catalog, setCatalog] = useState(null);
  useEffect(() => {
    let cancelled = false;
    api.billing
      .getCatalog()
      .then((c) => {
        if (!cancelled) setCatalog(c);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  // USD is the only quoted currency. A missing catalog means we do not know the
  // price, so we must not invent one — the buy button stays honest by asking the
  // server, which is the authority anyway.
  const numberPriceUsd = Number(catalog?.rates?.numberMonthlyUsd);
  const priceKnown = Number.isFinite(numberPriceUsd) && numberPriceUsd > 0;
  const canAffordNumber = priceKnown && balanceUsd >= numberPriceUsd;

  const filteredCatalog = availableCatalog.filter((item) => {
    const cc = (item.country || '').toUpperCase();
    const matchesCountry = cc === selectedCountry.toUpperCase();
    const normType = (t) => {
      const s = String(t || '').toLowerCase();
      if (s.includes('toll')) return 'toll';
      return 'local';
    };
    const matchesType =
      selectedType === 'All' ||
      !item.type ||
      normType(item.type) === normType(selectedType);
    const matchesArea =
      !searchAreaCode ||
      (item.areaCode && item.areaCode.includes(searchAreaCode)) ||
      (item.number && item.number.includes(searchAreaCode));
    return matchesCountry && matchesType && matchesArea;
  });

  const handleBuyNumber = async (catalogItem) => {
    setBuyError(null);
    if (!kycApproved) {
      try {
        const st = await api.kyc.getStatus();
        if (!st?.approved) {
          setKycApproved(false);
          showToast('Complete identity verification before buying a number', 'error', 5000);
          return;
        }
        setKycApproved(true);
      } catch {
        /* server still enforces KYC on /buy */
      }
    }
    if (priceKnown && balanceUsd < numberPriceUsd) {
      const msg = `A phone number costs $${numberPriceUsd.toFixed(
        2
      )} per month. Add credit to your wallet to buy one.`;
      setBuyError(msg);
      return;
    }
    setBuying(true);
    setPurchasedSuccess(null);
    try {
      const bought = await buyPhoneNumber(catalogItem, targetAgentId || null);
      if (bought?.checkoutUrl) {
        return;
      }
      if (bought?.ok === false) {
        const failed =
          bought.failureReason === 'pending'
            ? 'The order is still being placed. It will appear in your lines shortly.'
            : bought.failureReason === 'carrier_balance_exhausted'
              ? 'Phone numbers are temporarily unavailable. Your wallet was not charged.'
              : 'Purchase failed — the number could not be provisioned. Your wallet has been refunded.';
        setBuyError(failed);
        if (bought.failureReason !== 'pending') await refreshWallet?.();
        return;
      }
      setPurchasedSuccess(catalogItem.formatted || catalogItem.number);
      showToast('Number purchased — provisioning to your workspace', 'success', 5000);
      await refreshWallet?.();
      setTimeout(() => {
        setPurchasedSuccess(null);
        onCloseBuyModal();
      }, 1800);
    } catch (e) {
      if (e.status === 402 || e.code === 'insufficient_balance') {
        const msg = priceKnown
          ? `${e.message} A phone number costs $${numberPriceUsd.toFixed(2)} per month.`
          : e.message;
        setBuyError(msg);
        await refreshWallet?.();
      } else if (e.status === 403 || e.code === 'kyc_required') {
        setKycApproved(false);
        setBuyError('Verify your identity to buy a phone number.');
      } else if (e.code === 'carrier_balance_exhausted' || e.status === 503) {
        setBuyError(
          e.message ||
            'Phone numbers are temporarily unavailable. Your wallet was not charged.'
        );
      } else {
        setBuyError(e.message || 'Could not start number purchase');
      }
    } finally {
      setBuying(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header & Quick Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">
            Phone lines ({phoneNumbers.length})
          </h2>
          <p className="text-xs text-[#524E5E] mt-0.5">
            Buy a number and connect it to an AI agent. Rental is billed monthly; call time is billed
            from your wallet.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <TactileButton
            onClick={() => setShowTelephonySettings((prev) => !prev)}
            variant={showTelephonySettings ? "primary" : "secondary"}
            icon={Sliders}
            size="md"
          >
            Telephony Settings
          </TactileButton>

          <TactileButton
            onClick={onOpenBuyModal}
            variant="primary"
            icon={Plus}
            size="md"
          >
            Buy Phone Number
          </TactileButton>
        </div>
      </div>

      {/* Telephony Infrastructure & Carrier Settings Panel */}
      {showTelephonySettings ? (
        <SolidCard className="p-5 border-[#6344E7]/30 bg-[#FAF9FD]" data-testid="numbers-telephony-settings">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4 pb-3 border-b border-[#E4E2EB]">
            <div>
              <div className="flex items-center gap-2">
                <Server className="w-4 h-4 text-[#6344E7]" />
                <h3 className="text-sm font-bold text-[#0F0E17]">Telephony Infrastructure & Calling Trunks</h3>
              </div>
              <p className="text-xs text-[#524E5E] mt-0.5">
                The entire website respects this selection in real-time. Switching carriers changes the live dialer,
                number search catalog, and async provisioning instantly.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={refreshProviderInfo}
                disabled={providerBusy}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-lg border border-[#E4E2EB] bg-white text-[#524E5E] hover:text-[#0F0E17] transition-colors"
              >
                <RefreshCw className={`w-3 h-3 ${providerBusy ? 'animate-spin' : ''}`} />
                Refresh
              </button>
              <button
                type="button"
                onClick={() => setShowTelephonySettings(false)}
                className="text-xs text-[#524E5E] hover:text-[#0F0E17] p-1"
                aria-label="Close telephony settings"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            {/* Telnyx Trunk Card */}
            {(() => {
              const telnyxSt = providerInfo?.providers?.find((p) => p.id === 'telnyx');
              const isTelnyxActive = (providerInfo?.activeProvider || 'telnyx') === 'telnyx';
              const isReady = Boolean(telnyxSt?.ready);
              return (
                <div
                  className={`rounded-xl border p-4 transition-all ${
                    isTelnyxActive
                      ? 'border-[#6344E7] bg-white ring-1 ring-[#6344E7] shadow-xs'
                      : 'border-[#E4E2EB] bg-white hover:border-[#8C879A]'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Radio className="w-4 h-4 text-[#6344E7]" />
                      <span className="text-sm font-bold text-[#0F0E17]">Telnyx Telephony</span>
                    </div>
                    {isTelnyxActive ? (
                      <span className="text-[10px] uppercase font-bold text-[#6344E7] bg-[#6344E7]/10 px-2 py-0.5 rounded font-mono">
                        Active Trunk
                      </span>
                    ) : (
                      <span className={`text-[10px] font-mono px-2 py-0.5 rounded font-semibold ${isReady ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
                        {isReady ? 'Ready' : 'Setup Incomplete'}
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-[#524E5E] space-y-1 mb-3 font-mono">
                    <div>Caller ID: <span className="text-[#0F0E17] font-semibold">{telnyxSt?.phoneNumber || '+13526146416'}</span></div>
                    <div>Connection ID: <span className="text-[#0F0E17]">{telnyxSt?.connectionId || '3041007474451679060'}</span></div>
                    <div>Webhook: <span className="text-[#0F0E17]">/api/telnyx/webhook</span></div>
                    <div>Audio Stream: <span className="text-[#0F0E17]">/ws/telnyx-stream</span></div>
                    {telnyxSt?.balance !== undefined && (
                      <div>Prepaid Credit: <span className="text-[#0F0E17] font-semibold">${Number(telnyxSt.balance || 0).toFixed(2)}</span></div>
                    )}
                  </div>
                  <TactileButton
                    variant={isTelnyxActive ? 'primary' : 'secondary'}
                    size="sm"
                    className="w-full text-xs"
                    disabled={isTelnyxActive || providerBusy}
                    loading={providerBusy && !isTelnyxActive}
                    onClick={() => handleSwitchProvider('telnyx')}
                  >
                    {isTelnyxActive ? 'Currently Active Trunk' : 'Switch to Telnyx'}
                  </TactileButton>
                </div>
              );
            })()}

            {/* Vobiz Trunk Card */}
            {(() => {
              const vobizSt = providerInfo?.providers?.find((p) => p.id === 'vobiz');
              const isVobizActive = providerInfo?.activeProvider === 'vobiz';
              const isReady = Boolean(vobizSt?.ready);
              return (
                <div
                  className={`rounded-xl border p-4 transition-all ${
                    isVobizActive
                      ? 'border-[#6344E7] bg-white ring-1 ring-[#6344E7] shadow-xs'
                      : 'border-[#E4E2EB] bg-white hover:border-[#8C879A]'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Radio className="w-4 h-4 text-[#6344E7]" />
                      <span className="text-sm font-bold text-[#0F0E17]">Vobiz Telephony</span>
                    </div>
                    {isVobizActive ? (
                      <span className="text-[10px] uppercase font-bold text-[#6344E7] bg-[#6344E7]/10 px-2 py-0.5 rounded font-mono">
                        Active Trunk
                      </span>
                    ) : (
                      <span className={`text-[10px] font-mono px-2 py-0.5 rounded font-semibold ${isReady ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
                        {isReady ? 'Ready' : 'Setup Incomplete'}
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-[#524E5E] space-y-1 mb-3 font-mono">
                    <div>Auth ID: <span className="text-[#0F0E17] font-semibold">{vobizSt?.accountInfo?.auth_id || 'MA_LX2CKOU1'}</span></div>
                    <div>App ID: <span className="text-[#0F0E17] font-semibold">{vobizSt?.accountInfo?.app_id || '551682'}</span></div>
                    <div>Answer URL: <span className="text-[#0F0E17]">/api/vobiz/answer</span></div>
                    <div>Hangup URL: <span className="text-[#0F0E17]">/api/vobiz/hangup</span></div>
                    <div>Fallback URL: <span className="text-[#0F0E17]">/api/vobiz/fallback</span></div>
                    <div>Audio Stream: <span className="text-[#0F0E17]">/ws/vobiz-stream</span></div>
                  </div>
                  <TactileButton
                    variant={isVobizActive ? 'primary' : 'secondary'}
                    size="sm"
                    className="w-full text-xs"
                    disabled={isVobizActive || providerBusy}
                    loading={providerBusy && !isVobizActive}
                    onClick={() => handleSwitchProvider('vobiz')}
                  >
                    {isVobizActive ? 'Currently Active Trunk' : 'Switch to Vobiz'}
                  </TactileButton>
                </div>
              );
            })()}
          </div>
        </SolidCard>
      ) : providerInfo ? (
        /* Active Telephony Infrastructure Banner with Configure Quick Action */
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]" data-testid="numbers-provider-banner">
          <div className="flex items-center gap-2.5">
            <Radio className="w-4 h-4 text-[#6344E7] shrink-0" />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-[#0F0E17]">
                  Trunk: {providerInfo.activeLabel || providerInfo.activeProvider}
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-semibold">
                  Live Infrastructure
                </span>
              </div>
              <p className="text-[11px] text-[#524E5E] mt-0.5">
                All numbers are routed and provisioned directly through {providerInfo.activeLabel || providerInfo.activeProvider}.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {providerInfo.phoneNumber && (
              <div className="text-left sm:text-right text-[11px] text-[#524E5E] font-mono">
                Caller ID: <span className="font-bold text-[#0F0E17]">{providerInfo.phoneNumber}</span>
              </div>
            )}
            <button
              type="button"
              onClick={() => setShowTelephonySettings(true)}
              className="text-xs font-semibold text-[#6344E7] hover:underline shrink-0"
            >
              Configure Trunk →
            </button>
          </div>
        </div>
      ) : null}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <SolidCard className="p-4">
          <div className="text-[10px] font-bold text-[#8C879A] uppercase">Owned lines</div>
          <div className="text-2xl font-bold text-[#0F0E17]">{phoneNumbers.length}</div>
        </SolidCard>
        <SolidCard className="p-4">
          <div className="text-[10px] font-bold text-[#8C879A] uppercase">Available to assign</div>
          <div className="text-2xl font-bold text-[#047857]">{unassignedCount}</div>
        </SolidCard>
        <SolidCard className="p-4">
          <div className="text-[10px] font-bold text-[#8C879A] uppercase">Linked to agents</div>
          <div className="text-2xl font-bold text-[#6344E7]">{assignedCount}</div>
        </SolidCard>
      </div>

      {/* Money the current lines cost per month, from the server's rates. */}
      <div className="text-[11px] text-[#524E5E]">
        Monthly rental for these {phoneNumbers.length} line
        {phoneNumbers.length === 1 ? '' : 's'}:{' '}
        <span className="font-mono font-semibold text-[#0F0E17]">
          ${monthlyRentalUsd.toFixed(2)}
        </span>{' '}
        per month. Call time is billed separately from your wallet.
      </div>

      {/* Numbers Inventory Table Card */}
      <SolidCard padding="p-0" className="overflow-hidden">
        <div className="overflow-x-auto touch-pan-x">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[10px] font-bold text-[#8C879A] uppercase tracking-wider">
                <th className="py-3 px-5">Phone Number</th>
                <th className="py-3 px-4">Telephony Platform</th>
                <th className="py-3 px-4">Location / Type</th>
                <th className="py-3 px-4">Assigned AI Employee</th>
                <th className="py-3 px-4 font-mono">Monthly Rate</th>
                <th className="py-3 px-4">Calls</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E4E2EB]">
              {/* chisel: layout-stable skeleton while loading; explicit empty state otherwise */}
              {isLoading && phoneNumbers.length === 0 ? (
                <tr>
                  <td colSpan={8} className="p-0">
                    <PhoneNumberRowSkeleton rows={3} />
                  </td>
                </tr>
              ) : phoneNumbers.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center">
                    <div className="max-w-xs mx-auto space-y-2">
                      <div className="w-10 h-10 rounded-2xl bg-[#F0EEF6] flex items-center justify-center text-[#6344E7] mx-auto">
                        <Phone className="w-5 h-5" />
                      </div>
                      <p className="text-xs font-bold text-[#0F0E17]">No active phone lines</p>
                      <p className="text-[11px] text-[#524E5E]">
                        Buy a virtual number to begin routing calls to your AI employees.
                      </p>
                      <TactileButton onClick={onOpenBuyModal} variant="primary" size="sm" icon={Plus}>
                        Buy number
                      </TactileButton>
                    </div>
                  </td>
                </tr>
              ) : (
                phoneNumbers.map((num) => (
                  <tr key={num.id} className="hover:bg-[#FAF9FD] transition-colors">
                    {/* Number & Capabilities */}
                    <td className="py-4 px-5">
                    <div className="font-mono font-bold text-sm text-[#0F0E17] flex items-center gap-2 flex-wrap">
                      <Phone className="w-3.5 h-3.5 text-[#6344E7]" />
                      <span>{num.number}</span>
                      {num.isDevSandbox && (
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-amber-50 text-amber-900 border border-amber-200">
                          {num.label || 'Shared test line'}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 mt-1">
                      {num.capabilities?.map((cap) => (
                        <span key={cap} className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-[#F0EEF6] text-[#524E5E] border border-[#E4E2EB]">
                          {cap}
                        </span>
                      ))}
                    </div>
                  </td>

                  {/* Telephony Platform */}
                  <td className="py-4 px-4">
                    <TelephonyPlatformBadge
                      provider={num.provider || (num.telnyxNumberId ? 'telnyx' : num.plivoNumberId ? 'vobiz' : providerInfo?.activeProvider || 'vobiz')}
                    />
                  </td>

                  {/* Locality */}
                  <td className="py-4 px-4">
                    <div className="font-semibold text-[#0F0E17]">{num.locality}</div>
                    <div className="text-[11px] text-[#524E5E]">{num.country} • {num.type}</div>
                  </td>

                  {/* Assigned Agent Dropdown */}
                  <td className="py-4 px-4">
                    <select
                      value={num.assignedAgentId || ''}
                      onChange={async (e) => {
                        try {
                          await assignNumberToAgent(num.id, e.target.value);
                          showToast(e.target.value ? 'Number assigned' : 'Number unassigned', 'success');
                        } catch (err) {
                          showToast(err.message || 'Could not assign number', 'error');
                        }
                      }}
                      className="bg-[#FAF9FD] border border-[#E4E2EB] hover:border-[#D1CFDB] rounded-xl px-2.5 py-1.5 text-xs text-[#0F0E17] font-medium focus:outline-none focus:border-[#6344E7] transition-colors"
                    >
                      <option value="">Unassigned (Pool)</option>
                      {agents.map((agent) => (
                        <option key={agent.id} value={agent.id}>
                          {agent.name} ({agent.role})
                        </option>
                      ))}
                    </select>
                  </td>

                  {/* Monthly Cost */}
                  <td className="py-4 px-4 font-mono text-[#524E5E]">
                    ${Number(num.monthlyCost || 0).toFixed(2)}/mo
                  </td>

                  {/* Line-level inbound/outbound switches */}
                  <td className="py-4 px-4">
                    <div className="flex flex-col gap-1">
                      <label className="flex items-center gap-1.5 text-[10px] text-[#524E5E]">
                        <input
                          type="checkbox"
                          checked={num.inboundEnabled !== false}
                          onChange={async (e) => {
                            try {
                              await updateNumberRouting(num.id, {
                                inboundEnabled: e.target.checked,
                              });
                            } catch (err) {
                              showToast(err.message || 'Could not update', 'error');
                            }
                          }}
                          data-testid={`number-inbound-${num.id}`}
                          className="w-3 h-3 accent-[#6344E7]"
                        />
                        Accepts calls
                      </label>
                      <label className="flex items-center gap-1.5 text-[10px] text-[#524E5E]">
                        <input
                          type="checkbox"
                          checked={num.outboundEnabled !== false}
                          onChange={async (e) => {
                            try {
                              await updateNumberRouting(num.id, {
                                outboundEnabled: e.target.checked,
                              });
                            } catch (err) {
                              showToast(err.message || 'Could not update', 'error');
                            }
                          }}
                          data-testid={`number-outbound-${num.id}`}
                          className="w-3 h-3 accent-[#6344E7]"
                        />
                        Can call out
                      </label>
                    </div>
                  </td>

                  {/* Status */}
                  <td className="py-4 px-4">
                    <StatusBadge status={num.status} size="xs" />
                  </td>

                  {/* Actions */}
                  <td className="py-4 px-5 text-right">
                    <button
                      type="button"
                      onClick={() => {
                        if (confirm(`Release ${num.number}? It will be returned to the carrier pool.`)) {
                          releasePhoneNumber(num.id);
                        }
                      }}
                      className="text-xs font-semibold text-[#DC2626] hover:underline"
                    >
                      Release
                    </button>
                  </td>
                </tr>
              )))}
            </tbody>
          </table>
        </div>
      </SolidCard>

      {/* BUY VIRTUAL NUMBER MODAL */}
      <Modal
        isOpen={isBuyModalOpen}
        onClose={onCloseBuyModal}
        title={
          purchasedSuccess
            ? 'Number ready'
            : !kycApproved
              ? 'Verify identity'
              : 'Buy Virtual Telephone Number'
        }
        subtitle={
          purchasedSuccess
            ? undefined
            : !kycApproved
              ? 'One quick ID check unlocks phone numbers and live calls.'
              : 'Only numbers currently available in your selected country are shown.'
        }
        maxWidth="max-w-2xl"
      >
        <div className="space-y-5">
          {purchasedSuccess ? (
            <div className="p-8 text-center space-y-2">
              <CheckCircle2 className="w-10 h-10 text-[#047857] mx-auto animate-bounce" />
              <h3 className="text-base font-bold text-[#0F0E17]">Number Successfully Provisioned!</h3>
              <p className="font-mono text-sm text-[#6344E7]">{purchasedSuccess}</p>
              <p className="text-xs text-[#524E5E]">Inbound calls will now route directly to your selected AI agent.</p>
            </div>
          ) : !kycApproved ? (
            <VerifyIdentityCard
              variant="gate"
              onApproved={() => {
                setKycApproved(true);
              }}
            />
          ) : (
            <>
              {buyError && (
                <div
                  data-testid="buy-number-error"
                  role="alert"
                  className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900 flex items-start gap-2"
                >
                  <p className="flex-1">{buyError}</p>
                  <button
                    type="button"
                    aria-label="Dismiss"
                    className="shrink-0 p-1 rounded-md hover:bg-red-100"
                    onClick={() => setBuyError(null)}
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}

              {/* Price and affordability, both from the server. USD only. */}
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
                <div className="text-[11px] text-[#524E5E]">
                  <span className="font-semibold text-[#0F0E17]">
                    {priceKnown ? `$${numberPriceUsd.toFixed(2)}` : 'Loading price…'} / month
                  </span>
                  {', charged to your wallet when you buy.'}
                  <span className="block mt-0.5 text-[10px] text-[#8C879A]">
                    Same rate on every number below — monthly rental.
                  </span>
                  <span className="block mt-0.0">
                    Wallet: ${balanceUsd.toFixed(2)}
                  </span>
                </div>
                {priceKnown && !canAffordNumber && (
                  <button
                    type="button"
                    className="shrink-0 text-[11px] font-semibold text-[#B45309] hover:underline"
                    onClick={() => openAddFunds?.('buy-number')}
                  >
                    Add credit to buy a number
                  </button>
                )}
              </div>

              {/* Carrier Trunk Indicator */}
              {providerInfo && (
                <div className="flex items-center justify-between px-3 py-2 rounded-xl bg-[#6344E7]/5 border border-[#6344E7]/20 text-[11px]">
                  <span className="text-[#524E5E]">Telephony Infrastructure</span>
                  <span className="font-bold text-[#6344E7] uppercase tracking-wide">
                    {providerInfo.activeLabel || providerInfo.activeProvider} (Active)
                  </span>
                </div>
              )}

              {/* Search Filters */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
                {/* Country */}
                <div>
                  <label className="block text-[10px] font-bold text-[#8C879A] uppercase mb-1">Country</label>
                  <select
                    value={selectedCountry}
                    onChange={(e) => setSelectedCountry(e.target.value)}
                    className="w-full bg-white border border-[#E4E2EB] rounded-lg p-2 min-h-[40px] sm:min-h-[34px] text-base sm:text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                    data-testid="buy-number-country"
                  >
                    {countries.map((c) => (
                      <option key={c.code} value={c.code}>
                        {c.name} ({c.dial})
                      </option>
                    ))}
                  </select>
                </div>

                {/* Type */}
                <div>
                  <label className="block text-[10px] font-bold text-[#8C879A] uppercase mb-1">Number Type</label>
                  <select
                    value={selectedType}
                    onChange={(e) => setSelectedType(e.target.value)}
                    className="w-full bg-white border border-[#E4E2EB] rounded-lg p-2 min-h-[40px] sm:min-h-[34px] text-base sm:text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                  >
                    <option value="Local DID">Local DID (Area Code)</option>
                    <option value="Toll-Free">Toll-Free (800 / 888)</option>
                    <option value="All">All Types</option>
                  </select>
                </div>

                {/* Area Code */}
                <div>
                  <label className="block text-[10px] font-bold text-[#8C879A] uppercase mb-1">Area Code / Prefix</label>
                  <input
                    type="text"
                    value={searchAreaCode}
                    onChange={(e) => setSearchAreaCode(e.target.value)}
                    placeholder="e.g. 415, 212, 800"
                    className="w-full bg-white border border-[#E4E2EB] rounded-lg p-2 min-h-[40px] sm:min-h-[34px] text-base sm:text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                  />
                </div>
              </div>

              {/* Direct Agent Binding Dropdown */}
              <div className="p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <span className="text-xs font-bold text-[#0F0E17] block">Assign Directly to AI Employee</span>
                  <span className="text-[11px] text-[#524E5E]">Optional: Route all inbound traffic immediately to this agent.</span>
                </div>
                <select
                  value={targetAgentId}
                  onChange={(e) => setTargetAgentId(e.target.value)}
                  className="bg-white border border-[#E4E2EB] rounded-xl px-3 py-2 sm:py-1.5 min-h-[40px] sm:min-h-[34px] text-base sm:text-xs text-[#0F0E17] font-semibold focus:outline-none focus:border-[#6344E7] transition-colors"
                >
                  <option value="">Leave Unassigned (Pool)</option>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} ({a.role})
                    </option>
                  ))}
                </select>
              </div>

              {/* Available Inventory Results */}
              <div className="space-y-2 max-h-72 overflow-y-auto transition-opacity duration-200">
                {catalogLoading ? (
                  <CatalogSkeleton rows={4} />
                ) : catalogError ? (
                  <div className="p-6 text-center text-xs text-red-800 bg-red-50 border border-red-200 rounded-xl flex items-start gap-2">
                    <p className="flex-1">{catalogError}</p>
                    <button type="button" aria-label="Dismiss" onClick={() => setCatalogError(null)}>
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ) : filteredCatalog.length === 0 ? (
                  <div className="p-8 text-center text-xs text-[#524E5E]">
                    No phone numbers are available for <strong>{selectedCountry}</strong> right
                    now. Try another country or check back later.
                  </div>
                ) : (
                  filteredCatalog.map((item) => (
                    <div
                      key={item.formatted || item.number || item.e164}
                      className="p-3.5 rounded-xl bg-white border border-[#E4E2EB] hover:border-[#D1CFDB] flex items-center justify-between gap-4 transition-all shadow-2xs"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-[#F0EEF6] border border-[#E4E2EB] flex items-center justify-center text-[#6344E7]">
                          <Phone className="w-3.5 h-3.5" />
                        </div>
                        <div>
                          <div className="font-mono font-bold text-sm text-[#0F0E17] flex items-center gap-2">
                            <span>{item.number}</span>
                            <TelephonyPlatformBadge
                              provider={item.provider || providerInfo?.activeProvider || 'vobiz'}
                              size="xs"
                            />
                          </div>
                          <div className="text-[10px] text-[#524E5E]">{item.locality || item.region || 'National'} • {item.type}</div>
                        </div>
                      </div>

                      <div className="flex items-center gap-3">
                        <span className="text-xs font-mono font-semibold text-[#524E5E]">
                          ${Number(
                            numberPriceUsd || item.monthlyUsd || item.fee || 0
                          ).toFixed(2)}/mo
                          {item.source === 'inventory' ? (
                            <span className="ml-1 text-[10px] text-[#047857]">In stock</span>
                          ) : null}
                        </span>
                        <TactileButton
                          size="xs"
                          variant="primary"
                          disabled={buying || (priceKnown && !canAffordNumber)}
                          loading={buying}
                          onClick={() => handleBuyNumber(item)}
                          data-testid="buy-number-submit"
                        >
                          {buying ? 'Buying…' : 'Buy & Bind'}
                        </TactileButton>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </div>
      </Modal>
    </div>
  );
}
