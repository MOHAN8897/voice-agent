import React, { useState, useEffect, useCallback } from 'react';
import {
  Shield,
  Users,
  Phone,
  Building2,
  Wallet,
  Minus,
  Plus,
  Radio,
  Server,
  CheckCircle2,
  AlertCircle,
  Trash2,
  Lock,
  Unlock,
  Search,
  ShoppingCart,
  RefreshCw,
  Globe,
  Sliders,
  Check,
  AlertTriangle,
  ChevronRight,
} from 'lucide-react';
import { api } from '../../services/api';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { AdminMetricsSkeleton } from '../ui/Skeleton';
import { showToast } from '../ui/ToastHost';

function moneyUsd(cents) {
  return `$${(Number(cents || 0) / 100).toFixed(2)}`;
}

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
  const [telephonyInfo, setTelephonyInfo] = useState(null);
  const [providerBusy, setProviderBusy] = useState(false);

  // Tenant action states
  const [tenantStatusBusyId, setTenantStatusBusyId] = useState(null);
  const [deleteConfirmTenant, setDeleteConfirmTenant] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  // Platform Phone Number Management states
  const [phoneNumbers, setPhoneNumbers] = useState([]);
  const [phoneNumbersLoading, setPhoneNumbersLoading] = useState(false);
  const [releaseBusyId, setReleaseBusyId] = useState(null);

  // Direct Carrier Phone Buying states
  const [buyProvider, setBuyProvider] = useState('vobiz');
  const [buyCountry, setBuyCountry] = useState('US');
  const [carrierResults, setCarrierResults] = useState([]);
  const [carrierSearchLoading, setCarrierSearchLoading] = useState(false);
  const [adminBuyTargetTenant, setAdminBuyTargetTenant] = useState('');
  const [buyingNumberE164, setBuyingNumberE164] = useState(null);

  // Test Call states
  const [testCallTo, setTestCallTo] = useState('+918897908470');
  const [testCallFrom, setTestCallFrom] = useState('+917965480745');
  const [testCallBusy, setTestCallBusy] = useState(false);
  const [testCallResult, setTestCallResult] = useState(null);

  const handleTestCall = async () => {
    if (!testCallTo.trim()) {
      showToast('Enter destination phone number in E.164 format', 'error');
      return;
    }
    setTestCallBusy(true);
    setTestCallResult(null);
    try {
      const res = await api.admin.triggerTestCall({
        toE164: testCallTo.trim(),
        fromE164: testCallFrom.trim() || null,
        provider: telephonyInfo?.activeProvider || 'vobiz',
      });
      setTestCallResult(res);
      showToast(`Test call initiated via ${res.provider?.toUpperCase()}! Call UUID: ${res.call_uuid?.slice(0, 8)}...`, 'success');
    } catch (err) {
      showToast(err.message || 'Test call failed', 'error');
      setTestCallResult({ ok: false, error: err.message });
    } finally {
      setTestCallBusy(false);
    }
  };

  const load = useCallback(async () => {
    setError(null);
    try {
      const [dash, list, tel, phones] = await Promise.all([
        api.admin.overview(),
        api.admin.tenants(),
        api.telephony.getProvider().catch(() => null),
        api.admin.listPhoneNumbers().catch(() => []),
      ]);
      setOverview(dash);
      setTenants(list);
      if (tel) {
        setTelephonyInfo(tel);
        if (tel.activeProvider) {
          setBuyProvider(tel.activeProvider);
        }
      }
      setPhoneNumbers(phones);
    } catch (e) {
      setError(e.message || 'Admin API access denied');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!grantTenant && tenants[0]?.tenantId) {
      setGrantTenant(tenants[0].tenantId);
    }
    if (!adminBuyTargetTenant && tenants[0]?.tenantId) {
      setAdminBuyTargetTenant(tenants[0].tenantId);
    }
  }, [tenants, grantTenant, adminBuyTargetTenant]);

  const selected = tenants.find((t) => t.tenantId === grantTenant);
  const fxRateInr = Number(selected?.fxRateInr || tenants.find((t) => t.fxRateInr)?.fxRateInr) || 0;

  const adjust = async (sign) => {
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

  const switchProvider = async (providerId) => {
    if (providerBusy || telephonyInfo?.activeProvider === providerId) return;
    setProviderBusy(true);
    try {
      await api.admin.setTelephonyProvider(providerId);
      showToast(`Switched active calling trunk to ${providerId.toUpperCase()}`, 'success');
      const updated = await api.telephony.getProvider();
      setTelephonyInfo(updated);
      setBuyProvider(providerId);
      await load();
    } catch (e) {
      showToast(e.message || 'Failed to switch telephony infrastructure', 'error');
    } finally {
      setProviderBusy(false);
    }
  };

  // Toggle Tenant Block / Unblock status
  const toggleTenantStatus = async (tenant) => {
    const isProtected = String(tenant.name || '').toLowerCase().includes('mohan saiteja');
    if (isProtected && tenant.status === 'active') {
      showToast("Primary workspace [mohan saiteja's Workspace] is protected and cannot be blocked.", 'error');
      return;
    }
    const nextStatus = tenant.status === 'active' ? 'suspended' : 'active';
    setTenantStatusBusyId(tenant.tenantId);
    try {
      await api.admin.updateTenantStatus(tenant.tenantId, nextStatus);
      showToast(
        nextStatus === 'active' ? `Unblocked ${tenant.name}` : `Blocked ${tenant.name}`,
        'success'
      );
      await load();
    } catch (e) {
      showToast(e.message || 'Failed to update tenant status', 'error');
    } finally {
      setTenantStatusBusyId(null);
    }
  };

  // Delete Tenant Permanently
  const confirmDeleteTenant = async () => {
    if (!deleteConfirmTenant) return;
    const isProtected = String(deleteConfirmTenant.name || '').toLowerCase().includes('mohan saiteja');
    if (isProtected) {
      showToast("Primary workspace [mohan saiteja's Workspace] is protected and cannot be deleted.", 'error');
      setDeleteConfirmTenant(null);
      return;
    }
    setDeleteBusy(true);
    try {
      await api.admin.deleteTenant(deleteConfirmTenant.tenantId);
      showToast(`Workspace "${deleteConfirmTenant.name}" has been permanently removed`, 'success');
      setDeleteConfirmTenant(null);
      await load();
    } catch (e) {
      showToast(e.message || 'Failed to delete workspace', 'error');
    } finally {
      setDeleteBusy(false);
    }
  };

  // Search Carrier Numbers (Vobiz or Telnyx)
  const searchCarrier = async () => {
    setCarrierSearchLoading(true);
    setCarrierResults([]);
    try {
      const results = await api.admin.searchCarrierNumbers(buyProvider, buyCountry);
      setCarrierResults(results);
      if (results.length === 0) {
        showToast(`No numbers found for ${buyCountry} on ${buyProvider.toUpperCase()}`, 'info');
      }
    } catch (e) {
      showToast(e.message || 'Failed to search carrier numbers', 'error');
    } finally {
      setCarrierSearchLoading(false);
    }
  };

  // Buy and Provision Number directly in Admin panel
  const handleAdminBuyNumber = async (item) => {
    const e164 = item.e164 || item.phone_number;
    if (!e164) return;
    setBuyingNumberE164(e164);
    try {
      await api.admin.buyPhoneNumber({
        e164,
        provider: buyProvider,
        country: buyCountry,
        tenantId: adminBuyTargetTenant || tenants[0]?.tenantId,
      });
      showToast(`Provisioned ${e164} on ${buyProvider.toUpperCase()} directly to workspace`, 'success');
      setCarrierResults((prev) => prev.filter((n) => (n.e164 || n.phone_number) !== e164));
      await load();
    } catch (e) {
      showToast(e.message || 'Failed to provision carrier number', 'error');
    } finally {
      setBuyingNumberE164(null);
    }
  };

  // Release Phone Number
  const handleReleaseNumber = async (numberId, e164) => {
    if (!window.confirm(`Are you sure you want to release ${e164}?`)) return;
    setReleaseBusyId(numberId);
    try {
      await api.admin.releasePhoneNumber(numberId);
      showToast(`Released line ${e164}`, 'success');
      await load();
    } catch (e) {
      showToast(e.message || 'Failed to release line', 'error');
    } finally {
      setReleaseBusyId(null);
    }
  };

  return (
    <div className="space-y-6" data-testid="admin-wallet-panel">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">Platform Administration</h2>
          <p className="text-xs text-[#524E5E] mt-1">
            Global management of workspaces, telephony infrastructure, carrier inventory, and platform balances.
          </p>
        </div>
        <TactileButton
          variant="secondary"
          size="sm"
          onClick={load}
          className="text-xs shrink-0 self-start sm:self-auto"
        >
          <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
          Refresh Console
        </TactileButton>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-800 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-red-600" />
          <span>{error}</span>
        </div>
      )}

      {/* Metrics Row */}
      {overview ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['Workspaces', overview.tenants, Building2],
            ['Users', overview.users, Users],
            ['Active Phone Lines', overview.activeNumbers, Phone],
            ['Failed Orders', overview.failedPurchases, Shield],
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

      {/* Telephony Infrastructure Selection Card */}
      <SolidCard className="p-5 space-y-4" data-testid="admin-telephony-card">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-[#6344E7]" />
            <h3 className="text-sm font-bold text-[#0F0E17]">Active Telephony Infrastructure</h3>
            <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-[#6344E7]/10 text-[#6344E7] font-semibold">
              Live Gateway
            </span>
          </div>
          {telephonyInfo && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-[#8C879A]">Current Primary:</span>
              <span className="font-bold text-[#0F0E17] uppercase tracking-wide">
                {telephonyInfo.activeLabel || telephonyInfo.activeProvider}
              </span>
              {telephonyInfo.ready ? (
                <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full font-medium">
                  <CheckCircle2 className="w-3 h-3" /> Ready
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full font-medium">
                  <AlertCircle className="w-3 h-3" /> Incomplete
                </span>
              )}
            </div>
          )}
        </div>

        <p className="text-xs text-[#524E5E]">
          Switching the provider updates all outbound dialing, inbound webhooks, and phone number purchasing workflows in real time.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
          {(telephonyInfo?.providers || [
            { id: 'vobiz', label: 'Vobiz Voice', enabled: true, ready: true },
            { id: 'telnyx', label: 'Telnyx Voice', enabled: true, ready: false },
          ]).map((p) => {
            const isActive = (telephonyInfo?.activeProvider || 'vobiz') === p.id;
            return (
              <div
                key={p.id}
                className={`relative rounded-xl border p-4 transition-all ${
                  isActive
                    ? 'border-[#6344E7] bg-[#6344E7]/5 ring-1 ring-[#6344E7]'
                    : 'border-[#E4E2EB] bg-[#FAF9FD] hover:border-[#8C879A]'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Server className="w-4 h-4 text-[#524E5E]" />
                    <span className="text-sm font-bold text-[#0F0E17]">{p.label}</span>
                  </div>
                  {isActive && (
                    <span className="text-[10px] uppercase font-bold text-[#6344E7] bg-[#6344E7]/10 px-2 py-0.5 rounded font-mono">
                      Active Trunk
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-[#524E5E] space-y-1 mb-3 font-mono">
                  <div>
                    Caller ID:{' '}
                    <span className="text-[#0F0E17] font-semibold">{p.phoneNumber || 'Dynamic Pool'}</span>
                  </div>
                  <div>
                    Endpoints:{' '}
                    <span className="text-[#0F0E17]">
                      {p.id === 'vobiz' ? '/api/vobiz/answer' : '/api/telnyx/webhook'}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    Status:{' '}
                    <span className={p.ready ? 'text-emerald-700 font-medium' : 'text-[#8C879A]'}>
                      {p.ready ? 'Live & Handshake Verified' : p.enabled ? 'Credentials Present' : 'Disabled'}
                    </span>
                  </div>
                </div>
                <TactileButton
                  variant={isActive ? 'primary' : 'secondary'}
                  size="sm"
                  className="w-full text-xs"
                  disabled={isActive || providerBusy}
                  loading={providerBusy && !isActive}
                  onClick={() => switchProvider(p.id)}
                >
                  {isActive ? 'Currently Active Trunk' : `Switch Platform to ${p.label}`}
                </TactileButton>
              </div>
            );
          })}
        </div>
      </SolidCard>

      {/* Telephony Canary & Live Test Call Card */}
      <SolidCard className="p-5 space-y-4" data-testid="admin-test-call-card">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-[#6344E7]" />
            <h3 className="text-sm font-bold text-[#0F0E17]">Live Telephony Test Call (Canary Probe)</h3>
          </div>
          <span className="text-xs font-mono font-medium text-[#6344E7] bg-[#6344E7]/10 px-2 py-0.5 rounded">
            Trunk: {telephonyInfo?.activeProvider?.toUpperCase() || 'VOBIZ'}
          </span>
        </div>
        <p className="text-xs text-[#524E5E]">
          Dispatch a live PSTN voice call to test carrier connectivity, audio streaming WebSocket, and VoiceXML instructions.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="text-[11px] font-semibold text-[#524E5E] block mb-1">
              Destination Phone Number (To)
            </label>
            <input
              type="text"
              className="w-full text-xs font-mono border border-[#E4E2EB] rounded-lg px-3 py-2 bg-white text-[#0F0E17]"
              value={testCallTo}
              onChange={(e) => setTestCallTo(e.target.value)}
              placeholder="+918897908470"
              data-testid="admin-test-call-to"
            />
          </div>
          <div>
            <label className="text-[11px] font-semibold text-[#524E5E] block mb-1">
              Outbound Caller ID (From / Available Lines)
            </label>
            {phoneNumbers.length > 0 ? (
              <select
                className="w-full text-xs font-mono border border-[#E4E2EB] rounded-lg px-3 py-2 bg-white text-[#0F0E17]"
                value={testCallFrom}
                onChange={(e) => setTestCallFrom(e.target.value)}
                data-testid="admin-test-call-from"
              >
                {phoneNumbers.map((p) => {
                  const val = p.e164 || p.number;
                  const prov = (p.provider || 'vobiz').toUpperCase();
                  return (
                    <option key={p.id || val} value={val}>
                      {val} • {prov} ({p.tenantName || 'Workspace'})
                    </option>
                  );
                })}
              </select>
            ) : (
              <input
                type="text"
                className="w-full text-xs font-mono border border-[#E4E2EB] rounded-lg px-3 py-2 bg-white text-[#0F0E17]"
                value={testCallFrom}
                onChange={(e) => setTestCallFrom(e.target.value)}
                placeholder="+917965480745"
                data-testid="admin-test-call-from"
              />
            )}
          </div>
        </div>

        <div className="flex items-center justify-between pt-1">
          <div className="text-[11px] text-[#524E5E]">
            {testCallResult?.ok ? (
              <span className="text-emerald-700 font-medium inline-flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> Call Active (UUID: {testCallResult.call_uuid?.slice(0, 12)}...)
              </span>
            ) : testCallResult?.error ? (
              <span className="text-rose-600 font-medium inline-flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5" /> {testCallResult.error}
              </span>
            ) : (
              <span>Ready to dial destination via {telephonyInfo?.activeProvider || 'vobiz'} trunk</span>
            )}
          </div>
          <TactileButton
            variant="primary"
            size="sm"
            loading={testCallBusy}
            disabled={testCallBusy || !testCallTo.trim()}
            onClick={handleTestCall}
            data-testid="admin-test-call-submit"
          >
            Initiate Test Call
          </TactileButton>
        </div>
      </SolidCard>

      {/* Admin Carrier Phone Buying & Provisioning Panel */}
      <SolidCard className="p-5 space-y-4" data-testid="admin-phone-buy-card">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div className="flex items-center gap-2">
            <ShoppingCart className="w-4 h-4 text-[#6344E7]" />
            <h3 className="text-sm font-bold text-[#0F0E17]">Carrier Number Acquisition & Provisioning</h3>
            <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-semibold border border-emerald-200">
              Admin Direct Buy
            </span>
          </div>
        </div>

        <p className="text-xs text-[#524E5E]">
          Search live phone numbers directly across carrier inventories (Vobiz or Telnyx) and provision them directly into any workspace.
        </p>

        {/* Carrier Search Filter Controls */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
          <div>
            <label className="block text-[10px] font-bold text-[#8C879A] uppercase mb-1">Carrier Provider</label>
            <select
              value={buyProvider}
              onChange={(e) => setBuyProvider(e.target.value)}
              className="w-full bg-white border border-[#E4E2EB] rounded-lg p-2 text-xs text-[#0F0E17] font-semibold focus:outline-none focus:border-[#6344E7]"
            >
              <option value="vobiz">Vobiz Voice (Active)</option>
              <option value="telnyx">Telnyx Voice</option>
            </select>
          </div>

          <div>
            <label className="block text-[10px] font-bold text-[#8C879A] uppercase mb-1">Country</label>
            <select
              value={buyCountry}
              onChange={(e) => setBuyCountry(e.target.value)}
              className="w-full bg-white border border-[#E4E2EB] rounded-lg p-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
            >
              <option value="US">United States (+1)</option>
              <option value="IN">India (+91)</option>
              <option value="GB">United Kingdom (+44)</option>
              <option value="CA">Canada (+1)</option>
              <option value="AU">Australia (+61)</option>
            </select>
          </div>

          <div>
            <label className="block text-[10px] font-bold text-[#8C879A] uppercase mb-1">Target Workspace</label>
            <select
              value={adminBuyTargetTenant}
              onChange={(e) => setAdminBuyTargetTenant(e.target.value)}
              className="w-full bg-white border border-[#E4E2EB] rounded-lg p-2 text-xs text-[#0F0E17] font-medium focus:outline-none focus:border-[#6344E7]"
            >
              {tenants.map((t) => (
                <option key={t.tenantId} value={t.tenantId}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-end">
            <TactileButton
              variant="primary"
              size="sm"
              loading={carrierSearchLoading}
              onClick={searchCarrier}
              className="w-full text-xs min-h-[34px]"
            >
              <Search className="w-3.5 h-3.5 mr-1" />
              Search Carrier DIDs
            </TactileButton>
          </div>
        </div>

        {/* Carrier Search Results List */}
        {carrierResults.length > 0 && (
          <div className="space-y-2 pt-1 max-h-60 overflow-y-auto">
            <div className="text-xs font-semibold text-[#0F0E17] px-1">
              Available Numbers on {buyProvider.toUpperCase()} ({carrierResults.length}):
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {carrierResults.map((item) => {
                const num = item.e164 || item.phone_number;
                const isBuying = buyingNumberE164 === num;
                return (
                  <div
                    key={num}
                    className="flex items-center justify-between p-3 rounded-xl bg-white border border-[#E4E2EB] shadow-2xs hover:border-[#6344E7] transition-all"
                  >
                    <div>
                      <div className="font-mono font-bold text-xs text-[#0F0E17]">{num}</div>
                      <div className="text-[10px] text-[#524E5E]">
                        {item.country || buyCountry} • {item.type || 'Local DID'} •{' '}
                        <span className="uppercase text-[#6344E7] font-semibold">{buyProvider}</span>
                      </div>
                    </div>
                    <TactileButton
                      variant="primary"
                      size="xs"
                      disabled={isBuying || Boolean(buyingNumberE164)}
                      loading={isBuying}
                      onClick={() => handleAdminBuyNumber(item)}
                      className="text-xs"
                    >
                      {isBuying ? 'Ordering…' : 'Order & Assign'}
                    </TactileButton>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Existing Platform Numbers Table */}
        <div className="pt-2">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wide text-[#8C879A]">
              Currently Provisioned Platform Phone Lines ({phoneNumbers.length})
            </h4>
          </div>
          <div className="overflow-x-auto rounded-xl border border-[#E4E2EB]">
            <table className="w-full text-left text-xs bg-white">
              <thead>
                <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[10px] font-bold text-[#8C879A] uppercase">
                  <th className="py-2.5 px-3">Phone Line (E.164)</th>
                  <th className="py-2.5 px-3">Carrier Trunk</th>
                  <th className="py-2.5 px-3">Workspace</th>
                  <th className="py-2.5 px-3">Assigned Agent</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E4E2EB]">
                {phoneNumbers.length === 0 ? (
                  <tr>
                    <td colSpan="6" className="py-6 text-center text-xs text-[#524E5E]">
                      No active phone numbers found across platform workspaces.
                    </td>
                  </tr>
                ) : (
                  phoneNumbers.map((p) => (
                    <tr key={p.id} className="hover:bg-[#FAF9FD]/50">
                      <td className="py-2.5 px-3 font-mono font-bold text-[#0F0E17]">{p.e164}</td>
                      <td className="py-2.5 px-3">
                        <span className={`text-[10px] uppercase font-mono px-2 py-0.5 rounded font-bold border ${
                          (p.provider || '').toLowerCase().includes('vobiz')
                            ? 'bg-purple-50 text-purple-700 border-purple-200'
                            : 'bg-sky-50 text-sky-700 border-sky-200'
                        }`}>
                          {p.provider || 'vobiz'}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-semibold text-[#0F0E17]">{p.tenantName}</td>
                      <td className="py-2.5 px-3 text-[#524E5E]">
                        {p.agentName ? (
                          <span className="text-[#6344E7] font-medium">{p.agentName}</span>
                        ) : (
                          <span className="text-[#8C879A]">Unassigned Pool</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3">
                        <span className="inline-flex items-center gap-1 text-[10px] font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                          <Check className="w-2.5 h-2.5" /> Active
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <button
                          type="button"
                          onClick={() => handleReleaseNumber(p.id, p.e164)}
                          disabled={releaseBusyId === p.id}
                          className="text-[11px] font-semibold text-rose-600 hover:text-rose-800 disabled:opacity-50"
                        >
                          {releaseBusyId === p.id ? 'Releasing…' : 'Release'}
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </SolidCard>

      {/* Adjust Wallet Balance Card */}
      <SolidCard className="p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Wallet className="w-4 h-4 text-[#6344E7]" />
          <h3 className="text-sm font-bold text-[#0F0E17]">Adjust Workspace Balance (USD)</h3>
        </div>
        {selected && (
          <p className="text-[11px] text-[#524E5E]" data-testid="admin-selected-wallet">
            Selected: <span className="font-semibold text-[#0F0E17]">{selected.name}</span> · Current Balance:{' '}
            <span className="font-mono font-bold text-[#0F0E17]">{moneyUsd(walletUsdCents(selected))}</span>
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
              <Plus className="w-3.5 h-3.5 mr-1" />
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
              <Minus className="w-3.5 h-3.5 mr-1" />
              Debit
            </TactileButton>
          </div>
        </div>
      </SolidCard>

      {/* Workspaces & Tenants Management Table */}
      <SolidCard padding="p-0" className="overflow-hidden">
        <div className="p-4 border-b border-[#E4E2EB] flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <h3 className="text-sm font-bold text-[#0F0E17]">Platform Workspaces</h3>
            <p className="text-[11px] text-[#524E5E] mt-0.5">
              Manage subscriber workspaces, control account status (Block / Unblock), and remove test workspaces.
            </p>
          </div>
          <span className="text-xs font-mono px-2.5 py-1 rounded-full bg-[#FAF9FD] border border-[#E4E2EB] text-[#524E5E]">
            Total: {tenants.length}
          </span>
        </div>

        <div className="overflow-x-auto scrollbar-none touch-pan-x">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[10px] font-bold text-[#8C879A] uppercase">
                <th className="py-3 px-4">Workspace Name</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 font-mono">Wallet (USD)</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E4E2EB]">
              {tenants.map((t) => {
                const isProtected = String(t.name || '').toLowerCase().includes('mohan saiteja');
                const isBusy = tenantStatusBusyId === t.tenantId;
                const isActive = t.status === 'active';

                return (
                  <tr key={t.tenantId} data-testid={`admin-tenant-row-${t.tenantId}`} className="hover:bg-[#FAF9FD]/50">
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-[#0F0E17]">{t.name}</span>
                        {isProtected && (
                          <span className="inline-flex items-center gap-1 text-[10px] font-bold bg-[#6344E7]/10 text-[#6344E7] border border-[#6344E7]/20 px-2 py-0.5 rounded-full">
                            <Shield className="w-2.5 h-2.5" /> Primary Workspace
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      {isActive ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full">
                          <Check className="w-3 h-3" /> Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-700 bg-amber-50 border border-amber-200 px-2.5 py-0.5 rounded-full">
                          <Lock className="w-3 h-3" /> Blocked ({t.status})
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 font-mono font-bold text-[#0F0E17]">
                      {moneyUsd(walletUsdCents(t))}
                    </td>
                    <td className="py-3 px-4 text-right">
                      {isProtected ? (
                        <span className="text-[11px] text-[#8C879A] italic">Protected System Workspace</span>
                      ) : (
                        <div className="flex items-center justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => toggleTenantStatus(t)}
                            disabled={isBusy}
                            className={`inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border font-medium transition-colors ${
                              isActive
                                ? 'border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100'
                                : 'border-emerald-200 bg-emerald-50 text-emerald-800 hover:bg-emerald-100'
                            }`}
                          >
                            {isActive ? (
                              <>
                                <Lock className="w-3 h-3" /> Block
                              </>
                            ) : (
                              <>
                                <Unlock className="w-3 h-3" /> Unblock
                              </>
                            )}
                          </button>
                          <button
                            type="button"
                            onClick={() => setDeleteConfirmTenant(t)}
                            className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border border-red-200 bg-red-50 text-red-700 hover:bg-red-100 font-medium transition-colors"
                          >
                            <Trash2 className="w-3 h-3" /> Delete
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </SolidCard>

      {/* Delete Confirmation Modal */}
      {deleteConfirmTenant && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs">
          <div className="w-full max-w-md bg-white rounded-2xl shadow-xl border border-[#E4E2EB] p-5 space-y-4">
            <div className="flex items-center gap-3 text-rose-600">
              <div className="w-10 h-10 rounded-full bg-rose-50 border border-rose-200 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5 text-rose-600" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-[#0F0E17]">Delete Workspace</h3>
                <p className="text-xs text-[#524E5E]">This action cannot be undone.</p>
              </div>
            </div>

            <p className="text-xs text-[#524E5E] leading-relaxed">
              Are you sure you want to permanently delete{' '}
              <strong className="text-[#0F0E17] font-semibold">{deleteConfirmTenant.name}</strong>? All associated agents,
              call histories, and workspace settings will be purged.
            </p>

            <div className="flex items-center justify-end gap-2 pt-2">
              <TactileButton
                variant="secondary"
                size="sm"
                onClick={() => setDeleteConfirmTenant(null)}
                disabled={deleteBusy}
                className="text-xs"
              >
                Cancel
              </TactileButton>
              <button
                type="button"
                onClick={confirmDeleteTenant}
                disabled={deleteBusy}
                className="inline-flex items-center justify-center px-4 py-2 rounded-xl text-xs font-bold text-white bg-rose-600 hover:bg-rose-700 disabled:opacity-50 transition-colors shadow-xs"
              >
                {deleteBusy ? 'Deleting…' : 'Yes, Delete Workspace'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
