import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { openRazorpayWalletCheckout } from '../../utils/razorpayCheckout';
import {
  CreditCard,
  Zap,
  Clock,
  ShieldCheck,
  CheckCircle2,
  Download,
  AlertCircle,
  Plus,
  ArrowUpRight,
} from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { useWorkspace } from '../context/WorkspaceContext';

/** Plain-language labels for wallet ledger kinds. */
const TRANSACTION_LABEL = {
  usage_pstn: 'Phone call usage',
  usage_web: 'Browser test call',
  did_purchase: 'Phone number',
  did_refund: 'Phone number refund',
  admin_seed: 'Starting balance',
  admin_grant: 'Balance added',
  admin_debit: 'Balance removed',
  topup: 'Top-up (USD)',
  razorpay_topup_inr: 'Top-up',
  razorpay_topup: 'Top-up',
};

function describeTransactionKind(kind) {
  return TRANSACTION_LABEL[kind] || kind || 'Adjustment';
}

function toCsv(rows) {
  const header = ['when', 'type', 'reference', 'inr', 'usd'];
  const body = rows.map((r) => [
    r.createdAt || '',
    describeTransactionKind(r.kind),
    r.referenceId || '',
    ((Number(r.amountInrPaise) || 0) / 100).toFixed(2),
    ((Number(r.amountCents) || 0) / 100).toFixed(2),
  ]);
  const escape = (cell) => `"${String(cell).replace(/"/g, '""')}"`;
  return [header, ...body].map((line) => line.map(escape).join(',')).join('\n');
}

