"use client";

import { useCallback, useEffect, useState } from "react";
import { DevCard } from "@/components/dev/DevCard";
import { devFetch } from "@/lib/useAdminResource";
import { Button } from "@/components/ui/Button";

interface CallRow {
  callId: string;
  shortId: string;
  sessionId: string;
  tenantId: string | null;
  tenantName: string;
  agentId: string | null;
  agentName: string;
  channel: string;
  tier: string;
  direction: string;
  status: string;
  durationSec: number;
  durationFormatted: string;
  createdAt: string | null;
  endedAt: string | null;
  retailInr: number | null;
  retailUsd: number | null;
  supplierCostInr: number | null;
  supplierCostUsd: number | null;
  marginInr: number | null;
  marginUsd: number | null;
  marginPercent: number | null;
  costStatus: "ready" | "incomplete";
  missingCost: string[];
  retailRateSource: string;
  carrierCostStatus: string;
  fxRateInr: number | null;
  breakdown: {
    carrierInr: number | null;
    sttInr: number | null;
    llmInr: number | null;
    ttsInr: number | null;
    otherInr: number | null;
  };
}

interface StageComponent {
  rateId?: string;
  unit?: string;
  quantity?: string;
  nativeCost?: string;
  costInr?: string;
}

interface CallDetail {
  ok: boolean;
  callId: string;
  shortId: string;
  sessionId: string;
  tenant: { id: string | null; name: string };
  agent: { id: string | null; name: string };
  tier: string;
  channel: string;
  direction: string;
  status: string;
  endReason: string | null;
  durationSec: number;
  durationFormatted: string;
  createdAt: string | null;
  endedAt: string | null;
  costStatus: "ready" | "incomplete";
  missingCost: string[];
  fxRateInr: number | null;
  retail: {
    source: string;
    rateInrPerMin: number | null;
    rateUsdPerMin: number | null;
    totalBilledInr: number | null;
    totalBilledUsd: number | null;
  };
  supplier: {
    status: "ready" | "incomplete";
    missing: string[];
    totalInr: number | null;
    totalUsd: number | null;
    marginInr: number | null;
    marginPercent: number | null;
    carrier: {
      status: string;
      source: string;
      billableSeconds: number;
      amountInr: number | null;
      amountUsd: number | null;
      currency: string | null;
      raw: Record<string, unknown>;
    };
    stt: {
      model: string | null;
      status: string | null;
      audioSeconds: number;
      costInr: number | null;
      costUsd: number | null;
      components: StageComponent[];
    };
    llm: {
      model: string | null;
      status: string | null;
      inputTokens: number;
      outputTokens: number;
      costInr: number | null;
      costUsd: number | null;
      components: StageComponent[];
    };
    tts: {
      model: string | null;
      status: string | null;
      characters: number;
      outputAudioSeconds: number;
      costInr: number | null;
      costUsd: number | null;
      components: StageComponent[];
    };
    other: { costInr: number | null; costUsd: number | null };
  };
  margin: { inr: number | null; usd: number | null; percent: number | null };
  transcriptSummary?: string | null;
}

interface CallsResponse {
  ok: boolean;
  total: number;
  limit: number;
  offset: number;
  fxRateInr: number;
  calls: CallRow[];
}

