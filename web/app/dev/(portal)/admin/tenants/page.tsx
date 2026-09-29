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
  plan: string | null;
  status: string;
  createdAt: string | null;
};

type TenantDetail = {
  tenant: Record<string, unknown>;
  agents: Array<{ agent_id: string; name: string }>;
  numbers: Array<{ e164: string }>;
  members?: Array<{ userId: string; role: string }>;
};

const PLANS = ["free", "starter", "growth", "business", "enterprise"];
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

  return (
    <div className="space-y-6 p-6">
      <AdminPageHeader
        title="Tenants"
        description="Each tenant is one customer workspace. Plan and status changes apply to the whole workspace."
      />

      <AdminError error={error} />
      <AdminError error={tenants.error} />

      <DevCard title="All tenants">
        <div className="mb-3">
          <SkeuoInput
            placeholder="Search tenants by name"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search tenants"
            className="max-w-sm"
          />
        </div>
        <AdminLoading loading={tenants.loading} />
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh>Name</SkeuoTh>
            <SkeuoTh>Plan</SkeuoTh>
            <SkeuoTh>Status</SkeuoTh>
            <SkeuoTh>Created</SkeuoTh>
            <SkeuoTh className="text-right">Change</SkeuoTh>
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
                <SkeuoTd>
                  <select
                    defaultValue={t.plan ?? ""}
                    onChange={(e) => patch(t, { plan: e.target.value || null })}
                    disabled={busy === `patch:${t.tenantId}`}
                    aria-label={`Plan for ${t.name}`}
                    className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-2 py-1 text-xs text-text"
                  >
                    <option value="">unset</option>
                    {PLANS.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
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
                <SkeuoTd className="text-right">
                  <SkeuoButton
                    variant="ghost"
                    disabled={busy === `detail:${t.tenantId}`}
                    onClick={() => openDetail(t.tenantId)}
                  >
                    Inspect
                  </SkeuoButton>
                </SkeuoTd>
              </SkeuoTableRow>
            ))}
            {(tenants.data?.tenants ?? []).length === 0 && !tenants.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-text-muted">
                  No tenants match.
                </SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>
      </DevCard>

      {detail && (
        <DevCard title={`Workspace: ${String(detail.tenant.name ?? "")}`}>
          <button
            type="button"
            className="absolute right-4 top-4 text-xs text-text-muted hover:text-text"
            onClick={() => setDetail(null)}
          >
            Close
          </button>
          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <h4 className="text-sm font-medium text-text">Agents</h4>
              {detail.agents?.length ? (
                <ul className="mt-1 space-y-1 text-sm text-text-muted">
                  {detail.agents.map((a) => (
                    <li key={a.agent_id}>{a.name}</li>
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
                    <li key={n.e164}>{n.e164}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-sm text-text-muted">None.</p>
              )}
            </div>
            <div>
              <h4 className="text-sm font-medium text-text">Members</h4>
              {detail.members?.length ? (
                <ul className="mt-1 space-y-1 text-sm text-text-muted">
                  {detail.members.map((m) => (
                    <li key={m.userId}>{m.role}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-sm text-text-muted">
                  None. A tenant with no members cannot be signed into.
                </p>
              )}
            </div>
          </div>
        </DevCard>
      )}
    </div>
  );
}
