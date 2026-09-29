"use client";

import { DevCard } from "@/components/dev/DevCard";
import {
  AdminError,
  AdminLoading,
  AdminPageHeader,
  AdminStat,
} from "@/components/admin/AdminNav";
import { SkeuoBadge, SkeuoTable, SkeuoTableBody, SkeuoTableHead, SkeuoTableRow, SkeuoTd, SkeuoTh } from "@/components/ui/skeuo";
import {
  adminAction,
  formatDay,
  formatMinutes,
  formatUsd,
  formatWhen,
  useAdminResource,
} from "@/lib/useAdminResource";
import { useState } from "react";

type Analytics = {
  windowDays: number;
  since: string;
  totals: {
    calls: number;
    seconds: number;
    missedCalls: number;
    tenants: number;
    tenantsActive: number;
    users: number;
    activeNumbers: number;
    failedPurchases: number;
    walletBalanceCents: number;
  };
  callsByDay: Array<{ date: string; calls: number; seconds: number }>;
  callsByStatus: Record<string, number>;
  callsByDirection: Record<string, number>;
  topUpsByDay: Array<{ date: string; cents: number; inrPaise: number }>;
  topTenantsByCalls: Array<{ name: string; calls: number }>;
};

type Purchase = {
  purchaseId: string;
  tenantId: string;
  e164: string;
  status: string;
  createdAt: string;
};

const WINDOWS = [7, 30, 90] as const;

