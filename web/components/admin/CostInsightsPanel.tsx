"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { DevCard } from "@/components/dev/DevCard";
import { AdminError, AdminLoading } from "@/components/admin/AdminNav";
import { SkeuoButton, SkeuoInput, SkeuoTable, SkeuoTableBody, SkeuoTableHead, SkeuoTableRow, SkeuoTd, SkeuoTh } from "@/components/ui/skeuo";
import { devFetch } from "@/lib/useAdminResource";

type Channel = {
  channel: "pstn" | "browser";
  label: string;
  costUsd: number;
  costInr: number;
  connectedMinutes: number;
  calls: number;
  tenants: number;
  missingCostCalls: number;
  coveragePercent: number | null;
  averageUsdPerMin: number | null;
  averageInrPerMin: number | null;
  apiUsd: number;
  apiInr: number;
  carrierUsd: number;
  carrierInr: number;
  transcriptionUsd: number;
  transcriptionInr: number;
  unconnectedPrewarmUsd: number;
  unconnectedPrewarmInr: number;
  unconnectedPrewarmRecords: number;
  carrierCdrCalls: number;
  carrierEstimatedCalls: number;
  reconstructedCalls: number;
  currentPriceUsdPerMin: number;
  currentPriceInrPerMin: number;
  models: string[];
};
type Insights = {
  asOf: string;
  since: string;
  callsReviewed: number;
  windowCapped: boolean;
  channels: Channel[];
  notes: string[];
  samples: { callId: string; tenant: string; channel: string; durationSec: number; costUsd: number; costInr: number; model: string; carrierSource: string }[];
};

function money(value: number | null, currency: "USD" | "INR") {
  if (value === null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency, minimumFractionDigits: currency === "USD" ? 4 : 2, maximumFractionDigits: 6 }).format(value);
}

