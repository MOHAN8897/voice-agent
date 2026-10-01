"use client";

import { useState } from "react";
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
  createdAt: string | null;
  walletBalanceUsd?: number;
  walletCurrency?: string;
};

type TenantDetail = {
  tenant: Record<string, unknown>;
  wallet?: {
    balanceUsd?: number;
    balanceInr?: number;
    currency?: string;
    updatedAt?: string | null;
  } | null;
  agents: Array<{ agentId?: string; agent_id?: string; name: string; status?: string }>;
  numbers: Array<{ id?: string; e164: string; agentId?: string | null; status?: string }>;
  users?: Array<{ userId: string; email?: string; role: string; fullName?: string }>;
  members?: Array<{ userId: string; email?: string; role: string }>;
  recentCalls?: Array<{ callId: string; startedAt?: string | null; status?: string | null }>;
};

const STATUSES = ["active", "suspended", "past_due", "cancelled"];

export default function AdminTenantsPage() {
  const [query, setQuery] = useState("");
  const tenants = useAdminResource<{ tenants: Tenant[] }>(
    `/api/dev/admin/tenants?q=${encodeURIComponent(query)}`,
    [query]
  );
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<TenantDetail | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");

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

  function patch(t: Tenant, body: Record<string, unknown>) {
    return run(`patch:${t.tenantId}`, async () => {
      await adminAction(`/api/dev/admin/tenants/${t.tenantId}`, { method: "PATCH", body });
      await tenants.reload();
    });
  }

  async function openDetail(tenantId: string) {
    await run(`detail:${tenantId}`, async () => {
      const { devFetch } = await import("@/lib/useAdminResource");
      setDetail((await devFetch(`/api/dev/admin/tenants/${tenantId}`)) as TenantDetail);
    });
  }

  function createTenant() {
    return run("create", async () => {
      await adminAction("/api/dev/admin/tenants", {
        method: "POST",
        body: { name: newName.trim(), status: "active" },
      });
      setNewName("");
      setCreateOpen(false);
      await tenants.reload();
    });
  }

  function deleteTenant(t: Tenant) {
    if (
      !window.confirm(
        `Delete tenant “${t.name}”? Soft-deletes the workspace (status cancelled). Numbers must be released first unless you force.`
      )
    ) {
      return;
    }
    return run(`delete:${t.tenantId}`, async () => {
      try {
        await adminAction(`/api/dev/admin/tenants/${t.tenantId}`, { method: "DELETE" });
      } catch (e) {
        const msg = e instanceof Error ? e.message : "";
        if (/active number/i.test(msg) && window.confirm(`${msg}\n\nForce delete anyway?`)) {
          await adminAction(`/api/dev/admin/tenants/${t.tenantId}?force=true`, { method: "DELETE" });
        } else {
          throw e;
        }
      }
      if (detail?.tenant?.tenantId === t.tenantId) setDetail(null);
      await tenants.reload();
    });
  }

  const members = detail?.users?.length ? detail.users : detail?.members ?? [];

  return (
    <div className="space-y-6 p-6">
      <AdminPageHeader
        title="Tenants"
        description="One customer workspace each. Same tenant ids appear on Numbers and Wallets. Data is stored in Postgres and survives API restarts."
      />

      <AdminError error={error} />
      <AdminError error={tenants.error} />

      <DevCard title="All tenants">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <SkeuoInput
            placeholder="Search tenants by name"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search tenants"
            className="max-w-sm"
          />
          <SkeuoButton variant="primary" onClick={() => setCreateOpen(true)}>
            Add tenant
          </SkeuoButton>
        </div>
        <AdminLoading loading={tenants.loading} />
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh>Name</SkeuoTh>
            <SkeuoTh>Wallet</SkeuoTh>
            <SkeuoTh>Status</SkeuoTh>
            <SkeuoTh>Created</SkeuoTh>
            <SkeuoTh className="text-right">Actions</SkeuoTh>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {(tenants.data?.tenants ?? []).map((t) => (
              <SkeuoTableRow key={t.tenantId}>
                <SkeuoTd>
                  <button
                    type="button"
                    className="text-left font-medium hover:underline"
                    onClick={() => openDetail(t.tenantId)}
                  >
                    {t.name}
                  </button>
                  <p className="font-mono text-[10px] text-text-subtle">{t.tenantId}</p>
                </SkeuoTd>
                <SkeuoTd className="font-mono text-xs">
                  ${Number(t.walletBalanceUsd ?? 0).toFixed(2)}
                </SkeuoTd>
                <SkeuoTd>
                  <select
                    defaultValue={t.status ?? "active"}
                    onChange={(e) => patch(t, { status: e.target.value })}
                    disabled={busy === `patch:${t.tenantId}`}
                    aria-label={`Status for ${t.name}`}
                    className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-2 py-1 text-xs text-text"
                  >
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </SkeuoTd>
                <SkeuoTd className="text-xs text-text-muted">{formatWhen(t.createdAt)}</SkeuoTd>
                <SkeuoTd className="text-right space-x-2">
                  <SkeuoButton
                    variant="ghost"
                    disabled={busy === `detail:${t.tenantId}`}
                    onClick={() => openDetail(t.tenantId)}
                  >
                    Inspect
                  </SkeuoButton>
                  <SkeuoButton
                    variant="ghost"
                    disabled={busy === `delete:${t.tenantId}`}
                    onClick={() => deleteTenant(t)}
                  >
                    Delete
                  </SkeuoButton>
                </SkeuoTd>
              </SkeuoTableRow>
            ))}
            {(tenants.data?.tenants ?? []).length === 0 && !tenants.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-text-muted">No tenants match.</SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>
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
              Creates a workspace with an empty USD wallet (persisted in the database).
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

      {detail && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="inspect-tenant-title"
        >
          <div className="relative max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-surface-border bg-surface-panel p-5 shadow-lg">
            <button
              type="button"
              className="absolute right-4 top-4 text-xs text-text-muted hover:text-text"
              onClick={() => setDetail(null)}
            >
              Close
            </button>
            <h3 id="inspect-tenant-title" className="pr-12 text-sm font-semibold text-text">
              {String(detail.tenant.name ?? "Workspace")}
            </h3>
            <p className="mt-1 font-mono text-[10px] text-text-subtle">
              {String(detail.tenant.tenantId ?? "")}
            </p>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-surface-border-subtle p-3">
                <h4 className="text-xs font-semibold text-text">Meta</h4>
                <dl className="mt-2 space-y-1 text-xs text-text-muted">
                  <div className="flex justify-between gap-2">
                    <dt>Status</dt>
                    <dd>
                      <SkeuoBadge>{String(detail.tenant.status ?? "—")}</SkeuoBadge>
                    </dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt>Created</dt>
                    <dd>{formatWhen(String(detail.tenant.createdAt ?? "") || null)}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt>Billing source</dt>
                    <dd>{String(detail.tenant.billingSource ?? "—")}</dd>
                  </div>
                </dl>
              </div>
              <div className="rounded-lg border border-surface-border-subtle p-3">
                <h4 className="text-xs font-semibold text-text">Wallet</h4>
                {detail.wallet ? (
                  <dl className="mt-2 space-y-1 text-xs text-text-muted">
                    <div className="flex justify-between gap-2">
                      <dt>USD</dt>
                      <dd className="font-mono">${Number(detail.wallet.balanceUsd ?? 0).toFixed(2)}</dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt>Currency</dt>
                      <dd>{detail.wallet.currency || "USD"}</dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt>Updated</dt>
                      <dd>{formatWhen(detail.wallet.updatedAt ?? null)}</dd>
                    </div>
                  </dl>
                ) : (
                  <p className="mt-2 text-xs text-text-muted">No wallet row yet.</p>
                )}
              </div>
            </div>

            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <div>
                <h4 className="text-sm font-medium text-text">Agents</h4>
                {detail.agents?.length ? (
                  <ul className="mt-1 space-y-1 text-sm text-text-muted">
                    {detail.agents.map((a) => (
                      <li key={a.agentId || a.agent_id}>
                        {a.name}
                        {a.status ? ` · ${a.status}` : ""}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-sm text-text-muted">None.</p>
                )}
              </div>
              <div>
                <h4 className="text-sm font-medium text-text">Phone numbers</h4>
                {detail.numbers?.length ? (
                  <ul className="mt-1 space-y-1 font-mono text-sm text-text-muted">
                    {detail.numbers.map((n) => (
                      <li key={n.id || n.e164}>{n.e164}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-sm text-text-muted">None.</p>
                )}
              </div>
              <div>
                <h4 className="text-sm font-medium text-text">Members</h4>
                {members.length ? (
                  <ul className="mt-1 space-y-1 text-sm text-text-muted">
                    {members.map((m) => (
                      <li key={m.userId}>
                        {m.email || m.userId} · {m.role}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-sm text-text-muted">
                    None. A tenant with no members cannot be signed into.
                  </p>
                )}
              </div>
            </div>

            {!!detail.recentCalls?.length && (
              <div className="mt-4">
                <h4 className="text-sm font-medium text-text">Recent calls</h4>
                <ul className="mt-1 space-y-1 font-mono text-xs text-text-muted">
                  {detail.recentCalls.map((c) => (
                    <li key={c.callId}>
                      {c.callId.slice(0, 8)}… · {formatWhen(c.startedAt ?? null)}
                      {c.status ? ` · ${c.status}` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
