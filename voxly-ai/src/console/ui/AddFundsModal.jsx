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

function moneyUsd(n) {
  return `$${(Number(n) || 0).toFixed(2)}`;
}

/**
 * Wallet top-up: USD UI → INR Razorpay order. UPI hidden for international card users.
 */
export function AddFundsModal({ isOpen, onClose, reason = null }) {
  const { user } = useAuth();
  const { wallet, refreshWallet } = useWorkspace();
  const [amountUsd, setAmountUsd] = useState(10);
  const [catalog, setCatalog] = useState(null);
  const [razorpay, setRazorpay] = useState({ enabled: false, keyId: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(null);

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setDone(null);
    let cancelled = false;
    Promise.all([
      api.billing.getCatalog().catch(() => null),
      api.billing.razorpayConfig().catch((e) => ({
        enabled: false,
        keyId: '',
        loadError: e?.message || 'Could not reach billing config',
      })),
    ]).then(([cat, rz]) => {
      if (cancelled) return;
      setCatalog(cat);
      setRazorpay(rz || { enabled: false, keyId: '' });
      if (rz?.loadError) {
        setError(
          `${rz.loadError}. If you just set RAZORPAY_API_KEY / SECRET, restart the API and hard-refresh.`
        );
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
  const amountInr = Math.max(100, Math.round(amountUsd * fx));

  const pay = useCallback(async () => {
    if (!canPay || busy) return;
    setBusy(true);
    setError(null);
    try {
      if (!razorpay.enabled) {
        throw new Error('Razorpay is not enabled. Check RAZORPAY_API_KEY / RAZORPAY_API_SECRET on the API.');
      }
      const order = await api.billing.createRazorpayOrder(amountInr);
      await openRazorpayWalletCheckout({
        order,
        keyId: razorpay.keyId,
        user: { email: user?.email, name: user?.name },
        hideUpi: true,
        onSuccess: async (response) => {
          try {
            await api.billing.verifyRazorpayPayment({
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            });
            await refreshWallet();
            setDone(`${moneyUsd(amountUsd)} added to your wallet.`);
            showToast('Payment received', 'success');
          } catch (e) {
            setError(e.message || 'Could not verify the payment');
          }
        },
        onError: (e) => setError(e.message || 'Payment cancelled'),
      });
    } catch (e) {
      setError(e.message || 'Payment failed');
    } finally {
      setBusy(false);
    }
  }, [amountInr, amountUsd, busy, canPay, razorpay, refreshWallet, user]);

  const buyMinutes = useMemo(
    () => (rateUsd > 0 ? Math.floor(amountUsd / rateUsd) : 0),
    [amountUsd, rateUsd]
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Add credit to your wallet"
      subtitle="Pay in USD (cards via Razorpay). Unused balance never expires."
      maxWidth="max-w-lg"
    >
      <div data-testid="add-funds-modal" className="space-y-4">
        {reason && (
          <div className="flex items-start gap-2 p-3 rounded-xl bg-[#FFFBEB] border border-[#FDE68A]">
            <AlertCircle className="w-4 h-4 text-[#B45309] mt-0.5 shrink-0" />
            <p className="text-xs text-[#78350F]">{reason}</p>
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
                Razorpay is not enabled on this API. Set <code>RAZORPAY_API_KEY</code> and{' '}
                <code>RAZORPAY_API_SECRET</code> in the API <code>.env</code>, restart the API
                process, then hard-refresh this page. Keys must be on the same backend this console
                proxies to (local Vite → port 8000).
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
                  className="flex-1 bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-sm font-mono"
                />
              </div>
              <div className="flex flex-wrap gap-1.5">
                {USD_PRESETS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setAmountUsd(p)}
                    data-testid={`add-funds-preset-${p}`}
                    className={`px-2.5 py-1.5 rounded-xl text-xs font-mono font-bold border transition-all ${
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
                Minimum {moneyUsd(minUsd)}. ≈ {buyMinutes} min at {moneyUsd(rateUsd)}/min.
              </p>
            </div>

            {(tooSmall || tooLarge) && (
              <p className="text-[11px] text-[#B91C1C]">
                Enter between {moneyUsd(minUsd)} and {moneyUsd(maxUsd)}.
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
              className="w-full justify-center"
            >
              {busy ? 'Opening checkout…' : `Pay ${moneyUsd(amountUsd)}`}
            </TactileButton>

            <p className="text-[10px] text-center text-[#8C879A] flex items-center justify-center gap-1">
              {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
              Cards and netbanking via Razorpay. We never see your card details.
            </p>
          </>
        )}
      </div>
    </Modal>
  );
}

export default AddFundsModal;
