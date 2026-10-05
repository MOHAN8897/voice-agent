import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, CreditCard, Loader2, Wallet } from 'lucide-react';
import { Modal } from './Modal';
import { TactileButton } from './TactileButton';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useWorkspace } from '../context/WorkspaceContext';
import { showToast } from './ToastHost';
import { openRazorpayWalletCheckout } from '../../utils/razorpayCheckout';

/** USD presets for English-speaking SaaS; Razorpay still settles in INR under the hood. */
const USD_PRESETS = [5, 10, 25, 50, 100];

/** Internal call-site keys → customer copy. Raw env/admin strings never show. */
const REASON_COPY = {
  topbar: null,
  billing: null,
  'buy-number': 'Add credit to buy a phone number.',
};

function moneyUsd(n) {
  return `$${(Number(n) || 0).toFixed(2)}`;
}

function friendlyReason(reason) {
  if (reason == null || reason === '') return null;
  if (typeof reason !== 'string') return null;
  if (Object.prototype.hasOwnProperty.call(REASON_COPY, reason)) return REASON_COPY[reason];
  if (/RAZORPAY|API_KEY|API_SECRET|\.env|Didit|STRIPE|secret/i.test(reason)) {
    return 'Add credit to continue.';
  }
  return reason;
}

function customerPaymentError(raw) {
  const msg = String(raw || '');
  if (/RAZORPAY|API_KEY|API_SECRET|\.env|not configured|not enabled/i.test(msg)) {
    return 'Card payments are temporarily unavailable. Please try again later or contact support.';
  }
  return msg || 'Payment failed';
}

/**
 * Wallet top-up via Razorpay.
 *
 * Charged in the currency the account is configured for (USD once international
 * payments are enabled, INR otherwise). UPI settles domestically only, so it is
 * hidden for any non-INR order — otherwise checkout offers a rail that cannot
 * take the payment.
 */
