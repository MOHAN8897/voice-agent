"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { portalFetch } from "@/lib/auth-client";
import {
  DEFAULT_TIER_LABELS,
  PRICE_SOURCE_LABEL,
  formatInr,
  responseError,
  type TierProfileRow,
} from "@/components/dev/voice-stack/profileModel";

/** Platform-wide channel prices; tier prices are shown read-only here. */
export function PlatformPricesPanel({ rows, onSaved }: { rows: TierProfileRow[]; onSaved: () => Promise<void> | void }) {
  const [pricesSaving, setPricesSaving] = useState(false);
  const [pricesStatus, setPricesStatus] = useState("");
  const [pricesError, setPricesError] = useState("");
  const [webInr, setWebInr] = useState("0");
  const [numberInr, setNumberInr] = useState("0");
  const [fxRate, setFxRate] = useState("95.64");
  const [liveFx, setLiveFx] = useState<number | null>(null);

  const loadPrices = useCallback(async () => {
    try {
      const res = await portalFetch("dev", "/api/dev/admin/billing-rates");
      if (!res.ok) return;
      const data = await res.json();
      const r = data.rates;
      if (r) {
        setWebInr(String(r.webInrPerMin ?? (r.webUsdPerMin ? (r.webUsdPerMin * (r.fxRateInr || 95.64)).toFixed(2) : "0")));
        setNumberInr(String(r.numberMonthlyInr ?? (r.numberMonthlyUsd ? (r.numberMonthlyUsd * (r.fxRateInr || 95.64)).toFixed(2) : "0")));
        setFxRate(String(r.fxRateInr ?? "95.64"));
      }
      if (data.fx?.liveRateInr) {
        setLiveFx(data.fx.liveRateInr);
      }
    } catch {
      // Non-blocking prices fetch
    }
  }, []);

  useEffect(() => {
    void loadPrices();
  }, [loadPrices]);

  async function handleSavePrices() {
    if (pricesSaving) return;
    const web = Number(webInr);
    const fx = Number(fxRate);
    const did = Number(numberInr);
    if (!Number.isFinite(web) || web <= 0) {
      setPricesError("Default web calling rate must be greater than zero.");
      return;
    }
    if (!Number.isFinite(did) || did < 0) {
      setPricesError("Number rental must be zero or more.");
      return;
    }
    if (!Number.isFinite(fx) || fx <= 0) {
      setPricesError("FX rate must be greater than zero.");
      return;
    }
    setPricesSaving(true);
    setPricesError("");
    setPricesStatus("");
    try {
      const payload = {
        rateCurrency: "INR",
        webInrPerMin: web,
        didMonthlyInr: did,
        fxRateInr: fx,
        reason: "Updated Platform & Channel Prices (INR) from Stacks & Tiers workbench",
      };
      const res = await portalFetch("dev", "/api/dev/admin/billing-rates", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await responseError(res));
      setPricesStatus("Platform prices saved as a new rate version. New calls use it; calls in progress keep their starting price.");
      await loadPrices();
      await onSaved();
    } catch (err) {
      setPricesError(err instanceof Error ? err.message : "Failed to save prices.");
    } finally {
      setPricesSaving(false);
    }
  }

  return (
    <DevCard
      title="Platform & Channel Prices (INR)"
      description="Web calling default, number rental and exchange-rate settings. Phone-call prices are managed once, on each tier card."
    >
      {pricesError && (
        <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">
          {pricesError}
        </div>
      )}
      {pricesStatus && (
        <div className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
          {pricesStatus}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {/* Web Calling Rate */}
        <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-1.5">
          <label className="block text-xs font-semibold text-text">
            Default Web Calling Rate
          </label>
          <p className="text-[11px] text-text-muted">Used only when the selected stack has no separate web price. Configure overrides in each stack’s pricing section.</p>
          <div className="relative mt-1">
            <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-xs text-text-muted">₹</span>
            <input
              type="number"
              step="0.01"
              min="0"
              value={webInr}
              onChange={(e) => setWebInr(e.target.value)}
              className="w-full rounded-lg border border-surface-border bg-surface-raised pl-8 pr-3 py-2 text-sm text-text font-mono focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
            />
          </div>
        </div>

        {/* Phone DID Rental Rate */}
        <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-1.5">
          <label className="block text-xs font-semibold text-text">
            DID Phone Number Rental
          </label>
          <p className="text-[11px] text-text-muted">Monthly leased virtual carrier phone number in ₹</p>
          <div className="relative mt-1">
            <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-xs text-text-muted">₹</span>
            <input
              type="number"
              step="1"
              min="0"
              value={numberInr}
              onChange={(e) => setNumberInr(e.target.value)}
              className="w-full rounded-lg border border-surface-border bg-surface-raised pl-8 pr-3 py-2 text-sm text-text font-mono focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
            />
          </div>
        </div>

        {/* FX Exchange Rate */}
        <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-1.5">
          <div className="flex items-center justify-between">
            <label className="block text-xs font-semibold text-text">USD → INR FX Rate</label>
            {liveFx ? (
              <span className="text-[10px] font-mono text-emerald-400">
                Live: ₹{liveFx.toFixed(2)}
              </span>
            ) : null}
          </div>
          <p className="text-[11px] text-text-muted">Platform charge FX rate (rupees per USD)</p>
          <div className="relative mt-1">
            <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-xs text-text-muted">₹</span>
            <input
              type="number"
              step="0.01"
              min="50"
              value={fxRate}
              onChange={(e) => setFxRate(e.target.value)}
              className="w-full rounded-lg border border-surface-border bg-surface-raised pl-8 pr-3 py-2 text-sm text-text font-mono focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
            />
          </div>
        </div>
      </div>

      <div className="mt-6 rounded-xl border border-surface-border-subtle bg-surface-raised/40 p-4" data-testid="tier-prices-readonly">
        <h4 className="text-xs font-semibold text-text">Phone call prices by tier (read-only)</h4>
        <p className="mt-0.5 text-[11px] text-text-muted">
          Each tier price is edited only on its tier card in Voice Stack. Saving a core tier price publishes a new billing rate version.
        </p>
        <ul className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map((row) => (
            <li key={row.tier} className="rounded-lg border border-surface-border bg-surface-panel px-3 py-2 text-xs">
              <span className="font-semibold text-text">{row.label || DEFAULT_TIER_LABELS[row.tier] || row.tier}</span>
              <span className="block font-mono text-text">{formatInr(row.retailRate?.inrPaisePerMin)}</span>
              <span className="block text-[11px] text-text-subtle">{PRICE_SOURCE_LABEL[row.priceSource || "missing"] || row.priceSource}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-6 pt-4 border-t border-border flex items-center justify-between">
        <p className="text-xs text-text-subtle">
          Saving publishes a new rate version that applies to new calls only. Calls already in progress finish at the price they started with, and each charge records the rate version it used.
        </p>
        <Button
          type="button"
          disabled={pricesSaving}
          onClick={() => void handleSavePrices()}
          className="px-5 py-2.5"
        >
          {pricesSaving ? "Saving Prices…" : "Save Platform Prices"}
        </Button>
      </div>
    </DevCard>
  );
}
