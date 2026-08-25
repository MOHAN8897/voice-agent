"use client";

import { useMemo, useState } from "react";
import type { SessionTraceEvent } from "@/components/live/LiveVoiceSession";
import { DevCard } from "@/components/dev/DevCard";

const KIND_COLORS: Record<string, string> = {
  call: "bg-accent/20 text-accent",
  stt: "bg-blue-500/20 text-blue-300",
  vad: "bg-yellow-500/20 text-yellow-300",
  brain: "bg-purple-500/20 text-purple-300",
  tts: "bg-green-500/20 text-green-300",
};

export function SessionTracePanel({ events }: { events: SessionTraceEvent[] }) {
  const [open, setOpen] = useState(true);
  const waterfall = useMemo(() => {
    if (events.length < 2) return [];
    const start = events[0].at;
    return events.map((e, i) => ({
      ...e,
      offsetMs: e.at - start,
      deltaMs: i === 0 ? 0 : e.at - events[i - 1].at,
    }));
  }, [events]);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <DevCard title="Event stream" description="Live session trace">
        <button
          type="button"
          className="mb-3 text-xs text-accent"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "Collapse" : "Expand"} trace drawer
        </button>
        {open && (
          <ul className="max-h-64 space-y-1 overflow-y-auto font-mono text-[11px]">
            {events.length === 0 ? (
              <li className="text-text-muted">Start a session to see events.</li>
            ) : (
              events.map((e, i) => (
                <li key={`${e.at}-${i}`} className="flex gap-2 text-text-muted">
                  <span className={`rounded px-1 ${KIND_COLORS[e.kind] || "bg-surface-raised"}`}>{e.kind}</span>
                  <span>{e.detail}</span>
                </li>
              ))
            )}
          </ul>
        )}
      </DevCard>

      <DevCard title="Latency waterfall" description="Relative offsets from first event">
        <div className="space-y-2">
          {waterfall.length === 0 ? (
            <p className="text-sm text-text-muted">Waterfall appears after session events.</p>
          ) : (
            waterfall.map((e, i) => (
              <div key={`${e.at}-${i}`} className="flex items-center gap-3 text-xs">
                <span className="w-16 font-mono text-text-subtle">{e.offsetMs}ms</span>
                <div
                  className="h-2 rounded bg-accent/60"
                  style={{ width: `${Math.min(100, Math.max(8, e.deltaMs / 4))}%` }}
                />
                <span className="text-text-muted">{e.kind}</span>
              </div>
            ))
          )}
        </div>
      </DevCard>
    </div>
  );
}
