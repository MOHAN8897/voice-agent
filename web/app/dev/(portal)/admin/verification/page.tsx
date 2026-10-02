"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
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

type Verification = {
  userId: string;
  email?: string | null;
  fullName?: string | null;
  tenantId?: string;
  status: string;
  approved: boolean;
  verifiedAt?: string | null;
  decidedAt?: string | null;
  sessionId?: string | null;
  updatedAt?: string | null;
  decision?: {
    source?: string;
    actor?: string;
    reason?: string | null;
    at?: string;
  } | null;
};

type KycList = {
  configured: boolean;
  workflowId?: string | null;
  gatePurchases: boolean;
  verifications: Verification[];
};

const STATUS_TONE: Record<string, "success" | "warning" | "danger" | "muted" | "info"> = {
  Approved: "success",
  Declined: "danger",
  "In Review": "warning",
  "In Progress": "info",
  "Awaiting User": "info",
  "Not Started": "muted",
  Abandoned: "muted",
  Expired: "muted",
  "Kyc Expired": "danger",
  Resubmitted: "warning",
};

export default function AdminVerificationPage() {
  const kyc = useAdminResource<KycList>("/api/dev/admin/kyc");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<{ v: Verification; status: string } | null>(null);

  const rows = useMemo(() => {
    const all = kyc.data?.verifications ?? [];
    return all.filter((v) => {
      if (statusFilter && v.status !== statusFilter) return false;
      if (!query.trim()) return true;
      const q = query.trim().toLowerCase();
      return `${v.email ?? ""} ${v.fullName ?? ""} ${v.userId} ${v.status}`.toLowerCase().includes(q);
    });
  }, [kyc.data, query, statusFilter]);

  const approved = (kyc.data?.verifications ?? []).filter((v) => v.approved).length;
  const inReview = (kyc.data?.verifications ?? []).filter((v) =>
    ["In Review", "In Progress", "Awaiting User"].includes(v.status)
  ).length;
  const declined = (kyc.data?.verifications ?? []).filter((v) => v.status === "Declined").length;

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

  function askStatus(v: Verification, status: string) {
    setPending({ v, status });
  }

  function confirmStatus(statement: string) {
    if (!pending) return;
    const { v, status } = pending;
    return run(`${status}:${v.userId}`, async () => {
      await adminAction(`/api/dev/admin/kyc/${v.userId}/status`, {
        method: "POST",
        body: { status, reason: statement },
      });
      setPending(null);
      await kyc.reload();
    });
  }

  return (
    <div className="space-y-6 p-6" data-testid="admin-verification-page">
      <AdminPageHeader
        title="Identity verification"
        description="Didit KYC for English-market buyers. Manual Approve / Decline requires a written statement and is stored on the verification decision + admin audit log."
        actions={
          <SkeuoButton type="button" onClick={() => kyc.reload()} disabled={Boolean(busy)}>
            Refresh
          </SkeuoButton>
        }
      />

      <AdminError error={error || kyc.error} />
      <AdminLoading loading={kyc.loading && !kyc.data} />

      {kyc.data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <AdminStat
              label="Didit"
              value={kyc.data.configured ? "Configured" : "Missing keys"}
              tone={kyc.data.configured ? "good" : "warn"}
              hint={kyc.data.workflowId ? `workflow ${kyc.data.workflowId.slice(0, 8)}…` : "no workflow"}
            />
            <AdminStat label="Approved" value={approved} tone="good" />
            <AdminStat label="Pending / in review" value={inReview} tone={inReview ? "warn" : "default"} />
            <AdminStat label="Declined" value={declined} tone={declined ? "warn" : "default"} />
          </div>

          <DevCard
            title="Manual overrides"
            description="Pending reviews that stall (missed webhook, false decline) must be resolved with an explicit admin statement. Didit remains source of truth until you override."
          >
            <p className="text-xs text-text-muted">
              Purchase gate: {kyc.data.gatePurchases ? "on" : "off"} · Click Approve / Decline on a row to
              open the confirmation dialog.
            </p>
          </DevCard>

          <DevCard title="Verifications">
            <div className="mb-4 flex flex-wrap gap-2">
              <SkeuoInput
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search email, name, user id…"
                className="min-w-[220px] flex-1"
                data-testid="kyc-search"
              />
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="rounded-skeuo-sm border border-surface-border bg-surface-panel px-3 py-2 text-sm"
                data-testid="kyc-status-filter"
              >
                <option value="">All statuses</option>
                {[
                  "Approved",
                  "Declined",
                  "In Review",
                  "In Progress",
                  "Awaiting User",
                  "Not Started",
                  "Abandoned",
                  "Expired",
                  "Kyc Expired",
                ].map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>

            {rows.length === 0 ? (
              <p className="py-8 text-center text-sm text-text-muted" data-testid="kyc-empty">
                No verification sessions yet. A row appears when a customer starts Didit from Phone numbers or Settings.
              </p>
            ) : (
              <SkeuoTable>
                <SkeuoTableHead>
                  <SkeuoTableRow>
                    <SkeuoTh>User</SkeuoTh>
                    <SkeuoTh>Status</SkeuoTh>
                    <SkeuoTh>Last decision</SkeuoTh>
                    <SkeuoTh>Updated</SkeuoTh>
                    <SkeuoTh>Actions</SkeuoTh>
                  </SkeuoTableRow>
                </SkeuoTableHead>
                <SkeuoTableBody>
                  {rows.map((v) => (
                    <SkeuoTableRow key={v.userId} data-testid={`kyc-row-${v.userId}`}>
                      <SkeuoTd>
                        <div className="font-medium text-text">{v.email || v.userId}</div>
                        <div className="text-xs text-text-muted">{v.fullName || "—"}</div>
                        {v.tenantId ? (
                          <Link
                            href={`/dev/admin/tenants/${v.tenantId}`}
                            className="mt-0.5 block font-mono text-[10px] text-accent underline"
                          >
                            Tenant {v.tenantId.slice(0, 8)}…
                          </Link>
                        ) : null}
                      </SkeuoTd>
                      <SkeuoTd>
                        <SkeuoBadge tone={STATUS_TONE[v.status] || "muted"}>{v.status}</SkeuoBadge>
                        {v.approved && (
                          <span className="ml-2 text-[10px] uppercase tracking-wide text-status-success">
                            gate pass
                          </span>
                        )}
                      </SkeuoTd>
                      <SkeuoTd>
                        {v.decision?.reason ? (
                          <div className="max-w-[220px]">
                            <div className="text-xs text-text">{v.decision.reason}</div>
                            <div className="text-[10px] text-text-muted">
                              {v.decision.source || "—"}
                              {v.decision.actor ? ` · ${v.decision.actor}` : ""}
                            </div>
                          </div>
                        ) : (
                          <span className="font-mono text-xs text-text-muted">
                            {v.sessionId ? `${v.sessionId.slice(0, 12)}…` : "—"}
                          </span>
                        )}
                      </SkeuoTd>
                      <SkeuoTd>
                        <span className="text-xs text-text-muted">
                          {formatWhen(v.updatedAt || v.decidedAt || v.verifiedAt)}
                        </span>
                      </SkeuoTd>
                      <SkeuoTd>
                        <div className="flex flex-wrap gap-2">
                          <SkeuoButton
                            type="button"
                            size="sm"
                            disabled={Boolean(busy) || v.approved}
                            onClick={() => askStatus(v, "Approved")}
                            data-testid={`kyc-approve-${v.userId}`}
                          >
                            Approve
                          </SkeuoButton>
                          <SkeuoButton
                            type="button"
                            size="sm"
                            variant="ghost"
                            disabled={Boolean(busy) || v.status === "Declined"}
                            onClick={() => askStatus(v, "Declined")}
                            data-testid={`kyc-decline-${v.userId}`}
                          >
                            Decline
                          </SkeuoButton>
                        </div>
                      </SkeuoTd>
                    </SkeuoTableRow>
                  ))}
                </SkeuoTableBody>
              </SkeuoTable>
            )}
          </DevCard>
        </>
      )}

      <AdminConfirmDialog
        open={Boolean(pending)}
        title={
          pending
            ? `${pending.status === "Approved" ? "Approve" : "Decline"} verification`
            : "Confirm"
        }
        description={
          pending
            ? `${pending.v.email || pending.v.userId} — current status ${pending.v.status}. This overrides Didit for purchase/call gates.`
            : undefined
        }
        confirmLabel={pending?.status === "Approved" ? "Confirm approve" : "Confirm decline"}
        tone={pending?.status === "Declined" ? "danger" : "default"}
        statementPlaceholder="e.g. Documents reviewed offline; Didit webhook missed for session …"
        busy={Boolean(busy)}
        onCancel={() => setPending(null)}
        onConfirm={(statement) => void confirmStatus(statement)}
      />
    </div>
  );
}
