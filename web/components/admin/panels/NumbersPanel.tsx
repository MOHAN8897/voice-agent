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

  // Assignment Table Filters
  const [query, setQuery] = useState("");
  const [carrierFilter, setCarrierFilter] = useState("all");
  const [purchaseStatusFilter, setPurchaseStatusFilter] = useState("all");
  const [pinningFilter, setPinningFilter] = useState("all");
  const [tenantFilter, setTenantFilter] = useState(tenantFocus);

  // Pool Table Filters
  const [poolQuery, setPoolQuery] = useState("");
  const [poolCarrierFilter, setPoolCarrierFilter] = useState("all");
  const [poolTypeFilter, setPoolTypeFilter] = useState("all");

  const [releaseTarget, setReleaseTarget] = useState<Assignment | null>(null);
  const [providerBusy, setProviderBusy] = useState(false);
  const [carrierProvider, setCarrierProvider] = useState("vobiz");
  const [carrierCountry, setCarrierCountry] = useState("IN");
  const [carrierTenantId, setCarrierTenantId] = useState(tenantFocus);
  const [carrierReason, setCarrierReason] = useState("");
  const [carrierResults, setCarrierResults] = useState<CarrierCandidate[]>([]);
  const [carrierSearchBusy, setCarrierSearchBusy] = useState(false);
  const [carrierNotice, setCarrierNotice] = useState<string | null>(null);

  // Sync tenantFocus if it changes via URL
  useEffect(() => {
    if (tenantFocus) {
      setTenantFilter(tenantFocus);
      setNewTenant(tenantFocus);
      setCarrierTenantId(tenantFocus);
    }
  }, [tenantFocus]);

  const selectedPool = useMemo(
    () => (pool.data?.numbers ?? []).find((n) => n.e164 === selectedE164) || null,
    [pool.data, selectedE164]
  );

  const availablePool = useMemo(
    () => (pool.data?.numbers ?? []).filter((n) => n.available),
    [pool.data]
  );
  const inventoryCount = availablePool.filter((n) => n.inInventory || n.source.includes("inventory")).length;

  // Filtered Assignments
  const allAssignments = numbers.data?.assignments ?? [];
  const rows = useMemo(() => {
    return allAssignments.filter((a) => {
      if (tenantFilter && a.tenantId !== tenantFilter) return false;
      if (carrierFilter !== "all" && (a.provider || "").toLowerCase() !== carrierFilter) return false;
      if (purchaseStatusFilter !== "all" && (a.purchaseStatus || "manual").toLowerCase() !== purchaseStatusFilter) return false;
      if (pinningFilter === "pinned" && !a.agent) return false;
      if (pinningFilter === "unpinned" && a.agent) return false;

      if (!query.trim()) return true;
      const q = query.trim().toLowerCase();
      const searchTarget = `${a.e164} ${a.tenant} ${a.tenantId} ${a.agent ?? ""} ${a.telnyxNumberId ?? ""} ${a.carrierNumberId ?? ""}`.toLowerCase();
      return searchTarget.includes(q);
    });
  }, [allAssignments, tenantFilter, carrierFilter, purchaseStatusFilter, pinningFilter, query]);

  // Filtered Pool Numbers
  const filteredPoolNumbers = useMemo(() => {
    return availablePool.filter((n) => {
      const prov = (n.provider || pool.data?.activeProvider || "vobiz").toLowerCase();
      if (poolCarrierFilter !== "all" && prov !== poolCarrierFilter) return false;

      const isInv = n.inInventory || n.source.includes("inventory");
      if (poolTypeFilter === "inventory" && !isInv) return false;
      if (poolTypeFilter === "trunk" && isInv) return false;

      if (!poolQuery.trim()) return true;
      const q = poolQuery.trim().toLowerCase();
      return `${n.e164} ${n.source} ${n.telnyxNumberId ?? ""} ${n.carrierNumberId ?? ""}`.toLowerCase().includes(q);
    });
  }, [availablePool, pool.data?.activeProvider, poolCarrierFilter, poolTypeFilter, poolQuery]);

  const hasAssignmentFilters = Boolean(
    query.trim() ||
      carrierFilter !== "all" ||
      purchaseStatusFilter !== "all" ||
      pinningFilter !== "all" ||
      tenantFilter
  );

  const hasPoolFilters = Boolean(
    poolQuery.trim() ||
      poolCarrierFilter !== "all" ||
      poolTypeFilter !== "all"
  );

  function resetAssignmentFilters() {
    setQuery("");
    setCarrierFilter("all");
    setPurchaseStatusFilter("all");
    setPinningFilter("all");
    setTenantFilter("");
  }

  function resetPoolFilters() {
    setPoolQuery("");
    setPoolCarrierFilter("all");
    setPoolTypeFilter("all");
  }

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
        throw new Error("Pick a number and a workspace");
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
      const q = new URLSearchParams({ provider: carrierProvider, country: carrierCountry.trim().toUpperCase() });
      const result = await adminAction<{ numbers: CarrierCandidate[] }>(
        `/api/dev/admin/numbers/carrier-search?${q.toString()}`,
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
          title="Phone Numbers & Trunks"
          description={`Release returns a DID to Platform inventory (hosted on ${activeProvUpper}, available for instant purchase).`}
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
        <AdminStat label="Assigned numbers" value={allAssignments.length ?? "—"} />
        <AdminStat
          label="Available in pool"
          value={availablePool.length}
          hint={`unassigned + platform inventory (${activeProvUpper})`}
        />
        <AdminStat label="In inventory" value={inventoryCount} tone="good" hint="ready for instant assignment" />
        <AdminStat
          label="Workspaces"
          value={tenants.data?.tenants.length ?? "—"}
          hint="active tenants"
        />
      </div>

      {/* Purchase from Wholesale Carrier */}
      <DevCard
        title="Purchase a carrier number"
        description="Search carrier inventory, then provision a number directly to a workspace. Each order requires a reason and is recorded in the admin activity log."
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Carrier</span>
            <select
              value={carrierProvider}
              onChange={(event) => {
                setCarrierProvider(event.target.value);
                setCarrierCountry(event.target.value === "vobiz" ? "IN" : "US");
              }}
              className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
            >
              <option value="vobiz" disabled={activeProv !== "vobiz"}>Vobiz</option>
              <option value="telnyx" disabled={activeProv !== "telnyx"}>Telnyx</option>
            </select>
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Country code</span>
            <input
              value={carrierCountry}
              maxLength={2}
              onChange={(event) => setCarrierCountry(event.target.value.toUpperCase())}
              className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text font-mono"
            />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Target workspace</span>
            <select
              value={carrierTenantId}
              onChange={(event) => setCarrierTenantId(event.target.value)}
              className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
            >
              <option value="">Choose workspace…</option>
              {(tenants.data?.tenants ?? []).map((tenant) => (
                <option key={tenant.tenantId} value={tenant.tenantId}>
                  {tenant.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Order reason (8+ characters)</span>
            <input
              value={carrierReason}
              onChange={(event) => setCarrierReason(event.target.value)}
              maxLength={500}
              placeholder="e.g. Sales team dedicated DID"
              className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
            />
          </label>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <SkeuoButton
            disabled={carrierSearchBusy || !carrierCountry.trim() || carrierProvider !== activeProv}
            onClick={() => void searchCarrierInventory()}
          >
            {carrierSearchBusy ? "Searching…" : "Search carrier inventory"}
          </SkeuoButton>
          <span className="text-xs text-text-muted">Only unassigned inventory on the active carrier is shown.</span>
        </div>
        {carrierNotice && (
          <p className="mt-3 rounded-skeuo-sm border border-accent/20 bg-accent/5 px-3 py-2 text-xs text-text" role="status">
            {carrierNotice}
          </p>
        )}
        {carrierResults.length > 0 && (
          <div className="mt-4 overflow-x-auto rounded-skeuo-sm border border-surface-border-subtle">
            <table className="w-full min-w-[500px] text-left text-sm">
              <thead className="bg-surface-panel-raised text-xs uppercase text-text-subtle">
                <tr>
                  <th className="p-3">Number</th>
                  <th className="p-3">Country</th>
                  <th className="p-3">Monthly rate</th>
                  <th className="p-3">Action</th>
                </tr>
              </thead>
              <tbody>
                {carrierResults.map((candidate) => (
                  <tr key={candidate.e164} className="border-t border-surface-border-subtle">
                    <td className="p-3 font-mono">{candidate.e164}</td>
                    <td className="p-3">{candidate.country}</td>
                    <td className="p-3">${candidate.monthlyUsd.toFixed(2)} / ₹{candidate.monthlyInr.toFixed(2)}</td>
                    <td className="p-3">
                      <SkeuoButton
                        disabled={Boolean(busy) || !carrierTenantId || carrierReason.trim().length < 8}
                        onClick={() => void purchaseCarrierNumber(candidate)}
                      >
                        {busy === `carrier-buy:${candidate.e164}` ? "Ordering…" : "Provision"}
                      </SkeuoButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!carrierSearchBusy && carrierResults.length === 0 && (
          <p className="mt-3 text-xs text-text-muted">Search to view available carrier inventory.</p>
        )}
      </DevCard>

      {/* Manual Assignment Form */}
      <DevCard
        title="Assign number to workspace"
        description={`Platform inventory and ${activeProvUpper} carrier DIDs appear here. Select a number below or from the inventory table.`}
      >
        <div className="flex flex-wrap items-end gap-3">
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Selected number</span>
            <select
              value={selectedE164}
              onChange={(e) => setSelectedE164(e.target.value)}
              aria-label="Available number"
              className="min-w-[240px] rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 font-mono text-sm text-text"
            >
              <option value="">Select number…</option>
              {availablePool.map((n) => (
                <option key={n.e164} value={n.e164}>
                  {n.e164} · {n.inInventory || n.source.includes("inventory") ? "inventory" : n.source} ({(n.provider || activeProv).toUpperCase()})
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Target workspace</span>
            <select
              value={newTenant}
              onChange={(e) => setNewTenant(e.target.value)}
              aria-label="Tenant"
              className="min-w-[220px] rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
            >
              <option value="">Select workspace…</option>
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
            {busy === "allocate" ? "Assigning…" : "Assign to workspace"}
          </SkeuoButton>
        </div>
        {availablePool.length === 0 && !pool.loading && (
          <p className="mt-3 text-xs text-text-muted">
            No available numbers on {activeProvUpper}. Release a tenant DID to inventory, or purchase a line in the carrier dashboard.
          </p>
        )}
      </DevCard>

      {/* Available Pool & Platform Inventory Search/Filter Table */}
      <DevCard
        title="Available Pool & Platform Inventory"
        description="Search unassigned platform numbers and carrier trunk lines. Click 'Select' on any line to prefill the assignment form."
      >
        <div className="mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Search pool number</label>
              <SkeuoInput
                placeholder="E.164 phone number…"
                value={poolQuery}
                onChange={(e) => setPoolQuery(e.target.value)}
                aria-label="Search available pool"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Carrier trunk</label>
              <select
                value={poolCarrierFilter}
                onChange={(e) => setPoolCarrierFilter(e.target.value)}
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="all">All trunks</option>
                <option value="vobiz">Vobiz</option>
                <option value="telnyx">Telnyx</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Classification</label>
              <select
                value={poolTypeFilter}
                onChange={(e) => setPoolTypeFilter(e.target.value)}
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="all">All types</option>
                <option value="inventory">Platform Sales Inventory</option>
                <option value="trunk">Wholesale Trunk Pool</option>
              </select>
            </div>
          </div>

          <div className="flex items-center justify-between border-t border-surface-border-subtle pt-2 text-xs text-text-muted">
            <span>
              Showing <strong className="text-text">{filteredPoolNumbers.length}</strong> of{" "}
              <strong className="text-text">{availablePool.length}</strong> available lines
            </span>
            {hasPoolFilters && (
              <button
                type="button"
                onClick={resetPoolFilters}
                className="text-accent-primary hover:underline"
              >
                Clear filters
              </button>
            )}
          </div>
        </div>

        <AdminLoading loading={pool.loading} />
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh>Number</SkeuoTh>
            <SkeuoTh>Carrier</SkeuoTh>
            <SkeuoTh>Type</SkeuoTh>
            <SkeuoTh>Status</SkeuoTh>
            <SkeuoTh className="text-right">Action</SkeuoTh>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {filteredPoolNumbers.map((n) => {
              const isInv = n.inInventory || n.source.includes("inventory");
              const prov = (n.provider || pool.data?.activeProvider || "vobiz").toUpperCase();
              return (
                <SkeuoTableRow key={n.e164}>
                  <SkeuoTd className="font-mono font-medium text-text">{n.e164}</SkeuoTd>
                  <SkeuoTd>
                    <SkeuoBadge tone={prov === "VOBIZ" ? "warning" : "info"}>{prov}</SkeuoBadge>
                  </SkeuoTd>
                  <SkeuoTd className="text-xs">
                    {isInv ? (
                      <span className="font-medium text-status-success">Platform Inventory</span>
                    ) : (
                      <span className="text-text-muted">{n.source || "Carrier Trunk"}</span>
                    )}
                  </SkeuoTd>
                  <SkeuoTd>
                    <SkeuoBadge tone="success">Ready</SkeuoBadge>
                  </SkeuoTd>
                  <SkeuoTd className="text-right">
                    <SkeuoButton
                      variant={selectedE164 === n.e164 ? "primary" : "secondary"}
                      size="sm"
                      onClick={() => setSelectedE164(n.e164)}
                    >
                      {selectedE164 === n.e164 ? "Selected" : "Select"}
                    </SkeuoButton>
                  </SkeuoTd>
                </SkeuoTableRow>
              );
            })}
            {filteredPoolNumbers.length === 0 && !pool.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-center py-6 text-text-muted" colSpan={5}>
                  No available pool numbers match current filters.
                </SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>
      </DevCard>

      {/* Tenant Assignments Table with Multi-Filter System */}
      <DevCard title="Active Workspace Assignments">
        <div className="mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Search assignments</label>
              <SkeuoInput
                placeholder="Number, workspace, agent, ID…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Filter numbers"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Carrier</label>
              <select
                value={carrierFilter}
                onChange={(e) => setCarrierFilter(e.target.value)}
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="all">All carriers</option>
                <option value="vobiz">Vobiz</option>
                <option value="telnyx">Telnyx</option>
              </select>
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Purchase status</label>
              <select
                value={purchaseStatusFilter}
                onChange={(e) => setPurchaseStatusFilter(e.target.value)}
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="all">All statuses</option>
                <option value="active">Active</option>
                <option value="paid">Paid</option>
                <option value="provisioned">Provisioned</option>
                <option value="pending">Pending</option>
                <option value="failed">Failed</option>
              </select>
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Agent pinning</label>
              <select
                value={pinningFilter}
                onChange={(e) => setPinningFilter(e.target.value)}
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="all">All assignments</option>
                <option value="pinned">Pinned to Agent</option>
                <option value="unpinned">Not pinned</option>
              </select>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Filter by workspace</label>
              <select
                value={tenantFilter}
                onChange={(e) => setTenantFilter(e.target.value)}
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="">All workspaces</option>
                {(tenants.data?.tenants ?? []).map((t) => (
                  <option key={t.tenantId} value={t.tenantId}>
                    {t.name} ({t.tenantId.slice(0, 8)}…)
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-end justify-between border-t border-surface-border-subtle pt-2 text-xs text-text-muted">
              <div>
                Showing <strong className="text-text">{rows.length}</strong> of{" "}
                <strong className="text-text">{allAssignments.length}</strong> assignments
              </div>
              {hasAssignmentFilters && (
                <button
                  type="button"
                  onClick={resetAssignmentFilters}
                  className="rounded px-2 py-1 text-accent-primary hover:underline hover:bg-accent-primary/10 transition-colors"
                >
                  Clear filters
                </button>
              )}
            </div>
          </div>
        </div>

        <AdminLoading loading={numbers.loading} />
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh>Number</SkeuoTh>
            <SkeuoTh>Provider</SkeuoTh>
            <SkeuoTh>Workspace</SkeuoTh>
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
                  <div className="font-medium text-text">{a.e164}</div>
                  {(a.telnyxNumberId || a.carrierNumberId) && (
                    <div className="text-[10px] text-text-subtle font-sans" title="Carrier line ID">
                      Line: {a.telnyxNumberId || a.carrierNumberId}
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
                    className="font-medium text-accent-primary hover:underline"
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
                      size="sm"
                      disabled={busy === `release:${a.numberId}`}
                      onClick={() => setReleaseTarget(a)}
                    >
                      Release
                    </SkeuoButton>
                  </div>
                </SkeuoTd>
              </SkeuoTableRow>
            ))}
            {rows.length === 0 && !numbers.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-center py-6 text-text-muted" colSpan={8}>
                  No assigned numbers found matching current filters.
                </SkeuoTd>
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
