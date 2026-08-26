"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ConsolePage } from "@/components/console/ConsolePage";
import { PageHeader } from "@/components/console/PageHeader";
import { StatCard } from "@/components/console/StatCard";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { SkeuoStatusLight } from "@/components/ui/skeuo/SkeuoStatusLight";
import { DistributionList, LatencyBar } from "@/components/analytics/AnalyticsInstruments";
import {
  type FleetAnalytics,
  type MetricsSnapshot,
  aggregateFleetFromCalls,
  errorRate,
  fmtMs,
  fmtPct,
  topEntries,
} from "@/lib/analytics-utils";
import { ensureArray } from "@/lib/ensure-array";

type ProviderRow = { id?: string; enabled?: boolean; configured?: boolean; healthy?: boolean; stages?: string[] };
type TierRow = { tier?: string; combination_id?: string; preview?: Record<string, unknown>; error?: string };

const SECTIONS = [
  { id: "volume", label: "Volume" },
  { id: "quality", label: "Quality" },
  { id: "latency", label: "Latency" },
  { id: "reliability", label: "Reliability" },
  { id: "cost", label: "Cost" },
  { id: "memory", label: "Memory" },
  { id: "providers", label: "Providers" },
  { id: "combinations", label: "Combinations" },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

export function AnalyticsWorkspace() {
  const [metrics, setMetrics] = useState<MetricsSnapshot>({});
  const [fleet, setFleet] = useState<FleetAnalytics>({});
  const [providers, setProviders] = useState<ProviderRow[]>([]);
  const [tiers, setTiers] = useState<TierRow[]>([]);
  const [section, setSection] = useState<SectionId>("volume");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [mR, fR, pR, tR, callsR] = await Promise.all([
          fetch("/api/metrics", { credentials: "include" }),
          fetch("/api/analytics/fleet", { credentials: "include" }),
          fetch("/api/providers/status", { credentials: "include" }),
          fetch("/api/tiers", { credentials: "include" }),
          fetch("/api/calls?limit=500", { credentials: "include" }),
        ]);
        if (cancelled) return;
        if (mR.ok) setMetrics(await mR.json());
        if (fR.ok) {
          setFleet(await fR.json());
        } else if (callsR.ok) {
          const cj = await callsR.json();
          const list = ensureArray<Record<string, unknown>>(cj.calls);
          setFleet(aggregateFleetFromCalls(list, typeof cj.total === "number" ? cj.total : list.length));
        }
        if (pR.ok) {
          const j = await pR.json();
          setProviders((j.providers as ProviderRow[]) || []);
        }
        if (tR.ok) {
          const j = await tR.json();
          setTiers((j.tiers as TierRow[]) || []);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const errRate = errorRate(metrics);
  const cacheHit = metrics.brain_tokens?.cache_hit_rate ?? metrics.prompt_cache?.hit_rate;

  return (
    <ConsolePage className="space-y-6">
      <PageHeader
        eyebrow="Fleet instrumentation"
        title="Analytics"
        description="Aggregate volume, quality, latency, reliability, cost, and provider performance — separate from per-call debugging."
        actions={
          <Link href="/app/calls">
            <SkeuoButton variant="secondary" size="sm">Open Calls archive</SkeuoButton>
          </Link>
        }
      />

      <SkeuoPanel padding="md" title="Signal rack" description="Select instrumentation module">
        <div className="flex flex-wrap gap-2">
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setSection(s.id)}
              className={
                section === s.id
                  ? "skeuo-btn-primary rounded-skeuo-sm px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-white"
                  : "skeuo-btn-secondary rounded-skeuo-sm px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-text-muted"
              }
            >
              {s.label}
            </button>
          ))}
        </div>
      </SkeuoPanel>

      {loading ? (
        <SkeuoPanel padding="lg">
          <p className="text-sm text-text-muted">Loading fleet instrumentation…</p>
        </SkeuoPanel>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="E2E P50" value={fmtMs(metrics.e2e_ms?.p50)} unit="ms" />
            <StatCard label="E2E P95" value={fmtMs(metrics.e2e_ms?.p95)} unit="ms" tone="accent" />
            <StatCard label="Cache hit" value={fmtPct(cacheHit)} unit="%" tone="accent" />
            <StatCard
              label="Completion"
              value={fmtPct(fleet.completion_rate)}
              unit="%"
              tone={fleet.completion_rate != null && fleet.completion_rate < 0.9 ? "warn" : "ok"}
            />
          </div>

          {section === "volume" && (
            <div className="grid gap-6 lg:grid-cols-2">
              <SkeuoPanel title="Volume" description="Call archive traffic — durable records" padding="md">
                <div className="grid grid-cols-2 gap-3">
                  <StatCard label="Total calls" value={String(fleet.total_calls ?? "—")} />
                  <StatCard label="Sample" value={String(fleet.sample_size ?? "—")} hint="Recent archive window" />
                  <StatCard label="Avg duration" value={fleet.duration_sec_avg != null ? String(fleet.duration_sec_avg) : "—"} unit="s" />
                  <StatCard label="Live sessions" value={String(metrics.sessions?.active ?? "—")} />
                </div>
                <DistributionList title="Channel mix" entries={topEntries(fleet.channels)} />
              </SkeuoPanel>
              <SkeuoPanel title="Tier distribution" description="Traffic by configured tier" padding="md">
                <DistributionList title="Calls by tier" entries={topEntries(fleet.tiers)} />
                <DistributionList
                  title="Finalization"
                  entries={Object.entries(fleet.finalization || {}) as Array<[string, number]>}
                />
              </SkeuoPanel>
            </div>
          )}

          {section === "quality" && (
            <SkeuoPanel title="Quality & disposition" description="Task outcome mix from archived calls" padding="md">
              <DistributionList
                title="Disposition trends"
                entries={topEntries(fleet.dispositions)}
                emptyLabel="No disposition data — complete calls in Test Studio first."
              />
              <p className="mt-4 text-xs text-text-muted">
                Per-call outcome detail, summaries, and extracted fields live in the Calls investigation workspace.
              </p>
            </SkeuoPanel>
          )}

          {section === "latency" && (
            <div className="grid gap-6 lg:grid-cols-2">
              <SkeuoPanel title="Stage latency" description="In-process turn samples from /api/metrics" padding="md">
                <div className="space-y-4">
                  <LatencyBar label="STT" stats={metrics.stt_ms} tone="bg-status-info/70" />
                  <LatencyBar label="LLM (brain)" stats={metrics.brain_ms} tone="bg-accent-primary/70" />
                  <LatencyBar label="LLM TTFT" stats={metrics.brain_ttft_ms} tone="bg-accent-primary/50" />
                  <LatencyBar label="TTS" stats={metrics.tts_ms} tone="bg-status-success/70" />
                  <LatencyBar label="E2E turn" stats={metrics.e2e_ms} tone="bg-accent-secondary/70" />
                </div>
              </SkeuoPanel>
              <SkeuoPanel title="TTFT split" description="First turn vs steady-state" padding="md">
                <div className="grid gap-3 sm:grid-cols-2">
                  <StatCard label="First turn TTFT P50" value={fmtMs(metrics.first_turn_ttft_ms?.p50)} unit="ms" />
                  <StatCard label="Steady TTFT P50" value={fmtMs(metrics.steady_turn_ttft_ms?.p50)} unit="ms" />
                  <StatCard label="Brain prep P50" value={fmtMs(metrics.brain_prep_ms?.p50)} unit="ms" />
                  <StatCard label="Turn samples" value={String(metrics.total_turns ?? 0)} />
                </div>
                <div className="mt-4 skeuo-inset rounded-skeuo-md p-4">
                  <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Stage waterfall (P50)</p>
                  <div className="mt-3 flex h-10 overflow-hidden rounded-skeuo-sm border border-surface-border-subtle">
                    <div className="flex w-[28%] items-center justify-center bg-status-info/30 font-mono text-[10px]">STT</div>
                    <div className="flex w-[44%] items-center justify-center bg-accent-primary/35 font-mono text-[10px]">LLM</div>
                    <div className="flex w-[28%] items-center justify-center bg-status-success/35 font-mono text-[10px]">TTS</div>
                  </div>
                </div>
              </SkeuoPanel>
            </div>
          )}

          {section === "reliability" && (
            <SkeuoPanel title="Reliability" description="Errors, rate limits, and finalization failures" padding="md">
              <div className="grid gap-3 sm:grid-cols-3">
                <StatCard
                  label="Error rate"
                  value={errRate != null ? fmtPct(errRate) : "—"}
                  unit="%"
                  tone={errRate != null && errRate > 0.05 ? "warn" : "ok"}
                />
                <StatCard label="Rate limited" value={String(metrics.rate_limited ?? 0)} />
                <StatCard label="Failed archives" value={String(fleet.finalization?.failed ?? 0)} tone="warn" />
              </div>
              <DistributionList
                title="Error codes"
                entries={topEntries(metrics.errors)}
                emptyLabel="No provider errors recorded in this process window."
              />
            </SkeuoPanel>
          )}

          {section === "cost" && (
            <SkeuoPanel title="Cost & usage" description="Brain token layers — INR estimates deferred to benchmark history" padding="md">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <StatCard label="Brain calls" value={String(metrics.brain_tokens?.calls ?? 0)} />
                <StatCard label="Input tokens P50" value={metrics.brain_tokens?.input?.p50 != null ? String(metrics.brain_tokens.input.p50) : "—"} />
                <StatCard label="Output tokens P50" value={metrics.brain_tokens?.output?.p50 != null ? String(metrics.brain_tokens.output.p50) : "—"} />
                <StatCard label="Cached tokens P50" value={metrics.brain_tokens?.cached?.p50 != null ? String(metrics.brain_tokens.cached.p50) : "—"} tone="accent" />
              </div>
              {metrics.brain_tokens?.layer_avg_est && (
                <DistributionList
                  title="Layer token estimates (avg)"
                  entries={Object.entries(metrics.brain_tokens.layer_avg_est).map(([k, v]) => [k, Math.round(v)])}
                />
              )}
              <p className="mt-4 text-xs text-text-muted">
                Per-minute INR breakdown and tier comparison require benchmark session history (Phase 11).
              </p>
            </SkeuoPanel>
          )}

          {section === "memory" && (
            <SkeuoPanel title="Memory health" description="Projection layer estimates and merge activity" padding="md">
              <div className="grid gap-3 sm:grid-cols-2">
                <StatCard label="Summary layer est." value={String(metrics.brain_tokens?.layer_avg_est?.summary ?? "—")} />
                <StatCard label="History layer est." value={String(metrics.brain_tokens?.layer_avg_est?.history ?? "—")} />
              </div>
              <p className="mt-4 text-sm text-text-muted">
                Per-call memory merge ops, projections, and event provenance are in the Calls investigation console — not mixed into fleet charts.
              </p>
              <Link href="/app/calls" className="mt-4 inline-block">
                <SkeuoButton variant="secondary" size="sm">Inspect call memory</SkeuoButton>
              </Link>
            </SkeuoPanel>
          )}

          {section === "providers" && (
            <SkeuoPanel title="Provider performance" description="Registry health lamps — STT · LLM · TTS" padding="md">
              <ul className="space-y-2">
                {providers.length === 0 ? (
                  <li className="text-sm text-text-muted">No providers in registry.</li>
                ) : (
                  providers.map((p) => (
                    <li
                      key={p.id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-skeuo-sm border border-surface-border-subtle skeuo-inset px-3 py-2"
                    >
                      <span className="font-mono text-sm text-text">{p.id}</span>
                      <div className="flex flex-wrap items-center gap-3">
                        <SkeuoStatusLight
                          status={p.healthy ? "ok" : p.configured ? "warn" : "idle"}
                          label={p.healthy ? "Healthy" : p.configured ? "Degraded" : "Not configured"}
                        />
                        <span className="font-mono text-[10px] text-text-subtle">
                          {(p.stages || []).join(" · ") || "—"}
                        </span>
                      </div>
                    </li>
                  ))
                )}
              </ul>
            </SkeuoPanel>
          )}

          {section === "combinations" && (
            <SkeuoPanel title="Combination performance" description="Resolved stacks per tier" padding="md">
              <ul className="space-y-2">
                {tiers.map((t) => (
                  <li key={t.tier} className="rounded-skeuo-sm border border-surface-border-subtle skeuo-inset px-3 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-mono text-sm uppercase text-text">{t.tier}</span>
                      <span className="font-mono text-[10px] text-text-subtle">
                        {fleet.combinations?.[t.combination_id || ""] ?? 0} calls
                      </span>
                    </div>
                    <p className="mt-1 font-mono text-[10px] text-text-muted break-all">
                      {t.combination_id || t.error || "—"}
                    </p>
                  </li>
                ))}
              </ul>
              <DistributionList title="Archive combination mix" entries={topEntries(fleet.combinations)} />
            </SkeuoPanel>
          )}
        </>
      )}
    </ConsolePage>
  );
}