export function GlobalCallsWorkbench() {
  const [calls, setCalls] = useState<CallRow[]>([]);
  const [total, setTotal] = useState(0);
  const [limit] = useState(25);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [tier, setTier] = useState<string>("all");
  const [channel, setChannel] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Detail Modal State
  const [selectedCallId, setSelectedCallId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CallDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Debounce search
  useEffect(() => {
    const handle = setTimeout(() => {
      setDebouncedSearch(search);
      setOffset(0);
    }, 350);
    return () => clearTimeout(handle);
  }, [search]);

  const loadCalls = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set("limit", String(limit));
      params.set("offset", String(offset));
      if (debouncedSearch.trim()) params.set("q", debouncedSearch.trim());
      if (tier !== "all") params.set("tier", tier);
      if (channel !== "all") params.set("channel", channel);

      const data = (await devFetch(`/api/dev/admin/calls?${params.toString()}`)) as CallsResponse;
      if (data && data.ok) {
        setCalls(data.calls || []);
        setTotal(data.total || 0);
      } else {
        throw new Error("Invalid response from server");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load calls");
    } finally {
      setLoading(false);
    }
  }, [limit, offset, debouncedSearch, tier, channel]);

  useEffect(() => {
    void loadCalls();
  }, [loadCalls]);

  const openCallDetail = async (callId: string) => {
    setSelectedCallId(callId);
    setDetail(null);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const data = (await devFetch(`/api/dev/admin/calls/${callId}/detail`)) as CallDetail;
      if (data && data.ok) {
        setDetail(data);
      } else {
        throw new Error("Failed to load call audit breakdown");
      }
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : "Failed to load audit detail");
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => {
    setSelectedCallId(null);
    setDetail(null);
  };

  // Close modal on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && selectedCallId) {
        closeDetail();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedCallId]);

  // Aggregate metrics for visible page
  const pricedCalls = calls.filter((call) => call.marginInr != null);
  const retailKnown = calls.filter((call) => call.retailInr != null);
  const supplierKnown = calls.filter((call) => call.supplierCostInr != null);
  const pageRetailInr = retailKnown.reduce((acc, call) => acc + (call.retailInr ?? 0), 0);
  const pageSupplierInr = supplierKnown.reduce((acc, call) => acc + (call.supplierCostInr ?? 0), 0);
  const pageMarginInr = pricedCalls.reduce((acc, call) => acc + (call.marginInr ?? 0), 0);
  const pageMarginRetail = pricedCalls.reduce((acc, call) => acc + (call.retailInr ?? 0), 0);
  const pageMarginPct = pageMarginRetail > 0 ? (pageMarginInr / pageMarginRetail) * 100 : null;
  const incompleteCalls = calls.filter((call) => call.costStatus === "incomplete");

  const money = (value: number | null, digits = 2) => (value == null ? "—" : `₹${value.toFixed(digits)}`);
  const usd = (value: number | null, digits = 4) => (value == null ? "—" : `$${value.toFixed(digits)}`);
  const componentLabel = (components: StageComponent[]) =>
    components.length === 0
      ? "—"
      : components
          .map((row) =>
            [
              row.rateId,
              row.quantity != null && row.unit ? `${row.quantity} ${row.unit}` : row.unit,
              row.costInr != null ? `₹${row.costInr}` : null,
            ]
              .filter(Boolean)
              .join(" · "),
          )
          .join("; ");

  return (
    <div className="space-y-6">
      {/* Overview Stats Bar */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-surface-border-subtle bg-surface-card p-4 shadow-sm">
          <p className="text-xs font-medium text-text-muted">Total Recorded Calls</p>
          <p className="mt-1.5 text-2xl font-bold tracking-tight text-text">{total}</p>
          <p className="mt-1 text-xs text-text-subtle">Across all tenants & channels</p>
        </div>

        <div className="rounded-xl border border-surface-border-subtle bg-surface-card p-4 shadow-sm">
          <p className="text-xs font-medium text-text-muted">Page Retail Billed</p>
          <p className="mt-1.5 text-2xl font-bold tracking-tight text-text">{money(pageRetailInr)}</p>
          <p className="mt-1 text-xs text-text-subtle">
            {retailKnown.length} of {calls.length} calls with a pinned retail rate
          </p>
        </div>

        <div className="rounded-xl border border-surface-border-subtle bg-surface-card p-4 shadow-sm">
          <p className="text-xs font-medium text-text-muted">Page Supplier Cost</p>
          <p className="mt-1.5 text-2xl font-bold tracking-tight text-amber-300">{money(pageSupplierInr, 4)}</p>
          <p className="mt-1 text-xs text-text-subtle">
            {supplierKnown.length} of {calls.length} calls fully measured
          </p>
        </div>

        <div className="rounded-xl border border-surface-border-subtle bg-surface-card p-4 shadow-sm">
          <p className="text-xs font-medium text-text-muted">Net Platform Profit</p>
          <div className="mt-1.5 flex items-baseline gap-2">
            <span
              className={`text-2xl font-bold tracking-tight ${
                pageMarginInr >= 0 ? "text-emerald-400" : "text-rose-300"
              }`}
            >
              {money(pageMarginInr)}
            </span>
            {pageMarginPct != null && (
              <span
                className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${
                  pageMarginInr >= 0
                    ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-400"
                    : "border-rose-500/25 bg-rose-500/10 text-rose-300"
                }`}
              >
                {pageMarginPct >= 0 ? `+${pageMarginPct.toFixed(1)}%` : `${pageMarginPct.toFixed(1)}%`}
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-text-subtle">
            {pricedCalls.length} priced calls
            {incompleteCalls.length > 0 ? ` · ${incompleteCalls.length} incomplete` : ""}
          </p>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <DevCard title="Global Calls & Cost Ledger" description="Real-time multi-tenant session ledger with complete wholesale supplier cost attribution.">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-1 flex-wrap items-center gap-2">
            <div className="relative min-w-[240px] flex-1 max-w-md">
              <input
                type="text"
                placeholder="Search short ID (e.g. 4820E4), full UUID, agent, or tenant..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full rounded-xl border border-surface-border bg-surface-raised px-3.5 py-2 text-sm text-text placeholder:text-text-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch("")}
                  className="absolute right-3 top-2.5 text-xs text-text-muted hover:text-text"
                >
                  ✕
                </button>
              )}
            </div>

            <select
              value={tier}
              onChange={(e) => {
                setTier(e.target.value);
                setOffset(0);
              }}
              className="rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
            >
              <option value="all">All Tiers</option>
              <option value="medium">Standard Regional (pstn_medium)</option>
              <option value="low">Economical (pstn_low)</option>
              <option value="premium">Flagship Live (pstn_premium)</option>
            </select>

            <select
              value={channel}
              onChange={(e) => {
                setChannel(e.target.value);
                setOffset(0);
              }}
              className="rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
            >
              <option value="all">All Channels</option>
              <option value="pstn">PSTN Phone</option>
              <option value="browser">Browser Web Agent</option>
            </select>
          </div>

          <Button type="button" variant="secondary" onClick={() => void loadCalls()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </Button>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
            {error}
          </div>
        )}

        {/* Calls Table */}
        <div className="mt-4 overflow-x-auto rounded-xl border border-surface-border-subtle bg-surface-raised/20">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-surface-border-subtle bg-surface-raised/60 text-xs font-semibold text-text-muted">
              <tr>
                <th className="px-4 py-3">Call Ref</th>
                <th className="px-4 py-3">Tenant & Agent</th>
                <th className="px-4 py-3">Tier & Channel</th>
                <th className="px-4 py-3">Duration</th>
                <th className="px-4 py-3">Retail Billed</th>
                <th className="px-4 py-3">Supplier Cost</th>
                <th className="px-4 py-3">Net Profit</th>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border-subtle">
              {loading && calls.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-text-muted">
                    Loading global calls and supplier cost ledger…
                  </td>
                </tr>
              ) : calls.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-text-muted">
                    No calls found matching the active filter.
                  </td>
                </tr>
              ) : (
                calls.map((call) => {
                  const isMedium = call.tier.startsWith("medium") || call.tier === "standard";
                  const isLow = call.tier.startsWith("low") || call.tier.includes("economical");
                  const tierLabel = isMedium
                    ? call.tier === "medium" ? "Standard" : `Standard (${call.tier.replace("medium_", "")})`
                    : isLow
                    ? call.tier === "low" ? "Economical" : `Economical (${call.tier.replace("low_", "")})`
                    : call.tier === "premium" ? "Flagship" : call.tier;
                  const aiCosts = [call.breakdown.sttInr, call.breakdown.llmInr, call.breakdown.ttsInr];
                  const aiCost = aiCosts.every((value) => value != null)
                    ? aiCosts.reduce<number>((sum, value) => sum + (value ?? 0), 0)
                    : null;

                  return (
                    <tr
                      key={call.callId}
                      className="transition-colors hover:bg-surface-raised/40 cursor-pointer"
                      onClick={() => void openCallDetail(call.callId)}
                    >
                      <td className="px-4 py-3 font-mono font-semibold text-accent-primary">
                        <span className="rounded bg-accent-primary/10 px-2 py-0.5">
                          #{call.shortId}
                        </span>
                      </td>

                      <td className="px-4 py-3">
                        <p className="font-medium text-text">{call.agentName}</p>
                        <p className="text-xs text-text-subtle truncate max-w-[140px]" title={call.tenantName}>
                          {call.tenantName}
                        </p>
                      </td>

                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-1 items-start">
                          <span
                            className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                              isMedium
                                ? "border-sky-500/30 bg-sky-500/10 text-sky-300"
                                : isLow
                                ? "border-amber-500/30 bg-amber-500/10 text-amber-300"
                                : "border-purple-500/30 bg-purple-500/10 text-purple-300"
                            }`}
                          >
                            {tierLabel}
                          </span>
                          <span className="text-[11px] text-text-muted uppercase tracking-wider font-mono">
                            {call.channel}
                          </span>
                        </div>
                      </td>

                      <td className="px-4 py-3 font-mono text-text">
                        {call.durationFormatted}
                      </td>

                      <td className="px-4 py-3 font-mono font-medium text-text">
                        {money(call.retailInr)}
                      </td>

                      <td className="px-4 py-3">
                        <p className="font-mono font-semibold text-amber-300">{money(call.supplierCostInr, 4)}</p>
                        {call.supplierCostInr == null ? (
                          <p className="text-[10px] text-amber-400/80" title={call.missingCost.join(", ")}>
                            Incomplete: {call.missingCost.join(", ") || "cost snapshot missing"}
                          </p>
                        ) : (
                          <p className="text-[10px] text-text-subtle">
                            PSTN: {money(call.breakdown.carrierInr)} · AI: {money(aiCost)}
                          </p>
                        )}
                      </td>

                      <td className="px-4 py-3">
                        {call.marginInr == null ? (
                          <span className="text-xs text-text-subtle" title={call.missingCost.join(", ")}>
                            Not calculable
                          </span>
                        ) : (
                          <span
                            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                              call.marginInr >= 0
                                ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-400"
                                : "border-rose-500/25 bg-rose-500/10 text-rose-300"
                            }`}
                          >
                            {money(call.marginInr)}
                            {call.marginPercent != null && (
                              <span className="text-[10px] opacity-80">({call.marginPercent}%)</span>
                            )}
                          </span>
                        )}
                      </td>

                      <td className="px-4 py-3 text-xs text-text-muted whitespace-nowrap">
                        {call.createdAt ? new Date(call.createdAt).toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}
                      </td>

                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            void openCallDetail(call.callId);
                          }}
                          className="rounded-lg border border-surface-border bg-surface-card px-2.5 py-1 text-xs font-medium text-text hover:border-accent-primary/40 hover:text-accent-primary transition-colors"
                        >
                          Audit Cost
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="mt-4 flex items-center justify-between text-xs text-text-muted">
          <span>
            Showing {calls.length > 0 ? offset + 1 : 0}–{Math.min(offset + calls.length, total)} of {total} calls
          </span>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="secondary"
              disabled={offset === 0 || loading}
              onClick={() => setOffset((prev) => Math.max(0, prev - limit))}
            >
              Previous
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={offset + limit >= total || loading}
              onClick={() => setOffset((prev) => prev + limit)}
            >
              Next
            </Button>
          </div>
        </div>
      </DevCard>

      {/* Modal: Call Cost Audit Drawer */}
      {selectedCallId && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm animate-in fade-in duration-200"
          onClick={closeDetail}
        >
          <div
            className="relative w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-2xl border border-surface-border-subtle bg-surface-card p-6 shadow-2xl space-y-6"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-surface-border-subtle pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xl font-bold text-accent-primary">
                    CALL #{detail?.shortId || selectedCallId.slice(0, 8).toUpperCase()}
                  </span>
                  <span className="rounded-full border border-surface-border bg-surface-raised px-2.5 py-0.5 text-xs text-text-muted">
                    {detail?.tier.toUpperCase()} · {detail?.channel.toUpperCase()}
                  </span>
                  <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-300">
                    {detail?.status || "completed"}
                  </span>
                </div>
                <p className="mt-1 text-sm text-text-muted">
                  Agent: <span className="font-medium text-text">{detail?.agent.name || "—"}</span> · Tenant:{" "}
                  <span className="font-medium text-text">{detail?.tenant.name || "—"}</span>
                </p>
              </div>

              <button
                type="button"
                onClick={closeDetail}
                className="rounded-xl border border-surface-border bg-surface-raised p-2 text-text-muted hover:text-text hover:bg-surface-panel transition-colors"
              >
                ✕
              </button>
            </div>

            {detailLoading ? (
              <div className="py-12 text-center text-sm text-text-muted">
                Loading session ledger and stage usage cost breakdown…
              </div>
            ) : detailError ? (
              <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
                {detailError}
              </div>
            ) : detail ? (
              <>
                {/* Cost Status */}
                {detail.costStatus === "incomplete" && (
                  <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
                    <p className="font-semibold">Supplier or retail cost is incomplete for this call.</p>
                    <p className="mt-1 text-amber-200/80">
                      Missing: {detail.missingCost.join(", ") || "pinned cost data"}
                      {detail.supplier.missing.length > 0 ? ` · Supplier: ${detail.supplier.missing.join(", ")}` : ""}
                    </p>
                    <p className="mt-1 text-amber-200/60">
                      Unknown values are shown as “—” and are excluded from margin totals.
                    </p>
                  </div>
                )}

                {/* KPI Top Cards */}
                <div className="grid gap-3 sm:grid-cols-4">
                  <div className="rounded-xl border border-surface-border bg-surface-raised/40 p-3">
                    <p className="text-xs text-text-subtle">Call Duration</p>
                    <p className="mt-1 font-mono text-lg font-bold text-text">{detail.durationFormatted}</p>
                    <p className="text-[11px] text-text-muted">{detail.durationSec} billable seconds</p>
                  </div>

                  <div className="rounded-xl border border-surface-border bg-surface-raised/40 p-3">
                    <p className="text-xs text-text-subtle">Retail Billed</p>
                    <p className="mt-1 font-mono text-lg font-bold text-text">{money(detail.retail.totalBilledInr)}</p>
                    <p className="text-[11px] text-text-muted">
                      {detail.retail.rateInrPerMin != null
                        ? `${money(detail.retail.rateInrPerMin)}/min · ${detail.retail.source}`
                        : `No ${detail.retail.source === "unavailable" ? "pinned" : detail.retail.source} retail rate`}
                    </p>
                  </div>

                  <div className="rounded-xl border border-surface-border bg-surface-raised/40 p-3">
                    <p className="text-xs text-text-subtle">Supplier Cost</p>
                    <p className="mt-1 font-mono text-lg font-bold text-amber-300">{money(detail.supplier.totalInr, 4)}</p>
                    <p className="text-[11px] text-text-muted">
                      {detail.supplier.totalUsd != null ? `${usd(detail.supplier.totalUsd, 4)} USD` : detail.supplier.status}
                    </p>
                  </div>

                  <div
                    className={`rounded-xl border p-3 ${
                      detail.margin.inr != null && detail.margin.inr < 0
                        ? "border-rose-500/30 bg-rose-500/10"
                        : "border-emerald-500/30 bg-emerald-500/10"
                    }`}
                  >
                    <p
                      className={`text-xs ${
                        detail.margin.inr != null && detail.margin.inr < 0 ? "text-rose-300" : "text-emerald-300"
                      }`}
                    >
                      Net Platform Profit
                    </p>
                    <p
                      className={`mt-1 font-mono text-lg font-bold ${
                        detail.margin.inr != null && detail.margin.inr < 0 ? "text-rose-300" : "text-emerald-400"
                      }`}
                    >
                      {money(detail.margin.inr)}
                    </p>
                    <p
                      className={`text-[11px] font-semibold ${
                        detail.margin.inr != null && detail.margin.inr < 0 ? "text-rose-300" : "text-emerald-300"
                      }`}
                    >
                      {detail.margin.percent != null ? `${detail.margin.percent}% gross margin` : "Not calculable"}
                    </p>
                  </div>
                </div>

                {/* 4-Box Supplier Cost Breakdown */}
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
                      Wholesale Supplier Cost Breakdown (By Stage)
                    </h4>
                    <span className="text-[11px] text-text-muted">
                      Other measured: {money(detail.supplier.other.costInr, 4)} · FX {detail.fxRateInr ?? "—"}
                    </span>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    {/* Telephony Box */}
                    <div className="rounded-xl border border-surface-border-subtle bg-surface-raised/30 p-4 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-text text-sm">1. PSTN Telephony Trunk</span>
                        <span className="font-mono text-xs font-bold text-amber-300">
                          {money(detail.supplier.carrier.amountInr, 4)}
                        </span>
                      </div>
                      <div className="text-xs text-text-muted space-y-1">
                        <p>Cost basis: <span className="text-text font-medium">{detail.supplier.carrier.status}</span></p>
                        <p>Billable Talk Time: <span className="font-mono text-text">{detail.supplier.carrier.billableSeconds}s</span></p>
                        <p>Source: <span className="font-mono text-[11px] text-text-subtle">{detail.supplier.carrier.source}</span></p>
                        {detail.supplier.carrier.currency && (
                          <p>Currency: <span className="font-mono text-text">{detail.supplier.carrier.currency}</span></p>
                        )}
                      </div>
                    </div>

                    {/* STT Box */}
                    <div className="rounded-xl border border-surface-border-subtle bg-surface-raised/30 p-4 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-text text-sm">2. Speech Recognition (STT)</span>
                        <span className="font-mono text-xs font-bold text-amber-300">
                          {money(detail.supplier.stt.costInr, 4)}
                        </span>
                      </div>
                      <div className="text-xs text-text-muted space-y-1">
                        <p>Model: <span className="text-text font-medium">{detail.supplier.stt.model || "—"}</span></p>
                        <p>Audio Processed: <span className="font-mono text-text">{detail.supplier.stt.audioSeconds.toFixed(1)}s</span> ({(detail.supplier.stt.audioSeconds / 60).toFixed(2)} min)</p>
                        <p>Pinned rate: <span className="font-mono text-[11px] text-text-subtle">{componentLabel(detail.supplier.stt.components)}</span></p>
                      </div>
                    </div>

                    {/* LLM Box */}
                    <div className="rounded-xl border border-surface-border-subtle bg-surface-raised/30 p-4 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-text text-sm">3. Reasoning & LLM</span>
                        <span className="font-mono text-xs font-bold text-amber-300">
                          {money(detail.supplier.llm.costInr, 4)}
                        </span>
                      </div>
                      <div className="text-xs text-text-muted space-y-1">
                        <p>Model: <span className="text-text font-medium">{detail.supplier.llm.model || "—"}</span></p>
                        <p>Input Tokens: <span className="font-mono text-text">{detail.supplier.llm.inputTokens.toLocaleString()}</span></p>
                        <p>Output Tokens: <span className="font-mono text-text">{detail.supplier.llm.outputTokens.toLocaleString()}</span></p>
                        <p>Pinned rate: <span className="font-mono text-[11px] text-text-subtle">{componentLabel(detail.supplier.llm.components)}</span></p>
                      </div>
                    </div>

                    {/* TTS Box */}
                    <div className="rounded-xl border border-surface-border-subtle bg-surface-raised/30 p-4 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-text text-sm">4. Speech Synthesis (TTS)</span>
                        <span className="font-mono text-xs font-bold text-amber-300">
                          {money(detail.supplier.tts.costInr, 4)}
                        </span>
                      </div>
                      <div className="text-xs text-text-muted space-y-1">
                        <p>Model: <span className="text-text font-medium">{detail.supplier.tts.model || "—"}</span></p>
                        <p>Characters Synthesized: <span className="font-mono text-text">{detail.supplier.tts.characters.toLocaleString()} chars</span></p>
                        <p>Output Audio: <span className="font-mono text-text">{detail.supplier.tts.outputAudioSeconds.toFixed(1)}s</span></p>
                        <p>Pinned rate: <span className="font-mono text-[11px] text-text-subtle">{componentLabel(detail.supplier.tts.components)}</span></p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Session Metadata Drawer */}
                <div className="rounded-xl border border-surface-border-subtle bg-surface-raised/20 p-4 space-y-2">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
                    Session & Carrier Metadata
                  </h4>
                  <div className="grid gap-2 sm:grid-cols-2 text-xs">
                    <div>
                      <span className="text-text-subtle">Full Call UUID:</span>
                      <p className="font-mono text-text select-all">{detail.callId}</p>
                    </div>
                    <div>
                      <span className="text-text-subtle">Carrier Session ID:</span>
                      <p className="font-mono text-text select-all">{detail.sessionId || "—"}</p>
                    </div>
                    <div>
                      <span className="text-text-subtle">Disconnect Reason:</span>
                      <p className="font-mono text-text">{detail.endReason || "normal_clearing"}</p>
                    </div>
                    <div>
                      <span className="text-text-subtle">Call Started:</span>
                      <p className="font-mono text-text">
                        {detail.createdAt ? new Date(detail.createdAt).toLocaleString() : "—"}
                      </p>
                    </div>
                  </div>
                </div>
              </>
            ) : null}

            <div className="flex justify-end pt-2 border-t border-surface-border-subtle">
              <Button type="button" variant="secondary" onClick={closeDetail}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