export function BillingModule() {
  const { user } = useAuth();
  const {
    wallet,
    toggleAutoRecharge,
    updateAutoRechargeSettings,
  } = useWorkspace();

  const [topupSuccess, setTopupSuccess] = useState(null);
  const [topupError, setTopupError] = useState(null);
  const [threshold, setThreshold] = useState(wallet.autoRechargeThresholdUsd);
  const [amount, setAmount] = useState(wallet.autoRechargeAmountUsd);
  const [serverWallet, setServerWallet] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [razorpayEnabled, setRazorpayEnabled] = useState(false);
  const [payBusy, setPayBusy] = useState(false);

  const refreshBilling = useCallback(async () => {
    try {
      const [w, inv, cfg, tx] = await Promise.all([
        api.billing.getWallet(),
        api.billing.listInvoices(),
        api.billing.razorpayConfig(),
        api.billing.listTransactions(40),
      ]);
      setServerWallet(w);
      setInvoices(inv);
      setRazorpayEnabled(!!cfg?.enabled);
      setTransactions(tx);
    } catch {
      /* demo wallet fallback */
    }
  }, []);

  useEffect(() => {
    refreshBilling();
  }, [refreshBilling]);

  const handleTopupUsd = async (amountUsd) => {
    setTopupError(null);
    setPayBusy(true);
    try {
      const cfg = await api.billing.razorpayConfig();
      if (!cfg?.enabled) throw new Error('Razorpay is not configured on the server.');
      const fx = Number(serverWallet?.fxRateInr) || 95.64;
      const amountInr = Math.max(100, Math.round(Number(amountUsd) * fx));
      const order = await api.billing.createRazorpayOrder(amountInr);
      await openRazorpayWalletCheckout({
        order,
        keyId: cfg.keyId,
        user,
        hideUpi: true,
        onSuccess: async (response) => {
          const result = await api.billing.verifyRazorpayPayment({
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          });
          await refreshBilling();
          setTopupSuccess(
            `Payment successful. Invoice ${result.invoiceNumber || result.invoiceId || ''} — wallet updated.`
          );
          setTimeout(() => setTopupSuccess(null), 5000);
        },
        onError: (err) => setTopupError(err.message || 'Payment failed'),
      });
    } catch (err) {
      setTopupError(err.message || 'Could not start payment');
    } finally {
      setPayBusy(false);
    }
  };

  const exportTransactionsCsv = useCallback(() => {
    if (typeof window === 'undefined' || !transactions.length) return;
    const blob = new Blob([toCsv(transactions)], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `voxly-billing-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [transactions]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">
          Wallet & per-second billing
        </h2>
        <p className="text-xs text-[#524E5E] mt-0.5">
          Pay-as-you-go wallet. Phone and browser calls meter by the second; unanswered carrier legs are free.
        </p>
      </div>

      {topupSuccess && (
        <div className="p-3.5 rounded-xl bg-[#22C55E]/10 border border-[#22C55E]/20 text-xs font-semibold text-[#15803D] flex items-center gap-2 animate-in fade-in duration-150">
          <CheckCircle2 className="w-4 h-4 shrink-0 text-[#15803D]" />
          <span>{topupSuccess}</span>
        </div>
      )}

      {topupError && (
        <div className="p-3.5 rounded-xl bg-red-500/10 border border-red-500/20 text-xs font-semibold text-red-700 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{topupError}</span>
        </div>
      )}

      {/* Primary Balance Ribbon */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* Left 2 Cols: Balance & Top-Up Buttons */}
        <SolidCard className="md:col-span-2 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className="text-xs font-semibold text-[#524E5E] uppercase tracking-wider flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5 text-amber-500" />
                <span>Available Talk Time Balance</span>
              </span>
              <span className="text-[11px] font-mono font-medium text-[#15803D] bg-[#22C55E]/10 border border-[#22C55E]/20 px-2 py-0.5 rounded-md">
                Wallet funded
              </span>
            </div>

            <div className="flex items-baseline gap-3 my-2 flex-wrap">
              <span className="text-3xl sm:text-4xl font-mono font-bold text-[#0F0E17] tracking-tight">
              {Number(wallet?.remainingMinutes || 0).toLocaleString()} min
              </span>
              <span className="text-sm font-mono text-[#524E5E]">
                (${Number(serverWallet?.balanceUsd ?? wallet.usdEquivalent ?? 0).toFixed(2)} USD)
              </span>
            </div>

            <p className="text-xs text-[#524E5E]">
              Phone calls billed at{' '}
              <strong className="text-[#0F0E17] font-semibold">
                ${Number(serverWallet?.rateUsdPerMin ?? wallet.rateUsdPerMin ?? 0.12).toFixed(3)}/min
              </strong>
              . Web tests billed at $
              {Number(serverWallet?.webRateUsdPerMin ?? wallet.webRateUsdPerMin ?? 0.09).toFixed(3)}/min.
              Your usage this workspace: $
              {Number(serverWallet?.myUsageUsd ?? wallet.myUsageUsd ?? 0).toFixed(2)}.
              Unanswered carrier legs are not billed.
            </p>
          </div>

          {/* Quick Top-Up Strip — USD display */}
          <div className="pt-5 mt-4 border-t border-[#E4E2EB] space-y-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-semibold text-[#524E5E] mr-1">Top up (USD):</span>
              {[5, 10, 25, 50, 100].map((usd) => (
                <button
                  key={usd}
                  type="button"
                  disabled={payBusy || !razorpayEnabled}
                  onClick={() => handleTopupUsd(usd)}
                  data-testid={`billing-topup-usd-${usd}`}
                  className="px-3.5 py-1.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] hover:border-[#6344E7] text-xs font-mono font-bold text-[#0F0E17] hover:text-[#6344E7] active:scale-[0.98] transition-all shadow-craft-xs disabled:opacity-50"
                >
                  +${usd}
                </button>
              ))}
            </div>
            {!razorpayEnabled && (
              <p className="text-[11px] text-[#B45309]">
                Razorpay is not enabled on this API — set RAZORPAY_API_KEY / RAZORPAY_API_SECRET,
                restart the API, then hard-refresh. Wallet top-up stays unavailable until then.
              </p>
            )}
          </div>
        </SolidCard>

        {/* Right Col: payment methods actually offered by the server */}
        <SolidCard className="space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="font-bold text-[#0F0E17]">Payment methods</span>
            <span className="text-[10px] text-[#15803D] font-mono font-medium bg-[#22C55E]/10 border border-[#22C55E]/20 px-2 py-0.5 rounded-md">
              {razorpayEnabled ? 'Razorpay' : 'Offline'}
            </span>
          </div>

          <ul className="space-y-2 text-xs text-[#524E5E]">
            <li className="flex items-center justify-between p-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
              <span className="font-semibold text-[#0F0E17]">Razorpay</span>
              <span>{razorpayEnabled ? 'Cards & netbanking' : 'Not enabled'}</span>
            </li>
          </ul>

          <p className="text-[11px] text-[#524E5E] leading-relaxed">
            Card details stay on Razorpay. Wallet balance is shown in USD. UPI is disabled for this product.
          </p>
        </SolidCard>
      </div>

      {/* Auto-Recharge Automation & Per-Second Cost Decomposition Split */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Auto-Recharge Controller */}
        <SolidCard className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-xs font-bold text-[#0F0E17]">Auto-Recharge Protection</h3>
              <p className="text-[11px] text-[#524E5E]">Prevents active telephone calls from dropping due to depleted credits.</p>
              <p className="text-[10px] text-[#8C879A] mt-1">Preview only — auto-recharge is not stored on the server yet. Top up manually via Razorpay or Stripe.</p>
            </div>
            <button
              type="button"
              onClick={toggleAutoRecharge}
              aria-label="Toggle auto recharge"
              className={`w-10 h-6 flex items-center rounded-full p-1 transition-colors ${
                wallet.autoRechargeEnabled ? 'bg-[#22C55E]' : 'bg-[#E4E2EB]'
              }`}
            >
              <div
                className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform ${
                  wallet.autoRechargeEnabled ? 'translate-x-4' : 'translate-x-0'
                }`}
              />
            </button>
          </div>

          <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-3 text-xs">
            <div className="flex items-center justify-between gap-4">
              <span className="text-[#524E5E]">When balance falls below:</span>
              <div className="flex items-center gap-1 font-mono font-bold text-[#0F0E17]">
                <span>$</span>
                <input
                  type="number"
                  value={threshold}
                  onChange={(e) => {
                    const v = parseFloat(e.target.value) || 0;
                    setThreshold(v);
                    updateAutoRechargeSettings(v, amount);
                  }}
                  className="w-16 bg-white border border-[#E4E2EB] rounded-lg px-2 py-1 text-right text-[#0F0E17] focus:outline-none focus:border-[#6344E7] shadow-craft-xs"
                />
              </div>
            </div>

            <div className="flex items-center justify-between gap-4">
              <span className="text-[#524E5E]">Automatically charge card:</span>
              <div className="flex items-center gap-1 font-mono font-bold text-[#0F0E17]">
                <span>$</span>
                <input
                  type="number"
                  value={amount}
                  onChange={(e) => {
                    const v = parseFloat(e.target.value) || 0;
                    setAmount(v);
                    updateAutoRechargeSettings(threshold, v);
                  }}
                  className="w-16 bg-white border border-[#E4E2EB] rounded-lg px-2 py-1 text-right text-[#0F0E17] focus:outline-none focus:border-[#6344E7] shadow-craft-xs"
                />
              </div>
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
        </SolidCard>

        {/* What a call costs, taken from the live rates the server bills by. */}
        <SolidCard className="space-y-3">
          <h3 className="text-xs font-bold text-[#0F0E17]">What a call costs</h3>
          <p className="text-[11px] text-[#524E5E]">
            These are the rates your workspace is charged. Each call's actual cost is itemised in the
            usage ledger below.
          </p>

          <div className="space-y-2 text-xs font-mono">
            <div className="p-2.5 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] flex justify-between">
              <span className="text-[#524E5E]">Phone call (per minute)</span>
              <span className="text-[#0F0E17] font-semibold">
                ${Number(serverWallet?.rateUsdPerMin ?? 0).toFixed(3)}
              </span>
            </div>
            <div className="p-2.5 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] flex justify-between">
              <span className="text-[#524E5E]">Browser test call (per minute)</span>
              <span className="text-[#0F0E17] font-semibold">
                ${Number(serverWallet?.webRateUsdPerMin ?? 0).toFixed(3)}
              </span>
            </div>
            <div className="p-2.5 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] flex justify-between">
              <span className="text-[#524E5E]">Phone number rental (per month)</span>
              <span className="text-[#0F0E17] font-semibold">
                ${Number(serverWallet?.didMonthlyUsd ?? 0).toFixed(2)}
              </span>
            </div>
          </div>
        </SolidCard>
      </div>

      {invoices.length > 0 && (
        <SolidCard padding="p-0" className="overflow-hidden">
          <div className="p-4 border-b border-[#E4E2EB]">
            <h3 className="text-xs font-bold text-[#0F0E17]">Wallet invoices</h3>
            <p className="text-[11px] text-[#524E5E] mt-0.5">Paid top-ups with Razorpay reference IDs.</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[10px] text-[#524E5E] uppercase tracking-wider font-semibold">
                  <th className="py-2.5 px-4">Invoice #</th>
                  <th className="py-2.5 px-3">Date</th>
                  <th className="py-2.5 px-3">Amount</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-4">Payment ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E4E2EB]">
                {invoices.map((inv) => (
                  <tr key={inv.invoiceId} className="hover:bg-[#FAF9FD]/80">
                    <td className="py-2.5 px-4 font-semibold text-[#0F0E17]">{inv.invoiceNumber}</td>
                    <td className="py-2.5 px-3 text-[#524E5E]">
                      {inv.createdAt ? new Date(inv.createdAt).toLocaleString() : '—'}
                    </td>
                    <td className="py-2.5 px-3 text-[#0F0E17]">
                      {inv.amountUsd != null
                        ? `$${Number(inv.amountUsd).toFixed(2)}`
                        : inv.amountInr != null
                          ? `$${(Number(inv.amountInr) / (Number(serverWallet?.fxRateInr) || 95.64)).toFixed(2)}`
                          : '—'}
                    </td>
                    <td className="py-2.5 px-3 text-[#15803D] capitalize">{inv.status}</td>
                    <td className="py-2.5 px-4 text-[#524E5E] truncate max-w-[140px]">{inv.paymentId || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SolidCard>
      )}

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

        {transactions.length === 0 ? (
          <p className="px-4 py-6 text-center text-xs text-[#8C879A]">
            No charges yet. Add funds to place calls or buy a number.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[10px] text-[#524E5E] uppercase tracking-wider font-semibold">
                  <th className="py-2.5 px-4">When</th>
                  <th className="py-2.5 px-3">Type</th>
                  <th className="py-2.5 px-3">Reference</th>
                  <th className="py-2.5 px-4 text-right">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E4E2EB]">
                {transactions.map((row) => {
                  const inr = Number(row.amountInrPaise || 0) / 100;
                  const usd = Number(row.amountCents || 0) / 100;
                  const isCredit = inr > 0 || usd > 0;
                  return (
                    <tr key={row.id} className="hover:bg-[#FAF9FD]/80 transition-colors">
                      <td className="py-2.5 px-4 text-[#524E5E]">
                        {row.createdAt ? new Date(row.createdAt).toLocaleString() : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-[#0F0E17]">{describeTransactionKind(row.kind)}</td>
                      <td className="py-2.5 px-3 text-[#8C879A] truncate max-w-[220px]">
                        {row.referenceId || '—'}
                      </td>
                      <td
                        className={`py-2.5 px-4 text-right font-bold ${
                          isCredit ? 'text-[#15803D]' : 'text-[#0F0E17]'
                        }`}
                      >
                        {usd !== 0
                          ? `$${usd.toFixed(2)}`
                          : inr !== 0
                            ? `$${(inr / (Number(serverWallet?.fxRateInr) || 95.64)).toFixed(2)}`
                            : '—'}
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
