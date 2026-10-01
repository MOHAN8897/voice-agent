"use client";

import { useEffect, useState } from "react";
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
  SkeuoInput,
  SkeuoTable,
  SkeuoTableBody,
  SkeuoTableHead,
  SkeuoTableRow,
  SkeuoTd,
  SkeuoTh,
} from "@/components/ui/skeuo";
import {
  adminAction,
  formatInr,
  formatUsd,
  formatWhen,
  useAdminResource,
} from "@/lib/useAdminResource";

type Purchase = {
  purchaseId: string;
  tenantId: string;
  e164: string;
  status: string;
  createdAt: string;
};

type WalletRow = {
  tenantId: string;
  name: string;
  status: string;
  balanceInrPaise: number;
  balanceCents: number;
  currency: string;
  updatedAt: string | null;
};

type Rates = {
  pstnInrPerMin: number;
  webInrPerMin: number;
  pstnUsdPerMin: number;
  webUsdPerMin: number;
  didMonthlyInr: number;
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
  const wallets = useAdminResource<{ wallets: WalletRow[] }>("/api/dev/admin/wallets");
  const ratesRes = useAdminResource<{ rates: Rates }>("/api/dev/admin/billing-rates");

  const [tenantId, setTenantId] = useState("");
  const [rupees, setRupees] = useState("415");
  const [pstnInr, setPstnInr] = useState("9");
  const [webInr, setWebInr] = useState("7");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    const r = ratesRes.data?.rates;
    if (!r) return;
    setPstnInr(String(r.pstnInrPerMin ?? 9));
    setWebInr(String(r.webInrPerMin ?? 7));
  }, [ratesRes.data]);

  const rows = (wallets.data?.wallets ?? []).filter((w) =>
    query.trim()
      ? `${w.name} ${w.tenantId}`.toLowerCase().includes(query.trim().toLowerCase())
      : true
  );
  const purchaseRows = purchases.data?.purchases ?? [];
  const failed = purchaseRows.filter((p) => p.status === "failed").length;
  const totalInr = rows.reduce((sum, w) => sum + (w.balanceInrPaise || 0), 0);

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

  function adjust(sign: 1 | -1) {
    const amount = Math.abs(Number(rupees));
    if (!tenantId || !Number.isFinite(amount) || amount <= 0) {
      setError("Pick a tenant and enter a positive INR amount.");
      return;
    }
    return run(sign > 0 ? "credit" : "debit", async () => {
      await adminAction("/api/dev/admin/wallets/adjust", {
        method: "POST",
        body: {
          tenantId,
          amountInrPaise: Math.round(amount * 100) * sign,
          reason: sign > 0 ? "admin_grant" : "admin_debit",
        },
      });
      await wallets.reload();
    });
  }

  function saveRates() {
    return run("rates", async () => {
      await adminAction("/api/dev/admin/billing-rates", {
        method: "PUT",
        body: {
          pstnInrPerMin: Number(pstnInr),
          webInrPerMin: Number(webInr),
        },
      });
      await ratesRes.reload();
    });
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
    <div className="space-y-6 p-6" data-testid="admin-billing-wallets-page">
      <AdminPageHeader
        title="Wallet & rates"
        description="Manual INR top-ups, per-minute call rates, and number purchase status. Customer payments use Razorpay."
      />

      <AdminError error={error} />
      <AdminError error={purchases.error} />
      <AdminError error={wallets.error} />
      <AdminError error={ratesRes.error} />

      <div className="grid gap-4 sm:grid-cols-4">
        <AdminStat label="Wallet INR total" value={formatInr(totalInr)} />
        <AdminStat
          label="PSTN ₹/min"
          value={`₹${ratesRes.data?.rates?.pstnInrPerMin ?? "—"}`}
        />
        <AdminStat
          label="Browser ₹/min"
          value={`₹${ratesRes.data?.rates?.webInrPerMin ?? "—"}`}
        />
        <AdminStat label="Failed purchases" value={failed} tone={failed > 0 ? "warn" : "good"} />
      </div>

      <DevCard title="Per-minute rates (INR)">
        <div className="flex flex-wrap items-end gap-3">
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Phone (PSTN) ₹/min</span>
            <SkeuoInput
              value={pstnInr}
              onChange={(e) => setPstnInr(e.target.value)}
              inputMode="decimal"
              className="w-28"
              aria-label="PSTN INR per minute"
            />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Browser test ₹/min</span>
            <SkeuoInput
              value={webInr}
              onChange={(e) => setWebInr(e.target.value)}
              inputMode="decimal"
              className="w-28"
              aria-label="Web agent INR per minute"
            />
          </label>
          <SkeuoButton type="button" disabled={!!busy} onClick={() => void saveRates()}>
            {busy === "rates" ? "Saving…" : "Save rates"}
          </SkeuoButton>
        </div>
        <p className="mt-2 text-[11px] text-text-muted">
          Applies to wallet debit for PSTN and browser test sessions. Razorpay top-ups credit INR
          automatically after payment verification.
        </p>
      </DevCard>

      <DevCard title="Manual wallet top-up / debit (INR)">
        <div className="flex flex-wrap items-end gap-3">
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Tenant</span>
            <select
              className="min-w-[220px] rounded-skeuo-sm border border-border bg-surface-panel px-3 py-2 text-sm"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              aria-label="Tenant for wallet adjust"
            >
              <option value="">Select tenant…</option>
              {(wallets.data?.wallets ?? []).map((w) => (
                <option key={w.tenantId} value={w.tenantId}>
                  {w.name} — {formatInr(w.balanceInrPaise)}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Amount (₹)</span>
            <SkeuoInput
              value={rupees}
              onChange={(e) => setRupees(e.target.value)}
              inputMode="decimal"
              aria-label="INR amount"
              className="w-28"
            />
          </label>
          <SkeuoButton type="button" disabled={!!busy} onClick={() => void adjust(1)}>
            {busy === "credit" ? "Crediting…" : "Increase"}
          </SkeuoButton>
          <SkeuoButton
            type="button"
            variant="secondary"
            disabled={!!busy}
            onClick={() => void adjust(-1)}
          >
            {busy === "debit" ? "Debiting…" : "Decrease"}
          </SkeuoButton>
        </div>
      </DevCard>

      <DevCard title="Tenant wallets">
        <div className="mb-3">
          <SkeuoInput
            placeholder="Search by tenant name or id"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search wallets"
            className="max-w-sm"
          />
        </div>
        <AdminLoading loading={wallets.loading} />
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh>Tenant</SkeuoTh>
            <SkeuoTh>Status</SkeuoTh>
            <SkeuoTh>USD</SkeuoTh>
            <SkeuoTh>Updated</SkeuoTh>
            <SkeuoTh className="text-right">Select</SkeuoTh>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {rows.map((w) => (
              <SkeuoTableRow key={w.tenantId}>
                <SkeuoTd>
                  <p className="font-medium">{w.name}</p>
                  <p className="font-mono text-[10px] text-text-subtle">{w.tenantId}</p>
                </SkeuoTd>
                <SkeuoTd>{w.status || "—"}</SkeuoTd>
                <SkeuoTd className="font-mono">{formatUsd(w.balanceCents)}</SkeuoTd>
                <SkeuoTd>{formatWhen(w.updatedAt)}</SkeuoTd>
                <SkeuoTd className="text-right">
                  <SkeuoButton type="button" size="sm" onClick={() => setTenantId(w.tenantId)}>
                    Use
                  </SkeuoButton>
                </SkeuoTd>
              </SkeuoTableRow>
            ))}
          </SkeuoTableBody>
        </SkeuoTable>
      </DevCard>

      <DevCard title="Number purchases">
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
            <SkeuoTh>When</SkeuoTh>
            <SkeuoTh className="text-right">Actions</SkeuoTh>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {purchaseRows.map((p) => (
              <SkeuoTableRow key={p.purchaseId}>
                <SkeuoTd className="font-mono">{p.e164}</SkeuoTd>
                <SkeuoTd className="font-mono text-[10px]">{p.tenantId}</SkeuoTd>
                <SkeuoTd>
                  <SkeuoBadge tone={TONE[p.status] || "muted"}>{p.status}</SkeuoBadge>
                </SkeuoTd>
                <SkeuoTd>{formatWhen(p.createdAt)}</SkeuoTd>
                <SkeuoTd className="space-x-2 text-right">
                  {p.status === "failed" && (
                    <SkeuoButton
                      type="button"
                      size="sm"
                      disabled={busy === `retry:${p.purchaseId}`}
                      onClick={() => void retry(p.purchaseId)}
                    >
                      Retry
                    </SkeuoButton>
                  )}
                  {p.status === "paid" && (
                    <SkeuoButton
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={busy === `refund:${p.purchaseId}`}
                      onClick={() => void refund(p.purchaseId)}
                    >
                      Refund
                    </SkeuoButton>
                  )}
                </SkeuoTd>
              </SkeuoTableRow>
            ))}
          </SkeuoTableBody>
        </SkeuoTable>
      </DevCard>
    </div>
  );
}
