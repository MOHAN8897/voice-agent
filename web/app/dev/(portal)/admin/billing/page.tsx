"use client";

import { useState } from "react";
import { DevCard } from "@/components/dev/DevCard";
import {
  AdminError,
  AdminLoading,
  AdminPageHeader,
  AdminStat,
} from "@/components/admin/AdminNav";
import {
  SkeuoBadge,
  SkeuoButton,
  SkeuoTable,
  SkeuoTableBody,
  SkeuoTableHead,
  SkeuoTableRow,
  SkeuoTd,
  SkeuoTh,
} from "@/components/ui/skeuo";
import { adminAction, formatUsd, formatWhen, useAdminResource } from "@/lib/useAdminResource";

type Purchase = {
  purchaseId: string;
  tenantId: string;
  e164: string;
  status: string;
  createdAt: string;
};

const STATUSES = ["", "paid", "failed", "refunded", "pending"] as const;

const TONE: Record<string, "success" | "warning" | "danger" | "muted"> = {
  paid: "success",
  active: "success",
  failed: "danger",
  refunded: "muted",
  pending: "warning",
};

export default function AdminBillingPage() {
  const [status, setStatus] = useState<string>("");
  const purchases = useAdminResource<{ purchases: Purchase[] }>(
    `/api/dev/admin/purchases${status ? `?status=${status}` : ""}`,
    [status]
  );
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);

  const rows = purchases.data?.purchases ?? [];
  const failed = rows.filter((p) => p.status === "failed").length;

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

  function retry(id: string) {
    return run(`retry:${id}`, async () => {
      await adminAction(`/api/dev/admin/purchases/${id}/retry-provision`);
      await purchases.reload();
    });
  }

  function refund(id: string) {
    if (!window.confirm("Refund this purchase? Money is returned to the original payment method.")) {
      return;
    }
    return run(`refund:${id}`, async () => {
      await adminAction(`/api/dev/admin/purchases/${id}/refund`);
      await purchases.reload();
    });
  }

  return (
    <div className="space-y-6 p-6">
      <AdminPageHeader
        title="Billing"
        description="Number purchases and their provisioning state. A failed purchase has already taken the customer's money."
      />

      <AdminError error={error} />
      <AdminError error={purchases.error} />

      <div className="grid gap-4 sm:grid-cols-3">
        <AdminStat label="Purchases listed" value={rows.length} />
        <AdminStat label="Failed" value={failed} tone={failed > 0 ? "warn" : "good"} />
        <AdminStat label="Number rental" value={formatUsd(400)} hint="per number, per month" />
      </div>

      <DevCard title="Purchases">
        <div className="mb-3 flex flex-wrap gap-1">
          {STATUSES.map((s) => (
            <button
              key={s || "all"}
              type="button"
              onClick={() => setStatus(s)}
              className={`rounded-skeuo-sm px-3 py-1 text-xs font-medium transition-colors ${
                status === s
                  ? "bg-accent-primary text-white"
                  : "bg-surface-panel-raised text-text-muted hover:text-text"
              }`}
            >
              {s || "all"}
            </button>
          ))}
        </div>
        <AdminLoading loading={purchases.loading} />
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh>Number</SkeuoTh>
            <SkeuoTh>Tenant</SkeuoTh>
            <SkeuoTh>Status</SkeuoTh>
            <SkeuoTh>Created</SkeuoTh>
            <SkeuoTh className="text-right">Actions</SkeuoTh>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {rows.map((p) => (
              <SkeuoTableRow key={p.purchaseId}>
                <SkeuoTd className="font-mono">{p.e164}</SkeuoTd>
                <SkeuoTd className="font-mono text-xs text-text-subtle">
                  {p.tenantId.slice(0, 8)}
                </SkeuoTd>
                <SkeuoTd>
                  <SkeuoBadge tone={TONE[p.status] ?? "muted"}>{p.status}</SkeuoBadge>
                </SkeuoTd>
                <SkeuoTd className="text-xs text-text-muted">{formatWhen(p.createdAt)}</SkeuoTd>
                <SkeuoTd className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    {p.status === "failed" && (
                      <SkeuoButton
                        variant="ghost"
                        disabled={busy === `retry:${p.purchaseId}`}
                        onClick={() => retry(p.purchaseId)}
                      >
                        Retry
                      </SkeuoButton>
                    )}
                    {p.status !== "refunded" && (
                      <SkeuoButton
                        variant="ghost"
                        disabled={busy === `refund:${p.purchaseId}`}
                        onClick={() => refund(p.purchaseId)}
                      >
                        Refund
                      </SkeuoButton>
                    )}
                  </div>
                </SkeuoTd>
              </SkeuoTableRow>
            ))}
            {rows.length === 0 && !purchases.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-text-muted">
                  No purchases with this status.
                </SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>
      </DevCard>
    </div>
  );
}
