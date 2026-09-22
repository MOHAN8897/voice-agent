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
  Check,
  Sparkles,
  ArrowRight
} from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { useWorkspace } from '../context/WorkspaceContext';
import { PRICING_TIERS } from '../../data/siteContent';

export function BillingModule() {
  const { user } = useAuth();
  const {
    wallet,
    addFunds,
    toggleAutoRecharge,
    updateAutoRechargeSettings,
    currentWorkspace,
    updateWorkspaceTier
  } = useWorkspace();

  const [topupSuccess, setTopupSuccess] = useState(null);
  const [topupError, setTopupError] = useState(null);
  const [planSuccess, setPlanSuccess] = useState(null);
  const [annualBilling, setAnnualBilling] = useState(true);
  const [threshold, setThreshold] = useState(wallet.autoRechargeThresholdUsd);
  const [amount, setAmount] = useState(wallet.autoRechargeAmountUsd);
  const [serverWallet, setServerWallet] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [razorpayEnabled, setRazorpayEnabled] = useState(false);
  const [payBusy, setPayBusy] = useState(false);

  const refreshBilling = useCallback(async () => {
    try {
      const [w, inv, cfg] = await Promise.all([
        api.billing.getWallet(),
        api.billing.listInvoices(),
        api.billing.razorpayConfig(),
      ]);
      setServerWallet(w);
      setInvoices(inv);
      setRazorpayEnabled(!!cfg?.enabled);
    } catch {
      /* demo wallet fallback */
    }
  }, []);

  useEffect(() => {
    refreshBilling();
  }, [refreshBilling]);

  const handleTopupInr = async (amountInr) => {
    setTopupError(null);
    setPayBusy(true);
    try {
      const cfg = await api.billing.razorpayConfig();
      if (!cfg?.enabled) throw new Error('Razorpay is not configured on the server.');
      const order = await api.billing.createRazorpayOrder(amountInr);
      await openRazorpayWalletCheckout({
        order,
        keyId: cfg.keyId,
        user,
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

  const handleTopup = async (amtUsd) => {
    setTopupError(null);
    try {
      await addFunds(amtUsd);
    } catch (err) {
      setTopupError(err.message || 'Top-up failed');
    }
  };

  const handleSelectPlan = (_tierName) => {
    setTopupError('Plan changes are not billed yet — use wallet top-up for PSTN usage.');
  };

  const activeTierName = (currentWorkspace?.tier || 'Professional Fleet').replace(' Fleet', '');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">
          Wallet, Per-Second Billing & Plans
        </h2>
        <p className="text-xs text-[#524E5E] mt-0.5">
          Pure per-second telephony metering with zero charges for unanswered rings and customizable plan tiers.
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

      {planSuccess && (
        <div className="p-3.5 rounded-xl bg-[#6344E7]/10 border border-[#6344E7]/20 text-xs font-semibold text-[#6344E7] flex items-center gap-2 animate-in fade-in duration-150">
          <Sparkles className="w-4 h-4 shrink-0 text-[#6344E7]" />
          <span>{planSuccess}</span>
        </div>
      )}

      {/* Subscription Plans Section */}
      <SolidCard className="space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-[#E4E2EB]">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
                Fleet Subscription Plan
              </span>
              <span className="text-[10px] font-mono font-bold text-[#15803D] bg-[#22C55E]/10 border border-[#22C55E]/20 px-2 py-0.5 rounded-md">
                Active: {currentWorkspace?.tier || 'Professional Fleet'}
              </span>
            </div>
            <p className="text-xs text-[#524E5E] mt-0.5">
              Select or switch your fleet tier to scale concurrent voice channels, agent limits, and included minutes.
            </p>
          </div>

          {/* Monthly vs Annual Toggle */}
          <div className="inline-flex p-1 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB] self-start sm:self-center">
            <button
              type="button"
              onClick={() => setAnnualBilling(false)}
              className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                !annualBilling
                  ? 'bg-white text-[#0F0E17] shadow-xs'
                  : 'text-[#524E5E] hover:text-[#0F0E17]'
              }`}
            >
              Monthly
            </button>
            <button
              type="button"
              onClick={() => setAnnualBilling(true)}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                annualBilling
                  ? 'bg-white text-[#0F0E17] shadow-xs'
                  : 'text-[#524E5E] hover:text-[#0F0E17]'
              }`}
            >
              <span>Annual</span>
              <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-[#0F0E17] text-white">
                -20%
              </span>
            </button>
          </div>
        </div>

        {/* 3 Interactive Plan Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {PRICING_TIERS.map((tier) => {
            const price = annualBilling ? tier.priceAnnual : tier.priceMonthly;
            const isCurrentActive = activeTierName.toLowerCase() === tier.name.toLowerCase();

            return (
              <div
                key={tier.name}
                onClick={() => handleSelectPlan(tier.name)}
                className={`p-5 rounded-xl border flex flex-col justify-between transition-all cursor-pointer relative group ${
                  isCurrentActive
                    ? 'bg-white border-2 border-[#6344E7] shadow-craft-md ring-2 ring-[#6344E7]/10'
                    : 'bg-[#FAF9FD] border-[#E4E2EB] hover:border-[#D1CFDB] hover:bg-white'
                }`}
              >
                {/* Active Indicator Badge */}
                {isCurrentActive && (
                  <div className="absolute -top-2.5 right-4 bg-[#6344E7] text-white text-[10px] font-bold px-2 py-0.5 rounded-full flex items-center gap-1 shadow-xs">
                    <Check className="w-2.5 h-2.5 stroke-[3]" />
                    <span>Active Plan</span>
                  </div>
                )}

                <div>
                  <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#6344E7] mb-1">
                    {tier.badge}
                  </div>
                  <h3 className="text-base font-bold text-[#0F0E17]">{tier.name}</h3>
                  <p className="text-xs text-[#524E5E] mt-1 line-clamp-2 leading-relaxed">
                    {tier.description}
                  </p>

                  <div className="my-3 pb-3 border-b border-[#E4E2EB] flex items-baseline gap-1">
                    <span className="text-2xl font-bold font-mono text-[#0F0E17]">${price}</span>
                    <span className="text-xs text-[#524E5E]">/ month</span>
                    {annualBilling && (
                      <span className="text-[10px] text-[#15803D] font-mono font-semibold ml-1">
                        (Annual)
                      </span>
                    )}
                  </div>

                  <ul className="space-y-1.5 text-xs text-[#524E5E] mb-4">
                    {tier.features.slice(0, 4).map((f, idx) => (
                      <li key={idx} className="flex items-center gap-1.5">
                        <Check className="w-3 h-3 text-[#15803D] shrink-0" />
                        <span className="truncate">{f}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleSelectPlan(tier.name);
                  }}
                  className={`w-full py-2 px-3 rounded-lg text-xs font-semibold transition-all flex items-center justify-center gap-1.5 active:scale-[0.98] ${
                    isCurrentActive
                      ? 'bg-[#6344E7] text-white shadow-xs font-bold'
                      : 'bg-white border border-[#E4E2EB] hover:bg-[#FAF9FD] text-[#0F0E17]'
                  }`}
                >
                  {isCurrentActive ? (
                    <>
                      <Check className="w-3.5 h-3.5 stroke-[3]" />
                      <span>Current Plan</span>
                    </>
                  ) : (
                    <span>Switch to {tier.name}</span>
                  )}
                </button>
              </div>
            );
          })}
        </div>
      </SolidCard>

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
                Active Fleet Funded
              </span>
            </div>

            <div className="flex items-baseline gap-3 my-2 flex-wrap">
              <span className="text-3xl sm:text-4xl font-mono font-bold text-[#0F0E17] tracking-tight">
                {wallet.remainingMinutes.toLocaleString()} min
              </span>
              <span className="text-sm font-mono text-[#524E5E]">
                (${(serverWallet?.balanceUsd ?? wallet.usdEquivalent).toFixed(2)} USD
                {serverWallet?.balanceInr != null ? ` · ₹${serverWallet.balanceInr.toFixed(2)} INR` : ''})
              </span>
            </div>

            <p className="text-xs text-[#524E5E]">
              Billed at <strong className="text-[#0F0E17] font-semibold">$0.095 per minute</strong> ($0.001583/sec). Zero charges for unanswered or busy calls.
            </p>
          </div>

          {/* Quick Top-Up Strip */}
          <div className="pt-5 mt-4 border-t border-[#E4E2EB] space-y-3">
            {razorpayEnabled && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-semibold text-[#524E5E] mr-1">Top up (INR · Razorpay):</span>
                {[500, 1000, 2500, 5000].map((inr) => (
                  <button
                    key={inr}
                    type="button"
                    disabled={payBusy}
                    onClick={() => handleTopupInr(inr)}
                    className="px-3.5 py-1.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] hover:border-[#6344E7] text-xs font-mono font-bold text-[#0F0E17] hover:text-[#6344E7] active:scale-[0.98] transition-all shadow-craft-xs disabled:opacity-50"
                  >
                    +₹{inr}
                  </button>
                ))}
              </div>
            )}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-semibold text-[#524E5E] mr-1">Top up (USD · Stripe):</span>
              {[50, 100, 250, 500].map((val) => (
                <button
                  key={val}
                  type="button"
                  onClick={() => handleTopup(val)}
                  className="px-3.5 py-1.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] hover:border-[#6344E7] text-xs font-mono font-bold text-[#0F0E17] hover:text-[#6344E7] active:scale-[0.98] transition-all shadow-craft-xs"
                >
                  +${val}
                </button>
              ))}
            </div>
          </div>
        </SolidCard>

        {/* Right Col: Default Card on File */}
        <SolidCard className="space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="font-bold text-[#0F0E17]">Payment Method</span>
            <span className="text-[10px] text-[#15803D] font-mono font-medium bg-[#22C55E]/10 border border-[#22C55E]/20 px-2 py-0.5 rounded-md">
              {razorpayEnabled ? 'Razorpay + Stripe' : 'Stripe'}
            </span>
          </div>

          <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-9 h-6 rounded-md bg-white border border-[#E4E2EB] flex items-center justify-center text-[10px] font-bold text-[#0F0E17] shadow-craft-xs">
                VISA
              </div>
              <div>
                <div className="text-xs font-mono font-semibold text-[#0F0E17]">•••• 4242</div>
                <div className="text-[10px] text-[#524E5E]">Expires 12/2028</div>
              </div>
            </div>
          </div>

          <p className="text-[11px] text-[#524E5E] leading-relaxed">
            All payments are processed securely via Stripe. Invoices and receipts include itemized telephony tax breakdowns.
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
            <span>Emergency Overdraft Buffer: <strong className="text-[#0F0E17] font-semibold">$15.00 buffer</strong> allows active calls to complete gracefully if payment declines.</span>
          </div>
        </SolidCard>

        {/* Transparent Cost Decomposition */}
        <SolidCard className="space-y-3">
          <h3 className="text-xs font-bold text-[#0F0E17]">Transparent Cost Decomposition</h3>
          <p className="text-[11px] text-[#524E5E]">Exactly how your $0.095/min ($0.001583/sec) is allocated across infrastructure.</p>

          <div className="space-y-2 text-xs font-mono">
            <div className="p-2.5 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] flex justify-between">
              <span className="text-[#524E5E]">1. Carrier PSTN Inbound/Outbound</span>
              <span className="text-[#0F0E17] font-semibold">$0.0120 / min</span>
            </div>
            <div className="p-2.5 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] flex justify-between">
              <span className="text-[#524E5E]">2. Streaming STT (Deepgram Nova-2)</span>
              <span className="text-[#0F0E17] font-semibold">$0.0070 / min</span>
            </div>
            <div className="p-2.5 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] flex justify-between">
              <span className="text-[#524E5E]">3. LLM Tokens (Streaming First-Token)</span>
              <span className="text-[#0F0E17] font-semibold">$0.0250 / min</span>
            </div>
            <div className="p-2.5 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] flex justify-between">
              <span className="text-[#524E5E]">4. Neural Voice Synthesis (Cartesia/11Labs)</span>
              <span className="text-[#0F0E17] font-semibold">$0.0460 / min</span>
            </div>
            <div className="p-2.5 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] flex justify-between">
              <span className="text-[#524E5E]">5. Regional Media Edge & Transcoding</span>
              <span className="text-[#0F0E17] font-semibold">$0.0050 / min</span>
            </div>
          </div>
        </SolidCard>
      </div>

      {/* Paid invoices (Razorpay wallet) */}
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
                    <td className="py-2.5 px-3 text-[#0F0E17]">₹{inv.amountInr?.toFixed(2)}</td>
                    <td className="py-2.5 px-3 text-[#15803D] capitalize">{inv.status}</td>
                    <td className="py-2.5 px-4 text-[#524E5E] truncate max-w-[140px]">{inv.paymentId || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SolidCard>
      )}

      {/* Itemized Cost Ledger Table */}
      <SolidCard padding="p-0" className="overflow-hidden">
        <div className="p-4 border-b border-[#E4E2EB] flex items-center justify-between">
          <h3 className="text-xs font-bold text-[#0F0E17]">Recent Per-Second Usage Ledger</h3>
          <button
            type="button"
            onClick={() => alert('Downloading itemized CSV usage ledger...')}
            className="flex items-center gap-1.5 text-xs text-[#6344E7] font-semibold hover:underline"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export CSV</span>
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[10px] text-[#524E5E] uppercase tracking-wider font-semibold">
                <th className="py-2.5 px-4">Transaction ID</th>
                <th className="py-2.5 px-3">Agent</th>
                <th className="py-2.5 px-3">Duration</th>
                <th className="py-2.5 px-3">PSTN</th>
                <th className="py-2.5 px-3">STT</th>
                <th className="py-2.5 px-3">LLM</th>
                <th className="py-2.5 px-3">TTS</th>
                <th className="py-2.5 px-4 text-right">Total Charged</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E4E2EB]">
              {wallet.costLedger.map((row) => (
                <tr key={row.id} className="hover:bg-[#FAF9FD]/80 transition-colors">
                  <td className="py-2.5 px-4 text-[#0F0E17] font-semibold">{row.id}</td>
                  <td className="py-2.5 px-3 text-[#524E5E]">{row.agent}</td>
                  <td className="py-2.5 px-3 text-[#0F0E17]">{row.durationSeconds}s</td>
                  <td className="py-2.5 px-3 text-[#524E5E]">{row.telecom}</td>
                  <td className="py-2.5 px-3 text-[#524E5E]">{row.stt}</td>
                  <td className="py-2.5 px-3 text-[#524E5E]">{row.llm}</td>
                  <td className="py-2.5 px-3 text-[#524E5E]">{row.tts}</td>
                  <td className="py-2.5 px-4 text-right font-bold text-[#15803D]">{row.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SolidCard>
    </div>
  );
}
