import React, { useCallback, useEffect, useState } from 'react';
import { Shield, Users, Phone, Building2, Wallet } from 'lucide-react';
import { api } from '../../services/api';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { showToast } from '../ui/ToastHost';

export function AdminModule() {
  const [overview, setOverview] = useState(null);
  const [tenants, setTenants] = useState([]);
  const [error, setError] = useState(null);
  const [grantTenant, setGrantTenant] = useState('');
  const [grantInr, setGrantInr] = useState('5000');
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

  const grant = async () => {
    const paise = Math.round(Number(grantInr) * 100);
    if (!grantTenant || !Number.isFinite(paise) || paise <= 0) return;
    setBusy(true);
    try {
      await api.admin.grantCredits({
        tenantId: grantTenant,
        amountInrPaise: paise,
        reason: 'admin_grant',
      });
      showToast('Credits granted', 'success');
      await load();
    } catch (e) {
      showToast(e.message || 'Grant failed', 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">Platform admin</h2>
        <p className="text-xs text-[#524E5E] mt-1">
          Access is decided by the API allowlist on every request. This page is not a hardcoded email check.
        </p>
      </div>
      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-800">{error}</div>
      )}
      {overview && (
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
      )}
      <SolidCard className="p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Wallet className="w-4 h-4 text-[#6344E7]" />
          <h3 className="text-sm font-bold text-[#0F0E17]">Grant wallet credits (INR)</h3>
        </div>
        <div className="grid sm:grid-cols-3 gap-3">
          <select
            value={grantTenant}
            onChange={(e) => setGrantTenant(e.target.value)}
            className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs"
          >
            {tenants.map((t) => (
              <option key={t.tenantId} value={t.tenantId}>
                {t.name} ({t.tenantId.slice(0, 8)})
              </option>
            ))}
          </select>
          <input
            type="number"
            min="1"
            value={grantInr}
            onChange={(e) => setGrantInr(e.target.value)}
            className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-mono"
            placeholder="Amount INR"
          />
          <TactileButton variant="primary" size="sm" loading={busy} onClick={grant}>
            Credit wallet
          </TactileButton>
        </div>
      </SolidCard>
      <SolidCard padding="p-0" className="overflow-hidden">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[10px] font-bold text-[#8C879A] uppercase">
              <th className="py-3 px-4">Workspace</th>
              <th className="py-3 px-4">Plan</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4 font-mono">INR</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#E4E2EB]">
            {tenants.map((t) => (
              <tr key={t.tenantId}>
                <td className="py-3 px-4 font-semibold">{t.name}</td>
                <td className="py-3 px-4">{t.plan}</td>
                <td className="py-3 px-4">{t.status}</td>
                <td className="py-3 px-4 font-mono">₹{(Number(t.balanceInrPaise || 0) / 100).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </SolidCard>
    </div>
  );
}
