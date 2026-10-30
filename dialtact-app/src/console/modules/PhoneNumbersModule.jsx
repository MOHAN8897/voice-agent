import React, { useState, useEffect, useRef } from 'react';
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
import { Badge, StatusBadge } from '../ui/StatusBadge';
import { PageHeader } from '../ui/PageHeader';
import { formatInr, walletAmounts } from '../../lib/money';
import { humanizeToken } from '../../lib/internalLabels';
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';
import { useWorkspace } from '../context/WorkspaceContext';
import { showToast } from '../ui/ToastHost';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { VoiceServiceKycCard } from '../ui/VoiceServiceKycCard';
import { VerifyIdentityCard } from '../ui/VerifyIdentityCard';
import { CatalogSkeleton, PhoneNumberRowSkeleton } from '../ui/Skeleton';
import { Tabs } from '../ui/Tabs';

/** "₹X / month", or "Free" when the admin set the monthly rent to zero. */
function monthlyRentLabel(inr) {
  const n = Number(inr);
  if (!Number.isFinite(n)) return 'Price unavailable';
  return n === 0 ? 'Free' : `${formatInr(n)} / month`;
}

/** Same day next month, clamped to the month's last day (as the server renews). */
function addOneMonth(date) {
  const d = new Date(date);
  const day = d.getDate();
  d.setDate(1);
  d.setMonth(d.getMonth() + 1);
  const last = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
  d.setDate(Math.min(day, last));
  return d;
}

function formatRenewalDate(value) {
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

/** Number types the buy dialog filters by, with what each means for the caller. */
export const NUMBER_CATEGORIES = [
  { id: 'all', label: 'All', help: 'Every number available in this country right now.' },
  { id: 'mobile', label: 'Mobile', help: 'A 10-digit mobile-series number. It is not tied to a city.' },
  { id: 'landline', label: 'Landline', help: 'A city landline with an STD code, such as 080 for Bengaluru. Callers see a local business number.' },
  { id: 'toll_free', label: 'Toll-free', help: 'Callers ring it free of charge, such as 1800 numbers in India.' },
];

function catalogCategory(item) {
  if (item.category) return item.category;
  return String(item.type || '').toLowerCase().includes('toll') ? 'toll_free' : 'other';
}

function categoryName(item) {
  const id = catalogCategory(item);
  return item.categoryLabel || NUMBER_CATEGORIES.find((c) => c.id === id)?.label || 'Other';
}

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
  return (
    <Badge tone="neutral" size={size === 'xs' ? 'xs' : 'sm'} className="font-sans" title="Calls on this number go through Dialtact's phone network">
      Dialtact line
    </Badge>
  );
}

