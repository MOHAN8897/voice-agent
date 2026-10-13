"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AdminConfirmDialog } from "@/components/admin/AdminConfirmDialog";
import {
  AdminError,
  AdminLoading,
  AdminPageHeader,
  AdminStat,
} from "@/components/admin/AdminNav";
import { DevCard } from "@/components/dev/DevCard";
import {
  SkeuoBadge,
  SkeuoButton,
  SkeuoInput,
  SkeuoTable,
  SkeuoTableBody,
  SkeuoTableHead,
  SkeuoTableRow,
  SkeuoTd,
  SkeuoTh,
} from "@/components/ui/skeuo";
import { adminAction, formatWhen, useAdminResource } from "@/lib/useAdminResource";

type Assignment = {
  e164: string;
  numberId: string;
  tenant: string;
  tenantId: string;
  tenantPlan?: string | null;
  tenantStatus?: string | null;
  agent: string | null;
  agentId: string | null;
  purchaseStatus: string | null;
  stripeSubscriptionId: string | null;
  telnyxNumberId: string | null;
  carrierNumberId?: string | null;
  provider?: string | null;
  walletBalanceUsd?: number;
  walletCurrency?: string;
  createdAt: string | null;
};

type Tenant = {
  tenantId: string;
  name: string;
  walletBalanceUsd?: number;
  walletCurrency?: string;
};

type PoolNumber = {
  e164: string;
  numberId: string | null;
  telnyxNumberId: string | null;
  carrierNumberId?: string | null;
  provider?: string | null;
  tenantId: string | null;
  tenantName: string | null;
  status: string;
  source: string;
  available: boolean;
  inInventory?: boolean;
};

type CarrierCandidate = {
  e164: string;
  provider: string;
  country: string;
  monthlyUsd: number;
  monthlyInr: number;
};

const PURCHASE_TONE: Record<string, "success" | "warning" | "danger" | "muted"> = {
  active: "success",
  paid: "success",
  failed: "danger",
  refunded: "muted",
  pending: "warning",
  provisioned: "success",
};

