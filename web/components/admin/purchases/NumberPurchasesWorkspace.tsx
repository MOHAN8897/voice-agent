"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { adminAction, useAdminResource } from "@/lib/useAdminResource";
import { SkeuoButton } from "@/components/ui/skeuo";
import { relativeTime, type BadgeTone } from "@/components/admin/accounts/model";
import {
  ActionDialog,
  Drawer,
  DrawerSection,
  EmptyState,
  KeyValues,
  Notice,
  StatusBadge,
  TextInput,
  useDebounced,
} from "@/components/admin/accounts/ui";

/* ------------------------------------------------------------------ API shapes */

type Issue = {
  code: string;
  scope: "platform" | "tenant" | "number";
  severity: "error" | "warning" | "info";
  title: string;
  detail: string;
  action: string;
  href: string | null;
};

type Money = { usd: number; inr: number; at: string | null };

type Purchase = {
  purchaseId: string;
  tenantId: string;
  tenantName: string | null;
  e164: string;
  provider: string | null;
  status: Bucket;
  rawStatus: string;
  stuck: boolean;
  createdAt: string | null;
  updatedAt: string | null;
  charged: Money | null;
  refund: { state: "refunded" | "not_charged" | "failed" | "not_needed" | "pending"; amount?: Money };
  job: { status: string; attempts: number; updatedAt: string | null } | null;
  issue: Issue | null;
  carrier: { errorType?: string | null; providerStatus?: number | null; context?: Record<string, unknown> | null } | null;
  canRetry: boolean;
  canRefund: boolean;
  timeline?: Array<{ at: string | null; kind: string; label: string; detail?: string | null; actor?: string; tone: string }>;
};

type Refusal = {
  id: string;
  at: string | null;
  tenantId: string | null;
  tenantName: string | null;
  e164: string;
  code: string;
  platform: boolean;
  context: Record<string, unknown> | null;
  issue: Issue | null;
};

type Alert = Issue & {
  filter?: Bucket;
  affected?: { count: number; tenants: string[]; numbers: string[]; lastAt: string | null };
};

type Health = {
  provider: string;
  configured: boolean;
  rent: { inr: number; usd: number };
  carrierBalance: { ok: boolean; balance?: number; currency?: string } | null;
  inventoryPricing: { ok: boolean; inventoryCount?: number; pricedCount?: number; aboveRentCount?: number; cheapestInr?: number | null } | null;
  alerts: Alert[];
  counts: Record<Bucket, number>;
  refusalsLast7Days: number;
  checkedAt: string;
};

type Bucket = "succeeded" | "provisioning" | "needs_attention" | "failed" | "refunded";
type View = Bucket | "" | "refused";

const VIEWS: Array<{ id: View; label: string }> = [
  { id: "", label: "All" },
  { id: "needs_attention", label: "Needs attention" },
  { id: "provisioning", label: "Provisioning" },
  { id: "succeeded", label: "Succeeded" },
  { id: "refunded", label: "Refunded" },
  { id: "failed", label: "Failed" },
  { id: "refused", label: "Refused before charge" },
];

const BUCKET_LABEL: Record<Bucket, string> = {
  succeeded: "Succeeded",
  provisioning: "Provisioning",
  needs_attention: "Needs attention",
  failed: "Failed",
  refunded: "Refunded",
};

const BUCKET_TONE: Record<Bucket, BadgeTone> = {
  succeeded: "success",
  provisioning: "info",
  needs_attention: "error",
  failed: "muted",
  refunded: "warning",
};

const REFUND_LABEL: Record<Purchase["refund"]["state"], string> = {
  refunded: "Refunded",
  not_charged: "Not charged",
  failed: "Refund failed",
  not_needed: "—",
  pending: "Held (decide)",
};

