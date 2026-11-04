"use client";

import { useMemo, useState } from "react";
import { AdminConfirmDialog } from "@/components/admin/AdminConfirmDialog";
import { AdminError, AdminLoading, AdminPageHeader, AdminStat } from "@/components/admin/AdminNav";
import { relativeTime, type BadgeTone } from "@/components/admin/accounts/model";
import { EmptyState, Field, Modal, Notice, StatusBadge, TextInput } from "@/components/admin/accounts/ui";
import { ChannelPricingPanel } from "@/components/dev/voice-stack/ChannelPricingPanel";
import { SkeuoButton } from "@/components/ui/skeuo";
import { adminAction, useAdminResource } from "@/lib/useAdminResource";

const BASE = "/api/dev/admin/capacity";

type Signal = { level: "critical" | "warning" | "info" | "ok"; code: string; title: string; detail: string; action: string | null };
type Purchase = {
  id: string; requestId: string; resourceType: "concurrent_calls" | "cps"; resourceLabel: string; quantity: number;
  quotedMonthlyCost: string | null; monthlyCost: string | null; currency: string | null;
  status: "pending" | "succeeded" | "failed" | "unknown"; nextBillingDate: string | null; error: string | null;
  actor: string; reason: string; createdAt: string | null;
};
type TenantRow = {
  tenantId: string; name: string; numbers: number; numberChannels: number; paidChannels: number; held: number;
  included: number; cap: number; activeNow: number; peak7d: number; rejected7d: number; queued7d: number; incidents24h: number;
};
type Incident = { kind: string; scope: string; label: string; count: number; tenantId: string | null; tenantName: string | null; detail: string | null; lastAt: string };
type Approval = { purchaseId: string; tenantId: string; tenantName: string; e164: string; createdAt: string | null };
type Policy = { approvalMode: "auto" | "manual"; autoBuy: boolean; autoBuyMonthlyBudgetInr: string; autoBuySpent30d: string; version: number | null; updatedAt?: string | null };
type Overview = {
  configured: boolean;
  settings: { channelsPerNumber?: number; concurrencyBlockSize?: number; priceInrPerChannel?: number };
  concurrency: {
    owned: number; vobizLimit: number | null; vobizLive: number | null; held: number; heldByNumbers: number; heldByPaid: number;
    freeToHold: number; numbersSellable: number | null; live: number; available: number; peak7d: number; peak30d: number;
  };
  cps: { owned: number; vobizLimit: number | null; peak24h: number; paced24h: number };
  vobiz: { available: boolean };
  estimate: { required: number; recommended: number; shortfall: number; buy: number; blockSize: number; utilizationPct: number };
  signals: Signal[];
  incidents: Incident[];
  tenants: TenantRow[];
  purchases: Purchase[];
  policy: Policy;
  approvals: Approval[];
};
type Price = { available: boolean; monthlyCost?: string; currency?: string; reason?: string; message?: string };
type PreviewResponse = { price: Price; balance: { available: boolean; balance?: string; currency?: string }; blocked: Purchase | null };

const LEVEL_TONE: Record<Signal["level"], "error" | "warning" | "info" | "success"> = {
  critical: "error", warning: "warning", info: "info", ok: "success",
};
const PURCHASE_TONE: Record<Purchase["status"], BadgeTone> = { succeeded: "success", failed: "error", unknown: "warning", pending: "warning" };
const PURCHASE_LABEL: Record<Purchase["status"], string> = { succeeded: "Bought", failed: "Not bought", unknown: "No answer: check Vobiz", pending: "In progress" };

