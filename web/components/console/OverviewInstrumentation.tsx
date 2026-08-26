import Link from "next/link";
import { SkeuoButton, SkeuoPanel, SkeuoStatusLight } from "@/components/ui/skeuo";
import { PageHeader } from "@/components/console/PageHeader";

function dbStatus(health: Record<string, unknown>): { label: string; status: "ok" | "warn" | "error" | "idle" } {
  const db = health.database;
  if (db && typeof db === "object" && "ok" in db) {
    const row = db as { ok?: boolean; configured?: boolean };
    if (!row.configured) return { label: "Not configured", status: "idle" };
    return row.ok ? { label: "Connected", status: "ok" } : { label: "Offline", status: "error" };
  }
  return { label: "—", status: "idle" };
}

function redisStatus(health: Record<string, unknown>): { label: string; status: "ok" | "warn" | "error" | "idle" } {
  const redis = health.redis;
  if (redis && typeof redis === "object" && "ok" in redis) {
    const row = redis as { ok?: boolean; configured?: boolean };
    if (!row.configured) return { label: "Not configured", status: "idle" };
    return row.ok ? { label: "Connected", status: "ok" } : { label: "Offline", status: "error" };
  }
  return { label: "—", status: "idle" };
}

export function OverviewInstrumentation({
  health,
  metrics,
}: {
  health: Record<string, unknown>;
  metrics: Record<string, unknown>;
}) {
  const sessions = (metrics.sessions as { active?: number } | undefined)?.active;
  const cache = metrics.prompt_cache as { hit_rate?: number } | undefined;
  const apiOk = Boolean(health.ok);
  const db = dbStatus(health);
  const redis = redisStatus(health);

  return (
  <div className="space-y-8">
    <PageHeader
      eyebrow="System"
      title="System Overview"
      description="Instrumentation command center — agent health, live calls, latency, cost, and provider lamps."
      actions={
        <Link href="/app/test-studio">
          <SkeuoButton variant="primary">Open Test Studio</SkeuoButton>
        </Link>
      }
    />

    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <SkeuoPanel title="Active agents" description="Fleet health summary" padding="md">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-muted">API health</span>
            <SkeuoStatusLight status={apiOk ? "ok" : "error"} label={apiOk ? "Healthy" : "Degraded"} />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-muted">Active sessions</span>
            <span className="font-mono text-lg tabular-nums text-text">
              {sessions != null ? String(sessions) : "—"}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-muted">Agents needing attention</span>
            <SkeuoStatusLight status="ok" label="None" />
          </div>
        </div>
      </SkeuoPanel>

      <SkeuoPanel title="Live calls" description="Today's traffic" padding="md">
        <div className="grid grid-cols-2 gap-3">
          <div className="skeuo-inset rounded-skeuo-md p-3">
            <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Today</p>
            <p className="mt-1 font-mono text-xl tabular-nums text-text">—</p>
          </div>
          <div className="skeuo-inset rounded-skeuo-md p-3">
            <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Active</p>
            <p className="mt-1 font-mono text-xl tabular-nums text-status-live">
              {sessions != null ? String(sessions) : "—"}
            </p>
          </div>
          <div className="skeuo-inset rounded-skeuo-md p-3">
            <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Completed</p>
            <p className="mt-1 font-mono text-xl tabular-nums text-text">—</p>
          </div>
          <div className="skeuo-inset rounded-skeuo-md p-3">
            <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Failed</p>
            <p className="mt-1 font-mono text-xl tabular-nums text-text">—</p>
          </div>
        </div>
      </SkeuoPanel>

      <SkeuoPanel title="Latency" description="First audible byte" padding="md">
        <div className="space-y-3">
          <div className="flex justify-between font-mono text-sm">
            <span className="text-text-muted">P50</span>
            <span className="tabular-nums text-text">—</span>
          </div>
          <div className="flex justify-between font-mono text-sm">
            <span className="text-text-muted">P95</span>
            <span className="tabular-nums text-text">—</span>
          </div>
          <div className="flex justify-between font-mono text-sm">
            <span className="text-text-muted">First byte</span>
            <span className="tabular-nums text-accent-primary">—</span>
          </div>
          <p className="text-xs text-text-muted">Populates from call traces after production traffic.</p>
        </div>
      </SkeuoPanel>

      <SkeuoPanel title="Cost" description="Usage estimate" padding="md">
        <div className="grid grid-cols-2 gap-3">
          <div className="skeuo-inset rounded-skeuo-md p-3">
            <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Today</p>
            <p className="mt-1 font-mono text-xl tabular-nums text-text">—</p>
          </div>
          <div className="skeuo-inset rounded-skeuo-md p-3">
            <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">This month</p>
            <p className="mt-1 font-mono text-xl tabular-nums text-text">—</p>
          </div>
        </div>
        <p className="mt-3 font-mono text-xs text-text-muted">
          Est. per minute: — · Cache hit{" "}
          {cache?.hit_rate != null ? `${Math.round(cache.hit_rate * 100)}%` : "—"}
        </p>
      </SkeuoPanel>

      <SkeuoPanel title="System health" description="Provider & infra lamps" padding="md" className="xl:col-span-2">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="flex items-center justify-between rounded-skeuo-sm border border-surface-border-subtle px-3 py-2 skeuo-inset">
            <span className="text-sm text-text-muted">STT</span>
            <SkeuoStatusLight status={apiOk ? "ok" : "warn"} label="Pipeline" />
          </div>
          <div className="flex items-center justify-between rounded-skeuo-sm border border-surface-border-subtle px-3 py-2 skeuo-inset">
            <span className="text-sm text-text-muted">LLM</span>
            <SkeuoStatusLight status={apiOk ? "ok" : "warn"} label="Pipeline" />
          </div>
          <div className="flex items-center justify-between rounded-skeuo-sm border border-surface-border-subtle px-3 py-2 skeuo-inset">
            <span className="text-sm text-text-muted">TTS</span>
            <SkeuoStatusLight status={apiOk ? "ok" : "warn"} label="Pipeline" />
          </div>
          <div className="flex items-center justify-between rounded-skeuo-sm border border-surface-border-subtle px-3 py-2 skeuo-inset">
            <span className="text-sm text-text-muted">Database</span>
            <SkeuoStatusLight status={db.status} label={db.label} />
          </div>
          <div className="flex items-center justify-between rounded-skeuo-sm border border-surface-border-subtle px-3 py-2 skeuo-inset">
            <span className="text-sm text-text-muted">Redis</span>
            <SkeuoStatusLight status={redis.status} label={redis.label} />
          </div>
          <div className="flex items-center justify-between rounded-skeuo-sm border border-surface-border-subtle px-3 py-2 skeuo-inset">
            <span className="text-sm text-text-muted">Worker</span>
            <SkeuoStatusLight status={apiOk ? "ok" : "idle"} label={String(health.version ?? "—")} />
          </div>
        </div>
      </SkeuoPanel>
    </div>

    <div className="grid gap-4 lg:grid-cols-2">
      <SkeuoPanel title="Needs your attention" padding="md">
        <ul className="space-y-3 text-sm text-text-muted">
          <li>No blocking incidents reported.</li>
          <li>Review agent configuration before routing production traffic.</li>
        </ul>
      </SkeuoPanel>
      <SkeuoPanel title="Workflow" padding="md">
        <ol className="space-y-3 text-sm">
          {[
            ["Configure agent", "/app/agents"],
            ["Test live", "/app/test-studio"],
            ["Inspect calls", "/app/calls"],
            ["Analytics", "/app/analytics"],
          ].map(([label, href], i) => (
            <li key={href} className="flex items-center justify-between">
              <span className="text-text-muted">
                <span className="mr-2 font-mono text-accent-primary/80">0{i + 1}</span>
                {label}
              </span>
              <Link href={href} className="text-accent-primary hover:underline">
                Open
              </Link>
            </li>
          ))}
        </ol>
      </SkeuoPanel>
    </div>
  </div>
  );
}