/** Plain CSS bar chart: no chart dependency, and it cannot mis-render an empty set. */
function CallsByDay({ series }: { series: Analytics["callsByDay"] }) {
  const max = series.reduce((m, d) => Math.max(m, d.calls), 0);
  if (!series.length || max === 0) {
    return <p className="py-6 text-center text-sm text-text-muted">No calls in this window.</p>;
  }
  return (
    <div>
      <div className="flex h-40 items-end gap-1" role="img" aria-label="Calls per day">
        {series.map((d) => (
          <div key={d.date} className="group relative flex-1" title={`${d.date}: ${d.calls} calls, ${formatMinutes(d.seconds)}`}>
            <div
              className="w-full rounded-t bg-accent-primary/70 transition-colors group-hover:bg-accent-primary"
              style={{ height: `${Math.max(3, (d.calls / max) * 100)}%` }}
            />
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-between text-[10px] text-text-subtle">
        <span>{formatDay(series[0].date)}</span>
        <span>
          peak {max}/day
        </span>
        <span>{formatDay(series[series.length - 1].date)}</span>
      </div>
    </div>
  );
}

export default function AdminOverviewPage() {
  const [days, setDays] = useState<number>(30);
  const { data, error, loading, reload } = useAdminResource<Analytics>(
    `/api/dev/admin/analytics?days=${days}`,
    [days]
  );
  const purchases = useAdminResource<{ purchases: Purchase[] }>("/api/dev/admin/purchases");
  const [busy, setBusy] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const failed = (purchases.data?.purchases ?? []).filter((p) => p.status === "failed");

  async function retry(purchaseId: string) {
    setBusy(purchaseId);
    setActionError(null);
    try {
      await adminAction(`/api/dev/admin/purchases/${purchaseId}/retry-provision`);
      await purchases.reload();
      await reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Retry failed");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="space-y-6 p-6">
      <AdminPageHeader
        title="SaaS overview"
        description="Live operational numbers, aggregated from the real call, wallet, and tenant tables."
        actions={
          <div className="flex items-center gap-1">
            {WINDOWS.map((w) => (
              <button
                key={w}
                type="button"
                onClick={() => setDays(w)}
                className={`rounded-skeuo-sm px-3 py-1 text-xs font-medium transition-colors ${
                  days === w
                    ? "bg-accent-primary text-white"
                    : "bg-surface-panel-raised text-text-muted hover:text-text"
                }`}
              >
                {w}d
              </button>
            ))}
          </div>
        }
      />

      <AdminError error={error} />
      <AdminError error={actionError} />
      <AdminLoading loading={loading} />

      {data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <AdminStat
              label={`Calls (${days}d)`}
              value={data.totals.calls.toLocaleString()}
              hint={formatMinutes(data.totals.seconds)}
            />
            <AdminStat
              label="Talk time"
              value={formatMinutes(data.totals.seconds)}
              hint={`avg ${data.totals.calls ? Math.round(data.totals.seconds / data.totals.calls) : 0}s per call`}
            />
            <AdminStat
              label="Missed calls"
              value={data.totals.missedCalls}
              tone={data.totals.missedCalls > 0 ? "warn" : "good"}
              hint="from call attempts"
            />
            <AdminStat
              label="Wallet balance"
              value={formatUsd(data.totals.walletBalanceCents)}
              hint="across all tenants"
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <AdminStat
              label="Tenants"
              value={data.totals.tenants}
              hint={`${data.totals.tenantsActive} active`}
            />
            <AdminStat label="Users" value={data.totals.users} hint="not deleted" />
            <AdminStat label="Active numbers" value={data.totals.activeNumbers} hint="not released" />
            <AdminStat
              label="Failed purchases"
              value={data.totals.failedPurchases}
              tone={data.totals.failedPurchases > 0 ? "warn" : "good"}
              hint="need retry or refund"
            />
          </div>

          <DevCard title={`Calls per day (${days} days)`} delayMs={60}>
            <CallsByDay series={data.callsByDay} />
          </DevCard>

          <div className="grid gap-4 lg:grid-cols-2">
            <DevCard title="Calls by status" delayMs={80}>
              <SkeuoTable>
                <SkeuoTableHead>
                  <SkeuoTh>Status</SkeuoTh>
                  <SkeuoTh className="text-right">Calls</SkeuoTh>
                </SkeuoTableHead>
                <SkeuoTableBody>
                  {Object.entries(data.callsByStatus)
                    .sort((a, b) => b[1] - a[1])
                    .map(([status, count]) => (
                      <SkeuoTableRow key={status}>
                        <SkeuoTd>
                          <SkeuoBadge tone={status === "missed" ? "warning" : "muted"}>{status}</SkeuoBadge>
                        </SkeuoTd>
                        <SkeuoTd className="text-right font-mono">{count}</SkeuoTd>
                      </SkeuoTableRow>
                    ))}
                  {Object.keys(data.callsByStatus).length === 0 && (
                    <SkeuoTableRow>
                      <SkeuoTd className="text-text-muted">
                        No calls in this window.
                      </SkeuoTd>
                    </SkeuoTableRow>
                  )}
                </SkeuoTableBody>
              </SkeuoTable>
            </DevCard>

            <DevCard title="Busiest tenants" delayMs={100}>
              <SkeuoTable>
                <SkeuoTableHead>
                  <SkeuoTh>Tenant</SkeuoTh>
                  <SkeuoTh className="text-right">Calls</SkeuoTh>
                </SkeuoTableHead>
                <SkeuoTableBody>
                  {data.topTenantsByCalls.map((t) => (
                    <SkeuoTableRow key={t.name}>
                      <SkeuoTd>{t.name}</SkeuoTd>
                      <SkeuoTd className="text-right font-mono">{t.calls}</SkeuoTd>
                    </SkeuoTableRow>
                  ))}
                  {data.topTenantsByCalls.length === 0 && (
                    <SkeuoTableRow>
                      <SkeuoTd className="text-text-muted">
                        No calls in this window.
                      </SkeuoTd>
                    </SkeuoTableRow>
                  )}
                </SkeuoTableBody>
              </SkeuoTable>
            </DevCard>
          </div>
        </>
      )}

      <DevCard
        title="Failed number purchases"
        description="A purchase stuck in failed still holds a paid order — retry provisioning or refund it."
        delayMs={120}
      >
        <AdminError error={purchases.error} />
        {failed.length === 0 ? (
          <p className="text-sm text-text-muted">No failed purchases.</p>
        ) : (
          <SkeuoTable>
            <SkeuoTableHead>
              <SkeuoTh>Number</SkeuoTh>
              <SkeuoTh>Created</SkeuoTh>
              <SkeuoTh className="text-right">Action</SkeuoTh>
            </SkeuoTableHead>
            <SkeuoTableBody>
              {failed.map((p) => (
                <SkeuoTableRow key={p.purchaseId}>
                  <SkeuoTd className="font-mono">{p.e164}</SkeuoTd>
                  <SkeuoTd className="text-text-muted">{formatWhen(p.createdAt)}</SkeuoTd>
                  <SkeuoTd className="text-right">
                    <button
                      type="button"
                      disabled={busy === p.purchaseId}
                      onClick={() => retry(p.purchaseId)}
                      className="rounded-skeuo-sm bg-accent-primary px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                    >
                      {busy === p.purchaseId ? "Retrying…" : "Retry provisioning"}
                    </button>
                  </SkeuoTd>
                </SkeuoTableRow>
              ))}
            </SkeuoTableBody>
          </SkeuoTable>
        )}
      </DevCard>
    </div>
  );
}