function inr(value: string | number | null | undefined) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function newRequestId() {
  return typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

/* ------------------------------------------------------------------ buy dialog */

const RESOURCE_COPY = {
  concurrent_calls: {
    title: "Concurrent calls",
    unit: "calls at once",
    what: "How many calls can run at the same time across every workspace (inbound and outbound). Each number a tenant buys holds one.",
    when: "Buy when numbers are being queued for capacity, calls show \"all lines busy\", or the page shows amber/red.",
  },
  cps: {
    title: "Calls per second (CPS)",
    unit: "new calls per second",
    what: "How fast new outbound calls can start across every workspace. It does not add simultaneous calls.",
    when: "Buy only when campaigns are too slow (\"Calls waited for dialling speed\" keeps appearing). 1 CPS starts 60 calls a minute.",
  },
} as const;

function BuyDialog({
  resource, suggested, blockSize, owned, onClose, onDone,
}: {
  resource: "concurrent_calls" | "cps"; suggested: number; blockSize: number; owned: number;
  onClose: () => void; onDone: (message: string) => void;
}) {
  const copy = RESOURCE_COPY[resource];
  const [quantity, setQuantity] = useState(String(Math.max(1, suggested)));
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [confirm, setConfirm] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requestId] = useState(newRequestId);
  const qty = Number(quantity);
  const validQty = Number.isInteger(qty) && qty >= 1 && qty <= 10000;
  const offBlock = resource === "concurrent_calls" && validQty && blockSize > 1 && qty % blockSize !== 0;

  async function getPrice() {
    if (!validQty) { setError("Enter a whole number between 1 and 10000."); return; }
    setBusy(true); setError(null); setPreview(null); setConfirm("");
    try {
      setPreview(await adminAction<PreviewResponse>(`${BASE}/preview`, { body: { resourceType: resource, quantity: qty } }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not get the Vobiz price.");
    } finally { setBusy(false); }
  }

  async function buy() {
    if (!preview?.price.available || !preview.price.monthlyCost) return;
    if (Number(confirm) !== qty) { setError(`Type ${qty} to confirm.`); return; }
    if (reason.trim().length < 8) { setError("Write a reason of at least 8 characters (kept in the audit log)."); return; }
    setBusy(true); setError(null);
    try {
      const res = await adminAction<{ ok: boolean; purchase: Purchase; applied?: { applied: boolean; platformCapacity?: number; platformCps?: number; message?: string } | null }>(
        `${BASE}/purchase`,
        { body: { resourceType: resource, quantity: qty, expectedMonthlyCost: preview.price.monthlyCost, requestId,
                  confirmQuantity: Number(confirm), reason: reason.trim() } },
      );
      if (res.ok) {
        const applied = res.applied?.applied
          ? resource === "cps" ? ` Dialling speed is now ${res.applied.platformCps} CPS.` : ` Capacity is now ${res.applied.platformCapacity} calls.`
          : res.applied?.message ? ` ${res.applied.message}` : "";
        onDone(`Bought ${qty} ${copy.unit} for ${inr(res.purchase.monthlyCost || preview.price.monthlyCost)} a month.${applied}`);
      } else if (res.purchase.status === "unknown") {
        setError(res.purchase.error || "Vobiz did not answer. Check the purchase history before trying again.");
      } else {
        setError(res.purchase.error || "Vobiz refused the purchase. Nothing was bought.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "The purchase failed. Nothing was bought.");
    } finally { setBusy(false); }
  }

  const balanceLow = Boolean(preview?.balance.available && preview.price.monthlyCost &&
    Number(preview.balance.balance) < Number(preview.price.monthlyCost));

  return (
    <Modal open wide title={`Buy ${copy.title.toLowerCase()} on Vobiz`} onClose={onClose}>
      <div className="space-y-3 text-sm" data-testid="capacity-buy-dialog">
        <Notice tone="info">
          <strong className="text-text">What this is:</strong> {copy.what}
          <br /><strong className="text-text">When to buy:</strong> {copy.when}
        </Notice>
        <ol className="list-decimal space-y-1 pl-5 text-xs text-text-muted">
          <li>Enter how many to add{resource === "concurrent_calls" ? ` (Vobiz sells concurrency in blocks of ${blockSize})` : ""}.</li>
          <li>Get the live Vobiz price. Nothing is bought yet.</li>
          <li>Type the quantity again and a reason, then buy. Vobiz charges the first month from the Vobiz balance at once and renews every 30 days.</li>
        </ol>
        <Field label={`How many to add (${copy.unit})`} hint={`You have ${owned} now; after buying: ${validQty ? owned + qty : "—"}.`}>
          <TextInput type="number" min={1} step={1} value={quantity} onChange={(e) => { setQuantity(e.target.value); setPreview(null); }} />
        </Field>
        {offBlock && <Notice tone="warning">{qty} is not a multiple of {blockSize}. Vobiz may refuse it; the price check will tell you.</Notice>}
        {preview?.blocked && (
          <Notice tone="error">An earlier purchase got no answer from Vobiz. Mark it as bought or not bought in the history below before buying again.</Notice>
        )}
        {preview && !preview.price.available && (
          <Notice tone="error">{preview.price.message || "Vobiz could not price this right now. Nothing was bought."}</Notice>
        )}
        {preview?.price.available && (
          <div className="rounded-skeuo-sm border border-surface-border bg-surface-panel-inset p-3 text-xs" data-testid="capacity-buy-price">
            <div className="flex justify-between"><span>Vobiz price</span><span className="font-mono text-text">{inr(preview.price.monthlyCost)} / 30 days</span></div>
            <div className="flex justify-between"><span>Vobiz balance</span><span className="font-mono text-text">{preview.balance.available ? inr(preview.balance.balance) : "unavailable"}</span></div>
            {balanceLow && <p className="mt-2 text-status-error">The Vobiz balance is lower than the price: top up Vobiz first or the purchase will fail.</p>}
          </div>
        )}
        {preview?.price.available && !preview.blocked && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={`Type ${qty} to confirm`}>
              <TextInput inputMode="numeric" value={confirm} onChange={(e) => setConfirm(e.target.value)} data-testid="capacity-buy-confirm" />
            </Field>
            <Field label="Reason (audit log)">
              <TextInput value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. 4 numbers waiting for capacity" />
            </Field>
          </div>
        )}
        {error && <Notice tone="error">{error}</Notice>}
        <div className="flex justify-end gap-2 pt-1">
          <SkeuoButton variant="ghost" onClick={onClose} disabled={busy}>Cancel</SkeuoButton>
          {!preview?.price.available || preview.blocked ? (
            <SkeuoButton variant="primary" onClick={() => void getPrice()} loading={busy} disabled={busy || !validQty}>Get Vobiz price</SkeuoButton>
          ) : (
            <SkeuoButton variant="primary" onClick={() => void buy()} loading={busy}
              disabled={busy || balanceLow || Number(confirm) !== qty || reason.trim().length < 8} data-testid="capacity-buy-submit">
              Buy {qty} for {inr(preview.price.monthlyCost)} / month
            </SkeuoButton>
          )}
        </div>
      </div>
    </Modal>
  );
}

/* ------------------------------------------------------------------ approval mode */

function PolicyCard({ policy, onSaved }: { policy: Policy; onSaved: (m: string) => void }) {
  const [mode, setMode] = useState(policy.approvalMode);
  const [autoBuy, setAutoBuy] = useState(policy.autoBuy);
  const [budget, setBudget] = useState(policy.autoBuyMonthlyBudgetInr || "0");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirty = mode !== policy.approvalMode || autoBuy !== policy.autoBuy || Number(budget) !== Number(policy.autoBuyMonthlyBudgetInr);

  async function save() {
    setBusy(true); setError(null);
    try {
      await adminAction(`${BASE}/policy`, { method: "PUT", body: { approvalMode: mode, autoBuy, autoBuyMonthlyBudgetInr: Number(budget) || 0, reason: reason.trim() } });
      setReason("");
      onSaved("Number approval settings saved.");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save."); } finally { setBusy(false); }
  }

  return (
    <section className="card-surface space-y-3 p-4" data-testid="capacity-policy">
      <div>
        <h2 className="text-sm font-semibold text-text">How new numbers get their channel</h2>
        <p className="mt-0.5 text-xs text-text-muted">Tenants only buy and pay for a number. Each number holds one call channel from your Vobiz concurrency.</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {([
          ["auto", "Automatic", "Approved straight away when a channel is free. If none is free, auto-buy (below) or the approval queue."],
          ["manual", "Admin approval", "Every purchase waits in the queue below. Approving holds the channel and activates the number; rejecting refunds the tenant."],
        ] as const).map(([value, label, help]) => (
          <label key={value} className={`cursor-pointer rounded-skeuo-sm border p-3 text-xs ${mode === value ? "border-accent-primary bg-accent-primary/10" : "border-surface-border"}`}>
            <input type="radio" name="approval-mode" className="mr-2" checked={mode === value} onChange={() => setMode(value)} />
            <span className="font-semibold text-text">{label}</span>
            <span className="mt-1 block text-text-muted">{help}</span>
          </label>
        ))}
      </div>
      <div className={`grid gap-3 sm:grid-cols-[auto_1fr] ${mode === "manual" ? "opacity-50" : ""}`}>
        <label className="flex items-center gap-2 text-xs text-text">
          <input type="checkbox" checked={autoBuy} disabled={mode === "manual"} onChange={(e) => setAutoBuy(e.target.checked)} />
          Auto-buy Vobiz concurrency when a number needs a channel
        </label>
        <Field label="Auto-buy limit (₹ of Vobiz monthly cost, in total)"
          hint={`Bundles bought by auto-buy cost ${inr(policy.autoBuySpent30d)} a month now (they renew every 30 days). Auto-buy never takes this above the limit; numbers wait in the queue instead.`}>
          <TextInput type="number" min={0} step={1} value={budget} disabled={mode === "manual" || !autoBuy} onChange={(e) => setBudget(e.target.value)} />
        </Field>
      </div>
      {dirty && (
        <Field label="Reason for this change (audit log)">
          <TextInput value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Switching to approval during launch" />
        </Field>
      )}
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex justify-end">
        <SkeuoButton variant="primary" size="sm" disabled={!dirty || busy || reason.trim().length < 8} loading={busy} onClick={() => void save()}>
          Save approval settings
        </SkeuoButton>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ page */

export function CallCapacityWorkspace() {
  const { data, error, loading, reload } = useAdminResource<Overview>(BASE);
  const [buying, setBuying] = useState<null | "concurrent_calls" | "cps">(null);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [rejecting, setRejecting] = useState<Approval | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const done = (text: string) => { setNotice({ tone: "success", text }); setBuying(null); void reload(); };
  const fail = (e: unknown) => setNotice({ tone: "error", text: e instanceof Error ? e.message : "That did not work." });

  async function approve(row: Approval) {
    setBusyId(row.purchaseId);
    try {
      await adminAction(`${BASE}/approvals/${row.purchaseId}/approve`);
      done(`Approved ${row.e164} for ${row.tenantName}. Its channel is held and the number is being activated.`);
    } catch (e) { fail(e); } finally { setBusyId(null); }
  }

  async function reject(statement: string) {
    if (!rejecting) return;
    setBusyId(rejecting.purchaseId);
    try {
      await adminAction(`${BASE}/approvals/${rejecting.purchaseId}/reject`, { body: { reason: statement } });
      done(`Rejected ${rejecting.e164}. ${rejecting.tenantName} was refunded in full.`);
      setRejecting(null);
    } catch (e) { fail(e); } finally { setBusyId(null); }
  }

  async function resolve(p: Purchase, outcome: "succeeded" | "failed") {
    setBusyId(p.id);
    try {
      await adminAction(`${BASE}/purchases/${p.id}/resolve`, { body: { outcome } });
      done(outcome === "succeeded" ? "Marked as bought; limits updated from Vobiz." : "Marked as not bought. You can buy again.");
    } catch (e) { fail(e); } finally { setBusyId(null); }
  }

  async function sync() {
    setSyncing(true);
    try {
      const res = await adminAction<{ applied: boolean; platformCapacity?: number; platformCps?: number; message?: string }>(
        `${BASE}/sync`, { body: { reason: "Use the limits the Vobiz account allows" } });
      done(res.applied ? `Now using the Vobiz limits: ${res.platformCapacity} calls, ${res.platformCps} CPS.` : res.message || "Already matches Vobiz.");
    } catch (e) { fail(e); } finally { setSyncing(false); }
  }

  const c = data?.concurrency;
  const est = data?.estimate;
  const utilTone = !est ? "default" : est.utilizationPct >= 90 ? "warn" : est.utilizationPct >= 70 ? "warn" : "good";
  const vobizMismatch = Boolean(c && c.vobizLimit != null && c.vobizLimit !== c.owned) ||
    Boolean(data && data.cps.vobizLimit != null && data.cps.vobizLimit !== data.cps.owned);
  const incidents = useMemo(() => data?.incidents ?? [], [data]);

  return (
    <div>
      <AdminPageHeader
        title="Call capacity"
        description="Vobiz concurrency (calls at once) and CPS (new calls per second) are one shared pool for every workspace. Each number a tenant buys holds one channel from it. This page shows what you own, what tenants need, and when to buy more."
        actions={<>
          <SkeuoButton size="sm" variant="ghost" onClick={() => void reload()}>Refresh</SkeuoButton>
          <SkeuoButton size="sm" onClick={() => setBuying("cps")}>Buy CPS</SkeuoButton>
          <SkeuoButton size="sm" variant="primary" onClick={() => setBuying("concurrent_calls")} data-testid="capacity-buy-concurrency">Buy concurrency</SkeuoButton>
        </>}
      />
      <AdminError error={error} />
      <AdminLoading loading={loading && !data} />
      {notice && <div className="mb-4"><Notice tone={notice.tone}>{notice.text}</Notice></div>}

      {data && c && est && (
        <div className="space-y-6">
          <section className="space-y-2" data-testid="capacity-signals">
            {data.signals.map((s) => (
              <Notice key={s.code} tone={LEVEL_TONE[s.level]}>
                <strong className="text-text">{s.title}.</strong> {s.detail}
                {s.action && <span className="block pt-1 font-medium">Next step: {s.action}.</span>}
              </Notice>
            ))}
          </section>

          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="capacity-stats">
            <AdminStat label="Concurrency owned" value={c.owned} hint={c.vobizLimit != null ? `Vobiz account allows ${c.vobizLimit}` : "Vobiz limit unavailable"}
              tone={c.vobizLimit != null && c.owned > c.vobizLimit ? "warn" : "default"} />
            <AdminStat label="Held for tenants" value={`${c.held} / ${c.owned}`} tone={utilTone}
              hint={`${c.heldByNumbers} for numbers · ${c.heldByPaid} paid channels`} />
            <AdminStat label="Free to hold" value={c.freeToHold} tone={c.freeToHold ? "good" : "warn"}
              hint={c.numbersSellable != null ? `${c.numbersSellable} more numbers can be sold` : "Numbers hold no channels"} />
            <AdminStat label="Live calls now" value={`${c.live} / ${c.owned}`} hint={`Busiest day: ${c.peak7d} (7d) · ${c.peak30d} (30d)`} />
            <AdminStat label="CPS (new calls / second)" value={data.cps.owned}
              hint={data.cps.vobizLimit != null ? `Vobiz allows ${data.cps.vobizLimit} · peak ${data.cps.peak24h}/s in 24h` : `Peak ${data.cps.peak24h}/s in 24h`}
              tone={data.cps.vobizLimit != null && data.cps.owned > data.cps.vobizLimit ? "warn" : "default"} />
            <AdminStat label="Calls waited for CPS (24h)" value={data.cps.paced24h} tone={data.cps.paced24h ? "warn" : "default"} hint="They retry; nothing is lost" />
            <AdminStat label="Numbers waiting for approval" value={data.approvals.length} tone={data.approvals.length ? "warn" : "default"} />
            <AdminStat label="Approval mode" value={data.policy.approvalMode === "auto" ? (data.policy.autoBuy ? "Auto + buy" : "Auto") : "Manual"} />
          </section>

          <section className="card-surface p-4" data-testid="capacity-estimate">
            <h2 className="text-sm font-semibold text-text">How much concurrency to own</h2>
            <div className="mt-3 grid gap-3 text-xs sm:grid-cols-4">
              <div><span className="block text-text-subtle">Needed now</span><span className="font-mono text-lg text-text">{est.required}</span>
                <span className="block text-text-muted">the higher of held channels ({c.held}) and the busiest day ({c.peak30d})</span></div>
              <div><span className="block text-text-subtle">Recommended (with 20% headroom)</span><span className="font-mono text-lg text-text">{est.recommended}</span></div>
              <div><span className="block text-text-subtle">You own</span><span className="font-mono text-lg text-text">{c.owned}</span></div>
              <div><span className="block text-text-subtle">Buy now</span>
                <span className={`font-mono text-lg ${est.buy ? "text-status-warning" : "text-status-success"}`}>{est.buy || "Nothing"}</span>
                {est.buy ? <span className="block text-text-muted">{est.buy / est.blockSize} block(s) of {est.blockSize}</span> : null}</div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {est.buy > 0 && <SkeuoButton size="sm" variant="primary" onClick={() => setBuying("concurrent_calls")}>Buy {est.buy} concurrent calls</SkeuoButton>}
              {vobizMismatch && <SkeuoButton size="sm" loading={syncing} onClick={() => void sync()}>Use the Vobiz limits</SkeuoButton>}
            </div>
            <p className="mt-2 text-[11px] text-text-subtle">
              Vobiz sells concurrency in blocks of {est.blockSize} and renews every 30 days. Buying here charges your Vobiz balance; tenants are charged only for their numbers (and any paid channels).
            </p>
          </section>

          <section className="card-surface p-4" data-testid="capacity-approvals">
            <h2 className="text-sm font-semibold text-text">Numbers waiting for approval</h2>
            <p className="mt-0.5 text-xs text-text-muted">The tenant has paid. Approve to hold its channel and activate it; reject to refund them in full. Anything not approved within 3 days is refunded automatically.</p>
            {data.approvals.length === 0 ? (
              <p className="mt-3 text-xs text-text-subtle">Nothing is waiting.</p>
            ) : (
              <table className="mt-3 w-full text-xs">
                <thead><tr className="text-left text-text-subtle"><th className="py-1">Workspace</th><th>Number</th><th>Waiting</th><th className="text-right">Decision</th></tr></thead>
                <tbody>
                  {data.approvals.map((row) => (
                    <tr key={row.purchaseId} className="border-t border-surface-border-subtle">
                      <td className="py-2 text-text">{row.tenantName}</td>
                      <td className="font-mono">{row.e164}</td>
                      <td className="text-text-muted">{row.createdAt ? relativeTime(row.createdAt) : "—"}</td>
                      <td className="text-right">
                        <div className="flex justify-end gap-2">
                          <SkeuoButton size="sm" variant="ghost" disabled={busyId === row.purchaseId} onClick={() => setRejecting(row)}>Reject & refund</SkeuoButton>
                          <SkeuoButton size="sm" variant="primary" loading={busyId === row.purchaseId} onClick={() => void approve(row)}>Approve</SkeuoButton>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {data.approvals.length > c.freeToHold && c.freeToHold >= 0 && data.approvals.length > 0 && (
              <div className="mt-3"><Notice tone="warning">
                {c.freeToHold} channel(s) are free for {data.approvals.length} waiting number(s). Buy concurrency first, or approvals beyond {c.freeToHold} are refused.
              </Notice></div>
            )}
          </section>

          <PolicyCard key={`${data.policy.version}`} policy={data.policy} onSaved={done} />

          <section className="card-surface p-4" data-testid="capacity-purchases">
            <h2 className="text-sm font-semibold text-text">Vobiz bundles bought here</h2>
            {data.purchases.length === 0 ? (
              <p className="mt-3 text-xs text-text-subtle">None yet.</p>
            ) : (
              <table className="mt-3 w-full text-xs">
                <thead><tr className="text-left text-text-subtle"><th className="py-1">When</th><th>What</th><th>Monthly cost</th><th>Status</th><th>By</th><th /></tr></thead>
                <tbody>
                  {data.purchases.map((p) => (
                    <tr key={p.id} className="border-t border-surface-border-subtle align-top">
                      <td className="py-2 text-text-muted">{p.createdAt ? relativeTime(p.createdAt) : "—"}</td>
                      <td className="text-text">{p.quantity} {p.resourceLabel}<span className="block text-text-subtle">{p.reason}</span></td>
                      <td className="font-mono">{inr(p.monthlyCost || p.quotedMonthlyCost)}{p.nextBillingDate ? <span className="block text-text-subtle">renews {p.nextBillingDate.slice(0, 10)}</span> : null}</td>
                      <td><StatusBadge tone={PURCHASE_TONE[p.status]}>{PURCHASE_LABEL[p.status]}</StatusBadge>{p.error ? <span className="block pt-1 text-text-subtle">{p.error}</span> : null}</td>
                      <td className="text-text-muted">{p.actor === "auto-buy" ? "Auto-buy" : p.actor}</td>
                      <td className="text-right">
                        {(p.status === "unknown" || p.status === "pending") && (
                          <div className="flex flex-col items-end gap-1">
                            <span className="text-[11px] text-text-subtle">Check the Vobiz limits above (or the Vobiz console), then:</span>
                            <div className="flex gap-1">
                              <SkeuoButton size="sm" variant="ghost" disabled={busyId === p.id} onClick={() => void resolve(p, "failed")}>It was not bought</SkeuoButton>
                              <SkeuoButton size="sm" disabled={busyId === p.id} onClick={() => void resolve(p, "succeeded")}>It was bought</SkeuoButton>
                            </div>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className="card-surface p-4" data-testid="capacity-tenants">
            <h2 className="text-sm font-semibold text-text">Workspaces</h2>
            {data.tenants.length === 0 ? (
              <EmptyState title="No workspaces use calls yet" body="Workspaces appear here once they own a number, buy channels or make calls." />
            ) : (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[720px] text-xs">
                  <thead><tr className="text-left text-text-subtle">
                    <th className="py-1">Workspace</th><th>Numbers</th><th>Held (numbers + paid)</th><th>Free extra</th><th>Limit</th><th>Live</th><th>Peak 7d</th><th>Refused / waited 7d</th><th>Incidents 24h</th>
                  </tr></thead>
                  <tbody>
                    {data.tenants.map((t) => (
                      <tr key={t.tenantId} className="border-t border-surface-border-subtle">
                        <td className="py-2 text-text">{t.name}</td>
                        <td className="font-mono">{t.numbers}</td>
                        <td className="font-mono">{t.held} <span className="text-text-subtle">({t.numberChannels} + {t.paidChannels})</span></td>
                        <td className="font-mono">{t.included}</td>
                        <td className="font-mono">{t.cap}</td>
                        <td className="font-mono">{t.activeNow}</td>
                        <td className="font-mono">{t.peak7d}</td>
                        <td className="font-mono">{t.rejected7d} / {t.queued7d}</td>
                        <td>{t.incidents24h ? <StatusBadge tone="warning">{t.incidents24h}</StatusBadge> : <span className="text-text-subtle">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="card-surface p-4" data-testid="capacity-incidents">
            <h2 className="text-sm font-semibold text-text">Capacity problems (last 3 days)</h2>
            <p className="mt-0.5 text-xs text-text-muted">Every call or purchase refused or delayed for capacity. Platform rows mean you need more Vobiz capacity; workspace rows mean that workspace used all its own channels.</p>
            {incidents.length === 0 ? (
              <p className="mt-3 text-xs text-text-subtle">No capacity problems.</p>
            ) : (
              <table className="mt-3 w-full text-xs">
                <thead><tr className="text-left text-text-subtle"><th className="py-1">Last seen</th><th>What happened</th><th>Workspace</th><th>Times</th></tr></thead>
                <tbody>
                  {incidents.map((i) => (
                    <tr key={`${i.kind}-${i.tenantId}-${i.lastAt}`} className="border-t border-surface-border-subtle align-top">
                      <td className="py-2 text-text-muted">{relativeTime(i.lastAt)}</td>
                      <td className="text-text">
                        <StatusBadge tone={i.scope === "platform" ? "error" : "warning"}>{i.scope === "platform" ? "Platform" : "Workspace"}</StatusBadge>{" "}
                        {i.label}{i.detail ? <span className="block text-text-subtle">{i.detail}</span> : null}
                      </td>
                      <td>{i.tenantName || "—"}</td>
                      <td className="font-mono">{i.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <ChannelPricingPanel onSaved={() => void reload()} />
        </div>
      )}

      {buying && data && (
        <BuyDialog
          resource={buying}
          suggested={buying === "concurrent_calls" ? (data.estimate.buy || data.estimate.blockSize) : 1}
          blockSize={data.estimate.blockSize}
          owned={buying === "concurrent_calls" ? data.concurrency.owned : data.cps.owned}
          onClose={() => setBuying(null)}
          onDone={done}
        />
      )}
      <AdminConfirmDialog
        open={Boolean(rejecting)}
        title={rejecting ? `Reject ${rejecting.e164}?` : "Reject"}
        description={rejecting ? `${rejecting.tenantName} gets a full refund to their wallet and the number is released.` : undefined}
        confirmLabel="Reject and refund"
        tone="danger"
        statementLabel="Reason (shown in the audit log)"
        busy={Boolean(rejecting && busyId === rejecting.purchaseId)}
        onCancel={() => setRejecting(null)}
        onConfirm={reject}
      />
    </div>
  );
}