export function AddFundsModal({ isOpen, onClose, reason = null }) {
  const { user } = useAuth();
  const { wallet, refreshWallet } = useWorkspace();
  const [amountUsd, setAmountUsd] = useState(10);
  const [catalog, setCatalog] = useState(null);
  const [razorpay, setRazorpay] = useState({ enabled: false, keyId: '', international: false, currency: 'USD' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(null);

  const banner = friendlyReason(reason);

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setDone(null);
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
      setRazorpay({ international: false, currency: 'USD', ...(rz || {}) });
      if (rz?.loadError || rz?.enabled === false) {
        /* shown via the soft unavailable banner below — no env var names */
      }
      if (cat?.topupMinUsd) setAmountUsd(Math.max(Number(cat.topupMinUsd) || 5, 10));
    });
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  const minUsd = catalog?.topupMinUsd ?? 3;
  const maxUsd = catalog?.topupMaxUsd ?? 500;
  const fx = Number(catalog?.rates?.fxRateInr) || 95.64;
  const rateUsd = Number(catalog?.rates?.pstnUsdPerMin) || 0.12;
  const balanceUsd =
    Number(wallet?.balanceUsd) ||
    (Number(wallet?.balanceInr) || 0) / fx ||
    0;
  const minutes = rateUsd > 0 ? Math.floor(balanceUsd / rateUsd) : Number(wallet?.remainingMinutes || 0);
  const tooSmall = amountUsd < minUsd;
  const tooLarge = amountUsd > maxUsd;
  const canPay = !tooSmall && !tooLarge && amountUsd > 0 && razorpay.enabled;
  const chargeCurrency = razorpay.currency || 'USD';
  const isInternational = chargeCurrency !== 'INR';
  const symbol = chargeCurrency === 'INR' ? '₹' : chargeCurrency === 'USD' ? '$' : `${chargeCurrency} `;
  const amountLabel = isInternational ? `${symbol}${amountUsd}` : `₹${Math.round(amountUsd * fx)}`;

  const pay = useCallback(async () => {
    if (!canPay || busy) return;
    setBusy(true);
    setError(null);
    try {
      if (!razorpay.enabled) {
        throw new Error('payments_unavailable');
      }
      const chargeAmount = isInternational ? amountUsd : Math.max(100, Math.round(amountUsd * fx));
      const order = await api.billing.createRazorpayOrder(chargeAmount, chargeCurrency);
      await openRazorpayWalletCheckout({
        order,
        keyId: razorpay.keyId,
        user: { email: user?.email, name: user?.name },
        hideUpi: isInternational,
        onSuccess: async (response) => {
          try {
            await api.billing.verifyRazorpayPayment({
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            });
            await refreshWallet();
            const charged = response.razorpay_payment?.currency
              ? `${response.razorpay_payment.currency} ${Number(response.razorpay_payment.amount || 0) / 100}`
              : amountLabel;
            setDone(`${charged} added to your wallet.`);
            showToast('Payment received', 'success');
          } catch (e) {
            setError(customerPaymentError(e.message));
          }
        },
        onError: (e) => setError(customerPaymentError(e.message || 'Payment cancelled')),
      });
    } catch (e) {
      setError(customerPaymentError(e.message));
    } finally {
      setBusy(false);
    }
  }, [amountLabel, amountUsd, busy, canPay, chargeCurrency, fx, isInternational, razorpay, refreshWallet, user]);

  const buyMinutes = useMemo(
    () => (rateUsd > 0 ? Math.floor(amountUsd / rateUsd) : 0),
    [amountUsd, rateUsd]
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Add credit to your wallet"
      subtitle={`Pay by card${isInternational ? ` in ${chargeCurrency}` : ''}. Unused balance never expires.`}
      maxWidth="max-w-lg"
    >
      <div data-testid="add-funds-modal" className="space-y-4">
        {banner && (
          <div className="flex items-start gap-2 p-3 rounded-xl bg-[#FFFBEB] border border-[#FDE68A]">
            <AlertCircle className="w-4 h-4 text-[#B45309] mt-0.5 shrink-0" />
            <p className="text-xs text-[#78350F]">{banner}</p>
          </div>
        )}

        {done ? (
          <div className="text-center py-6 space-y-3">
            <CheckCircle2 className="w-10 h-10 text-[#047857] mx-auto" />
            <p className="text-sm font-bold text-[#0F0E17]">{done}</p>
            <p className="text-xs text-[#524E5E]">Balance: {moneyUsd(wallet?.balanceUsd ?? balanceUsd)}</p>
            <TactileButton variant="brand" size="md" onClick={onClose}>
              Done
            </TactileButton>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
              <div className="flex items-center gap-2">
                <Wallet className="w-4 h-4 text-[#6344E7]" />
                <div>
                  <div className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A]">Balance</div>
                  <div className="text-sm font-bold text-[#0F0E17]">{moneyUsd(balanceUsd)}</div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A]">≈ call time</div>
                <div className="text-sm font-bold text-[#0F0E17]">{minutes} min</div>
              </div>
            </div>

            {!razorpay.enabled && (
              <p className="text-[11px] text-[#B45309]" data-testid="add-funds-razorpay-off">
                Card payments are temporarily unavailable. Please try again later or contact support.
              </p>
            )}

            <div>
              <label htmlFor="add-funds-amount" className="block text-xs font-bold text-[#0F0E17] mb-1.5">
                Amount (USD)
              </label>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-sm font-bold text-[#524E5E]">$</span>
                <input
                  id="add-funds-amount"
                  type="number"
                  min={minUsd}
                  max={maxUsd}
                  step="1"
                  value={amountUsd}
                  onChange={(e) => setAmountUsd(Number(e.target.value))}
                  data-testid="add-funds-amount"
                  className="flex-1 bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-base sm:text-sm min-h-[42px] sm:min-h-[38px] font-mono text-[#0F0E17]"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                {USD_PRESETS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setAmountUsd(p)}
                    data-testid={`add-funds-preset-${p}`}
                    className={`min-w-[44px] min-h-[38px] sm:min-h-[34px] px-3 py-1.5 rounded-xl text-xs font-mono font-bold border transition-all flex items-center justify-center ${
                      amountUsd === p
                        ? 'bg-[#0F0E17] text-white border-[#0F0E17]'
                        : 'bg-white text-[#524E5E] border-[#E4E2EB] hover:border-[#6344E7]'
                    }`}
                  >
                    ${p}
                  </button>
                ))}
              </div>
              <p className="text-[10px] text-[#8C879A] mt-1.5">
                Minimum {symbol}{minUsd}. ≈ {buyMinutes} min at {moneyUsd(rateUsd)}/min.
              </p>
            </div>

            {(tooSmall || tooLarge) && (
              <p className="text-[11px] text-[#B91C1C]">
                Enter between {symbol}{minUsd} and {symbol}{maxUsd}.
              </p>
            )}
            {error && (
              <div
                data-testid="add-funds-error"
                role="alert"
                className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900"
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
              {busy ? 'Opening checkout…' : `Pay ${amountLabel}`}
            </TactileButton>

            <p className="text-[10px] text-center text-[#8C879A] flex items-center justify-center gap-1">
              {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
              {isInternational
                ? `Secure card checkout. Charged in ${chargeCurrency}. We never see your card details.`
                : 'Secure card checkout. We never see your card details.'}
            </p>
          </>
        )}
      </div>
    </Modal>
  );
}

export default AddFundsModal;