const inr = (v: number | null | undefined) =>
  v == null ? "—" : `₹${Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function severityTone(severity: string): "error" | "warning" | "info" {
  return severity === "error" ? "error" : severity === "warning" ? "warning" : "info";
}

function contextLine(ctx: Record<string, unknown> | null | undefined): string | null {
  if (!ctx) return null;
  const parts: string[] = [];
  const cur = String(ctx.currency ?? "INR") === "INR" ? "₹" : "$";
  if (ctx.carrierBalance != null) parts.push(`Vobiz balance ${cur}${Number(ctx.carrierBalance).toFixed(2)}`);
  if (ctx.carrierRequired != null) parts.push(`needed ${cur}${Number(ctx.carrierRequired).toFixed(2)}`);
  if (ctx.carrierPrice != null) parts.push(`Vobiz price ${cur}${Number(ctx.carrierPrice).toFixed(2)}`);
  if (ctx.retailPrice != null) parts.push(`rent ${cur}${Number(ctx.retailPrice).toFixed(2)}`);
  if (ctx.errorType) parts.push(String(ctx.errorType));
  return parts.length ? parts.join(" · ") : null;
}

/* ------------------------------------------------------------------ page */

/**
 * Number purchases: every attempt to buy a number, what happened to the money,
 * and the platform problems (Vobiz balance, rent below Vobiz price, credentials)
 * that stop every tenant at once.
 *
 * URL: ?status=<bucket|refused>&q=<search>&open=<purchaseId>
 */
export function NumberPurchasesWorkspace() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const view = (params.get("status") ?? "") as View;
  const open = params.get("open") ?? "";
  const [q, setQ] = useState(params.get("q") ?? "");
  const debouncedQ = useDebounced(q, 300);
  const [token, setToken] = useState(0);

  const replace = useCallback(
    (mutate: (p: URLSearchParams) => void) => {
      const next = new URLSearchParams(params.toString());
      mutate(next);
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router]
  );

  const health = useAdminResource<Health>("/api/dev/admin/number-purchases/health", [token]);
  const listPath =
    view === "refused"
      ? null
      : `/api/dev/admin/number-purchases?limit=200${view ? `&status=${view}` : ""}${debouncedQ ? `&q=${encodeURIComponent(debouncedQ)}` : ""}`;
  const list = useAdminResource<{ items: Purchase[]; total: number; counts: Record<Bucket, number> }>(listPath, [token]);
  const refusals = useAdminResource<{ items: Refusal[]; total: number; windowDays: number }>(
    view === "refused" ? "/api/dev/admin/number-purchases/refusals?limit=200" : null,
    [token]
  );
  const counts = health.data?.counts ?? list.data?.counts;
  const refresh = () => setToken((t) => t + 1);

  const refusalRows = useMemo(() => {
    const needle = debouncedQ.trim().toLowerCase();
    const rows = refusals.data?.items ?? [];
    return needle ? rows.filter((r) => `${r.e164} ${r.tenantName ?? ""} ${r.code}`.toLowerCase().includes(needle)) : rows;
  }, [refusals.data, debouncedQ]);

  return (
    <div className="space-y-4 px-6 py-5" data-testid="number-purchases-page">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">Number purchases</h1>
          <p className="mt-1 max-w-2xl text-sm text-text-muted">
            Every number a tenant tried to buy: what was charged, what was refunded, and why anything failed. Platform problems that block
            every tenant are listed first.
          </p>
        </div>
        <SkeuoButton variant="secondary" size="sm" onClick={refresh} data-testid="purchases-refresh">
          Refresh
        </SkeuoButton>
      </header>

      <PlatformHealth health={health.data} error={health.error} loading={health.loading} onFilter={(f) => replace((p) => p.set("status", f))} />

      <section className="space-y-3 rounded-skeuo-md border border-surface-border-subtle bg-surface-panel p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-1" role="tablist" aria-label="Purchase status">
            {VIEWS.map((v) => {
              const count = v.id === "" ? undefined : v.id === "refused" ? health.data?.refusalsLast7Days : counts?.[v.id as Bucket];
              const active = view === v.id;
              return (
                <button
                  key={v.id || "all"}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  data-testid={`purchases-filter-${v.id || "all"}`}
                  onClick={() => replace((p) => (v.id ? p.set("status", v.id) : p.delete("status")))}
                  className={cn(
                    "inline-flex min-h-9 items-center gap-1.5 rounded-skeuo-sm px-3 text-sm transition-colors",
                    active ? "bg-accent-primary text-white" : "text-text-muted hover:bg-surface-panel-raised hover:text-text"
                  )}
                >
                  {v.label}
                  {count != null && (
                    <span className={cn("rounded-full px-1.5 font-mono text-[11px]", active ? "bg-white/20" : "bg-surface-panel-inset")}>{count}</span>
                  )}
                </button>
              );
            })}
          </div>
          <div className="w-full sm:w-64">
            <TextInput
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search number, workspace, ID"
              aria-label="Search purchases"
            />
          </div>
        </div>

        {view === "refused" ? (
          <RefusalsTable rows={refusalRows} loading={refusals.loading} error={refusals.error} windowDays={refusals.data?.windowDays ?? 7} />
        ) : (
          <PurchasesTable
            rows={list.data?.items ?? []}
            loading={list.loading}
            error={list.error}
            onOpen={(id) => replace((p) => p.set("open", id))}
          />
        )}
      </section>

      <PurchaseDrawer
        id={open}
        onClose={() => replace((p) => p.delete("open"))}
        onChanged={refresh}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ platform health */

function PlatformHealth({
  health,
  error,
  loading,
  onFilter,
}: {
  health: Health | null;
  error: string | null;
  loading: boolean;
  onFilter: (f: Bucket) => void;
}) {
  if (error) return <Notice tone="error">Could not load platform status: {error}</Notice>;
  if (!health) return loading ? <p className="text-sm text-text-muted">Checking Vobiz balance and pricing…</p> : null;
  const bal = health.carrierBalance;
  const pricing = health.inventoryPricing;
  return (
    <section className="space-y-3" aria-label="Platform status" data-testid="purchases-health">
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <Tile
          label="Vobiz account balance"
          value={bal?.ok ? inr(bal.balance) : health.provider === "vobiz" ? "Unavailable" : "Not used"}
          tone={health.alerts.some((a) => a.code === "carrier_balance_exhausted") ? "error" : undefined}
          testId="tile-carrier-balance"
        />
        <Tile label="Number rent (per month)" value={inr(health.rent.inr)} hint={<Link href="/dev/admin/billing" className="underline">Change in Wallet & rates</Link>} />
        <Tile
          label="Cheapest Vobiz number"
          value={pricing?.ok ? inr(pricing.cheapestInr) : "—"}
          hint={pricing?.ok ? "setup + first month" : undefined}
          tone={pricing?.ok && pricing.cheapestInr != null && pricing.cheapestInr > health.rent.inr ? "error" : undefined}
        />
        <Tile
          label="Hidden from tenants"
          value={pricing?.ok ? `${pricing.aboveRentCount ?? 0} of ${pricing.pricedCount ?? 0}` : "—"}
          hint="priced above rent"
          tone={pricing?.ok && (pricing.aboveRentCount ?? 0) > 0 ? "warning" : undefined}
        />
      </div>
      {health.alerts.length === 0 ? (
        <Notice tone="success">Tenants can buy numbers: the Vobiz balance and rent cover the current inventory, and nothing is waiting on you.</Notice>
      ) : (
        <ul className="space-y-2" data-testid="purchases-alerts">
          {health.alerts.map((a) => (
            <li key={a.code} data-testid={`alert-${a.code}`}>
              <AlertCard alert={a} onFilter={onFilter} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Tile({ label, value, hint, tone, testId }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "error" | "warning"; testId?: string }) {
  return (
    <div
      className={cn(
        "rounded-skeuo-sm border bg-surface-panel p-3",
        tone === "error" ? "border-status-error/40" : tone === "warning" ? "border-status-warning/40" : "border-surface-border-subtle"
      )}
      data-testid={testId}
    >
      <p className="text-[11px] text-text-subtle">{label}</p>
      <p className={cn("mt-1 font-mono text-lg", tone === "error" ? "text-status-error" : "text-text")}>{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-text-muted">{hint}</p>}
    </div>
  );
}

function AlertCard({ alert, onFilter }: { alert: Alert; onFilter: (f: Bucket) => void }) {
  const tone = severityTone(alert.severity);
  const border =
    tone === "error" ? "border-status-error/40 bg-status-error/5" : tone === "warning" ? "border-status-warning/40 bg-status-warning/5" : "border-surface-border-subtle bg-surface-panel";
  return (
    <div className={cn("rounded-skeuo-sm border p-3 text-sm", border)} role={tone === "error" ? "alert" : "status"}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold text-text">{alert.title}</p>
          <p className="mt-0.5 text-text-muted">{alert.detail}</p>
          <p className="mt-1 text-text">
            <span className="font-medium">What to do: </span>
            {alert.action}
          </p>
          {alert.affected && alert.affected.count > 0 && (
            <p className="mt-1 text-xs text-text-muted" data-testid="alert-affected">
              {alert.affected.count} attempt{alert.affected.count === 1 ? "" : "s"} affected
              {alert.affected.tenants.length ? ` · ${alert.affected.tenants.join(", ")}` : ""}
              {alert.affected.numbers.length ? ` · ${alert.affected.numbers.join(", ")}` : ""}
              {alert.affected.lastAt ? ` · last ${relativeTime(alert.affected.lastAt)}` : ""}
            </p>
          )}
        </div>
        <div className="flex shrink-0 gap-2">
          {alert.filter && (
            <SkeuoButton size="sm" variant="secondary" onClick={() => onFilter(alert.filter as Bucket)}>
              Show them
            </SkeuoButton>
          )}
          {alert.href && (
            <Link href={alert.href} className="inline-flex min-h-8 items-center rounded-skeuo-sm border border-surface-border px-3 text-xs font-medium text-text hover:bg-surface-panel-raised">
              Fix it
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ tables */

const th = "px-3 py-2 text-left text-[11px] font-medium text-text-subtle";
const td = "px-3 py-2 align-top";

function PurchasesTable({ rows, loading, error, onOpen }: { rows: Purchase[]; loading: boolean; error: string | null; onOpen: (id: string) => void }) {
  if (error) return <Notice tone="error">{error}</Notice>;
  if (!rows.length) {
    return loading ? (
      <p className="py-6 text-center text-sm text-text-muted">Loading purchases…</p>
    ) : (
      <div className="py-8">
        <EmptyState title="No purchases here" body="Nothing matches this filter. Purchases refused before any charge are under “Refused before charge”." />
      </div>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] text-sm" data-testid="purchases-table">
        <thead className="border-b border-surface-border-subtle">
          <tr>
            <th className={th}>Number</th>
            <th className={th}>Workspace</th>
            <th className={th}>Status</th>
            <th className={th}>Why</th>
            <th className={th}>Charged</th>
            <th className={th}>Refund</th>
            <th className={th}>When</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr
              key={p.purchaseId}
              className="cursor-pointer border-b border-surface-border-subtle/60 hover:bg-surface-panel-raised"
              onClick={() => onOpen(p.purchaseId)}
              data-testid="purchase-row"
            >
              <td className={cn(td, "font-mono")}>
                <button type="button" className="underline-offset-2 hover:underline" onClick={(e) => { e.stopPropagation(); onOpen(p.purchaseId); }}>
                  {p.e164}
                </button>
              </td>
              <td className={td}>{p.tenantName || <span className="font-mono text-xs text-text-muted">{p.tenantId.slice(0, 8)}</span>}</td>
              <td className={td}>
                <StatusBadge tone={BUCKET_TONE[p.status]}>{BUCKET_LABEL[p.status]}</StatusBadge>
              </td>
              <td className={cn(td, "max-w-[280px] text-text-muted")}>{p.issue?.title ?? "—"}</td>
              <td className={cn(td, "font-mono text-xs")}>{p.charged ? inr(p.charged.inr) : "—"}</td>
              <td className={cn(td, "text-xs", p.refund.state === "failed" && "text-status-error")}>{REFUND_LABEL[p.refund.state]}</td>
              <td className={cn(td, "text-xs text-text-muted")} title={p.createdAt ?? ""}>{relativeTime(p.createdAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RefusalsTable({ rows, loading, error, windowDays }: { rows: Refusal[]; loading: boolean; error: string | null; windowDays: number }) {
  if (error) return <Notice tone="error">{error}</Notice>;
  if (!rows.length) {
    return loading ? (
      <p className="py-6 text-center text-sm text-text-muted">Loading refusals…</p>
    ) : (
      <div className="py-8">
        <EmptyState title="No refused purchases" body={`No buy attempt was refused in the last ${windowDays} days.`} />
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <p className="text-xs text-text-muted">
        Buy attempts stopped before the wallet was charged, last {windowDays} days. Tenants saw a plain message; the reason below is the real one.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm" data-testid="refusals-table">
          <thead className="border-b border-surface-border-subtle">
            <tr>
              <th className={th}>When</th>
              <th className={th}>Workspace</th>
              <th className={th}>Number</th>
              <th className={th}>Reason</th>
              <th className={th}>Details</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-surface-border-subtle/60" data-testid="refusal-row">
                <td className={cn(td, "text-xs text-text-muted")} title={r.at ?? ""}>{relativeTime(r.at)}</td>
                <td className={td}>{r.tenantName ?? "—"}</td>
                <td className={cn(td, "font-mono")}>{r.e164}</td>
                <td className={td}>
                  <span className="flex flex-wrap items-center gap-1.5">
                    {r.platform && <StatusBadge tone="error">Platform</StatusBadge>}
                    <span>{r.issue?.title ?? r.code}</span>
                  </span>
                  {r.platform && r.issue?.action && <span className="mt-0.5 block text-xs text-text-muted">{r.issue.action}</span>}
                </td>
                <td className={cn(td, "text-xs text-text-muted")}>{contextLine(r.context) ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ drawer */

function PurchaseDrawer({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const [token, setToken] = useState(0);
  const detail = useAdminResource<Purchase>(id ? `/api/dev/admin/number-purchases/${encodeURIComponent(id)}` : null, [token]);
  const [action, setAction] = useState<"retry" | "refund" | null>(null);
  const p = detail.data;

  return (
    <>
      <Drawer
        open={Boolean(id)}
        title={p?.e164 ?? "Purchase"}
        subtitle={p ? `${p.tenantName ?? p.tenantId} · ${p.purchaseId}` : undefined}
        badges={p ? <StatusBadge tone={BUCKET_TONE[p.status]}>{BUCKET_LABEL[p.status]}</StatusBadge> : undefined}
        onClose={onClose}
        footer={
          p && (p.canRetry || p.canRefund) ? (
            <div className="flex flex-wrap justify-end gap-2">
              {p.canRetry && (
                <SkeuoButton variant="secondary" onClick={() => setAction("retry")} data-testid="purchase-retry">
                  Retry provisioning
                </SkeuoButton>
              )}
              {p.canRefund && (
                <SkeuoButton variant="primary" onClick={() => setAction("refund")} data-testid="purchase-refund">
                  Refund {p.charged ? inr(p.charged.inr) : ""}
                </SkeuoButton>
              )}
            </div>
          ) : undefined
        }
      >
        {detail.error && <Notice tone="error">{detail.error}</Notice>}
        {!p && detail.loading && <p className="text-sm text-text-muted">Loading…</p>}
        {p && (
          <>
            {p.issue && (
              <DrawerSection title="What went wrong">
                <div className="space-y-1.5 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel p-3 text-sm" data-testid="purchase-issue">
                  <p className="font-semibold text-text">{p.issue.title}</p>
                  <p className="text-text-muted">{p.issue.detail}</p>
                  <p className="text-text">
                    <span className="font-medium">What to do: </span>
                    {p.issue.action}
                  </p>
                  {p.issue.href && (
                    <Link href={p.issue.href} className="text-xs font-medium text-accent-primary underline">
                      Open the setting
                    </Link>
                  )}
                </div>
              </DrawerSection>
            )}
            <DrawerSection title="Money">
              <KeyValues
                items={[
                  ["Charged", p.charged ? `${inr(p.charged.inr)} ($${p.charged.usd.toFixed(2)})` : "Nothing"],
                  ["Refund", p.refund.amount ? `${inr(p.refund.amount.inr)} · ${relativeTime(p.refund.amount.at)}` : REFUND_LABEL[p.refund.state]],
                ]}
              />
            </DrawerSection>
            <DrawerSection title="Carrier" hint="Operator-only. Tenants never see these details.">
              <KeyValues
                items={[
                  ["Provider", p.provider ?? "—"],
                  ["Job", p.job ? `${p.job.status} · ${p.job.attempts} attempt${p.job.attempts === 1 ? "" : "s"}` : "—"],
                  ["Error", p.carrier?.errorType ? `${p.carrier.errorType}${p.carrier.providerStatus ? ` (HTTP ${p.carrier.providerStatus})` : ""}` : "—"],
                  ["Figures", contextLine(p.carrier?.context) ?? "—"],
                ]}
              />
            </DrawerSection>
            <DrawerSection title="Timeline">
              <ol className="space-y-2 text-sm" data-testid="purchase-timeline">
                {(p.timeline ?? []).map((ev, i) => (
                  <li key={`${ev.kind}-${i}`} className="flex gap-3">
                    <span
                      className={cn(
                        "mt-1.5 h-2 w-2 shrink-0 rounded-full",
                        ev.tone === "error" ? "bg-status-error" : ev.tone === "warning" ? "bg-status-warning" : ev.tone === "success" ? "bg-status-success" : "bg-text-subtle"
                      )}
                      aria-hidden="true"
                    />
                    <div className="min-w-0">
                      <p className="text-text">{ev.label}</p>
                      {ev.detail && <p className="text-xs text-text-muted">{ev.detail}</p>}
                      <p className="text-[11px] text-text-subtle" title={ev.at ?? ""}>
                        {ev.at ? new Date(ev.at).toLocaleString() : "—"}
                        {ev.actor && ev.actor !== "system" ? ` · ${ev.actor}` : ""}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            </DrawerSection>
          </>
        )}
      </Drawer>

      <ActionDialog
        open={action !== null && Boolean(p)}
        title={action === "retry" ? "Retry provisioning" : "Refund this purchase"}
        action={action === "retry" ? "retry" : "refund"}
        count={1}
        confirmLabel={action === "retry" ? "Retry now" : "Refund to wallet"}
        description={
          action === "retry" ? (
            "The job is queued again with fresh attempts. It first checks whether the Vobiz account already owns the number, so it never buys it twice."
          ) : (
            <>
              The charge goes back to the tenant&rsquo;s wallet and the purchase is closed; it can never be provisioned afterwards.
              {p?.rawStatus === "needs_attention" && (
                <span className="mt-2 block font-medium text-status-error">
                  Vobiz may have sold us this number. Check the Vobiz console first: if the account owns it, retry instead.
                </span>
              )}
            </>
          )
        }
        onClose={(changed) => {
          setAction(null);
          if (changed) {
            setToken((t) => t + 1);
            onChanged();
          }
        }}
        onRun={async (reason) => {
          if (!p) return;
          await adminAction(`/api/dev/admin/number-purchases/${encodeURIComponent(p.purchaseId)}/${action}`, { body: { reason } });
        }}
      />
    </>
  );
}
