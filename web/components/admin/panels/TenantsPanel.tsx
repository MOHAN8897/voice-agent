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
import { AdminConfirmDialog } from "@/components/admin/AdminConfirmDialog";

export type Tenant = {
  tenantId: string;
  name: string;
  status: string;
  plan?: string | null;
  createdAt: string | null;
  deletedAt?: string | null;
  walletBalanceUsd?: number;
  walletCurrency?: string;
  numberCount?: number;
  memberCount?: number;
  isInventory?: boolean;
};

const STATUSES = ["", "active", "suspended", "quarantined", "past_due", "cancelled", "deleted"];
const PLANS = ["", "starter", "growth", "enterprise", "default", "dev", "platform"];
const STATUS_TONE: Record<string, "success" | "warning" | "danger" | "muted"> = {
  active: "success",
  suspended: "danger",
  quarantined: "danger",
  past_due: "warning",
  cancelled: "muted",
  deleted: "muted",
};
const PAGE_SIZE = 50;

export function AdminTenantsPage() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [plan, setPlan] = useState("");
  const [hasNumbers, setHasNumbers] = useState("");
  const [balanceBand, setBalanceBand] = useState("");
  const [showInventory, setShowInventory] = useState(false);
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Selection for bulk actions
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Creation modal
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newPlan, setNewPlan] = useState("starter");

  // Single tenant deletion modal
  const [deleteTarget, setDeleteTarget] = useState<Tenant | null>(null);
  const [deleteReleaseNumbers, setDeleteReleaseNumbers] = useState(true);
  const [deleteRevokeSessions, setDeleteRevokeSessions] = useState(true);
  const [deleteForce, setDeleteForce] = useState(false);

  // Status transition modal
  const [statusTarget, setStatusTarget] = useState<{ tenant: Tenant; nextStatus: string } | null>(null);
  const [statusReleaseNumbers, setStatusReleaseNumbers] = useState(false);
  const [statusRevokeSessions, setStatusRevokeSessions] = useState(true);

  // Wallet adjustment modal
  const [walletTarget, setWalletTarget] = useState<Tenant | null>(null);
  const [walletAmount, setWalletAmount] = useState("10");
  const [walletMode, setWalletMode] = useState<"credit" | "debit">("credit");
  const [walletNote, setWalletNote] = useState("");

  // Impersonate modal
  const [impersonateTarget, setImpersonateTarget] = useState<Tenant | null>(null);

  // Bulk actions modal
  const [bulkActionTarget, setBulkActionTarget] = useState<
    "delete" | "suspend" | "activate" | "restore" | "change_plan" | null
  >(null);
  const [bulkPlan, setBulkPlan] = useState("starter");
  const [bulkReleaseNumbers, setBulkReleaseNumbers] = useState(true);
  const [bulkRevokeSessions, setBulkRevokeSessions] = useState(true);
  const [bulkForce, setBulkForce] = useState(false);

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
    if (includeDeleted) p.set("includeDeleted", "true");
    p.set("limit", String(PAGE_SIZE));
    p.set("offset", String(offset));
    return `/api/dev/admin/tenants?${p.toString()}`;
  }, [query, status, plan, hasNumbers, balanceBand, showInventory, includeDeleted, offset]);

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

  const total = tenants.data?.total ?? tenants.data?.tenants?.length ?? 0;
  const rows = tenants.data?.tenants ?? [];

  // Toggle selection
  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (selectedIds.size === rows.length && rows.length > 0) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(rows.map((r) => r.tenantId)));
    }
  }

  // 1. Create tenant
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

  // 2. Delete tenant
  function confirmDelete(statement: string) {
    if (!deleteTarget) return;
    return run(`delete:${deleteTarget.tenantId}`, async () => {
      const p = new URLSearchParams({
        force: String(deleteForce),
        releaseNumbers: String(deleteReleaseNumbers),
        revokeSessions: String(deleteRevokeSessions),
        note: statement,
      });
      await adminAction(`/api/dev/admin/tenants/${deleteTarget.tenantId}?${p.toString()}`, {
        method: "DELETE",
      });
      setDeleteTarget(null);
      setSelectedIds((prev) => {
        const next = new Set(prev);
        if (deleteTarget) next.delete(deleteTarget.tenantId);
        return next;
      });
      await tenants.reload();
    });
  }

  // 3. Restore tenant
  function restoreTenant(t: Tenant) {
    return run(`restore:${t.tenantId}`, async () => {
      await adminAction(`/api/dev/admin/tenants/${t.tenantId}/restore`, {
        method: "POST",
      });
      await tenants.reload();
    });
  }

  // 4. Quick change plan
  function quickChangePlan(t: Tenant, nextPlan: string) {
    if (!nextPlan || nextPlan === t.plan) return;
    return run(`plan:${t.tenantId}`, async () => {
      await adminAction(`/api/dev/admin/tenants/${t.tenantId}`, {
        method: "PATCH",
        body: { plan: nextPlan },
      });
      await tenants.reload();
    });
  }

  // 5. Quick change status
  function onStatusDropdownChange(t: Tenant, nextStatus: string) {
    if (!nextStatus || nextStatus === t.status) return;
    setStatusTarget({ tenant: t, nextStatus });
    setStatusReleaseNumbers(nextStatus === "cancelled" || nextStatus === "suspended");
    setStatusRevokeSessions(nextStatus === "cancelled" || nextStatus === "suspended");
  }

  function confirmStatus(statement: string) {
    if (!statusTarget) return;
    return run(`status:${statusTarget.tenant.tenantId}`, async () => {
      await adminAction(`/api/dev/admin/tenants/${statusTarget.tenant.tenantId}`, {
        method: "PATCH",
        body: {
          status: statusTarget.nextStatus,
          note: statement,
          releaseNumbers: statusReleaseNumbers,
          revokeSessions: statusRevokeSessions,
        },
      });
      setStatusTarget(null);
      await tenants.reload();
    });
  }

  // 6. Adjust wallet
  function confirmWalletAdjust() {
    if (!walletTarget) return;
    const dollars = Number(walletAmount);
    if (!Number.isFinite(dollars) || dollars <= 0) {
      setError("Enter a positive USD amount");
      return;
    }
    if (walletNote.trim().length < 8) {
      setError("Wallet adjustment requires an admin statement (min 8 chars)");
      return;
    }
    return run(`wallet:${walletTarget.tenantId}`, async () => {
      const sign = walletMode === "credit" ? 1 : -1;
      await adminAction("/api/dev/admin/wallets/adjust", {
        method: "POST",
        body: {
          tenantId: walletTarget.tenantId,
          amountUsdCents: Math.round(dollars * 100) * sign,
          reason: walletMode === "credit" ? "admin_credit" : "admin_debit",
          note: walletNote.trim(),
        },
      });
      setWalletTarget(null);
      setWalletNote("");
      await tenants.reload();
    });
  }

  // 7. Impersonate customer session
  function confirmImpersonate(statement: string) {
    if (!impersonateTarget) return;
    return run(`impersonate:${impersonateTarget.tenantId}`, async () => {
      const res = await adminAction<{ url?: string }>(
        `/api/dev/admin/tenants/${impersonateTarget.tenantId}/impersonate`,
        {
          method: "POST",
          body: { note: statement, ttlMinutes: 30 },
        }
      );
      setImpersonateTarget(null);
      if (res.url) {
        window.open(res.url, "_blank", "noopener,noreferrer");
      }
    });
  }

  // 8. Bulk action confirmation
  function confirmBulkAction(statement: string) {
    if (!bulkActionTarget || selectedIds.size === 0) return;
    return run("bulk", async () => {
      await adminAction("/api/dev/admin/tenants/bulk", {
        method: "POST",
        body: {
          action: bulkActionTarget,
          tenantIds: Array.from(selectedIds),
          plan: bulkActionTarget === "change_plan" ? bulkPlan : undefined,
          note: statement,
          releaseNumbers: bulkReleaseNumbers,
          revokeSessions: bulkRevokeSessions,
          force: bulkForce,
        },
      });
      setBulkActionTarget(null);
      setSelectedIds(new Set());
      await tenants.reload();
    });
  }

  return (
    <div className="space-y-6 p-6">
      <AdminPageHeader
        title="Tenants"
        description="Customer workspaces. Manage lifecycle, delete, restore, adjust wallet, switch tiers, and execute bulk actions."
        actions={
          <div className="flex items-center gap-2">
            <SkeuoButton variant="primary" onClick={() => setCreateOpen(true)}>
              + Add tenant
            </SkeuoButton>
          </div>
        }
      />

      <AdminError error={error} />
      <AdminError error={tenants.error} />

      <DevCard title="All tenants">
        {/* Filters */}
        <div className="mb-4 flex flex-wrap items-end gap-3 border-b border-surface-border-subtle pb-4">
          <label className="text-xs text-text-muted">
            Search
            <SkeuoInput
              placeholder="Tenant name or ID"
              value={query}
              onChange={(e) => {
                setOffset(0);
                setQuery(e.target.value);
              }}
              aria-label="Search tenants"
              className="mt-1 w-44"
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
                  {s ? s.toUpperCase() : "All statuses"}
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
                  {p ? p.toUpperCase() : "All plans"}
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
            Show Inventory
          </label>
          <label className="flex items-center gap-2 text-xs font-medium text-text">
            <input
              type="checkbox"
              checked={includeDeleted}
              onChange={(e) => {
                setOffset(0);
                setIncludeDeleted(e.target.checked);
              }}
            />
            Show Deleted / Cancelled
          </label>
        </div>

        {/* Floating Bulk Action Bar */}
        {selectedIds.size > 0 && (
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-skeuo-md border border-primary/30 bg-primary/10 p-3 text-xs shadow-sm">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-text">
                {selectedIds.size} tenant{selectedIds.size === 1 ? "" : "s"} selected
              </span>
              <button
                type="button"
                onClick={() => setSelectedIds(new Set())}
                className="text-text-muted underline hover:text-text"
              >
                Clear selection
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <SkeuoButton
                variant="ghost"
                onClick={() => setBulkActionTarget("activate")}
                disabled={Boolean(busy)}
              >
                Bulk Activate
              </SkeuoButton>
              <SkeuoButton
                variant="ghost"
                onClick={() => setBulkActionTarget("suspend")}
                disabled={Boolean(busy)}
              >
                Bulk Suspend
              </SkeuoButton>
              <div className="flex items-center gap-1">
                <select
                  value={bulkPlan}
                  onChange={(e) => setBulkPlan(e.target.value)}
                  className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-2 py-1 text-xs text-text"
                >
                  {PLANS.filter(Boolean).map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
                <SkeuoButton
                  variant="ghost"
                  onClick={() => setBulkActionTarget("change_plan")}
                  disabled={Boolean(busy)}
                >
                  Apply Plan
                </SkeuoButton>
              </div>
              <SkeuoButton
                variant="ghost"
                onClick={() => setBulkActionTarget("restore")}
                disabled={Boolean(busy)}
              >
                Bulk Restore
              </SkeuoButton>
              <SkeuoButton
                variant="ghost"
                className="border-status-error/40 text-status-error hover:bg-status-error/10"
                onClick={() => setBulkActionTarget("delete")}
                disabled={Boolean(busy)}
              >
                Bulk Delete
              </SkeuoButton>
            </div>
          </div>
        )}

        <AdminLoading loading={tenants.loading} />

        {/* Tenants Table */}
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh className="w-10">
              <input
                type="checkbox"
                aria-label="Select all visible tenants"
                checked={rows.length > 0 && selectedIds.size === rows.length}
                onChange={toggleSelectAll}
              />
            </SkeuoTh>
            <SkeuoTh>Tenant</SkeuoTh>
            <SkeuoTh>Tier / Plan</SkeuoTh>
            <SkeuoTh>Wallet</SkeuoTh>
            <SkeuoTh>Members</SkeuoTh>
            <SkeuoTh>Numbers</SkeuoTh>
            <SkeuoTh>Status</SkeuoTh>
            <SkeuoTh>Created</SkeuoTh>
            <SkeuoTh className="text-right">Actions</SkeuoTh>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {rows.map((t) => {
              const isDeleted = Boolean(t.deletedAt) || t.status === "cancelled" || t.status === "deleted";
              const isSelected = selectedIds.has(t.tenantId);

              return (
                <SkeuoTableRow
                  key={t.tenantId}
                  className={isDeleted ? "opacity-60 bg-surface-panel-raised/30" : undefined}
                >
                  <SkeuoTd>
                    <input
                      type="checkbox"
                      aria-label={`Select tenant ${t.name}`}
                      checked={isSelected}
                      onChange={() => toggleSelect(t.tenantId)}
                    />
                  </SkeuoTd>
                  <SkeuoTd>
                    <div className="flex items-center gap-2">
                      <Link
                        href={`/dev/admin/tenants/${t.tenantId}`}
                        className="font-medium text-text hover:underline"
                      >
                        {t.name}
                      </Link>
                      {t.isInventory && <SkeuoBadge tone="muted">Inventory</SkeuoBadge>}
                      {isDeleted && <SkeuoBadge tone="danger">Deleted</SkeuoBadge>}
                    </div>
                    <p className="font-mono text-[10px] text-text-subtle">{t.tenantId}</p>
                  </SkeuoTd>

                  {/* Plan Switcher */}
                  <SkeuoTd>
                    <select
                      value={t.plan || "starter"}
                      disabled={isDeleted || busy === `plan:${t.tenantId}`}
                      onChange={(e) => quickChangePlan(t, e.target.value)}
                      className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-2 py-1 text-xs text-text transition hover:border-surface-border"
                      title="Quick change plan"
                    >
                      {PLANS.filter(Boolean).map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </SkeuoTd>

                  {/* Wallet Balance & Quick Adjust */}
                  <SkeuoTd>
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-xs font-semibold text-text">
                        ${Number(t.walletBalanceUsd ?? 0).toFixed(2)}
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          setWalletTarget(t);
                          setWalletAmount("10");
                          setWalletMode("credit");
                          setWalletNote("");
                        }}
                        className="rounded px-1 text-[11px] font-bold text-primary hover:bg-primary/10"
                        title="Adjust wallet balance"
                      >
                        +$
                      </button>
                    </div>
                  </SkeuoTd>

                  <SkeuoTd className="font-mono text-xs">{t.memberCount ?? 0}</SkeuoTd>
                  <SkeuoTd className="font-mono text-xs">{t.numberCount ?? 0}</SkeuoTd>

                  {/* Status Switcher */}
                  <SkeuoTd>
                    <div className="flex items-center gap-1.5">
                      <SkeuoBadge tone={STATUS_TONE[t.status] ?? "muted"}>{t.status}</SkeuoBadge>
                      <select
                        value={t.status ?? "active"}
                        disabled={isDeleted || busy === `status:${t.tenantId}`}
                        onChange={(e) => onStatusDropdownChange(t, e.target.value)}
                        className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-1.5 py-0.5 text-[11px] text-text"
                        title="Change tenant status"
                      >
                        {STATUSES.filter(Boolean).map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </select>
                    </div>
                  </SkeuoTd>

                  <SkeuoTd className="text-xs text-text-muted">{formatWhen(t.createdAt)}</SkeuoTd>

                  {/* Multi-action buttons on each row */}
                  <SkeuoTd className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Link href={`/dev/admin/tenants/${t.tenantId}`}>
                        <SkeuoButton variant="ghost">Open</SkeuoButton>
                      </Link>

                      <SkeuoButton
                        variant="ghost"
                        disabled={Boolean(busy) || isDeleted}
                        onClick={() => setImpersonateTarget(t)}
                        title="Impersonate customer console"
                      >
                        Console
                      </SkeuoButton>

                      {isDeleted ? (
                        <SkeuoButton
                          variant="ghost"
                          className="border-status-success/40 text-status-success hover:bg-status-success/10"
                          disabled={Boolean(busy)}
                          onClick={() => restoreTenant(t)}
                          title="Restore soft-deleted tenant"
                        >
                          Restore
                        </SkeuoButton>
                      ) : (
                        <SkeuoButton
                          variant="ghost"
                          className="border-status-error/40 text-status-error hover:bg-status-error/10"
                          disabled={Boolean(busy)}
                          onClick={() => {
                            setDeleteTarget(t);
                            setDeleteReleaseNumbers(true);
                            setDeleteRevokeSessions(true);
                            setDeleteForce(false);
                          }}
                          title="Delete tenant"
                        >
                          Delete
                        </SkeuoButton>
                      )}
                    </div>
                  </SkeuoTd>
                </SkeuoTableRow>
              );
            })}
            {rows.length === 0 && !tenants.loading && (
              <SkeuoTableRow>
                <SkeuoTd colSpan={9} className="py-6 text-center text-text-muted">
                  No tenants match the current filters.
                </SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>

        {/* Pagination */}
        <div className="mt-4 flex items-center justify-between text-xs text-text-muted border-t border-surface-border-subtle pt-3">
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

      {/* Modal: Create Tenant */}
      {createOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-tenant-title"
        >
          <div className="w-full max-w-md rounded-xl border border-surface-border bg-surface-panel p-5 shadow-lg">
            <h3 id="create-tenant-title" className="text-sm font-semibold text-text">
              Add Tenant Workspace
            </h3>
            <p className="mt-1 text-xs text-text-muted">
              Creates a customer workspace initialized with an empty USD wallet.
            </p>
            <label className="mt-4 block text-xs font-medium text-text">
              Workspace Name
              <SkeuoInput
                className="mt-1 w-full"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Acme Voice Corp"
              />
            </label>
            <label className="mt-3 block text-xs font-medium text-text">
              Initial Plan Tier
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
            <div className="mt-5 flex justify-end gap-2">
              <SkeuoButton variant="ghost" onClick={() => setCreateOpen(false)}>
                Cancel
              </SkeuoButton>
              <SkeuoButton
                variant="primary"
                disabled={!newName.trim() || busy === "create"}
                onClick={() => createTenant()}
              >
                {busy === "create" ? "Creating…" : "Create Workspace"}
              </SkeuoButton>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Delete Single Tenant */}
      <AdminConfirmDialog
        open={Boolean(deleteTarget)}
        title={`Delete workspace "${deleteTarget?.name}"?`}
        description="Soft-deletes this workspace. You can choose whether to release assigned phone numbers to platform inventory and revoke member sessions."
        tone="danger"
        confirmLabel="Delete workspace"
        statementPlaceholder="Reason for deleting this tenant (min 8 chars required for audit)"
        busy={Boolean(deleteTarget && busy.startsWith(`delete:${deleteTarget.tenantId}`))}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
      >
        <div className="space-y-2 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-2.5">
          <label className="flex items-center gap-2 cursor-pointer font-medium text-text">
            <input
              type="checkbox"
              checked={deleteReleaseNumbers}
              onChange={(e) => setDeleteReleaseNumbers(e.target.checked)}
            />
            Release assigned phone numbers back to Platform inventory
          </label>
          <label className="flex items-center gap-2 cursor-pointer font-medium text-text">
            <input
              type="checkbox"
              checked={deleteRevokeSessions}
              onChange={(e) => setDeleteRevokeSessions(e.target.checked)}
            />
            Revoke all member sessions immediately (force logout)
          </label>
          <label className="flex items-center gap-2 cursor-pointer text-text-muted">
            <input
              type="checkbox"
              checked={deleteForce}
              onChange={(e) => setDeleteForce(e.target.checked)}
            />
            Force delete even if active phone numbers cannot be released
          </label>
        </div>
      </AdminConfirmDialog>

      {/* Modal: Status Change */}
      <AdminConfirmDialog
        open={Boolean(statusTarget)}
        title={`Change status to "${statusTarget?.nextStatus}"?`}
        description={`Confirm lifecycle change for "${statusTarget?.tenant.name}".`}
        tone={
          statusTarget?.nextStatus === "cancelled" || statusTarget?.nextStatus === "suspended"
            ? "danger"
            : "default"
        }
        confirmLabel={`Set ${statusTarget?.nextStatus}`}
        statementPlaceholder="Why are you changing this tenant's lifecycle status? (min 8 chars)"
        busy={Boolean(statusTarget && busy.startsWith(`status:${statusTarget.tenant.tenantId}`))}
        onCancel={() => setStatusTarget(null)}
        onConfirm={confirmStatus}
      >
        {(statusTarget?.nextStatus === "suspended" || statusTarget?.nextStatus === "cancelled") && (
          <div className="space-y-2 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-2.5">
            <label className="flex items-center gap-2 cursor-pointer text-text">
              <input
                type="checkbox"
                checked={statusReleaseNumbers}
                onChange={(e) => setStatusReleaseNumbers(e.target.checked)}
              />
              Release all phone numbers to Platform inventory
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-text">
              <input
                type="checkbox"
                checked={statusRevokeSessions}
                onChange={(e) => setStatusRevokeSessions(e.target.checked)}
              />
              Revoke member refresh tokens (force logout)
            </label>
          </div>
        )}
      </AdminConfirmDialog>

      {/* Modal: Adjust Wallet */}
      {walletTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="wallet-adjust-title"
        >
          <div className="w-full max-w-md rounded-xl border border-surface-border bg-surface-panel p-5 shadow-lg">
            <h3 id="wallet-adjust-title" className="text-sm font-semibold text-text">
              Adjust Wallet · {walletTarget.name}
            </h3>
            <p className="mt-1 text-xs text-text-muted">
              Current balance:{" "}
              <strong className="text-text font-mono">
                ${Number(walletTarget.walletBalanceUsd ?? 0).toFixed(2)} USD
              </strong>
            </p>

            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={() => setWalletMode("credit")}
                className={`flex-1 rounded-skeuo-sm border py-1.5 text-xs font-semibold ${
                  walletMode === "credit"
                    ? "border-status-success bg-status-success/15 text-status-success"
                    : "border-surface-border bg-surface-panel-raised text-text-muted"
                }`}
              >
                + Credit (Add Funds)
              </button>
              <button
                type="button"
                onClick={() => setWalletMode("debit")}
                className={`flex-1 rounded-skeuo-sm border py-1.5 text-xs font-semibold ${
                  walletMode === "debit"
                    ? "border-status-error bg-status-error/15 text-status-error"
                    : "border-surface-border bg-surface-panel-raised text-text-muted"
                }`}
              >
                - Debit (Deduct Funds)
              </button>
            </div>

            <label className="mt-3 block text-xs font-medium text-text">
              Amount (USD)
              <SkeuoInput
                type="number"
                min="0.01"
                step="0.01"
                value={walletAmount}
                onChange={(e) => setWalletAmount(e.target.value)}
                className="mt-1 w-full font-mono text-sm"
              />
            </label>

            {/* Quick amount chips */}
            <div className="mt-2 flex gap-1.5 text-xs">
              {["5", "10", "25", "50", "100"].map((amt) => (
                <button
                  key={amt}
                  type="button"
                  onClick={() => setWalletAmount(amt)}
                  className="rounded border border-surface-border-subtle bg-surface-panel-raised px-2 py-0.5 text-text hover:bg-surface-panel"
                >
                  ${amt}
                </button>
              ))}
            </div>

            <label className="mt-3 block text-xs font-medium text-text">
              Admin Statement (required, min 8 chars)
              <textarea
                value={walletNote}
                onChange={(e) => setWalletNote(e.target.value)}
                placeholder="Reason for manual wallet adjustment"
                rows={2}
                className="mt-1 w-full rounded-skeuo-sm border border-surface-border bg-surface-panel-raised px-2 py-1.5 text-xs text-text"
              />
            </label>

            <div className="mt-5 flex justify-end gap-2">
              <SkeuoButton variant="ghost" onClick={() => setWalletTarget(null)}>
                Cancel
              </SkeuoButton>
              <SkeuoButton
                variant="primary"
                disabled={
                  Boolean(busy) ||
                  !walletAmount ||
                  Number(walletAmount) <= 0 ||
                  walletNote.trim().length < 8
                }
                onClick={confirmWalletAdjust}
              >
                {busy ? "Adjusting…" : `Confirm ${walletMode === "credit" ? "Credit" : "Debit"}`}
              </SkeuoButton>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Impersonate Customer Session */}
      <AdminConfirmDialog
        open={Boolean(impersonateTarget)}
        title={`Open Console as "${impersonateTarget?.name}"?`}
        description="Starts a secure 30-minute support session in the customer console. Action is logged in the permanent audit trail."
        confirmLabel="Launch Session"
        statementPlaceholder="Support reason for impersonation (min 8 chars)"
        busy={Boolean(impersonateTarget && busy.startsWith(`impersonate:${impersonateTarget.tenantId}`))}
        onCancel={() => setImpersonateTarget(null)}
        onConfirm={confirmImpersonate}
      />

      {/* Modal: Bulk Actions */}
      <AdminConfirmDialog
        open={Boolean(bulkActionTarget)}
        title={`Execute Bulk ${bulkActionTarget?.replace("_", " ").toUpperCase()}?`}
        description={`This action will be applied simultaneously across ${selectedIds.size} selected workspace(s).`}
        tone={bulkActionTarget === "delete" || bulkActionTarget === "suspend" ? "danger" : "default"}
        confirmLabel={`Execute on ${selectedIds.size} tenants`}
        statementPlaceholder={`Admin rationale for bulk ${bulkActionTarget} (min 4 chars)`}
        minLength={4}
        busy={busy === "bulk"}
        onCancel={() => setBulkActionTarget(null)}
        onConfirm={confirmBulkAction}
      >
        {bulkActionTarget === "delete" && (
          <div className="space-y-2 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-2.5">
            <label className="flex items-center gap-2 cursor-pointer font-medium text-text">
              <input
                type="checkbox"
                checked={bulkReleaseNumbers}
                onChange={(e) => setBulkReleaseNumbers(e.target.checked)}
              />
              Release active numbers across all selected tenants
            </label>
            <label className="flex items-center gap-2 cursor-pointer font-medium text-text">
              <input
                type="checkbox"
                checked={bulkRevokeSessions}
                onChange={(e) => setBulkRevokeSessions(e.target.checked)}
              />
              Revoke active sessions for all members
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-text-muted">
              <input
                type="checkbox"
                checked={bulkForce}
                onChange={(e) => setBulkForce(e.target.checked)}
              />
              Force delete even if active numbers remain
            </label>
          </div>
        )}
        {bulkActionTarget === "suspend" && (
          <div className="space-y-2 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-2.5">
            <label className="flex items-center gap-2 cursor-pointer text-text">
              <input
                type="checkbox"
                checked={bulkRevokeSessions}
                onChange={(e) => setBulkRevokeSessions(e.target.checked)}
              />
              Revoke active member sessions
            </label>
          </div>
        )}
        {bulkActionTarget === "change_plan" && (
          <p className="font-semibold text-text">
            All selected workspaces will be migrated to the <u>{bulkPlan}</u> tier.
          </p>
        )}
      </AdminConfirmDialog>
    </div>
  );
}
