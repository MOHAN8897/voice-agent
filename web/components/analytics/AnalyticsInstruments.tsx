"use client";

import { cn } from "@/lib/cn";
import type { StageStats } from "@/lib/analytics-utils";

export function LatencyBar({
  label,
  stats,
  tone,
}: {
  label: string;
  stats?: StageStats;
  tone: string;
}) {
  const p50 = stats?.p50 ?? 0;
  const p95 = stats?.p95 ?? 0;
  const max = Math.max(p50, p95, 1);

  return (
    <div className="space-y-2">
      <div className="flex justify-between font-mono text-[10px] uppercase tracking-wider text-text-subtle">
        <span>{label}</span>
        <span>
          P50 {stats?.p50 != null ? `${stats.p50}ms` : "—"} · P95 {stats?.p95 != null ? `${stats.p95}ms` : "—"}
        </span>
      </div>
      <div className="space-y-1">
        <div className="h-2 overflow-hidden rounded-full skeuo-inset">
          <div className={cn("h-full rounded-full", tone)} style={{ width: `${Math.min(100, (p50 / max) * 100)}%` }} />
        </div>
        <div className="h-1.5 overflow-hidden rounded-full skeuo-inset">
          <div
            className={cn("h-full rounded-full opacity-70", tone)}
            style={{ width: `${Math.min(100, (p95 / max) * 100)}%` }}
          />
        </div>
      </div>
      <p className="font-mono text-[9px] text-text-subtle">n={stats?.count ?? 0}</p>
    </div>
  );
}

export function DistributionList({
  title,
  entries,
  emptyLabel,
}: {
  title: string;
  entries: Array<[string, number]>;
  emptyLabel?: string;
}) {
  const total = entries.reduce((s, [, v]) => s + v, 0);
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">{title}</p>
      {entries.length === 0 ? (
        <p className="mt-2 text-sm text-text-muted">{emptyLabel || "No data in sample."}</p>
      ) : (
        <ul className="mt-2 space-y-2">
          {entries.map(([key, count]) => {
            const pct = total > 0 ? Math.round((count / total) * 100) : 0;
            return (
              <li key={key} className="skeuo-inset rounded-skeuo-sm px-3 py-2">
                <div className="flex justify-between gap-2 text-sm">
                  <span className="text-text-muted">{key.replace(/_/g, " ")}</span>
                  <span className="font-mono text-text">{count}</span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-panel-raised">
                  <div className="h-full bg-accent-primary/60" style={{ width: `${pct}%` }} />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
