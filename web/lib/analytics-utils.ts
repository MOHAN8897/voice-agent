export type StageStats = {
  count?: number;
  p50?: number | null;
  p95?: number | null;
  avg?: number | null;
  min?: number | null;
  max?: number | null;
};

export type MetricsSnapshot = {
  uptime_s?: number;
  total_turns?: number;
  stt_ms?: StageStats;
  brain_ms?: StageStats;
  tts_ms?: StageStats;
  e2e_ms?: StageStats;
  brain_ttft_ms?: StageStats;
  brain_prep_ms?: StageStats;
  first_turn_ttft_ms?: StageStats;
  steady_turn_ttft_ms?: StageStats;
  brain_tokens?: {
    calls?: number;
    cache_hit_rate?: number;
    cache_write_rate?: number;
    input?: StageStats;
    output?: StageStats;
    cached?: StageStats;
    layer_avg_est?: Record<string, number>;
  };
  prompt_cache?: { hit_rate?: number };
  recent_brain_turns?: Array<Record<string, unknown>>;
  errors?: Record<string, number>;
  rate_limited?: number;
  sessions?: { active?: number };
};

export type FleetAnalytics = {
  total_calls?: number;
  sample_size?: number;
  dispositions?: Record<string, number>;
  channels?: Record<string, number>;
  tiers?: Record<string, number>;
  combinations?: Record<string, number>;
  finalization?: { complete?: number; failed?: number; other?: number };
  duration_sec_avg?: number | null;
  completion_rate?: number | null;
};

export function fmtMs(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${Math.round(v)}`;
}

export function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${Math.round(v * 100)}`;
}

export function topEntries(map: Record<string, number> | undefined, limit = 8) {
  if (!map) return [];
  return Object.entries(map)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit);
}

export function aggregateFleetFromCalls(
  items: Array<Record<string, unknown>>,
  total?: number
): FleetAnalytics {
  const dispositions: Record<string, number> = {};
  const channels: Record<string, number> = {};
  const tiers: Record<string, number> = {};
  const combinations: Record<string, number> = {};
  let finalization_complete = 0;
  let finalization_failed = 0;
  const durations: number[] = [];

  for (const row of items) {
    const d = String(row.disposition || "pending");
    dispositions[d] = (dispositions[d] || 0) + 1;
    const ch = String(row.channel || "unknown");
    channels[ch] = (channels[ch] || 0) + 1;
    const tier = String(row.tier || "unknown");
    tiers[tier] = (tiers[tier] || 0) + 1;
    const combo = String(row.combination_id || "unknown");
    combinations[combo] = (combinations[combo] || 0) + 1;
    const fs = String(row.finalization_status || "");
    if (fs === "complete") finalization_complete += 1;
    else if (fs === "failed") finalization_failed += 1;
    const dur = row.duration_sec;
    if (typeof dur === "number" && dur >= 0) durations.push(dur);
  }

  const avg_duration = durations.length
    ? Math.round((durations.reduce((a, b) => a + b, 0) / durations.length) * 10) / 10
    : null;

  return {
    total_calls: total ?? items.length,
    sample_size: items.length,
    dispositions,
    channels,
    tiers,
    combinations,
    finalization: {
      complete: finalization_complete,
      failed: finalization_failed,
      other: Math.max(0, items.length - finalization_complete - finalization_failed),
    },
    duration_sec_avg: avg_duration,
    completion_rate: items.length ? Math.round((finalization_complete / items.length) * 1000) / 1000 : null,
  };
}

export function errorRate(metrics: MetricsSnapshot): number | null {
  const turns = metrics.total_turns ?? 0;
  const errors = Object.values(metrics.errors || {}).reduce((a, b) => a + b, 0);
  if (!turns) return errors > 0 ? 1 : null;
  return errors / turns;
}
