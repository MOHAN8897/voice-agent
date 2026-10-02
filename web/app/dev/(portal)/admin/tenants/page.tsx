"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { DevCard } from "@/components/dev/DevCard";
import {
  AdminError,
  AdminLoading,
  AdminPageHeader,
} from "@/components/admin/AdminNav";
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

type Tenant = {
  tenantId: string;
  name: string;
  status: string;
  plan?: string | null;
  createdAt: string | null;
  walletBalanceUsd?: number;
  walletCurrency?: string;
  numberCount?: number;
  memberCount?: number;
  isInventory?: boolean;
};

const STATUSES = ["", "active", "suspended", "past_due", "cancelled"];
const PLANS = ["", "starter", "growth", "enterprise", "default", "dev", "platform"];
const PAGE_SIZE = 50;

export default function AdminTenantsPage() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [plan, setPlan] = useState("");
  const [hasNumbers, setHasNumbers] = useState("");
  const [balanceBand, setBalanceBand] = useState("");
  const [showInventory, setShowInventory] = useState(false);
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newPlan, setNewPlan] = useState("starter");

  const listUrl = useMemo(() => {
    const p = new URLSearchParams();
    if (query.trim()) p.set("q", query.trim());
    if (status) p.set("status", status);
    if (plan) p.set("plan", plan);
    if (hasNumbers === "yes") p.set("hasNumbers", "true");
    if (hasNumbers === "no") p.set("hasNumbers", "false");
    if (balanceBand === "zero") {
      p.set("maxBalanceUsd", "0");
    } else if (balanceBand === "low") {
      p.set("maxBalanceUsd", "5");
    } else if (balanceBand === "funded") {
      p.set("minBalanceUsd", "5");
    }
    p.set("excludeInventory", showInventory ? "false" : "true");
    p.set("limit", String(PAGE_SIZE));
    p.set("offset", String(offset));
    return `/api/dev/admin/tenants?${p.toString()}`;
  }, [query, status, plan, hasNumbers, balanceBand, showInventory, offset]);

  const tenants = useAdminResource<{ tenants: Tenant[]; total?: number }>(listUrl, [listUrl]);

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

  function createTenant() {
    return run("create", async () => {
      await adminAction("/api/dev/admin/tenants", {
        method: "POST",
        body: { name: newName.trim(), status: "active", plan: newPlan },
      });
      setNewName("");
      setCreateOpen(false);
      setOffset(0);
      await tenants.reload();
    });
  }

  const total = tenants.data?.total ?? tenants.data?.tenants?.length ?? 0;
  const rows = tenants.data?.tenants ?? [];

  return (
    <div className="space-y-6 p-6">
      <AdminPageHeader
        title="Tenants"
        description="Customer workspaces. Open a row for the full cockpit (plan, limits, wallet, numbers, audit)."
        actions={
          <SkeuoButton variant="primary" onClick={() => setCreateOpen(true)}>
            Add tenant
          </SkeuoButton>
        }
      />

      <AdminError error={error} />
      <AdminError error={tenants.error} />

      <DevCard title="All tenants">
        <div className="mb-3 flex flex-wrap items-end gap-2">
          <label className="text-xs text-text-muted">
            Search
            <SkeuoInput
              placeholder="Name"
              value={query}
              onChange={(e) => {
                setOffset(0);
                setQuery(e.target.value);
              }}
              aria-label="Search tenants"
              className="mt-1 max-w-xs"
            />
          </label>
          <label className="text-xs text-text-muted">
            Status
            <select
              value={status}
              onChange={(e) => {
                setOffset(0);
                setStatus(e.target.value);
              }}
              className="mt-1 block rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-2 py-1.5 text-xs text-text"
              aria-label="Filter by status"
            >
              {STATUSES.map((s) => (
                <option key={s || "all"} value={s}>
                  {s || "All statuses"}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-text-muted">
            Plan
            <select
              value={plan}
              onChange={(e) => {
                setOffset(0);
                setPlan(e.target.value);
              }}
              className="mt-1 block rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-2 py-1.5 text-xs text-text"
              aria-label="Filter by plan"
            >
              {PLANS.map((p) => (
                <option key={p || "all"} value={p}>
                  {p || "All plans"}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-text-muted">
            Numbers
            <select
              value={hasNumbers}
              onChange={(e) => {
                setOffset(0);
                setHasNumbers(e.target.value);
              }}
              className="mt-1 block rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-2 py-1.5 text-xs text-text"
              aria-label="Filter by numbers"
            >
              <option value="">Any</option>
              <option value="yes">Has numbers</option>
              <option value="no">No numbers</option>
            </select>
          </label>
          <label className="text-xs text-text-muted">
            Balance
            <select
              value={balanceBand}
              onChange={(e) => {
                setOffset(0);
                setBalanceBand(e.target.value);
              }}
              className="mt-1 block rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-2 py-1.5 text-xs text-text"
              aria-label="Filter by balance"
            >
              <option value="">Any balance</option>
              <option value="zero">$0</option>
              <option value="low">Under $5</option>
              <option value="funded">$5+</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs text-text-muted">
            <input
              type="checkbox"
              checked={showInventory}
              onChange={(e) => {
                setOffset(0);
                setShowInventory(e.target.checked);
              }}
            />
            Show Platform inventory
          </label>
        </div>

        <AdminLoading loading={tenants.loading} />
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh>Name</SkeuoTh>
            <SkeuoTh>Plan</SkeuoTh>
            <SkeuoTh>Wallet</SkeuoTh>
            <SkeuoTh>Members</SkeuoTh>
            <SkeuoTh>Numbers</SkeuoTh>
            <SkeuoTh>Status</SkeuoTh>
            <SkeuoTh>Created</SkeuoTh>
            <SkeuoTh className="text-right">Actions</SkeuoTh>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {rows.map((t) => (
              <SkeuoTableRow key={t.tenantId}>
                <SkeuoTd>
                  <Link
                    href={`/dev/admin/tenants/${t.tenantId}`}
                    className="font-medium text-text hover:underline"
                  >
                    {t.name}
                  </Link>
                  <p className="font-mono text-[10px] text-text-subtle">{t.tenantId}</p>
                </SkeuoTd>
                <SkeuoTd>
                  <SkeuoBadge>{t.plan || "—"}</SkeuoBadge>
                </SkeuoTd>
                <SkeuoTd className="font-mono text-xs">
                  ${Number(t.walletBalanceUsd ?? 0).toFixed(2)}
                </SkeuoTd>
                <SkeuoTd className="font-mono text-xs">{t.memberCount ?? 0}</SkeuoTd>
                <SkeuoTd className="font-mono text-xs">{t.numberCount ?? 0}</SkeuoTd>
                <SkeuoTd>
                  <SkeuoBadge>{t.status ?? "active"}</SkeuoBadge>
                </SkeuoTd>
                <SkeuoTd className="text-xs text-text-muted">{formatWhen(t.createdAt)}</SkeuoTd>
                <SkeuoTd className="text-right">
                  <Link href={`/dev/admin/tenants/${t.tenantId}`}>
                    <SkeuoButton variant="ghost">Open</SkeuoButton>
                  </Link>
                </SkeuoTd>
              </SkeuoTableRow>
            ))}
            {rows.length === 0 && !tenants.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-text-muted">No tenants match.</SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>

        <div className="mt-3 flex items-center justify-between text-xs text-text-muted">
          <span>
            {total} tenant{total === 1 ? "" : "s"}
            {total > PAGE_SIZE ? ` · showing ${offset + 1}–${Math.min(offset + PAGE_SIZE, total)}` : ""}
          </span>
          <div className="flex gap-2">
            <SkeuoButton
              variant="ghost"
              disabled={offset <= 0 || Boolean(busy)}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous
            </SkeuoButton>
            <SkeuoButton
              variant="ghost"
              disabled={offset + PAGE_SIZE >= total || Boolean(busy)}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </SkeuoButton>
          </div>
        </div>
      </DevCard>

      {createOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-tenant-title"
        >
          <div className="w-full max-w-md rounded-xl border border-surface-border bg-surface-panel p-5 shadow-lg">
            <h3 id="create-tenant-title" className="text-sm font-semibold text-text">
              Add tenant
            </h3>
            <p className="mt-1 text-xs text-text-muted">
              Creates a workspace with an empty USD wallet.
            </p>
            <label className="mt-4 block text-xs font-medium text-text">
              Name
              <SkeuoInput
                className="mt-1 w-full"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Acme Corp"
              />
            </label>
            <label className="mt-3 block text-xs font-medium text-text">
              Plan
              <select
                value={newPlan}
                onChange={(e) => setNewPlan(e.target.value)}
                className="mt-1 block w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-2 py-1.5 text-xs text-text"
              >
                {PLANS.filter(Boolean).map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <div className="mt-4 flex justify-end gap-2">
              <SkeuoButton variant="ghost" onClick={() => setCreateOpen(false)}>
                Cancel
              </SkeuoButton>
              <SkeuoButton
                variant="primary"
                disabled={!newName.trim() || busy === "create"}
                onClick={() => createTenant()}
              >
                Create
              </SkeuoButton>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