export function CostInsightsPanel({ display, onUsePrice }: {
  display: "USD" | "INR" | "both";
  onUsePrice: (field: "pstn" | "web", usd: number, inr: number) => void;
}) {
  const [days, setDays] = useState(30);
  const [margin, setMargin] = useState("30");
  const [report, setReport] = useState<{ data: Insights | null; error: string | null; loading: boolean }>({ data: null, error: null, loading: true });
  const request = useRef(0);
  const reload = useCallback(async () => {
    const id = ++request.current;
    setReport((previous) => ({ ...previous, error: null, loading: true }));
    try {
      const data = await devFetch(`/api/dev/admin/billing/cost-insights?days=${days}`) as Insights;
      if (id === request.current) setReport({ data, error: null, loading: false });
    } catch (error) {
      if (id === request.current) setReport({ data: null, error: error instanceof Error ? error.message : "Could not load supplier costs", loading: false });
    }
  }, [days]);
  useEffect(() => {
    void reload();
    const interval = window.setInterval(() => { void reload(); }, 60_000);
    return () => { request.current++; window.clearInterval(interval); };
  }, [reload]);
  const target = Number(margin);
  const validMargin = margin.trim() !== "" && Number.isFinite(target) && target >= 0 && target < 95;
  const denominator = 1 - target / 100;
  function currency(usd: number | null, inr: number | null) {
    if (display === "INR") return money(inr, "INR");
    if (display === "USD") return money(usd, "USD");
    return <>{money(usd, "USD")} <span className="text-sm font-normal text-text-muted">/ {money(inr, "INR")}</span></>;
  }

  return (
    <section data-testid="admin-cost-insights" aria-label="Observed supplier costs">
      <DevCard title="Observed supplier cost per minute" description="Use tenant call usage to plan your selling rates. Refreshes every minute.">
        <div className="flex flex-wrap items-end gap-4">
          <label className="text-xs text-text-muted">Usage window
            <select aria-label="Cost analysis window" value={days} onChange={(e) => setDays(Number(e.target.value))}
              className="ml-2 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text">
              <option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option>
            </select>
          </label>
          <label className="text-xs text-text-muted">Target gross margin (%)
            <SkeuoInput aria-label="Target gross margin percent" value={margin} onChange={(e) => setMargin(e.target.value)}
              type="number" min={0} max={94.99} step="0.5" aria-invalid={!validMargin} className="ml-2 w-24" />
          </label>
          <SkeuoButton variant="ghost" onClick={() => void reload()} disabled={report.loading} data-testid="cost-insights-refresh">Refresh costs</SkeuoButton>
          <p className="text-xs text-text-muted" aria-live="polite">{report.loading ? "Refreshing usage…" : report.data ? `Updated ${new Date(report.data.asOf).toLocaleTimeString()}` : ""}</p>
        </div>
        {!validMargin && <p role="alert" className="mt-3 text-sm text-danger">Enter a margin from 0% to less than 95%.</p>}
        <AdminError error={report.error} />
        {report.loading && !report.data && <AdminLoading loading />}
        {report.data && <>
          <p className="mt-4 text-xs text-text-muted">Total known supplier cost ÷ connected minutes, across {report.data.callsReviewed} completed tenant sessions. Each minute has equal weight.</p>
          {report.data.windowCapped && <p role="status" className="mt-2 text-sm text-warning">Limited to the most recent 5,000 sessions; unused prewarm overhead is excluded from this partial cohort. Use a shorter window for fuller coverage.</p>}
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {report.data.channels.map((channel) => {
              const hasAverage = channel.averageUsdPerMin !== null && channel.averageInrPerMin !== null;
              const suggestedUsd = hasAverage && validMargin ? Math.ceil(channel.averageUsdPerMin! / denominator * 1_000_000) / 1_000_000 : null;
              const suggestedInr = hasAverage && validMargin ? Math.ceil(channel.averageInrPerMin! / denominator * 100) / 100 : null;
              const grossMargin = (cost: number | null, price: number) => cost !== null && price > 0 ? `${((1 - cost / price) * 100).toFixed(1)}%` : "—";
              const usdMargin = grossMargin(channel.averageUsdPerMin, channel.currentPriceUsdPerMin);
              const inrMargin = grossMargin(channel.averageInrPerMin, channel.currentPriceInrPerMin);
              return <article key={channel.channel} data-testid={`cost-channel-${channel.channel}`} className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset p-4">
                <h4 className="font-semibold">{channel.label}</h4>
                <p className="mt-2 font-mono text-2xl font-semibold tabular-nums">{hasAverage ? currency(channel.averageUsdPerMin, channel.averageInrPerMin) : "No usable cost data yet"}<span className="ml-1 text-sm font-normal text-text-muted">{hasAverage ? "/ min" : ""}</span></p>
                <p className="mt-2 text-xs text-text-muted">{channel.calls} calls · {channel.tenants} tenants · {channel.connectedMinutes.toFixed(2)} connected minutes</p>
                <p className="mt-1 text-xs text-text-muted">Cost coverage: {channel.coveragePercent === null ? "no sessions" : `${channel.coveragePercent}%`} · {channel.missingCostCalls} records excluded for missing or invalid usage</p>
                <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                  <dt className="text-text-muted">API usage total</dt><dd className="text-right font-mono">{currency(channel.apiUsd, channel.apiInr)}</dd>
                  <dt className="text-text-muted">Carrier total</dt><dd className="text-right font-mono">{currency(channel.carrierUsd, channel.carrierInr)}</dd>
                  <dt className="text-text-muted">Transcription total</dt><dd className="text-right font-mono">{currency(channel.transcriptionUsd, channel.transcriptionInr)}</dd>
                  <dt className="text-text-muted">Unused prewarm total</dt><dd className="text-right font-mono">{currency(channel.unconnectedPrewarmUsd, channel.unconnectedPrewarmInr)}</dd>
                  <dt className="text-text-muted">Current selling price / min</dt><dd className="text-right font-mono">{currency(channel.currentPriceUsdPerMin, channel.currentPriceInrPerMin)}</dd>
                  <dt className="text-text-muted">Current gross margin</dt><dd className="text-right font-mono">{display === "both" ? `${usdMargin} USD / ${inrMargin} INR` : display === "INR" ? inrMargin : usdMargin}</dd>
                  <dt className="font-medium">Price at target margin / min</dt><dd className="text-right font-mono font-semibold" data-testid={`suggested-price-${channel.channel}`}>{currency(suggestedUsd, suggestedInr)}</dd>
                </dl>
                <p className="mt-3 text-xs text-text-muted">{channel.channel === "pstn" ? `${channel.carrierCdrCalls} carrier CDRs · ${channel.carrierEstimatedCalls} tariff estimates · ${channel.unconnectedPrewarmRecords} unused prewarm records` : "Web sessions have no carrier charge."}</p>
                {channel.reconstructedCalls > 0 && <p className="mt-1 text-xs text-text-muted">{channel.reconstructedCalls} historical calls reconstructed from saved response usage.</p>}
                {channel.models.length > 0 && <p className="mt-1 break-words text-xs text-text-muted">Models: {channel.models.join(", ")}</p>}
                <SkeuoButton variant="ghost" className="mt-4" disabled={report.loading || suggestedUsd === null || suggestedInr === null}
                  onClick={() => suggestedUsd !== null && suggestedInr !== null && onUsePrice(channel.channel === "pstn" ? "pstn" : "web", suggestedUsd, suggestedInr)}
                  data-testid={`use-suggested-${channel.channel}`}>Use suggested price in draft</SkeuoButton>
              </article>;
            })}
          </div>
          <p className="mt-4 text-xs text-text-muted">Suggested price = observed cost ÷ (1 − gross margin). Review the draft in Prices, then use its Save button to apply it.</p>
          <details className="mt-4 rounded-skeuo-sm border border-surface-border-subtle p-3">
            <summary className="cursor-pointer text-sm font-medium">Random call audit sample ({report.data.samples.length})</summary>
            <div className="mt-3 overflow-x-auto">
              <SkeuoTable><SkeuoTableHead><SkeuoTh>Call / tenant</SkeuoTh><SkeuoTh>Channel</SkeuoTh><SkeuoTh>Connected seconds</SkeuoTh><SkeuoTh>Supplier cost</SkeuoTh><SkeuoTh>Carrier source</SkeuoTh></SkeuoTableHead>
                <SkeuoTableBody>{report.data.samples.map((sample) => <SkeuoTableRow key={sample.callId}>
                  <SkeuoTd><span className="block font-mono text-xs">{sample.callId.slice(0, 8)}</span><span className="text-xs text-text-muted">{sample.tenant}</span></SkeuoTd>
                  <SkeuoTd>{sample.channel === "pstn" ? "PSTN" : "Web"}</SkeuoTd><SkeuoTd>{sample.durationSec}</SkeuoTd>
                  <SkeuoTd>{currency(sample.costUsd, sample.costInr)}</SkeuoTd><SkeuoTd>{sample.carrierSource === "vobiz_cdr" ? "CDR" : sample.carrierSource === "tariff_estimate" ? "Estimate" : "No carrier"}</SkeuoTd>
                </SkeuoTableRow>)}</SkeuoTableBody></SkeuoTable>
            </div>
          </details>
          <ul className="mt-4 flex list-disc flex-col gap-1 pl-4 text-xs text-text-muted">{report.data.notes.map((note) => <li key={note}>{note}</li>)}</ul>
          <p className="mt-2 text-xs text-text-muted"><a className="underline" href="https://www.vobiz.ai/docs/cdr" target="_blank" rel="noreferrer">Carrier billing documentation</a> · <a className="underline" href="https://ai.google.dev/gemini-api/docs/live-api/best-practices#pricing-and-billing" target="_blank" rel="noreferrer">Gemini billing documentation</a></p>
        </>}
      </DevCard>
    </section>
  );
}
