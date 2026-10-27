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
import { TactileButton } from '../ui/TactileButton';
import {
  BillingBalanceSkeleton,
  InvoiceRowsSkeleton,
  TransactionRowsSkeleton,
} from '../ui/Skeleton';
import { useWorkspace } from '../context/WorkspaceContext';
import { showToast } from '../ui/ToastHost';

/** Plain-language labels for wallet ledger kinds. */
const TRANSACTION_LABEL = {
  usage_pstn: 'Phone call usage',
  usage_web: 'Browser test call',
  usage_web_test: 'Browser test call',
  usage_campaign: 'Outbound campaign',
  did_purchase: 'Phone number rental',
  did_refund: 'Phone number refund',
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

const FIELD_CLASS =
  'w-full min-h-[40px] rounded-xl border border-[#E4E2EB] bg-white px-3 py-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]';

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

function invoiceStatusClass(status) {
  const value = String(status || '').toLowerCase();
  if (value === 'issued' || value === 'paid') {
    return 'bg-[#22C55E]/10 text-[#15803D] border-[#22C55E]/20';
  }
  if (value === 'refunded' || value === 'credited') {
    return 'bg-[#FFFBEB] text-[#B45309] border-[#FDE68A]';
  }
  if (value === 'void' || value === 'cancelled') {
    return 'bg-slate-100 text-slate-600 border-slate-200';
  }
  return 'bg-[#FAF9FD] text-[#524E5E] border-[#E4E2EB]';
}

function describeTransactionKind(row) {
  if (typeof row === 'string') {
    return TRANSACTION_LABEL[row] || row || 'Adjustment';
  }
  if (!row) return 'Adjustment';
  if (row.kind === 'usage_web_test' || row.kind === 'usage_web') return 'Browser test call';
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

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">
          Wallet &amp; per-second billing
        </h2>
        <p className="text-xs text-[#524E5E] mt-0.5">
          Pay-as-you-go wallet. Phone and browser calls meter by the second; unanswered carrier legs are free.
        </p>
      </div>

      {/* Primary Balance Ribbon */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* Left 2 Cols: Balance & Top-Up Buttons */}
        <SolidCard className="md:col-span-2 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className="text-xs font-semibold text-[#524E5E] uppercase tracking-wider flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5 text-amber-500" />
                <span>Available talk time balance</span>
              </span>
              <span
                className={`text-[11px] font-mono font-medium px-2 py-0.5 rounded-md border ${
                  hasBalance
                    ? 'text-[#15803D] bg-[#22C55E]/10 border-[#22C55E]/20'
                    : 'text-[#B45309] bg-[#FFFBEB] border-[#FDE68A]'
                }`}
              >
                {hasBalance ? 'Wallet funded' : 'Add funds to start'}
              </span>
            </div>

            {billingLoading && !serverWallet ? (
              <div className="py-2">
                <BillingBalanceSkeleton />
              </div>
            ) : (
              <div className="flex items-baseline gap-3 my-2 flex-wrap">
                <span className="text-3xl sm:text-4xl font-mono font-bold text-[#0F0E17] tracking-tight">
                  {remainingMinutes.toLocaleString()} min
                </span>
                <span className="text-sm font-mono text-[#524E5E]">
                  {balanceInr > 0 ? (
                    <>
                      <strong className="font-semibold text-[#0F0E17]">{money(balanceInr, 'INR')}</strong>{' '}
                      <span className="text-xs text-[#8C879A]">(${balanceUsd.toFixed(2)} USD)</span>
                    </>
                  ) : (
                    `($${balanceUsd.toFixed(2)} USD)`
                  )}
                </span>
              </div>
            )}

            <div className="space-y-1.5 text-xs text-[#524E5E]">
              <p>
                Voice stacks meter by the second based on the agent's selected voice tier:
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-1 pb-1">
                <div className="p-2 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB]">
                  <span className="block text-[11px] font-semibold text-[#0F0E17]">Economical (Low)</span>
                  <span className="text-xs font-mono font-bold text-[#6344E7]">
                    ₹{Number(serverWallet?.pstnLowRateInrPerMin ?? serverWallet?.tierRates?.low?.inrPerMin ?? 4.70).toFixed(2)}/min
                  </span>{' '}
                  <span className="text-[10px] text-[#8C879A] font-mono">
                    (${Number(serverWallet?.pstnLowRateUsdPerMin ?? serverWallet?.tierRates?.low?.usdPerMin ?? 0.05).toFixed(3)}/min)
                  </span>
                </div>
                <div className="p-2 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB]">
                  <span className="block text-[11px] font-semibold text-[#0F0E17]">Standard Regional</span>
                  <span className="text-xs font-mono font-bold text-[#6344E7]">
                    ₹{Number(serverWallet?.pstnMediumRateInrPerMin ?? serverWallet?.tierRates?.medium?.inrPerMin ?? 8.46).toFixed(2)}/min
                  </span>{' '}
                  <span className="text-[10px] text-[#8C879A] font-mono">
                    (${Number(serverWallet?.pstnMediumRateUsdPerMin ?? serverWallet?.tierRates?.medium?.usdPerMin ?? 0.09).toFixed(3)}/min)
                  </span>
                </div>
                <div className="p-2 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB]">
                  <span className="block text-[11px] font-semibold text-[#0F0E17]">Flagship Live (Premium)</span>
                  <span className="text-xs font-mono font-bold text-[#6344E7]">
                    ₹{Number(serverWallet?.pstnPremiumRateInrPerMin ?? serverWallet?.tierRates?.premium?.inrPerMin ?? 14.10).toFixed(2)}/min
                  </span>{' '}
                  <span className="text-[10px] text-[#8C879A] font-mono">
                    (${Number(serverWallet?.pstnPremiumRateUsdPerMin ?? serverWallet?.tierRates?.premium?.usdPerMin ?? 0.15).toFixed(3)}/min)
                  </span>
                </div>
              </div>
              <p className="text-[11px] text-[#8C879A]">
                Web calls use the selected stack’s web price. Each call locks its rate when it starts.
                Your usage this workspace: ${Number(serverWallet?.myUsageUsd ?? wallet.myUsageUsd ?? 0).toFixed(2)}. Unanswered carrier legs are not billed.
              </p>
            </div>
          </div>

          {/* Quick top-up — one checkout path, priced by the server */}
          <div className="pt-5 mt-4 border-t border-[#E4E2EB] space-y-3">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div>
                <span className="text-xs font-semibold text-[#524E5E]">
                  Add funds ({razorpayCurrency})
                </span>
                <p className="text-[10px] text-[#8C879A] mt-0.5 max-w-md">
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
                  className="px-3.5 py-2 min-h-[38px] rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] hover:border-[#6344E7] text-xs font-mono font-bold text-[#0F0E17] hover:text-[#6344E7] active:scale-[0.98] transition-all shadow-craft-xs disabled:opacity-50"
                >
                  +{currencySymbol}
                  {preset.toLocaleString('en-IN')}
                </button>
              ))}
            </div>
            {!razorpayEnabled && (
              <p className="text-[11px] text-[#B45309]" data-testid="billing-payments-unavailable">
                Card payments are temporarily unavailable. Please try again later or contact support.
              </p>
            )}
          </div>
        </SolidCard>

        <SolidCard className="space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="font-bold text-[#0F0E17]">Payment methods</span>
            <span
              className={`text-[10px] font-medium px-2 py-0.5 rounded-md border ${
                razorpayEnabled
                  ? 'text-[#15803D] bg-[#22C55E]/10 border-[#22C55E]/20'
                  : 'text-[#92400E] bg-[#FFFBEB] border-[#FDE68A]'
              }`}
            >
              {razorpayEnabled ? 'Available' : 'Unavailable'}
            </span>
          </div>

          <ul className="space-y-2 text-xs text-[#524E5E]">
            <li className="flex items-center justify-between p-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
              <span className="font-semibold text-[#0F0E17]">Cards</span>
              <span>{razorpayEnabled ? 'Visa, Mastercard & more' : 'Temporarily unavailable'}</span>
            </li>
            {razorpayEnabled && razorpayCurrency === 'INR' && (
              <li className="flex items-center justify-between p-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
                <span className="font-semibold text-[#0F0E17]">UPI &amp; net banking</span>
                <span>Instant confirmation</span>
              </li>
            )}
          </ul>

          <p className="text-[11px] text-[#524E5E] leading-relaxed">
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
              <h3 className="text-xs font-bold text-[#0F0E17] flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-[#6344E7]" />
                <span>Invoice profile</span>
              </h3>
              <p className="text-[11px] text-[#524E5E] mt-0.5">
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
                  <span className="block text-[10px] font-semibold uppercase tracking-wider text-[#8C879A] mb-1">
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
                  <span className="block text-[10px] font-semibold uppercase tracking-wider text-[#8C879A] mb-1">
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
                  <span className="block text-[10px] font-semibold uppercase tracking-wider text-[#8C879A] mb-1">
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
                    className={`${FIELD_CLASS} font-mono uppercase`}
                  />
                </label>
                <label className="block">
                  <span className="block text-[10px] font-semibold uppercase tracking-wider text-[#8C879A] mb-1">
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
                <span className="block text-[10px] font-semibold uppercase tracking-wider text-[#8C879A] mb-1">
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
                <span className="block text-[10px] font-semibold uppercase tracking-wider text-[#8C879A] mb-1">
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
                  <span className="block text-[10px] font-semibold uppercase tracking-wider text-[#8C879A] mb-1">
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
                  <span className="block text-[10px] font-semibold uppercase tracking-wider text-[#8C879A] mb-1">
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
                  <span className="block text-[10px] font-semibold uppercase tracking-wider text-[#8C879A] mb-1">
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
                <p className="text-[11px] text-red-700 flex items-start gap-1.5" role="alert">
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
            <p className="text-[11px] text-[#8C879A]">Loading invoice profile…</p>
          ) : profile ? (
            <div className="space-y-2 text-xs" data-testid="billing-profile-summary">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-[#8C879A]">
                    Billed to
                  </div>
                  <div className="font-semibold text-[#0F0E17]">
                    {profile.legalName || 'Account holder'}
                  </div>
                  <div className="text-[#524E5E]">{profile.billingEmail || 'No billing email set'}</div>
                </div>
                <span
                  className={`text-[10px] font-medium px-2 py-0.5 rounded-md border whitespace-nowrap ${
                    profile.complete
                      ? 'text-[#15803D] bg-[#22C55E]/10 border-[#22C55E]/20'
                      : 'text-[#92400E] bg-[#FFFBEB] border-[#FDE68A]'
                  }`}
                >
                  {profile.complete ? 'Complete' : 'Incomplete'}
                </span>
              </div>
              <div className="rounded-xl border border-[#E4E2EB] bg-[#FAF9FD] p-3 text-[#524E5E] space-y-1">
                <div>
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-[#8C879A]">
                    GSTIN{' '}
                  </span>
                  <span className="font-mono font-semibold text-[#0F0E17]">
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
              <p className="text-[10px] text-[#8C879A]">
                Invoices snapshot this profile when they are issued, so later edits never rewrite an
                invoice you already have. A GSTIN is required to claim input tax credit.
              </p>
            </div>
          ) : (
            <div className="text-[11px] text-[#8C879A] space-y-2">
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
          <h3 className="text-xs font-bold text-[#0F0E17]">What a call costs</h3>
          <p className="text-[11px] text-[#524E5E]">
            These are the rates your workspace is charged. Each call's actual cost is itemised in the
            usage ledger below.
          </p>

          <div className="space-y-2 text-xs font-mono">
            <div className="p-2.5 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] flex justify-between items-center">
              <span className="text-[#524E5E]">Phone call (PSTN voice)</span>
              <span className="text-[#0F0E17] font-semibold">
                ₹{Number(serverWallet?.rateInrPerMin ?? 5.00).toFixed(2)}/min
                <span className="text-[10px] text-[#8C879A] ml-1 font-normal">
                  (${Number(serverWallet?.rateUsdPerMin ?? 0.053).toFixed(3)})
                </span>
              </span>
            </div>
            <div className="p-2.5 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] flex justify-between items-center">
              <span className="text-[#524E5E]">Default web price · stack overrides apply</span>
              <span className="text-[#0F0E17] font-semibold">
                ₹{Number(serverWallet?.webRateInrPerMin ?? 4.50).toFixed(2)}/min
                <span className="text-[10px] text-[#8C879A] ml-1 font-normal">
                  (${Number(serverWallet?.webRateUsdPerMin ?? 0.048).toFixed(3)})
                </span>
              </span>
            </div>
            {Object.entries(serverWallet?.webTierRates || {}).map(([tier, rate]) => <div key={tier} className="flex justify-between gap-3 rounded-lg border border-[#E4E2EB] bg-[#FAF9FD] p-2.5"><span className="text-[#524E5E]">{rate.label || tier} · Web calls</span><span className="font-semibold text-[#0F0E17]">₹{Number(rate.inrPerMin).toFixed(2)}/min <span className="text-[10px] text-[#8C879A]">(${Number(rate.usdPerMin).toFixed(3)})</span></span></div>)}
            <div className="p-2.5 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] flex justify-between items-center">
              <span className="text-[#524E5E]">Phone number rental</span>
              <span className="text-[#0F0E17] font-semibold">
                ₹{Number(serverWallet?.didMonthlyInr ?? 564.00).toFixed(2)}/mo
                <span className="text-[10px] text-[#8C879A] ml-1 font-normal">
                  (${Number(serverWallet?.didMonthlyUsd ?? 6.00).toFixed(2)})
                </span>
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2 text-[11px] text-[#524E5E]">
            <ShieldCheck className="w-4 h-4 text-[#15803D] shrink-0" />
            <span>
              Calls stop at the minimum balance of{' '}
              <strong className="text-[#0F0E17] font-semibold">
                ${Number(serverWallet?.minBalanceUsd ?? 0).toFixed(2)}
              </strong>
              . Top up to keep your agents taking calls.
            </span>
          </div>

          {lastSession?.has_call && (
            <div className="pt-3 border-t border-[#E4E2EB] space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-bold text-[#0F0E17] flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-500" />
                  Last call session ({lastSession.duration_formatted})
                </span>
                <span className="font-mono font-bold text-[#0F0E17]">
                  {lastSession.tenant_wallet_deduction?.amount != null
                    ? `${lastSession.tenant_wallet_deduction.currency === 'INR' ? '₹' : '$'}${Number(lastSession.tenant_wallet_deduction.amount).toFixed(2)} billed`
                    : 'Charge pending'}
                </span>
              </div>
            </div>
          )}
        </SolidCard>
      </div>

      <SolidCard padding="p-0" className="overflow-hidden">
        <div className="p-4 border-b border-[#E4E2EB] flex items-center justify-between gap-3">
          <div>
            <h3 className="text-xs font-bold text-[#0F0E17]">Invoices &amp; tax receipts</h3>
            <p className="text-[11px] text-[#524E5E] mt-0.5">
              Every successful top-up issues a GST invoice. Download the PDF, or open a row for the
              place of supply, payment reference and any credit notes.
            </p>
          </div>
          {invoices.length > 0 ? (
            <span className="text-[10px] font-mono font-semibold text-[#524E5E] bg-[#FAF9FD] border border-[#E4E2EB] px-2 py-0.5 rounded-md whitespace-nowrap">
              {invoices.length} issued
            </span>
          ) : null}
        </div>
        <div className="overflow-x-auto">
          {billingLoading && invoices.length === 0 ? (
            <InvoiceRowsSkeleton rows={3} />
          ) : invoices.length === 0 ? (
            <p className="px-4 py-6 text-center text-xs text-[#8C879A]">
              No invoices yet. A GST invoice is issued automatically after your first top-up.
            </p>
          ) : (
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[10px] text-[#524E5E] uppercase tracking-wider font-semibold">
                  <th className="py-2.5 px-4">Invoice #</th>
                  <th className="py-2.5 px-3">Date</th>
                  <th className="py-2.5 px-3 text-right">Taxable</th>
                  <th className="py-2.5 px-3 text-right">GST</th>
                  <th className="py-2.5 px-3 text-right">Total paid</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-4 text-right">PDF</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E4E2EB]">
                {invoices.map((inv) => {
                  const expanded = expandedInvoiceId === inv.invoiceId;
                  return (
                    <React.Fragment key={inv.invoiceId}>
                      <tr className="hover:bg-[#FAF9FD]/80">
                        <td className="py-2.5 px-4 font-semibold text-[#0F0E17] whitespace-nowrap">
                          {inv.invoiceNumber}
                        </td>
                        <td className="py-2.5 px-3 text-[#524E5E] whitespace-nowrap">
                          {formatDate(inv.createdAt)}
                        </td>
                        <td className="py-2.5 px-3 text-right text-[#0F0E17] whitespace-nowrap">
                          {money(inv.taxableInr, 'INR')}
                        </td>
                        <td className="py-2.5 px-3 text-right text-[#0F0E17] whitespace-nowrap">
                          <div>{money(inv.taxInr, 'INR')}</div>
                          <div className="text-[10px] text-[#8C879A] font-sans">
                            {taxKindLabel(inv.taxKind, inv.taxRatePercent)}
                          </div>
                        </td>
                        <td className="py-2.5 px-3 text-right font-bold text-[#0F0E17] whitespace-nowrap">
                          {invoiceTotal(inv)}
                        </td>
                        <td className="py-2.5 px-3">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-semibold capitalize ${invoiceStatusClass(inv.status)}`}
                          >
                            {inv.status || 'issued'}
                          </span>
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
                              className="min-w-[32px] min-h-[32px] flex items-center justify-center rounded-lg text-[#6344E7] hover:bg-[#6344E7]/10 disabled:opacity-50"
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
                              className="min-w-[32px] min-h-[32px] flex items-center justify-center rounded-lg text-[#524E5E] hover:bg-[#F0EEF6]"
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
                        <tr className="bg-[#FAF9FD]">
                          <td colSpan={7} className="px-4 py-3">
                            {invoiceDetailBusy ? (
                              <span className="flex items-center gap-2 text-[11px] text-[#524E5E]">
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                Loading invoice details…
                              </span>
                            ) : invoiceDetailError ? (
                              <span className="flex items-center gap-2 text-[11px] text-red-700">
                                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                                {invoiceDetailError}
                              </span>
                            ) : invoiceDetail ? (
                              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-[11px]">
                                <div className="space-y-1.5">
                                  <div>
                                    <div className="text-[10px] font-semibold uppercase tracking-wider text-[#8C879A]">
                                      Place of supply
                                    </div>
                                    <div className="text-[#0F0E17]">
                                      {invoiceDetail.placeOfSupply || '—'}
                                      {invoiceDetail.placeOfSupplyCode
                                        ? ` (${invoiceDetail.placeOfSupplyCode})`
                                        : ''}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-[10px] font-semibold uppercase tracking-wider text-[#8C879A]">
                                      Payment reference
                                    </div>
                                    <div className="font-mono text-[#0F0E17] break-all">
                                      {invoiceDetail.paymentId || '—'}
                                    </div>
                                  </div>
                                </div>
                                <div className="space-y-1.5">
                                  <div>
                                    <div className="text-[10px] font-semibold uppercase tracking-wider text-[#8C879A]">
                                      Payment method
                                    </div>
                                    <div className="text-[#0F0E17]">
                                      {paymentMethodLabel(invoiceDetail.paymentMethod)}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-[10px] font-semibold uppercase tracking-wider text-[#8C879A]">
                                      Paid on
                                    </div>
                                    <div className="text-[#0F0E17]">
                                      {formatDate(invoiceDetail.paidAt || invoiceDetail.createdAt, {
                                        withTime: true,
                                      })}
                                    </div>
                                  </div>
                                </div>
                                <div className="space-y-1.5">
                                  <div>
                                    <div className="text-[10px] font-semibold uppercase tracking-wider text-[#8C879A]">
                                      Billed to
                                    </div>
                                    <div className="text-[#0F0E17]">
                                      {invoiceDetail.buyer?.legalName || 'Account holder'}
                                    </div>
                                    <div className="font-mono text-[#524E5E]">
                                      {invoiceDetail.customerGstin || invoiceDetail.buyer?.gstin
                                        ? `GSTIN ${invoiceDetail.customerGstin || invoiceDetail.buyer.gstin}`
                                        : 'No GSTIN on this invoice'}
                                    </div>
                                  </div>
                                  {invoiceDetail.creditNotes?.length ? (
                                    <div>
                                      <div className="text-[10px] font-semibold uppercase tracking-wider text-[#8C879A]">
                                        Credit notes
                                      </div>
                                      {invoiceDetail.creditNotes.map((note) => (
                                        <div key={note.creditNoteId} className="text-[#0F0E17]">
                                          {note.creditNoteNumber} · {money(note.amountInr, 'INR')}{' '}
                                          <span className="text-[#8C879A]">
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
      <SolidCard padding="p-0" className="overflow-hidden">
        <div className="p-4 border-b border-[#E4E2EB] flex items-center justify-between gap-3">
          <div>
            <h3 className="text-xs font-bold text-[#0F0E17]">Billing activity</h3>
            <p className="text-[11px] text-[#524E5E] mt-0.5">
              Top-ups, call usage and number rentals as they were charged.
            </p>
          </div>
          <button
            type="button"
            onClick={exportTransactionsCsv}
            disabled={!transactions.length}
            data-testid="billing-export-csv"
            className="flex items-center gap-1.5 text-xs text-[#6344E7] font-semibold hover:underline disabled:opacity-40 disabled:hover:no-underline"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export CSV</span>
          </button>
        </div>

        {billingLoading && transactions.length === 0 ? (
          <TransactionRowsSkeleton rows={6} />
        ) : transactions.length === 0 ? (
          <p className="px-4 py-6 text-center text-xs text-[#8C879A]">
            No charges yet. Add funds to place calls or buy a number.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[10px] text-[#524E5E] uppercase tracking-wider font-semibold">
                  <th className="py-2.5 px-4">When</th>
                  <th className="py-2.5 px-3">Activity</th>
                  <th className="py-2.5 px-3">Description</th>
                  <th className="py-2.5 px-4 text-right">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E4E2EB]">
                {transactions.map((row) => {
                  const amt = formatRowAmount(row, serverWallet);
                  const isCredit = amt.isCredit;
                  const displayAmount = amt.primary;
                  const activityLabel = describeTransactionKind(row);
                  const isWebTest = row.kind === 'usage_web_test' || row.kind === 'usage_web';

                  return (
                    <tr key={row.id} className="hover:bg-[#FAF9FD]/80 transition-colors">
                      <td className="py-2.5 px-4 text-[#524E5E] whitespace-nowrap">
                        {row.createdAt ? new Date(row.createdAt).toLocaleString() : '—'}
                      </td>
                      <td className="py-2.5 px-3 whitespace-nowrap">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold ${
                            isCredit
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : row.isCampaign
                              ? 'bg-purple-50 text-purple-700 border border-purple-200'
                              : isWebTest
                              ? 'bg-blue-50 text-blue-700 border border-blue-200'
                              : 'bg-slate-50 text-slate-700 border border-slate-200'
                          }`}
                        >
                          {activityLabel}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-[#0F0E17]">
                        <div className="font-semibold text-xs text-[#0F0E17] flex items-center gap-1.5 flex-wrap">
                          <span>{row.description || activityLabel}</span>
                          {row.tier && (
                            <span
                              data-testid={`tx-tier-badge-${row.tier}`}
                              className="text-[10px] text-[#6344E7] bg-[#6344E7]/10 border border-[#6344E7]/25 px-1.5 py-0.5 rounded font-semibold"
                            >
                              {row.tierLabel || row.tier}
                            </span>
                          )}
                          {row.durationSec != null && row.durationSec > 0 && !row.description?.includes(`${row.durationSec}s`) && (
                            <span className="text-[10px] text-[#524E5E] bg-[#FAF9FD] border border-[#E4E2EB] px-1.5 py-0.5 rounded font-mono">
                              {row.durationSec}s
                            </span>
                          )}
                        </div>
                        {row.referenceId && (
                          <div className="text-[10px] text-[#8C879A] truncate max-w-[260px]">
                            {row.referenceId}
                          </div>
                        )}
                      </td>
                      <td
                        className={`py-2.5 px-4 text-right font-bold whitespace-nowrap ${
                          isCredit ? 'text-[#15803D]' : 'text-[#0F0E17]'
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
