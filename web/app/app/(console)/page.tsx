import { apiGet } from "@/lib/api";
import Link from "next/link";
import { PageHeader } from "@/components/console/PageHeader";
import { StatCard } from "@/components/console/StatCard";
import { Panel } from "@/components/console/Panel";

function dbLabel(health: Record<string, unknown>): string {
  const db = health.database;
  if (db && typeof db === "object" && "ok" in db) {
    const row = db as { ok?: boolean; configured?: boolean };
    if (!row.configured) return "Not configured";
    return row.ok ? "Connected" : "Offline";
  }
  return "—";
}

function redisLabel(health: Record<string, unknown>): string {
  const redis = health.redis;
  if (redis && typeof redis === "object" && "ok" in redis) {
    const row = redis as { ok?: boolean; configured?: boolean };
    if (!row.configured) return "Not configured";
    return row.ok ? "Connected" : "Offline";
  }
  return "—";
}

export default async function OverviewPage() {
  let health: Record<string, unknown> = {};
  let metrics: Record<string, unknown> = {};
  try {
    health = await apiGet("/api/health");
  } catch {
    health = { ok: false };
  }
  try {
    metrics = await apiGet("/api/metrics");
  } catch {
    metrics = {};
  }

  const sessions = (metrics.sessions as { active?: number } | undefined)?.active;
  const cache = metrics.prompt_cache as { hit_rate?: number } | undefined;

  return (
    <div>
      <PageHeader
        eyebrow="Fleet"
        title="Overview"
        description="Health, latency, and what needs you — not a provider matrix."
        actions={
          <Link href="/app/test-studio" className="rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white">
            Open Test Studio
          </Link>
        }
      />

      <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="API health" value={health.ok ? "Healthy" : "Degraded"} tone={health.ok ? "ok" : "warn"} hint={String(health.version ?? "—")} />
        <StatCard label="Database" value={dbLabel(health)} tone={dbLabel(health) === "Connected" ? "ok" : "warn"} />
        <StatCard label="Redis" value={redisLabel(health)} />
        <StatCard label="Active sessions" value={sessions != null ? String(sessions) : "—"} hint="Live conversation manager" />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <StatCard label="Calls today" value="—" hint="Populates after production traffic" />
        <StatCard label="P95 first-audible" value="—" hint="From call traces" />
        <StatCard
          label="Prompt cache"
          value={cache?.hit_rate != null ? `${Math.round(cache.hit_rate * 100)}%` : "—"}
          tone="accent"
          hint="Stable brain prefix"
        />
      </div>

      <div className="mt-8 grid gap-4 lg:grid-cols-2">
        <Panel title="Needs your attention">
          <ul className="space-y-3 text-sm text-text-muted">
            <li>No blocking incidents reported.</li>
            <li>Review agent configuration before routing production traffic.</li>
          </ul>
        </Panel>
        <Panel title="Workflow">
          <ol className="space-y-3 text-sm">
            {[
              ["Configure agent", "/app/agents"],
              ["Test live", "/app/test-studio"],
              ["Inspect calls", "/app/calls"],
              ["Analytics", "/app/analytics"],
            ].map(([label, href], i) => (
              <li key={href} className="flex items-center justify-between">
                <span className="text-text-muted">
                  <span className="mr-2 font-mono text-accent/70">0{i + 1}</span>
                  {label}
                </span>
                <Link href={href} className="text-accent hover:underline">
                  Open
                </Link>
              </li>
            ))}
          </ol>
        </Panel>
      </div>
    </div>
  );
}
