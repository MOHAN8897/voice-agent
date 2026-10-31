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
  tenantName?: string;
  status: string;
  approved: boolean;
  callsBlocked?: boolean;
  kycType?: "voice" | "identity";
  provider?: string;
  verifications?: Record<string, string>;
  verifiedAt?: string | null;
  decidedAt?: string | null;
  sessionId?: string | null;
  /** Voice KYC only: why sub-account or hosted-link setup failed. */
  setupIssue?: string | null;
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
  activeProvider?: string;
  verifications: Verification[];
  voiceVerifications?: unknown[];
  diditVerifications?: unknown[];
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

export function AdminVerificationPage() {
  const kyc = useAdminResource<KycList>("/api/dev/admin/kyc");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [gateFilter, setGateFilter] = useState("all");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<{ v: Verification; status: string } | null>(null);

  const allVerifications = kyc.data?.verifications ?? [];
  const rows = useMemo(() => {
    return allVerifications.filter((v) => {
      if (statusFilter && v.status !== statusFilter) return false;
      if (gateFilter === "passed" && !v.approved) return false;
      if (gateFilter === "pending" && (v.approved || v.status === "Declined")) return false;
      if (gateFilter === "declined" && v.status !== "Declined") return false;

      if (!query.trim()) return true;
      const q = query.trim().toLowerCase();
      const target = `${v.email ?? ""} ${v.fullName ?? ""} ${v.userId} ${v.tenantId ?? ""} ${v.status} ${v.sessionId ?? ""} ${v.decision?.reason ?? ""}`.toLowerCase();
      return target.includes(q);
    });
  }, [allVerifications, query, statusFilter, gateFilter]);

  const approved = (kyc.data?.verifications ?? []).filter((v) => v.approved).length;
  const inReview = (kyc.data?.verifications ?? []).filter((v) =>
    ["In Review", "In Progress", "Awaiting User"].includes(v.status)
  ).length;
  const declined = (kyc.data?.verifications ?? []).filter((v) => v.status === "Declined").length;

  const hasFilters = Boolean(query.trim() || statusFilter || gateFilter !== "all");

  function resetFilters() {
    setQuery("");
    setStatusFilter("");
    setGateFilter("all");
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
        title="Identity & Telephony verification"
        description="Tenant carrier subaccounts (Vobiz Voice KYC) and buyer identity verifications. Manual Approve / Decline requires a written statement and is recorded in the admin audit log."
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
              label={kyc.data.activeProvider === "vobiz" ? "Telephony KYC (Vobiz)" : "Identity Verification"}
              value={kyc.data.configured ? "Configured" : "Missing keys"}
              tone={kyc.data.configured ? "good" : "warn"}
              hint={kyc.data.activeProvider === "vobiz" ? "Carrier subaccount KYC" : (kyc.data.workflowId ? `workflow ${kyc.data.workflowId.slice(0, 8)}…` : "no workflow")}
            />
            <AdminStat label="Approved" value={approved} tone="good" />
            <AdminStat label="Pending / in review" value={inReview} tone={inReview ? "warn" : "default"} />
            <AdminStat label="Declined" value={declined} tone={declined ? "warn" : "default"} />
          </div>

          <DevCard
            title="Manual overrides"
            description="Pending reviews that stall (carrier delay, false decline) can be resolved with an explicit admin statement. Provider remains source of truth until you override."
          >
            <p className="text-xs text-text-muted">
              Purchase gate: {kyc.data.gatePurchases ? "on" : "off"} · Click Approve / Decline on a row to
              open the confirmation dialog.
            </p>
          </DevCard>

          <DevCard title="Verifications">
            <div className="mb-4 space-y-3">
              <div className="grid gap-3 sm:grid-cols-3">
                <SkeuoInput
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search email, name, user ID, tenant ID…"
                  data-testid="kyc-search"
                />
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="rounded-skeuo-sm border border-surface-border bg-surface-panel px-3 py-2 text-sm text-text"
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
                <select
                  value={gateFilter}
                  onChange={(e) => setGateFilter(e.target.value)}
                  className="rounded-skeuo-sm border border-surface-border bg-surface-panel px-3 py-2 text-sm text-text"
                >
                  <option value="all">All gate outcomes</option>
                  <option value="passed">Gate Pass Active (Approved)</option>
                  <option value="pending">Review / In Progress</option>
                  <option value="declined">Gate Blocked (Declined)</option>
                </select>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-surface-border-subtle pt-2 text-xs text-text-muted">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="mr-1">Quick:</span>
                  {["", "Approved", "In Review", "Declined", "In Progress"].map((s) => (
                    <button
                      key={s || "all"}
                      type="button"
                      onClick={() => setStatusFilter(s)}
                      className={`rounded px-2 py-0.5 text-xs transition-colors ${
                        statusFilter === s
                          ? "bg-accent-primary text-white"
                          : "bg-surface-panel-raised text-text-muted hover:text-text"
                      }`}
                    >
                      {s || "All"}
                    </button>
                  ))}
                </div>

                <div className="flex items-center gap-2">
                  <span>
                    Showing <strong className="text-text">{rows.length}</strong> of{" "}
                    <strong className="text-text">{allVerifications.length}</strong> verifications
                  </span>
                  {hasFilters && (
                    <button
                      type="button"
                      onClick={resetFilters}
                      className="text-accent-primary hover:underline"
                    >
                      Clear filters
                    </button>
                  )}
                </div>
              </div>
            </div>

            {rows.length === 0 ? (
              <p className="py-8 text-center text-sm text-text-muted" data-testid="kyc-empty">
                No verification sessions match the current filters.
              </p>
            ) : (
              <SkeuoTable>
                <SkeuoTableHead>
                  <SkeuoTh>User</SkeuoTh>
                  <SkeuoTh>Status</SkeuoTh>
                  <SkeuoTh>Last decision</SkeuoTh>
                  <SkeuoTh>Updated</SkeuoTh>
                  <SkeuoTh>Actions</SkeuoTh>
                </SkeuoTableHead>
                <SkeuoTableBody>
                  {rows.map((v) => (
                    <SkeuoTableRow key={v.userId} data-testid={`kyc-row-${v.userId}`}>
                      <SkeuoTd>
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium text-text">{v.email || v.userId}</span>
                          {v.kycType === "voice" && (
                            <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[9px] font-semibold text-indigo-700 border border-indigo-200">
                              Voice KYC
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-text-muted">
                          {v.fullName || "—"} {v.tenantName && !v.fullName?.includes(v.tenantName) ? `· ${v.tenantName}` : ""}
                        </div>
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
                        {v.callsBlocked && (
                          <span className="ml-1 text-[10px] uppercase tracking-wide text-status-danger font-medium">
                            calls blocked
                          </span>
                        )}
                        {v.setupIssue && (
                          <p className="mt-1 max-w-[260px] text-xs text-status-warning" data-testid="kyc-setup-issue">
                            {v.setupIssue}
                          </p>
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
