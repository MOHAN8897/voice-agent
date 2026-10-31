import React, { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../../services/api';
import {
  Zap,
  ShieldCheck,
  Download,
  AlertCircle,
  FileText,
  Loader2,
  Pencil,
  Plus,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { PageHeader } from '../ui/PageHeader';
import { Badge } from '../ui/StatusBadge';
import { formatInr, formatUsd, relativeTime, walletAmounts } from '../../lib/money';
import { publicLabel } from '../../lib/internalLabels';
import { TactileButton } from '../ui/TactileButton';
import {
  BillingBalanceSkeleton,
  InvoiceRowsSkeleton,
  TransactionRowsSkeleton,
} from '../ui/Skeleton';
import { useWorkspace } from '../context/WorkspaceContext';
import { showToast } from '../ui/ToastHost';
import { ChannelsPanel } from './ChannelsPanel';

/** Plain-language labels for wallet ledger kinds. */
const TRANSACTION_LABEL = {
  usage_pstn: 'Phone call usage',
  usage_web: 'Browser test call',
  usage_web_test: 'Browser test call',
  usage_campaign: 'Outbound campaign',
  did_purchase: 'Phone number rent (first month)',
  did_refund: 'Phone number refund',
  did_rental: 'Phone number monthly rental',
  channel_purchase: 'Call channels',
  channel_renewal: 'Call channels renewal',
  channel_refund: 'Call channels refund',
  admin_seed: 'Welcome balance',
  admin_grant: 'Balance added',
  admin_debit: 'Balance removed',
  topup: 'Wallet top-up',
  razorpay_topup_inr: 'Wallet top-up',
  razorpay_topup: 'Wallet top-up',
  forfeiture: 'Account forfeiture',
};

/** Top-up presets in the currency checkout will charge. */
const CHARGE_PRESETS = {
  INR: [500, 1000, 2500, 5000],
  USD: [5, 10, 25, 50],
};

const BILLING_TIERS = [
  { id: 'low', label: 'Economy' },
  { id: 'medium', label: 'Standard' },
  { id: 'premium', label: 'Premium' },
];

const FIELD_CLASS =
  'w-full min-h-[40px] rounded-control border border-line bg-surface px-3 py-2 text-base sm:text-ui text-ink focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20';

function money(amount, currency = 'INR') {
  const value = Number(amount) || 0;
  if (currency === 'INR') {
    return `₹${value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (currency === 'USD') return `$${value.toFixed(2)}`;
  return `${currency} ${value.toFixed(2)}`;
}

function symbolFor(currency) {
  if (currency === 'INR') return '₹';
  if (currency === 'USD') return '$';
  return `${currency} `;
}

/** Server-published PSTN rates only; a missing rate stays unavailable rather than guessed. */
function pstnTierRate(wallet, tier) {
  const [inrField, usdField] = {
    low: ['pstnLowRateInrPerMin', 'pstnLowRateUsdPerMin'],
    medium: ['pstnMediumRateInrPerMin', 'pstnMediumRateUsdPerMin'],
    premium: ['pstnPremiumRateInrPerMin', 'pstnPremiumRateUsdPerMin'],
  }[tier];
  const inrSource = wallet?.[inrField] ?? wallet?.tierRates?.[tier]?.inrPerMin;
  const usdSource = wallet?.[usdField] ?? wallet?.tierRates?.[tier]?.usdPerMin;
  const inr = Number(inrSource);
  const usd = Number(usdSource);
  return {
    inr: inrSource != null && Number.isFinite(inr) ? inr : null,
    usd: usdSource != null && Number.isFinite(usd) ? usd : null,
  };
}

/** Renders a server-published rate, or says it is unavailable instead of inventing one. */
function DualRate({ inr, usd, per = 'min', usdDigits = 3 }) {
  const inrValue = Number(inr);
  const usdValue = Number(usd);
  const hasInr = inr != null && Number.isFinite(inrValue);
  const hasUsd = usd != null && Number.isFinite(usdValue);
  if (!hasInr && !hasUsd) {
    return <span className="text-meta text-fg-muted font-medium">Rate unavailable</span>;
  }
  return (
    <span className="text-ink font-semibold font-mono tabular-nums whitespace-nowrap">
      {hasInr && `₹${inrValue.toFixed(2)}/${per}`}
      {hasUsd && (
        <span className="text-meta text-fg-muted ml-1 font-normal">
          (${usdValue.toFixed(usdDigits)}{hasInr ? '' : `/${per}`})
        </span>
      )}
    </span>
  );
}

function formatDate(value, { withTime = false } = {}) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  });
}

function taxKindLabel(kind, ratePercent) {
  const rate = Number(ratePercent) > 0 ? ` @ ${Number(ratePercent).toFixed(2).replace(/\.00$/, '')}%` : '';
  switch (kind) {
    case 'cgst_sgst':
      return `CGST + SGST${rate}`;
    case 'igst':
      return `IGST${rate}`;
    case 'export':
      return 'Zero-rated export';
    case 'none':
      return 'No GST';
    default:
      return kind ? `${kind}${rate}` : 'GST';
  }
}

/** What the customer actually paid, in the order currency and in INR. */
function invoiceTotal(inv) {
  const currency = String(inv.currency || 'INR').toUpperCase();
  const gross = Number(inv.gross ?? inv.amount ?? 0);
  const grossInr = Number(inv.grossInr ?? 0);
  if (currency === 'INR') return money(gross, 'INR');
  const inr = grossInr ? ` (${money(grossInr, 'INR')})` : '';
  return `${money(gross, currency)}${inr}`;
}

function paymentMethodLabel(method) {
  if (!method) return '—';
  const value = String(method).toLowerCase();
  const labels = {
    card: 'Card',
    upi: 'UPI',
    netbanking: 'Net banking',
    wallet: 'Wallet',
    emi: 'EMI',
  };
  return labels[value] || method;
}

function invoiceStatusTone(status) {
  const value = String(status || '').toLowerCase();
  if (value === 'issued' || value === 'paid') return 'success';
  if (value === 'refunded' || value === 'credited') return 'warning';
  return 'neutral';
}

function describeTransactionKind(row) {
  if (typeof row === 'string') {
    return TRANSACTION_LABEL[row] || row || 'Adjustment';
  }
  if (!row) return 'Adjustment';
  if (row.kind === 'usage_web_test' || row.kind === 'usage_web') return 'Browser test call';
  if (TRANSACTION_LABEL[row.kind] && String(row.kind).startsWith('channel_')) return TRANSACTION_LABEL[row.kind];
  if (row.isCampaign) return 'Outbound campaign';
  if (row.direction === 'outbound') return 'Outbound call';
  if (row.direction === 'inbound') return 'Inbound call';
  return TRANSACTION_LABEL[row.kind] || row.kind || 'Adjustment';
}

function formatRowAmount(row, serverWallet) {
  const inrPaise = Number(row.amountInrPaise || 0);
  const cents = Number(row.amountCents || 0);
  const fx = Number(serverWallet?.fxRateInr) || 95.64;
  const isCredit = inrPaise > 0 || cents > 0;
  const isDebit = inrPaise < 0 || cents < 0;

  if (!isCredit && !isDebit) {
    return { primary: '$0.00', secondary: null, isCredit: false };
  }

  const sign = isCredit ? '+' : '-';
  if (row.displayAmount != null && row.displayCurrency) {
    const symbol = String(row.displayCurrency).toUpperCase() === 'INR' ? '₹' : '$';
    return { primary: `${sign}${symbol}${Number(row.displayAmount).toFixed(2)}`, isCredit };
  }
  const isTenantInr =
    (serverWallet?.walletCurrency || serverWallet?.primaryCurrency || '').toUpperCase() === 'INR' ||
    (inrPaise !== 0 && cents === 0);

  if (isTenantInr) {
    const totalPaise = Math.abs(inrPaise) + Math.round(Math.abs(cents) * fx);
    const amount = totalPaise / 100;
    const inrStr = amount < 0.01 && amount > 0 ? amount.toFixed(3) : amount.toFixed(2);
    return { primary: `${sign}₹${inrStr}`, isCredit };
  }

  const totalCents = Math.abs(cents) + Math.round(Math.abs(inrPaise) / fx);
  const effectiveUsd = totalCents / 100;
  const usdStr = effectiveUsd < 0.01 && effectiveUsd > 0 ? effectiveUsd.toFixed(3) : effectiveUsd.toFixed(2);
  return { primary: `${sign}$${usdStr}`, isCredit };
}

function toCsv(rows, serverWallet) {
  const header = ['when', 'activity_type', 'description', 'reference', 'duration_sec', 'inr', 'usd'];
  const fx = Number(serverWallet?.fxRateInr) || 95.64;
  const body = rows.map((r) => {
    const inrPaise = Number(r.amountInrPaise) || 0;
    const cents = Number(r.amountCents) || 0;
    const inrVal = ((inrPaise + cents * fx) / 100).toFixed(2);
    const usdVal = ((cents + inrPaise / fx) / 100).toFixed(2);
    return [
      r.createdAt || '',
      describeTransactionKind(r),
      r.description || '',
      r.referenceId || '',
      r.durationSec ?? '',
      inrVal,
      usdVal,
    ];
  });
  const escape = (cell) => `"${String(cell).replace(/"/g, '""')}"`;
  return [header, ...body].map((line) => line.map(escape).join(',')).join('\n');
}

export function BillingModule() {
  const {
    wallet,
    openAddFunds,
    isAddFundsOpen,
    refreshWallet,
  } = useWorkspace();

  const [serverWallet, setServerWallet] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [lastSession, setLastSession] = useState(null);
  const [razorpayEnabled, setRazorpayEnabled] = useState(false);
  const [razorpayCurrency, setRazorpayCurrency] = useState('INR');
  const [billingLoading, setBillingLoading] = useState(true);

  const [profile, setProfile] = useState(null);
  const [profileDraft, setProfileDraft] = useState(null);
  const [profileEditing, setProfileEditing] = useState(false);
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileError, setProfileError] = useState(null);

  const [expandedInvoiceId, setExpandedInvoiceId] = useState(null);
  const [invoiceDetail, setInvoiceDetail] = useState(null);
  const [invoiceDetailBusy, setInvoiceDetailBusy] = useState(false);
  const [invoiceDetailError, setInvoiceDetailError] = useState(null);
  const [downloadingInvoice, setDownloadingInvoice] = useState(null);
  const invoiceDetailSeq = useRef(0);
  const wasAddFundsOpen = useRef(false);

  const refreshBilling = useCallback(async () => {
    try {
      const [w, inv, cfg, tx, lastSess, prof] = await Promise.all([
        api.billing.getWallet(),
        api.billing.listInvoices(),
        api.billing.razorpayConfig(),
        api.billing.listTransactions(40),
        api.billing.getLastSession().catch(() => null),
        api.billing.getBillingProfile().catch(() => null),
      ]);
      setServerWallet(w);
      setInvoices(inv || []);
      setRazorpayEnabled(!!cfg?.enabled);
      setRazorpayCurrency(cfg?.currency || 'INR');
      setTransactions(tx || []);
      setLastSession(lastSess || null);
      if (prof) {
        setProfile(prof);
        setProfileError(null);
      }
    } catch {
      /* demo wallet fallback */
    } finally {
      setBillingLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshBilling();
  }, [refreshBilling]);

  // A top-up (or a delayed bank confirmation) changes balances and invoices.
  // Re-read them when the shared checkout modal closes.
  useEffect(() => {
    if (wasAddFundsOpen.current && !isAddFundsOpen) {
      refreshBilling();
      refreshWallet();
    }
    wasAddFundsOpen.current = isAddFundsOpen;
  }, [isAddFundsOpen, refreshBilling, refreshWallet]);

  const exportTransactionsCsv = useCallback(() => {
    if (typeof window === 'undefined' || !transactions.length) return;
    const blob = new Blob([toCsv(transactions, serverWallet)], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `dialtact-billing-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [transactions, serverWallet]);

  const downloadInvoice = useCallback(
    async (inv) => {
      if (downloadingInvoice) return;
      setDownloadingInvoice(inv.invoiceId);
      try {
        await api.billing.downloadInvoicePdf(inv.invoiceId, inv.invoiceNumber);
      } catch (err) {
        showToast(err.message || 'That invoice could not be downloaded. Please try again.', 'error');
      } finally {
        setDownloadingInvoice(null);
      }
    },
    [downloadingInvoice]
  );

  const toggleInvoiceDetail = useCallback(
    async (inv) => {
      if (expandedInvoiceId === inv.invoiceId) {
        invoiceDetailSeq.current += 1;
        setExpandedInvoiceId(null);
        setInvoiceDetail(null);
        setInvoiceDetailError(null);
        setInvoiceDetailBusy(false);
        return;
      }
      const seq = ++invoiceDetailSeq.current;
      setExpandedInvoiceId(inv.invoiceId);
      setInvoiceDetail(null);
      setInvoiceDetailError(null);
      setInvoiceDetailBusy(true);
      try {
        const detail = await api.billing.getInvoice(inv.invoiceId);
        if (seq === invoiceDetailSeq.current) setInvoiceDetail(detail);
      } catch (err) {
        if (seq === invoiceDetailSeq.current) {
          setInvoiceDetailError(err.message || 'Invoice details could not be loaded.');
        }
      } finally {
        if (seq === invoiceDetailSeq.current) setInvoiceDetailBusy(false);
      }
    },
    [expandedInvoiceId]
  );

  const startProfileEdit = () => {
    setProfileError(null);
    setProfileDraft({
      legalName: profile?.legalName || '',
      gstin: profile?.gstin || '',
      billingEmail: profile?.billingEmail || '',
      addressLine1: profile?.addressLine1 || '',
      addressLine2: profile?.addressLine2 || '',
      city: profile?.city || '',
      stateCode: profile?.stateCode || '',
      stateName: profile?.stateName || '',
      postalCode: profile?.postalCode || '',
      countryCode: profile?.countryCode || 'IN',
      customerType: profile?.customerType || 'individual',
      stateOptions: profile?.stateOptions || [],
    });
    setProfileEditing(true);
  };

  const cancelProfileEdit = () => {
    setProfileDraft(null);
    setProfileEditing(false);
    setProfileError(null);
  };

  const setDraftField = (key) => (event) => {
    const raw = event.target.value;
    setProfileDraft((prev) => {
      if (!prev) return prev;
      const next = { ...prev, [key]: raw };
      if (key === 'gstin') {
        next.gstin = raw.toUpperCase().replace(/[^0-9A-Z]/g, '').slice(0, 15);
        if (next.gstin) {
          next.customerType = 'business';
          if (next.gstin.length >= 2) {
            next.stateCode = next.gstin.slice(0, 2);
            const match = prev.stateOptions.find((s) => s.code === next.stateCode);
            if (match) next.stateName = match.name;
          }
        }
      }
      if (key === 'stateCode') {
        const match = prev.stateOptions.find((s) => s.code === raw);
        next.stateName = match?.name || '';
      }
      return next;
    });
  };

  const saveProfile = async (event) => {
    event.preventDefault();
    if (!profileDraft || profileBusy) return;
    setProfileBusy(true);
    setProfileError(null);
    try {
      const saved = await api.billing.updateBillingProfile({
        legalName: profileDraft.legalName,
        gstin: profileDraft.gstin || null,
        billingEmail: profileDraft.billingEmail,
        addressLine1: profileDraft.addressLine1,
        addressLine2: profileDraft.addressLine2,
        city: profileDraft.city,
        stateCode: profileDraft.stateCode,
        stateName: profileDraft.stateName,
        postalCode: profileDraft.postalCode,
        countryCode: profileDraft.countryCode || 'IN',
        customerType: profileDraft.customerType,
      });
      setProfile({ ...saved, stateOptions: profile?.stateOptions || [] });
      setProfileDraft(null);
      setProfileEditing(false);
      showToast('Invoice profile saved. New invoices will use it.', 'success');
    } catch (err) {
      setProfileError(err.message || 'Your invoice profile could not be saved.');
    } finally {
      setProfileBusy(false);
    }
  };

  const balanceInr = Number(serverWallet?.balanceInr ?? wallet?.balanceInr ?? 0);
  const balanceUsd = Number(serverWallet?.balanceUsd ?? wallet?.usdEquivalent ?? 0);
  const hasBalance = balanceInr > 0 || balanceUsd > 0;
  const remainingMinutes = Number(serverWallet?.remainingMinutes ?? wallet?.remainingMinutes ?? 0);
  const presets = CHARGE_PRESETS[razorpayCurrency] || CHARGE_PRESETS.INR;
  const currencySymbol = symbolFor(razorpayCurrency);
  const fxRate = Number(serverWallet?.fxRateInr ?? wallet?.fxRateInr) || 95.64;
  const balanceMoney = walletAmounts({ balanceInr, balanceUsd, fxRateInr: fxRate });
  const usageUsd = Number(serverWallet?.myUsageUsd ?? wallet?.myUsageUsd ?? 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Wallet and billing"
        description="Top up your wallet and download GST invoices. Calls are billed by the second, and unanswered calls are free."
      />

      {/* Primary Balance Ribbon */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* Left 2 Cols: Balance & Top-Up Buttons */}
        <SolidCard className="md:col-span-2 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className="text-ui font-medium text-fg-body flex items-center gap-1.5">
                <Zap className="w-4 h-4 text-fg-subtle" aria-hidden="true" />
                <span>Wallet balance</span>
              </span>
              <Badge tone={hasBalance ? 'success' : 'danger'} dot>
                {hasBalance ? 'Wallet funded' : 'Add funds to start'}
              </Badge>
            </div>

            {billingLoading && !serverWallet ? (
              <div className="py-2">
                <BillingBalanceSkeleton />
              </div>
            ) : (
              <div className="flex items-baseline gap-x-3 gap-y-1 my-2 flex-wrap" data-testid="billing-balance">
                <span className="text-3xl sm:text-4xl font-mono tabular-nums font-bold text-ink tracking-tight">
                  {balanceMoney.primary}
                </span>
                <span className="text-copy text-fg-body">
                  <span className="font-mono tabular-nums font-semibold text-ink">{remainingMinutes.toLocaleString('en-IN')} min</span> of talk time
                  {balanceUsd > 0 && (
                    <span className="ml-1.5 text-meta font-mono tabular-nums text-fg-muted">({formatUsd(balanceUsd)})</span>
                  )}
                </span>
              </div>
            )}

            <div className="space-y-1.5 text-ui text-fg-body">
              <p>
                Phone calls are billed by the second at the rate of your agent's voice tier:
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-1 pb-1">
                {BILLING_TIERS.map((tier) => {
                  const rate = pstnTierRate(serverWallet, tier.id);
                  return (
                    <div key={tier.id} className="p-2.5 rounded-control bg-canvas border border-line">
                      <span className="block text-meta font-medium text-fg-muted">{publicLabel(serverWallet?.tierRates?.[tier.id]?.label) || publicLabel(serverWallet?.webTierRates?.[tier.id]?.label) || tier.label}</span>
                      {rate.inr != null ? (
                        <>
                          <span className="text-ui font-mono tabular-nums font-semibold text-ink">
                            ₹{rate.inr.toFixed(2)}/min
                          </span>
                          {rate.usd != null && (
                            <>
                              {' '}
                              <span className="text-meta text-fg-muted font-mono">
                                (${rate.usd.toFixed(3)}/min)
                              </span>
                            </>
                          )}
                        </>
                      ) : (
                        <span className="text-meta text-fg-muted">Rate unavailable</span>
                      )}
                    </div>
                  );
                })}
              </div>
              <p className="text-meta text-fg-muted">
                Browser test calls use the agent's web price. Each call keeps the rate it started with,
                and unanswered calls are not billed. Spent so far in this workspace:{' '}
                <span className="font-mono tabular-nums text-fg-body">{formatInr(usageUsd * fxRate)}</span>{' '}
                <span className="font-mono tabular-nums">({formatUsd(usageUsd)})</span>.
              </p>
            </div>
          </div>

          {/* Quick top-up — one checkout path, priced by the server */}
          <div className="pt-5 mt-4 border-t border-line space-y-3">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div>
                <span className="text-title text-ink">
                  Add funds ({razorpayCurrency})
                </span>
                <p className="text-meta text-fg-muted mt-0.5 max-w-md">
                  GST is calculated at checkout and shown before you pay. Every successful top-up
                  issues a GST invoice.
                </p>
              </div>
              <TactileButton
                variant="brand"
                size="sm"
                icon={Plus}
                disabled={!razorpayEnabled}
                onClick={() => openAddFunds('billing')}
                data-testid="billing-add-funds"
              >
                Add funds
              </TactileButton>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {presets.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  disabled={!razorpayEnabled}
                  onClick={() => openAddFunds('billing', preset)}
                  data-testid={`billing-topup-${preset}`}
                  className="px-3.5 py-2 min-h-[44px] sm:min-h-[38px] rounded-control bg-surface border border-line hover:border-line-strong text-ui font-mono tabular-nums font-semibold text-ink hover:bg-canvas active:scale-[0.98] transition-[background-color,border-color,transform] shadow-craft-xs disabled:opacity-50"
                >
                  +{currencySymbol}
                  {preset.toLocaleString('en-IN')}
                </button>
              ))}
            </div>
            {!razorpayEnabled && (
              <p className="text-meta text-warning-fg" data-testid="billing-payments-unavailable">
                Card payments are temporarily unavailable. Please try again later or contact support.
              </p>
            )}
          </div>
        </SolidCard>

        <SolidCard className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-title text-ink">Payment methods</h2>
            <Badge tone={razorpayEnabled ? 'success' : 'warning'} dot>
              {razorpayEnabled ? 'Available' : 'Unavailable'}
            </Badge>
          </div>

          <ul className="space-y-2 text-ui text-fg-body">
            <li className="flex items-center justify-between p-2.5 rounded-control bg-canvas border border-line">
              <span className="font-semibold text-ink">Cards</span>
              <span>{razorpayEnabled ? 'Visa, Mastercard & more' : 'Temporarily unavailable'}</span>
            </li>
            {razorpayEnabled && razorpayCurrency === 'INR' && (
              <li className="flex items-center justify-between p-2.5 rounded-control bg-canvas border border-line">
                <span className="font-semibold text-ink">UPI &amp; net banking</span>
                <span>Instant confirmation</span>
              </li>
            )}
          </ul>

          <p className="text-meta text-fg-body leading-relaxed">
            Card and bank details stay with our payment partner. A GST invoice is issued for every
            successful top-up and is downloadable below.
          </p>
        </SolidCard>
      </div>

      {/* Invoice identity & live per-call rates */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <SolidCard className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-title text-ink flex items-center gap-2">
                <FileText className="w-4 h-4 text-fg-subtle" aria-hidden="true" />
                <span>Invoice profile</span>
              </h2>
              <p className="text-ui text-fg-muted mt-0.5">
                The legal name, GSTIN and address printed on your tax invoices.
              </p>
            </div>
            {!profileEditing && profile ? (
              <TactileButton
                variant="secondary"
                size="xs"
                icon={Pencil}
                onClick={startProfileEdit}
                data-testid="billing-profile-edit"
              >
                Edit
              </TactileButton>
            ) : null}
          </div>

          {profileEditing && profileDraft ? (
            <form className="space-y-3" onSubmit={saveProfile} data-testid="billing-profile-form">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label className="block">
                  <span className="block text-meta font-medium text-fg-body mb-1">
                    Customer type
                  </span>
                  <select
                    value={profileDraft.customerType}
                    onChange={setDraftField('customerType')}
                    className={FIELD_CLASS}
                  >
                    <option value="individual">Individual</option>
                    <option value="business">Business</option>
                  </select>
                </label>
                <label className="block">
                  <span className="block text-meta font-medium text-fg-body mb-1">
                    Registered legal name
                  </span>
                  <input
                    type="text"
                    value={profileDraft.legalName}
                    onChange={setDraftField('legalName')}
                    maxLength={255}
                    placeholder="As registered for GST"
                    className={FIELD_CLASS}
                  />
                </label>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label className="block">
                  <span className="block text-meta font-medium text-fg-body mb-1">
                    GSTIN (optional)
                  </span>
                  <input
                    type="text"
                    value={profileDraft.gstin}
                    onChange={setDraftField('gstin')}
                    maxLength={15}
                    placeholder="27ABCDE1234F1Z5"
                    autoComplete="off"
                    spellCheck={false}
                    data-testid="billing-profile-gstin"
                    className={`${FIELD_CLASS}`}
                  />
                </label>
                <label className="block">
                  <span className="block text-meta font-medium text-fg-body mb-1">
                    Billing email
                  </span>
                  <input
                    type="email"
                    value={profileDraft.billingEmail}
                    onChange={setDraftField('billingEmail')}
                    maxLength={320}
                    placeholder="accounts@company.com"
                    className={FIELD_CLASS}
                  />
                </label>
              </div>

              <label className="block">
                <span className="block text-meta font-medium text-fg-body mb-1">
                  Address line 1
                </span>
                <input
                  type="text"
                  value={profileDraft.addressLine1}
                  onChange={setDraftField('addressLine1')}
                  maxLength={255}
                  className={FIELD_CLASS}
                />
              </label>
              <label className="block">
                <span className="block text-meta font-medium text-fg-body mb-1">
                  Address line 2
                </span>
                <input
                  type="text"
                  value={profileDraft.addressLine2}
                  onChange={setDraftField('addressLine2')}
                  maxLength={255}
                  className={FIELD_CLASS}
                />
              </label>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <label className="block">
                  <span className="block text-meta font-medium text-fg-body mb-1">
                    City
                  </span>
                  <input
                    type="text"
                    value={profileDraft.city}
                    onChange={setDraftField('city')}
                    maxLength={120}
                    className={FIELD_CLASS}
                  />
                </label>
                <label className="block">
                  <span className="block text-meta font-medium text-fg-body mb-1">
                    State
                  </span>
                  <select
                    value={profileDraft.stateCode}
                    onChange={setDraftField('stateCode')}
                    className={FIELD_CLASS}
                  >
                    <option value="">Select state</option>
                    {profileDraft.stateOptions.map((state) => (
                      <option key={state.code} value={state.code}>
                        {state.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="block text-meta font-medium text-fg-body mb-1">
                    PIN code
                  </span>
                  <input
                    type="text"
                    value={profileDraft.postalCode}
                    onChange={setDraftField('postalCode')}
                    maxLength={12}
                    inputMode="numeric"
                    className={FIELD_CLASS}
                  />
                </label>
              </div>

              {profileError ? (
                <p className="text-meta text-danger-fg flex items-start gap-1.5" role="alert">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  <span>{profileError}</span>
                </p>
              ) : null}

              <div className="flex items-center gap-2 pt-1">
                <TactileButton
                  type="submit"
                  variant="brand"
                  size="sm"
                  loading={profileBusy}
                  disabled={profileBusy}
                  data-testid="billing-profile-save"
                >
                  Save profile
                </TactileButton>
                <TactileButton
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={cancelProfileEdit}
                  disabled={profileBusy}
                >
                  Cancel
                </TactileButton>
              </div>
            </form>
          ) : billingLoading && !profile ? (
            <p className="text-meta text-fg-muted">Loading invoice profile…</p>
          ) : profile ? (
            <div className="space-y-2 text-ui" data-testid="billing-profile-summary">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-meta font-medium text-fg-muted">
                    Billed to
                  </div>
                  <div className="font-semibold text-ink">
                    {profile.legalName || 'Account holder'}
                  </div>
                  <div className="text-fg-body">{profile.billingEmail || 'No billing email set'}</div>
                </div>
                <Badge tone={profile.complete ? 'success' : 'warning'} dot>
                  {profile.complete ? 'Complete' : 'Incomplete'}
                </Badge>
              </div>
              <div className="rounded-control border border-line bg-canvas p-3 text-fg-body space-y-1">
                <div>
                  <span className="text-meta font-medium text-fg-muted">
                    GSTIN{' '}
                  </span>
                  <span className="font-mono font-semibold text-ink">
                    {profile.gstin || 'Not provided'}
                  </span>
                </div>
                <div>
                  {[profile.addressLine1, profile.addressLine2].filter(Boolean).join(', ') ||
                    'No billing address yet'}
                </div>
                <div>
                  {[profile.city, profile.stateName || profile.stateCode, profile.postalCode]
                    .filter(Boolean)
                    .join(', ') || '—'}
                </div>
              </div>
              <p className="text-meta text-fg-muted">
                Invoices snapshot this profile when they are issued, so later edits never rewrite an
                invoice you already have. A GSTIN is required to claim input tax credit.
              </p>
            </div>
          ) : (
            <div className="text-meta text-fg-muted space-y-2">
              <p>Your invoice profile could not be loaded.</p>
              <TactileButton
                variant="secondary"
                size="xs"
                onClick={() => {
                  setBillingLoading(true);
                  refreshBilling();
                }}
              >
                Retry
              </TactileButton>
            </div>
          )}
        </SolidCard>

        {/* What a call costs, taken from the live rates the server bills by. */}
        <SolidCard className="space-y-3">
          <h2 className="text-title text-ink">What a call costs</h2>
          <p className="text-ui text-fg-muted">
            These are the rates your workspace is charged. Each call's actual cost is listed under
            Billing activity below.
          </p>

          <div className="space-y-2 text-ui">
            <div className="p-2.5 rounded-control bg-canvas border border-line flex justify-between items-center gap-3">
              <span className="text-fg-body">Phone call</span>
              <DualRate inr={serverWallet?.rateInrPerMin} usd={serverWallet?.rateUsdPerMin} />
            </div>
            <div className="p-2.5 rounded-control bg-canvas border border-line flex justify-between items-center gap-3">
              <span className="text-fg-body">Browser test call (usual rate; some agents differ)</span>
              <DualRate inr={serverWallet?.webRateInrPerMin} usd={serverWallet?.webRateUsdPerMin} />
            </div>
            {Object.entries(serverWallet?.webTierRates || {}).map(([tier, rate]) => <div key={tier} className="flex justify-between items-center gap-3 rounded-control border border-line bg-canvas p-2.5"><span className="text-fg-body">Browser test call · {publicLabel(rate.label) || BILLING_TIERS.find((t) => t.id === tier)?.label || tier}</span><DualRate inr={rate.inrPerMin} usd={rate.usdPerMin} /></div>)}
            <div className="p-2.5 rounded-control bg-canvas border border-line flex justify-between items-center gap-3">
              <span className="text-fg-body">Phone number rent (monthly)</span>
              <DualRate inr={serverWallet?.didMonthlyInr} usd={serverWallet?.didMonthlyUsd} per="mo" usdDigits={2} />
            </div>
          </div>

          <div className="flex items-start gap-2 text-ui text-fg-body">
            <ShieldCheck className="w-4 h-4 text-fg-subtle shrink-0 mt-0.5" aria-hidden="true" />
            <span>
              Calls stop at the minimum balance of{' '}
              <strong className="text-ink font-semibold font-mono tabular-nums">
                {formatInr(Number(serverWallet?.minBalanceUsd ?? 0) * fxRate)}
              </strong>{' '}
              <span className="font-mono tabular-nums text-fg-muted">({formatUsd(serverWallet?.minBalanceUsd ?? 0)})</span>
              . Top up to keep your agents taking calls.
            </span>
          </div>

          {lastSession?.has_call && (
            <div className="pt-3 border-t border-line space-y-2 text-ui">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <span className="font-medium text-ink flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-success" aria-hidden="true" />
                  Last call ({lastSession.duration_formatted})
                </span>
                <span className="font-mono tabular-nums font-semibold text-ink">
                  {lastSession.tenant_wallet_deduction?.amount != null
                    ? `${lastSession.tenant_wallet_deduction.currency === 'INR' ? '₹' : '$'}${Number(lastSession.tenant_wallet_deduction.amount).toFixed(2)} billed`
                    : 'Charge pending'}
                </span>
              </div>
            </div>
          )}
        </SolidCard>
      </div>

      {/* Concurrent call channels: limit, purchase, and usage analytics. */}
      <ChannelsPanel onCharged={() => { refreshBilling(); refreshWallet(); }} />

      <SolidCard padding="p-0" className="overflow-hidden min-w-0">
        <div className="p-4 sm:px-5 border-b border-line flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-title text-ink">Invoices and tax receipts</h2>
            <p className="text-ui text-fg-muted mt-0.5">
              Every successful top-up issues a GST invoice. Download the PDF, or open a row for the
              place of supply, payment reference and any credit notes.
            </p>
          </div>
          {invoices.length > 0 ? (
            <Badge tone="neutral">{invoices.length} issued</Badge>
          ) : null}
        </div>
        <div className="overflow-x-auto">
          {billingLoading && invoices.length === 0 ? (
            <InvoiceRowsSkeleton rows={3} />
          ) : invoices.length === 0 ? (
            <p className="px-4 py-8 text-center text-ui text-fg-muted">
              No invoices yet. A GST invoice is issued automatically after your first top-up.
            </p>
          ) : (
            <table className="w-full text-left text-ui">
              <thead>
                <tr className="border-b border-line bg-canvas text-meta text-fg-muted font-medium">
                  <th className="py-2.5 px-4">Invoice #</th>
                  <th className="py-2.5 px-3">Date</th>
                  <th className="py-2.5 px-3 text-right">Taxable</th>
                  <th className="py-2.5 px-3 text-right">GST</th>
                  <th className="py-2.5 px-3 text-right">Total paid</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-4 text-right">PDF</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {invoices.map((inv) => {
                  const expanded = expandedInvoiceId === inv.invoiceId;
                  return (
                    <React.Fragment key={inv.invoiceId}>
                      <tr className="hover:bg-canvas">
                        <td className="py-2.5 px-4 font-mono tabular-nums font-semibold text-ink whitespace-nowrap">
                          {inv.invoiceNumber}
                        </td>
                        <td className="py-2.5 px-3 text-fg-body whitespace-nowrap">
                          {formatDate(inv.createdAt)}
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono tabular-nums text-ink whitespace-nowrap">
                          {money(inv.taxableInr, 'INR')}
                        </td>
                        <td className="py-2.5 px-3 text-right text-ink whitespace-nowrap">
                          <div className="font-mono tabular-nums">{money(inv.taxInr, 'INR')}</div>
                          <div className="text-meta text-fg-muted font-sans">
                            {taxKindLabel(inv.taxKind, inv.taxRatePercent)}
                          </div>
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono tabular-nums font-semibold text-ink whitespace-nowrap">
                          {invoiceTotal(inv)}
                        </td>
                        <td className="py-2.5 px-3">
                          <Badge tone={invoiceStatusTone(inv.status)} className="capitalize">
                            {inv.status || 'issued'}
                          </Badge>
                        </td>
                        <td className="py-2.5 px-4">
                          <div className="flex items-center justify-end gap-1">
                            <button
                              type="button"
                              onClick={() => downloadInvoice(inv)}
                              disabled={downloadingInvoice === inv.invoiceId}
                              aria-label={`Download invoice ${inv.invoiceNumber}`}
                              title="Download PDF"
                              data-testid={`billing-invoice-download-${inv.invoiceNumber}`}
                              className="min-w-[36px] min-h-[36px] flex items-center justify-center rounded-control text-accent-fg hover:bg-accent-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
                            >
                              {downloadingInvoice === inv.invoiceId ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <Download className="w-3.5 h-3.5" />
                              )}
                            </button>
                            <button
                              type="button"
                              onClick={() => toggleInvoiceDetail(inv)}
                              aria-expanded={expanded}
                              aria-label={`${expanded ? 'Hide' : 'Show'} details for invoice ${inv.invoiceNumber}`}
                              data-testid={`billing-invoice-detail-${inv.invoiceNumber}`}
                              className="min-w-[36px] min-h-[36px] flex items-center justify-center rounded-control text-fg-body hover:bg-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                            >
                              {expanded ? (
                                <ChevronUp className="w-3.5 h-3.5" />
                              ) : (
                                <ChevronDown className="w-3.5 h-3.5" />
                              )}
                            </button>
                          </div>
                        </td>
                      </tr>
                      {expanded && (
                        <tr className="bg-canvas">
                          <td colSpan={7} className="px-4 py-3">
                            {invoiceDetailBusy ? (
                              <span className="flex items-center gap-2 text-meta text-fg-body">
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                Loading invoice details…
                              </span>
                            ) : invoiceDetailError ? (
                              <span className="flex items-center gap-2 text-meta text-danger-fg">
                                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                                {invoiceDetailError}
                              </span>
                            ) : invoiceDetail ? (
                              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-ui">
                                <div className="space-y-1.5">
                                  <div>
                                    <div className="text-meta font-medium text-fg-muted">
                                      Place of supply
                                    </div>
                                    <div className="text-ink">
                                      {invoiceDetail.placeOfSupply || '—'}
                                      {invoiceDetail.placeOfSupplyCode
                                        ? ` (${invoiceDetail.placeOfSupplyCode})`
                                        : ''}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-meta font-medium text-fg-muted">
                                      Payment reference
                                    </div>
                                    <div className="font-mono text-ink break-all">
                                      {invoiceDetail.paymentId || '—'}
                                    </div>
                                  </div>
                                </div>
                                <div className="space-y-1.5">
                                  <div>
                                    <div className="text-meta font-medium text-fg-muted">
                                      Payment method
                                    </div>
                                    <div className="text-ink">
                                      {paymentMethodLabel(invoiceDetail.paymentMethod)}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-meta font-medium text-fg-muted">
                                      Paid on
                                    </div>
                                    <div className="text-ink">
                                      {formatDate(invoiceDetail.paidAt || invoiceDetail.createdAt, {
                                        withTime: true,
                                      })}
                                    </div>
                                  </div>
                                </div>
                                <div className="space-y-1.5">
                                  <div>
                                    <div className="text-meta font-medium text-fg-muted">
                                      Billed to
                                    </div>
                                    <div className="text-ink">
                                      {invoiceDetail.buyer?.legalName || 'Account holder'}
                                    </div>
                                    <div className="font-mono text-fg-body">
                                      {invoiceDetail.customerGstin || invoiceDetail.buyer?.gstin
                                        ? `GSTIN ${invoiceDetail.customerGstin || invoiceDetail.buyer.gstin}`
                                        : 'No GSTIN on this invoice'}
                                    </div>
                                  </div>
                                  {invoiceDetail.creditNotes?.length ? (
                                    <div>
                                      <div className="text-meta font-medium text-fg-muted">
                                        Credit notes
                                      </div>
                                      {invoiceDetail.creditNotes.map((note) => (
                                        <div key={note.creditNoteId} className="text-ink">
                                          {note.creditNoteNumber} · {money(note.amountInr, 'INR')}{' '}
                                          <span className="text-fg-muted">
                                            (GST {money(note.taxInr, 'INR')})
                                          </span>
                                        </div>
                                      ))}
                                    </div>
                                  ) : null}
                                </div>
                              </div>
                            ) : null}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </SolidCard>

      {/* Every wallet movement, straight from the billing ledger. */}
      <SolidCard padding="p-0" className="overflow-hidden min-w-0">
        <div className="p-4 sm:px-5 border-b border-line flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-title text-ink">Billing activity</h2>
            <p className="text-ui text-fg-muted mt-0.5">
              Top-ups, call usage and number rentals as they were charged.
            </p>
          </div>
          <TactileButton
            variant="secondary"
            size="sm"
            icon={Download}
            onClick={exportTransactionsCsv}
            disabled={!transactions.length}
            data-testid="billing-export-csv"
          >
            Export CSV
          </TactileButton>
        </div>

        {billingLoading && transactions.length === 0 ? (
          <TransactionRowsSkeleton rows={6} />
        ) : transactions.length === 0 ? (
          <p className="px-4 py-8 text-center text-ui text-fg-muted">
            No charges yet. Add funds to place calls or buy a number.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-ui">
              <thead>
                <tr className="border-b border-line bg-canvas text-meta text-fg-muted font-medium">
                  <th className="py-2.5 px-4">When</th>
                  <th className="py-2.5 px-3">Activity</th>
                  <th className="py-2.5 px-3">Description</th>
                  <th className="py-2.5 px-4 text-right">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {transactions.map((row) => {
                  const amt = formatRowAmount(row, serverWallet);
                  const isCredit = amt.isCredit;
                  const displayAmount = amt.primary;
                  const activityLabel = describeTransactionKind(row);
                  const isWebTest = row.kind === 'usage_web_test' || row.kind === 'usage_web';

                  return (
                    <tr key={row.id} className="hover:bg-canvas transition-colors">
                      <td className="py-2.5 px-4 text-fg-body whitespace-nowrap" title={row.createdAt ? new Date(row.createdAt).toLocaleString('en-IN') : undefined}>
                        {row.createdAt ? relativeTime(row.createdAt) : '—'}
                      </td>
                      <td className="py-2.5 px-3 whitespace-nowrap">
                        <Badge tone={isCredit ? 'success' : row.isCampaign ? 'accent' : isWebTest ? 'info' : 'neutral'}>
                          {activityLabel}
                        </Badge>
                      </td>
                      <td className="py-2.5 px-3 text-ink">
                        <div className="font-medium text-ui text-ink flex items-center gap-1.5 flex-wrap">
                          <span>{row.description || activityLabel}</span>
                          {row.tier && (
                            <span
                              data-testid={`tx-tier-badge-${row.tier}`}
                              className="text-meta text-accent-fg bg-accent-soft border border-accent-soft px-1.5 py-0.5 rounded-pill font-medium"
                            >
                              {row.tierLabel || row.tier}
                            </span>
                          )}
                          {row.durationSec != null && row.durationSec > 0 && !row.description?.includes(`${row.durationSec}s`) && (
                            <span className="text-meta text-fg-body bg-canvas border border-line px-1.5 py-0.5 rounded-pill font-mono tabular-nums">
                              {row.durationSec}s
                            </span>
                          )}
                        </div>
                        {row.referenceId && (
                          <div className="text-meta font-mono text-fg-muted truncate max-w-[260px]" title={row.referenceId}>
                            {row.referenceId}
                          </div>
                        )}
                      </td>
                      <td
                        className={`py-2.5 px-4 text-right font-mono tabular-nums font-semibold whitespace-nowrap ${
                          isCredit ? 'text-success-fg' : 'text-ink'
                        }`}
                      >
                        <div>{displayAmount}</div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </SolidCard>
    </div>
  );
}
