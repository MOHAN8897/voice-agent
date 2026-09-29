import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, CreditCard, Loader2, Wallet } from 'lucide-react';
import { Modal } from './Modal';
import { TactileButton } from './TactileButton';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useWorkspace } from '../context/WorkspaceContext';
import { showToast } from './ToastHost';
import { openRazorpayWalletCheckout } from '../../utils/razorpayCheckout';

/** Smallest payments first — a new workspace must be able to fund itself cheaply. */
const USD_PRESETS = [3, 5, 10, 25, 50];
const INR_PRESETS = [300, 500, 1000, 2500, 5000];

function money(n, currency) {
  const value = Number(n) || 0;
  return currency === 'INR' ? `₹${value.toFixed(0)}` : `$${value.toFixed(2)}`;
}

/**
 * The payment wall: add wallet credit from anywhere in the console.
 *
 * The $3 minimum and the number price come from `GET /api/billing/catalog`, so the
 * console can never quote a price the server would reject.
 */
export function AddFundsModal({ isOpen, onClose, reason = null }) {
  const { user } = useAuth();
  const { wallet, refreshWallet } = useWorkspace();
  const [currency, setCurrency] = useState('USD');
  const [amount, setAmount] = useState(3);
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
      api.billing.razorpayConfig().catch(() => ({ enabled: false, keyId: '' })),
    ]).then(([cat, rz]) => {
      if (cancelled) return;
      setCatalog(cat);
      setRazorpay(rz || { enabled: false, keyId: '' });
      if (cat?.topupMinUsd) setAmount(cat.topupMinUsd);
    });
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  const minUsd = catalog?.topupMinUsd ?? 3;
  const maxUsd = catalog?.topupMaxUsd ?? 500;
  const minInr = catalog?.topupMinInr ?? 100;
  const maxInr = catalog?.topupMaxInr ?? 500000;
  const presets = currency === 'INR' ? INR_PRESETS : USD_PRESETS;

  const balance = useMemo(() => {
    const inr = Number(wallet?.balanceInr) || 0;
    const usd = Number(wallet?.balanceUsd) || 0;
    if (currency === 'INR') return { value: inr, label: money(inr, 'INR') };
    return { value: usd, label: money(usd, 'USD') };
  }, [wallet, currency]);

  const minutes = useMemo(() => {
    const rateInr = Number(catalog?.rates?.pstnInrPerMin) || 9;
    const rateUsd = Number(catalog?.rates?.pstnUsdPerMin) || 0.09;
    if (currency === 'INR') return Math.floor(Number(wallet?.balanceInr || 0) / rateInr);
    return Math.floor(Number(wallet?.balanceUsd || 0) / rateUsd);
  }, [wallet, currency, catalog]);

  const tooSmall = currency === 'INR' ? amount < minInr : amount < minUsd;
  const tooLarge = currency === 'INR' ? amount > maxInr : amount > maxUsd;
  const canPay = !tooSmall && !tooLarge && amount > 0;

  const pay = useCallback(async () => {
    if (!canPay) return;
    setBusy(true);
    setError(null);
    try {
      if (currency === 'INR') {
        if (!razorpay.enabled) {
          throw new Error('Razorpay is not enabled on this deployment. Try the USD option.');
        }
        const order = await api.billing.createRazorpayOrder(Number(amount));
        await openRazorpayWalletCheckout({
          order,
          keyId: razorpay.keyId,
          user: { email: user?.email, name: user?.name },
          onSuccess: async (response) => {
            try {
              await api.billing.verifyRazorpayPayment({
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature,
              });
              await refreshWallet();
              setDone(`${money(amount, 'INR')} added to your wallet.`);
              showToast('Payment received', 'success');
            } catch (e) {
              setError(e.message || 'Could not verify the payment');
            }
          },
          onError: (e) => setError(e.message || 'Payment cancelled'),
        });
        return;
      }

      // USD goes through Stripe Checkout; the wallet is credited by the webhook.
      const result = await api.billing.topUp(Number(amount));
      if (result?.checkoutUrl) {
        window.location.href = result.checkoutUrl;
        return;
      }
      await refreshWallet();
      setDone(`${money(amount, 'USD')} added to your wallet.`);
    } catch (e) {
      setError(e.message || 'Payment failed');
    } finally {
      setBusy(false);
    }
  }, [amount, canPay, currency, razorpay, refreshWallet, user]);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Add credit to your wallet"
      subtitle="Pay for calls as you make them, or buy a phone number. Unused credit never expires."
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
            <p className="text-xs text-[#524E5E]">
              Balance: {money(wallet?.balanceUsd, 'USD')}
              {wallet?.balanceInr != null ? ` · ${money(wallet?.balanceInr, 'INR')}` : ''}
            </p>
            <TactileButton variant="brand" size="md" onClick={onClose}>
              Done
            </TactileButton>
          </div>
        ) : (
          <>
            {/* Current balance, so the user knows where they stand. */}
            <div className="flex items-center justify-between p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
              <div className="flex items-center gap-2">
                <Wallet className="w-4 h-4 text-[#6344E7]" />
                <div>
                  <div className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A]">
                    Balance
                  </div>
                  <div className="text-sm font-bold text-[#0F0E17]">{balance.label}</div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A]">
                  ≈ call time
                </div>
                <div className="text-sm font-bold text-[#0F0E17]">{minutes} min</div>
              </div>
            </div>

            {/* Currency */}
            <div className="inline-flex p-1 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB] w-full">
              {[
                { id: 'USD', label: 'USD · card' },
                { id: 'INR', label: 'INR · UPI / card' },
              ].map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => {
                    setCurrency(c.id);
                    setError(null);
                  }}
                  data-testid={`add-funds-currency-${c.id}`}
                  className={`flex-1 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    currency === c.id
                      ? 'bg-white text-[#0F0E17] shadow-xs'
                      : 'text-[#524E5E] hover:text-[#0F0E17]'
                  }`}
                >
                  {c.label}
                </button>
              ))}
            </div>

            {currency === 'INR' && !razorpay.enabled && (
              <p className="text-[11px] text-[#B45309]">
                Razorpay is not enabled on this deployment, so INR payments are unavailable.
              </p>
            )}

            {/* Amount */}
            <div>
              <label htmlFor="add-funds-amount" className="block text-xs font-bold text-[#0F0E17] mb-1.5">
                How much?
              </label>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-sm font-bold text-[#524E5E]">
                  {currency === 'INR' ? '₹' : '$'}
                </span>
                <input
                  id="add-funds-amount"
                  type="number"
                  min={currency === 'INR' ? minInr : minUsd}
                  max={currency === 'INR' ? maxInr : maxUsd}
                  step={currency === 'INR' ? '100' : '1'}
                  value={amount}
                  onChange={(e) => setAmount(Number(e.target.value))}
                  data-testid="add-funds-amount"
                  className="flex-1 bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-sm font-mono"
                />
              </div>
              <div className="flex flex-wrap gap-1.5">
                {presets.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setAmount(p)}
                    data-testid={`add-funds-preset-${p}`}
                    className={`px-2.5 py-1.5 rounded-xl text-xs font-mono font-bold border transition-all ${
                      amount === p
                        ? 'bg-[#0F0E17] text-white border-[#0F0E17]'
                        : 'bg-white text-[#524E5E] border-[#E4E2EB] hover:border-[#6344E7]'
                    }`}
                  >
                    {currency === 'INR' ? `₹${p}` : `$${p}`}
                  </button>
                ))}
              </div>
              <p className="text-[10px] text-[#8C879A] mt-1.5">
                Smallest payment {currency === 'INR' ? money(minInr, 'INR') : money(minUsd, 'USD')}.
              </p>
            </div>

            {/* What this buys, at the live rates. */}
            <div className="p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-[11px] text-[#524E5E] space-y-1">
              <div className="flex justify-between">
                <span>Phone call time</span>
                <span className="font-mono">
                  {Math.floor(amount / (catalog?.rates?.pstnUsdPerMin || 0.09))} min
                </span>
              </div>
              <div className="flex justify-between">
                <span>Phone number (monthly)</span>
                <span className="font-mono">
                  {money(catalog?.rates?.numberMonthlyUsd ?? 4, 'USD')}
                </span>
              </div>
            </div>

            {tooSmall && (
              <p className="text-[11px] text-[#B91C1C]">
                The minimum payment is {currency === 'INR' ? money(minInr, 'INR') : money(minUsd, 'USD')}.
              </p>
            )}
            {tooLarge && (
              <p className="text-[11px] text-[#B91C1C]">
                The maximum payment is {currency === 'INR' ? money(maxInr, 'INR') : money(maxUsd, 'USD')}.
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
              {busy ? 'Opening checkout…' : `Pay ${money(amount, currency)}`}
            </TactileButton>

            <p className="text-[10px] text-center text-[#8C879A] flex items-center justify-center gap-1">
              {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
              Card details are entered on the payment provider, never here.
            </p>
          </>
        )}
      </div>
    </Modal>
  );
}

export default AddFundsModal;
