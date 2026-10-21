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
  prewarmPerMinUsd?: number;
  prewarmPerMinInr?: number;
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

export function CostInsightsPanel({ display }: {
  display: "USD" | "INR" | "both";
  onUsePrice?: (field: "pstn" | "web", usd: number, inr: number) => void;
}) {
  const [days, setDays] = useState(30);
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

  function currency(usd: number | null, inr: number | null) {
    if (display === "INR") return money(inr, "INR");
    if (display === "USD") return money(usd, "USD");
    return <>{money(usd, "USD")} <span className="text-sm font-normal text-text-muted">/ {money(inr, "INR")}</span></>;
  }

  return (
    <section data-testid="admin-cost-insights" aria-label="Observed supplier costs">
      <DevCard title="Observed supplier cost per minute" description="Live supplier costs for carrier telephony, recording, transcription, and agent AI engine averaged per minute.">
        <div className="flex flex-wrap items-end gap-4">
          <label className="text-xs text-text-muted">Usage window
            <select aria-label="Cost analysis window" value={days} onChange={(e) => setDays(Number(e.target.value))}
              className="ml-2 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text">
              <option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option>
            </select>
          </label>
          <SkeuoButton variant="ghost" onClick={() => void reload()} disabled={report.loading} data-testid="cost-insights-refresh">Refresh costs</SkeuoButton>
          <p className="text-xs text-text-muted" aria-live="polite">{report.loading ? "Refreshing usage…" : report.data ? `Updated ${new Date(report.data.asOf).toLocaleTimeString()}` : ""}</p>
        </div>
        <AdminError error={report.error} />
        {report.loading && !report.data && <AdminLoading loading />}
        {report.data && <>
          <p className="mt-4 text-xs text-text-muted">Total known supplier cost ÷ connected minutes, across {report.data.callsReviewed} completed tenant sessions. Normalized strictly to 1-minute usage increments.</p>
          {report.data.windowCapped && <p role="status" className="mt-2 text-sm text-warning">Limited to the most recent 5,000 sessions; unused prewarm overhead is excluded from this partial cohort. Use a shorter window for fuller coverage.</p>}
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {report.data.channels.map((channel) => {
              const mins = channel.connectedMinutes > 0 ? channel.connectedMinutes : 0;
              const hasAverage = channel.averageUsdPerMin !== null && channel.averageInrPerMin !== null;
              const carrierPerMinUsd = mins > 0 ? channel.carrierUsd / mins : 0;
              const carrierPerMinInr = mins > 0 ? channel.carrierInr / mins : 0;
              const apiPerMinUsd = mins > 0 ? channel.apiUsd / mins : 0;
              const apiPerMinInr = mins > 0 ? channel.apiInr / mins : 0;
              const txPerMinUsd = mins > 0 ? channel.transcriptionUsd / mins : 0;
              const txPerMinInr = mins > 0 ? channel.transcriptionInr / mins : 0;
              const prewarmPerMinUsd = channel.prewarmPerMinUsd ?? (mins > 0 ? (channel.unconnectedPrewarmUsd || 0) / mins : 0);
              const prewarmPerMinInr = channel.prewarmPerMinInr ?? (mins > 0 ? (channel.unconnectedPrewarmInr || 0) / mins : 0);
              const totalPerMinUsd = channel.averageUsdPerMin ?? (carrierPerMinUsd + apiPerMinUsd + txPerMinUsd + (channel.channel === "pstn" ? prewarmPerMinUsd : 0));
              const totalPerMinInr = channel.averageInrPerMin ?? (carrierPerMinInr + apiPerMinInr + txPerMinInr + (channel.channel === "pstn" ? prewarmPerMinInr : 0));

              return <article key={channel.channel} data-testid={`cost-channel-${channel.channel}`} className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset p-4">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold text-text">{channel.label}</h4>
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-surface-panel border border-surface-border-subtle text-text-muted">
                    {mins > 0 ? `${mins.toFixed(2)} min` : "0 min"}
                  </span>
                </div>
                <div className="mt-2 flex items-baseline gap-1.5">
                  <p className="font-mono text-2xl font-bold tabular-nums text-text">
                    {hasAverage ? currency(totalPerMinUsd, totalPerMinInr) : "No usable cost data yet"}
                  </p>
                  <span className="text-sm font-semibold text-text-muted">{hasAverage ? "/ min" : ""}</span>
                </div>
                <p className="mt-1 text-xs text-text-muted">{channel.calls} calls · {channel.tenants} tenants · {channel.connectedMinutes.toFixed(2)} connected minutes</p>
                <p className="mt-0.5 text-xs text-text-muted">Cost coverage: {channel.coveragePercent === null ? "no sessions" : `${channel.coveragePercent}%`} · {channel.missingCostCalls} records excluded for missing or invalid usage</p>

                <div className="mt-4 rounded-skeuo-xs border border-surface-border-subtle bg-surface-panel p-3">
                  <h5 className="text-[11px] font-bold uppercase tracking-wider text-text-muted">
                    Admin Per-Minute Supplier Cost (1 min normalized)
                  </h5>
                  <dl className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                    {channel.channel === "pstn" ? (
                      <>
                        <dt className="text-text-muted font-medium">Carrier (Telephony & Recording) / min</dt>
                        <dd className="text-right font-mono font-semibold text-text">
                          {mins > 0 ? currency(carrierPerMinUsd, carrierPerMinInr) : "—"} <span className="text-[10px] font-normal text-text-muted">{mins > 0 ? "/ min" : ""}</span>
                        </dd>
                      </>
                    ) : (
                      <>
                        <dt className="text-text-muted font-medium">Carrier (Telephony & Recording)</dt>
                        <dd className="text-right font-mono text-text-muted italic">
                          Not applicable (Web session)
                        </dd>
                      </>
                    )}

                    <dt className="text-text-muted font-medium">Agent AI Core (Gemini Live) / min</dt>
                    <dd className="text-right font-mono font-semibold text-text">
                      {mins > 0 ? currency(apiPerMinUsd, apiPerMinInr) : "—"} <span className="text-[10px] font-normal text-text-muted">{mins > 0 ? "/ min" : ""}</span>
                    </dd>

                    <dt className="text-text-muted font-medium">Transcription / min</dt>
                    <dd className="text-right font-mono font-semibold text-text">
                      {mins > 0 ? currency(txPerMinUsd, txPerMinInr) : "—"} <span className="text-[10px] font-normal text-text-muted">{mins > 0 ? "/ min" : ""}</span>
                    </dd>

                    {channel.channel === "pstn" && ((channel.unconnectedPrewarmRecords ?? 0) > 0 || prewarmPerMinInr > 0) && (
                      <>
                        <dt className="text-text-muted font-medium">Unused Prewarm Overhead / min</dt>
                        <dd className="text-right font-mono font-semibold text-text">
                          {mins > 0 ? currency(prewarmPerMinUsd, prewarmPerMinInr) : "—"} <span className="text-[10px] font-normal text-text-muted">{mins > 0 ? "/ min" : ""}</span>
                        </dd>
                      </>
                    )}

                    <dt className="pt-2 border-t border-surface-border-subtle font-bold text-text">
                      Total Admin Supplier Cost / min
                    </dt>
                    <dd className="pt-2 border-t border-surface-border-subtle text-right font-mono font-bold text-accent-primary">
                      {hasAverage ? currency(totalPerMinUsd, totalPerMinInr) : "—"} <span className="text-[10px] font-normal text-text-muted">{hasAverage ? "/ min" : ""}</span>
                    </dd>
                  </dl>
                </div>

                <p className="mt-3 text-xs text-text-muted">{channel.channel === "pstn" ? `${channel.carrierCdrCalls} carrier CDRs · ${channel.carrierEstimatedCalls} tariff estimates · ${channel.unconnectedPrewarmRecords} unused prewarm records` : "Web sessions have no carrier charge."}</p>
                {channel.reconstructedCalls > 0 && <p className="mt-1 text-xs text-text-muted">{channel.reconstructedCalls} historical calls reconstructed from saved response usage.</p>}
                {channel.models.length > 0 && <p className="mt-1 break-words text-xs text-text-muted">Models: {channel.models.join(", ")}</p>}
              </article>;
            })}
          </div>
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
