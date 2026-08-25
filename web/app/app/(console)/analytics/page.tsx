import { apiGet } from "@/lib/api";
import { PageHeader } from "@/components/console/PageHeader";
import { StatCard } from "@/components/console/StatCard";
import { Panel } from "@/components/console/Panel";

export default async function AnalyticsPage() {
  let metrics: Record<string, unknown> = {};
  try {
    metrics = await apiGet("/api/metrics");
  } catch {
    metrics = {};
  }

  const cache = metrics.prompt_cache as { hit_rate?: number } | undefined;
  const snap = metrics as { e2e_p50_ms?: number; e2e_p95_ms?: number; error_rate?: number };

  return (
    <div>
      <PageHeader
        eyebrow="Fleet"
        title="Analytics"
        description="Quality, latency, reliability, and cost — separate from per-call debugging."
      />

      <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="E2E P50" value={snap.e2e_p50_ms != null ? `${Math.round(snap.e2e_p50_ms)}ms` : "—"} />
        <StatCard label="E2E P95" value={snap.e2e_p95_ms != null ? `${Math.round(snap.e2e_p95_ms)}ms` : "—"} />
        <StatCard
          label="Cache hit"
          value={cache?.hit_rate != null ? `${Math.round(cache.hit_rate * 100)}%` : "—"}
          tone="accent"
        />
        <StatCard
          label="Error rate"
          value={snap.error_rate != null ? `${Math.round(snap.error_rate * 100)}%` : "—"}
          tone={snap.error_rate && snap.error_rate > 0.05 ? "warn" : "ok"}
        />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Panel title="Latency waterfall">
          <p className="text-sm text-text-muted">STT → LLM TTFT → TTS. Per-call traces live on the Calls page.</p>
          <div className="mt-4 flex h-8 overflow-hidden rounded-lg bg-surface-raised">
            <div className="flex w-[28%] items-center justify-center bg-accent-secondary/40 font-mono text-[10px] text-text">STT</div>
            <div className="flex w-[44%] items-center justify-center bg-accent/40 font-mono text-[10px] text-white">LLM</div>
            <div className="flex w-[28%] items-center justify-center bg-accent-hover/50 font-mono text-[10px] text-white">TTS</div>
          </div>
        </Panel>
        <Panel title="Disposition mix">
          <p className="text-sm text-text-muted">Aggregates appear after calls finalize with structured outcomes.</p>
          <ul className="mt-4 space-y-2 text-sm text-text-muted">
            <li className="flex justify-between"><span>Qualified</span><span className="font-mono">—</span></li>
            <li className="flex justify-between"><span>Callback</span><span className="font-mono">—</span></li>
            <li className="flex justify-between"><span>Not interested</span><span className="font-mono">—</span></li>
          </ul>
        </Panel>
      </div>
    </div>
  );
}