export function AdminNumbersPage() {
  const searchParams = useSearchParams();
  const tenantFocus = searchParams.get("tenantId") || "";
  const numbers = useAdminResource<{ assignments: Assignment[]; activeProvider?: string }>(
    "/api/dev/admin/phone-assignments"
  );
  const tenants = useAdminResource<{ tenants: Tenant[] }>("/api/dev/admin/tenants");
  const pool = useAdminResource<{ numbers: PoolNumber[]; activeProvider?: string; telnyxError?: string }>(
    "/api/dev/admin/numbers/pool"
  );

  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [selectedE164, setSelectedE164] = useState("");
  const [newTenant, setNewTenant] = useState(tenantFocus);
  const [query, setQuery] = useState("");
  const [releaseTarget, setReleaseTarget] = useState<Assignment | null>(null);
  const [providerBusy, setProviderBusy] = useState(false);
  const [carrierProvider, setCarrierProvider] = useState("vobiz");
  const [carrierCountry, setCarrierCountry] = useState("IN");
  const [carrierTenantId, setCarrierTenantId] = useState(tenantFocus);
  const [carrierReason, setCarrierReason] = useState("");
  const [carrierResults, setCarrierResults] = useState<CarrierCandidate[]>([]);
  const [carrierSearchBusy, setCarrierSearchBusy] = useState(false);
  const [carrierNotice, setCarrierNotice] = useState<string | null>(null);

  const selectedPool = useMemo(
    () => (pool.data?.numbers ?? []).find((n) => n.e164 === selectedE164) || null,
    [pool.data, selectedE164]
  );

  const availablePool = useMemo(
    () => (pool.data?.numbers ?? []).filter((n) => n.available),
    [pool.data]
  );
  const inventoryCount = availablePool.filter((n) => n.inInventory || n.source.includes("inventory")).length;

  const rows = (numbers.data?.assignments ?? []).filter((a) => {
    if (tenantFocus && a.tenantId !== tenantFocus) return false;
    if (!query.trim()) return true;
    return `${a.e164} ${a.tenant} ${a.agent ?? ""}`.toLowerCase().includes(query.trim().toLowerCase());
  });

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy("");
    }
  }

  function allocate() {
    return run("allocate", async () => {
      if (!selectedE164.trim() || !newTenant) {
        throw new Error("Pick a number and a tenant");
      }
      await adminAction("/api/dev/admin/numbers/allocate", {
        method: "POST",
        body: {
          e164: selectedE164.trim(),
          tenantId: newTenant,
          telnyxNumberId: selectedPool?.telnyxNumberId || null,
        },
      });
      setSelectedE164("");
      await Promise.all([numbers.reload(), pool.reload(), tenants.reload()]);
    });
  }

  function reassign(a: Assignment, tenantId: string) {
    return run(`reassign:${a.numberId}`, async () => {
      await adminAction(`/api/dev/admin/numbers/${a.numberId}`, {
        method: "PATCH",
        body: { tenantId },
      });
      await Promise.all([numbers.reload(), pool.reload()]);
    });
  }

  function confirmRelease(statement: string) {
    if (!releaseTarget) return;
    const a = releaseTarget;
    return run(`release:${a.numberId}`, async () => {
      await adminAction(`/api/dev/admin/numbers/${a.numberId}/release`, {
        method: "POST",
        body: { note: statement },
      });
      setReleaseTarget(null);
      await Promise.all([numbers.reload(), pool.reload()]);
    });
  }

  const activeProv = pool.data?.activeProvider || numbers.data?.activeProvider || "vobiz";
  const activeProvUpper = activeProv.toUpperCase();

  useEffect(() => {
    setCarrierProvider(activeProv);
    setCarrierCountry(activeProv === "vobiz" ? "IN" : "US");
    setCarrierResults([]);
    setCarrierNotice(null);
  }, [activeProv]);

  async function switchCarrier() {
    const nextProvider = activeProv === "vobiz" ? "telnyx" : "vobiz";
    if (!window.confirm(`Switch the platform-wide calling network to ${nextProvider.toUpperCase()}? This affects new calls across workspaces.`)) return;
    setProviderBusy(true);
    setError(null);
    try {
      await adminAction("/api/dev/telephony/provider", {
        method: "PATCH",
        body: { provider: nextProvider },
      });
      await Promise.all([numbers.reload(), pool.reload()]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not switch the calling network");
    } finally {
      setProviderBusy(false);
    }
  }

  async function searchCarrierInventory() {
    setCarrierSearchBusy(true);
    setError(null);
    setCarrierNotice(null);
    try {
      if (carrierProvider !== activeProv) {
        throw new Error("Switch to the active carrier before searching inventory");
      }
      const query = new URLSearchParams({ provider: carrierProvider, country: carrierCountry.trim().toUpperCase() });
      const result = await adminAction<{ numbers: CarrierCandidate[] }>(
        `/api/dev/admin/numbers/carrier-search?${query.toString()}`,
        { method: "GET" }
      );
      setCarrierResults(result.numbers ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Carrier inventory search failed");
      setCarrierResults([]);
    } finally {
      setCarrierSearchBusy(false);
    }
  }

  function purchaseCarrierNumber(candidate: CarrierCandidate) {
    return run(`carrier-buy:${candidate.e164}`, async () => {
      if (candidate.provider !== activeProv) {
        throw new Error("Switch to the active carrier before ordering this number");
      }
      if (!carrierTenantId) throw new Error("Choose a target workspace first");
      if (carrierReason.trim().length < 8) throw new Error("Enter an 8-character reason for the carrier order");
      if (!window.confirm(`Provision ${candidate.e164} for the selected workspace? Carrier charges may apply.`)) return;
      setCarrierNotice(null);
      const result = await adminAction<{ status?: string; provisioning?: boolean }>("/api/dev/admin/numbers/carrier-purchase", {
        method: "POST",
        body: {
          e164: candidate.e164,
          provider: candidate.provider,
          country: candidate.country,
          tenantId: carrierTenantId,
          reason: carrierReason.trim(),
        },
      });
      setCarrierResults((current) => current.filter((item) => item.e164 !== candidate.e164));
      setCarrierNotice(
        result.provisioning
          ? "The order was accepted and is recorded as pending until the carrier confirms its line ID. Do not place a second order for this number."
          : "The number is active and assigned to the selected workspace."
      );
      await Promise.all([numbers.reload(), pool.reload()]);
    });
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <AdminPageHeader
          title="Phone numbers"
          description={`Release returns a DID to Platform inventory (still on ${activeProvUpper}, for sale again). Assignments exclude inventory — those show in the available pool.`}
        />
        <div className="flex flex-wrap items-center gap-2 self-start sm:self-auto">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-bold bg-accent/10 text-accent border border-accent/20">
            <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
            Active Carrier: {activeProvUpper}
          </span>
          <SkeuoButton disabled={providerBusy} onClick={() => void switchCarrier()}>
            {providerBusy ? "Switching…" : `Switch to ${activeProv === "vobiz" ? "Telnyx" : "Vobiz"}`}
          </SkeuoButton>
          <Link href="/dev/test-studio" className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel px-3 py-2 text-xs font-medium text-text-muted hover:text-text">
            Open call testing
          </Link>
        </div>
      </div>

      <AdminError error={error} />
      <AdminError error={numbers.error} />
      <AdminError error={tenants.error} />
      <AdminError error={pool.error} />
      {pool.data?.telnyxError && (
        <AdminError error={`${activeProvUpper} inventory: ${pool.data.telnyxError}`} />
      )}

      <div className="grid gap-4 sm:grid-cols-4">
        <AdminStat label="Assigned to tenants" value={numbers.data?.assignments.length ?? "—"} />
        <AdminStat
          label="Available in pool"
          value={availablePool.length}
          hint={`unassigned + platform inventory (${activeProvUpper})`}
        />
        <AdminStat label="In inventory" value={inventoryCount} tone="good" hint="ready for customer buy" />
        <AdminStat
          label="Tenants"
          value={tenants.data?.tenants.length ?? "—"}
          hint="same list as Tenants / Wallets"
        />
      </div>

      <DevCard
        title="Purchase a carrier number"
        description="Search carrier inventory, then provision a number directly to a workspace. Each order requires a reason and is recorded in the admin activity log."
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block text-xs"><span className="mb-1 block text-text-muted">Carrier</span><select value={carrierProvider} onChange={(event) => { setCarrierProvider(event.target.value); setCarrierCountry(event.target.value === "vobiz" ? "IN" : "US"); }} className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm"><option value="vobiz" disabled={activeProv !== "vobiz"}>Vobiz</option><option value="telnyx" disabled={activeProv !== "telnyx"}>Telnyx</option></select></label>
          <label className="block text-xs"><span className="mb-1 block text-text-muted">Country code</span><input value={carrierCountry} maxLength={2} onChange={(event) => setCarrierCountry(event.target.value.toUpperCase())} className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm" /></label>
          <label className="block text-xs"><span className="mb-1 block text-text-muted">Target workspace</span><select value={carrierTenantId} onChange={(event) => setCarrierTenantId(event.target.value)} className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm"><option value="">Choose workspace…</option>{(tenants.data?.tenants ?? []).map((tenant) => <option key={tenant.tenantId} value={tenant.tenantId}>{tenant.name}</option>)}</select></label>
          <label className="block text-xs"><span className="mb-1 block text-text-muted">Order reason (8+ characters)</span><input value={carrierReason} onChange={(event) => setCarrierReason(event.target.value)} maxLength={500} className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm" /></label>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3"><SkeuoButton disabled={carrierSearchBusy || !carrierCountry.trim() || carrierProvider !== activeProv} onClick={() => void searchCarrierInventory()}>{carrierSearchBusy ? "Searching…" : "Search numbers"}</SkeuoButton><span className="text-xs text-text-muted">Only unassigned inventory on the active carrier is shown.</span></div>
        {carrierNotice && <p className="mt-3 rounded-skeuo-sm border border-accent/20 bg-accent/5 px-3 py-2 text-xs text-text" role="status">{carrierNotice}</p>}
        {carrierResults.length > 0 && (
          <div className="mt-4 overflow-x-auto rounded-skeuo-sm border border-surface-border-subtle">
            <table className="w-full min-w-[500px] text-left text-sm"><thead className="bg-surface-panel-raised text-xs uppercase text-text-subtle"><tr><th className="p-3">Number</th><th className="p-3">Country</th><th className="p-3">Monthly rate</th><th className="p-3">Action</th></tr></thead><tbody>{carrierResults.map((candidate) => <tr key={candidate.e164} className="border-t border-surface-border-subtle"><td className="p-3 font-mono">{candidate.e164}</td><td className="p-3">{candidate.country}</td><td className="p-3">${candidate.monthlyUsd.toFixed(2)} / ₹{candidate.monthlyInr.toFixed(2)}</td><td className="p-3"><SkeuoButton disabled={Boolean(busy) || !carrierTenantId || carrierReason.trim().length < 8} onClick={() => void purchaseCarrierNumber(candidate)}>{busy === `carrier-buy:${candidate.e164}` ? "Ordering…" : "Provision"}</SkeuoButton></td></tr>)}</tbody></table>
          </div>
        )}
        {!carrierSearchBusy && carrierResults.length === 0 && <p className="mt-3 text-xs text-text-muted">Search to view available carrier inventory.</p>}
      </DevCard>

      <DevCard
        title="Assign number to tenant"
        description={`Platform inventory and ${activeProvUpper} carrier DIDs appear here. Only unassigned lines for the active trunk can be allocated.`}
      >
        <div className="flex flex-wrap items-end gap-3">
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Available number</span>
            <select
              value={selectedE164}
              onChange={(e) => setSelectedE164(e.target.value)}
              aria-label="Available number"
              className="min-w-[220px] rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 font-mono text-sm text-text"
            >
              <option value="">Select number…</option>
              {availablePool.map((n) => (
                <option key={n.e164} value={n.e164}>
                  {n.e164} · {n.inInventory || n.source.includes("inventory") ? "inventory" : n.source}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Tenant</span>
            <select
              value={newTenant}
              onChange={(e) => setNewTenant(e.target.value)}
              aria-label="Tenant"
              className="min-w-[200px] rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
            >
              <option value="">Select tenant…</option>
              {(tenants.data?.tenants ?? []).map((t) => (
                <option key={t.tenantId} value={t.tenantId}>
                  {t.name}
                  {t.walletBalanceUsd != null ? ` · $${Number(t.walletBalanceUsd).toFixed(2)}` : ""}
                </option>
              ))}
            </select>
          </label>
          <SkeuoButton
            onClick={allocate}
            disabled={!selectedE164.trim() || !newTenant || busy === "allocate"}
          >
            {busy === "allocate" ? "Assigning…" : "Assign to tenant"}
          </SkeuoButton>
        </div>
        {availablePool.length === 0 && !pool.loading && (
          <p className="mt-3 text-xs text-text-muted">
            No available numbers on {activeProvUpper}. Release a tenant DID to inventory, or purchase a line in the carrier dashboard.
          </p>
        )}
      </DevCard>

      <DevCard title="Tenant assignments">
        <div className="mb-3">
          <SkeuoInput
            placeholder="Filter by number, tenant, or agent"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Filter numbers"
            className="max-w-sm"
          />
        </div>
        <AdminLoading loading={numbers.loading} />
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh>Number</SkeuoTh>
            <SkeuoTh>Provider</SkeuoTh>
            <SkeuoTh>Tenant</SkeuoTh>
            <SkeuoTh>Wallet</SkeuoTh>
            <SkeuoTh>Agent</SkeuoTh>
            <SkeuoTh>Purchase</SkeuoTh>
            <SkeuoTh>Created</SkeuoTh>
            <SkeuoTh className="text-right">Actions</SkeuoTh>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {rows.map((a) => (
              <SkeuoTableRow key={a.numberId}>
                <SkeuoTd className="font-mono">
                  <div>{a.e164}</div>
                  {(a.telnyxNumberId || a.carrierNumberId) && (
                    <div className="text-[10px] text-text-subtle font-sans" title="Carrier number ID">
                      Carrier ID: {a.telnyxNumberId || a.carrierNumberId}
                    </div>
                  )}
                </SkeuoTd>
                <SkeuoTd>
                  <SkeuoBadge tone={a.provider === "vobiz" ? "warning" : "info"}>
                    {(a.provider || activeProv).toUpperCase()}
                  </SkeuoBadge>
                </SkeuoTd>
                <SkeuoTd className="text-sm">
                  <Link
                    href={`/dev/admin/tenants/${a.tenantId}`}
                    className="font-medium hover:underline"
                  >
                    {a.tenant}
                  </Link>
                  <p className="font-mono text-[10px] text-text-subtle">{a.tenantId}</p>
                  <p className="text-[10px] text-text-muted">{a.tenantStatus || "—"}</p>
                </SkeuoTd>
                <SkeuoTd className="font-mono text-xs">
                  ${Number(a.walletBalanceUsd ?? 0).toFixed(2)}
                </SkeuoTd>
                <SkeuoTd className="text-sm text-text-muted">
                  {a.agent ?? <SkeuoBadge tone="warning">not pinned</SkeuoBadge>}
                </SkeuoTd>
                <SkeuoTd>
                  <SkeuoBadge tone={PURCHASE_TONE[a.purchaseStatus ?? ""] ?? "muted"}>
                    {a.purchaseStatus ?? "manual"}
                  </SkeuoBadge>
                </SkeuoTd>
                <SkeuoTd className="text-xs text-text-muted">{formatWhen(a.createdAt)}</SkeuoTd>
                <SkeuoTd className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    <select
                      defaultValue={a.tenantId}
                      onChange={(e) => e.target.value !== a.tenantId && reassign(a, e.target.value)}
                      disabled={busy === `reassign:${a.numberId}`}
                      aria-label={`Reassign ${a.e164}`}
                      className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-2 py-1 text-xs text-text"
                    >
                      {(tenants.data?.tenants ?? []).map((t) => (
                        <option key={t.tenantId} value={t.tenantId}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                    <SkeuoButton
                      variant="ghost"
                      disabled={busy === `release:${a.numberId}`}
                      onClick={() => setReleaseTarget(a)}
                    >
                      Release to inventory
                    </SkeuoButton>
                  </div>
                </SkeuoTd>
              </SkeuoTableRow>
            ))}
            {rows.length === 0 && !numbers.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-text-muted" colSpan={8}>No tenant-assigned numbers for {activeProvUpper}.</SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>
      </DevCard>

      <AdminConfirmDialog
        open={Boolean(releaseTarget)}
        title={`Release ${releaseTarget?.e164 ?? ""} to inventory`}
        description={`Stops routing for the tenant immediately. The DID stays on ${activeProvUpper} under Platform inventory and becomes buyable again. Rental is not auto-refunded.`}
        confirmLabel="Release to inventory"
        tone="danger"
        statementPlaceholder="e.g. Tenant churned; return DID to sales inventory"
        busy={Boolean(busy)}
        onCancel={() => setReleaseTarget(null)}
        onConfirm={(statement) => void confirmRelease(statement)}
      />
    </div>
  );
}
