"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
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
  /** Dollar figure for display; derived server-side when only INR is funded. */
  balanceUsd: number;
  currency: string;
  walletCurrency: string;
  updatedAt: string | null;
};

type Rates = {
  pstnUsdPerMin: number;
  webUsdPerMin: number;
  numberMonthlyUsd: number;
  /** The rate money is actually converted at. */
  fxRateInr: number;
  /** Read-only mirrors at fxRateInr. */
  pstnInrPerMin: number;
  webInrPerMin: number;
  numberMonthlyInr: number;
};

/** Market rate, shown for reference only — charging uses rates.fxRateInr. */
type FxInfo = {
  liveRateInr: number | null;
  source?: string;
  asOf?: string | null;
  chargeRateInr: number;
};

type PaymentSettings = {
  configured: boolean;
  keyId: string;
  testMode: boolean;
  internationalEnabled: boolean;
  /** Razorpay has no status endpoint; this is always null by design. */
  internationalVerified: null;
  internationalNote: string;
  currency: string;
  availableCurrencies: string[];
  minCharge: number;
  supportsUpi: boolean;
  settlesIn: string;
};

type PayOrder = {
  orderId: string;
  tenantName: string | null;
  status: string;
  currency: string;
  amount: number;
  amountInr: number;
  createdAt: string | null;
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
  const wallets = useAdminResource<{ wallets: WalletRow[]; currency: string }>(
    "/api/dev/admin/wallets"
  );
  const ratesRes = useAdminResource<{ currency: string; rates: Rates; fx: FxInfo }>(
    "/api/dev/admin/billing-rates"
  );

  const payments = useAdminResource<PaymentSettings>("/api/dev/admin/payments");
  const payOrders = useAdminResource<{ orders: PayOrder[] }>("/api/dev/admin/payments/orders");
  const [intlEnabled, setIntlEnabled] = useState(false);
  const [payCurrency, setPayCurrency] = useState("USD");

  const searchParams = useSearchParams();
  const tenantFromUrl = searchParams.get("tenantId") || "";
  const [tenantId, setTenantId] = useState(tenantFromUrl);
  // USD is the currency admins author prices in; the INR mirror is read-only.
  const [dollars, setDollars] = useState("25");
  const [adjustNote, setAdjustNote] = useState("");
  const [pstnUsd, setPstnUsd] = useState("0.09");
  const [webUsd, setWebUsd] = useState("0.07");
  const [numberUsd, setNumberUsd] = useState("4");
  const [fxRate, setFxRate] = useState("95.64");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Wallets filter state
  const [query, setQuery] = useState("");
  const [walletStatusFilter, setWalletStatusFilter] = useState("all");
  const [walletBalanceFilter, setWalletBalanceFilter] = useState("all");

  // Orders filter state
  const [orderQuery, setOrderQuery] = useState("");
  const [orderStatus, setOrderStatus] = useState("all");
  const [orderCurrency, setOrderCurrency] = useState("all");

  // Purchases filter state
  const [purchaseQuery, setPurchaseQuery] = useState("");

  useEffect(() => {
    if (tenantFromUrl) setTenantId(tenantFromUrl);
  }, [tenantFromUrl]);

  useEffect(() => {
    const r = ratesRes.data?.rates;
    if (!r) return;
    setPstnUsd(String(r.pstnUsdPerMin ?? 0.09));
    setWebUsd(String(r.webUsdPerMin ?? 0.07));
    setNumberUsd(String(r.numberMonthlyUsd ?? 4));
    setFxRate(String(r.fxRateInr ?? 95.64));
  }, [ratesRes.data]);

  const chargeFx = Number(ratesRes.data?.rates?.fxRateInr) || 95.64;
  const liveFx = Number(ratesRes.data?.fx?.liveRateInr) || 0;

  useEffect(() => {
    const p = payments.data;
    if (!p) return;
    setIntlEnabled(Boolean(p.internationalEnabled));
    setPayCurrency(p.currency || "USD");
  }, [payments.data]);

  function savePayments() {
    return run("payments", async () => {
      await adminAction("/api/dev/admin/payments", {
        method: "PUT",
        body: { internationalEnabled: intlEnabled, currency: payCurrency },
      });
      await Promise.all([payments.reload(), payOrders.reload()]);
    });
  }

  const allWallets = wallets.data?.wallets ?? [];
  const rows = useMemo(() => {
    return allWallets.filter((w) => {
      if (walletStatusFilter !== "all" && (w.status || "").toLowerCase() !== walletStatusFilter.toLowerCase()) return false;
      const bal = w.balanceUsd || 0;
      if (walletBalanceFilter === "funded" && bal <= 0) return false;
      if (walletBalanceFilter === "low" && (bal <= 0 || bal >= 5)) return false;
      if (walletBalanceFilter === "depleted" && bal > 0) return false;
      if (!query.trim()) return true;
      return `${w.name} ${w.tenantId}`.toLowerCase().includes(query.trim().toLowerCase());
    });
  }, [allWallets, walletStatusFilter, walletBalanceFilter, query]);

  const allOrders = payOrders.data?.orders ?? [];
  const filteredOrders = useMemo(() => {
    return allOrders.filter((o) => {
      if (orderStatus !== "all" && (o.status || "").toLowerCase() !== orderStatus.toLowerCase()) return false;
      if (orderCurrency !== "all" && (o.currency || "").toUpperCase() !== orderCurrency.toUpperCase()) return false;
      if (!orderQuery.trim()) return true;
      const q = orderQuery.trim().toLowerCase();
      return `${o.tenantName ?? ""} ${o.orderId}`.toLowerCase().includes(q);
    });
  }, [allOrders, orderStatus, orderCurrency, orderQuery]);

  const allPurchases = purchases.data?.purchases ?? [];
  const purchaseRows = useMemo(() => {
    return allPurchases.filter((p) => {
      if (!purchaseQuery.trim()) return true;
      const q = purchaseQuery.trim().toLowerCase();
      return `${p.e164} ${p.tenantId} ${p.purchaseId}`.toLowerCase().includes(q);
    });
  }, [allPurchases, purchaseQuery]);

  const failed = purchaseRows.filter((p) => p.status === "failed").length;
  const totalUsdCents = rows.reduce(
    (sum, w) => sum + Math.round((w.balanceUsd || 0) * 100),
    0
  );

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
    const amount = Math.abs(Number(dollars));
    const note = adjustNote.trim();
    if (!tenantId || !Number.isFinite(amount) || amount <= 0) {
      setError("Pick a tenant and enter a positive USD amount.");
      return;
    }
    if (note.length < 8) {
      setError("Write an admin statement (8+ characters) before adjusting a wallet.");
      return;
    }
    return run(sign > 0 ? "credit" : "debit", async () => {
      await adminAction("/api/dev/admin/wallets/adjust", {
        method: "POST",
        body: {
          tenantId,
          amountUsdCents: Math.round(amount * 100) * sign,
          reason: sign > 0 ? "admin_grant" : "admin_debit",
          note,
        },
      });
      setAdjustNote("");
      await wallets.reload();
    });
  }

  function saveRates() {
    return run("rates", async () => {
      await adminAction("/api/dev/admin/billing-rates", {
        method: "PUT",
        body: {
          pstnUsdPerMin: Number(pstnUsd),
          webUsdPerMin: Number(webUsd),
          numberMonthlyUsd: Number(numberUsd),
          fxRateInr: Number(fxRate),
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
        description="Prices are set in USD. The INR figures shown are derived at the charge rate. Customer payments run through Razorpay."
        actions={
          tenantId ? (
            <Link href={`/dev/admin/tenants/${tenantId}?tab=wallet`}>
              <SkeuoButton variant="ghost">Tenant wallet cockpit</SkeuoButton>
            </Link>
          ) : undefined
        }
      />

      <AdminError error={error} />
      <AdminError error={purchases.error} />
      <AdminError error={wallets.error} />
      <AdminError error={ratesRes.error} />

      <div className="grid gap-4 sm:grid-cols-4">
        <AdminStat label="Wallet USD total" value={formatUsd(totalUsdCents)} />
        <AdminStat
          label="PSTN $/min"
          value={`$${ratesRes.data?.rates?.pstnUsdPerMin ?? "—"}`}
        />
        <AdminStat
          label="Number rental $/mo"
          value={`$${ratesRes.data?.rates?.numberMonthlyUsd ?? "—"}`}
        />
        <AdminStat label="Failed purchases" value={failed} tone={failed > 0 ? "warn" : "good"} />
      </div>

      <DevCard title="USD → INR reference">
        <div className="flex flex-wrap items-end gap-4">
          <div className="text-xs">
            <span className="mb-1 block text-text-muted">Charge rate (USD → INR)</span>
            <SkeuoInput
              value={fxRate}
              onChange={(e) => setFxRate(e.target.value)}
              inputMode="decimal"
              className="w-28"
              aria-label="Charge FX rate INR per USD"
              data-testid="admin-fx-charge-rate"
            />
            <span className="mt-1 block text-[11px] text-text-muted">
              Prices are multiplied by this. Saving it reprices everything.
            </span>
          </div>
          <div
            className="text-xs"
            data-testid="admin-fx-live"
            aria-label={`Live rate ${liveFx || "unavailable"} rupees per dollar`}
          >
            <span className="mb-1 block text-text-muted">Live market rate</span>
            <p className="font-mono text-lg font-semibold">
              {liveFx ? `₹${liveFx.toFixed(2)}` : "unavailable"}
            </p>
            <span className="block text-[11px] text-text-muted">
              {ratesRes.data?.fx?.asOf ? `as of ${ratesRes.data.fx.asOf}` : "reference only"}
              {ratesRes.data?.fx?.source ? ` · ${ratesRes.data.fx.source}` : ""}
            </span>
          </div>
        </div>
      </DevCard>

      <DevCard title="Prices (USD)">
        <div className="flex flex-wrap items-end gap-3">
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Phone (PSTN) $/min</span>
            <SkeuoInput
              value={pstnUsd}
              onChange={(e) => setPstnUsd(e.target.value)}
              inputMode="decimal"
              className="w-28"
              aria-label="PSTN USD per minute"
              data-testid="admin-rate-pstn-usd"
            />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Browser test $/min</span>
            <SkeuoInput
              value={webUsd}
              onChange={(e) => setWebUsd(e.target.value)}
              inputMode="decimal"
              className="w-28"
              aria-label="Web agent USD per minute"
              data-testid="admin-rate-web-usd"
            />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Phone number rental $/mo</span>
            <SkeuoInput
              value={numberUsd}
              onChange={(e) => setNumberUsd(e.target.value)}
              inputMode="decimal"
              className="w-28"
              aria-label="Number rental USD per month"
              data-testid="admin-rate-number-usd"
            />
          </label>
          <SkeuoButton type="button" disabled={!!busy} onClick={() => void saveRates()}>
            {busy === "rates" ? "Saving…" : "Save rates"}
          </SkeuoButton>
        </div>
        {/* Derived mirrors: shown so an admin can see the rupee consequence of
            the dollar price they just typed, without a second source of truth. */}
        <div
          className="mt-3 flex flex-wrap gap-4 font-mono text-[11px] text-text-muted"
          data-testid="admin-rate-inr-mirror"
        >
          <span>PSTN ≈ ₹{((Number(pstnUsd) || 0) * chargeFx).toFixed(2)}/min</span>
          <span>Browser ≈ ₹{((Number(webUsd) || 0) * chargeFx).toFixed(2)}/min</span>
          <span>Number ≈ ₹{((Number(numberUsd) || 0) * chargeFx).toFixed(2)}/mo</span>
        </div>
      </DevCard>

      <DevCard title="Manual wallet top-up / debit (USD)">
        <p className="mb-3 text-xs text-text-muted">
          Credits or debits one wallet leg (USD or INR, matching the tenant&apos;s primary currency).
          Every change requires a statement for the audit trail.
        </p>
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
                  {w.name} — {formatUsd(Math.round((w.balanceUsd || 0) * 100))}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Amount ($)</span>
            <SkeuoInput
              value={dollars}
              onChange={(e) => setDollars(e.target.value)}
              inputMode="decimal"
              aria-label="USD amount"
              className="w-28"
              data-testid="admin-wallet-usd-amount"
            />
            <span className="mt-1 block font-mono text-[11px] text-text-muted">
              ≈ ₹{((Number(dollars) || 0) * chargeFx).toFixed(2)}
            </span>
          </label>
          <label className="block min-w-[240px] flex-1 text-xs">
            <span className="mb-1 block text-text-muted">Admin statement</span>
            <SkeuoInput
              value={adjustNote}
              onChange={(e) => setAdjustNote(e.target.value)}
              placeholder="Required — why is this adjustment being made?"
              data-testid="admin-wallet-note"
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

      <DevCard title="Payments — Razorpay">
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span
            className={`rounded-skeuo-sm px-2 py-1 font-semibold ${
              payments.data?.configured ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
            }`}
            data-testid="admin-payments-status"
          >
            {payments.data?.configured ? "Keys configured" : "Keys missing"}
            {payments.data?.testMode ? " · test mode" : " · live"}
          </span>
          {payments.data?.keyId ? (
            <span className="font-mono text-text-muted">{payments.data.keyId}</span>
          ) : null}
          <span className="text-text-muted">Settles in {payments.data?.settlesIn ?? "INR"}</span>
          <span
            className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-2 py-1 font-medium text-text-subtle"
            data-testid="admin-payments-intl-badge"
          >
            International: Not checkable via API
          </span>
        </div>

        <div className="mt-4 flex flex-wrap items-end gap-4">
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={intlEnabled}
              onChange={(e) => setIntlEnabled(e.target.checked)}
              aria-label="Enable international payments"
              data-testid="admin-payments-international"
              className="h-4 w-4"
            />
            <span>
              Accept international cards
              <span className="block text-[11px] text-text-muted">
                Cards issued outside India. Settles to INR.
              </span>
            </span>
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-text-muted">Charge currency</span>
            <select
              value={payCurrency}
              onChange={(e) => setPayCurrency(e.target.value)}
              aria-label="Charge currency"
              data-testid="admin-payments-currency"
              disabled={!intlEnabled}
              className="rounded-skeuo-sm border border-border bg-surface-panel px-3 py-2 text-sm disabled:opacity-50"
            >
              {(payments.data?.availableCurrencies ?? ["INR"]).map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <SkeuoButton
            type="button"
            disabled={!!busy || !payments.data?.configured}
            onClick={() => void savePayments()}
          >
            {busy === "payments" ? "Saving…" : "Save payment settings"}
          </SkeuoButton>
        </div>

        {intlEnabled && (
          <p className="mt-3 text-[11px] text-amber-800" data-testid="admin-payments-hint">
            Razorpay provides no API to confirm this, so it has to be checked by hand:{' '}
            <strong>Account &amp; Settings → Payment methods → International payments</strong>. Until
            Razorpay approves it, foreign cards are declined at checkout.
          </p>
        )}
        {intlEnabled && payCurrency !== "INR" && (
          <p className="mt-2 text-[11px] text-text-muted">
            UPI and netbanking are hidden automatically for {payCurrency} orders — they settle
            domestically only. Minimum charge {payments.data?.minCharge} {payCurrency}.
          </p>
        )}
      </DevCard>

      <DevCard title="Payment orders">
        <div className="mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Search orders</label>
              <SkeuoInput
                placeholder="Tenant or order ID…"
                value={orderQuery}
                onChange={(e) => setOrderQuery(e.target.value)}
                aria-label="Search orders"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Status</label>
              <select
                value={orderStatus}
                onChange={(e) => setOrderStatus(e.target.value)}
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="all">All statuses</option>
                <option value="captured">Captured / Paid</option>
                <option value="paid">Paid</option>
                <option value="created">Created</option>
                <option value="attempted">Attempted</option>
                <option value="failed">Failed</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Currency</label>
              <select
                value={orderCurrency}
                onChange={(e) => setOrderCurrency(e.target.value)}
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="all">All currencies</option>
                <option value="USD">USD</option>
                <option value="INR">INR</option>
                <option value="EUR">EUR</option>
              </select>
            </div>
          </div>
          <div className="flex items-center justify-between border-t border-surface-border-subtle pt-2 text-xs text-text-muted">
            <span>
              Showing <strong className="text-text">{filteredOrders.length}</strong> of{" "}
              <strong className="text-text">{allOrders.length}</strong> orders
            </span>
            {(orderQuery.trim() || orderStatus !== "all" || orderCurrency !== "all") && (
              <button
                type="button"
                onClick={() => {
                  setOrderQuery("");
                  setOrderStatus("all");
                  setOrderCurrency("all");
                }}
                className="text-accent-primary hover:underline"
              >
                Clear filters
              </button>
            )}
          </div>
        </div>

        <AdminLoading loading={payOrders.loading} />
        <AdminError error={payOrders.error} />
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh>Tenant</SkeuoTh>
            <SkeuoTh>Charged</SkeuoTh>
            <SkeuoTh>Settled (INR)</SkeuoTh>
            <SkeuoTh>Status</SkeuoTh>
            <SkeuoTh>When</SkeuoTh>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {filteredOrders.map((o) => (
              <SkeuoTableRow key={o.orderId}>
                <SkeuoTd>
                  <div className="font-medium text-text">{o.tenantName || "Unassigned"}</div>
                  <div className="font-mono text-[10px] text-text-muted">{o.orderId}</div>
                </SkeuoTd>
                <SkeuoTd className="font-mono font-medium">
                  {o.currency} {o.amount.toFixed(2)}
                </SkeuoTd>
                <SkeuoTd className="font-mono">{formatInr(Math.round(o.amountInr * 100))}</SkeuoTd>
                <SkeuoTd>
                  <SkeuoBadge
                    tone={
                      o.status === "captured" || o.status === "paid"
                        ? "success"
                        : o.status === "failed"
                        ? "danger"
                        : "warning"
                    }
                  >
                    {o.status}
                  </SkeuoBadge>
                </SkeuoTd>
                <SkeuoTd className="text-xs text-text-muted">{formatWhen(o.createdAt)}</SkeuoTd>
              </SkeuoTableRow>
            ))}
            {filteredOrders.length === 0 && !payOrders.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-center py-6 text-text-muted" colSpan={5}>
                  No payment orders found matching current filters.
                </SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>
      </DevCard>

      <DevCard title="Tenant wallets">
        <div className="mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Search wallet</label>
              <SkeuoInput
                placeholder="Search tenant name or id…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search wallets"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Balance level</label>
              <select
                value={walletBalanceFilter}
                onChange={(e) => setWalletBalanceFilter(e.target.value)}
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="all">All balances</option>
                <option value="funded">Funded (&gt; $0)</option>
                <option value="low">Low balance (&lt; $5)</option>
                <option value="depleted">Zero / Depleted ($0)</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Workspace status</label>
              <select
                value={walletStatusFilter}
                onChange={(e) => setWalletStatusFilter(e.target.value)}
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="all">All statuses</option>
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
                <option value="past_due">Past Due</option>
                <option value="deleted">Deleted</option>
              </select>
            </div>
          </div>
          <div className="flex items-center justify-between border-t border-surface-border-subtle pt-2 text-xs text-text-muted">
            <span>
              Showing <strong className="text-text">{rows.length}</strong> of{" "}
              <strong className="text-text">{allWallets.length}</strong> workspaces
            </span>
            {(query.trim() || walletBalanceFilter !== "all" || walletStatusFilter !== "all") && (
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  setWalletBalanceFilter("all");
                  setWalletStatusFilter("all");
                }}
                className="text-accent-primary hover:underline"
              >
                Clear filters
              </button>
            )}
          </div>
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
                  <Link href={`/dev/admin/tenants/${w.tenantId}?tab=wallet`} className="font-medium text-accent-primary hover:underline">
                    {w.name}
                  </Link>
                  <p className="font-mono text-[10px] text-text-subtle">{w.tenantId}</p>
                </SkeuoTd>
                <SkeuoTd>
                  <SkeuoBadge tone={w.status === "active" ? "success" : w.status === "deleted" ? "danger" : "warning"}>
                    {w.status || "active"}
                  </SkeuoBadge>
                </SkeuoTd>
                <SkeuoTd className="font-mono font-medium" data-testid="admin-wallet-usd-cell">
                  {formatUsd(Math.round((w.balanceUsd || 0) * 100))}
                </SkeuoTd>
                <SkeuoTd className="text-xs text-text-muted">{formatWhen(w.updatedAt)}</SkeuoTd>
                <SkeuoTd className="text-right">
                  <SkeuoButton type="button" size="sm" onClick={() => setTenantId(w.tenantId)}>
                    Use
                  </SkeuoButton>
                </SkeuoTd>
              </SkeuoTableRow>
            ))}
            {rows.length === 0 && !wallets.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-center py-6 text-text-muted" colSpan={5}>
                  No workspaces found matching current filters.
                </SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>
      </DevCard>

      <DevCard title="Number purchases">
        <div className="mb-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-1">
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

            <div className="min-w-[220px]">
              <SkeuoInput
                placeholder="Search number, tenant, ID…"
                value={purchaseQuery}
                onChange={(e) => setPurchaseQuery(e.target.value)}
                aria-label="Search purchases"
              />
            </div>
          </div>

          <div className="flex items-center justify-between border-t border-surface-border-subtle pt-2 text-xs text-text-muted">
            <span>
              Showing <strong className="text-text">{purchaseRows.length}</strong> of{" "}
              <strong className="text-text">{allPurchases.length}</strong> purchases
            </span>
            {(status || purchaseQuery.trim()) && (
              <button
                type="button"
                onClick={() => {
                  setStatus("");
                  setPurchaseQuery("");
                }}
                className="text-accent-primary hover:underline"
              >
                Clear filters
              </button>
            )}
          </div>
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
                <SkeuoTd className="font-mono font-medium">{p.e164}</SkeuoTd>
                <SkeuoTd className="font-mono text-xs text-text-muted">{p.tenantId}</SkeuoTd>
                <SkeuoTd>
                  <SkeuoBadge tone={TONE[p.status] || "muted"}>{p.status}</SkeuoBadge>
                </SkeuoTd>
                <SkeuoTd className="text-xs text-text-muted">{formatWhen(p.createdAt)}</SkeuoTd>
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
                  {(p.status === "paid" || p.status === "failed") && (
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
            {purchaseRows.length === 0 && !purchases.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-center py-6 text-text-muted" colSpan={5}>
                  No number purchases found matching current filters.
                </SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>
      </DevCard>
    </div>
  );
}
