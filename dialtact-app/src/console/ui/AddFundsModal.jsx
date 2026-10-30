import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, CreditCard, Loader2, ShieldCheck, Wallet } from 'lucide-react';
import { Modal } from './Modal';
import { TactileButton } from './TactileButton';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useWorkspace } from '../context/WorkspaceContext';
import { showToast } from './ToastHost';
import { openRazorpayWalletCheckout } from '../../utils/razorpayCheckout';
import { walletAmounts } from '../../lib/money';

/** Presets in the currency the account is charged in. */
const PRESETS = {
  INR: [500, 1000, 2500, 5000, 10000],
  USD: [5, 10, 25, 50, 100],
};

/** Internal call-site keys → customer copy. Raw env/admin strings never show. */
const REASON_COPY = {
  topbar: null,
  billing: null,
  'buy-number': 'Add credit to buy a phone number.',
};

function currencySymbol(currency) {
  if (currency === 'INR') return '₹';
  if (currency === 'USD') return '$';
  return `${currency} `;
}

function money(amount, currency) {
  const value = Number(amount) || 0;
  if (currency === 'INR') {
    return `₹${value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (currency === 'USD') return `$${value.toFixed(2)}`;
  return `${currency} ${value.toFixed(2)}`;
}

function friendlyReason(reason) {
  if (reason == null || reason === '') return null;
  if (typeof reason !== 'string') return null;
  if (Object.prototype.hasOwnProperty.call(REASON_COPY, reason)) return REASON_COPY[reason];
  if (/RAZORPAY|API_KEY|API_SECRET|\.env|Didit|secret/i.test(reason)) {
    return 'Add credit to continue.';
  }
  return reason;
}

function customerPaymentError(raw) {
  const msg = String(raw || '');
  if (/payment_cancelled|payment cancelled/i.test(msg)) {
    return null;
  }
  if (/payments_unavailable|RAZORPAY|API_KEY|API_SECRET|\.env|not configured|not enabled/i.test(msg)) {
    return 'Card payments are temporarily unavailable. Please try again later or contact support.';
  }
  return msg || 'Payment failed';
}

function taxLabel(taxKind) {
  switch (taxKind) {
    case 'cgst_sgst':
      return 'CGST + SGST';
    case 'igst':
      return 'IGST';
    case 'export':
      return 'Zero-rated export';
    default:
      return 'GST';
  }
}

const CONFIRMING_MESSAGE =
  'Checkout completed. We are checking the payment before crediting your wallet. Use Check payment status; please do not pay again.';

/** Verify outcomes that mean "paid, still settling", not "failed". */
const PENDING_CODES = new Set([
  'payment_not_captured',
  'payment_capture_unavailable',
  'payment_verification_unavailable',
]);

const PENDING_MESSAGE =
  'Your bank has approved the payment and it is still being completed. Your wallet will be credited automatically, usually within a few minutes. You can close this window; please do not pay again.';

/**
 * Wallet top-up via Razorpay.
 *
 * The amount is entered in the currency the account is charged in. The server
 * quotes GST before checkout so the tenant sees the taxable value, the tax split
 * and exactly what will be credited, never just a single "pay" number.
 */
export function AddFundsModal({ isOpen, onClose, reason = null, initialAmount = null }) {
  const { user } = useAuth();
  const { wallet, refreshWallet } = useWorkspace();
  const [amount, setAmount] = useState(() => Number(initialAmount) || 10);
  const [catalog, setCatalog] = useState(null);
  const [razorpay, setRazorpay] = useState({ enabled: false, keyId: '', international: false, currency: 'INR' });
  const [quote, setQuote] = useState(null);
  const [quoteBusy, setQuoteBusy] = useState(false);
  const [quoteError, setQuoteError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [pendingNote, setPendingNote] = useState(null);
  const [done, setDone] = useState(null);
  const quoteSeq = useRef(0);
  const pendingPayment = useRef(null);
  const payLock = useRef(false);
  const confirmLock = useRef(false);
  const [quoteRefresh, setQuoteRefresh] = useState(0);

  const banner = friendlyReason(reason);
  const chargeCurrency = razorpay.currency || 'USD';
  const symbol = currencySymbol(chargeCurrency);
  const presets = PRESETS[chargeCurrency] || PRESETS.USD;
  const isInternational = chargeCurrency !== 'INR';

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setConfirming(Boolean(pendingPayment.current));
    setDone(null);
    setQuote(pendingPayment.current?.quote || null);
    setQuoteError(null);
    let cancelled = false;
    Promise.all([
      api.billing.getCatalog().catch(() => null),
      api.billing.razorpayConfig().catch(() => ({
        enabled: false,
        keyId: '',
        loadError: true,
      })),
    ]).then(([cat, rz]) => {
      if (cancelled) return;
      setCatalog(cat);
      const config = { international: false, currency: 'INR', ...(rz || {}) };
      if (pendingPayment.current?.quote?.currency) config.currency = pendingPayment.current.quote.currency;
      setRazorpay(config);
      const currency = config.currency || 'INR';
      const minimum = currency === 'INR' ? Number(cat?.topupMinInr) || 100 : Number(cat?.topupMinUsd) || 3;
      const defaultAmount = Number(initialAmount) > 0 ? Number(initialAmount) : Math.max(minimum, currency === 'INR' ? 500 : 10);
      setAmount(pendingPayment.current?.quote?.amount ?? defaultAmount);
    });
    return () => {
      cancelled = true;
    };
  }, [isOpen, initialAmount]);

  const minAmount = useMemo(() => {
    if (chargeCurrency === 'INR') return Number(catalog?.topupMinInr) || 100;
    if (chargeCurrency === 'USD') return Number(catalog?.topupMinUsd) || 3;
    return 1;
  }, [catalog, chargeCurrency]);
  const maxAmount = useMemo(() => {
    if (chargeCurrency === 'INR') return Number(catalog?.topupMaxInr) || 500000;
    if (chargeCurrency === 'USD') return Number(catalog?.topupMaxUsd) || 500;
    return 5000;
  }, [catalog, chargeCurrency]);

  const fx = Number(catalog?.rates?.fxRateInr) || 95.64;
  const rateUsd = Number(catalog?.rates?.pstnUsdPerMin) || 0.12;
  const rateInr = Number(catalog?.rates?.pstnInrPerMin) || rateUsd * fx;
  const balanceUsd =
    Number(wallet?.balanceUsd) ||
    (Number(wallet?.balanceInr) || 0) / fx ||
    0;
  const minutes = rateInr > 0 && quote?.creditInr
    ? Math.floor(Number(quote.creditInr) / rateInr)
    : rateUsd > 0
      ? Math.floor(balanceUsd / rateUsd)
      : Number(wallet?.remainingMinutes || 0);

  // Server-side quote: the only source of truth for GST and charge totals.
  useEffect(() => {
    if (!isOpen || !razorpay.enabled) { quoteSeq.current += 1; setQuote(null); setQuoteBusy(false); return; }
    if (pendingPayment.current) { setQuote(pendingPayment.current.quote); setQuoteBusy(false); return; }
    const value = Number(amount);
    if (!Number.isFinite(value) || value <= 0) {
      setQuote(null);
      setQuoteError(null);
      return;
    }
    const seq = ++quoteSeq.current;
    setQuote(null);
    setQuoteBusy(true);
    setQuoteError(null);
    const timer = window.setTimeout(() => {
      api.billing.quoteTopup(value, chargeCurrency)
        .then((result) => {
          if (seq === quoteSeq.current) setQuote({ ...result, quotedAmount: value, quotedCurrency: chargeCurrency });
        })
        .catch((e) => {
          if (seq !== quoteSeq.current) return;
          setQuote(null);
          const message = customerPaymentError(e.message);
          setQuoteError(message || 'Could not price this top-up.');
        })
        .finally(() => {
          if (seq === quoteSeq.current) setQuoteBusy(false);
        });
    }, 300);
    return () => {
      window.clearTimeout(timer);
      if (seq === quoteSeq.current) { quoteSeq.current += 1; setQuoteBusy(false); }
    };
  }, [amount, chargeCurrency, isOpen, razorpay.enabled, quoteRefresh, confirming]);

  const inRange = Number(amount) >= minAmount && Number(amount) <= maxAmount;
  const canPay = inRange && Number(amount) > 0 && razorpay.enabled && !!quote && quote.quotedAmount === Number(amount) && quote.quotedCurrency === chargeCurrency && !quoteBusy && !busy && !confirming && !done;
  const totalLabel = quote ? money(quote.total, chargeCurrency) : money(amount, chargeCurrency);

  const confirmPayment = useCallback(async (response, paymentQuote) => {
    if (confirmLock.current) return;
    confirmLock.current = true;
    pendingPayment.current = { response, quote: paymentQuote };
    setConfirming(true); setBusy(true); setError(null); setPendingNote(null);
    try {
      const result = await api.billing.verifyRazorpayPayment(response);
      if (result?.ok === false) throw new Error('Payment verification is pending.');
      await refreshWallet().catch(() => null);
      pendingPayment.current = null;
      setConfirming(false);
      setDone({ credited: result?.creditedInr != null ? Number(result.creditedInr) : Number(paymentQuote.creditInr),
        invoiceNumber: result?.invoiceNumber || null });
      showToast('Payment received', 'success');
    } catch (err) {
      if (PENDING_CODES.has(err?.code)) {
        // Paid but not settled yet (authorised, or Razorpay unreachable). The
        // server captures and credits it on its own; this is not a failure.
        setPendingNote(PENDING_MESSAGE);
        refreshWallet().catch(() => null);
      } else {
        setError(`${customerPaymentError(err.message) || 'Payment confirmation is pending.'} Check payment status before making another payment.`);
      }
    } finally { confirmLock.current = false; setBusy(false); }
  }, [refreshWallet]);

  const pay = useCallback(async () => {
    if (!canPay || payLock.current || pendingPayment.current) return;
    payLock.current = true; setBusy(true); setError(null);
    try {
      const order = await api.billing.createRazorpayOrder(Number(quote.amount), chargeCurrency,
        quote.totalMinor ?? Math.round(Number(quote.total) * 100));
      await openRazorpayWalletCheckout({ order, keyId: razorpay.keyId,
        user: { email: user?.email, name: user?.name }, hideUpi: isInternational,
        onSuccess: (response) => confirmPayment(response, { ...quote, creditInr: order.creditedInr ?? quote.creditInr }),
        onError: (err) => {
          const message = customerPaymentError(err.message);
          if (message) setError(`${message} No wallet credit was added for this failed attempt. Retry in checkout or close it.`);
        },
      });
    } catch (err) {
      const message = customerPaymentError(err.message);
      if (/quote.*changed|tax or charge total changed/i.test(err.message || '')) {
        setQuote(null); setQuoteRefresh((current) => current + 1);
      }
      if (message) setError(message);
    } finally { payLock.current = false; setBusy(false); }
  }, [canPay, chargeCurrency, confirmPayment, isInternational, quote, razorpay, user]);

  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        if (busy) return;
        if (pendingPayment.current) {
          // Closing mid-confirmation is safe: the server finishes the payment.
          showToast('Payment is being confirmed. Your wallet will update automatically.', 'info');
        }
        onClose?.();
      }}
      title="Add credit to your wallet"
      subtitle={`Secure checkout in ${chargeCurrency}. Tax and wallet credit are shown separately.`}
      maxWidth="max-w-lg"
    >
      <div data-testid="add-funds-modal" className="space-y-4">
        {banner && !done && (
          <div className="flex items-start gap-2 p-3 rounded-control bg-warning-soft border border-warning-line">
            <AlertCircle className="w-4 h-4 text-warning-fg mt-0.5 shrink-0" />
            <p className="text-ui text-warning-fg">{banner}</p>
          </div>
        )}

        {done ? (
          <div className="text-center py-6 space-y-3">
            <CheckCircle2 className="w-10 h-10 text-success-fg mx-auto" />
            <p className="text-title text-ink">
              {money(done.credited, 'INR')} added to your wallet.
            </p>
            <p className="text-ui text-fg-body">
              Balance: <span className="font-mono tabular-nums">{walletAmounts(wallet).primary}</span>
            </p>
            {done.invoiceNumber ? (
              <p className="text-meta text-fg-muted">
                GST invoice <span className="font-mono font-semibold">{done.invoiceNumber}</span> is
                available under Billing → Invoices and tax receipts.
              </p>
            ) : null}
            <TactileButton variant="brand" size="md" onClick={onClose}>
              Done
            </TactileButton>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between p-3 rounded-control bg-canvas border border-line">
              <div className="flex items-center gap-2">
                <Wallet className="w-4 h-4 text-fg-subtle" aria-hidden="true" />
                <div>
                  <div className="text-meta text-fg-muted">Balance</div>
                  <div className="text-copy font-semibold font-mono tabular-nums text-ink">{walletAmounts(wallet).primary}</div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-meta text-fg-muted">About</div>
                <div className="text-copy font-semibold font-mono tabular-nums text-ink">{minutes} min</div>
              </div>
            </div>

            {!razorpay.enabled && (
              <p className="text-ui text-warning-fg" data-testid="add-funds-razorpay-off">
                Card payments are temporarily unavailable. Please try again later or contact support.
              </p>
            )}

            <div>
              <label htmlFor="add-funds-amount" className="block text-ui font-medium text-ink mb-1.5">
                Amount ({chargeCurrency}) {quote?.priceIncludesTax ? 'including GST' : 'before GST'}
              </label>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-copy font-semibold text-fg-body">{symbol}</span>
                <input
                  id="add-funds-amount"
                  type="number"
                  disabled={busy || confirming}
                  min={minAmount}
                  max={maxAmount}
                  step={chargeCurrency === 'INR' ? '100' : '1'}
                  value={amount}
                  onChange={(e) => {
                    setAmount(Number(e.target.value));
                    setError(null);
                    setQuote(null);
                  }}
                  data-testid="add-funds-amount"
                  className="flex-1 min-w-0 bg-surface border border-line rounded-control px-3 py-2 text-base sm:text-copy min-h-[44px] sm:min-h-[40px] font-mono tabular-nums text-ink focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                {presets.map((p) => (
                  <button
                    key={p}
                    type="button"
                    disabled={busy || confirming}
                    onClick={() => {
                      setAmount(p);
                      setError(null);
                      setQuote(null);
                    }}
                    data-testid={`add-funds-preset-${p}`}
                    aria-pressed={Number(amount) === p}
                    className={`min-w-[44px] min-h-[44px] sm:min-h-[36px] px-3 py-1.5 rounded-control text-ui font-mono tabular-nums font-semibold border transition-colors flex items-center justify-center ${
                      Number(amount) === p
                        ? 'bg-ink text-white border-ink'
                        : 'bg-surface text-fg-body border-line hover:border-line-strong hover:bg-canvas'
                    }`}
                  >
                    {symbol}
                    {p.toLocaleString?.('en-IN') ?? p}
                  </button>
                ))}
              </div>
              <p className="text-meta text-fg-muted mt-1.5">
                Minimum {money(minAmount, chargeCurrency)} · maximum {money(maxAmount, chargeCurrency)}
                {quote?.creditInr != null ? ` · ${minutes} min at ${money(rateInr, 'INR')}/min` : ''}.
              </p>
            </div>

            {(Number(amount) < minAmount || Number(amount) > maxAmount) && (
              <p className="text-meta text-danger-fg">
                Enter between {money(minAmount, chargeCurrency)} and {money(maxAmount, chargeCurrency)}.
              </p>
            )}

            {/* Server-quoted breakdown: what is taxed, what is credited. */}
            {razorpay.enabled && Number(amount) >= minAmount ? (
              <div
                className="rounded-control border border-line bg-surface overflow-hidden"
                data-testid="add-funds-breakdown"
                aria-live="polite"
              >
                <div className="flex items-center justify-between px-3 py-2 border-b border-line bg-canvas">
                  <span className="text-meta font-medium text-fg-body">Charge breakdown</span>
                  {quoteBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin text-fg-muted" /> : null}
                </div>
                <dl className="divide-y divide-line text-ui">
                  <div className="flex items-center justify-between px-3 py-2">
                    <dt className="text-fg-body">Wallet credit (taxable value)</dt>
                    <dd className="font-mono tabular-nums font-semibold text-ink">
                      {quote ? money(quote.creditInr, 'INR') : '—'}
                    </dd>
                  </div>
                  <div className="flex items-center justify-between px-3 py-2">
                    <dt className="text-fg-body">
                      {quote?.taxKind === 'export'
                        ? 'GST (export of services, zero-rated)'
                        : `${taxLabel(quote?.taxKind)} ${quote?.ratePercent ? `@ ${quote.ratePercent}%` : ''}`}
                    </dt>
                    <dd className="font-mono tabular-nums font-semibold text-ink">
                      {quote ? money(quote.tax, chargeCurrency) : '—'}
                    </dd>
                  </div>
                  {quote?.taxKind === 'cgst_sgst' ? (
                    <div className="flex items-center justify-between px-3 py-2">
                      <dt className="text-fg-muted pl-3">CGST / SGST</dt>
                      <dd className="font-mono tabular-nums text-fg-body">
                        {money(quote.cgst, chargeCurrency)} + {money(quote.sgst, chargeCurrency)}
                      </dd>
                    </div>
                  ) : null}
                  <div className="flex items-center justify-between px-3 py-2 bg-canvas">
                    <dt className="font-semibold text-ink">Total payable</dt>
                    <dd className="font-mono tabular-nums text-copy font-bold text-ink" data-testid="add-funds-total">
                      {quote ? money(quote.total, chargeCurrency) : '—'}
                    </dd>
                  </div>
                </dl>
                <p className="px-3 py-2 text-meta text-fg-muted border-t border-line">
                  GST is a statutory charge and is not wallet credit. Your invoice shows the same
                  split and is downloadable under Billing.
                </p>
              </div>
            ) : null}

            {quote?.checkoutTerms && <p className="whitespace-pre-wrap text-ui text-fg-body" data-testid="checkout-tax-terms">{quote.checkoutTerms}</p>}
            {quoteError ? (
              <p className="text-meta text-warning-fg" role="status">
                {quoteError}
              </p>
            ) : null}

            {confirming ? (
              <div
                data-testid="add-funds-confirming"
                role="status"
                className="rounded-control border border-warning-line bg-warning-soft px-3 py-2 text-ui text-warning-fg"
              >
                {pendingNote || CONFIRMING_MESSAGE}
                <TactileButton variant="secondary" size="sm" className="mt-3" disabled={busy || !pendingPayment.current}
                  onClick={() => { const pending = pendingPayment.current; if (pending) confirmPayment(pending.response, pending.quote); }}>Check payment status</TactileButton>
              </div>
            ) : null}

            {error && (
              <div
                data-testid="add-funds-error"
                role="alert"
                className="rounded-control border border-danger-line bg-danger-soft px-3 py-2 text-ui text-danger-fg"
              >
                {error}
              </div>
            )}

            <TactileButton
              variant="brand"
              size="md"
              icon={CreditCard}
              loading={busy}
              disabled={!canPay}
              data-testid="add-funds-submit"
              onClick={pay}
              className="w-full justify-center min-h-[44px]"
            >
              {busy ? 'Opening checkout…' : `Pay ${totalLabel}`}
            </TactileButton>

            <div className="flex items-start justify-center gap-1.5 text-meta text-fg-muted text-center">
              <ShieldCheck className="w-3.5 h-3.5 shrink-0 mt-0.5" aria-hidden="true" />
              <span>
                {isInternational
                  ? `Secure card checkout in ${chargeCurrency}. We never see your card details.`
                  : 'Secure card checkout with UPI, cards and netbanking. We never see your payment details.'}
                {' '}A failed payment adds no credit and can be retried. If you close this window after paying,
                your wallet is still credited automatically within a few minutes.
              </span>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}

export default AddFundsModal;
