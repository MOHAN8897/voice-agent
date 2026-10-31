"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { portalFetch } from "@/lib/auth-client";
import { responseError } from "@/components/dev/voice-stack/profileModel";

type ChannelOverview = {
  pricing: {
    configured: boolean;
    version?: number;
    priceInrPerChannel: number;
    free?: boolean;
    platformCapacity?: number;
    includedChannels?: number;
    graceDays?: number;
    maxChannelsPerTenant?: number;
    periodDays: number;
    updatedAt?: string | null;
  };
  soldPaidChannels: number;
  tenantsWithPaidChannels: number;
  liveCalls: number;
  vobiz: { available: boolean; maxConcurrent?: number; concurrentCalls?: number; utilizationPct?: number; reason?: string };
};

const inputClass =
  "w-full rounded-lg border border-surface-border bg-surface-raised px-3 py-2 text-sm text-text font-mono focus:outline-none focus:ring-2 focus:ring-accent-primary/40";

/** Price per concurrent call channel and the platform's Vobiz capacity. */
export function ChannelPricingPanel() {
  const [overview, setOverview] = useState<ChannelOverview | null>(null);
  const [price, setPrice] = useState("0");
  const [capacity, setCapacity] = useState("20");
  const [included, setIncluded] = useState("1");
  const [graceDays, setGraceDays] = useState("3");
  const [maxPerTenant, setMaxPerTenant] = useState("0");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await portalFetch("dev", "/api/dev/admin/billing/channels");
      if (!res.ok) return;
      const data = (await res.json()) as ChannelOverview;
      setOverview(data);
      const p = data.pricing;
      if (p.configured) {
        setPrice(String(p.priceInrPerChannel ?? 0));
        setCapacity(String(p.platformCapacity ?? 20));
        setIncluded(String(p.includedChannels ?? 1));
        setGraceDays(String(p.graceDays ?? 3));
        setMaxPerTenant(String(p.maxChannelsPerTenant ?? 0));
      } else if (data.vobiz?.available && data.vobiz.maxConcurrent) {
        setCapacity(String(data.vobiz.maxConcurrent));
      }
    } catch {
      // Non-blocking: the form still saves.
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function save() {
    if (saving) return;
    const body = {
      priceInrPerChannel: Number(price),
      platformCapacity: Number(capacity),
      includedChannels: Number(included),
      graceDays: Number(graceDays),
      maxChannelsPerTenant: Number(maxPerTenant),
      reason: reason.trim(),
    };
    if (!Number.isFinite(body.priceInrPerChannel) || body.priceInrPerChannel < 0) {
      setError("Price per channel must be zero or more.");
      return;
    }
    if (!Number.isInteger(body.platformCapacity) || body.platformCapacity < 1) {
      setError("Platform capacity must be a whole number of at least 1.");
      return;
    }
    if (!Number.isInteger(body.includedChannels) || body.includedChannels < 0 || body.includedChannels > body.platformCapacity) {
      setError("Included channels must be between 0 and the platform capacity.");
      return;
    }
    if (body.reason.length < 8) {
      setError("Give a reason of at least 8 characters; it is kept with this price version.");
      return;
    }
    setSaving(true);
    setError("");
    setStatus("");
    try {
      const res = await portalFetch("dev", "/api/dev/admin/billing/channels", { method: "PUT", body: JSON.stringify(body) });
      if (!res.ok) throw new Error(await responseError(res));
      setStatus(
        body.priceInrPerChannel > 0
          ? "Saved as a new channel price version. It applies to new purchases now and to each workspace at its next 30-day renewal; periods already paid are not re-priced."
          : "Saved. Channels are free: purchases and renewals debit nothing."
      );
      setReason("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save channel pricing.");
    } finally {
      setSaving(false);
    }
  }

  const vobiz = overview?.vobiz;
  const capNum = Number(capacity) || 0;
  const overVobiz = Boolean(vobiz?.available && vobiz.maxConcurrent && capNum > vobiz.maxConcurrent);

  return (
    <DevCard
      title="Concurrent call channels"
      description="Price per simultaneous-call channel (per 30 days, matching Vobiz's 30-day capacity renewal) and the capacity the platform has bought from Vobiz."
    >
      {error && <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">{error}</div>}
      {status && <div className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">{status}</div>}

      <div className="mb-4 grid gap-3 sm:grid-cols-4 text-xs" data-testid="channel-capacity-summary">
        <div className="rounded-lg border border-surface-border bg-surface-panel px-3 py-2">
          <span className="block text-text-muted">Live calls now</span>
          <span className="font-mono text-text">{overview?.liveCalls ?? "—"}</span>
        </div>
        <div className="rounded-lg border border-surface-border bg-surface-panel px-3 py-2">
          <span className="block text-text-muted">Paid channels sold</span>
          <span className="font-mono text-text">
            {overview?.soldPaidChannels ?? "—"} <span className="text-text-subtle">({overview?.tenantsWithPaidChannels ?? 0} workspaces)</span>
          </span>
        </div>
        <div className="rounded-lg border border-surface-border bg-surface-panel px-3 py-2">
          <span className="block text-text-muted">Vobiz account limit</span>
          <span className="font-mono text-text">
            {vobiz?.available ? `${vobiz.concurrentCalls ?? 0} / ${vobiz.maxConcurrent ?? 0}` : "unavailable"}
          </span>
        </div>
        <div className="rounded-lg border border-surface-border bg-surface-panel px-3 py-2">
          <span className="block text-text-muted">Price version</span>
          <span className="font-mono text-text">{overview?.pricing.configured ? `v${overview.pricing.version}` : "not configured"}</span>
        </div>
      </div>

      {!overview?.pricing.configured && (
        <p className="mb-4 text-[11px] text-text-muted">
          Not configured yet: workspaces keep the legacy per-tenant limit. Saving switches every workspace to included + paid channels.
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <label className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-1.5 text-xs">
          <span className="block font-semibold text-text">Price per channel (₹ / 30 days)</span>
          <span className="block text-[11px] text-text-muted">0 means channels are free and nothing is debited. Tenants see price × channels before confirming.</span>
          <input type="number" min="0" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} className={inputClass} />
        </label>
        <label className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-1.5 text-xs">
          <span className="block font-semibold text-text">Platform capacity (channels)</span>
          <span className="block text-[11px] text-text-muted">Simultaneous calls bought from Vobiz. Live calls across all workspaces never exceed it, and paid channels cannot be oversold.</span>
          <input type="number" min="1" step="1" value={capacity} onChange={(e) => setCapacity(e.target.value)} className={inputClass} />
          {overVobiz && <span className="block text-[11px] text-amber-300">Higher than the Vobiz account limit ({vobiz?.maxConcurrent}); calls over it will be refused by Vobiz.</span>}
        </label>
        <label className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-1.5 text-xs">
          <span className="block font-semibold text-text">Included channels per workspace</span>
          <span className="block text-[11px] text-text-muted">Free channels every workspace has; also what a workspace drops back to if a renewal stays unpaid.</span>
          <input type="number" min="0" step="1" value={included} onChange={(e) => setIncluded(e.target.value)} className={inputClass} />
        </label>
        <label className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-1.5 text-xs">
          <span className="block font-semibold text-text">Grace period (days)</span>
          <span className="block text-[11px] text-text-muted">After a failed renewal, paid channels keep working this long while renewal is retried.</span>
          <input type="number" min="0" max="30" step="1" value={graceDays} onChange={(e) => setGraceDays(e.target.value)} className={inputClass} />
        </label>
        <label className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-1.5 text-xs">
          <span className="block font-semibold text-text">Max channels per workspace</span>
          <span className="block text-[11px] text-text-muted">0 = limited only by platform capacity.</span>
          <input type="number" min="0" step="1" value={maxPerTenant} onChange={(e) => setMaxPerTenant(e.target.value)} className={inputClass} />
        </label>
        <label className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-1.5 text-xs">
          <span className="block font-semibold text-text">Reason for this change</span>
          <span className="block text-[11px] text-text-muted">Kept with the price version for audit.</span>
          <input type="text" value={reason} onChange={(e) => setReason(e.target.value)} className={inputClass} placeholder="e.g. Vobiz capacity increased to 40" />
        </label>
      </div>

      <div className="mt-6 pt-4 border-t border-border flex items-center justify-between gap-3">
        <p className="text-xs text-text-subtle">
          Price changes apply to new purchases and to each workspace at its next renewal. Additions mid-period are prorated; reductions take effect at renewal without refund.
        </p>
        <Button type="button" disabled={saving} onClick={() => void save()} className="px-5 py-2.5 shrink-0">
          {saving ? "Saving…" : "Save channel pricing"}
        </Button>
      </div>
    </DevCard>
  );
}
