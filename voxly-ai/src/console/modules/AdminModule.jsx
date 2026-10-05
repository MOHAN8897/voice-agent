import React, { useCallback, useEffect, useState } from 'react';
import { Shield, Users, Phone, Building2, Wallet, Minus, Plus } from 'lucide-react';
import { api } from '../../services/api';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { AdminMetricsSkeleton } from '../ui/Skeleton';
import { showToast } from '../ui/ToastHost';

function moneyUsd(cents) {
  return `$${(Number(cents || 0) / 100).toFixed(2)}`;
}

/**
 * USD is the display currency everywhere in this console.
 *
 * The server sends `balanceUsdCents` already converted at the admin-configured
 * rate, so nothing here re-derives a rate — a rate hardcoded in the UI is how
 * the screen and the invoice drift apart.
 */
function walletUsdCents(t) {
  if (t?.balanceUsdCents != null) return Number(t.balanceUsdCents) || 0;
  return Number(t?.balanceCents) || 0;
}

export function AdminModule() {
  const [overview, setOverview] = useState(null);
  const [tenants, setTenants] = useState([]);
  const [error, setError] = useState(null);
  const [grantTenant, setGrantTenant] = useState('');
  const [grantUsd, setGrantUsd] = useState('50');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [dash, list] = await Promise.all([api.admin.overview(), api.admin.tenants()]);
      setOverview(dash);
      setTenants(list);
    } catch (e) {
      setError(e.message || 'Admin API denied');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!grantTenant && tenants[0]?.tenantId) setGrantTenant(tenants[0].tenantId);
  }, [tenants, grantTenant]);

  const selected = tenants.find((t) => t.tenantId === grantTenant);
  // Charge rate from the server, not a constant: an admin changing the rate must
  // not leave this screen quoting a different dollar figure.
  const fxRateInr = Number(selected?.fxRateInr || tenants.find((t) => t.fxRateInr)?.fxRateInr) || 0;

  const adjust = async (sign) => {
    // The operator types USD — that is the currency this console speaks. The API
    // takes INR paise, so convert once here at the server-supplied charge rate.
    const usd = Math.abs(Number(grantUsd));
    if (!grantTenant || !Number.isFinite(usd) || usd <= 0) return;
    if (!fxRateInr) {
      showToast('No USD/INR rate available — cannot convert the amount', 'error');
      return;
    }
    const usdCents = Math.round(usd * 100);
    const paise = Math.round(usd * fxRateInr * 100) * (sign < 0 ? -1 : 1);
    setBusy(true);
    try {
      await api.admin.grantCredits({
        tenantId: grantTenant,
        amountInrPaise: paise,
        reason: sign < 0 ? 'admin_debit' : 'admin_grant',
      });
      showToast(
        sign < 0 ? `Debited ${moneyUsd(usdCents)}` : `Credited ${moneyUsd(usdCents)}`,
        'success'
      );
      await load();
    } catch (e) {
      showToast(e.message || 'Wallet adjust failed', 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="admin-wallet-panel">
      <div>
        <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">Platform admin</h2>
        <p className="text-xs text-[#524E5E] mt-1">
          Wallet balances are real currency, shown in USD. Access is
          re-checked against the server allowlist on every request.
        </p>
      </div>
      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-800">{error}</div>
      )}
      {overview ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['Tenants', overview.tenants, Building2],
            ['Users', overview.users, Users],
            ['Active numbers', overview.activeNumbers, Phone],
            ['Failed purchases', overview.failedPurchases, Shield],
          ].map(([label, value, Icon]) => (
            <SolidCard key={label} className="p-4">
              <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-[#8C879A]">
                <Icon className="w-3.5 h-3.5" />
                {label}
              </div>
              <p className="text-2xl font-mono font-bold text-[#0F0E17] mt-2">{value}</p>
            </SolidCard>
          ))}
        </div>
      ) : (
        <AdminMetricsSkeleton count={4} />
      )}
      <SolidCard className="p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Wallet className="w-4 h-4 text-[#6344E7]" />
          <h3 className="text-sm font-bold text-[#0F0E17]">Adjust wallet balance (USD)</h3>
        </div>
        {selected && (
          <p className="text-[11px] text-[#524E5E]" data-testid="admin-selected-wallet">
            Selected: {selected.name} · {moneyUsd(walletUsdCents(selected))}
          </p>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <select
            value={grantTenant}
            onChange={(e) => setGrantTenant(e.target.value)}
            data-testid="admin-tenant-select"
            className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-base sm:text-xs min-h-[42px] sm:min-h-[36px] sm:col-span-2 text-[#0F0E17]"
          >
            {tenants.map((t) => (
              <option key={t.tenantId} value={t.tenantId}>
                {t.name} — {moneyUsd(walletUsdCents(t))}
              </option>
            ))}
          </select>
          <input
            type="number"
            min="1"
            value={grantUsd}
            onChange={(e) => setGrantUsd(e.target.value)}
            data-testid="admin-credit-amount"
            className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-base sm:text-xs min-h-[42px] sm:min-h-[36px] font-mono text-[#0F0E17]"
            placeholder="Amount USD"
          />
          <div className="flex gap-2">
            <TactileButton
              variant="primary"
              size="sm"
              loading={busy}
              onClick={() => adjust(1)}
              data-testid="admin-credit-add"
              className="flex-1 sm:flex-initial min-h-[42px] sm:min-h-[36px]"
            >
              <Plus className="w-3.5 h-3.5" />
              Add
            </TactileButton>
            <TactileButton
              variant="secondary"
              size="sm"
              loading={busy}
              onClick={() => adjust(-1)}
              data-testid="admin-credit-debit"
              className="flex-1 sm:flex-initial min-h-[42px] sm:min-h-[36px]"
            >
              <Minus className="w-3.5 h-3.5" />
              Debit
            </TactileButton>
          </div>
        </div>
        <p className="text-[10px] text-[#8C879A]">
          Customer top-ups via Razorpay are credited in the currency they paid
          after payment verification. Amounts are entered here in USD and converted at
          the current rate. Use Add/Debit only for support adjustments.
        </p>
      </SolidCard>
      <SolidCard padding="p-0" className="overflow-hidden">
        <div className="overflow-x-auto scrollbar-none touch-pan-x">
          <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[10px] font-bold text-[#8C879A] uppercase">
              <th className="py-3 px-4">Workspace</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4 font-mono">USD</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#E4E2EB]">
            {tenants.map((t) => (
              <tr key={t.tenantId} data-testid={`admin-tenant-row-${t.tenantId}`}>
                <td className="py-3 px-4 font-semibold">{t.name}</td>
                <td className="py-3 px-4">{t.status}</td>
                <td className="py-3 px-4 font-mono">{moneyUsd(t.balanceCents)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </SolidCard>
    </div>
  );
}
