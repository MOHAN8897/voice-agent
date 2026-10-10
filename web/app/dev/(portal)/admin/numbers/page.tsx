"use client";

import { useMemo, useState } from "react";
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
  plivoNumberId?: string | null;
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
  plivoNumberId?: string | null;
  provider?: string | null;
  tenantId: string | null;
  tenantName: string | null;
  status: string;
  source: string;
  available: boolean;
  inInventory?: boolean;
};

const PURCHASE_TONE: Record<string, "success" | "warning" | "danger" | "muted"> = {
  active: "success",
  paid: "success",
  failed: "danger",
  refunded: "muted",
  pending: "warning",
  provisioned: "success",
};

export default function AdminNumbersPage() {
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

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <AdminPageHeader
          title="Phone numbers"
          description={`Release returns a DID to Platform inventory (still on ${activeProvUpper}, for sale again). Assignments exclude inventory — those show in the available pool.`}
        />
        <div className="self-start sm:self-auto">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-bold bg-accent/10 text-accent border border-accent/20">
            <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
            Active Carrier: {activeProvUpper}
          </span>
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
                <SkeuoTd className="font-mono">{a.e164}</SkeuoTd>
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