export function PhoneNumbersModule({ isBuyModalOpen, onCloseBuyModal, onOpenBuyModal, onNavigate }) {
  const { user } = useAuth();
  // A workspace scheduled for deletion may only restore or export; every other API
  // answers 403 and the client signs out. Do not call them from this page.
  const workspaceLocked = user?.tenantStatus === 'quarantined';
  const purchaseIntentKey = user?.tenantId && user?.id ? `dialtact_number_intent:${user.tenantId}:${user.id}` : null;
  const resumedIntent = useRef(null);
  const restoredCountry = useRef(false);
  const purchaseLock = useRef(false);
  const [pendingNumber, setPendingNumber] = useState(null);
  const {
    phoneNumbers,
    agents,
    availableCatalog,
    buyPhoneNumber,
    assignNumberToAgent,
    releasePhoneNumber,
    buyNumberPreselectedAgent,
    setBuyNumberPreselectedAgent,
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
  const [numberCategory, setNumberCategory] = useState('all');
  const [searchAreaCode, setSearchAreaCode] = useState('');
  // The server filters by area too (it reads further into the inventory), so wait
  // for typing to settle before asking it.
  const [areaQuery, setAreaQuery] = useState('');
  useEffect(() => {
    const id = window.setTimeout(() => setAreaQuery(searchAreaCode.trim()), 400);
    return () => window.clearTimeout(id);
  }, [searchAreaCode]);
  const [targetAgentId, setTargetAgentId] = useState(buyNumberPreselectedAgent || '');
  const [purchasedSuccess, setPurchasedSuccess] = useState(null);
  const [buyError, setBuyError] = useState(null);
  const [buying, setBuying] = useState(false);
  // ordering: wallet debit + carrier order accepted; provisioning: waiting for
  // the carrier to confirm the line. Shown so a slow carrier never looks frozen.
  const [buyPhase, setBuyPhase] = useState(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState(null);
  const [kycApproved, setKycApproved] = useState(false);
  const [kycMode, setKycMode] = useState('checking');
  const [kycLoading, setKycLoading] = useState(false);
  const [kycStatusError, setKycStatusError] = useState('');
  const [providerInfo, setProviderInfo] = useState(null);

  const rememberNumber = (item) => {
    const intent = { number: item.number || item.e164, country: item.country || selectedCountry, agentId: targetAgentId, savedAt: Date.now() };
    setPendingNumber(intent);
    if (purchaseIntentKey) {
      try { sessionStorage.setItem(purchaseIntentKey, JSON.stringify(intent)); } catch { /* Selection remains in this open dialog. */ }
    }
  };
  const forgetNumber = () => {
    setPendingNumber(null);
    if (purchaseIntentKey) {
      try { sessionStorage.removeItem(purchaseIntentKey); } catch { /* No stored selection. */ }
    }
  };
  useEffect(() => {
    if (!purchaseIntentKey || resumedIntent.current === purchaseIntentKey) return;
    resumedIntent.current = purchaseIntentKey;
    setPendingNumber(null);
    try {
      const intent = JSON.parse(sessionStorage.getItem(purchaseIntentKey) || 'null');
      if (!intent || !/^\+[1-9]\d{7,14}$/.test(intent.number) || !/^[A-Z]{2}$/.test(intent.country) || !Number.isFinite(intent.savedAt) || Date.now() - intent.savedAt > 86400000) return;
      restoredCountry.current = true;
      setPendingNumber(intent); setSelectedCountry(intent.country); setTargetAgentId(intent.agentId || '');
      onOpenBuyModal?.();
    } catch { /* Invalid saved data cannot start a purchase. */ }
  }, [purchaseIntentKey, onOpenBuyModal]);

  const refreshProviderInfo = async () => {
    try {
      const data = await api.telephony?.getProvider?.();
      if (data) {
        setProviderInfo(data);
        if (!restoredCountry.current && data.phoneNumber?.startsWith('+91')) {
          setSelectedCountry('IN');
        } else if (!restoredCountry.current && data.phoneNumber?.startsWith('+1')) {
          setSelectedCountry('US');
        }
      }
    } catch {}
  };

  useEffect(() => {
    if (workspaceLocked) return undefined;
    let cancelled = false;
    api.telephony
      ?.getProvider?.()
      .then((data) => {
        if (!cancelled && data) {
          setProviderInfo(data);
          if (!restoredCountry.current && data.phoneNumber?.startsWith('+91')) {
            setSelectedCountry('IN');
          } else if (!restoredCountry.current && data.phoneNumber?.startsWith('+1')) {
            setSelectedCountry('US');
          }
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [workspaceLocked]);

  useEffect(() => {
    if (!isBuyModalOpen || workspaceLocked) return;
    setBuyError(null);
    setCatalogLoading(true);
    setCatalogError(null);
    reloadCatalog?.(selectedCountry, { category: numberCategory, area: areaQuery })
      .catch((e) => setCatalogError(e.message || 'Could not load numbers for this country'))
      .finally(() => setCatalogLoading(false));
  }, [isBuyModalOpen, selectedCountry, numberCategory, areaQuery, reloadCatalog, workspaceLocked]);

  // The active carrier owns its gate. Didit remains a separate optional identity flow.
  useEffect(() => {
    if (!isBuyModalOpen || workspaceLocked) return undefined;
    let cancelled = false;
    setKycLoading(true);
    setKycMode('checking');
    setKycStatusError('');
    (async () => {
      try {
        const voiceStatus = await api.kyc.getVoiceStatus();
        if (cancelled) return;
        if (voiceStatus?.required) {
          setKycMode('voice');
          setKycApproved(Boolean(voiceStatus.approved));
          return;
        }
        const platformStatus = await api.kyc.getStatus();
        if (cancelled) return;
        setKycMode(platformStatus?.required ? 'platform' : 'none');
        setKycApproved(!platformStatus?.required || Boolean(platformStatus.approved));
      } catch (e) {
        if (!cancelled) {
          setKycMode('error');
          setKycApproved(false);
          setKycStatusError(e.message || 'Could not load verification status. Close and reopen this window to retry.');
        }
      } finally {
        if (!cancelled) setKycLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isBuyModalOpen, workspaceLocked]);

  useEffect(() => {
    if (workspaceLocked) return undefined;
    let cancelled = false;
    api.telephony
      .getCountries()
      .then((data) => {
        if (cancelled) return;
        if (data.countries?.length) setCountries(data.countries);
        if (data.default && !restoredCountry.current) setSelectedCountry(data.default);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [workspaceLocked]);

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
  // Only wallet-billed numbers pay the monthly rent; platform/test lines do not.
  const rentedNumbers = phoneNumbers.filter((n) => n.rentBilled);
  const monthlyRentInr = rentedNumbers.reduce((sum, n) => sum + (Number(n.monthlyInr) || 0), 0);
  const nextRenewal = rentedNumbers
    .filter((n) => n.nextRenewalAt)
    .sort((a, b) => String(a.nextRenewalAt).localeCompare(String(b.nextRenewalAt)))[0] || null;
  const balanceUsd = Number(wallet?.balanceUsd) || 0;
  const balanceInr = Number(wallet?.balanceInr) || 0;

  // Price and wallet top-up floor come from the server so the console can never
  // quote something `/api/telephony/buy` or `/api/billing/topup` would reject.
  const [catalog, setCatalog] = useState(null);
  useEffect(() => {
    if (workspaceLocked) return undefined;
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
  }, [workspaceLocked]);
  // USD is the only quoted currency. A missing catalog means we do not know the
  // price, so we must not invent one — the buy button stays honest by asking the
  // server, which is the authority anyway.
  // The admin "Phone number monthly rent": charged for the first month at purchase
  // and again on each monthly renewal. Zero is a real price (free numbers).
  const numberPriceUsd = Number(catalog?.rates?.numberMonthlyUsd);
  const numberPriceInr = Number(catalog?.rates?.numberMonthlyInr);
  const priceKnown = catalog != null && Number.isFinite(numberPriceInr) && numberPriceInr >= 0;
  // The server debits whichever wallet leg can cover the rent.
  const canAffordNumber = priceKnown && (
    numberPriceInr === 0 ||
    balanceInr >= numberPriceInr ||
    (Number.isFinite(numberPriceUsd) && balanceUsd >= numberPriceUsd)
  );
  const rentLabel = priceKnown ? monthlyRentLabel(numberPriceInr) : 'Price unavailable';
  const firstRenewalLabel = formatRenewalDate(addOneMonth(new Date()));

  const areaNeedle = searchAreaCode.trim().toLowerCase();
  const areaDigits = areaNeedle.replace(/\D/g, '').replace(/^0+/, '');
  const filteredCatalog = availableCatalog.filter((item) => {
    const cc = String(item.country || '').toUpperCase();
    const matchesCountry = cc === String(selectedCountry || '').toUpperCase();
    const matchesType = numberCategory === 'all' || catalogCategory(item) === numberCategory;
    const text = [item.areaLabel, item.city, item.region, item.locality, item.stdCode, item.areaCode]
      .map((v) => String(v || '').toLowerCase())
      .join(' ');
    const national = String(item.number || '').replace(/\D/g, '').slice(String(item.country || '').toUpperCase() === 'IN' ? 2 : 1);
    const matchesArea =
      !areaNeedle ||
      text.includes(areaNeedle) ||
      (areaDigits && (String(item.stdCode || '').replace(/^0+/, '') === areaDigits || national.startsWith(areaDigits)));
    return matchesCountry && matchesType && matchesArea;
  });
  const activeCategory = NUMBER_CATEGORIES.find((c) => c.id === numberCategory) || NUMBER_CATEGORIES[0];

  const completeNumberPurchase = async (catalogItem) => {
    setBuyError(null);
    if (!priceKnown) { setBuyError('The number price could not be loaded. Please reopen this window and retry.'); return; }
    if (kycMode === 'voice') {
      try {
        const st = await api.kyc.getVoiceStatus({ refresh: true });
        if (!st?.approved) {
          setKycApproved(false);
          rememberNumber(catalogItem);
          return;
        }
        setKycApproved(true);
      } catch (error) {
        setBuyError(error.message || 'Could not check phone service verification. Retry before buying.');
        return;
      }
    } else if (!kycApproved) {
      rememberNumber(catalogItem); return;
    }
    if (priceKnown && !canAffordNumber) {
      setBuyError(`A phone number costs ${monthlyRentLabel(numberPriceInr)}. Add credit to your wallet to buy one.`);
      return;
    }
    setBuying(true);
    setPurchasedSuccess(null);
    try {
      const bought = await buyPhoneNumber(catalogItem, targetAgentId || null, { onPhase: setBuyPhase });
      if (bought?.checkoutUrl) {
        return;
      }
      if (bought?.ok === false) {
        let failed;
        if (bought.failureReason === 'pending') {
          failed = 'Your number is paid for and still being activated. It will appear in your lines shortly. Do not buy it again.';
        } else if (bought.status === 'needs_attention') {
          failed = bought.failureReason;
        } else if (bought.failureReason === 'carrier_balance_exhausted') {
          failed = 'Phone numbers are temporarily unavailable. Your wallet was not charged.';
        } else if (bought.refunded) {
          failed = 'Purchase failed. The number could not be activated and the rental charge has been refunded to your wallet.';
        } else {
          failed = 'Purchase failed. The number could not be activated; your refund is being processed. Contact support if it does not appear in your wallet shortly.';
        }
        setBuyError(failed);
        if (bought.failureReason !== 'pending') await refreshWallet?.();
        return;
      }
      setPurchasedSuccess(catalogItem.formatted || catalogItem.number);
      forgetNumber();
      showToast('Number purchased — provisioning to your workspace', 'success', 5000);
      await refreshWallet?.();
      setTimeout(() => {
        setPurchasedSuccess(null);
        setBuyNumberPreselectedAgent?.(null);
        onCloseBuyModal();
      }, 1800);
    } catch (e) {
      if (e.status === 402 || e.code === 'insufficient_balance') {
        const msg = priceKnown
          ? `${e.message} A phone number costs ${monthlyRentLabel(numberPriceInr)}.`
          : e.message;
        setBuyError(msg);
        await refreshWallet?.();
      } else if (e.status === 403 || e.code === 'kyc_required' || e.code === 'voice_kyc_required') {
        setKycApproved(false);
        const message = e.code === 'voice_kyc_required'
          ? 'Complete phone service verification to buy a number.'
          : 'Your account needs an additional verification step before buying a number.';
        if (e.code === 'voice_kyc_required') {
          setKycMode('voice');
        } else {
          setKycMode('error');
          setKycStatusError(message);
        }
        setBuyError(message);
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
      setBuyPhase(null);
    }
  };

  const closeBuyModal = () => {
    forgetNumber();
    setBuyNumberPreselectedAgent?.(null);
    onCloseBuyModal();
  };

  const handleBuyNumber = async (catalogItem) => {
    if (purchaseLock.current) return;
    purchaseLock.current = true;
    setBuying(true);
    try { await completeNumberPurchase(catalogItem); }
    finally { purchaseLock.current = false; setBuying(false); }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Phone numbers (${phoneNumbers.length})`}
        description="Buy a number and connect it to an agent. Each number has a monthly rent, renewed from your wallet on its purchase date; call time is billed separately."
        actions={
          <TactileButton
            onClick={onOpenBuyModal}
            variant="primary"
            icon={Plus}
            size="md"
          >
            Buy phone number
          </TactileButton>
        }
      />

      {providerInfo ? (
        /* Active Telephony Infrastructure Banner */
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-4 rounded-card bg-surface border border-line shadow-craft-xs" data-testid="numbers-provider-banner">
          <div className="flex min-w-0 items-start gap-2.5">
            <Radio className="w-4 h-4 text-fg-subtle shrink-0 mt-0.5" aria-hidden="true" />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-copy font-semibold text-ink">
                  Phone network
                </span>
                <Badge tone="success" dot>Working</Badge>
              </div>
              <p className="text-ui text-fg-muted mt-0.5">
                Calls to and from your numbers go through Dialtact's phone network.
              </p>
            </div>
          </div>
          {providerInfo.phoneNumber && (
            <div className="text-left sm:text-right text-ui text-fg-body">
              Caller ID: <span className="font-mono tabular-nums font-semibold text-ink">{providerInfo.phoneNumber}</span>
            </div>
          )}
        </div>
      ) : null}

      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        <SolidCard padding="p-3 sm:p-4">
          <div className="text-meta text-fg-muted">Numbers you own</div>
          <div className="mt-0.5 text-heading font-mono tabular-nums text-ink">{phoneNumbers.length}</div>
        </SolidCard>
        <SolidCard padding="p-3 sm:p-4">
          <div className="text-meta text-fg-muted">Not assigned</div>
          <div className="mt-0.5 text-heading font-mono tabular-nums text-ink">{unassignedCount}</div>
        </SolidCard>
        <SolidCard padding="p-3 sm:p-4">
          <div className="text-meta text-fg-muted">Linked to agents</div>
          <div className="mt-0.5 text-heading font-mono tabular-nums text-ink">{assignedCount}</div>
        </SolidCard>
      </div>

      {/* Money the current lines cost per month, from the server's rates. */}
      <div className="text-ui text-fg-body" data-testid="numbers-rent-summary">
        Monthly rent for {rentedNumbers.length} rented line{rentedNumbers.length === 1 ? '' : 's'}:{' '}
        <span className="font-mono tabular-nums font-semibold text-ink">{formatInr(monthlyRentInr)}</span>{' '}
        per month.
        {nextRenewal ? (
          <>
            {' '}Next renewal:{' '}
            <span className="font-semibold text-ink">{formatRenewalDate(nextRenewal.nextRenewalAt)}</span>
            {', '}
            <span className="font-mono tabular-nums font-semibold text-ink">{formatInr(nextRenewal.nextRenewalInr)}</span>
            {' '}for {nextRenewal.formatted || nextRenewal.number}.
          </>
        ) : null}{' '}
        Call time is billed separately from your wallet.
      </div>

      {/* Numbers Inventory Table Card */}
      <SolidCard padding="p-0" className="overflow-hidden min-w-0">
        <div className="overflow-x-auto touch-pan-x">
          <table className="w-full min-w-[920px] text-left text-ui">
            <thead>
              <tr className="border-b border-line bg-canvas text-meta font-medium text-fg-muted">
                <th className="py-2.5 px-5">Phone number</th>
                <th className="py-2.5 px-4">Network</th>
                <th className="py-2.5 px-4">Location and type</th>
                <th className="py-2.5 px-4">Assigned agent</th>
                <th className="py-2.5 px-4">Monthly rent</th>
                <th className="py-2.5 px-4">Calls</th>
                <th className="py-2.5 px-4">Status</th>
                <th className="py-2.5 px-5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
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
                      <div className="w-10 h-10 rounded-control bg-surface-subtle flex items-center justify-center text-fg-body mx-auto">
                        <Phone className="w-5 h-5" aria-hidden="true" />
                      </div>
                      <p className="text-title text-ink">No phone numbers yet</p>
                      <p className="text-ui text-fg-muted">
                        Buy a number so callers can reach your agents.
                      </p>
                      <TactileButton onClick={onOpenBuyModal} variant="primary" size="sm" icon={Plus}>
                        Buy number
                      </TactileButton>
                    </div>
                  </td>
                </tr>
              ) : (
                phoneNumbers.map((num) => (
                  <tr key={num.id} className="hover:bg-canvas transition-colors">
                    {/* Number & Capabilities */}
                    <td className="py-4 px-5">
                    <div className="font-mono tabular-nums font-semibold text-copy text-ink flex items-center gap-2 whitespace-nowrap">
                      <Phone className="w-3.5 h-3.5 shrink-0 text-fg-subtle" aria-hidden="true" />
                      <span>{num.number}</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                      {num.isDevSandbox && (
                        <Badge tone="info" size="xs">
                          {num.label || 'Shared test line'}
                        </Badge>
                      )}
                      {num.capabilities?.map((cap) => (
                        <span key={cap} className="text-meta px-1.5 py-0.5 rounded-pill bg-surface-subtle text-fg-body border border-line">
                          {String(cap).length <= 3 ? String(cap).toUpperCase() : humanizeToken(cap)}
                        </span>
                      ))}
                    </div>
                  </td>

                  {/* Telephony Platform */}
                  <td className="py-4 px-4">
                    <TelephonyPlatformBadge
                      provider={num.provider || (num.telnyxNumberId ? 'telnyx' : num.carrierNumberId ? 'vobiz' : providerInfo?.activeProvider || 'vobiz')}
                    />
                  </td>

                  {/* Locality */}
                  <td className="py-4 px-4">
                    <div className="font-medium text-ink">{num.locality}</div>
                    <div className="text-meta text-fg-muted">{num.country} · {num.type}</div>
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
                      aria-label={`Agent for ${num.number}`}
                      className="max-w-[14rem] bg-surface border border-line hover:border-line-strong rounded-control px-2.5 py-1.5 min-h-[36px] text-base sm:text-ui text-ink focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-colors"
                    >
                      <option value="">Not assigned</option>
                      {agents.map((agent) => (
                        <option key={agent.id} value={agent.id}>
                          {agent.name} ({agent.role})
                        </option>
                      ))}
                    </select>
                  </td>

                  {/* Monthly rent and next renewal */}
                  <td className="py-4 px-4 text-fg-body" data-testid="number-rent">
                    {num.rentBilled ? (
                      <>
                        <span className="font-mono tabular-nums text-ink whitespace-nowrap">{monthlyRentLabel(num.nextRenewalInr ?? num.monthlyInr)}</span>
                        {num.nextRenewalAt ? (
                          <span className="block text-meta text-fg-muted">
                            Renews on {formatRenewalDate(num.nextRenewalAt)}
                          </span>
                        ) : (
                          <span className="block text-meta text-fg-muted">Auto-renewal off</span>
                        )}
                      </>
                    ) : (
                      <span className="text-meta text-fg-muted">No rent</span>
                    )}
                  </td>

                  {/* Line-level inbound/outbound switches */}
                  <td className="py-4 px-4">
                    <div className="flex flex-col gap-1.5">
                      <label className="flex items-center gap-2 text-ui text-fg-body whitespace-nowrap">
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
                          className="w-4 h-4 accent-accent"
                        />
                        Accepts calls
                      </label>
                      <label className="flex items-center gap-2 text-ui text-fg-body whitespace-nowrap">
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
                          className="w-4 h-4 accent-accent"
                        />
                        Can call out
                      </label>
                    </div>
                  </td>

                  {/* Status */}
                  <td className="py-4 px-4">
                    <StatusBadge status={num.status} size="xs" />
                    {num.status === 'suspended_unpaid' && (
                      <p className="mt-1 max-w-[12rem] text-meta text-danger-fg">
                        Paused: the monthly rental could not be charged. Add funds and it reactivates automatically.
                      </p>
                    )}
                    {num.status === 'release_pending' && (
                      <p className="mt-1 max-w-[12rem] text-meta text-fg-muted">
                        Release in progress with the phone network (up to 24 hours).
                      </p>
                    )}
                  </td>

                  {/* Actions */}
                  <td className="py-4 px-5 text-right">
                    {num.status !== 'release_pending' && !num.isDevSandbox && (
                      <TactileButton
                        variant="danger"
                        size="xs"
                        onClick={async () => {
                          if (!confirm(`Release ${num.number}? Calls to it stop, the rest of this month's rental is not refunded, and you may not be able to get this number back.`)) return;
                          try {
                            await releasePhoneNumber(num.id);
                            showToast('Number released', 'success');
                          } catch (err) {
                            showToast(err.message || 'Could not release number', 'error');
                          }
                        }}
                      >
                        Release
                      </TactileButton>
                    )}
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
        onClose={closeBuyModal}
        title={
          purchasedSuccess
            ? 'Number ready'
            : pendingNumber && !kycApproved
              ? 'Verify phone service'
              : 'Buy a phone number'
        }
        subtitle={
          purchasedSuccess
            ? undefined
            : pendingNumber && !kycApproved
              ? 'Complete verification, then return to confirm your number purchase.'
              : 'Choose an available number, verify your phone service, and confirm your purchase.'
        }
        maxWidth="max-w-2xl"
      >
        <div className="space-y-5">
          {workspaceLocked ? (
            <div className="rounded-card border border-warning-line bg-warning-soft p-5 text-copy text-warning-fg" role="alert" data-testid="buy-number-workspace-locked">
              This workspace is scheduled for deletion, so new numbers cannot be bought. Restore the workspace from the banner at the top of the page to buy a number.
            </div>
          ) : (<>
          {pendingNumber && !purchasedSuccess && <div className="rounded-control border border-line-strong bg-canvas p-4 space-y-2" data-testid="selected-number-review">
            <p className="text-copy font-semibold text-ink">Selected number: <span className="font-mono tabular-nums">{pendingNumber.number}</span></p>
            <p className="text-copy text-ink">{priceKnown ? `${rentLabel}, renews on ${firstRenewalLabel}` : 'Price unavailable. Reload before buying.'}</p>
            <p className="text-ui text-fg-body">Monthly rental is deducted from your prepaid wallet (GST was applied when you added funds) only when you confirm the purchase, and renews monthly. Call usage is billed separately. The number is not reserved during verification; availability and pricing are checked again before purchase.</p>
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" className="min-h-11 text-ui font-semibold text-accent-fg hover:underline" onClick={forgetNumber}>Choose a different number</button>
              {kycApproved && <TactileButton variant="primary" disabled={buying || catalogLoading || !priceKnown || !canAffordNumber || !availableCatalog.some((item) => item.number === pendingNumber.number)} onClick={() => handleBuyNumber(availableCatalog.find((item) => item.number === pendingNumber.number))} data-testid="confirm-selected-number">{buying ? 'Buying…' : 'Confirm number purchase'}</TactileButton>}
            </div>
            {kycApproved && !catalogLoading && !catalogError && !availableCatalog.some((item) => item.number === pendingNumber.number) && <p className="text-ui text-warning-fg" role="status">This number is no longer available. Choose another number below.</p>}
          </div>}
          {purchasedSuccess ? (
            <div className="p-8 text-center space-y-2">
              <CheckCircle2 className="w-10 h-10 text-success-fg mx-auto" aria-hidden="true" />
              <h3 className="text-title text-ink">Your number is ready</h3>
              <p className="font-mono tabular-nums text-copy text-ink">{purchasedSuccess}</p>
              <p className="text-ui text-fg-body">Incoming calls now go to the agent you chose.</p>
            </div>
          ) : pendingNumber && !kycApproved ? (
            kycLoading || kycMode === 'checking' ? (
              <div className="rounded-card border border-line bg-canvas p-6 text-copy text-fg-body" role="status" aria-busy="true">
                Checking verification status…
              </div>
            ) : kycMode === 'voice' ? (
              <VoiceServiceKycCard onApproved={() => setKycApproved(true)} />
            ) : kycMode === 'platform' ? (
              <VerifyIdentityCard variant="gate" onApproved={() => setKycApproved(true)} />
            ) : kycMode === 'error' ? (
              <div className="rounded-card border border-warning-line bg-warning-soft p-5 text-copy text-warning-fg" role="alert">
                {kycStatusError || 'Could not load verification status. Close and reopen this window to retry.'}
              </div>
            ) : null
          ) : (
            <>
              {buyError && (
                <div
                  data-testid="buy-number-error"
                  role="alert"
                  className="rounded-control border border-danger-line bg-danger-soft px-3 py-2 text-ui text-danger-fg flex items-start gap-2"
                >
                  <p className="flex-1">{buyError}</p>
                  <button
                    type="button"
                    aria-label="Dismiss"
                    className="shrink-0 -m-1 min-w-[32px] min-h-[32px] flex items-center justify-center rounded-control hover:bg-surface/60"
                    onClick={() => setBuyError(null)}
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}

              {buying && buyPhase && (
                <div role="status" aria-live="polite" data-testid="buy-number-phase"
                  className="rounded-control border border-info-line bg-info-soft px-3 py-2 text-ui text-info-fg">
                  {buyPhase === 'provisioning'
                    ? 'Payment received. Activating your number with the phone network; this can take up to a minute. Keep this window open.'
                    : 'Checking the number is still free and placing your order…'}
                </div>
              )}

              {/* Monthly rent and affordability, both from the server. */}
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 p-3 rounded-control bg-canvas border border-line">
                <div className="text-ui text-fg-body">
                  <span className="font-semibold text-ink">
                    {priceKnown ? `${rentLabel}, renews on ${firstRenewalLabel}` : 'Price unavailable'}
                  </span>
                  {', the first month deducted from your prepaid wallet when you confirm.'}
                  <span className="block mt-0.5 text-meta text-fg-muted">
                    Wallet credit already includes GST, charged when funds were added; no further tax is added here.
                    The rent renews on the same date each month at the price in force that day. If the wallet cannot cover it, the line is paused (not released) until you top up.
                    Call usage is billed separately. Verification is required before purchase.
                  </span>
                  <span className="block mt-1">
                    Wallet: <span className="font-mono tabular-nums font-semibold text-ink">{walletAmounts(wallet).primary}</span>
                  </span>
                </div>
                {priceKnown && !canAffordNumber && (
                  <button
                    type="button"
                    className="shrink-0 min-h-[36px] text-ui font-semibold text-accent-fg hover:underline"
                    onClick={() => openAddFunds?.('buy-number')}
                  >
                    Add credit to buy a number
                  </button>
                )}
              </div>

              {kycLoading && <p role="status" className="text-copy text-fg-body">Checking phone service verification…</p>}
              {kycStatusError && <p role="alert" className="text-copy text-danger-fg">{kycStatusError}</p>}

              {/* Search filters: country, number type and city or area code */}
              <div className="space-y-3 p-3.5 rounded-control bg-canvas border border-line">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {/* Country */}
                  <div>
                    <label htmlFor="buy-number-country" className="block text-meta font-medium text-fg-body mb-1">Country</label>
                    <select
                      id="buy-number-country"
                      value={selectedCountry}
                      onChange={(e) => setSelectedCountry(e.target.value)}
                      className="w-full bg-surface border border-line rounded-control px-3 py-2 min-h-[44px] sm:min-h-[36px] text-base sm:text-ui text-ink focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-colors"
                      data-testid="buy-number-country"
                    >
                      {countries.map((c) => (
                        <option key={c.code} value={c.code}>
                          {c.name} ({c.dial})
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* City or area code */}
                  <div>
                    <label htmlFor="buy-number-area" className="block text-meta font-medium text-fg-body mb-1">City or area code</label>
                    <input
                      id="buy-number-area"
                      type="text"
                      value={searchAreaCode}
                      onChange={(e) => setSearchAreaCode(e.target.value)}
                      placeholder={selectedCountry === 'IN' ? 'For example Bengaluru or 080' : 'For example 415'}
                      className="w-full bg-surface border border-line rounded-control px-3 py-2 min-h-[44px] sm:min-h-[36px] text-base sm:text-ui text-ink focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-colors"
                      data-testid="buy-number-area"
                    />
                  </div>
                </div>

                {/* Number type */}
                <div data-testid="buy-number-type">
                  <span id="buy-number-type-label" className="block text-meta font-medium text-fg-body mb-1">Number type</span>
                  <Tabs
                    variant="pills"
                    size="sm"
                    label="Number type"
                    value={numberCategory}
                    onChange={setNumberCategory}
                    items={NUMBER_CATEGORIES.map((c) => ({ id: c.id, label: c.label, testId: `buy-number-type-${c.id}` }))}
                  />
                  <p className="mt-1.5 text-meta text-fg-muted" data-testid="buy-number-type-help">{activeCategory.help}</p>
                </div>
              </div>

              {/* Direct Agent Binding Dropdown */}
              <div className="p-3 rounded-control bg-canvas border border-line flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="min-w-0">
                  <label htmlFor="buy-number-agent" className="text-ui font-medium text-ink block">Assign to an agent</label>
                  <span className="text-meta text-fg-muted">Optional. Incoming calls go straight to this agent.</span>
                </div>
                <select
                  id="buy-number-agent"
                  value={targetAgentId}
                  onChange={(e) => setTargetAgentId(e.target.value)}
                  className="w-full sm:w-auto sm:max-w-[16rem] bg-surface border border-line rounded-control px-3 py-2 sm:py-1.5 min-h-[44px] sm:min-h-[36px] text-base sm:text-ui text-ink focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-colors"
                >
                  <option value="">Leave unassigned</option>
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
                  <div className="p-4 text-ui text-danger-fg bg-danger-soft border border-danger-line rounded-control flex items-start gap-2">
                    <p className="flex-1">{catalogError}</p>
                    <button type="button" aria-label="Dismiss" className="-m-1 min-w-[32px] min-h-[32px] flex items-center justify-center rounded-control" onClick={() => setCatalogError(null)}>
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ) : filteredCatalog.length === 0 ? (
                  <div className="p-8 text-center text-ui text-fg-muted" data-testid="buy-number-empty">
                    {numberCategory === 'all' && !areaNeedle ? (
                      <>No phone numbers are available for <strong>{selectedCountry}</strong> right now. Try another country or check back later.</>
                    ) : (
                      <>
                        No {numberCategory === 'all' ? '' : `${activeCategory.label.toLowerCase()} `}numbers
                        {areaNeedle ? <> match <strong>{searchAreaCode.trim()}</strong></> : null} in <strong>{selectedCountry}</strong> right now.
                        {' '}Try All types or clear the city filter.
                      </>
                    )}
                  </div>
                ) : (
                  filteredCatalog.map((item) => (
                    <div
                      key={item.formatted || item.number || item.e164}
                      className="p-3.5 rounded-control bg-surface border border-line hover:border-line-strong flex flex-wrap items-center justify-between gap-3 transition-colors shadow-craft-xs"
                    >
                      <div className="flex min-w-0 items-center gap-3">
                        <div className="w-8 h-8 shrink-0 rounded-control bg-surface-subtle border border-line flex items-center justify-center text-fg-body">
                          <Phone className="w-3.5 h-3.5" aria-hidden="true" />
                        </div>
                        <div className="min-w-0">
                          <div className="font-mono tabular-nums font-semibold text-copy text-ink flex flex-wrap items-center gap-2">
                            <span>{item.number}</span>
                            <TelephonyPlatformBadge
                              provider={item.provider || providerInfo?.activeProvider || 'vobiz'}
                              size="xs"
                            />
                          </div>
                          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-meta text-fg-muted">
                            <Badge tone={catalogCategory(item) === 'landline' ? 'info' : 'neutral'} size="xs" data-testid="buy-number-category">
                              {categoryName(item)}
                            </Badge>
                            <span>{item.areaLabel || item.locality || item.region || 'National'}</span>
                          </div>
                          {item.requirements?.length ? (
                            <ul className="mt-1 space-y-0.5 text-meta text-warning-fg" data-testid="buy-number-requirements">
                              {item.requirements.map((req) => <li key={req}>{req}</li>)}
                            </ul>
                          ) : null}
                        </div>
                      </div>

                      <div className="flex items-center gap-3 ml-auto">
                        <span className="text-ui font-mono tabular-nums font-medium text-fg-body whitespace-nowrap">
                          {rentLabel}
                          {item.source === 'inventory' ? (
                            <span className="ml-1.5 font-sans text-meta text-success-fg">In stock</span>
                          ) : null}
                        </span>
                        <TactileButton
                          size="xs"
                          variant="primary"
                          disabled={buying || !priceKnown || kycLoading || kycMode === 'error' || (kycApproved && !canAffordNumber)}
                          loading={buying}
                          onClick={() => handleBuyNumber(item)}
                          data-testid="buy-number-submit"
                        >
                          {buying ? 'Please wait…' : kycApproved ? 'Buy number' : 'Choose number'}
                        </TactileButton>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
          </>)}
        </div>
      </Modal>
    </div>
  );
}
